"""
Download character render images (CSPs) from dragdown.wiki for Rivals of Aether 2.

The character roster is discovered from the wiki rather than hardcoded, so a
newly released character is picked up without a code change. For each character
we union two MediaWiki listings -- the files embedded on RoA2/{Character} and
every uploaded file named T_{Code}_* -- filter to CSP renders, and save them to:
  Resources/Character_Renders_Source/{CharacterName}/

Files already present in Character_Renders_Source or already copied to
Character_Renders/Rivals_2_Full_Renders are skipped, so re-running is cheap.

Any discovered character missing from Resources/Character_database.csv is
appended to it (disable with --no-sync-db); nothing is ever removed, so
non-wiki entries such as Armando survive.

NOTE: dragdown.wiki HTML pages are behind a Cloudflare JavaScript challenge
(they return 403 to plain HTTP clients), so we use the MediaWiki API at
/w/api.php instead -- it is not challenged and returns direct image URLs.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Dict, Iterable, List

import requests

BASE_URL = "https://dragdown.wiki"
API_URL = f"{BASE_URL}/w/api.php"
PAGE_PREFIX = "RoA2/"
RESOURCES_DIR = Path(__file__).parent.parent / "Resources"
SOURCE_DIR = RESOURCES_DIR / "Character_Renders_Source"
FULL_RENDERS_DIR = RESOURCES_DIR / "Character_Renders" / "Rivals_2_Full_Renders"
CHAR_DB_PATH = RESOURCES_DIR / "Character_database.csv"

API_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_DELAY = 0.4
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Character display name -> the 3-letter code in T_{Code}_{Skin}_{Palette}_CSP.png.
# This is an OVERRIDE table, not a list you have to maintain: codes are normally
# derived from the render filenames on the character's own wiki page (see
# derive_char_code). Add an entry only when the wiki does something the filenames
# cannot tell us -- e.g. a character page with no CSPs uploaded yet.
CHAR_CODES = {
    "Absa": "Abs", "Armando": "Arm", "Clairen": "Cla", "Etalus": "Eta",
    "Fleet": "Fle", "Forsburn": "For", "Galvan": "Gal", "Gouie": "Gou",
    "Kragg": "Kra", "La Reina": "Lar", "Loxodont": "Lox", "Maypul": "May",
    "Olympia": "Oly", "Orcane": "Orc", "Ranno": "Ran", "Slade": "Sla",
    "Wrastor": "Wra", "Zetterburn": "Zet",
}

# Used only if wiki discovery returns something implausible.
FALLBACK_CHARACTERS = (
    "Absa", "Clairen", "Etalus", "Fleet", "Forsburn", "Galvan", "Gouie",
    "Kragg", "La Reina", "Loxodont", "Maypul", "Olympia", "Orcane", "Ranno",
    "Slade", "Wrastor", "Zetterburn",
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "RoA2-render-downloader/2.0 (https://dragdown.wiki; contact: aacal050@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
})


# -- MediaWiki API ----------------------------------------------------------


def api_query(params: dict) -> Iterable[dict]:
    """Yield each response page of a paginated MediaWiki query."""
    params = dict(params)
    params.setdefault("action", "query")
    params.setdefault("format", "json")
    seen_continues = set()

    while True:
        resp = SESSION.get(API_URL, params=params, timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        yield data

        cont = data.get("continue")
        if not cont:
            return
        token = repr(sorted(cont.items()))
        if token in seen_continues:
            return  # defensive: never loop forever on a misbehaving continue
        seen_continues.add(token)
        params.update(cont)


def normalize_filename(name: str) -> str:
    """Canonical on-disk name for a wiki file title.

    Percent-decoding and NFC normalization are what stop duplicate pairs like
    T_Cla_L%C3%A9on_*.png / T_Cla_Leon_*.png from appearing on disk.
    """
    name = name.split("File:", 1)[-1]
    name = urllib.parse.unquote(name)
    name = unicodedata.normalize("NFC", name)
    return name.replace(" ", "_")


def discover_characters() -> List[str]:
    """List character pages from the wiki rather than hardcoding them.

    A page counts as a character if it is a direct child of RoA2/ and has both
    a /Data and a /Matchups child. /Data alone is not enough -- RoA2/Items has
    one too -- but only characters have matchup pages.
    """
    titles: List[str] = []
    try:
        for data in api_query({"list": "allpages", "apprefix": PAGE_PREFIX,
                               "aplimit": "max"}):
            titles.extend(p["title"] for p in data.get("query", {}).get("allpages", []))
    except Exception as exc:
        print(f"  [error] character discovery failed: {exc}")
        return list(FALLBACK_CHARACTERS)

    tops = {t[len(PAGE_PREFIX):] for t in titles
            if t.startswith(PAGE_PREFIX) and t.count("/") == 1}

    def children_named(suffix: str) -> set:
        tail = "/" + suffix
        return {t[len(PAGE_PREFIX):-len(tail)] for t in titles
                if t.startswith(PAGE_PREFIX) and t.endswith(tail)}

    candidates = tops & children_named("Data") & children_named("Matchups")
    names = sorted(n.replace("_", " ") for n in candidates if n)

    if len(names) < 10:
        print(f"  Discovery returned only {len(names)} character(s); using fallback list.")
        return list(FALLBACK_CHARACTERS)

    return names


CSP_PREFIX_RE = re.compile(r"^T_([A-Za-z]+)_.*CSP.*\.png$", re.IGNORECASE)


def derive_char_code(images: Iterable[str]) -> str | None:
    """Read the T_Xxx code straight off the character's own render filenames.

    Every CSP on a character page shares one prefix, so the most common wins;
    counting rather than taking the first survives a stray foreign file being
    embedded on the page. Returns None if the page has no CSPs to learn from.
    """
    counts = collections.Counter()
    for name in images:
        match = CSP_PREFIX_RE.match(name)
        if match:
            counts[match.group(1)] += 1
    if not counts:
        return None
    # Sort by count desc, then name, so the result never depends on dict order.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def guess_char_code(display_name: str) -> str:
    """Last-resort code when the wiki gives us nothing to read.

    The convention is the first three letters of the first word -- which is
    wrong for La Reina (T_Lar_*), exactly why deriving beats guessing.
    """
    word = display_name.replace("_", " ").split()[0]
    return word[:3].capitalize()


def char_code(display_name: str, page_images: Iterable[str] | None = None) -> str:
    """The T_Xxx code for a character: override table, then derived, then guessed."""
    if display_name in CHAR_CODES:
        return CHAR_CODES[display_name]
    if page_images is not None:
        derived = derive_char_code(page_images)
        if derived:
            return derived
    return guess_char_code(display_name)


def list_page_images(slug: str) -> Dict[str, str]:
    """Files embedded on RoA2/{slug}, as {filename: url}."""
    out: Dict[str, str] = {}
    params = {
        "generator": "images",
        "titles": PAGE_PREFIX + slug,
        "gimlimit": "max",
        "prop": "imageinfo",
        "iiprop": "url",
    }
    for data in api_query(params):
        for page in data.get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo")
            if not info or not info[0].get("url"):
                continue
            out[normalize_filename(page.get("title", ""))] = info[0]["url"]
    return out


def list_prefix_images(code: str) -> Dict[str, str]:
    """Every uploaded file starting T_{code}_, as {filename: url}.

    Page-independent, and in practice a superset of list_page_images -- it
    surfaces renders that exist on the wiki but are not linked from the
    character page (e.g. T_Ran_Basketball_Grassroots_CSP.png).
    """
    out: Dict[str, str] = {}
    params = {
        "list": "allimages",
        "aiprefix": f"T_{code}_",
        "ailimit": "max",
        "aiprop": "url",
    }
    for data in api_query(params):
        for item in data.get("query", {}).get("allimages", []):
            url = item.get("url")
            if url:
                out[normalize_filename(item.get("name", ""))] = url
    return out


def get_csp_images(slug: str, character: str) -> tuple[Dict[str, str], str]:
    """Every CSP render for a character, as ({filename: url}, code).

    The page listing comes first because it is what teaches us the character's
    T_Xxx code; only then can we ask for every upload sharing that prefix.
    """
    try:
        page_images = list_page_images(slug)
    except Exception as exc:
        print(f"  [error] page images query failed: {exc}")
        page_images = {}

    code = char_code(character, page_images)

    try:
        prefix_images = list_prefix_images(code)
    except Exception as exc:
        print(f"  [error] file prefix query failed: {exc}")
        prefix_images = {}

    out: Dict[str, str] = {}
    for found in (page_images, prefix_images):
        for name, url in found.items():
            if not name.lower().endswith(".png"):
                continue
            # The CSP filter also excludes stray 3-field names like
            # T_Ran_Black.png; the prefix check prevents cross-character bleed.
            if "CSP" not in name.upper():
                continue
            if not name.startswith(f"T_{code}_"):
                continue
            out.setdefault(name, url)

    return out, code


# -- downloading ------------------------------------------------------------


def is_valid_png(path: Path) -> bool:
    """Magic bytes plus a structural check, which catches truncation."""
    try:
        with open(path, "rb") as fh:
            if fh.read(8) != PNG_MAGIC:
                return False
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def sweep_partials(root: Path) -> int:
    """Remove leftover .dl_*.part files from an interrupted run."""
    removed = 0
    if not root.is_dir():
        return 0
    for path in root.rglob(".dl_*.part"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def download_file(url: str, dest: Path, timeout: int = DOWNLOAD_TIMEOUT) -> None:
    """Fetch url to dest atomically.

    Streams to a sibling temp file and renames only after the bytes validate as
    a complete PNG, so an interrupted run can never leave a corrupt render in
    the library.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".dl_", suffix=".part")
    tmp = Path(tmp_name)

    try:
        with os.fdopen(fd, "wb") as fh:
            with SESSION.get(url, timeout=timeout, stream=True) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)

        if not is_valid_png(tmp):
            raise ValueError("downloaded file is not a valid PNG")

        os.replace(tmp, dest)  # atomic on NTFS within one volume
    finally:
        tmp.unlink(missing_ok=True)


# -- character database -----------------------------------------------------


def read_char_db() -> List[str]:
    """Character names currently listed in Character_database.csv."""
    if not CHAR_DB_PATH.is_file():
        return []
    names = []
    for line in CHAR_DB_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line.split(",")[0].strip())
    return names


def sync_char_db(characters: Iterable[str], write: bool = True) -> List[str]:
    """Append discovered characters missing from the CSV. Never removes rows."""
    known = {n.casefold() for n in read_char_db()}
    new = [c for c in characters if c.casefold() not in known]
    if not new or not write:
        return new

    text = CHAR_DB_PATH.read_text(encoding="utf-8-sig") if CHAR_DB_PATH.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(name + "\n" for name in new)
    CHAR_DB_PATH.write_text(text, encoding="utf-8")
    return new


# -- main -------------------------------------------------------------------


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download Rivals of Aether 2 CSP renders from dragdown.wiki.")
    parser.add_argument("--characters", nargs="+", metavar="NAME",
                        help="Only these characters (default: discover from the wiki).")
    parser.add_argument("--dest", type=Path, default=SOURCE_DIR,
                        help="Destination root folder.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-download files already present.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be fetched without writing files.")
    parser.add_argument("--delay", type=float, default=DOWNLOAD_DELAY,
                        help="Seconds between downloads.")
    parser.add_argument("--list-characters", action="store_true",
                        help="Print the discovered roster, flag any missing from "
                             "Character_database.csv, and exit without downloading.")
    parser.add_argument("--no-sync-db", action="store_true",
                        help="Do not add newly discovered characters to "
                             "Character_database.csv.")
    args = parser.parse_args(argv)

    if args.list_characters:
        characters = discover_characters()
        print(f"Discovered {len(characters)} character(s) on the wiki:")
        for name in characters:
            print(f"  {name}")
        missing = sync_char_db(characters, write=False)
        if missing:
            print(f"\nNot in Character_database.csv: {', '.join(missing)}")
            print("Run Download Renders to add them and fetch their renders.")
        else:
            print("\nCharacter_database.csv is up to date.")
        return 0

    removed = sweep_partials(args.dest)
    if removed:
        print(f"Cleaned up {removed} partial download(s) from an earlier run.")

    if args.characters:
        characters = list(args.characters)
    else:
        print("Discovering characters from the wiki...")
        characters = discover_characters()
        print(f"Found {len(characters)}: {', '.join(characters)}")

        added = sync_char_db(characters, write=not args.no_sync_db)
        if added and not args.no_sync_db:
            print(f"NEW CHARACTER(S) added to Character_database.csv: {', '.join(added)}")
        elif added:
            print(f"NEW CHARACTER(S) missing from Character_database.csv: {', '.join(added)}")

    downloaded = skipped = failed = 0

    for character in characters:
        slug = character.replace(" ", "_")

        print("\n" + "=" * 50)
        print(f"  {character}")
        print("=" * 50)

        images, code = get_csp_images(slug, character)
        if not images:
            print(f"  No CSP images found (code T_{code}_).")
            continue

        print(f"  Found {len(images)} image(s) [code T_{code}_]")
        char_dir = args.dest / character

        for filename, img_url in sorted(images.items()):
            dest = char_dir / filename

            if not args.overwrite and (dest.exists() or (FULL_RENDERS_DIR / filename).exists()):
                skipped += 1
                print(f"  [skip] {filename}")
                continue

            if args.dry_run:
                downloaded += 1
                print(f"  [dl]   {filename} (dry run)")
                continue

            try:
                download_file(img_url, dest)
            except Exception as exc:
                failed += 1
                print(f"  [error] {filename}: download failed - {exc}")
                continue

            downloaded += 1
            print(f"  [dl]   {filename}")
            if args.delay > 0:
                time.sleep(args.delay)

    print(f"\nDone. {downloaded} downloaded, {skipped} skipped, {failed} failed.")
    return 1 if failed and not downloaded else 0


if __name__ == "__main__":
    sys.exit(main())
