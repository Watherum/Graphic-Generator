"""
Download character render images (CSPs) from dragdown.wiki for Rivals of Aether 2.

For each character, fetches their wiki page, finds all image files in the gallery,
and saves them to:
  Resources/Character_Renders_Source/{CharacterName}/

Already-downloaded files are skipped.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from pathlib import Path
from typing import Optional, List

BASE_URL = "https://dragdown.wiki"
SOURCE_DIR = Path(__file__).parent.parent / "Resources" / "Character_Renders_Source"

# Character name -> wiki URL slug (spaces become underscores)
CHARACTERS = [
    "Ranno", "Clairen", "Fleet", "Kragg", "Loxodont", "Maypul",
    "Wrastor", "Zetterburn", "Orcane", "Forsburn", "Etalus",
    "Olympia", "Absa", "Galvan", "La_Reina", "Armando", "Slade",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
})


def fetch_html(url: str, referer: str = BASE_URL) -> BeautifulSoup:
    SESSION.headers["Referer"] = referer
    resp = SESSION.get(url, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def get_image_filenames(char_slug: str) -> List[str]:
    """Return all image filenames linked from the character's wiki page."""
    url = f"{BASE_URL}/wiki/RoA2/{char_slug}"
    soup = fetch_html(url, referer=f"{BASE_URL}/wiki/RoA2")

    filenames = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"/wiki/File:.*CSP.*\.png", re.IGNORECASE)):
        filename = a["href"].split("/wiki/File:")[-1]
        if filename not in seen:
            seen.add(filename)
            filenames.append(filename)

    return filenames


def get_direct_url(filename: str, char_page_url: str) -> Optional[str]:
    """Resolve a wiki File: page to the direct image download URL."""
    file_page_url = f"{BASE_URL}/wiki/File:{filename}"
    soup = fetch_html(file_page_url, referer=char_page_url)

    # MediaWiki puts the original-file link inside div.fullMedia
    full_media = soup.find("div", class_="fullMedia")
    if full_media:
        a = full_media.find("a")
        if a and a.get("href"):
            href = a["href"]
            if href.startswith("//"):
                return "https:" + href
            if href.startswith("/"):
                return BASE_URL + href
            return href

    # Fallback: find an <img> whose src contains the filename stem
    stem = filename.rsplit(".", 1)[0]
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if stem in src:
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                return BASE_URL + src
            return src

    return None


def download_file(url: str, dest: Path) -> None:
    SESSION.headers["Referer"] = BASE_URL
    resp = SESSION.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=16384):
            f.write(chunk)


def main() -> None:
    for char_slug in CHARACTERS:
        char_display = char_slug.replace("_", " ")
        char_dir = SOURCE_DIR / char_display
        char_page_url = f"{BASE_URL}/wiki/RoA2/{char_slug}"

        print(f"\n{'='*50}")
        print(f"  {char_display}")
        print(f"{'='*50}")

        try:
            filenames = get_image_filenames(char_slug)
        except Exception as e:
            print(f"  ERROR fetching page: {e}")
            continue

        if not filenames:
            print("  No images found on page.")
            continue

        print(f"  Found {len(filenames)} image(s)")
        char_dir.mkdir(parents=True, exist_ok=True)

        for filename in filenames:
            dest = char_dir / filename

            if dest.exists():
                print(f"  [skip] {filename}")
                continue

            try:
                img_url = get_direct_url(filename, char_page_url)
            except Exception as e:
                print(f"  [error] {filename}: could not fetch File page — {e}")
                continue

            if not img_url:
                print(f"  [error] {filename}: could not resolve direct URL")
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
