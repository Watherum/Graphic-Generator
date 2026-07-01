"""
create_release.py — Build a generator release zip (Rivals 2, Ultimate, or Melee).

Usage:
    python create_release.py                        # Rivals 2, exclude Character Renders (default)
    python create_release.py --game melee            # Melee generator
    python create_release.py --game ultimate         # Ultimate generator
    python create_release.py --include-renders       # include Character Renders (~100s MB)
    python create_release.py --out my_name.zip       # custom output filename
"""

import argparse
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Per-game settings: generator folder name, user-specific state files to skip,
# and the default zip filename.
GAMES = {
    "rivals": {
        "dir": "Rivals_2_Generator",
        "exclude_files": {
            "rivals_gui_settings.json",
            "rivals_custom_events.json",
            "rivals_event_configs.json",
            "CLAUDE.md",
            "missing.log",
        },
        "default_out": "Rivals2Generator.zip",
    },
    "ultimate": {
        "dir": "Ultimate_Generator",
        "exclude_files": {
            "ultimate_gui_settings.json",
            "ultimate_custom_events.json",
            "ultimate_event_configs.json",
            "CLAUDE.md",
            "missing.log",
        },
        "default_out": "UltimateGenerator.zip",
    },
    "melee": {
        "dir": "Melee_Generator",
        "exclude_files": {
            "melee_gui_settings.json",
            "melee_custom_events.json",
            "melee_event_configs.json",
            "CLAUDE.md",
            "missing.log",
        },
        "default_out": "MeleeGenerator.zip",
    },
}

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

# Folders inside the generator whose *contents* are excluded.
# The folders themselves won't appear in the zip (the app creates them on first run).
EXCLUDE_OUTPUT_DIRS = {
    "Youtube_Thumbnails",
    "Results_Posts",
}

# Relative paths (from the generator root) that are always excluded regardless
# of where they appear — e.g. licensed fonts that can't be redistributed.
EXCLUDE_RELATIVE_PATHS = {
    Path("Resources/Fonts/HKModular-Bold.otf"),
    Path("Resources/Fonts/HKModular-BoldRounded.otf"),
}

# Directory name fragments that are always excluded wherever they appear.
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".git",
}


def should_exclude(rel_path: Path, include_renders: bool, exclude_files: set) -> bool:
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
    if len(parts) == 1 and rel_path.name in exclude_files:
        return True

    # Skip licensed/non-redistributable files by relative path
    if rel_path in EXCLUDE_RELATIVE_PATHS:
        return True

    # Skip .gitkeep placeholder files
    if rel_path.name == ".gitkeep":
        return True

    return False


def build_zip(output_path: Path, include_renders: bool, game: dict):
    generator_dir = ROOT / game["dir"]

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

        # Generator tree
        for path in sorted(generator_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(generator_dir)
            if should_exclude(rel, include_renders, game["exclude_files"]):
                continue
            arcname = Path(game["dir"]) / rel
            zf.write(path, arcname)
            print(f"  + {arcname}")
            file_count += 1

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nDone — {file_count} files, {size_mb:.1f} MB → {output_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Build a generator release zip.")
    parser.add_argument(
        "--game", choices=sorted(GAMES), default="rivals",
        help="Which generator to package (default: rivals).",
    )
    parser.add_argument(
        "--include-renders", action="store_true",
        help="Include Character Renders folder (adds ~100s MB).",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output zip filename (default: per-game, e.g. Rivals2Generator.zip).",
    )
    args = parser.parse_args()

    game = GAMES[args.game]
    output_path = ROOT / (args.out or game["default_out"])
    if output_path.exists():
        print(f"Overwriting existing {output_path.name}")

    renders_note = "including" if args.include_renders else "excluding"
    print(f"Building {args.game} release zip ({renders_note} Character Renders)...\n")
    build_zip(output_path, args.include_renders, game)


if __name__ == "__main__":
    main()
