"""
Download character render images (CSPs) from dragdown.wiki for Rivals of Aether 2.

For each character, queries the MediaWiki API for all images on their wiki page,
filters down to CSP renders, and saves them to:
  Resources/Character_Renders_Source/{CharacterName}/

Files already present in Character_Renders_Source or already copied to
Character_Renders/Rivals_2_Full_Renders are skipped.

NOTE: dragdown.wiki HTML pages are behind a Cloudflare JavaScript challenge
(they return 403 to plain HTTP clients), so we use the MediaWiki API at /w/api.php
instead — it is not challenged and returns direct image URLs in one request.
"""

import time
from pathlib import Path
from typing import Dict, List

import requests

BASE_URL = "https://dragdown.wiki"
API_URL = f"{BASE_URL}/w/api.php"
RESOURCES_DIR = Path(__file__).parent.parent / "Resources"
SOURCE_DIR = RESOURCES_DIR / "Character_Renders_Source"
FULL_RENDERS_DIR = RESOURCES_DIR / "Character_Renders" / "Rivals_2_Full_Renders"

# Character name -> wiki page slug (spaces become underscores)
CHARACTERS = [
    "Ranno", "Clairen", "Fleet", "Kragg", "Loxodont", "Maypul",
    "Wrastor", "Zetterburn", "Orcane", "Forsburn", "Etalus",
    "Olympia", "Absa", "Galvan", "La_Reina", "Armando", "Slade",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "RoA2-render-downloader/1.0 (https://dragdown.wiki; contact: aacal050@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
})


def get_csp_images(char_slug: str) -> Dict[str, str]:
    """Return {filename: direct_url} for every CSP image on the character's page.

    Uses generator=images to list all File: pages embedded on the page, plus
    prop=imageinfo to resolve each one's direct download URL in the same query.
    """
    images: Dict[str, str] = {}
    params = {
        "action": "query",
        "generator": "images",
        "titles": f"RoA2/{char_slug}",
        "gimlimit": "max",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }

    while True:
        resp = SESSION.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")  # e.g. "File:T Ran Abyss Neutral CSP.png"
            if "CSP" not in title.upper():
                continue
            info = page.get("imageinfo")
            if not info:
                continue
            url = info[0].get("url")
            if not url:
                continue
            # Use the canonical (underscored) filename from the URL, dropping the "File:" prefix.
            filename = title.split("File:", 1)[-1].replace(" ", "_")
            images[filename] = url

        # MediaWiki paginates large image lists via "continue".
        if "continue" in data:
            params.update(data["continue"])
        else:
            break

    return images


def download_file(url: str, dest: Path) -> None:
    resp = SESSION.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=16384):
            f.write(chunk)


def main() -> None:
    for char_slug in CHARACTERS:
        char_display = char_slug.replace("_", " ")
        char_dir = SOURCE_DIR / char_display

        print(f"\n{'='*50}")
        print(f"  {char_display}")
        print(f"{'='*50}")

        try:
            images = get_csp_images(char_slug)
        except Exception as e:
            print(f"  ERROR querying API: {e}")
            continue

        if not images:
            print("  No CSP images found on page.")
            continue

        print(f"  Found {len(images)} image(s)")
        char_dir.mkdir(parents=True, exist_ok=True)

        for filename, img_url in sorted(images.items()):
            dest = char_dir / filename

            if dest.exists() or (FULL_RENDERS_DIR / filename).exists():
                print(f"  [skip] {filename}")
                continue

            try:
                download_file(img_url, dest)
                print(f"  [dl]   {filename}")
                time.sleep(0.4)
            except Exception as e:
                print(f"  [error] {filename}: download failed — {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
