"""
Copies all PNG files from Resources/Character_Renders_Source/{Character}/
into Resources/Character_Renders/Rivals_2_Full_Renders/, keeping original filenames.
Files that already exist in the destination are skipped.
"""

import shutil
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent.parent
SOURCE_DIR  = SCRIPT_DIR / "Resources" / "Character_Renders_Source"
DEST_DIR    = SCRIPT_DIR / "Resources" / "Character_Renders" / "Rivals_2_Full_Renders"

DEST_DIR.mkdir(parents=True, exist_ok=True)

copied = 0
skipped = 0

for char_dir in sorted(SOURCE_DIR.iterdir()):
    if not char_dir.is_dir():
        continue

    for src in sorted(char_dir.glob("*.png")):
        dest = DEST_DIR / src.name
        if dest.exists():
            print(f"[skip] {src.name}")
            skipped += 1
        else:
            shutil.copy2(src, dest)
            print(f"[copy] {char_dir.name} / {src.name}")
            copied += 1

print(f"\nDone. {copied} copied, {skipped} skipped.")
