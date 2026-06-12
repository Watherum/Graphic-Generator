"""
create_release.py — Build a Rivals 2 Generator release zip.

Usage:
    python create_release.py                   # exclude Character Renders (default)
    python create_release.py --include-renders # include Character Renders (~100s MB)
    python create_release.py --out my_name.zip # custom output filename
"""

import argparse
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Top-level files to bundle (secrets and dev-only files are excluded)
TOP_LEVEL_FILES = [
    "README.md",
    "LICENSE.txt",
    "requirements.txt",
    "requirments_install.cmd",
    "update.cmd",
    "Sample-test-names.txt",
    "Sample-Top-8 text.txt",
    "app.example.properties",
]

# Folders inside Rivals_2_Generator whose *contents* are excluded.
# The folders themselves won't appear in the zip (the app creates them on first run).
EXCLUDE_OUTPUT_DIRS = {
    "Youtube_Thumbnails",
    "Results_Posts",
}

# Individual files inside Rivals_2_Generator to skip (user-specific state).
EXCLUDE_FILES = {
    "rivals_gui_settings.json",
    "rivals_custom_events.json",
    "CLAUDE.md",
    "missing.log",
}

# Directory name fragments that are always excluded wherever they appear.
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".git",
}


def should_exclude(rel_path: Path, include_renders: bool) -> bool:
    parts = rel_path.parts

    # Skip hidden/cache dirs anywhere in the tree
    if any(p in EXCLUDE_DIR_NAMES for p in parts):
        return True

    # Skip output folder contents
    if parts[0] in EXCLUDE_OUTPUT_DIRS:
        return True

    # Skip Vod_Names contents (event-specific match files / logs)
    if parts[0] == "Vod_Names":
        return True

    # Always exclude the source/download folder
    if "Character_Renders_Source" in parts:
        return True

    # Skip character renders unless opted in
    if not include_renders and "Character_Renders" in parts:
        return True

    # Skip individually excluded files (top-level of generator folder)
    if len(parts) == 1 and rel_path.name in EXCLUDE_FILES:
        return True

    # Skip .gitkeep placeholder files
    if rel_path.name == ".gitkeep":
        return True

    return False


def build_zip(output_path: Path, include_renders: bool):
    rivals_dir = ROOT / "Rivals_2_Generator"

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        file_count = 0

        # Top-level files
        for name in TOP_LEVEL_FILES:
            path = ROOT / name
            if path.exists():
                zf.write(path, name)
                print(f"  + {name}")
                file_count += 1
            else:
                print(f"  - {name} (not found, skipping)")

        # Rivals_2_Generator tree
        for path in sorted(rivals_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(rivals_dir)
            if should_exclude(rel, include_renders):
                continue
            arcname = Path("Rivals_2_Generator") / rel
            zf.write(path, arcname)
            print(f"  + {arcname}")
            file_count += 1

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nDone — {file_count} files, {size_mb:.1f} MB → {output_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Build Rivals 2 Generator release zip.")
    parser.add_argument(
        "--include-renders", action="store_true",
        help="Include Character Renders folder (adds ~100s MB).",
    )
    parser.add_argument(
        "--out", default="Rivals_2_Generator_Release.zip",
        help="Output zip filename (default: Rivals_2_Generator_Release.zip).",
    )
    args = parser.parse_args()

    output_path = ROOT / args.out
    if output_path.exists():
        print(f"Overwriting existing {output_path.name}")

    renders_note = "including" if args.include_renders else "excluding"
    print(f"Building release zip ({renders_note} Character Renders)...\n")
    build_zip(output_path, args.include_renders)


if __name__ == "__main__":
    main()
