#!/usr/bin/env python3
"""PySide6 GUI for the Melee_Generator toolset.

Launched via ``Launch_Melee_GUI.vbs``. This replaced the original Tkinter GUI,
mirroring the design of the Rivals_2_Generator Qt GUI.

The main game-specific difference from Rivals: costume alts are numbered 1-8
(e.g. ``Fox (5).png``) rather than named skins, and the character database is a
two-column ``alias -> filename`` mapping.

Fetch/generate work runs the sibling scripts via ``QProcess``; the player/
character CSV databases and the settings / custom-events JSON files are read and
written directly.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
import datetime as _dt
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QProcess, Signal

import skin_utils
from team_utils import member_for_index, split_team
from skin_utils import (
    RENDERS_DIR,
    get_skins_for_char,
    join_pref,
    neutral_skin_for,
    preferred_stem,
    render_stem,
    skin_label,
    split_char_skin,
    split_pref,
    stem_for_label,
    strip_skins,
)

# --------------------------------------------------------------------------- #
#  Paths & constants                                                          #
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).parent.parent
REPO_ROOT = ROOT.parent            # git repo root (contains all generators)
GENERATOR_DIR = ROOT.name          # this generator's folder name (update pathspec)
PYTHON = sys.executable
THUMBNAIL_SCRIPT = ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"
FULL_RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Melee_Full_Renders"
PLAYER_DB_PATH = ROOT / "Resources" / "Player_database.csv"

#: Filled in by _thumbnail_generator on first use (see there).
_gen_module = None
CHAR_DB_PATH = ROOT / "Resources" / "Character_database.csv"
SETTINGS_PATH = ROOT / "melee_gui_settings.json"
CUSTOM_EVENTS_PATH = ROOT / "melee_custom_events.json"
#: Reserved key in the event-configs JSON holding per-VOD-file overrides.
#: Kept in step with FILE_CONFIG_KEY in populate_*_globals.py.
FILE_CONFIG_KEY = "__files__"

EVENT_CONFIGS_PATH = ROOT / "melee_event_configs.json"
# parry.gg and Challonge each need an API key; the fetchers read them from the
# Graphic Generator root (gitignored, so a fresh clone has none). Kept in step
# with PROPS_FILE in fetch_parrygg_sets.py / fetch_parrygg_top8.py and with
# challonge_api.PROPS_FILE.
APP_PROPERTIES_PATH = ROOT.parent / "app.properties"
PARRYGG_API_KEY = "parrygg.api.key"
# Challonge issues an OAuth application rather than a bare key; the legacy key
# is still honoured for accounts that were issued one before the portal changed.
# Kept in step with challonge_api.py.
CHALLONGE_CLIENT_ID = "challonge.client.id"
CHALLONGE_CLIENT_SECRET = "challonge.client.secret"
CHALLONGE_API_KEY = "challonge.api.key"
CHALLONGE_PORTAL = "https://challonge.com/settings/developer"

# Dark palette
_BG = "#1c1c1c"
_BG2 = "#2b2b2b"
_BG3 = "#3b3b3b"
_FG = "#ffffff"
_MUTED = "#999999"
_SEL = "#0078d4"
_HILITE = "#2d8cff"  # brighter blue for hover/selection highlights

# Syntax highlighting palette (VS Code "Dark+" inspired)
_SYN_COMMENT = "#6a9955"
_SYN_KEY = "#9cdcfe"
_SYN_STRING = "#ce9178"
_SYN_TAG = "#569cd6"
_SYN_NUMBER = "#b5cea8"

# The tournament sites data can be pulled from. Everything provider-specific --
# which script to run, how a slug is shaped, whether an API key is needed --
# is looked up here rather than branched on inline, so adding a third site is
# a new entry plus its two fetch scripts.
#
# Ordered: the first key is the default selection.
STARTGG = "startgg"
PARRYGG = "parrygg"
CHALLONGE = "challonge"
DEFAULT_PROVIDER = STARTGG

# Events that ship with the GUI. All start.gg; a provider key is written on
# every entry so nothing has to infer it from the slug shape.
FETCH_EVENTS = [
    {
        "provider": STARTGG,
        "label": "CR Clash",
        "slug_template": "tournament/cr-clash-{n}/event/melee-singles",
        "name_template": "CR Clash {n}",
        "default_abbrev": "CRC",
        "default_num": "77",
        "default_link": "",
        "top8_file": "CR Clash Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "provider": STARTGG,
        "label": "Immortal Fight Night",
        "slug_template": "tournament/immortal-fight-night-{n}/event/melee-singles",
        "name_template": "Immortal Fight Night {n}",
        "default_abbrev": "IFN",
        "default_num": "145",
        "default_link": "",
        "top8_file": "Immortal Fight Night Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "provider": STARTGG,
        "label": "Clip It",
        "slug_template": "tournament/clip-it-{n}/event/melee-singles",
        "name_template": "Clip It {n}",
        "default_num": "3",
        "default_link": "",
        "top8_file": "Clip It Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "provider": STARTGG,
        "label": "CR Arcadian",
        "slug_template": "tournament/cr-arcadian/event/melee-singles",
        "name_template": "CR Arcadian",
        "default_abbrev": "CRA",
        "default_num": "",
        "default_link": "",
        "top8_file": "CR Arcadian Top 8 HTML.txt",
        "tweet_link": "",
    },
]

_OUTPUT_FOLDERS = ["Vod_Names", "Youtube_Thumbnails", "Top_8_Texts", "Results_Posts"]

# VOD match-line length budget. Lines longer than this get the series abbreviation
# swapped in for the full tournament name (see fetch_sets.py --abbrev).
MAX_LINE_LEN = 100

#: The Vs separator, matched case-insensitively: the fetch script writes "Vs",
#: but plenty of existing files (most of Melee's) use "vs". Word boundaries stop
#: it matching inside a player tag.
_VOD_VS_RE = re.compile(r'\bvs\b', re.IGNORECASE)
#: Capturing twin of _VOD_VS_RE, so _rewrite_vod_players puts the separator
#: back exactly as the file had it.
_VOD_VS_SPLIT_RE = re.compile(r"(\s+vs\s+)", re.IGNORECASE)
_VOD_PARENS_RE = re.compile(r'\(([^)]*)\)')
_VOD_PLAYER_RE = re.compile(r'^(.+?)\s*\(([^)]*)\)\s*$')
_STARTGG_URL_RE = re.compile(r'^https?://(?:www\.)?start\.gg/')
_EMPTY_PARENS_RE = re.compile(r'\(\s*\)')


def _vod_missing_chars(text: str) -> bool:
    """True when a match line has Vs but is missing or has empty character parens."""
    if not _VOD_VS_RE.search(text):
        return False
    parens = _VOD_PARENS_RE.findall(text)
    return not parens or any(not p.strip() for p in parens)


def _normalize_startgg_slug(value: str) -> str:
    """Strip a start.gg URL prefix, leaving just the slug path.

    A copied bracket URL carries extra path segments after the event
    ("…/event/melee-singles/brackets/1/2"), which the API rejects — keep
    only the four segments that name the event.
    """
    slug = _STARTGG_URL_RE.sub("", value).strip().strip("/").split("?")[0]
    parts = slug.split("/")
    if len(parts) > 4 and parts[0] == "tournament" and parts[2] == "event":
        slug = "/".join(parts[:4])
    return slug


def _startgg_slug_problem(value: str) -> str:
    """Explain why a slug won't fetch, or "" if it looks like an event slug.

    A tournament runs several events (Melee singles, Melee doubles, Ultimate...)
    and a fetch pulls the sets of exactly one of them, so the slug has to name
    the event — "tournament/<tournament>/event/<event>" — not just the
    tournament.
    """
    slug = _normalize_startgg_slug(value)
    if not slug:
        return "Enter the event slug (or paste the event's start.gg URL)."
    if not slug.startswith("tournament/"):
        return ("That doesn't look like an event URL. A short link like "
                "start.gg/UIFN274 points at the whole tournament — open the "
                "event's bracket page and copy the URL from there.")
    if "/event/" not in slug:
        return ("This is the tournament, not one of its events. A tournament "
                "holds several events; open the one you want (e.g. Melee "
                "Singles) and copy its URL — it ends in /event/<name>.")
    if slug.split("/event/", 1)[1].strip("/") == "":
        return "The slug ends at /event/ — it needs the event name after it."
    return ""

_PARRYGG_URL_RE = re.compile(r'^https?://(?:www\.)?parry\.gg/')


def _normalize_parrygg_slug(value: str) -> str:
    """Strip a parry.gg URL prefix, leaving just the tournament slug.

    parry.gg identifies a *tournament*, not an event -- the event is picked
    separately by index. A copied bracket URL carries extra path segments
    ("<slug>/bracket/main") which the tournament lookup does not strip, so the
    slug has to arrive bare.
    """
    slug = _PARRYGG_URL_RE.sub("", value).strip().strip("/").split("?")[0]
    return slug.split("/")[0]


def _parrygg_slug_problem(value: str) -> str:
    """Explain why a parry.gg slug won't fetch, or "" if it looks usable."""
    # Tested before normalizing: normalizing keeps only the first path segment,
    # which would reduce "tournament/x/event/y" to a plausible-looking slug.
    raw = _STARTGG_URL_RE.sub("", value).strip().strip("/")
    if raw.startswith("tournament/") or "/event/" in raw:
        return ("That is a start.gg event slug, not a parry.gg one. Switch the "
                "provider above to start.gg, or paste the parry.gg URL -- its "
                "slug is the single path segment after https://parry.gg/.")
    slug = _normalize_parrygg_slug(value)
    if not slug:
        return "Enter the tournament slug (or paste the tournament's parry.gg URL)."
    return ""


def _api_key_problem(prop: str, label: str, where: str = "") -> str:
    """Explain a missing API key, or "" when one is present.

    The fetchers warn on stderr too, but only once a fetch has been run and
    failed; saying so as soon as the provider is picked is the cheaper answer.
    ``where`` names the page the key is issued from, when there is one.
    """
    from_where = f" Get one from {where}." if where else ""
    try:
        text = APP_PROPERTIES_PATH.read_text(encoding="utf-8")
    except OSError:
        return (f"{label} needs an API key. Create {APP_PROPERTIES_PATH.name} in "
                f"{APP_PROPERTIES_PATH.parent} with a line reading "
                f"{prop}=<your key>.{from_where}")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(prop):
            _, _, val = line.partition("=")
            if val.strip():
                return ""
    return (f"{APP_PROPERTIES_PATH} has no {prop} value. {label} "
            f"fetches will fail until one is added.{from_where}")


def _parrygg_api_key_problem() -> str:
    return _api_key_problem(PARRYGG_API_KEY, "parry.gg")


def _challonge_api_key_problem() -> str:
    """Explain missing Challonge credentials, or "" when they are present.

    Challonge is not one value like the other two. Its developer portal no
    longer issues bare v1 keys -- it issues an application, so the normal setup
    is a client id *and* secret, authorized through the OAuth client-credentials
    flow. An account that still has a v1 key may use that instead, which is why
    either is accepted; naming only one of the two would send a user with the
    other kind hunting for a setting that no longer exists.
    """
    props = {}
    try:
        for line in APP_PROPERTIES_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, val = line.partition("=")
            if sep:
                props[key.strip()] = val.strip()
    except OSError:
        return (f"Challonge needs credentials. Create {APP_PROPERTIES_PATH.name} "
                f"in {APP_PROPERTIES_PATH.parent} with {CHALLONGE_CLIENT_ID} "
                f"and {CHALLONGE_CLIENT_SECRET} from {CHALLONGE_PORTAL}.")
    if props.get(CHALLONGE_API_KEY):
        return ""
    if props.get(CHALLONGE_CLIENT_ID) and props.get(CHALLONGE_CLIENT_SECRET):
        return ""
    if props.get(CHALLONGE_CLIENT_ID) or props.get(CHALLONGE_CLIENT_SECRET):
        missing = (CHALLONGE_CLIENT_SECRET if props.get(CHALLONGE_CLIENT_ID)
                   else CHALLONGE_CLIENT_ID)
        return (f"{APP_PROPERTIES_PATH} is missing {missing}. Challonge needs "
                f"both the client id and the client secret.")
    return (f"{APP_PROPERTIES_PATH} has no Challonge credentials. Create an "
            f"application at {CHALLONGE_PORTAL}, then set {CHALLONGE_CLIENT_ID} "
            f"and {CHALLONGE_CLIENT_SECRET}.")


#: Any Challonge URL, scheme optional, community subdomain captured. Kept in
#: step with challonge_api.normalize_slug, which the fetchers use.
_CHALLONGE_URL_RE = re.compile(
    r'^(?:https?://)?(?:(?P<sub>[A-Za-z0-9_-]+)\.)?challonge\.com/', re.I)

#: Bracket *view* pages a copied URL tends to end in. The segment after the
#: slug is only a community name when it is not one of these.
_CHALLONGE_VIEW_SEGMENTS = {
    "module", "standings", "log", "matches", "participants", "groups",
    "settings", "edit", "bracket", "brackets", "teams", "predictions",
}


def _normalize_challonge_slug(value: str) -> str:
    """Reduce a pasted Challonge URL to the identifier v2.1 addresses.

    Challonge addresses a *tournament*, like parry.gg. A tournament under a
    community lives at both ``myorg.challonge.com/slug`` and
    ``challonge.com/myorg/slug``, and the API joins the two with a hyphen:
    ``myorg-slug``.

    This mirrors ``challonge_api.normalize_slug`` deliberately -- the GUI must
    not import the fetchers (they pull in ``requests`` and are run as separate
    processes), and the two are small enough that keeping them in step is
    cheaper than a shared import.
    """
    text = (value or "").strip()
    match = _CHALLONGE_URL_RE.match(text)
    subdomain = ""
    if match:
        text = text[match.end():]
        sub = (match.group("sub") or "").lower()
        if sub and sub != "www":
            subdomain = sub
    text = text.split("?")[0].split("#")[0].strip("/")
    if not text:
        return ""
    parts = [p for p in text.split("/") if p]
    if subdomain:
        return f"{subdomain}-{parts[0]}"
    if len(parts) >= 2 and parts[1].lower() not in _CHALLONGE_VIEW_SEGMENTS:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]


def _challonge_slug_problem(value: str) -> str:
    """Explain why a Challonge slug won't fetch, or "" if it looks usable."""
    # Tested before normalizing, for the parry.gg reason: normalizing keeps only
    # the leading path segments, so a start.gg event slug pasted here would
    # survive as a plausible-looking "tournament-foo" and save silently.
    raw = _STARTGG_URL_RE.sub("", value).strip().strip("/")
    if raw.startswith("tournament/") or "/event/" in raw:
        return ("That is a start.gg event slug, not a Challonge one. Switch the "
                "provider above to start.gg, or paste the Challonge URL -- its "
                "slug is the path segment after https://challonge.com/.")
    if _PARRYGG_URL_RE.match(value.strip()):
        return ("That is a parry.gg URL. Switch the provider above to parry.gg, "
                "or paste the Challonge URL instead.")
    slug = _normalize_challonge_slug(value)
    if not slug:
        return "Enter the tournament slug (or paste the tournament's Challonge URL)."
    return ""


# Per-provider behaviour. The positional argument names different things per
# site: start.gg addresses one event directly, while parry.gg and Challonge
# address a tournament -- parry then picks the event inside it by index, which
# is why only parry rows show an Event box.
#
# "note" is a standing caveat about the provider itself, shown under the
# dropdown whether or not anything is wrong. It is where Challonge's hard
# limits live, since neither is a transient error a fetch could report.
#
# "posts_platforms" drives the buttons on the Generate Posts tab, because
# what a results post can say depends on what the site knows about players:
# start.gg and parry.gg can both name handles, so they get a button each for
# Twitter and Discord, while Challonge has no social accounts at all and gets
# a single "Generate Post" that writes plain tags. "posts_note" says so on the
# tab, so an empty-looking post reads as a limit of the site rather than a bug.
PROVIDERS = {
    STARTGG: {
        "label": "start.gg",
        "sets_script": "fetch_sets.py",
        "top8_script": "fetch_startgg_top8.py",
        "normalize": _normalize_startgg_slug,
        "problem": _startgg_slug_problem,
        "needs_event_index": False,
        "posts_script": "fetch_results_tweet.py",
        "posts_platforms": [("twitter", "Fetch Twitter"),
                            ("discord", "Fetch Discord")],
        "posts_note": "",
        "api_key_problem": None,
        "slug_label": "Event URL:",
        "slug_placeholder": "start.gg/tournament/my-tournament-{n}/event/melee-singles",
        "slug_tooltip": ("The event's own start.gg URL or slug, ending in /event/<name>.\n"
                         "Put {n} where the event number goes so the entry can be "
                         "reused week to week."),
        "slug_hint": "event URL or slug, ending in /event/\u2026  \u00b7  use {n} for the event number",
        "intro": ("Adds one event from a tournament \u2014 the Melee singles bracket, "
                  "say \u2014 not the whole tournament. Open that event's page on "
                  "start.gg and paste its URL below; a tournament with several "
                  "events needs one entry each."),
        "note": "",
    },
    PARRYGG: {
        "label": "parry.gg",
        "sets_script": "fetch_parrygg_sets.py",
        "top8_script": "fetch_parrygg_top8.py",
        "normalize": _normalize_parrygg_slug,
        "problem": _parrygg_slug_problem,
        "needs_event_index": True,
        "posts_script": "fetch_parrygg_post.py",
        "posts_platforms": [("twitter", "Fetch Twitter"),
                            ("discord", "Fetch Discord")],
        "posts_note": ("Discord handles come from each player's linked "
                       "account. parry.gg stores no Twitter accounts of its "
                       "own, so a Twitter post reads the handle off the "
                       "player's linked start.gg account instead; anyone who "
                       "linked neither is listed by tag."),
        "api_key_problem": _parrygg_api_key_problem,
        "slug_label": "Tournament URL:",
        "slug_placeholder": "parry.gg/my-tournament-3-14-2026-019c9aeb",
        "slug_tooltip": ("The tournament's parry.gg URL, or just its slug -- the "
                         "single path segment after https://parry.gg/.\n"
                         "Put {n} where an event number goes if the slug carries one."),
        "slug_hint": "tournament URL or slug  \u00b7  the event within it is picked below",
        "intro": ("parry.gg addresses a whole tournament, then picks one event "
                  "inside it by number \u2014 so paste the tournament URL and set "
                  "Event to 0 for its first event, 1 for its second, and so on. "
                  "Needs an API key in app.properties."),
        "note": "",
    },
    CHALLONGE: {
        "label": "Challonge",
        "sets_script": "fetch_challonge_sets.py",
        "top8_script": "fetch_challonge_top8.py",
        "normalize": _normalize_challonge_slug,
        "problem": _challonge_slug_problem,
        "needs_event_index": False,
        "posts_script": "fetch_challonge_post.py",
        "posts_platforms": [("generic", "Generate Post")],
        "posts_note": ("Challonge stores no social accounts of any kind, so "
                       "the post lists plain tags. Standings need the bracket "
                       "to be finalized on challonge.com."),
        "api_key_problem": _challonge_api_key_problem,
        "slug_label": "Tournament URL:",
        "slug_placeholder": "challonge.com/my-weekly-{n}",
        "slug_tooltip": ("The tournament's Challonge URL, or just its slug -- the "
                         "path segment after https://challonge.com/.\n"
                         "A community bracket (myorg.challonge.com/my-weekly) "
                         "works too; the API addresses it as myorg-my-weekly, "
                         "which is what this box will be rewritten to.\n"
                         "Put {n} where the tournament number goes so the entry "
                         "can be reused week to week."),
        "slug_hint": "tournament URL or slug  ·  use {n} for the tournament number",
        "intro": ("Challonge addresses a whole tournament — paste its URL "
                  "below. A community bracket at myorg.challonge.com/my-weekly "
                  "works as well. Needs challonge.client.id and "
                  "challonge.client.secret in app.properties — create an "
                  "application at challonge.com/settings/developer to get "
                  "them."),
        # Neither limit is a transient failure a fetch could report, so both are
        # said up front rather than after a fetch has produced odd-looking output.
        "note": ("Challonge reports no character data at all, so every VOD line "
                 "arrives with empty ( ) — fill them in on the Generate "
                 "Thumbnails tab. It also reports no round names and no "
                 "participant counts: round names are worked out from the "
                 "bracket's shape, and a doubles team may not split correctly, "
                 "so check any team line by hand. Results posts are start.gg "
                 "only. The free tier allows 500 API requests a month; a "
                 "fetch spends a few of them (more for a large bracket), so "
                 "the budget is generous but not unlimited."),
    },
}


def provider_of(entry: dict) -> str:
    """The provider an event belongs to, defaulting to start.gg.

    Every saved event predates the provider key, and all of them are start.gg,
    so an absent key reads as start.gg and the saved events file needs no
    migration.
    """
    provider = entry.get("provider") or DEFAULT_PROVIDER
    return provider if provider in PROVIDERS else DEFAULT_PROVIDER


def _split_vod_line(line: str):
    """Split a match line into (prefix, players_section, suffix).

    The players section is what sits between the event/round and the trailing
    game tag. Both line formats put " - " immediately before player one, so the
    last such separator before the "Vs" is the boundary -- which is what makes
    this work for the older "{Event} {Round} - ..." files as well as the current
    "{Event} - {Round} - ..." ones. Returns None when there is no "Vs".
    """
    tag_idx = line.rfind(" - ")
    body = line[:tag_idx] if tag_idx != -1 else line
    suffix = line[tag_idx:] if tag_idx != -1 else ""
    m = _VOD_VS_RE.search(body)
    if not m:
        return None
    idx = body.rfind(" - ", 0, m.start())
    if idx == -1:
        return "", body, suffix
    return body[:idx + 3], body[idx + 3:], suffix


def _parse_vod_player_skins(line: str) -> list:
    """Return [(player_name, [(char, costume_or_None), ...]), ...] for a match line.

    A character may carry a per-set costume after a colon ("Mario:5").
    """
    split = _split_vod_line(line)
    if split is None:
        return []
    _prefix, section, _suffix = split
    results = []
    for player_str in _VOD_VS_RE.split(section):
        m = _VOD_PLAYER_RE.match(player_str.strip())
        if m:
            name = m.group(1).strip()
            chars = [split_char_skin(c) for c in m.group(2).split(",") if c.strip()]
            results.append((name, chars))
    return results


_VOD_CHARS_RE = re.compile(r'\s*\([^)]*\)')


def _strip_char_lists(line: str) -> str:
    """Drop the "(chars)" after every player -- the second way a title is shortened.

    Only the player section is touched (between the round and the trailing game
    suffix), so parentheses in an event name (``Some Event (Online) 12``) or a
    round (``Pools (A) Wnrs Rd 2``) survive. A line that does not split into the
    usual four fields is returned unchanged rather than mangled, and so is one
    that would be left with no players at all.
    """
    parts = line.split(" - ")
    if len(parts) < 4:
        return line
    middle = _VOD_CHARS_RE.sub("", " - ".join(parts[2:-1])).strip()
    if not middle:
        return line
    return " - ".join(parts[:2] + [middle, parts[-1]])


def _vod_shorten_flags(plain: str, copied: str) -> tuple[bool, bool]:
    """(abbreviated, characters dropped) for a copied line.

    Skins coming off is neither -- they are never part of a title, so nothing was
    given up by removing them. Nor is the '# ABBREV:' header shedding its prefix:
    copying it hands back the abbreviation it exists to carry, which is the whole
    value rather than a shortened one.
    """
    if _is_abbrev_line(plain):
        return (False, False)
    return (plain.split(" - ")[0] != copied.split(" - ")[0],
            "(" in plain and "(" not in copied)


def _vod_shorten_note(plain: str, copied: str) -> str:
    """The same as words: '', 'abbreviated', 'characters dropped', or both."""
    abbreviated, dropped = _vod_shorten_flags(plain, copied)
    return ", ".join(b for b, on in
                     (("abbreviated", abbreviated), ("characters dropped", dropped)) if on)


def _expand_team(name: str, chars: list) -> list:
    """Split a doubles tag into one entry per member: [(member, [(char, skin)])].

    A team has no row of its own in the player database -- each member does --
    so everything that reads or writes that database works on members, never on
    the "shane,THE PIZZA GUY" tag the VOD line carries. Character *i* belongs to
    member *i*; a member playing two characters gets both. A singles tag comes
    back unchanged, so callers need no special case.
    """
    members = split_team(name)
    if len(members) < 2:
        return [(name, chars)]
    buckets: list = [[] for _ in members]
    for i, entry in enumerate(chars):
        buckets[min(i, len(members) - 1)].append(entry)
    return list(zip(members, buckets))


def _parse_vod_team_members(line: str) -> list:
    """:func:`_parse_vod_player_skins` with every doubles tag split into members."""
    out: list = []
    for name, chars in _parse_vod_player_skins(line):
        out.extend(_expand_team(name, chars))
    return out


def _parse_vod_players(line: str) -> list[tuple[str, list[str]]]:
    """Extract [(player_name, [char, ...]), ...] from a match line, costumes stripped."""
    return [(name, [c for c, _ in chars])
            for name, chars in _parse_vod_player_skins(line)]


def _rewrite_vod_players(line: str, per_player: list) -> str:
    """Rebuild a match line with new character lists.

    ``per_player`` is [[(char, costume_or_None), ...], ...] in the same order
    :func:`_parse_vod_player_skins` returned them. Everything outside the
    parentheses (event, round, player names, game suffix) is left untouched.
    """
    split = _split_vod_line(line)
    if split is None:
        return line
    prefix, section, suffix = split
    # Keep the "Vs" separator exactly as written by splitting on a capture group.
    chunks = _VOD_VS_SPLIT_RE.split(section)
    out = []
    slot = 0
    for chunk in chunks:
        m = _VOD_PLAYER_RE.match(chunk.strip())
        if m and slot < len(per_player):
            name = m.group(1).strip()
            chars = ", ".join(f"{c}:{sk}" if sk else c for c, sk in per_player[slot])
            out.append(f"{name} ({chars})")
            slot += 1
        else:
            out.append(chunk)
    return prefix + "".join(out) + suffix


try:
    import populate_melee_globals as _pg
except ImportError:
    _pg = None


# --------------------------------------------------------------------------- #
#  Pure helpers (database parsing, render lookups, dispatcher reflection)      #
# --------------------------------------------------------------------------- #
def _ordinal_date(date) -> str:
    if not isinstance(date, _dt.date):
        return ""
    day = date.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return date.strftime(f"%B {day}{suffix}")


def _base_event_props(series: str) -> dict:
    """Default property dict for a series, via the populate_melee_globals
    dispatcher. Used to pre-fill the Thumbnail Config form. Longer prefixes are
    checked first so e.g. 'AWG Just Tech It' wins over 'AWG'."""
    if _pg is None:
        return {}
    try:
        if series.startswith('Quarantainment'):
            return _pg.setGlobalsQuarantainment(series)
        elif series.startswith('Students x Treehouse'):
            return _pg.setGlobalsSxT(series)
        elif series.startswith('Fro Fridays'):
            return _pg.setGlobalsFro(series)
        elif series.startswith('AWG Just Tech It'):
            return _pg.setGlobalsJustTechIt(series)
        elif series.startswith('Immortal Fight Night') or series.startswith('NYS HS Esports Showcase'):
            return _pg.setGlobalsIFN(series)
        elif series.startswith('Clip It'):
            return _pg.setGlobalsClipIt(series)
        elif series.startswith('CR Clash'):
            return _pg.setGlobalsCRClash(series)
        elif series.startswith('CR Arcadian'):
            return _pg.setGlobalsCRArcadian(series)
        elif series.startswith('AWG'):
            return _pg.setGlobalsAWG(series)
        elif series.startswith('C2C Finale'):
            return _pg.setGlobalsC2C(series)
        elif series.startswith('Catman'):
            return _pg.setGlobalsCatman(series)
        elif series.startswith('IzAw Sub') or series.startswith('Big Forhead Plays'):
            return _pg.setGlobalsIzAw(series)
        else:
            return _pg.set_default_properties(series)
    except Exception:
        return {}
def get_characters_from_renders() -> list[str]:
    """Derive character names from the renders folder by stripping the ' (N)' suffix."""
    if not RENDERS_DIR.exists():
        return []
    names: set[str] = set()
    for f in RENDERS_DIR.glob("*.png"):
        names.add(re.sub(r"\s*\(\d+\)$", "", f.stem))
    return sorted(names)


def get_alts_for_char(char_name: str) -> list[str]:
    """Available costume numbers for a character, read from the renders folder.

    Kept as a name because the GUI uses it throughout; the implementation lives
    in skin_utils so the generator resolves costumes from the same list.
    """
    return get_skins_for_char(char_name)


def load_player_db() -> tuple[list[str], dict[str, list[tuple[str, str]]]]:
    header_comments: list[str] = []
    players: dict[str, list[tuple[str, str]]] = {}
    try:
        lines = PLAYER_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], {}
    in_players = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if not in_players:
                header_comments.append(line)
            continue
        in_players = True
        parts = stripped.split(",")
        result: list[str] = []
        for p in parts:
            p = p.strip()
            if p.startswith("#"):
                break
            result.append(p)
        while result and not result[-1]:
            result.pop()
        if not result:
            continue
        name = result[0]
        chars: list[tuple[str, str]] = []
        for i in range(1, len(result) - 1, 2):
            char = result[i]
            alt = result[i + 1] if i + 1 < len(result) else ""
            if char:
                chars.append((char, alt))
        players[name] = chars
    return header_comments, players


def save_player_db(header_comments: list[str], players: dict[str, list[tuple[str, str]]]) -> None:
    lines = list(header_comments)
    for name, chars in players.items():
        parts = [name]
        for char, alt in chars:
            parts += [char, alt]
        lines.append(",".join(parts))
    PLAYER_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_char_db() -> tuple[list[str], list[tuple[str, str]]]:
    """Two-column character DB: returns (header_lines, [(alias, filename), ...])."""
    headers: list[str] = []
    entries: list[tuple[str, str]] = []
    try:
        lines = CHAR_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            headers.append(line)
        else:
            parts = [p.strip() for p in stripped.split(",", 1)]
            if len(parts) == 2:
                entries.append((parts[0], parts[1]))
    return headers, entries


def save_char_db(headers: list[str], entries: list[tuple[str, str]]) -> None:
    lines = list(headers)
    for alias, filename in entries:
        lines.append(f"{alias},{filename}")
    CHAR_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_thumbnail_events() -> list[tuple[str, str]]:
    """Parse startswith() calls from the dispatcher in generate_melee_thumbnails.py."""
    try:
        source = THUMBNAIL_SCRIPT.read_text(encoding="utf-8")
        names = re.findall(r"weekly_event\.startswith\('([^']+)'\)", source)
        return [(name, f"{name} {{n}}") for name in names]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
#  Dark stylesheet                                                             #
# --------------------------------------------------------------------------- #
def _make_check_icon() -> str:
    """Render a white checkmark PNG to a temp file for the checked-checkbox
    indicator and return a QSS-safe (forward-slash) path."""
    import tempfile
    path = Path(tempfile.gettempdir()) / "melee_qt_check.png"
    img = QtGui.QImage(16, 16, QtGui.QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    pen = QtGui.QPen(QtGui.QColor("#ffffff"), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QtCore.QPointF(3.5, 8.5), QtCore.QPointF(6.5, 11.5),
                    QtCore.QPointF(12.5, 4.5)])
    p.end()
    try:
        img.save(str(path), "PNG")
    except Exception:
        return ""
    return path.as_posix()


_CHECK_URL = _make_check_icon()

STYLESHEET = f"""
* {{ outline: 0; }}
QWidget {{
    background-color: {_BG2};
    color: {_FG};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background-color: {_BG}; }}
QScrollArea {{ border: 0; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {_MUTED}; }}
QLabel#warning {{ color: #E08000; }}
QLabel#heading {{ font-weight: 600; font-size: 11pt; }}

QGroupBox {{
    border: 1px solid {_BG3};
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 8px 8px 8px;
    background-color: {_BG2};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {_MUTED};
}}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 3px 5px;
    selection-background-color: {_SEL};
}}
QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus {{ border: 1px solid {_SEL}; }}
QPlainTextEdit, QTextEdit {{ font-family: "Consolas"; font-size: 10pt; }}

QComboBox {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 3px 5px;
}}
QComboBox:focus {{ border: 1px solid {_SEL}; }}
QComboBox QAbstractItemView {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    outline: 0;
    selection-background-color: {_HILITE};
    selection-color: #ffffff;
}}

QPushButton {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{ background-color: #474747; }}
QPushButton:pressed {{ background-color: #525252; }}
QPushButton:disabled {{ color: {_MUTED}; background-color: #303030; }}
QPushButton#accent {{
    background-color: {_SEL};
    border: 1px solid {_SEL};
    font-weight: 600;
}}
QPushButton#accent:hover {{ background-color: #1a86dd; }}
QPushButton#tool {{
    padding: 0;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    border-radius: 6px;
    font-size: 16px;
    color: {_MUTED};
}}
QPushButton#tool:hover {{
    color: {_FG};
    background-color: #474747;
    border-color: {_HILITE};
}}
QPushButton#tool:pressed {{ background-color: #525252; }}

QTabWidget::pane {{ border: 0; background-color: {_BG}; }}
QTabBar::tab {{
    background-color: {_BG2};
    color: {_MUTED};
    padding: 8px 16px;
    border: 0;
}}
QTabBar::tab:selected {{ color: {_FG}; border-bottom: 2px solid {_SEL}; }}
QTabBar::tab:hover {{ color: {_FG}; }}

QListWidget, QTreeWidget, QTableView, QListView {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    selection-background-color: {_SEL};
    selection-color: {_FG};
}}
QHeaderView::section {{
    background-color: {_BG2};
    color: {_MUTED};
    border: 0;
    border-bottom: 1px solid #4a4a4a;
    padding: 4px;
}}
QTableView {{ gridline-color: #353535; }}

QCheckBox {{ background: transparent; spacing: 7px; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #7a7a7a;
    border-radius: 3px;
    background-color: {_BG3};
}}
QCheckBox::indicator:hover {{ border-color: {_HILITE}; }}
QCheckBox::indicator:checked {{
    background-color: {_HILITE};
    border-color: {_HILITE};
    image: url({_CHECK_URL});
}}
QCheckBox::indicator:disabled {{ border-color: #4a4a4a; background-color: #303030; }}
QScrollBar:vertical {{ background: {_BG}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #4a4a4a; border-radius: 6px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #5a5a5a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {_BG}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #4a4a4a; border-radius: 6px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{ background: {_BG2}; }}
QToolButton {{ background: transparent; border: 0; padding: 2px; }}
QToolButton:hover {{ color: {_SEL}; }}
"""


# --------------------------------------------------------------------------- #
#  Reusable widgets                                                            #
# --------------------------------------------------------------------------- #
class _NoWheelSlider(QtWidgets.QSlider):
    """A slider that lets the wheel scroll the page instead of moving the handle.

    These sit inside a QScrollArea, where a widget that consumes the wheel makes
    the section unscrollable and silently edits values as the user scrolls past.
    Ignoring the event propagates it to the scroll area; the handle still responds
    to dragging, arrow keys and the box beside it.
    """

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelComboBox(QtWidgets.QComboBox):
    """A combo box with the same wheel behaviour as :class:`_NoWheelSlider`."""

    def wheelEvent(self, event):
        event.ignore()


class _EditableCombo(_NoWheelComboBox):
    """An editable combo that answers the QLineEdit API of the box it replaced.

    Lets a control grow a dropdown of known values without every caller (and
    every ``textChanged`` connection) having to change with it — a value that
    is not in the list can still be typed, exactly as before.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.textChanged = self.currentTextChanged

    def text(self) -> str:
        return self.currentText()

    def setText(self, value: str):
        self.setCurrentText(value)


def _fmt_norm(value: float) -> str:
    """Trim a normalized value to something short and exact: 0.280 -> 0.28."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


class NormalizedField(QtWidgets.QWidget):
    """A drag slider paired with the exact numeric box it drives.

    Used only for the config values that live on a normalized scale -- positions
    and shifts in [-1, 1], scales and offsets in [0, 1] -- where a number is hard
    to picture but a drag is not. Font sizes, angles and colours keep their plain
    boxes.

    The box stays authoritative: a value typed beyond the slider's range is kept
    verbatim (the generator accepts it; only the slider has ends) and the handle
    simply parks at the nearest end. Callers keep using ``.edit`` as the field, so
    load/save/clear paths are unchanged.
    """

    STEPS = 1000

    def __init__(self, lo: float = -1.0, hi: float = 1.0, width: int = 60, parent=None):
        super().__init__(parent)
        self._lo, self._hi = lo, hi
        # Guards the two-way sync so neither half echoes the other back.
        self._syncing = False

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setFixedWidth(width)
        self.slider = _NoWheelSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(lo * self.STEPS), int(hi * self.STEPS))
        self.slider.setSingleStep(5)     # arrow key -> 0.005
        self.slider.setPageStep(50)      # page up/down -> 0.05
        self.slider.setMinimumWidth(60)
        self.slider.setToolTip(
            f"Drag to set ({_fmt_norm(lo)} to {_fmt_norm(hi)}), arrow keys for fine "
            "steps — or type an exact value in the box")
        lay.addWidget(self.edit)
        lay.addWidget(self.slider, 1)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)

        self.edit.textChanged.connect(self._edit_to_slider)
        self.slider.valueChanged.connect(self._slider_to_edit)

    def _home(self) -> float:
        """Where the handle sits when the box is empty: zero if the range spans it."""
        return 0.0 if self._lo <= 0.0 <= self._hi else self._lo

    def _edit_to_slider(self, text: str):
        if self._syncing:
            return
        if not text.strip():
            # Cleared (Clear Config, or a key the config doesn't set): park the
            # handle rather than leaving it pointing at a value that is gone.
            value = self._home()
        else:
            try:
                value = float(text)
            except ValueError:
                return  # half-typed ("-", "0.") — leave the handle where it is
        self._syncing = True
        clamped = max(self._lo, min(self._hi, value))
        self.slider.setValue(int(round(clamped * self.STEPS)))
        self._syncing = False

    def _slider_to_edit(self, raw: int):
        if self._syncing:
            return
        self._syncing = True
        self.edit.setText(_fmt_norm(raw / self.STEPS))
        self._syncing = False


class FlowLayout(QtWidgets.QLayout):
    """Lays items left to right, wrapping to a new row when the width runs out.

    Qt has no such layout built in; this is the standard implementation from its
    own examples. Used for the Top 8 layout-config sections, which are
    fixed-width blocks that waste a screenful of vertical space when stacked one
    per row -- side by side they reflow to however many fit.

    Every item is placed at its size hint, so children want to be fixed-size.
    """

    def __init__(self, parent=None, margin: int = 0, spacing: int = 10):
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    # -- QLayout plumbing -------------------------------------------------- #
    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    # -- height depends on width, which is the whole point ------------------ #
    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QtCore.QSize(margins.left() + margins.right(),
                                   margins.top() + margins.bottom())

    def _do_layout(self, rect, test_only: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(),
                             -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        space = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + space
            if next_x - space > area.right() and line_height > 0:
                x = area.x()
                y = y + line_height + space
                next_x = x + hint.width() + space
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class _PreviewHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the generator folder for the previews, with caching switched off.

    The Top 8 pages fetch() their data file and the player CSV, and the GUI
    rewrites both as you type. The stock handler sends Last-Modified but no
    Cache-Control, which lets Chromium apply heuristic caching and answer a
    reload with the copy from before the edit -- the preview then shows names or
    placements that are no longer in the file.
    """

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *args):
        pass  # the GUI has its own console; this would only go to stderr


class CollapsibleBox(QtWidgets.QWidget):
    """A header button that shows/hides a content area below it."""

    def __init__(self, title: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._toggle = QtWidgets.QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(not collapsed)
        self._toggle.setStyleSheet("QToolButton { font-weight: 600; color: %s; }" % _MUTED)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if not collapsed else Qt.ArrowType.RightArrow)
        self._toggle.clicked.connect(self._on_toggle)

        self.content = QtWidgets.QWidget(self)
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 6, 4, 6)
        self.content.setVisible(not collapsed)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._toggle)
        lay.addWidget(self.content)

    def _on_toggle(self, checked: bool):
        self.content.setVisible(checked)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def setExpanding(self):
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)
        self.content.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                   QtWidgets.QSizePolicy.Policy.Expanding)
        self.layout().setStretchFactor(self.content, 1)

    def addWidget(self, w):
        self.content_layout.addWidget(w)

    def addLayout(self, lay):
        self.content_layout.addLayout(lay)


class ColorField(QtWidgets.QWidget):
    """A hex line edit + colour swatch button that stay in sync."""

    def __init__(self, default: str = "#FFFFFF", width: int = 90, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.edit = QtWidgets.QLineEdit(default)
        self.edit.setFixedWidth(width)
        self.swatch = QtWidgets.QPushButton()
        self.swatch.setFixedWidth(24)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.edit)
        lay.addWidget(self.swatch)
        self.edit.textChanged.connect(self._sync)
        self.swatch.clicked.connect(self._pick)
        self._sync()

    def _sync(self):
        c = self.edit.text().strip()
        if QtGui.QColor(c).isValid():
            self.swatch.setStyleSheet(f"background-color: {c}; border: 1px solid #4a4a4a;")

    def _pick(self):
        cur = QtGui.QColor(self.edit.text().strip() or "#FFFFFF")
        col = QtWidgets.QColorDialog.getColor(cur, self, "Pick color")
        if col.isValid():
            self.edit.setText(col.name())

    def value(self) -> str:
        return self.edit.text().strip()

    def setValue(self, v: str):
        self.edit.setText(v)


def _hline(text: str = "", w: int = 70) -> QtWidgets.QLineEdit:
    e = QtWidgets.QLineEdit(text)
    e.setFixedWidth(w)
    return e


def _thumbnail_generator():
    """Import the thumbnail generator on demand.

    The config preview renders through the same functions the batch run calls,
    so it can never drift from the real output. Imported lazily because it pulls
    in Pillow, which the GUI otherwise never needs.
    """
    global _gen_module
    if _gen_module is None:
        import generate_melee_thumbnails as _m
        _gen_module = _m
    return _gen_module


def _preview_sample_chars(count: int, skip: int = 0) -> list:
    """Characters with renders on disk, for the synthetic preview matches.

    One without a render would abort the whole render with "Character not
    found", so the roster is read from the renders folder rather than from the
    character CSV, which holds only alias rows.
    """
    names = [c for c in get_characters_from_renders() if get_skins_for_char(c)]
    if not names:
        return []
    return [names[(skip + i) % len(names)] for i in range(count)]


# The VOD editor's costume preview and the gap after it. The count label in
# the filter bar borrows both, which is what puts "Filter:" directly under
# "File:".
_VOD_PREVIEW_PX = 200
_VOD_PREVIEW_GAP = 16


def _is_set_line(text: str) -> bool:
    """A real match line. Blank rows and '#' comments -- the ABBREV header
    among them -- are file bookkeeping, not sets, so they never count."""
    t = text.strip()
    return bool(t) and not t.startswith("#")


ABBREV_PREFIX = "# ABBREV:"


def _is_abbrev_line(text: str) -> bool:
    """The '# ABBREV:' header row -- the one comment with a meaning."""
    return text.strip().upper().startswith(ABBREV_PREFIX)


def _abbrev_of_line(text: str) -> str:
    """'# ABBREV: SITA 65' -> 'SITA 65'."""
    return text.split(":", 1)[1].strip() if ":" in text else ""


def _muted(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    return lbl


# --------------------------------------------------------------------------- #
#  VOD list model (virtualized — handles large match lists smoothly)          #
# --------------------------------------------------------------------------- #
class VodModel(QtCore.QAbstractTableModel):
    # cols: 0 checkbox, 1 copy, 2 move-up, 3 move-down, 4 Len, 5 match line
    HEADERS = ["", "", "", "", "Len", "Match line"]

    # Emitted whenever the content written to disk changes (line text, added,
    # deleted or reordered rows). Check-marks are UI-only and never emit.
    contentChanged = Signal()

    def __init__(self):
        super().__init__()
        self._rows: list[dict] = []  # {"checked": bool, "text": str}
        # Set by the window to its _vod_abbrev_line, so the Len column and the
        # Copy button can never disagree about what a line becomes.
        self.copy_text_fn = None

    def copy_text(self, text: str) -> str:
        """The line as it would land on the clipboard."""
        if self.copy_text_fn is not None:
            return self.copy_text_fn(text)
        return strip_skins(text)

    def refresh_len_column(self):
        """Repaint Len after something outside a row changed the copy result.

        The abbreviation lives outside the model, so editing it changes every
        row's copied length without any row's text changing."""
        if self._rows:
            self.dataChanged.emit(self.index(0, 4), self.index(len(self._rows) - 1, 4))

    # -- Qt model API --
    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 6

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if col == 5 and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return row["text"]
        if col == 5 and _vod_missing_chars(row["text"]):
            if role == Qt.ItemDataRole.ForegroundRole:
                return QtGui.QColor("#ff6b6b")
            if role == Qt.ItemDataRole.ToolTipRole:
                return "Missing character data — add character name(s) inside the parentheses"
        if col == 4:
            # The length of what Copy puts on the clipboard -- the title this set
            # would be published under. Skins are stripped and the shortening
            # strategies have run, because all of that happens on the way to the
            # clipboard; showing the raw line length instead just reports a
            # number nobody publishes.
            #
            # The colour says how much had to be given up to get there:
            #   (none)  fits as written
            #   blue    the series abbreviation was enough
            #   yellow  the character lists had to go as well
            #   red     over the limit even then -- the line itself needs work,
            #           and nothing further is cut automatically because what to
            #           give up next is the user's call.
            plain = strip_skins(row["text"]).strip()
            copied = self.copy_text(row["text"]).strip()
            length = len(copied)
            # The header is not a title, so neither the shortening colours nor
            # the length limit apply to it.
            header = _is_abbrev_line(row["text"])
            abbreviated, dropped = _vod_shorten_flags(plain, copied)
            over = length > MAX_LINE_LEN and not header
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{length}/{MAX_LINE_LEN}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            if role == Qt.ItemDataRole.ForegroundRole:
                if over:
                    return QtGui.QColor("#ff6b6b")
                if dropped:
                    return QtGui.QColor("#ffd166")
                if abbreviated:
                    return QtGui.QColor("#6cb6ff")
            if role == Qt.ItemDataRole.ToolTipRole:
                if over:
                    return (f"{length} characters — over the {MAX_LINE_LEN} limit even "
                            f"{_vod_shorten_note(plain, copied) or 'at full length'}"
                            f".\nNothing further is cut automatically: shorten the line "
                            f"yourself, or set a shorter Abbreviation for this series in the "
                            f"Fetch tab.\nCopies as: {copied}")
                if dropped:
                    return (f"{len(plain)} characters as written. The abbreviation alone was "
                            f"not enough, so the character lists come off too, giving "
                            f"{length}:\n{copied}")
                if abbreviated:
                    return (f"{len(plain)} characters as written, abbreviated to {length} "
                            f"on copy:\n{copied}")
                if header:
                    return (f"The abbreviation this file's lines are shortened with.\n"
                            f"Copies as: {copied}")
                return ("Length of this line as a YouTube title. Per-set skins are "
                        "not counted — they are stripped before copying")
        if col == 1 and role == Qt.ItemDataRole.ToolTipRole:
            return "Copy line"
        if col == 2 and role == Qt.ItemDataRole.ToolTipRole:
            return "Move this line up one row"
        if col == 3 and role == Qt.ItemDataRole.ToolTipRole:
            return "Move this line down one row"
        if col == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if row["checked"] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole and row["checked"]:
            return QtGui.QColor("#1e3a5f")
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        row = self._rows[index.row()]
        if index.column() == 5 and role == Qt.ItemDataRole.EditRole:
            row["text"] = value
            # Refresh both the edited cell and the length column beside it
            self.dataChanged.emit(self.index(index.row(), 4), index)
            self.contentChanged.emit()
            return True
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            row["checked"] = (Qt.CheckState(value) == Qt.CheckState.Checked)
            left = self.index(index.row(), 0)
            right = self.index(index.row(), 5)
            self.dataChanged.emit(left, right)
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        elif index.column() == 5:
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    # -- convenience --
    def set_abbrev_header(self, header: str) -> bool:
        """Write the '# ABBREV:' header row, or drop it when *header* is empty.

        The header is a row like any other, so this goes through the model and
        rides the normal autosave out to the file.
        """
        line = f"# ABBREV: {header}".rstrip() if header else ""
        for r, row in enumerate(self._rows):
            if _is_abbrev_line(row["text"]):
                if row["text"] == line:
                    return False
                if line:
                    row["text"] = line
                    idx = self.index(r, 5)
                    self.dataChanged.emit(self.index(r, 4), idx)
                else:
                    self.beginRemoveRows(QtCore.QModelIndex(), r, r)
                    self._rows.pop(r)
                    self.endRemoveRows()
                self.contentChanged.emit()
                return True
        if not line:
            return False
        self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
        self._rows.insert(0, {"checked": False, "text": line})
        self.endInsertRows()
        self.contentChanged.emit()
        return True

    def load(self, lines: list[str]):
        self.beginResetModel()
        self._rows = [{"checked": False, "text": ln} for ln in lines]
        self.endResetModel()

    def add_blank(self) -> int:
        pos = len(self._rows)
        self.beginInsertRows(QtCore.QModelIndex(), pos, pos)
        self._rows.append({"checked": False, "text": ""})
        self.endInsertRows()
        return pos

    def set_all(self, checked: bool):
        if not self._rows:
            return
        for r in self._rows:
            r["checked"] = checked
        self.dataChanged.emit(self.index(0, 0),
                              self.index(len(self._rows) - 1, 5))

    def _delete_rows(self, doomed) -> int:
        """Drop every row *doomed* selects, except the '# ABBREV:' header.

        That header is file bookkeeping rather than a set, and losing it takes
        the abbreviation away from every line left behind, so neither bulk
        delete may take it whatever its check-mark says. Deleting it on purpose
        is still possible -- right-click Delete line, or clear the series'
        Abbreviation field, which rewrites the header through
        :meth:`set_abbrev_header`.
        """
        keep = [r for r in self._rows
                if not doomed(r) or _is_abbrev_line(r["text"])]
        removed = len(self._rows) - len(keep)
        if removed:
            self.beginResetModel()
            self._rows = keep
            self.endResetModel()
            self.contentChanged.emit()
        return removed

    def delete_marked(self) -> int:
        return self._delete_rows(lambda r: r["checked"])

    def delete_unmarked(self) -> int:
        return self._delete_rows(lambda r: not r["checked"])

    def delete_row(self, r: int):
        if 0 <= r < len(self._rows):
            self.beginRemoveRows(QtCore.QModelIndex(), r, r)
            self._rows.pop(r)
            self.endRemoveRows()
            self.contentChanged.emit()

    def move_row(self, r: int, delta: int) -> int:
        """Move row ``r`` by ``delta`` (±1). Returns the new index, or -1 if
        the move is out of bounds / unsupported."""
        if delta not in (-1, 1):
            return -1
        new = r + delta
        if not (0 <= r < len(self._rows)) or not (0 <= new < len(self._rows)):
            return -1
        # Qt's destination index is expressed in pre-removal coordinates, so a
        # downward move targets r + 2.
        dest = r + 2 if delta == 1 else new
        self.beginMoveRows(QtCore.QModelIndex(), r, r, QtCore.QModelIndex(), dest)
        self._rows.insert(new, self._rows.pop(r))
        self.endMoveRows()
        self.contentChanged.emit()
        return new

    def any_checked(self) -> bool:
        return any(r["checked"] for r in self._rows)

    def text_at(self, r: int) -> str:
        return self._rows[r]["text"] if 0 <= r < len(self._rows) else ""

    def to_text(self) -> str:
        return "\n".join(r["text"] for r in self._rows)


# --------------------------------------------------------------------------- #
#  Syntax highlighters                                                         #
# --------------------------------------------------------------------------- #
def _fmt(color: str) -> QtGui.QTextCharFormat:
    f = QtGui.QTextCharFormat()
    f.setForeground(QtGui.QColor(color))
    return f


class Top8DataHighlighter(QtGui.QSyntaxHighlighter):
    KEY = _fmt(_SYN_KEY)
    NUMBER = _fmt(_SYN_NUMBER)
    COMMENT = _fmt(_SYN_COMMENT)
    SKIN = _fmt(_SYN_STRING)

    def highlightBlock(self, text: str):
        if re.match(r"^[ \t]*#", text):
            self.setFormat(0, len(text), self.COMMENT)
            return
        # A placement line starts with its place number; anything else with a
        # colon is an "Event name:" style key. The page parses them apart the same
        # way, and without the digit check a placement line carrying a costume
        # override would colour everything up to that colon as if it were a key.
        if not re.match(r"^\d", text):
            m = re.match(r"^[^#\n][^:\t\n]*:", text)
            if m:
                self.setFormat(m.start(), m.end() - m.start(), self.KEY)
            return
        self.setFormat(0, re.match(r"^\d+", text).end(), self.NUMBER)
        # The optional costume override on the character field.
        m = re.search(r":[^,\n]*$", text)
        if m:
            self.setFormat(m.start(), m.end() - m.start(), self.SKIN)


class HtmlHighlighter(QtGui.QSyntaxHighlighter):
    TAG = _fmt(_SYN_TAG)
    ATTR = _fmt(_SYN_KEY)
    STRING = _fmt(_SYN_STRING)
    COMMENT = _fmt(_SYN_COMMENT)

    IN_COMMENT = 1

    def highlightBlock(self, text: str):
        for m in re.finditer(r"</?[a-zA-Z][\w:-]*", text):
            self.setFormat(m.start(), m.end() - m.start(), self.TAG)
        for m in re.finditer(r"[a-zA-Z_:][\w:-]*(?==)", text):
            self.setFormat(m.start(), m.end() - m.start(), self.ATTR)
        for m in re.finditer(r"\"[^\"]*\"|'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self.STRING)

        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != self.IN_COMMENT:
            m = re.search(r"<!--", text)
            start = m.start() if m else -1
        while start >= 0:
            end = text.find("-->", start)
            if end == -1:
                self.setCurrentBlockState(self.IN_COMMENT)
                length = len(text) - start
            else:
                length = end - start + 3
            self.setFormat(start, length, self.COMMENT)
            nxt = text.find("<!--", start + length)
            start = nxt


# --------------------------------------------------------------------------- #
#  Combo-box popup delegate                                                    #
# --------------------------------------------------------------------------- #
class ComboItemDelegate(QtWidgets.QStyledItemDelegate):
    """Paints dropdown rows ourselves so the hovered/selected item is clearly
    highlighted (the app-wide stylesheet can't reliably reach combo popups under
    the Fusion style)."""

    def paint(self, painter, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        state = opt.state
        active = bool(state & QtWidgets.QStyle.StateFlag.State_Selected) or \
            bool(state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        bg = QtGui.QColor(_HILITE) if active else QtGui.QColor(_BG3)
        fg = QtGui.QColor("#ffffff") if active else QtGui.QColor(_FG)
        painter.save()
        painter.fillRect(opt.rect, bg)
        painter.setPen(fg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(opt.rect.adjusted(8, 0, -8, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         "" if text is None else str(text))
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setHeight(max(s.height(), 26))
        return s


# --------------------------------------------------------------------------- #
#  Copy-line button delegate (VOD table)                                       #
# --------------------------------------------------------------------------- #
class CopyButtonDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a small clickable "copy" icon per row instead of using a real
    per-row widget, so the virtualized VOD table stays cheap. Emits
    ``copyRequested(row)`` on left-click."""

    copyRequested = QtCore.Signal(int)

    def paint(self, painter, option, index):
        painter.save()
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        base = QtGui.QColor(bg) if bg is not None else QtGui.QColor(_BG3)
        painter.fillRect(option.rect, base)

        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        size = 22
        bx = option.rect.x() + (option.rect.width() - size) // 2
        by = option.rect.y() + (option.rect.height() - size) // 2
        btn = QtCore.QRect(bx, by, size, size)
        if hovered:
            base = QtGui.QColor("#474747")
            painter.setBrush(base)
            painter.setPen(QtGui.QPen(QtGui.QColor(_HILITE), 1))
            painter.drawRoundedRect(btn, 5, 5)

        cx, cy = btn.center().x(), btn.center().y()
        back = QtCore.QRectF(cx - 1.0, cy - 6.0, 7.0, 9.0)
        front = QtCore.QRectF(cx - 4.0, cy - 3.0, 7.0, 9.0)
        ink = QtGui.QColor(_FG if hovered else _MUTED)
        painter.setPen(QtGui.QPen(ink, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(back, 1.6, 1.6)
        path = QtGui.QPainterPath()
        path.addRoundedRect(front, 1.6, 1.6)
        painter.fillPath(path, base)
        painter.drawRoundedRect(front, 1.6, 1.6)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and option.rect.contains(event.pos())):
            self.copyRequested.emit(index.row())
            return True
        return False


class MoveButtonDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a single ▲ or ▼ button per row for reordering that row. One
    instance handles one direction (``delta`` -1 = up, +1 = down), so up and
    down are separate buttons in separate columns. Painted rather than a real
    widget so the virtualized VOD table stays cheap. Emits
    ``moveRequested(row, delta)``. Disabled on the row where the move would run
    off the end (first row for up, last row for down)."""

    moveRequested = QtCore.Signal(int, int)

    def __init__(self, delta: int, parent=None):
        super().__init__(parent)
        self._delta = delta

    def _enabled_for(self, index) -> bool:
        if self._delta < 0:
            return index.row() > 0
        return index.row() < index.model().rowCount() - 1

    def paint(self, painter, option, index):
        painter.save()
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        base = QtGui.QColor(bg) if bg is not None else QtGui.QColor(_BG3)
        painter.fillRect(option.rect, base)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        enabled = self._enabled_for(index)
        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)

        size = 22
        bx = option.rect.x() + (option.rect.width() - size) // 2
        by = option.rect.y() + (option.rect.height() - size) // 2
        btn = QtCore.QRect(bx, by, size, size)
        if hovered and enabled:
            painter.setBrush(QtGui.QColor("#474747"))
            painter.setPen(QtGui.QPen(QtGui.QColor(_HILITE), 1))
            painter.drawRoundedRect(btn, 5, 5)

        cx, cy = btn.center().x(), btn.center().y()
        w = 4.5
        path = QtGui.QPainterPath()
        if self._delta < 0:  # up arrow
            path.moveTo(cx, cy - w)
            path.lineTo(cx - w, cy + w)
            path.lineTo(cx + w, cy + w)
        else:                # down arrow
            path.moveTo(cx, cy + w)
            path.lineTo(cx - w, cy - w)
            path.lineTo(cx + w, cy - w)
        path.closeSubpath()
        if not enabled:
            color = QtGui.QColor(_MUTED)
            color.setAlpha(70)
        else:
            color = QtGui.QColor(_FG if hovered else _MUTED)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and option.rect.contains(event.pos())):
            if self._enabled_for(index):
                self.moveRequested.emit(index.row(), self._delta)
            return True
        return False


# --------------------------------------------------------------------------- #
#  VOD line editor delegate                                                    #
# --------------------------------------------------------------------------- #
class VodLineDelegate(QtWidgets.QStyledItemDelegate):
    """On edit start, places the cursor inside the first empty () so the user
    doesn't have to click precisely between the parentheses."""

    def setEditorData(self, editor, index):
        super().setEditorData(editor, index)
        text = editor.text()
        m = _EMPTY_PARENS_RE.search(text)
        if m:
            target = m.start() + 1
            QtCore.QTimer.singleShot(0, lambda: editor.setCursorPosition(target))


# --------------------------------------------------------------------------- #
#  Main window                                                                 #
# --------------------------------------------------------------------------- #
class MeleeWindow(QtWidgets.QMainWindow):
    log_signal = Signal(str)
    update_status_signal = Signal(str, str)   # (message, level: ok|avail|err|busy)
    update_done_signal = Signal(bool, str)    # (success, new folder-tree sha)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Melee Generator Powered By Watherum")
        for folder in _OUTPUT_FOLDERS:
            (ROOT / folder).mkdir(exist_ok=True)

        self._procs: set[QProcess] = set()
        self._http_server = None
        self._http_server_port = None
        self._preview_cache: dict[str, QtGui.QPixmap] = {}

        self._load_settings()

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        self.tabs = QtWidgets.QTabWidget()
        splitter.addWidget(self.tabs)

        console_box = QtWidgets.QWidget()
        cbl = QtWidgets.QVBoxLayout(console_box)
        cbl.setContentsMargins(6, 4, 6, 6)
        hdr = QtWidgets.QHBoxLayout()
        hdr.addWidget(_muted("Console Output"))
        hdr.addStretch(1)
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self._clear_console)
        hdr.addWidget(clear_btn)
        cbl.addLayout(hdr)
        self.console = QtWidgets.QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"background-color: {_BG};")
        cbl.addWidget(self.console)
        splitter.addWidget(console_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([720, 200])
        self._splitter = splitter

        self.log_signal.connect(self._append_console)
        self.update_status_signal.connect(self._on_update_status)
        self.update_done_signal.connect(self._on_update_done)

        # Build tabs
        self._build_fetch_tab()
        self._build_thumbnails_tab()
        self._build_top8_tab()
        self._build_posts_tab()
        self._build_player_db_tab()
        self._build_renders_tab()
        self._build_char_db_tab()
        self._build_update_tab()

        # Player Database sits next to Generate Thumbnails, whose Import Missing
        # Players / Add Missing Costumes buttons write into it. Moved after the
        # build rather than built in that order, because a tab's construction
        # can depend on an earlier tab's widgets.
        bar = self.tabs.tabBar()
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Player Database":
                bar.moveTab(i, 2)
                break

        self._combo_delegate = ComboItemDelegate(self)
        for combo in self.findChildren(QtWidgets.QComboBox):
            combo.view().setItemDelegate(self._combo_delegate)

        self.resize(1280, 900)

    # ------------------------------------------------------------------ #
    #  Settings persistence                                              #
    # ------------------------------------------------------------------ #
    def _load_settings(self):
        try:
            self._settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._settings = {}
        try:
            self._custom_events = json.loads(CUSTOM_EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._custom_events = []
        try:
            self._event_configs = json.loads(EVENT_CONFIGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._event_configs = {}

    def _save_settings(self):
        if getattr(self, "_loading", False):
            return
        series = self._posts_series.currentText() if hasattr(self, "_posts_series") else ""
        posts_cfg = dict(self._settings.get("posts_cfg", {}))
        if series and hasattr(self, "_posts_has_next"):
            posts_cfg[series] = {
                "next_date": self._posts_date.date().toString("yyyy-MM-dd"),
                "next_link": self._posts_next_link.text(),
                "vods": self._posts_vods.text(),
                "has_next": self._posts_has_next.isChecked(),
            }
        data = {
            "last_event_nums": {
                label: w["num"].text() for label, w in self._fetch_widgets.items()
            },
            "abbrevs": {
                label: w["abbrev"].text() for label, w in self._fetch_widgets.items()
                if "abbrev" in w
            },
            "last_thumb_series": self._thumb_series.currentText() if hasattr(self, "_thumb_series") else "",
            "last_posts_series": series,
            "posts_cfg": posts_cfg,
            "last_update_tree": self._settings.get("last_update_tree", ""),
            "fetch_collapsed": self._settings.get("fetch_collapsed", {}),
            "fetch_provider": getattr(self, "_fetch_provider", DEFAULT_PROVIDER),
        }
        self._settings = data
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _on_fetch_collapsed(self, label: str, checked: bool):
        collapsed = self._settings.get("fetch_collapsed", {})
        collapsed[label] = not checked
        self._settings["fetch_collapsed"] = collapsed
        self._save_settings()

    def _on_custom_fetch_collapsed(self, entry: dict, checked: bool):
        entry["collapsed"] = not checked
        self._save_custom_events()

    def _save_custom_events(self):
        CUSTOM_EVENTS_PATH.write_text(json.dumps(self._custom_events, indent=2), encoding="utf-8")

    def _save_event_configs(self):
        EVENT_CONFIGS_PATH.write_text(json.dumps(self._event_configs, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ #
    #  Scroll-area tab helper                                            #
    # ------------------------------------------------------------------ #
    def _scroll_tab(self, title: str) -> QtWidgets.QVBoxLayout:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        scroll.setWidget(inner)
        self.tabs.addTab(scroll, title)
        return lay

    # ================================================================== #
    #  Tab: Fetch from start.gg                                          #
    # ================================================================== #
    def _build_fetch_tab(self):
        lay = self._scroll_tab("Fetch Data")
        self._fetch_widgets: dict[str, dict] = {}
        # label -> the CollapsibleBox for a built-in event. Built-ins are built
        # for every provider and only hidden when one does not match: their
        # widgets are what _save_settings reads back the event numbers and
        # abbreviations from, so destroying them would wipe both.
        self._fetch_boxes: dict[str, QtWidgets.QWidget] = {}

        saved_provider = self._settings.get("fetch_provider", DEFAULT_PROVIDER)
        self._fetch_provider = (saved_provider if saved_provider in PROVIDERS
                                else DEFAULT_PROVIDER)

        prow = QtWidgets.QHBoxLayout()
        prow.addWidget(QtWidgets.QLabel("Fetch from:"))
        self._provider_combo = _NoWheelComboBox()
        for key in PROVIDERS:
            self._provider_combo.addItem(PROVIDERS[key]["label"], key)
        self._provider_combo.setCurrentIndex(
            self._provider_combo.findData(self._fetch_provider))
        self._provider_combo.setToolTip(
            "The tournament site to pull match data from. Only the events "
            "belonging to the selected site are listed below.")
        self._provider_combo.currentIndexChanged.connect(self._on_provider_change)
        prow.addWidget(self._provider_combo)
        prow.addSpacing(12)
        self._provider_key_hint = _muted("")
        self._provider_key_hint.setWordWrap(True)
        prow.addWidget(self._provider_key_hint, 1)
        lay.addLayout(prow)

        # A standing caveat about the selected site -- what it cannot report,
        # rather than what has gone wrong. Only Challonge has one, so the label
        # is hidden entirely for the other providers.
        self._provider_note = _muted("")
        self._provider_note.setWordWrap(True)
        # Amber, the Len column's "something was given up" colour -- a caveat
        # to read rather than the red of something that has gone wrong.
        self._provider_note.setStyleSheet("color: #ffd166;")
        lay.addWidget(self._provider_note)

        fetch_collapsed = self._settings.get("fetch_collapsed", {})
        for cfg in FETCH_EVENTS:
            label = cfg["label"]
            collapsed = fetch_collapsed.get(label, False)
            cbox = CollapsibleBox(label, collapsed=collapsed)
            saved_num = self._settings.get("last_event_nums", {}).get(label, cfg["default_num"])

            row1 = QtWidgets.QHBoxLayout()
            # "Tournament #", not "Event #": the number identifies which
            # instalment of the series this is (IFN 274), while an *event* is
            # one bracket inside it -- the distinction the Add form's own copy
            # already draws, and the one parry.gg rows depend on.
            num_lbl = QtWidgets.QLabel("Tournament #:")
            num_lbl.setToolTip("The series instalment number, e.g. 274 for "
                               "Immortal Fight Night 274. It fills every {n} "
                               "in the event's URL and name.")
            row1.addWidget(num_lbl)
            num = _hline(saved_num, 60)
            num.setToolTip(num_lbl.toolTip())
            row1.addWidget(num)
            row1.addSpacing(12)
            link_lbl = QtWidgets.QLabel("Link for Top 8 Graphic:")
            link_tip = ("The short start.gg link printed on the Top 8 graphic "
                        '(its "Event link" field), e.g. start.gg/UIFN274. '
                        "Optional -- leave it blank and the graphic shows no link.")
            link_lbl.setToolTip(link_tip)
            row1.addWidget(link_lbl)
            link = QtWidgets.QLineEdit(cfg["default_link"].replace("{n}", saved_num))
            link.setMinimumWidth(280)
            link.setToolTip(link_tip)
            row1.addWidget(link)
            row1.addWidget(_muted("optional"))
            row1.addStretch(1)
            cbox.addLayout(row1)

            rowa = QtWidgets.QHBoxLayout()
            rowa.addWidget(QtWidgets.QLabel("Abbrev:"))
            saved_abbrev = self._settings.get("abbrevs", {}).get(
                label, cfg.get("default_abbrev", ""))
            abbrev = _hline(saved_abbrev, 90)
            abbrev.setToolTip("Short tournament name used for VOD lines over "
                              f"{MAX_LINE_LEN} characters (e.g. IFN). The event "
                              "number is appended automatically.")
            rowa.addWidget(abbrev)
            abbrev_hint = _muted(f"used when a match line exceeds {MAX_LINE_LEN} chars")
            # One line: a QHBoxLayout gives a wrapping label its minimum width,
            # which breaks a short hint into a narrow column.
            abbrev_hint.setWordWrap(False)
            rowa.addWidget(abbrev_hint)
            rowa.addStretch(1)
            cbox.addLayout(rowa)
            abbrev.textChanged.connect(
                lambda _t, lbl=label: (self._save_settings(),
                                       self._sync_abbrev_to_vod_file(lbl)))

            def _on_num(text, lk=link, tmpl=cfg["default_link"], lbl=label):
                lk.setText(tmpl.replace("{n}", text.strip()))
                if hasattr(self, "_thumb_series") and self._thumb_series.currentText() == lbl:
                    self._thumb_num.setText(text.strip())
                if hasattr(self, "_posts_series") and self._posts_series.currentText() == lbl:
                    self._posts_num.setText(text.strip())
                self._save_settings()
            num.textChanged.connect(_on_num)

            row2 = QtWidgets.QHBoxLayout()
            b1 = QtWidgets.QPushButton("Fetch VOD Names")
            b1.clicked.connect(lambda _=False, c=cfg, n=num, a=abbrev: self._fetch_sets(c, n.text().strip(), a.text().strip()))
            row2.addWidget(b1)
            b2 = QtWidgets.QPushButton("Fetch Top 8")
            b2.clicked.connect(lambda _=False, c=cfg, n=num, lk=link: self._fetch_top8(c, n.text().strip(), lk.text().strip()))
            row2.addWidget(b2)
            row2.addStretch(1)
            cbox.addLayout(row2)
            cbox._toggle.clicked.connect(lambda checked, lbl=label: self._on_fetch_collapsed(lbl, checked))
            lay.addWidget(cbox)
            self._fetch_widgets[label] = {"num": num, "link": link, "abbrev": abbrev}
            self._fetch_boxes[label] = cbox

        # Renaming a saved event refreshes the event lists, which reloads the
        # Thumbnails tab -- too much to do on every keystroke, so it is deferred.
        self._custom_refresh_timer = QtCore.QTimer(self)
        self._custom_refresh_timer.setSingleShot(True)
        self._custom_refresh_timer.setInterval(600)
        self._custom_refresh_timer.timeout.connect(self._refresh_thumbnail_events)

        # Saved custom tournaments
        self._saved_custom_box = QtWidgets.QGroupBox("Saved Events")
        self._saved_custom_layout = QtWidgets.QVBoxLayout(self._saved_custom_box)
        lay.addWidget(self._saved_custom_box)
        # Populated by _apply_provider() below, once the provider is known.

        # Add new custom
        self._custom_addbox = QtWidgets.QGroupBox("Add A Tournament's Event")
        form = QtWidgets.QGridLayout(self._custom_addbox)
        self._custom_intro = _muted("")
        self._custom_intro.setWordWrap(True)
        form.addWidget(self._custom_intro, 0, 0, 1, 4)
        self._custom_slug_label = QtWidgets.QLabel("Event URL:")
        form.addWidget(self._custom_slug_label, 1, 0)
        self._custom_slug = QtWidgets.QLineEdit()
        self._custom_slug.setFixedWidth(360)
        form.addWidget(self._custom_slug, 1, 1)
        self._custom_slug_note = _muted("")
        form.addWidget(self._custom_slug_note, 1, 2)
        self._custom_slug_hint = _muted("")
        self._custom_slug_hint.setWordWrap(True)
        form.addWidget(self._custom_slug_hint, 2, 1, 1, 3)
        self._custom_slug.textChanged.connect(self._refresh_custom_slug_hint)
        form.addWidget(QtWidgets.QLabel("Name:"), 3, 0)
        self._custom_name = QtWidgets.QLineEdit()
        self._custom_name.setFixedWidth(250)
        form.addWidget(self._custom_name, 3, 1)
        form.addWidget(_muted("series name for the VOD lines, e.g. Immortal Fight Night {n}"), 3, 2)
        form.addWidget(QtWidgets.QLabel("Abbrev:"), 4, 0)
        self._custom_abbrev = QtWidgets.QLineEdit()
        self._custom_abbrev.setFixedWidth(120)
        form.addWidget(self._custom_abbrev, 4, 1)
        form.addWidget(_muted(f"optional — used when a match line exceeds {MAX_LINE_LEN} chars"), 4, 2)
        custom_num_lbl = QtWidgets.QLabel("Tournament #:")
        custom_num_lbl.setToolTip(
            "Optional -- the series instalment number (274 for Immortal Fight "
            "Night 274). It fills every {n} above; a tournament whose URL and "
            "name have no {n} needs none.")
        form.addWidget(custom_num_lbl, 5, 0)
        self._custom_num = _hline("", 60)
        self._custom_num.setToolTip(custom_num_lbl.toolTip())
        form.addWidget(self._custom_num, 5, 1)
        form.addWidget(_muted("optional — fills every {n} above"), 5, 2)
        # parry.gg only: its slug names a tournament, so which event inside it
        # to pull is a separate choice. Hidden for start.gg, whose URL names the
        # event already. Deliberately not called "Event #" -- that is the
        # tournament's number, and two fields named Event read as the same one.
        self._custom_event_label = QtWidgets.QLabel("Event:")
        self._custom_event_label.setToolTip(
            "Which bracket inside the tournament to pull: 0 is its first event, "
            "1 the second, and so on. An event slug works here too.\n"
            "This is not the tournament number above -- it chooses singles vs "
            "doubles, not which week.")
        form.addWidget(self._custom_event_label, 6, 0)
        self._custom_event = _hline("0", 60)
        self._custom_event.setToolTip(self._custom_event_label.toolTip())
        form.addWidget(self._custom_event, 6, 1)
        self._custom_event_note = _muted(
            "which bracket in the tournament — 0 = the first (e.g. singles), 1 = the next")
        form.addWidget(self._custom_event_note, 6, 2)
        save_fetch = QtWidgets.QPushButton("Save & Fetch VOD Names")
        save_fetch.clicked.connect(self._fetch_custom_sets)
        form.addWidget(save_fetch, 7, 1)
        form.setColumnStretch(3, 1)
        lay.addWidget(self._custom_addbox)
        lay.addStretch(1)
        self._apply_provider()

    # ------------------------------------------------------------------ #
    #  Provider selection                                                 #
    # ------------------------------------------------------------------ #
    def _provider_cfg(self, provider: str = "") -> dict:
        return PROVIDERS[provider or self._fetch_provider]

    def _on_provider_change(self, *_a):
        self._fetch_provider = (self._provider_combo.currentData()
                                or DEFAULT_PROVIDER)
        self._save_settings()
        self._apply_provider()

    def _apply_provider(self):
        """Show only the selected provider's events and relabel the Add form.

        Built-in rows are hidden rather than destroyed -- _save_settings reads
        the event numbers and abbreviations back out of their widgets, so a
        provider switch must not take them with it.
        """
        cfg = self._provider_cfg()

        for label, box in self._fetch_boxes.items():
            entry = next((c for c in FETCH_EVENTS if c["label"] == label), {})
            box.setVisible(provider_of(entry) == self._fetch_provider)

        self._custom_slug_label.setText(cfg["slug_label"])
        self._custom_slug.setPlaceholderText(cfg["slug_placeholder"])
        self._custom_slug.setToolTip(cfg["slug_tooltip"])
        self._custom_slug_note.setText(cfg["slug_hint"])
        self._custom_intro.setText(cfg["intro"])
        for w in (self._custom_event_label, self._custom_event,
                  self._custom_event_note):
            w.setVisible(cfg["needs_event_index"])

        note = cfg.get("note") or ""
        self._provider_note.setText(note)
        self._provider_note.setVisible(bool(note))

        problem_fn = cfg.get("api_key_problem")
        problem = problem_fn() if problem_fn else ""
        self._provider_key_hint.setText(problem)
        self._provider_key_hint.setStyleSheet("color: #E5534B;" if problem else "")
        self._provider_key_hint.setVisible(bool(problem))

        self._build_saved_custom_rows()
        self._refresh_custom_slug_hint()

    def _refresh_custom_slug_hint(self, *_a):
        """Say, as the user types, why a slug won't fetch — blank once it will."""
        text = self._custom_slug.text().strip()
        problem = self._provider_cfg()["problem"](text) if text else ""
        self._custom_slug_hint.setText(problem)
        self._custom_slug_hint.setStyleSheet(
            "color: #E5534B;" if problem else "")
        self._custom_slug_hint.setVisible(bool(problem))

    @staticmethod
    def _custom_label(name_tmpl: str, slug_tmpl: str) -> str:
        """The series name a saved event is listed under: its name without {n}."""
        return (name_tmpl or slug_tmpl).replace(" {n}", "").replace("{n}", "").strip()

    def _build_saved_custom_rows(self):
        # Clear existing
        while self._saved_custom_layout.count():
            item = self._saved_custom_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # Only this provider's events. The filter is the Fetch tab's alone --
        # the Thumbnails, Top 8 and Posts tabs still list every saved event,
        # since a fetched VOD file is handled the same whatever pulled it.
        provider_cfg = self._provider_cfg()
        shown = [e for e in self._custom_events
                 if provider_of(e) == self._fetch_provider
                 and e.get("slug_template", e.get("slug", ""))]
        if not shown:
            self._saved_custom_layout.addWidget(_muted(
                f"No saved {provider_cfg['label']} events yet — add one below"))
            return
        for entry in shown:
            slug_tmpl = entry.get("slug_template", entry.get("slug", ""))
            cbox = CollapsibleBox(entry.get("label", slug_tmpl), collapsed=entry.get("collapsed", False))

            # A saved event is editable in place: a tournament renames a bracket
            # or moves to a new slug, and deleting and re-adding the entry would
            # take its abbreviation and Top 8 link with it.
            rowu = QtWidgets.QHBoxLayout()
            rowu.addWidget(QtWidgets.QLabel(provider_cfg["slug_label"]))
            slug_box = QtWidgets.QLineEdit(slug_tmpl)
            slug_box.setMinimumWidth(340)
            slug_box.setToolTip(provider_cfg["slug_tooltip"])
            rowu.addWidget(slug_box)
            if provider_cfg["needs_event_index"]:
                # parry.gg picks the event inside the tournament by index; a
                # tournament running both singles and doubles needs one saved
                # entry per bracket, differing only here.
                event_lbl = QtWidgets.QLabel("Event:")
                event_lbl.setToolTip(
                    "Which bracket inside the tournament to pull: 0 is its "
                    "first event, 1 the second, and so on. An event slug works "
                    "too.\nThis is not the tournament number below -- it "
                    "chooses singles vs doubles, not which week.")
                rowu.addWidget(event_lbl)
                event_box = _hline(str(entry.get("event", "0")), 60)
                event_box.setToolTip(event_lbl.toolTip())

                def _on_event(text, e=entry):
                    e["event"] = text.strip()
                    self._save_custom_events()
                event_box.textChanged.connect(_on_event)
                rowu.addWidget(event_box)
            rowu.addStretch(1)
            cbox.addLayout(rowu)

            rown = QtWidgets.QHBoxLayout()
            rown.addWidget(QtWidgets.QLabel("Name:"))
            name_box = QtWidgets.QLineEdit(entry.get("name_template", ""))
            name_box.setMinimumWidth(250)
            name_box.setToolTip("Names the VOD file and the generated event. "
                                "{n} is replaced by the event number.")
            rown.addWidget(name_box)
            name_hint = _muted("renames the event everywhere it is listed")
            name_hint.setWordWrap(False)
            rown.addWidget(name_hint)
            rown.addStretch(1)
            cbox.addLayout(rown)

            def _on_slug_text(text, e=entry):
                e["slug_template"] = text.strip()
                self._save_custom_events()

            def _on_slug_done(box=slug_box, e=entry):
                # Normalize a pasted URL, and say so if it names no event --
                # the same check the Add form makes, applied to an edit, and
                # through the provider the entry belongs to.
                cfg = self._provider_cfg(provider_of(e))
                # Checked before normalizing, for the reason given in
                # _fetch_custom_sets: normalizing can hide a wrong-provider slug.
                raw = box.text().strip()
                problem = cfg["problem"](raw)
                norm = cfg["normalize"](raw)
                if norm != box.text():
                    box.setText(norm)      # -> _on_slug_text
                if problem:
                    self._log(f"[{e.get('label', 'Saved event')}: {problem}]\n")

            def _on_name_text(text, e=entry, box=cbox):
                e["name_template"] = text.strip()
                label = self._custom_label(e["name_template"], e.get("slug_template", ""))
                if label:
                    e["label"] = label
                    e["top8_file"] = f"{label} Top 8 HTML.txt"
                    box._toggle.setText(label)
                self._save_custom_events()
                # Deferred: this fires per keystroke, and refreshing the event
                # lists reloads the Thumbnails tab's VOD file and config.
                self._custom_refresh_timer.start()

            slug_box.textChanged.connect(_on_slug_text)
            slug_box.editingFinished.connect(_on_slug_done)
            name_box.textChanged.connect(_on_name_text)

            row1 = QtWidgets.QHBoxLayout()
            num_lbl = QtWidgets.QLabel("Tournament #:")
            num_lbl.setToolTip("Optional -- the series instalment number (274 "
                               "for Immortal Fight Night 274). It fills every "
                               "{n} in the URL and name above; a tournament "
                               "whose name has no {n} needs none.")
            row1.addWidget(num_lbl)
            num = _hline(entry.get("current_num", ""), 60)
            num.setToolTip(num_lbl.toolTip())
            row1.addWidget(num)
            row1.addWidget(_muted("optional"))
            row1.addSpacing(12)
            link_lbl = QtWidgets.QLabel("Link for Top 8 Graphic:")
            link_tip = ("The short start.gg link printed on the Top 8 graphic "
                        '(its "Event link" field), e.g. start.gg/UIFN274. '
                        "Optional -- leave it blank and the graphic shows no link.")
            link_lbl.setToolTip(link_tip)
            row1.addWidget(link_lbl)
            link = QtWidgets.QLineEdit(entry.get("top8_link", ""))
            link.setMinimumWidth(260)
            link.setToolTip(link_tip)
            row1.addWidget(link)
            row1.addWidget(_muted("optional"))
            row1.addStretch(1)
            cbox.addLayout(row1)

            def _on_num(text, e=entry):
                e["current_num"] = text
                self._save_custom_events()

            def _on_link(text, e=entry):
                e["top8_link"] = text
                self._save_custom_events()

            rowa = QtWidgets.QHBoxLayout()
            rowa.addWidget(QtWidgets.QLabel("Abbrev:"))
            abbrev = _hline(entry.get("abbrev", ""), 90)
            abbrev.setToolTip("Short tournament name used for VOD lines over "
                              f"{MAX_LINE_LEN} characters. The event number is "
                              "appended automatically.")
            rowa.addWidget(abbrev)
            abbrev_hint = _muted(f"used when a match line exceeds {MAX_LINE_LEN} chars")
            # One line: a QHBoxLayout gives a wrapping label its minimum width,
            # which breaks a short hint into a narrow column.
            abbrev_hint.setWordWrap(False)
            rowa.addWidget(abbrev_hint)
            rowa.addStretch(1)
            cbox.addLayout(rowa)

            def _on_abbrev(text, e=entry):
                e["abbrev"] = text
                self._save_custom_events()
                self._sync_abbrev_to_vod_file(e.get("label", ""))

            num.textChanged.connect(_on_num)
            link.textChanged.connect(_on_link)
            abbrev.textChanged.connect(_on_abbrev)

            row2 = QtWidgets.QHBoxLayout()
            b1 = QtWidgets.QPushButton("Fetch VOD Names")
            b1.clicked.connect(lambda _=False, e=entry, n=num: self._fetch_saved_custom(e, n.text().strip()))
            row2.addWidget(b1)
            b2 = QtWidgets.QPushButton("Fetch Top 8")
            b2.clicked.connect(lambda _=False, e=entry, n=num, lk=link: self._fetch_saved_custom_top8(e, n.text().strip(), lk.text().strip()))
            row2.addWidget(b2)
            b3 = QtWidgets.QPushButton("Delete")
            b3.clicked.connect(lambda _=False, s=slug_tmpl: self._delete_custom_event(s))
            row2.addWidget(b3)
            row2.addStretch(1)
            cbox.addLayout(row2)
            cbox._toggle.clicked.connect(lambda checked, e=entry: self._on_custom_fetch_collapsed(e, checked))
            self._saved_custom_layout.addWidget(cbox)

    # ------------------------------------------------------------------ #
    #  Fetch command builders                                             #
    # ------------------------------------------------------------------ #
    #  The two providers differ only in which script runs and whether the
    #  event is named by the slug or picked by index beside it, so both
    #  commands are assembled in one place and every caller goes through it.

    def _sets_cmd(self, entry: dict, slug: str, name: str, out: str,
                  abbrev: str, num: str) -> list:
        cfg = self._provider_cfg(provider_of(entry))
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / cfg["sets_script"]),
               slug, "--name", name, "--out", out]
        if cfg["needs_event_index"]:
            cmd += ["--event", str(entry.get("event", "0")).strip() or "0"]
        if abbrev:
            cmd += ["--abbrev", f"{abbrev} {num}".strip()]
        return cmd

    def _top8_cmd(self, entry: dict, slug: str, name: str, out: str,
                  link: str) -> list:
        cfg = self._provider_cfg(provider_of(entry))
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / cfg["top8_script"]),
               slug, "--name", name, "--out", out]
        if cfg["needs_event_index"]:
            cmd += ["--event", str(entry.get("event", "0")).strip() or "0"]
        if link:
            cmd += ["--link", link]
        return cmd

    def _fetch_custom_sets(self):
        provider = self._fetch_provider
        cfg = self._provider_cfg(provider)
        # Validate what was typed, not what normalizing leaves behind: the
        # parry normalizer keeps only the first path segment, so a start.gg
        # slug pasted here would survive as a plausible-looking "tournament".
        # Both validators normalize internally anyway.
        raw = self._custom_slug.text().strip()
        problem = cfg["problem"](raw)
        if problem:
            self._log(f"[Error: {problem}]\n")
            return
        slug_tmpl = cfg["normalize"](raw)
        self._custom_slug.setText(slug_tmpl)  # normalize URL → slug in place
        name_tmpl = self._custom_name.text().strip()
        num = self._custom_num.text().strip()
        label = self._custom_label(name_tmpl, slug_tmpl)
        abbrev = self._custom_abbrev.text().strip()
        slug = slug_tmpl.replace("{n}", num)
        name = (name_tmpl or slug_tmpl).replace("{n}", num)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        entry = {
            "provider": provider,
            "label": label, "slug_template": slug_tmpl,
            "name_template": name_tmpl or slug_tmpl,
            "abbrev": abbrev,
            "top8_file": f"{label} Top 8 HTML.txt",
            "current_num": num, "top8_link": "",
        }
        if cfg["needs_event_index"]:
            entry["event"] = self._custom_event.text().strip() or "0"
        idx = next((i for i, e in enumerate(self._custom_events) if e.get("slug_template") == slug_tmpl), None)
        if idx is not None:
            entry["top8_link"] = self._custom_events[idx].get("top8_link", "")
            self._custom_events[idx] = entry
        else:
            self._custom_events.append(entry)
        self._save_custom_events()
        self._build_saved_custom_rows()
        self._refresh_thumbnail_events()
        self._run(self._sets_cmd(entry, slug, name, out, abbrev, num))

    def _fetch_saved_custom(self, entry: dict, num: str):
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        abbrev = entry.get("abbrev", "").strip()
        self._run(self._sets_cmd(entry, slug, name, out, abbrev, num))

    def _fetch_saved_custom_top8(self, entry: dict, num: str, link: str):
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        top8_file = entry.get("top8_file", f"{entry['label']} Top 8 HTML.txt")
        out_path = ROOT / "Top_8_Texts" / top8_file
        if not out_path.exists():
            out_path.touch()
        cmd = self._top8_cmd(entry, slug, name, str(out_path), link)

        def _done():
            try:
                shutil.copy2(out_path, ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt")
            except Exception:
                pass
            self._select_top8_event(entry["label"], num)
        self._run(cmd, on_done=_done)

    def _delete_custom_event(self, slug_tmpl: str):
        self._custom_events = [e for e in self._custom_events
                               if e.get("slug_template", e.get("slug")) != slug_tmpl]
        self._save_custom_events()
        self._build_saved_custom_rows()
        self._refresh_thumbnail_events()

    def _fetch_sets(self, cfg: dict, n: str, abbrev: str = ""):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        self._run(self._sets_cmd(cfg, slug, name, out, abbrev, n))

    def _fetch_top8(self, cfg: dict, n: str, link: str):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out = ROOT / "Top_8_Texts" / cfg["top8_file"]

        def _done():
            try:
                shutil.copy2(out, ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt")
            except Exception:
                pass
            self._select_top8_event(cfg["label"], n)
        self._run(self._top8_cmd(cfg, slug, name, str(out), link), on_done=_done)

    def _select_top8_event(self, label: str, num: str = ""):
        # `num` is accepted for caller compatibility but no longer used — the
        # Top 8 tab selects by series only (one text file per series).
        if label in [self._top8_series.itemText(i) for i in range(self._top8_series.count())]:
            self._top8_series.setCurrentText(label)
        self._refresh_top8_files()

    # ================================================================== #
    #  Tab: Generate Thumbnails                                          #
    # ================================================================== #
    def _build_thumbnails_tab(self):
        lay = self._scroll_tab("Generate Thumbnails")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._thumb_series = _NoWheelComboBox()
        self._thumb_series.setMinimumWidth(220)
        row1.addWidget(self._thumb_series)
        refresh = QtWidgets.QPushButton("⟳")
        refresh.setObjectName("tool")
        refresh.setToolTip("Refresh event list")
        refresh.clicked.connect(self._refresh_thumbnail_events)
        row1.addWidget(refresh)
        row1.addSpacing(12)
        num_lbl = QtWidgets.QLabel("# / Label:")
        num_tip = ("What replaces {n} in the series name -- an event number "
                   "(274), or a word for a tournament's other brackets "
                   "(Doubles, Crews).")
        num_lbl.setToolTip(num_tip)
        row1.addWidget(num_lbl)
        self._thumb_num = _hline("274", 160)
        self._thumb_num.setToolTip(num_tip)
        row1.addWidget(self._thumb_num)
        row1.addStretch(1)
        v.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        # A tournament can hold several events (a singles and a doubles bracket,
        # say), which share a series and therefore differ only in this name. The
        # dropdown lists the ones that already have a VOD file so one can be
        # picked instead of typed; it stays editable for an event not fetched yet.
        self._thumb_event_name = _EditableCombo()
        self._thumb_event_name.setMinimumWidth(320)
        self._thumb_event_name.setToolTip(
            "The event to generate. Picking one selects its VOD names file, "
            "and picking a file here selects the event.")
        row2.addWidget(self._thumb_event_name)
        self._thumb_event_name.activated.connect(self._on_thumb_event_pick)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        self._thumb_event_map: dict[str, str] = {}
        self._thumb_series.currentTextChanged.connect(self._on_thumb_series_change)
        self._thumb_num.textChanged.connect(self._update_thumb_name)

        # Config section
        self._build_thumbnail_config(lay)

        row_gen = QtWidgets.QHBoxLayout()
        self._gen_thumb_btn = QtWidgets.QPushButton("Generate Thumbnails")
        self._gen_thumb_btn.setObjectName("accent")
        self._gen_thumb_btn.setEnabled(False)
        self._gen_thumb_btn.setToolTip("Fill in character data for all match lines to enable")
        self._gen_thumb_btn.clicked.connect(self._generate_thumbnails)
        row_gen.addWidget(self._gen_thumb_btn)
        self._open_thumb_btn = QtWidgets.QPushButton("Open Output Folder")
        self._open_thumb_btn.clicked.connect(self._open_thumbnail_folder)
        row_gen.addWidget(self._open_thumb_btn)
        row_gen.addStretch(1)
        lay.addLayout(row_gen)
        self._thumb_event_name.textChanged.connect(self._refresh_open_folder_btn)

        # VOD Names editor
        self._build_vod_editor(lay)

        self._refresh_thumbnail_events()
        self._refresh_open_folder_btn()

    def _refresh_thumbnail_events(self):
        events = load_thumbnail_events()
        self._thumb_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        for entry in self._custom_events:
            label = entry.get("label", "")
            name_tmpl = entry.get("name_template", "")
            if label and name_tmpl and label not in self._thumb_event_map:
                self._thumb_event_map[label] = name_tmpl
                names.append(label)
        cur = self._thumb_series.currentText()
        self._thumb_series.blockSignals(True)
        self._thumb_series.clear()
        self._thumb_series.addItems(names)
        if names:
            last = self._settings.get("last_thumb_series")
            if last in names:
                self._thumb_series.setCurrentText(last)
            elif cur in names:
                self._thumb_series.setCurrentText(cur)
            else:
                self._thumb_series.setCurrentIndex(0)
        self._thumb_series.blockSignals(False)
        self._on_thumb_series_change()
        if hasattr(self, "_top8_series"):
            self._refresh_top8_series()

    def _on_thumb_series_change(self):
        series = self._thumb_series.currentText()
        widgets = self._fetch_widgets.get(series)
        if widgets:
            self._thumb_num.setText(widgets["num"].text())
        else:
            custom = next((e for e in self._custom_events if e.get("label") == series), None)
            if custom:
                self._thumb_num.setText(custom.get("current_num", ""))
            else:
                saved = self._settings.get("last_event_nums", {}).get(series)
                if saved:
                    self._thumb_num.setText(saved)
        self._update_thumb_name()
        self._load_config_into_form(series)
        self._refresh_vod_len()
        self._refresh_vod_files()
        self._save_settings()

    def _update_thumb_name(self):
        template = self._thumb_event_map.get(self._thumb_series.currentText(), "{n}")
        num = self._thumb_num.text().strip()
        name = template.format(n=num)
        if not num:
            # No label: the event is the series itself, so drop the separator
            # the label would have sat behind rather than leave it dangling.
            name = re.sub(r"\s{2,}", " ", name).strip()
        self._thumb_event_name.setText(name)
        self._save_settings()

    # --- Thumbnail config (writes melee_event_configs.json, applied by
    #     generate_melee_thumbnails.py as per-event property overrides) ---
    _CFG_FLOAT = ["resize_1", "resize_2", "resize_3"]
    _CFG_INT = ["font_player1_size", "font_player2_size", "font_event_size",
                "font_round_size", "text_angle"]
    _CFG_POS = ["center_shift_1", "center_shift_2_1", "center_shift_2_2",
                "center_shift_3_1", "center_shift_3_2", "center_shift_3_3",
                "text_player1", "text_player2", "text_event", "text_round",
                "char_offset1", "char_offset2", "char_window"]
    _CFG_COLOR = ["font_color1", "font_color2", "font_color3", "font_color4"]

    def _build_thumbnail_config(self, parent_layout):
        cbox = CollapsibleBox("Thumbnail Config", collapsed=True)
        parent_layout.addWidget(cbox)

        # What this form edits. A series config covers every event whose name
        # starts with the series; a file config covers one names file, which is
        # how two brackets of the same tournament -- a singles and a doubles --
        # get different layouts without one overwriting the other.
        srow = QtWidgets.QHBoxLayout()
        srow.addWidget(QtWidgets.QLabel("Applies to:"))
        self._cfg_scope = _NoWheelComboBox()
        self._cfg_scope.addItems([self._CFG_SCOPE_SERIES, self._CFG_SCOPE_FILE])
        self._cfg_scope.setMinimumWidth(160)
        self._cfg_scope.setToolTip(
            "Series: every event whose name starts with the series name.\n"
            "VOD file: only the selected names file — a doubles bracket can then "
            "look different from the singles one it shares a name with.")
        self._cfg_scope.currentTextChanged.connect(self._on_cfg_scope_change)
        srow.addWidget(self._cfg_scope)
        srow.addStretch(1)
        cbox.addLayout(srow)

        self._cfg_series_label = _muted("No series selected")
        cbox.addWidget(self._cfg_series_label)

        self._cfg_line: dict[str, QtWidgets.QLineEdit] = {}
        self._cfg_pos: dict[str, tuple[QtWidgets.QLineEdit, QtWidgets.QLineEdit]] = {}
        self._cfg_color: dict[str, ColorField] = {}

        def grid():
            g = QtWidgets.QGridLayout()
            g.setHorizontalSpacing(6)
            g.setVerticalSpacing(3)
            return g

        g = grid()
        g.addWidget(QtWidgets.QLabel("Background:"), 0, 0)
        self._cfg_background = QtWidgets.QLineEdit()
        g.addWidget(self._cfg_background, 0, 1)
        bg_btn = QtWidgets.QPushButton("Browse…")
        bg_btn.clicked.connect(lambda: self._browse_overlay(self._cfg_background))
        g.addWidget(bg_btn, 0, 2)
        g.addWidget(QtWidgets.QLabel("Foreground:"), 1, 0)
        self._cfg_foreground = QtWidgets.QLineEdit()
        g.addWidget(self._cfg_foreground, 1, 1)
        fg_btn = QtWidgets.QPushButton("Browse…")
        fg_btn.clicked.connect(lambda: self._browse_overlay(self._cfg_foreground))
        g.addWidget(fg_btn, 1, 2)
        g.addWidget(QtWidgets.QLabel("Font:"), 2, 0)
        self._cfg_font = _NoWheelComboBox()
        font_files = sorted(f.name for f in (ROOT / "Resources" / "Fonts").glob("*")
                            if f.suffix.lower() in (".ttf", ".otf"))
        self._cfg_font.addItems([""] + font_files)
        g.addWidget(self._cfg_font, 2, 1)
        cbox.addLayout(g)

        rowf = QtWidgets.QHBoxLayout()
        self._cfg_glow = QtWidgets.QCheckBox("Character Glow")
        self._cfg_one_char = QtWidgets.QCheckBox("One Character Per Player")
        rowf.addWidget(self._cfg_glow)
        rowf.addSpacing(20)
        rowf.addWidget(self._cfg_one_char)
        rowf.addStretch(1)
        cbox.addLayout(rowf)

        rs = QtWidgets.QHBoxLayout()
        rs.addWidget(QtWidgets.QLabel("Char Scale:"))
        for lbl, key in [("1-char", "resize_1"), ("2-char", "resize_2"), ("3-char", "resize_3")]:
            rs.addSpacing(8)
            rs.addWidget(QtWidgets.QLabel(lbl))
            f = NormalizedField(0.0, 1.0)
            self._cfg_line[key] = f.edit
            rs.addWidget(f, 1)
        cbox.addLayout(rs)

        def pos_row(label, *keys, lo=-1.0, hi=1.0):
            r = QtWidgets.QHBoxLayout()
            lab = QtWidgets.QLabel(label)
            lab.setFixedWidth(90)
            r.addWidget(lab)
            for k in keys:
                fx, fy = NormalizedField(lo, hi), NormalizedField(lo, hi)
                # Store the boxes, not the wrappers: every load/save/clear path
                # already speaks QLineEdit, and the sliders follow them.
                self._cfg_pos[k] = (fx.edit, fy.edit)
                r.addWidget(QtWidgets.QLabel("x"))
                r.addWidget(fx, 1)
                r.addWidget(QtWidgets.QLabel("y"))
                r.addWidget(fy, 1)
                r.addSpacing(8)
            cbox.addLayout(r)

        cbox.addWidget(_muted("Character Positions  (x, y — normalized -1 to 1):"))
        pos_row("1-char:", "center_shift_1")
        pos_row("2-char:", "center_shift_2_1", "center_shift_2_2")
        pos_row("3-char:", "center_shift_3_1", "center_shift_3_2", "center_shift_3_3")

        rsz = QtWidgets.QHBoxLayout()
        rsz.addWidget(QtWidgets.QLabel("Font Sizes:"))
        for lbl, key in [("P1", "font_player1_size"), ("P2", "font_player2_size"),
                         ("Event", "font_event_size"), ("Round", "font_round_size")]:
            rsz.addSpacing(8)
            rsz.addWidget(QtWidgets.QLabel(lbl))
            e = _hline("", 50)
            self._cfg_line[key] = e
            rsz.addWidget(e)
        rsz.addSpacing(16)
        rsz.addWidget(QtWidgets.QLabel("Angle°"))
        e = _hline("", 45)
        self._cfg_line["text_angle"] = e
        rsz.addWidget(e)
        rsz.addStretch(1)
        cbox.addLayout(rsz)

        cbox.addWidget(_muted("Font Colors  (P1, P2, Event, Round):"))
        rc = QtWidgets.QHBoxLayout()
        for lbl, key in [("P1:", "font_color1"), ("P2:", "font_color2"),
                         ("Event:", "font_color3"), ("Round:", "font_color4")]:
            rc.addWidget(QtWidgets.QLabel(lbl))
            cf = ColorField("#FFFFFF")
            self._cfg_color[key] = cf
            rc.addWidget(cf)
            rc.addSpacing(12)
        rc.addStretch(1)
        cbox.addLayout(rc)

        cbox.addWidget(_muted("Text Label Positions  (x, y — normalized 0 to 1):"))
        pos_row("Player 1:", "text_player1", lo=0.0, hi=1.0)
        pos_row("Player 2:", "text_player2", lo=0.0, hi=1.0)
        pos_row("Event:", "text_event", lo=0.0, hi=1.0)
        pos_row("Round:", "text_round", lo=0.0, hi=1.0)

        rcw = QtWidgets.QHBoxLayout()
        lab = QtWidgets.QLabel("Char Window:")
        lab.setFixedWidth(90)
        rcw.addWidget(lab)
        rcw.addWidget(QtWidgets.QLabel("w"))
        cw_w = NormalizedField(0.0, 1.0)
        rcw.addWidget(cw_w, 1)
        rcw.addWidget(QtWidgets.QLabel("h"))
        cw_h = NormalizedField(0.0, 1.0)
        rcw.addWidget(cw_h, 1)
        self._cfg_pos["char_window"] = (cw_w.edit, cw_h.edit)
        cbox.addLayout(rcw)

        cbox.addWidget(_muted("Character Offsets  (x, y — normalized 0 to 1):"))
        pos_row("P1 Offset:", "char_offset1", lo=0.0, hi=1.0)
        pos_row("P2 Offset:", "char_offset2", lo=0.0, hi=1.0)

        rer = QtWidgets.QHBoxLayout()
        self._cfg_single_text = QtWidgets.QCheckBox("Single Text Block")
        rer.addWidget(self._cfg_single_text)
        rer.addSpacing(20)
        rer.addWidget(QtWidgets.QLabel("Separator:"))
        self._cfg_text_split = _hline("", 110)
        rer.addWidget(self._cfg_text_split)
        rer.addStretch(1)
        cbox.addLayout(rer)
        cbox.addWidget(_muted(
            "Single Text Block: renders the event name and round as one combined label.\n"
            "Separator: the string placed between them, e.g. \" — \"."))

        rcb = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save Config")
        save.clicked.connect(self._save_thumbnail_config)
        rcb.addWidget(save)
        clear = QtWidgets.QPushButton("Clear Config")
        clear.clicked.connect(self._clear_thumbnail_config)
        rcb.addWidget(clear)
        rcb.addStretch(1)
        cbox.addLayout(rcb)

        self._build_config_preview(cbox)


    _CFG_SCOPE_SERIES = "Series"
    _CFG_SCOPE_FILE = "VOD file"

    def _cfg_scope_is_file(self) -> bool:
        combo = getattr(self, "_cfg_scope", None)
        return combo is not None and combo.currentText() == self._CFG_SCOPE_FILE

    def _cfg_target_file(self) -> str:
        """The names file a file-scoped config is written for."""
        combo = getattr(self, "_vod_file", None)
        return combo.currentText().strip() if combo is not None else ""

    def _saved_file_config(self, name: str) -> dict:
        """The stored override for one names file, matched as the generator does.

        Case-insensitively: the generator looks the file up by the basename it
        builds from the event name ("{event} names.txt"), which only matches the
        file on disk ("{Event} Names.txt") because Windows ignores case.
        """
        if not name:
            return {}
        wanted = name.strip().lower()
        for key, cfg in (self._event_configs.get(FILE_CONFIG_KEY) or {}).items():
            if str(key).strip().lower() == wanted:
                return cfg
        return {}

    def _config_base_props(self, series: str) -> dict:
        """What the form values sit on top of.

        A file config overrides *the series config*, not the Python defaults, so
        in file scope the series entry is part of the base -- otherwise the
        preview would draw a layout no run ever produces.
        """
        base = _base_event_props(series)
        if self._cfg_scope_is_file():
            return {**base, **self._event_configs.get(series, {})}
        return base

    def _on_cfg_scope_change(self):
        self._reload_config_form()

    def _reload_config_form(self):
        if hasattr(self, "_thumb_series") and hasattr(self, "_cfg_series_label"):
            self._load_config_into_form(self._thumb_series.currentText())

    def _cfg_scope_summary(self, series: str) -> str:
        """The line under the scope picker: what is being edited, and any catch."""
        if not self._cfg_scope_is_file():
            return f"Editing: {series}" if series else "No series selected"
        name = self._cfg_target_file()
        if not name:
            return "No VOD file selected"
        text = f"Editing: {name}"
        if not self._saved_file_config(name):
            text += " (new -- starting from the series config)"
        # A run reads the file its *event name* implies, so a config on any other
        # file would never be applied. Say so rather than let it quietly do
        # nothing.
        event_name = getattr(self, "_thumb_event_name", None)
        event_name = event_name.text().strip() if event_name is not None else ""
        if event_name and name.lower() != f"{event_name} names.txt".lower():
            text += f' -- note: generating "{event_name}" reads "{event_name} Names.txt"'
        return text

    def _load_config_into_form(self, series: str):
        if not hasattr(self, "_cfg_series_label"):
            return
        if self._cfg_scope_is_file():
            saved = self._saved_file_config(self._cfg_target_file())
        else:
            saved = self._event_configs.get(series, {})
        self._cfg_series_label.setText(self._cfg_scope_summary(series))
        base = self._config_base_props(series)
        cfg = {**base, **saved}

        self._cfg_background.setText(cfg.get("background_file", ""))
        self._cfg_foreground.setText(cfg.get("foreground_file", ""))
        font_path = cfg.get("font_location", "")
        self._cfg_font.setCurrentText(Path(font_path).name if font_path else "")
        self._cfg_glow.setChecked(bool(cfg.get("char_glow_bool", False)))
        self._cfg_one_char.setChecked(bool(cfg.get("one_char_flag", False)))

        for key in self._CFG_FLOAT + self._CFG_INT:
            self._cfg_line[key].setText(str(cfg[key]) if key in cfg else "")

        for key in self._CFG_POS:
            xe, ye = self._cfg_pos[key]
            val = cfg.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                xe.setText(str(val[0]))
                ye.setText(str(val[1]))
            else:
                xe.setText("")
                ye.setText("")

        for key in self._CFG_COLOR:
            self._cfg_color[key].setValue(cfg.get(key, "#FFFFFF"))

        self._cfg_single_text.setChecked(bool(cfg.get("event_round_single_text", False)))
        self._cfg_text_split.setText(cfg.get("event_round_text_split", ""))
        self._schedule_config_preview()

    #: Reports the canvas box so the capture can be cropped to the graphic.
    #: Stringified deliberately -- a bare JS array comes back from
    #: runJavaScript() as an empty string, so only JSON survives the bridge.
    _EXPORT_BOX_JS = """(function () {
        const c = document.getElementById('canvas');
        return JSON.stringify(c ? [c.offsetWidth, c.offsetHeight] : null);
    })()"""

    def _export_top8_image(self):
        """Render the selected Top 8 HTML to a PNG, wherever the user wants it.

        Rendering goes through the QtWebEngine already bundled with the GUI rather
        than a browser on the machine: the capture then works no matter what the
        default browser is (Brave, for one, hangs in headless mode), and needs
        nothing added to the HTML -- any page whose graphic starts at the top-left
        corner exports correctly, including one the user supplied themselves.
        """
        name = self._top8_html_file.currentText()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            self._log(f"[Export needs QtWebEngine: {exc}]\n")
            return

        start_dir = getattr(self, "_top8_export_dir", "") or str(ROOT / "Top_8_Results")
        suggested = str(Path(start_dir) / (Path(name).stem + ".png"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Top 8 image", suggested, "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        self._top8_export_dir = str(Path(path).parent)
        self._top8_export_btn.setEnabled(False)
        self._log(f"[Rendering {name}…]\n")

        view = QWebEngineView()
        # Larger than the 1920-wide canvas in both directions, so the page's own
        # fit script leaves it at 1:1 anchored in the corner and the capture is
        # just a crop from (0, 0).
        view.resize(2100, 1250)
        # Lays out and renders without ever appearing on screen -- verified to
        # produce a byte-identical capture to a shown window.
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view.show()
        self._top8_export_view = view  # must outlive this function

        def on_load(ok):
            if not ok:
                self._finish_top8_export(None, path, "page failed to load")
                return
            # Give the images, the webfont and fitText a moment to settle; the
            # page only sizes its text correctly once all three have landed.
            QtCore.QTimer.singleShot(1500, lambda: self._capture_top8_export(path))

        view.loadFinished.connect(on_load)
        view.load(QtCore.QUrl(self._top8_preview_url(name)))

    def _capture_top8_export(self, path: str):
        view = getattr(self, "_top8_export_view", None)
        if view is None:
            return
        pixmap = view.grab()
        view.page().runJavaScript(
            self._EXPORT_BOX_JS,
            lambda box: self._finish_top8_export(pixmap, path, None, box))

    def _finish_top8_export(self, pixmap, path: str, error=None, box=None):
        view = getattr(self, "_top8_export_view", None)
        self._top8_export_view = None
        if view is not None:
            view.deleteLater()
        self._top8_export_btn.setEnabled(True)
        if error or pixmap is None or pixmap.isNull():
            self._log(f"[Export failed: {error or 'nothing was rendered'}]\n")
            return

        try:
            box = json.loads(box) if isinstance(box, str) else box
        except ValueError:
            box = None
        if box and len(box) >= 2:
            width, height = int(box[0]), int(box[1])
        else:
            # No #canvas element (someone else's HTML): keep the whole capture.
            width, height = pixmap.width(), pixmap.height()
        width = max(1, min(width, pixmap.width()))
        height = max(1, min(height, pixmap.height()))
        # The canvas picks up a few pixels of baseline gap under its first image,
        # so a graphic a hair taller than 16:9 is snapped back to it. One that is
        # genuinely a different shape keeps its own height.
        wide = round(width * 9 / 16)
        if wide <= height <= wide * 1.02:
            height = wide
        if pixmap.copy(0, 0, width, height).save(path, "PNG"):
            self._log(f"[Saved {width}x{height} image: {path}]\n")
        else:
            self._log(f"[Export failed: could not write {path}]\n")

    #: Preview size. The page scales its 1920-wide canvas to whatever view it
    #: is given, so this is purely how much room the preview gets on screen.
    _TOP8_PREVIEW_SIZE = (1200, 675)

    def _build_top8_preview_section(self, parent_layout):
        """The Top 8 Preview section: a live render plus the PNG export.

        Its own section rather than a corner of Layout Config, so the render gets
        real room and sits next to the data and the HTML it is built from.
        """
        box = CollapsibleBox("Top 8 Preview", collapsed=False)
        parent_layout.addWidget(box)

        self._top8_preview_view = None
        self._top8_preview_url_loaded = ""
        self._top8_preview_holder = QtWidgets.QWidget()
        holder = QtWidgets.QVBoxLayout(self._top8_preview_holder)
        holder.setContentsMargins(0, 0, 0, 0)
        self._top8_preview_placeholder = _muted("Preview starting…")
        self._top8_preview_placeholder.setFixedSize(*self._TOP8_PREVIEW_SIZE)
        self._top8_preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top8_preview_placeholder.setStyleSheet(
            f"background-color: {_BG3}; border-radius: 4px;")
        holder.addWidget(self._top8_preview_placeholder)

        # Buttons, render and hint share one column the width of the preview, and
        # the column is centred in the section -- so the controls line up with the
        # render's left edge instead of drifting away from it.
        column = QtWidgets.QWidget()
        column.setFixedWidth(self._TOP8_PREVIEW_SIZE[0])
        col = QtWidgets.QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)

        btn_row = QtWidgets.QHBoxLayout()
        self._top8_export_btn = QtWidgets.QPushButton("Save Image…")
        self._top8_export_btn.setToolTip(
            "Render this graphic to a full-size PNG and choose where to save it")
        self._top8_export_btn.clicked.connect(self._export_top8_image)
        btn_row.addWidget(self._top8_export_btn)
        refresh = QtWidgets.QPushButton("⟳ Refresh")
        refresh.setToolTip("Reload the preview from the files on disk")
        refresh.clicked.connect(self._force_refresh_top8_preview)
        btn_row.addWidget(refresh)
        btn_row.addStretch(1)
        col.addLayout(btn_row)
        col.addWidget(_muted(
            "Renders the selected HTML file. It reloads itself whenever Layout "
            "Config or the Top 8 text data saves; Save Image writes it out at "
            "full size."))
        col.addWidget(self._top8_preview_holder)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column)
        row.addStretch(1)
        box.addLayout(row)

    def prewarm_top8_preview(self):
        """Build the web view while the main window is still hidden.

        Bringing QtWebEngine up reconfigures the top-level window's surface, and
        on Windows that repaints the entire window - a white flash wherever it
        happens. Doing it before the window is ever shown means nobody sees it.
        The cost is a Chromium process at startup rather than on first use.
        """
        self._build_top8_preview()

    def _build_top8_preview(self):
        if self._top8_preview_view is not None:
            return
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            self._top8_preview_placeholder.setText(
                "Preview needs QtWebEngine:" + NL + f"{exc}")
            return
        view = QWebEngineView()
        view.setFixedSize(*self._TOP8_PREVIEW_SIZE)
        # Chromium paints its viewport white until the document's own background
        # arrives, which on a dark GUI reads as a flash. Paint both the page and
        # the widget behind it in the panel colour so there is never a white
        # frame to see.
        dark = QtGui.QColor(_BG3)
        view.page().setBackgroundColor(dark)
        palette = view.palette()
        for role in (QtGui.QPalette.ColorRole.Window, QtGui.QPalette.ColorRole.Base):
            palette.setColor(role, dark)
        view.setPalette(palette)
        view.setAutoFillBackground(True)
        # The page scales its 1920-wide canvas to the window it is given, so a
        # small view shows the whole graphic without any zoom handling here.
        # It stays hidden behind the placeholder until it has something to show;
        # the page re-fits itself on becoming visible (it watches the viewport).
        view.hide()
        view.loadFinished.connect(self._on_top8_preview_loaded)
        self._top8_preview_view = view
        # Index 0, so the view takes the placeholder's slot rather than stacking
        # below it and growing the section.
        self._top8_preview_holder.layout().insertWidget(0, view)
        self._refresh_top8_preview()

    def _on_top8_preview_loaded(self, ok: bool):
        """Swap the placeholder for the view once there is a painted page behind it."""
        view = self._top8_preview_view
        if view is None:
            return
        if not ok:
            self._top8_preview_placeholder.setText("Preview failed to load")
            return
        if not view.isVisible():
            self._top8_preview_placeholder.hide()
            view.show()

    def _force_refresh_top8_preview(self):
        """Reload from scratch, whatever state the view thinks it is in."""
        self._top8_preview_url_loaded = ""   # force a fresh load(), not a reload
        self._refresh_top8_preview()

    def _refresh_top8_preview(self):
        """Point the preview at the selected file, or reload it in place."""
        view = getattr(self, "_top8_preview_view", None)
        if view is None:
            return
        name = self._top8_html_file.currentText()
        if not name:
            return
        url = self._top8_preview_url(name)
        if url != self._top8_preview_url_loaded:
            self._top8_preview_url_loaded = url
            view.load(QtCore.QUrl(url))
            return
        # Same file, new contents: bypass the cache so the edit actually shows.
        from PySide6.QtWebEngineCore import QWebEnginePage
        view.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)

    #: Preview size. 16:9, so it matches the canvas the generator draws.
    _CFG_PREVIEW_SIZE = (864, 486)

    def _build_config_preview(self, cbox):
        """Live thumbnail preview of whatever the config form currently says.

        Every value above is a normalized coordinate or a scale factor, which is
        hard to picture; this draws the result instead. It goes through the real
        generator with only_one=True, so the layout is exact -- just one
        character arrangement rather than all six.
        """
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BG3};")
        cbox.addWidget(sep)

        # Controls, hint and image share one column the width of the preview, and
        # the column is centred in the section -- the same arrangement the Top 8
        # preview uses, so the controls line up with the image's left edge instead
        # of drifting away from it as the window widens.
        column = QtWidgets.QWidget()
        column.setFixedWidth(self._CFG_PREVIEW_SIZE[0])
        col = QtWidgets.QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Preview:"))
        self._cfg_preview_sample = _NoWheelComboBox()
        self._cfg_preview_sample.addItems(
            ["Selected VOD line", "1 character", "2 characters", "3 characters"])
        self._cfg_preview_sample.setCurrentText("3 characters")
        self._cfg_preview_sample.setToolTip(
            "Which match to draw. The numbered samples use placeholder players so "
            "every character slot is filled, which is what the 1/2/3-char shifts "
            "above control.")
        self._cfg_preview_sample.currentTextChanged.connect(
            lambda *_: self._render_config_preview(force=True))
        row.addWidget(self._cfg_preview_sample)
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.setToolTip("Redraw the preview now")
        refresh.clicked.connect(lambda: self._render_config_preview(force=True))
        row.addWidget(refresh)
        self._cfg_preview_open = QtWidgets.QPushButton("Open Full Size")
        self._cfg_preview_open.setToolTip("Open the preview at full resolution")
        self._cfg_preview_open.setEnabled(False)
        self._cfg_preview_open.clicked.connect(self._open_preview_full_size)
        row.addWidget(self._cfg_preview_open)
        row.addStretch(1)
        col.addLayout(row)

        col.addWidget(_muted(
            "Draws the fields above as they stand, saved or not, so a shift can be "
            "judged before committing it. Generating still produces every character "
            "arrangement; this shows the first."))

        # Which line actually got drawn. A selected row that is a comment, a
        # header or an unparseable line falls back to the first real match, and
        # without this the preview looks like it simply ignored the selection.
        self._cfg_preview_line_label = _muted("")
        self._cfg_preview_line_label.setWordWrap(False)
        self._cfg_preview_line_label.setToolTip("The match line this preview was drawn from")
        col.addWidget(self._cfg_preview_line_label)

        self._cfg_preview_pil = None
        self._cfg_preview_label = QtWidgets.QLabel("Press Refresh to draw a preview")
        self._cfg_preview_label.setFixedSize(*self._CFG_PREVIEW_SIZE)
        self._cfg_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cfg_preview_label.setWordWrap(True)
        self._cfg_preview_label.setStyleSheet(
            f"background-color: {_BG3}; border-radius: 4px;")
        col.addWidget(self._cfg_preview_label)

        centred = QtWidgets.QHBoxLayout()
        centred.addStretch(1)
        centred.addWidget(column)
        centred.addStretch(1)
        cbox.addLayout(centred)

        # A burst of typing should render once, not once per keystroke.
        self._cfg_preview_timer = QtCore.QTimer(self)
        self._cfg_preview_timer.setSingleShot(True)
        self._cfg_preview_timer.setInterval(500)
        self._cfg_preview_timer.timeout.connect(self._render_config_preview)
        edits = list(self._cfg_line.values()) + [
            self._cfg_background, self._cfg_foreground, self._cfg_text_split]
        for xe, ye in self._cfg_pos.values():
            edits += [xe, ye]
        edits += [cf.edit for cf in self._cfg_color.values()]
        for e in edits:
            e.textChanged.connect(self._schedule_config_preview)
        for cb in (self._cfg_glow, self._cfg_one_char, self._cfg_single_text):
            cb.toggled.connect(self._schedule_config_preview)
        self._cfg_font.currentTextChanged.connect(self._schedule_config_preview)

    def _schedule_config_preview(self, *_args):
        """Queue a redraw, but only while the preview is actually on screen."""
        label = getattr(self, "_cfg_preview_label", None)
        if label is None or not label.isVisible():
            return
        self._cfg_preview_timer.start()

    def _selected_vod_match_line(self) -> str:
        """The VOD row the user has selected, else the first real match line."""
        model = getattr(self, "_vod_model", None)
        if model is None:
            return ""
        row = getattr(self, "_vod_selected_source_row", -1)
        if 0 <= row < model.rowCount():
            text = model.text_at(row)
            if _VOD_VS_RE.search(text):
                return text
        for r in range(model.rowCount()):
            text = model.text_at(r)
            if _VOD_VS_RE.search(text):
                return text
        return ""

    def _preview_sample_line(self, event_name: str):
        """(match line, event name to parse it with, abbreviation) for the preview.

        A real VOD line is parsed with the event name and abbreviation its own
        file declared, since that is what the generator would use; the synthetic
        samples are built around the event name in the form.
        """
        mode = self._cfg_preview_sample.currentText()
        if mode.startswith("Selected VOD"):
            line = self._selected_vod_match_line()
            if line:
                return (line,
                        getattr(self, "_vod_event_name", "") or event_name,
                        getattr(self, "_vod_abbrev", ""))
        try:
            count = int(mode.split()[0])
        except (ValueError, IndexError):
            count = 3
        p1 = _preview_sample_chars(count)
        # Offset the second player so the two sides are told apart at a glance.
        p2 = _preview_sample_chars(count, skip=count)
        if not p1 or not p2:
            raise RuntimeError("No character renders found to draw a sample with")
        return (f"{event_name} - Grand Final - Player One ({', '.join(p1)}) Vs "
                f"Player Two ({', '.join(p2)}) - SSBM", event_name, "")

    def _build_preview_image(self):
        """Render one thumbnail from the current form values."""
        if _pg is None:
            raise RuntimeError("populate_melee_globals could not be imported")
        gen = _thumbnail_generator()
        from PIL import Image

        series = self._thumb_series.currentText().strip()
        props = {**_base_event_props(series), **self._collect_config_form()}
        event_name = (self._thumb_event_name.text().strip() or series or "Sample Event")
        props["event_name"] = event_name
        props["event_short_name"] = event_name
        props["show_first_image"] = False
        # The generator resolves these against its working directory; the GUI's
        # is not guaranteed to be the generator root.
        for key in ("char_renders", "background_file", "foreground_file", "font_location"):
            val = props.get(key)
            if val and not os.path.isabs(str(val)):
                props[key] = str(ROOT / val)

        line, parse_name, abbrev = self._preview_sample_line(event_name)
        self._cfg_preview_line = line
        gen._properties = props
        gen._character_database = _pg.readCharDatabase(str(CHAR_DB_PATH))
        gen._player_database = _pg.readPlayerDatabase(
            str(PLAYER_DB_PATH), char_database=gen._character_database)
        # The placeholder players are deliberately absent from the player
        # database. Unlike Rivals, no default-costume map is needed to cope with
        # that: this generator falls back to alt 1 for any character it cannot
        # find a costume for, which every render folder has.

        with tempfile.TemporaryDirectory() as tmp:
            match = gen.createMatches([line], os.path.join(tmp, "missing.log"),
                                      parse_name, event_name, event_abbrev=abbrev)[0]
        background = Image.open(props["background_file"]).convert("RGBA")
        foreground = Image.open(props["foreground_file"]).convert("RGBA")
        gen.createRoundImages([match], background, foreground, only_one=True)
        return match.Images[0].convert("RGBA")

    def _render_config_preview(self, force: bool = False):
        label = getattr(self, "_cfg_preview_label", None)
        if label is None or (not force and not label.isVisible()):
            return
        try:
            image = self._build_preview_image()
        except Exception as exc:
            self._cfg_preview_pil = None
            self._cfg_preview_open.setEnabled(False)
            self._cfg_preview_line = ""
            self._show_preview_source_line()
            label.setPixmap(QtGui.QPixmap())
            label.setText("Preview failed:\n{e}".format(e=exc))
            return
        self._cfg_preview_pil = image
        self._cfg_preview_open.setEnabled(True)
        self._show_preview_source_line()
        qimage = QtGui.QImage(image.tobytes("raw", "RGBA"), image.width, image.height,
                              QtGui.QImage.Format.Format_RGBA8888).copy()
        label.setText("")
        label.setPixmap(QtGui.QPixmap.fromImage(qimage).scaled(
            label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _show_preview_source_line(self):
        """Name the line under the preview, elided to the column width."""
        label = getattr(self, "_cfg_preview_line_label", None)
        if label is None:
            return
        line = getattr(self, "_cfg_preview_line", "")
        if not line:
            label.setText("")
            return
        metrics = QtGui.QFontMetrics(label.font())
        label.setText(metrics.elidedText(
            "Drawn from: " + strip_skins(line),
            Qt.TextElideMode.ElideRight, self._CFG_PREVIEW_SIZE[0] - 8))

    def _open_preview_full_size(self):
        image = getattr(self, "_cfg_preview_pil", None)
        if image is None:
            return
        path = Path(tempfile.gettempdir()) / "rivals_config_preview.png"
        try:
            image.save(str(path))
            os.startfile(str(path))
        except Exception as exc:
            self._log("[Error opening preview: {e}]\n".format(e=exc))

    def _collect_config_form(self) -> dict:
        """The config the form currently describes, saved or not.

        Shared by Save Config and the live preview, so what the preview draws is
        exactly what saving would write.
        """
        cfg: dict = {}
        bg = self._cfg_background.text().strip()
        fg = self._cfg_foreground.text().strip()
        font_name = self._cfg_font.currentText().strip()
        if bg:
            cfg["background_file"] = bg
        if fg:
            cfg["foreground_file"] = fg
        if font_name:
            cfg["font_location"] = str(Path("Resources") / "Fonts" / font_name)
        cfg["char_glow_bool"] = self._cfg_glow.isChecked()
        cfg["one_char_flag"] = self._cfg_one_char.isChecked()

        for key in self._CFG_FLOAT:
            val = self._cfg_line[key].text().strip()
            if val:
                try:
                    cfg[key] = float(val)
                except ValueError:
                    pass
        for key in self._CFG_INT:
            val = self._cfg_line[key].text().strip()
            if val:
                try:
                    cfg[key] = int(val)
                except ValueError:
                    pass
        for key in self._CFG_POS:
            xe, ye = self._cfg_pos[key]
            x, y = xe.text().strip(), ye.text().strip()
            if x and y:
                try:
                    cfg[key] = [float(x), float(y)]
                except ValueError:
                    pass
        for key in self._CFG_COLOR:
            c = self._cfg_color[key].value()
            if c:
                cfg[key] = c

        cfg["event_round_single_text"] = self._cfg_single_text.isChecked()
        split = self._cfg_text_split.text()
        if split:
            cfg["event_round_text_split"] = split
        return cfg

    def _save_thumbnail_config(self):
        series = self._thumb_series.currentText().strip()
        if self._cfg_scope_is_file():
            name = self._cfg_target_file()
            if not name:
                self._log("[Error: no VOD file selected]\n")
                return
            files = self._event_configs.setdefault(FILE_CONFIG_KEY, {})
            # Replace whatever spelling is stored for this file, so a case
            # difference cannot leave two entries fighting over one run.
            for key in [k for k in files if str(k).strip().lower() == name.lower()]:
                del files[key]
            files[name] = self._collect_config_form()
            self._save_event_configs()
            self._log(f"[Config saved for file \"{name}\"]\n")
            self._cfg_series_label.setText(self._cfg_scope_summary(series))
            return
        if not series:
            self._log("[Error: no series selected]\n")
            return
        self._event_configs[series] = self._collect_config_form()
        self._save_event_configs()
        self._log(f"[Config saved for \"{series}\"]\n")

    def _clear_thumbnail_config(self):
        series = self._thumb_series.currentText().strip()
        if self._cfg_scope_is_file():
            # Dropping a file override means falling back to the series config,
            # so reload the form onto that rather than emptying every box.
            name = self._cfg_target_file()
            files = self._event_configs.get(FILE_CONFIG_KEY) or {}
            gone = [k for k in files if str(k).strip().lower() == name.lower()]
            for key in gone:
                del files[key]
            if gone:
                self._save_event_configs()
                self._log(f"[Config for file \"{name}\" removed -- "
                          f"back to the series config]\n")
            self._load_config_into_form(series)
            return
        if series in self._event_configs:
            del self._event_configs[series]
            self._save_event_configs()
        self._cfg_background.clear()
        self._cfg_foreground.clear()
        self._cfg_font.setCurrentText("")
        self._cfg_glow.setChecked(False)
        self._cfg_one_char.setChecked(False)
        for e in self._cfg_line.values():
            e.clear()
        for xe, ye in self._cfg_pos.values():
            xe.clear()
            ye.clear()
        for cf in self._cfg_color.values():
            cf.setValue("#FFFFFF")
        self._cfg_single_text.setChecked(False)
        self._cfg_text_split.clear()
        self._log(f"[Config cleared for \"{series}\"]\n")

    def _browse_overlay(self, target: QtWidgets.QLineEdit):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select overlay image", "",
            "Images (*.png *.jpg *.jpeg);;All files (*.*)")
        if not path:
            return
        dest_dir = ROOT / "Resources" / "Overlays"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(path).name
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(path, dest)
        target.setText(str(Path("Resources") / "Overlays" / Path(path).name))

    def _on_vod_row_changed(self, current, _previous):
        if current.isValid():
            src = self._vod_proxy.mapToSource(current)
            self._vod_selected_source_row = src.row()

    def _on_vod_row_clicked(self, index):
        if index.isValid():
            self._set_vod_selected_row(self._vod_proxy.mapToSource(index).row())

    def _on_vod_model_reset(self):
        self._set_vod_selected_row(-1)

    def _set_vod_selected_row(self, row: int):
        """Remember the row the preview should draw, and redraw if it changed."""
        if row == getattr(self, "_vod_selected_source_row", -1):
            return
        self._vod_selected_source_row = row
        # Selecting a line is the whole point of the "Selected VOD line" sample,
        # so don't make the user press Refresh as well.
        sample = getattr(self, "_cfg_preview_sample", None)
        if sample is not None and sample.currentText().startswith("Selected VOD"):
            self._schedule_config_preview()

    def _vod_move_row(self, proxy_row: int, delta: int):
        if self._vod_filter.text():
            self._log("[Clear the filter before reordering lines]\n")
            return
        src_row = self._vod_proxy.mapToSource(
            self._vod_proxy.index(proxy_row, 0)).row()
        new = self._vod_model.move_row(src_row, delta)
        if new < 0:
            return
        self._vod_selected_source_row = new
        self._vod_rebuild_red_rows()

    def _vod_rebuild_red_rows(self):
        self._vod_red_rows = {
            r for r in range(self._vod_model.rowCount())
            if _vod_missing_chars(self._vod_model.text_at(r))
        }

    def _on_vod_data_changed(self, top_left, bottom_right, roles=None):
        # Ignore repaint-only changes (a check-mark repainting the row, say):
        # they cannot have altered the text this tracks.
        if roles and (Qt.ItemDataRole.EditRole not in roles
                      and Qt.ItemDataRole.DisplayRole not in roles):
            return
        for row in range(top_left.row(), bottom_right.row() + 1):
            text = self._vod_model.text_at(row)
            was_red = row in self._vod_red_rows
            is_red = _vod_missing_chars(text)
            if is_red:
                self._vod_red_rows.add(row)
            else:
                self._vod_red_rows.discard(row)
            # Blanking a line or turning it into a comment also clears the red
            # flag, but neither is "character data complete" -- don't say so.
            if (was_red and not is_red
                    and text.strip() and not text.strip().startswith("#")):
                self._log(f"[Line {row + 1} character data complete]\n")

    def _on_vod_filter_changed(self, text: str):
        self._vod_proxy.setFilterFixedString(text)
        if self._vod_selected_source_row >= 0:
            src_idx = self._vod_model.index(self._vod_selected_source_row, 0)
            proxy_idx = self._vod_proxy.mapFromSource(src_idx)
            if proxy_idx.isValid():
                self._vod_view.setCurrentIndex(proxy_idx)
                self._vod_view.scrollTo(proxy_idx)

    def _update_import_btn(self):
        if not hasattr(self, "_import_players_btn"):
            return
        count = self._vod_model.rowCount()
        vs_lines = [self._vod_model.text_at(r) for r in range(count)
                    if _VOD_VS_RE.search(self._vod_model.text_at(r))]
        ready = bool(vs_lines) and not any(_vod_missing_chars(t) for t in vs_lines)
        self._import_players_btn.setEnabled(ready)
        if hasattr(self, "_import_skins_btn"):
            # Only worth offering when a line actually names a costume -- the
            # button has nothing to copy into the database otherwise -- and only
            # once every player has a row to write those costumes onto.
            named = any(":" in paren for t in vs_lines
                        for paren in _VOD_PARENS_RE.findall(t))
            missing = self._vod_players_missing_from_db(vs_lines)
            self._import_skins_btn.setEnabled(named and not missing)
            if not named:
                tip = "No line names a per-set costume (Character:Alt) yet"
            elif missing:
                shown = ", ".join(missing[:3])
                more = f" +{len(missing) - 3} more" if len(missing) > 3 else ""
                tip = (f"{len(missing)} player(s) are not in the player database "
                       f"({shown}{more}) — use Import Missing Players first")
            else:
                tip = ("Add every per-set costume named in these lines to that "
                       "player's row in the player database")
            self._import_skins_btn.setToolTip(tip)
        if hasattr(self, "_gen_thumb_btn"):
            self._gen_thumb_btn.setEnabled(ready)
            self._gen_thumb_btn.setToolTip(
                "" if ready else "Fill in character data for all match lines to enable"
            )

    def _vod_players_missing_from_db(self, lines) -> list:
        """Player tags in these lines with no row in the player database.

        Adding a costume to a player who has no row would silently do nothing, so
        the Add Missing Costumes button stays greyed out until Import Missing
        Players has created them. Reads the in-memory copy the Player Database
        tab keeps, since this runs on every edit to the VOD table.
        """
        db = getattr(self, "_db_players", None)
        if db is None:
            db = load_player_db()[1]
        known = {name.lower() for name in db}
        missing: list[str] = []
        for line in lines:
            for name, _chars in _parse_vod_team_members(line):
                if name.lower() not in known and name not in missing:
                    missing.append(name)
        return missing

    def _import_missing_skins(self):
        """Save every per-set costume named in these VOD lines onto its player's row.

        A costume typed into a line already renders without being in the
        database, so this is purely about making it stick -- next time it is one
        click away in the Set costumes dialog and the Player Database tab. New
        costumes are appended unstarred, and whichever costume was already
        winning for that character gets pinned, so no player's default silently
        changes.
        """
        headers, db = load_player_db()
        by_lower = {name.lower(): name for name in db}
        added = 0
        unknown: list[str] = []
        unresolved: list[str] = []
        for r in range(self._vod_model.rowCount()):
            for name, chars in _parse_vod_team_members(self._vod_model.text_at(r)):
                key = by_lower.get(name.lower())
                if key is None:
                    if name not in unknown:
                        unknown.append(name)
                    continue
                entries = db[key]
                for char, skin in chars:
                    if not skin:
                        continue
                    alt = stem_for_label(char, skin)
                    if not alt:
                        miss = f"{char}:{skin}"
                        if miss not in unresolved:
                            unresolved.append(miss)
                        continue
                    same = [i for i, (c, _) in enumerate(entries)
                            if c.upper() == char.upper()]
                    if any(split_pref(entries[i][1])[0] == alt for i in same):
                        continue
                    # A second costume makes the character's default ambiguous,
                    # so pin the one already in use -- same rule as Add Entry.
                    if same and not any(split_pref(entries[i][1])[1] for i in same):
                        c0, a0 = entries[same[0]]
                        entries[same[0]] = (c0, join_pref(split_pref(a0)[0], True))
                    entries.append((char, alt))
                    added += 1
                    self._log(f"[Costumes: added {char} — {alt} to '{key}']\n")

        for name in unknown:
            self._log(f"[Costumes: '{name}' is not in the player database — "
                      f"use Import Missing Players first]\n")
        for miss in unresolved:
            self._log(f"[Costumes: no render matches '{miss}']\n")
        if not added:
            self._log("[Costumes: nothing to add — every costume named is already "
                      "in the database]\n")
            return

        save_player_db(headers, db)
        self._log(f"[Costumes: saved {added} new costume "
                  f"{'entry' if added == 1 else 'entries'} to the database]\n")
        if hasattr(self, "_db_players"):
            self._db_players = db
            self._refresh_player_list()
            selected = getattr(self, "_db_selected_player", None)
            if selected in db:
                self._populate_char_tree(selected)

    def _import_missing_players(self):
        _headers, existing = load_player_db()
        existing_lower = {n.lower() for n in existing}
        new_players: dict = {}
        for r in range(self._vod_model.rowCount()):
            text = self._vod_model.text_at(r)
            # A doubles line names a team, which has no row of its own -- the
            # CSV splits on the comma the tag contains. Add a row per member,
            # with character *i* going to member *i*.
            for name, chars in _parse_vod_team_members(text):
                if not name or name.lower() in existing_lower:
                    continue
                key = name.lower()
                if key not in new_players:
                    new_players[key] = (name, set())
                new_players[key][1].update(c for c, _skin in chars)
        if not new_players:
            self._log("[Import Missing Players: no new players found]\n")
            return
        for _key, (name, chars) in new_players.items():
            entries = [(c, "1") for c in sorted(chars) if c]
            existing[name] = entries
        save_player_db(_headers, existing)
        self._log(f"[Imported {len(new_players)} new player(s): {', '.join(v[0] for v in new_players.values())}]\n")
        if hasattr(self, "_db_players"):
            self._db_players = existing
            self._refresh_player_list()

    # ------------------------------------------------------------------ #
    #  Event name <-> VOD file                                           #
    # ------------------------------------------------------------------ #
    # A run reads "{event} Names.txt", so the event name and the selected file
    # are two spellings of one choice. These keep them in step: picking either
    # one sets the other.
    _NAMES_SUFFIX = " Names.txt"

    @staticmethod
    def _event_name_for_file(name: str) -> str:
        """"Twist of Fate Doubles 3 Names.txt" -> "Twist of Fate Doubles 3"."""
        if name.lower().endswith(MeleeWindow._NAMES_SUFFIX.lower()):
            return name[:-len(MeleeWindow._NAMES_SUFFIX)]
        return name[:-4] if name.lower().endswith(".txt") else name

    def _file_for_event_name(self, event_name: str) -> str:
        """The listed file this event reads, matched as Windows matches it."""
        wanted = f"{event_name}{self._NAMES_SUFFIX}".lower()
        for i in range(self._vod_file.count()):
            if self._vod_file.itemText(i).lower() == wanted:
                return self._vod_file.itemText(i)
        return ""

    def _label_for_event(self, event_name: str) -> str:
        """The "# / Label" that rebuilds this event name from its series."""
        template = self._thumb_event_map.get(self._thumb_series.currentText(), "{n}")
        head, sep, tail = template.partition("{n}")
        # The event that *is* the series -- a tournament's own singles bracket,
        # beside its "... Doubles" and "... Crews" -- has no label at all. Its
        # name matches the template only once the separator that would have come
        # before the label is gone, so check that before anything else: falling
        # through to the whole name would label "Twist of Fate" with "Twist of
        # Fate" and spell the event "Twist of Fate Twist of Fate".
        if event_name.strip() == (head + tail).strip():
            return ""
        if sep and event_name.startswith(head) and event_name.endswith(tail):
            end = len(event_name) - len(tail) if tail else len(event_name)
            return event_name[len(head):end]
        return event_name

    def _refresh_thumb_event_names(self, file_names: list):
        """List the events that already have a names file, keeping the current one."""
        events = [self._event_name_for_file(n) for n in file_names]
        current = self._thumb_event_name.currentText()
        self._thumb_event_name.blockSignals(True)
        self._thumb_event_name.clear()
        self._thumb_event_name.addItems(events)
        self._thumb_event_name.setCurrentText(current)
        self._thumb_event_name.blockSignals(False)
        # With no number typed the name is just the series and a trailing space,
        # which names no event at all -- take the loaded file's instead. Only
        # then, so a number typed for an event not fetched yet is never lost.
        if events and not self._thumb_num.text().strip():
            loaded = self._vod_file.currentText()
            event_name = self._event_name_for_file(loaded) if loaded else events[0]
            self._thumb_num.setText(self._label_for_event(event_name))
            self._thumb_event_name.setCurrentText(event_name)

    def _on_thumb_event_pick(self, _index: int):
        """User picked an event: point the label and the VOD file at it."""
        event_name = self._thumb_event_name.currentText().strip()
        if not event_name:
            return
        label = self._label_for_event(event_name)
        if label != self._thumb_num.text().strip():
            # _update_thumb_name rewrites the event name from the template,
            # which this label reproduces exactly.
            self._thumb_num.setText(label)
        file_name = self._file_for_event_name(event_name)
        if file_name and file_name != self._vod_file.currentText():
            self._vod_file.setCurrentText(file_name)  # loads it
        self._refresh_open_folder_btn()
        self._save_settings()

    def _on_vod_file_pick(self, _index: int):
        """User picked a VOD file: name the event it holds."""
        event_name = self._event_name_for_file(self._vod_file.currentText())
        if not event_name or event_name == self._thumb_event_name.currentText().strip():
            return
        self._thumb_num.setText(self._label_for_event(event_name))  # -> _update_thumb_name
        self._thumb_event_name.setCurrentText(event_name)
        self._refresh_open_folder_btn()
        self._save_settings()

    def _generate_thumbnails(self):
        event_name = self._thumb_event_name.text().strip()
        if not event_name:
            self._log("[Error: event name is empty]\n")
            return
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"),
               "-e", event_name, "-o", str(ROOT / "Vod_Names" / "missing.log")]

        filter_text = getattr(self, "_vod_filter", None)
        filter_text = filter_text.text().strip() if filter_text else ""
        if filter_text and hasattr(self, "_vod_proxy"):
            src_count = self._vod_model.rowCount()
            comment_lines = [self._vod_model.text_at(r) for r in range(src_count)
                             if self._vod_model.text_at(r).strip().startswith("#")]
            proxy_count = self._vod_proxy.rowCount()
            match_lines = [
                self._vod_model.text_at(
                    self._vod_proxy.mapToSource(self._vod_proxy.index(pr, 0)).row()
                )
                for pr in range(proxy_count)
                if not self._vod_model.text_at(
                    self._vod_proxy.mapToSource(self._vod_proxy.index(pr, 0)).row()
                ).strip().startswith("#")
            ]
            tmp_path = ROOT / "Vod_Names" / "_filter_tmp names.txt"
            tmp_path.write_text("\n".join(comment_lines + match_lines), encoding="utf-8")
            # -v points at a temporary copy, whose name matches no config;
            # -c names the file the lines came from so its per-file config is
            # still the one applied.
            cmd += ["-v", str(tmp_path)]
            selected_vod = self._vod_loaded_name or self._vod_file.currentText()
            if selected_vod:
                cmd += ["-c", selected_vod]
            self._log(f"[Filter active: generating {len(match_lines)} line(s) matching \"{filter_text}\"]\n")

            def _cleanup(_):
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                self._refresh_open_folder_btn()

            self._run(cmd, on_done=_cleanup)
        else:
            self._run(cmd, on_done=self._refresh_open_folder_btn)

    def _refresh_open_folder_btn(self):
        event_name = self._thumb_event_name.text().strip()
        folder = ROOT / "Youtube_Thumbnails" / event_name
        self._open_thumb_btn.setEnabled(bool(event_name) and folder.is_dir())

    def _open_thumbnail_folder(self):
        folder = ROOT / "Youtube_Thumbnails" / self._thumb_event_name.text().strip()
        if not folder.is_dir():
            self._log(f"[Error: output folder not found: {folder}]\n")
            return
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"[Error opening folder: {exc}]\n")

    # --- VOD editor (virtualized table) ---
    def _build_vod_editor(self, parent_layout, expanding=False):
        cbox = CollapsibleBox("VOD Names", collapsed=False)
        if expanding:
            cbox.setExpanding()
        parent_layout.addWidget(cbox, 1 if expanding else 0)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("File:"))
        self._vod_file = _NoWheelComboBox()
        self._vod_file.setMinimumWidth(360)
        row.addWidget(self._vod_file)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh VOD file list")
        rb.clicked.connect(self._refresh_vod_files)
        row.addWidget(rb)
        row.addStretch(1)

        # Second row: the character/costume pickers and the two database
        # buttons. Splitting them off the file selector keeps each row short
        # enough to read left-to-right instead of one long strip of unrelated
        # controls.
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Character:"))
        self._vod_char_picker = QtWidgets.QComboBox()
        self._vod_char_picker.setMinimumWidth(160)
        self._vod_char_picker.setToolTip(
            "Pick a character to copy its exact spelling to the clipboard")
        self._refresh_vod_char_picker()
        self._vod_char_picker.activated.connect(self._copy_vod_char)
        # A new character invalidates the picked costume: reset to blank rather
        # than carrying over an alt number that means something else now.
        self._vod_char_picker.currentTextChanged.connect(
            lambda *_: self._refresh_vod_skin_picker(keep=False))
        row2.addWidget(self._vod_char_picker)
        crb = QtWidgets.QPushButton("⟳")
        crb.setObjectName("tool")
        crb.setToolTip("Refresh character list")
        crb.clicked.connect(self._refresh_vod_char_picker)
        row2.addWidget(crb)
        row2.addWidget(QtWidgets.QLabel("Costume:"))
        self._vod_skin_picker = QtWidgets.QComboBox()
        self._vod_skin_picker.setMinimumWidth(90)
        self._vod_skin_picker.setToolTip(
            "Optional per-set costume — picking one copies Character:Alt to the clipboard.\n"
            "Leave blank to use the player's preferred costume.")
        self._refresh_vod_skin_picker()
        # Same auto-copy as the character picker: choosing a costume puts the
        # whole "Character:Alt" token on the clipboard, ready to paste.
        self._vod_skin_picker.activated.connect(self._copy_vod_char)
        self._vod_skin_picker.currentTextChanged.connect(self._refresh_vod_preview)
        row2.addWidget(self._vod_skin_picker)
        cc = QtWidgets.QPushButton("Copy")
        cc.setToolTip("Copy the selected character (with costume, if chosen) to the clipboard")
        cc.clicked.connect(self._copy_vod_char)
        row2.addWidget(cc)
        row2.addSpacing(20)
        self._import_skins_btn = QtWidgets.QPushButton("Add Missing Costumes")
        self._import_skins_btn.clicked.connect(self._import_missing_skins)
        self._import_skins_btn.setEnabled(False)
        row2.addWidget(self._import_skins_btn)
        self._import_players_btn = QtWidgets.QPushButton("Import Missing Players")
        self._import_players_btn.setToolTip(
            "Add players from these VOD lines who are not yet in the player database")
        self._import_players_btn.clicked.connect(self._import_missing_players)
        self._import_players_btn.setEnabled(False)
        row2.addWidget(self._import_players_btn)
        row2.addStretch(1)

        # Filter bar. Built here but added directly above the table further
        # down, so it sits against the lines it filters instead of floating in
        # the picker column beside a 200px preview. The set count leads it -- a
        # slightly shorter filter box is a fair trade for seeing at a glance how
        # many real match lines the file holds.
        filter_row = QtWidgets.QHBoxLayout()
        self._vod_count_label = _muted("")
        self._vod_count_label.setWordWrap(False)
        # Occupy exactly the preview's column so the label after it starts where
        # "File:" does one row up.
        self._vod_count_label.setFixedWidth(_VOD_PREVIEW_PX)
        self._vod_count_label.setToolTip(
            "Match lines in this file — blank rows and '#' comments "
            "(the ABBREV header) are not counted")
        filter_row.addWidget(self._vod_count_label)
        filter_row.addSpacing(_VOD_PREVIEW_GAP)
        filter_row.addWidget(QtWidgets.QLabel("Filter:"))
        self._vod_filter = QtWidgets.QLineEdit()
        self._vod_filter.setPlaceholderText("Search match lines…")
        self._vod_filter.setClearButtonEnabled(True)
        filter_row.addWidget(self._vod_filter)

        # Full-size preview on the left with the toolbar rows stacked to its
        # right, the same arrangement the Player Database tab uses: an alt number
        # alone doesn't tell you what the render looks like, and at this size it
        # can share its height with both rows instead of stretching either one.
        picker_area = QtWidgets.QHBoxLayout()
        self._vod_preview_label = QtWidgets.QLabel()
        self._vod_preview_label.setFixedSize(_VOD_PREVIEW_PX, _VOD_PREVIEW_PX)
        self._vod_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vod_preview_label.setStyleSheet(
            f"background-color: {_BG3}; border-radius: 4px;")
        self._vod_preview_label.setToolTip(
            "Preview of the selected costume (alt 1 when none is picked)")
        picker_area.addWidget(self._vod_preview_label, 0, Qt.AlignmentFlag.AlignTop)
        picker_area.addSpacing(_VOD_PREVIEW_GAP)
        picker_rows = QtWidgets.QVBoxLayout()
        picker_rows.addLayout(row)
        # The stretch goes between the rows, not after them: the preview is
        # 200px tall whatever these rows do, so parking the pickers at the
        # bottom of that column puts them right above the filter bar -- the two
        # rows that act on the table sit together -- instead of leaving dead
        # space there.
        picker_rows.addStretch(1)
        picker_rows.addLayout(row2)
        picker_area.addLayout(picker_rows, 1)
        cbox.addLayout(picker_area)
        self._refresh_vod_preview()

        self._vod_model = VodModel()
        # Auto-save: every content change restarts a short debounce timer, so a
        # burst of typing results in a single write.
        self._vod_loaded_name = ""
        self._vod_suppress_autosave = False
        self._vod_save_timer = QtCore.QTimer(self)
        self._vod_save_timer.setSingleShot(True)
        self._vod_save_timer.setInterval(600)
        self._vod_save_timer.timeout.connect(self._auto_save_vod_file)
        self._vod_model.contentChanged.connect(self._sync_vod_abbrev_to_fetch)
        self._vod_model.contentChanged.connect(self._schedule_vod_autosave)
        # Len and the Copy button must never disagree about what a line becomes,
        # so both go through the same implementation.
        self._vod_model.copy_text_fn = self._vod_abbrev_line
        self._vod_proxy = QtCore.QSortFilterProxyModel()
        self._vod_proxy.setSourceModel(self._vod_model)
        self._vod_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._vod_proxy.setFilterKeyColumn(5)
        self._vod_filter.textChanged.connect(self._on_vod_filter_changed)

        self._vod_selected_source_row: int = -1

        self._vod_view = QtWidgets.QTableView()
        self._vod_view.setModel(self._vod_proxy)
        self._vod_view.setMinimumHeight(400)
        self._vod_view.verticalHeader().setVisible(False)
        self._vod_view.horizontalHeader().setSectionResizeMode(
            5, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._vod_view.setColumnWidth(0, 30)
        self._vod_view.setColumnWidth(1, 34)
        self._vod_view.setColumnWidth(2, 30)
        self._vod_view.setColumnWidth(3, 30)
        self._vod_view.setColumnWidth(4, 64)
        self._vod_view.setMouseTracking(True)  # enables per-cell hover state
        self._vod_copy_delegate = CopyButtonDelegate(self._vod_view)
        self._vod_copy_delegate.copyRequested.connect(self._vod_copy_row)
        self._vod_view.setItemDelegateForColumn(1, self._vod_copy_delegate)
        self._vod_up_delegate = MoveButtonDelegate(-1, self._vod_view)
        self._vod_up_delegate.moveRequested.connect(self._vod_move_row)
        self._vod_view.setItemDelegateForColumn(2, self._vod_up_delegate)
        self._vod_down_delegate = MoveButtonDelegate(1, self._vod_view)
        self._vod_down_delegate.moveRequested.connect(self._vod_move_row)
        self._vod_view.setItemDelegateForColumn(3, self._vod_down_delegate)
        self._vod_line_delegate = VodLineDelegate(self._vod_view)
        self._vod_view.setItemDelegateForColumn(5, self._vod_line_delegate)
        self._vod_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._vod_view.customContextMenuRequested.connect(self._vod_context_menu)
        self._vod_model.dataChanged.connect(lambda *_: self._vod_update_delete_btn())
        self._vod_model.dataChanged.connect(lambda *_: self._update_import_btn())
        self._vod_model.dataChanged.connect(self._on_vod_data_changed)
        self._vod_model.modelReset.connect(self._vod_update_delete_btn)
        self._vod_model.modelReset.connect(self._update_import_btn)
        self._vod_model.modelReset.connect(self._vod_rebuild_red_rows)
        self._vod_red_rows: set[int] = set()
        # Anything that can change what the table shows -- a new file, an edit
        # that comments a line out, a filter -- can change the count, and the
        # proxy is downstream of all of them.
        for _sig in (self._vod_proxy.modelReset, self._vod_proxy.layoutChanged,
                     self._vod_proxy.rowsInserted, self._vod_proxy.rowsRemoved,
                     self._vod_proxy.dataChanged):
            _sig.connect(lambda *_: self._refresh_vod_count())
        self._refresh_vod_count()
        cbox.addLayout(filter_row)
        cbox.addWidget(self._vod_view)
        self._vod_view.selectionModel().currentRowChanged.connect(self._on_vod_row_changed)

        rb2 = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save")
        save.clicked.connect(self._save_vod_file)
        rb2.addWidget(save)
        addr = QtWidgets.QPushButton("Add Row")
        addr.clicked.connect(self._vod_add_new_row)
        rb2.addWidget(addr)
        self._vod_delete_btn = QtWidgets.QPushButton("Delete Marked")
        self._vod_delete_btn.setEnabled(False)
        self._vod_delete_btn.clicked.connect(self._vod_delete_marked)
        rb2.addWidget(self._vod_delete_btn)
        self._vod_delete_unmarked_btn = QtWidgets.QPushButton("Delete Unmarked")
        self._vod_delete_unmarked_btn.setEnabled(False)
        self._vod_delete_unmarked_btn.clicked.connect(self._vod_delete_unmarked)
        rb2.addWidget(self._vod_delete_unmarked_btn)
        ca = QtWidgets.QPushButton("Check All")
        ca.clicked.connect(lambda: self._vod_model.set_all(True))
        rb2.addWidget(ca)
        ua = QtWidgets.QPushButton("Uncheck All")
        ua.clicked.connect(lambda: self._vod_model.set_all(False))
        rb2.addWidget(ua)
        rb2.addStretch(1)
        cbox.addLayout(rb2)

        self._vod_file.activated.connect(self._on_vod_file_pick)
        self._vod_file.currentTextChanged.connect(self._load_vod_file)

    def _refresh_vod_char_picker(self):
        cur = self._vod_char_picker.currentText()
        chars = sorted(get_characters_from_renders(), key=str.casefold)
        self._vod_char_picker.blockSignals(True)
        self._vod_char_picker.clear()
        self._vod_char_picker.addItems(chars)
        if cur in chars:
            self._vod_char_picker.setCurrentText(cur)
        self._vod_char_picker.blockSignals(False)
        self._refresh_vod_skin_picker()

    def _refresh_vod_skin_picker(self, *_args, keep: bool = True):
        """List the character's costumes; blank means "use the preferred one".

        ``keep`` re-selects the current alt after the rebuild, which is right
        when only the list was reloaded. Switching character passes False: the
        old alt numbered a different character's costume.
        """
        picker = getattr(self, "_vod_skin_picker", None)
        if picker is None:
            return
        char = self._vod_char_picker.currentText().strip()
        cur = picker.currentText()
        labels = [skin_label(st) for st in get_skins_for_char(char)] if char else []
        picker.blockSignals(True)
        picker.clear()
        picker.addItem("")          # no costume -> player's preferred
        picker.addItems(labels)
        if keep and cur in labels:
            picker.setCurrentText(cur)
        picker.blockSignals(False)
        self._refresh_vod_preview()

    def _refresh_vod_preview(self, *_args):
        """Show the picked costume, or alt 1 when none is picked."""
        label = getattr(self, "_vod_preview_label", None)
        if label is None:
            return
        char = self._vod_char_picker.currentText().strip()
        if not char:
            label.clear()
            return
        lbl = self._vod_skin_picker.currentText().strip()
        alt = stem_for_label(char, lbl) if lbl else neutral_skin_for(char)
        self._show_preview(render_stem(char, alt) if alt else "", label)

    def _copy_vod_char(self):
        name = self._vod_char_picker.currentText().strip()
        if not name:
            return
        skin = ""
        if getattr(self, "_vod_skin_picker", None) is not None:
            skin = self._vod_skin_picker.currentText().strip()
        text = f"{name}:{skin}" if skin else name
        QtWidgets.QApplication.clipboard().setText(text)
        self._log(f"[Copied character to clipboard: {text}]\n")

    def _refresh_top8_char_picker(self):
        if not hasattr(self, "_top8_char_picker"):
            return
        cur = self._top8_char_picker.currentText()
        chars = sorted(get_characters_from_renders(), key=str.casefold)
        self._top8_char_picker.blockSignals(True)
        self._top8_char_picker.clear()
        self._top8_char_picker.addItems(chars)
        if cur in chars:
            self._top8_char_picker.setCurrentText(cur)
        self._top8_char_picker.blockSignals(False)
        self._refresh_top8_skin_picker()

    def _refresh_top8_skin_picker(self, *_args, keep: bool = True):
        """List the character's costumes; blank means "use the preferred one"."""
        picker = getattr(self, "_top8_skin_picker", None)
        if picker is None:
            return
        char = self._top8_char_picker.currentText().strip()
        cur = picker.currentText()
        labels = [skin_label(st) for st in get_skins_for_char(char)] if char else []
        picker.blockSignals(True)
        picker.clear()
        picker.addItem("")          # no costume -> the player's preferred one
        picker.addItems(labels)
        if keep and cur in labels:
            picker.setCurrentText(cur)
        picker.blockSignals(False)
        self._refresh_top8_skin_preview()

    def _refresh_top8_skin_preview(self, *_args):
        """Show the picked costume, or alt 1 when none is picked."""
        label = getattr(self, "_top8_skin_preview_label", None)
        if label is None:
            return
        char = self._top8_char_picker.currentText().strip()
        if not char:
            label.clear()
            return
        lbl = self._top8_skin_picker.currentText().strip()
        alt = stem_for_label(char, lbl) if lbl else neutral_skin_for(char)
        self._show_preview(render_stem(char, alt) if alt else "", label)

    def _copy_top8_char(self):
        name = self._top8_char_picker.currentText().strip()
        if not name:
            return
        skin = ""
        if getattr(self, "_top8_skin_picker", None) is not None:
            skin = self._top8_skin_picker.currentText().strip()
        name = f"{name}:{skin}" if skin else name
        QtWidgets.QApplication.clipboard().setText(name)
        self._log(f"[Copied character to clipboard: {name}]\n")

    def _refresh_vod_len(self):
        """Len depends on the abbreviation, which lives outside the model."""
        if hasattr(self, "_vod_model"):
            self._vod_model.refresh_len_column()

    def _refresh_vod_count(self):
        """'41 sets', or '12 of 41 sets' while a filter is narrowing the view."""
        if not hasattr(self, "_vod_count_label"):
            return
        m = self._vod_model
        total = sum(1 for r in range(m.rowCount()) if _is_set_line(m.text_at(r)))
        word = "set" if total == 1 else "sets"
        if self._vod_filter.text().strip():
            shown = 0
            for r in range(self._vod_proxy.rowCount()):
                src = self._vod_proxy.mapToSource(self._vod_proxy.index(r, 0)).row()
                if _is_set_line(m.text_at(src)):
                    shown += 1
            self._vod_count_label.setText(f"{shown} of {total} {word}")
        else:
            self._vod_count_label.setText(f"{total} {word}")

    def _vod_header_abbrev(self) -> str:
        """The abbreviation the loaded rows currently spell, '' if they have none."""
        for r in range(self._vod_model.rowCount()):
            text = self._vod_model.text_at(r).strip()
            if _is_abbrev_line(text):
                return _abbrev_of_line(text)
        return ""

    def _abbrev_base(self, header: str, event_name: str) -> str:
        """'IFN 291' -> 'IFN': the header without this event's own label.

        The inverse of the join in :meth:`_abbrev_for_event`, since the Fetch
        tab's field holds the series part only.
        """
        label = self._label_for_event(event_name)
        if label and header.endswith(label) and header != label:
            return header[:-len(label)].strip()
        return re.sub(r"\s+\S*\d\S*$", "", header).strip() or header.strip()

    def _sync_vod_abbrev_to_fetch(self):
        """The other direction: an edited '# ABBREV:' row updates the Fetch tab.

        The header is an ordinary row, so it can be typed over (or deleted) in
        the VOD table -- and the field it came from has to follow, or the next
        edit of that field would quietly put the old value back.
        """
        if getattr(self, "_abbrev_syncing", False) or not hasattr(self, "_thumb_series"):
            return
        header = self._vod_header_abbrev()
        if header == getattr(self, "_vod_abbrev", ""):
            return
        self._vod_abbrev = header
        series = self._thumb_series.currentText()
        name = self._vod_loaded_name or self._vod_file.currentText()
        event_name = getattr(self, "_vod_event_name", "") or self._event_name_for_file(name)
        base = self._abbrev_base(header, event_name) if header else ""
        self._abbrev_syncing = True
        try:
            w = self._fetch_widgets.get(series, {})
            if "abbrev" in w:
                if w["abbrev"].text().strip() != base:
                    w["abbrev"].setText(base)   # -> _save_settings
            else:
                entry = next((e for e in self._custom_events
                              if e.get("label") == series), None)
                if entry is not None and str(entry.get("abbrev", "")).strip() != base:
                    entry["abbrev"] = base
                    self._save_custom_events()
                    self._build_saved_custom_rows()
        finally:
            self._abbrev_syncing = False
        self._refresh_vod_len()

    def _sync_abbrev_to_vod_file(self, series: str):
        """Push a Fetch-tab abbreviation edit into the loaded VOD file.

        The file carries its own '# ABBREV:' header, and that header is what the
        generator reads and what wins in :meth:`_abbrev_for_event` -- so without
        this, editing the field left the file (and every run from it) on the old
        abbreviation. Only the file loaded in Generate Thumbnails is rewritten:
        it is the one on screen, and a series can own hundreds of others.
        """
        if not hasattr(self, "_vod_model") or not hasattr(self, "_thumb_series"):
            return
        # Re-entrancy: the field may be being written *by* the reverse sync, and
        # rebuilding the header from it would overwrite a hand-typed one.
        if getattr(self, "_abbrev_syncing", False):
            return
        if series != self._thumb_series.currentText():
            return
        name = self._vod_loaded_name or self._vod_file.currentText()
        if not name:
            return
        event_name = getattr(self, "_vod_event_name", "") or self._event_name_for_file(name)
        if not event_name:
            return
        header = self._abbrev_for_event(event_name, use_header=False)
        self._vod_abbrev = header
        # Silent, like the VOD editor's own autosave -- this runs per keystroke,
        # and the Len column repainting is the visible feedback.
        self._vod_model.set_abbrev_header(header)
        self._refresh_vod_len()

    def _vod_abbrev_line(self, text: str) -> str:
        """Prepare a match line for the clipboard: the YouTube title for this set.

        Per-set costumes are a rendering detail, so they come off first -- both
        because they don't belong in the title and because the length limit is
        about the title, not about what we wrote to steer the generator.

        Then two strategies, in order, each applied only if the line is still
        over the limit: the series abbreviation in place of the event name, and
        after that the character lists. A line still too long once both have run
        is copied as it is and flagged yellow in the Len column -- what to give
        up next is the user's call.
        """
        if _is_abbrev_line(text):
            # The header exists to carry the abbreviation, so copying that row
            # is asking for the value, not for the bookkeeping around it.
            return _abbrev_of_line(text)
        text = strip_skins(text)
        if len(text) <= MAX_LINE_LEN:
            return text
        # First: the series abbreviation.
        event_name = getattr(self, "_vod_event_name", "")
        if not (event_name and text.startswith(event_name)):
            # Fall back to the line's own event name. The header only tells us
            # what the *first* line of the loaded file names; a renamed, merged
            # or hand-edited file -- or a stale load -- leaves lines whose event
            # it does not match, and those must still be abbreviated rather than
            # silently copied at full length.
            event_name = text.split(" - ")[0].strip() if " - " in text else ""
        if event_name and text.startswith(event_name):
            abbrev = self._abbrev_for_event(event_name)
            if abbrev:
                text = abbrev + text[len(event_name):]
                if len(text) <= MAX_LINE_LEN:
                    return text
        # Second: the character lists.
        return _strip_char_lists(text)

    def _abbrev_for_event(self, event_name: str, use_header: bool = True) -> str:
        """'Straight Into The Abyss 63' -> 'SITA 63'.

        The file's own '# ABBREV:' header wins, but only for the event that
        header belongs to. Otherwise the series abbreviation from the Fetch tab
        is joined to this event's own number -- on its own that field holds just
        'SITA', so using it raw dropped the number and produced 'SITA - ...'.

        ``use_header=False`` ignores the header, which is what an edit to the
        Fetch tab's field needs: it is rewriting that header, so reading it
        first would just hand back the value being replaced.
        """
        header = getattr(self, "_vod_abbrev", "")
        if use_header and header and getattr(self, "_vod_event_name", "") == event_name:
            return header
        series = self._thumb_series.currentText() if hasattr(self, "_thumb_series") else ""
        w = self._fetch_widgets.get(series, {}) if hasattr(self, "_fetch_widgets") else {}
        base = w["abbrev"].text().strip() if "abbrev" in w else ""
        if not base:
            # A saved custom event keeps its abbreviation in the JSON entry
            # rather than in a _fetch_widgets row.
            custom = next((e for e in getattr(self, "_custom_events", [])
                           if e.get("label") == series), None)
            if custom:
                base = str(custom.get("abbrev", "")).strip()
        if not base and use_header and header:
            base = re.sub(r"\s+\S*\d\S*$", "", header).strip()
        if not base:
            return ""
        suffix = ""
        if series and event_name.startswith(series):
            suffix = event_name[len(series):].strip()
        if not suffix:
            m = re.search(r"(\S*\d\S*)$", event_name)
            suffix = m.group(1) if m else ""
        return (base + " " + suffix).strip()

    def _vod_context_menu(self, pos):
        idx = self._vod_view.indexAt(pos)
        if not idx.isValid():
            return
        src_idx = self._vod_proxy.mapToSource(idx)
        menu = QtWidgets.QMenu(self)
        copy_act = menu.addAction("Copy line")
        skins_act = menu.addAction("Set costumes…")
        del_act = menu.addAction("Delete line")
        act = menu.exec(self._vod_view.viewport().mapToGlobal(pos))
        if act == copy_act:
            text = self._vod_model.text_at(src_idx.row())
            out = self._vod_abbrev_line(text)
            QtWidgets.QApplication.clipboard().setText(out)
            note = _vod_shorten_note(strip_skins(text), out)
            suffix = f" ({note})" if note else ""
            self._log(f"[Copied to clipboard{suffix}: {out}]\n")
        elif act == skins_act:
            self._vod_set_skins(src_idx.row())
        elif act == del_act:
            self._vod_model.delete_row(src_idx.row())
            self._vod_update_delete_btn()

    def _vod_set_skins(self, src_row: int):
        """Pick a per-set costume for each character in one match line.

        A row can hold up to four characters across two players, which is why
        this is a dialog rather than a column in the table. Leaving a costume on
        "(preferred)" writes no ``:Alt`` into the line, keeping it short.
        """
        line = self._vod_model.text_at(src_row)
        parsed = _parse_vod_player_skins(line)
        if not parsed:
            self._log("[Set costumes: could not parse that line]\n")
            return

        _, players = load_player_db()
        db = {name.lower(): entries for name, entries in players.items()}

        def preferred_label(player: str, char: str) -> str:
            """The costume this character renders as today, for the placeholder."""
            entries = db.get(player.lower().removesuffix(" [l]"), [])
            matches = [split_pref(sk) for c, sk in entries if c.upper() == char.upper()]
            if not matches:
                return ""
            alt = next((st for st, pref in matches if pref), matches[0][0])
            return alt or ""

        def owner_for(player: str, index: int, char: str) -> str:
            """Which member of a doubles team this character belongs to.

            Same rule the generator resolves renders by: character *i* is member
            *i*'s, unless that member has no row and another member's row has the
            character. A singles tag is returned unchanged.
            """
            base = player[:-4] if player[-4:] == " [L]" else player
            members = split_team(base)
            if len(members) < 2:
                return player
            if index < len(members) and members[index].lower() in db:
                return members[index]
            for a_member in members:
                if any(c.upper() == char.upper()
                       for c, _ in db.get(a_member.lower(), [])):
                    return a_member
            return member_for_index(base, index)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Set costumes for this set")
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(_muted("Leave a costume on \u201c(preferred)\u201d to use the "
                             "player's default from the player database."))
        form = QtWidgets.QFormLayout()
        combos = []          # (player_slot, char, combo)
        for slot, (name, chars) in enumerate(parsed):
            for idx, (char, skin) in enumerate(chars):
                combo = QtWidgets.QComboBox()
                combo.setMinimumWidth(160)
                owner = owner_for(name, idx, char)
                pref = preferred_label(owner, char)
                combo.addItem(f"(preferred{': ' + pref if pref else ''})", "")
                labels = [skin_label(st) for st in get_skins_for_char(char)]
                for lbl in labels:
                    combo.addItem(lbl, lbl)
                if skin:
                    # Accept whatever the line already says, even a stale alt
                    hit = stem_for_label(char, skin)
                    want = hit if hit else skin
                    if want not in labels:
                        combo.addItem(want, want)
                    combo.setCurrentText(want)
                form.addRow(f"{owner} \u2014 {char}", combo)
                combos.append((slot, char, combo))
        lay.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        per_player = [[] for _ in parsed]
        for slot, char, combo in combos:
            per_player[slot].append((char, combo.currentData() or None))
        new_line = _rewrite_vod_players(line, per_player)
        if new_line == line:
            return
        self._vod_model.setData(self._vod_model.index(src_row, 5), new_line,
                                Qt.ItemDataRole.EditRole)
        self._log(f"[Set costumes: {new_line}]\n")

    def _vod_files_for_series(self, series: str) -> list:
        """Names files belonging to a series, newest first."""
        vod_dir = ROOT / "Vod_Names"
        files = []
        if vod_dir.exists():
            for f in vod_dir.glob("*.txt"):
                if not series or f.name.startswith(series):
                    files.append(f)

        def _key(p):
            # Newest first. Every number in the name counts, so a split event
            # ("... 63-1") sorts beside its own event instead of dropping to the
            # bottom on its trailing part number.
            nums = re.findall(r"\d+", p.stem)
            return (tuple(-int(n) for n in nums) if nums else (0,), p.stem)

        files.sort(key=_key)
        return [f.name for f in files]

    def _refresh_vod_files(self):
        names = self._vod_files_for_series(self._thumb_series.currentText())
        cur = self._vod_file.currentText()
        self._vod_file.blockSignals(True)
        self._vod_file.clear()
        self._vod_file.addItems(names)
        if names:
            self._vod_file.setCurrentText(cur if cur in names else names[0])
        self._vod_file.blockSignals(False)
        self._refresh_thumb_event_names(names)
        if names:
            self._load_vod_file()
        else:
            self._flush_vod_autosave()
            self._vod_loaded_name = ""
            self._vod_model.load([])

    def _load_vod_file(self):
        # Commit pending edits to the file they belong to before switching
        self._flush_vod_autosave()
        name = self._vod_file.currentText()
        self._vod_loaded_name = name
        # A file-scoped thumbnail config belongs to this file, so the form has
        # to follow the selection rather than keep editing the old file.
        if self._cfg_scope_is_file():
            self._reload_config_form()
        if not name:
            self._vod_model.load([])
            return
        try:
            content = (ROOT / "Vod_Names" / name).read_text(encoding="utf-8")
        except Exception:
            content = ""
        self._vod_abbrev = ""
        self._vod_event_name = ""
        for raw in content.splitlines():
            stripped = raw.strip()
            if _is_abbrev_line(stripped):
                self._vod_abbrev = _abbrev_of_line(stripped)
            elif stripped and not stripped.startswith("#") and " - " in stripped:
                self._vod_event_name = self._derive_vod_event_name(stripped)
                break
        lines = [l for l in content.splitlines() if l.strip()]
        self._vod_suppress_autosave = True
        try:
            self._vod_model.load(lines)
        finally:
            self._vod_suppress_autosave = False
        self._vod_update_delete_btn()

    def _derive_vod_event_name(self, line: str) -> str:
        """The event-name prefix of a match line.

        The current format puts " - " between the event and the round, so the
        first segment is the event. Older files separate them with a space, and
        splitting those on " - " hands back "{event} {round}" -- which then gets
        abbreviated away with the event, or leaves the generator nothing to
        parse. The Thumbnails tab already knows the event name, so prefer that
        whenever the line actually starts with it.
        """
        configured = ""
        if hasattr(self, "_thumb_event_name"):
            configured = self._thumb_event_name.text().strip()
        if configured:
            if line.startswith(configured):
                return configured
            # Files often punctuate the number differently from the series
            # template ("CR Clash #77" in the file, "CR Clash 77" from the tab),
            # so fall back to comparing letters and digits only, and return the
            # slice of the line that consumed them -- the file's own spelling is
            # what the rest of the line is prefixed with.
            want = "".join(c for c in configured if c.isalnum()).lower()
            if want:
                seen = ""
                for i, ch in enumerate(line):
                    if ch.isalnum():
                        seen += ch.lower()
                        if not want.startswith(seen):
                            break
                        if seen == want:
                            return line[:i + 1]
        return line.split(" - ")[0].strip()

    def _vod_add_new_row(self):
        pos = self._vod_model.add_blank()
        src_idx = self._vod_model.index(pos, 5)
        proxy_idx = self._vod_proxy.mapFromSource(src_idx)
        self._vod_view.scrollTo(proxy_idx)
        self._vod_view.setCurrentIndex(proxy_idx)
        self._vod_view.edit(proxy_idx)

    def _vod_copy_row(self, r: int):
        src_row = self._vod_proxy.mapToSource(self._vod_proxy.index(r, 0)).row()
        text = self._vod_model.text_at(src_row)
        if text:
            out = self._vod_abbrev_line(text)
            QtWidgets.QApplication.clipboard().setText(out)
            note = _vod_shorten_note(strip_skins(text), out)
            suffix = f" ({note})" if note else ""
            self._log(f"[Copied to clipboard{suffix}: {out}]\n")

    def _vod_delete_marked(self):
        removed = self._vod_model.delete_marked()
        if removed:
            self._log(f"[Deleted {removed} marked row(s)]\n")
        else:
            self._log("[No rows marked to delete]\n")
        self._vod_update_delete_btn()

    def _vod_delete_unmarked(self):
        removed = self._vod_model.delete_unmarked()
        if removed:
            self._log(f"[Deleted {removed} unmarked row(s)]\n")
        else:
            self._log("[No unmarked rows to delete]\n")
        self._vod_update_delete_btn()

    def _vod_update_delete_btn(self):
        checked = self._vod_model.any_checked()
        if hasattr(self, "_vod_delete_btn"):
            self._vod_delete_btn.setEnabled(checked)
        if hasattr(self, "_vod_delete_unmarked_btn"):
            self._vod_delete_unmarked_btn.setEnabled(checked)

    def _schedule_vod_autosave(self):
        """Restart the debounce timer after a content change."""
        if self._vod_suppress_autosave:
            return
        if not (self._vod_loaded_name or self._vod_file.currentText()):
            return
        self._vod_save_timer.start()

    def _flush_vod_autosave(self):
        """Write immediately if a debounced save is still pending."""
        timer = getattr(self, "_vod_save_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self._auto_save_vod_file()

    def _auto_save_vod_file(self):
        # Write back to the file the rows were loaded from, not whatever the
        # combo happens to show now.
        name = self._vod_loaded_name or self._vod_file.currentText()
        if not name:
            return
        (ROOT / "Vod_Names" / name).write_text(self._vod_model.to_text(), encoding="utf-8")
        self._log(f"[Auto-saved: {name}]\n")

    def _save_vod_file(self):
        self._vod_save_timer.stop()
        name = self._vod_loaded_name or self._vod_file.currentText()
        if not name:
            self._log("[Error: no VOD names file selected]\n")
            return
        (ROOT / "Vod_Names" / name).write_text(self._vod_model.to_text(), encoding="utf-8")
        self._log(f"[Saved {name}]\n")

    # ================================================================== #
    #  Tab: Generate Top 8s                                             #
    # ================================================================== #
    def _build_top8_tab(self):
        lay = self._scroll_tab("Generate Top 8s")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._top8_series = QtWidgets.QComboBox()
        self._top8_series.setMinimumWidth(220)
        row1.addWidget(self._top8_series)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh series list")
        rb.clicked.connect(self._refresh_top8_series)
        row1.addWidget(rb)
        row1.addStretch(1)
        v.addLayout(row1)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        self._top8_event_name = _muted("")
        row2.addWidget(self._top8_event_name)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        self._top8_series.currentTextChanged.connect(self._on_top8_change)

        ctxt = CollapsibleBox("Top 8 Text Data", collapsed=False)
        lay.addWidget(ctxt)
        self._top8_text_path_label = _muted("")
        ctxt.addWidget(self._top8_text_path_label)

        t8_char_row = QtWidgets.QHBoxLayout()
        t8_char_row.addWidget(QtWidgets.QLabel("Character:"))
        self._top8_char_picker = QtWidgets.QComboBox()
        self._top8_char_picker.setMinimumWidth(160)
        self._top8_char_picker.setToolTip(
            "Pick a character, then Copy to paste the exact spelling into the Top 8 data")
        self._refresh_top8_char_picker()
        self._top8_char_picker.activated.connect(self._copy_top8_char)
        self._top8_char_picker.currentTextChanged.connect(
            lambda *_: self._refresh_top8_skin_picker(keep=False))
        t8_char_row.addWidget(self._top8_char_picker)
        t8_crb = QtWidgets.QPushButton("⟳")
        t8_crb.setObjectName("tool")
        t8_crb.setToolTip("Refresh character list")
        t8_crb.clicked.connect(self._refresh_top8_char_picker)
        t8_char_row.addWidget(t8_crb)
        t8_char_row.addWidget(QtWidgets.QLabel("Costume:"))
        self._top8_skin_picker = QtWidgets.QComboBox()
        self._top8_skin_picker.setMinimumWidth(90)
        self._top8_skin_picker.setToolTip(
            "Optional costume override — picking one copies Character:Alt to the clipboard.\n"
            "Leave blank to use the player's preferred costume.")
        self._refresh_top8_skin_picker()
        self._top8_skin_picker.activated.connect(self._copy_top8_char)
        self._top8_skin_picker.currentTextChanged.connect(self._refresh_top8_skin_preview)
        t8_char_row.addWidget(self._top8_skin_picker)
        t8_cc = QtWidgets.QPushButton("Copy")
        t8_cc.setToolTip("Copy the selected character (with costume, if chosen) to the clipboard")
        t8_cc.clicked.connect(self._copy_top8_char)
        t8_char_row.addWidget(t8_cc)
        t8_char_row.addStretch(1)

        # Preview to the left of the row, as on the Thumbnails and Player
        # Database tabs: an alt number alone does not tell you what the render
        # looks like.
        t8_picker_area = QtWidgets.QHBoxLayout()
        self._top8_skin_preview_label = QtWidgets.QLabel()
        self._top8_skin_preview_label.setFixedSize(200, 200)
        self._top8_skin_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._top8_skin_preview_label.setStyleSheet(
            f"background-color: {_BG3}; border-radius: 4px;")
        self._top8_skin_preview_label.setToolTip(
            "Preview of the selected costume (alt 1 when none is picked)")
        t8_picker_area.addWidget(self._top8_skin_preview_label, 0,
                                 Qt.AlignmentFlag.AlignTop)
        t8_picker_area.addSpacing(16)
        t8_rows = QtWidgets.QVBoxLayout()
        t8_rows.addLayout(t8_char_row)
        t8_rows.addStretch(1)
        t8_picker_area.addLayout(t8_rows, 1)
        ctxt.addLayout(t8_picker_area)
        ctxt.addWidget(_muted(
            "A character may carry a costume for this graphic after a colon "
            "(e.g. Mario:5); without one the player's preferred costume is used."))

        self._top8_text = QtWidgets.QPlainTextEdit()
        self._top8_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._top8_text.setMinimumHeight(320)
        Top8DataHighlighter(self._top8_text.document())
        ctxt.addWidget(self._top8_text)
        save_txt = QtWidgets.QPushButton("Save")
        save_txt.setToolTip("Write the data now (it also saves on its own as you type)")
        save_txt.clicked.connect(lambda: self._save_top8_text())
        ctxt.addWidget(save_txt)

        # One flag guards every programmatic write to the three editors below,
        # so loading a file or populating the config form never saves it back.
        self._top8_suppress_autosave = False
        self._top8_text_save_timer = QtCore.QTimer(self)
        self._top8_text_save_timer.setSingleShot(True)
        self._top8_text_save_timer.setInterval(800)
        self._top8_text_save_timer.timeout.connect(
            lambda: self._save_top8_text(auto=True))
        self._top8_text.textChanged.connect(self._on_top8_text_edit)

        self._build_top8_preview_section(lay)

        chtml = CollapsibleBox("Top 8 HTML Result", collapsed=False)
        lay.addWidget(chtml)
        rowh = QtWidgets.QHBoxLayout()
        rowh.addWidget(QtWidgets.QLabel("File:"))
        self._top8_html_file = QtWidgets.QComboBox()
        self._top8_html_file.setMinimumWidth(320)
        rowh.addWidget(self._top8_html_file)
        rbh = QtWidgets.QPushButton("⟳")
        rbh.setObjectName("tool")
        rbh.setToolTip("Refresh HTML file list")
        rbh.clicked.connect(self._refresh_top8_html_files)
        rowh.addWidget(rbh)
        openb = QtWidgets.QPushButton("Open in Browser")
        openb.clicked.connect(self._open_top8_html_in_browser)
        rowh.addWidget(openb)
        rowh.addStretch(1)
        chtml.addLayout(rowh)

        self._top8_html_warning = QtWidgets.QLabel("")
        self._top8_html_warning.setObjectName("warning")
        self._top8_html_warning.setWordWrap(True)
        chtml.addWidget(self._top8_html_warning)
        chtml.addWidget(_muted(
            "The HTML files are designed for OBS's fixed canvas, not for interactive browser viewing. "
            "The browser preview is for spot-checking data (names, placements), not pixel-perfect layout. "
            "Use Ctrl + + to zoom in, Ctrl+0 to reset."))

        self._build_default_top8_config(chtml)

        chtml_src = CollapsibleBox("HTML Source", collapsed=True)
        chtml.addWidget(chtml_src)
        self._top8_html_text = QtWidgets.QPlainTextEdit()
        self._top8_html_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._top8_html_text.setMinimumHeight(360)
        HtmlHighlighter(self._top8_html_text.document())
        chtml_src.addWidget(self._top8_html_text)
        save_html = QtWidgets.QPushButton("Save")
        save_html.setToolTip("Write the HTML now (it also saves on its own as you type)")
        save_html.clicked.connect(lambda: self._save_top8_html())
        chtml_src.addWidget(save_html)

        self._top8_html_save_timer = QtCore.QTimer(self)
        self._top8_html_save_timer.setSingleShot(True)
        self._top8_html_save_timer.setInterval(800)
        self._top8_html_save_timer.timeout.connect(
            lambda: self._save_top8_html(auto=True))
        self._top8_html_text.textChanged.connect(self._on_top8_html_edit)

        self._top8_html_file.currentTextChanged.connect(self._load_top8_html)
        self._top8_html_file.currentTextChanged.connect(
            lambda *_: self._refresh_top8_preview())
        self._d8_last_html_file = None
        lay.addStretch(1)

        self._refresh_top8_series()

    def _refresh_top8_series(self):
        names = list(getattr(self, "_thumb_event_map", {}).keys())
        cur = self._top8_series.currentText()
        self._top8_series.blockSignals(True)
        self._top8_series.clear()
        self._top8_series.addItems(names)
        if names:
            self._top8_series.setCurrentText(cur if cur in names else names[0])
        self._top8_series.blockSignals(False)
        self._on_top8_change()

    def _on_top8_change(self):
        self._refresh_top8_files()

    def _get_top8_text_path(self) -> Path:
        # The Default template is series-agnostic and reads its own sample data.
        if self._top8_html_file.currentText() == "Default Top 8.html":
            return ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt"
        series = self._top8_series.currentText()
        for cfg in FETCH_EVENTS:
            if cfg["label"] == series:
                return ROOT / "Top_8_Texts" / cfg["top8_file"]
        for entry in self._custom_events:
            if entry.get("label") == series:
                return ROOT / "Top_8_Texts" / entry.get("top8_file", f"{series} Top 8 HTML.txt")
        return ROOT / "Top_8_Texts" / f"{series} Top 8 HTML.txt"

    def _refresh_top8_files(self):
        self._load_top8_text()
        self._refresh_top8_html_files()

    def _load_top8_text(self):
        path = self._get_top8_text_path()
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        self._top8_text_path_label.setText(rel)
        if not path.exists():
            series = self._top8_series.currentText()
            template = self._thumb_event_map.get(series, series)
            event_name = template.format(n="").strip()
            content = (
                "# Top 8 Graphic\n# All information is tab deliminated\n\n"
                "#Graphic Information\n"
                f"Event name:\t{event_name}\n"
                "Event link:\t\nEvent entrants:\t Competitors\nEvent date:\t\n\n"
                "# Placements\n# place, name, sponsor, characters\n"
                "1,,,\n2,,,\n3,,,\n4,,,\n5,,,\n5,,,\n7,,,\n7,,,"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self._log(f"[Auto-created {path.name}]\n")
        content = path.read_text(encoding="utf-8")
        self._top8_last_chars = self._top8_char_signature(content)
        # Nesting-safe: _load_top8_text is called both on its own and from inside
        # _load_top8_html, which has already set the flag.
        prev = self._top8_suppress_autosave
        self._top8_suppress_autosave = True
        try:
            self._top8_text.setPlainText(content)
        finally:
            self._top8_suppress_autosave = prev
        m = re.search(r'(?m)^Event name:\t*(.*)$', content)
        self._top8_event_name.setText(
            m.group(1).strip() if m and m.group(1).strip()
            else self._top8_series.currentText())

    def _on_top8_text_edit(self):
        if self._top8_suppress_autosave:
            return
        self._top8_text_save_timer.start()

    def _on_top8_html_edit(self):
        if self._top8_suppress_autosave:
            return
        self._top8_html_save_timer.start()

    def _flush_top8_autosave(self):
        """Write immediately if any debounced Top 8 save is still pending."""
        for name in ("_top8_text_save_timer", "_top8_html_save_timer",
                     "_top8_config_save_timer"):
            timer = getattr(self, name, None)
            if timer is not None and timer.isActive():
                timer.stop()
                timer.timeout.emit()

    @staticmethod
    def _top8_char_signature(text: str) -> tuple:
        """The character/costume fields of every placement line, in order.

        A placement line is `place,name,sponsor,char[:alt][,char2...]`, so
        the fourth field onward is what decides which renders the page loads.
        """
        sig = []
        for line in text.splitlines():
            if not line[:1].isdigit():
                continue
            sig.append(tuple(f.strip() for f in line.split(",")[3:]))
        return tuple(sig)

    def _save_top8_text(self, auto: bool = False):
        path = self._get_top8_text_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        text = self._top8_text.toPlainText()
        path.write_text(text, encoding="utf-8")
        self._log(f"[{'Auto-saved' if auto else 'Saved'}: {path.name}]\n")
        # The preview reads this file, so it is stale until it reloads. A
        # changed character means different render URLs, and a reload in
        # place can still be answered from the image cache -- and the page's
        # own onerror fallback clears itself after one swap -- so that case
        # gets the same from-scratch load the Refresh button does.
        chars = self._top8_char_signature(text)
        if chars != getattr(self, "_top8_last_chars", None):
            self._top8_last_chars = chars
            self._force_refresh_top8_preview()
        else:
            self._refresh_top8_preview()

    def _series_abbrev(self, series: str) -> str:
        """The series' short name, as its Top 8 templates tend to be named.

        Built-in series carry it in FETCH_EVENTS and in the Fetch tab's own
        field; a saved event keeps it on its entry. The live field wins, so
        renaming an abbreviation there points the series at its template
        without a restart.
        """
        if not series:
            return ""
        w = getattr(self, "_fetch_widgets", {}).get(series, {})
        if "abbrev" in w:
            text = w["abbrev"].text().strip()
            if text:
                return text
        for entry in FETCH_EVENTS:
            if entry.get("label") == series and entry.get("default_abbrev"):
                return str(entry["default_abbrev"]).strip()
        for entry in getattr(self, "_custom_events", []):
            if entry.get("label") == series and entry.get("abbrev"):
                return str(entry["abbrev"]).strip()
        return ""

    def _refresh_top8_html_files(self):
        results_dir = ROOT / "Top_8_Results"
        series = self._top8_series.currentText()
        all_files = sorted(f.name for f in results_dir.glob("*.html")) if results_dir.exists() else []
        # List the event's own files first; keep the generic Default last.
        #
        # Unlike Rivals, this game's templates are named by abbreviation ("IFN
        # Top 8.HTML" for the "Immortal Fight Night" series), so matching the
        # series name alone finds nothing for most series -- the abbreviation is
        # tried as well. Every other template is still listed after those, so
        # nothing is hidden; what changed is which one gets *selected*.
        default = "Default Top 8.html"
        prefixes = [p.lower() for p in (series, self._series_abbrev(series)) if p]
        series_files = [f for f in all_files
                        if f != default
                        and any(f.lower().startswith(p) for p in prefixes)]
        others = [f for f in all_files if f != default and f not in series_files]
        listed = series_files + others
        files = listed + ([default] if default in all_files else [])
        cur = self._top8_html_file.currentText()
        self._top8_html_file.blockSignals(True)
        self._top8_html_file.clear()
        self._top8_html_file.addItems(files)
        self._top8_html_file.blockSignals(False)
        if files:
            self._top8_html_warning.setText("")
            # Prefer this series' own template, then the generic Default, and
            # only then another series' file. Selecting an arbitrary other-series
            # template left the preview showing a different event -- and, where
            # that template's art folder does not exist, showing nothing at all,
            # which reads as a preview that failed to load. Keep an explicit
            # choice the user already made, Default included.
            if cur in files:
                sel = cur
            elif series_files:
                top8 = [f for f in series_files if "Top 8" in f]
                sel = top8[-1] if top8 else series_files[-1]
            elif default in files:
                sel = default
            else:
                sel = files[0]
            self._top8_html_file.setCurrentText(sel)
            self._load_top8_html()
        else:
            self._top8_html_text.clear()
            self._top8_html_warning.setText(
                "⚠ No Top 8 HTML file found in Top_8_Results/. "
                "Create one by copying an existing template.")

    def _load_top8_html(self):
        name = self._top8_html_file.currentText()
        if not name:
            return
        path = ROOT / "Top_8_Results" / name
        if not path.exists():
            return
        raw = path.read_bytes()
        # Qt strips a leading BOM on setPlainText, so remember it here and write
        # it back in _save_top8_html -- otherwise every save silently drops it.
        self._top8_html_bom = raw.startswith(b"\xef\xbb\xbf")
        prev = self._top8_suppress_autosave
        self._top8_suppress_autosave = True
        try:
            self._top8_html_text.setPlainText(raw.decode("utf-8-sig"))
            if name != self._d8_last_html_file:
                self._d8_last_html_file = name
                self._load_default_top8_config()
                self._load_top8_text()
        finally:
            self._top8_suppress_autosave = prev

    def _save_top8_html(self, auto: bool = False):
        name = self._top8_html_file.currentText()
        if not name:
            if not auto:
                self._log("[Error: no HTML file selected]\n")
            return
        path = ROOT / "Top_8_Results" / name
        encoding = "utf-8-sig" if getattr(self, "_top8_html_bom", False) else "utf-8"
        path.write_text(self._top8_html_text.toPlainText(), encoding=encoding)
        self._log(f"[{'Auto-saved' if auto else 'Saved'}: {name}]\n")
        self._refresh_top8_preview()

    # --- Top 8 layout config (edits CSS in the selected HTML by element id) ---
    def _build_default_top8_config(self, parent_box):
        cbox = CollapsibleBox("Layout Config", collapsed=True)
        parent_box.addWidget(cbox)

        self._d8_label_color = ColorField("#ffffff")
        self._d8_sponsor_color = ColorField("#FFD700")
        self._d8_event = []
        for i in range(4):
            d = {"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)}
            if i == 0:
                d["color"] = ColorField("#ffffff")
            self._d8_event.append(d)
        self._d8_renders = [{"top": _hline("", 60), "left": _hline("", 60), "height": _hline("", 60)} for _ in range(8)]
        self._d8_nums = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)} for _ in range(8)]
        self._d8_names = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60),
                           "wrap": QtWidgets.QCheckBox()} for _ in range(8)]
        for f in self._d8_names:
            f["wrap"].setToolTip(
                "When on, this player's name wraps onto multiple lines at spaces "
                "instead of staying on a single line.")
        self._d8_sponsors = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)} for _ in range(8)]

        colbox = QtWidgets.QGroupBox("Colors")
        ch = QtWidgets.QHBoxLayout(colbox)
        ch.addWidget(QtWidgets.QLabel("Label:"))
        ch.addWidget(self._d8_label_color)
        ch.addSpacing(20)
        ch.addWidget(QtWidgets.QLabel("Sponsor:"))
        ch.addWidget(self._d8_sponsor_color)
        ch.addStretch(1)
        cbox.addWidget(colbox)

        evbox = QtWidgets.QGroupBox("Event Info")
        eg = QtWidgets.QGridLayout(evbox)
        for ci, txt in enumerate(["", "Top %", "Left %", "Size px", "Color"]):
            eg.addWidget(_muted(txt), 0, ci)
        for i, lbl in enumerate(["Name", "Link", "Entrants", "Date"]):
            f = self._d8_event[i]
            eg.addWidget(QtWidgets.QLabel(lbl + ":"), i + 1, 0)
            eg.addWidget(f["top"], i + 1, 1)
            eg.addWidget(f["left"], i + 1, 2)
            eg.addWidget(f["size"], i + 1, 3)
            if "color" in f:
                eg.addWidget(f["color"], i + 1, 4)
        eg.setColumnStretch(5, 1)
        cbox.addWidget(evbox)

        def slot_section(title, vars_list, col3_lbl):
            """Build one placement table. The caller places it; see the flow below."""
            has_wrap = any("wrap" in f for f in vars_list)
            gb = QtWidgets.QGroupBox(title)
            g = QtWidgets.QGridLayout(gb)
            headers = ["Place", "Top %", "Left %", col3_lbl] + (["Wrap"] if has_wrap else [])
            for ci, txt in enumerate(headers):
                g.addWidget(_muted(txt), 0, ci)
            for i, f in enumerate(vars_list):
                g.addWidget(QtWidgets.QLabel(str(i + 1)), i + 1, 0)
                g.addWidget(f["top"], i + 1, 1)
                g.addWidget(f["left"], i + 1, 2)
                third = "height" if "height" in f else "size"
                g.addWidget(f[third], i + 1, 3)
                if "wrap" in f:
                    g.addWidget(f["wrap"], i + 1, 4)
            # No stretch column here: in a flow layout the box is placed at its
            # size hint, so slack would only pad it and fit fewer per row.
            gb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                             QtWidgets.QSizePolicy.Policy.Fixed)
            return gb

        # The four placement tables are the same shape and eight rows tall each;
        # stacked they run off the screen, so they flow across the width instead
        # and rewrap as the window is resized.
        slots_host = QtWidgets.QWidget()
        slots_flow = FlowLayout(slots_host)
        for gb in (slot_section("Character Renders", self._d8_renders, "Height %"),
                   slot_section("Placement Numbers", self._d8_nums, "Size px"),
                   slot_section("Player Names", self._d8_names, "Size px"),
                   slot_section("Sponsors", self._d8_sponsors, "Size px")):
            slots_flow.addWidget(gb)
        cbox.addWidget(slots_host)

        apply_btn = QtWidgets.QPushButton("Apply Config && Save")
        apply_btn.setObjectName("accent")
        apply_btn.clicked.connect(lambda: self._apply_default_top8_config())
        cbox.addWidget(apply_btn)

        # Auto-save layout config: any field edit (debounced) re-applies to the
        # HTML and writes it. Programmatic loads are guarded by the suppress flag.
        self._top8_config_save_timer = QtCore.QTimer(self)
        self._top8_config_save_timer.setSingleShot(True)
        self._top8_config_save_timer.setInterval(700)
        self._top8_config_save_timer.timeout.connect(
            lambda: self._apply_default_top8_config(auto=True))
        color_fields = [self._d8_label_color, self._d8_sponsor_color]
        line_fields = []
        for f in self._d8_event:
            line_fields += [f["top"], f["left"], f["size"]]
            if "color" in f:
                color_fields.append(f["color"])
        for group in (self._d8_renders, self._d8_nums, self._d8_names, self._d8_sponsors):
            for f in group:
                line_fields += [f["top"], f["left"], f[next(
                    k for k in ("height", "size") if k in f)]]
        for e in line_fields:
            e.textChanged.connect(self._on_top8_config_edit)
        for cf in color_fields:
            cf.edit.textChanged.connect(self._on_top8_config_edit)
        for f in self._d8_names:
            f["wrap"].toggled.connect(self._on_top8_config_edit)

    def _on_top8_config_edit(self, *_):
        if self._top8_suppress_autosave:
            return
        self._top8_config_save_timer.start()

    def _load_default_top8_config(self):
        # Populating the form fires textChanged on every field, which would
        # schedule an auto-save of the very file being read. Its only caller,
        # _load_top8_html, already holds _top8_suppress_autosave for exactly
        # that reason -- so do not set the flag again here.
        html = self._top8_html_text.toPlainText()

        def get_style(elem_id):
            m = re.search(rf'id="{re.escape(elem_id)}"[^>]*?style="([^"]*)"', html)
            return m.group(1) if m else ""

        def wraps(style):
            # Per-element wrap = inline white-space:normal overriding the
            # .label rule's nowrap. No inline declaration -> inherits nowrap.
            m = re.search(r'white-space:\s*(nowrap|normal)', style)
            return bool(m) and m.group(1) == "normal"

        def num_prop(style, name):
            m = re.search(rf'{re.escape(name)}:\s*([\d.]+)', style)
            return m.group(1) if m else ""

        def color_prop(style):
            m = re.search(r'color:\s*(#[0-9a-fA-F]+)', style)
            return m.group(1) if m else ""

        m = re.search(r'#canvas \.label \{[^}]*color:\s*(#[0-9a-fA-F]+)', html, re.DOTALL)
        self._d8_label_color.setValue(m.group(1) if m else "#ffffff")
        m = re.search(r'#canvas \.sponsor \{[^}]*color:\s*(#[0-9a-fA-F]+)', html, re.DOTALL)
        self._d8_sponsor_color.setValue(m.group(1) if m else "#FFD700")

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            s = get_style(eid)
            f = self._d8_event[i]
            f["top"].setText(num_prop(s, "top"))
            f["left"].setText(num_prop(s, "left"))
            f["size"].setText(num_prop(s, "font-size"))
            if "color" in f:
                f["color"].setValue(color_prop(s) or "#ffffff")

        for i in range(8):
            n = i + 1
            s = get_style(f"place-{n}-render")
            self._d8_renders[i]["top"].setText(num_prop(s, "top"))
            self._d8_renders[i]["left"].setText(num_prop(s, "left"))
            self._d8_renders[i]["height"].setText(num_prop(s, "height"))
            s = get_style(f"place-{n}-num")
            self._d8_nums[i]["top"].setText(num_prop(s, "top"))
            self._d8_nums[i]["left"].setText(num_prop(s, "left"))
            self._d8_nums[i]["size"].setText(num_prop(s, "font-size"))
            s = get_style(f"place-{n}-name")
            self._d8_names[i]["top"].setText(num_prop(s, "top"))
            self._d8_names[i]["left"].setText(num_prop(s, "left"))
            self._d8_names[i]["size"].setText(num_prop(s, "font-size"))
            self._d8_names[i]["wrap"].setChecked(wraps(s))
            s = get_style(f"place-{n}-sponsor")
            self._d8_sponsors[i]["top"].setText(num_prop(s, "top"))
            self._d8_sponsors[i]["left"].setText(num_prop(s, "left"))
            self._d8_sponsors[i]["size"].setText(num_prop(s, "font-size"))

    def _apply_default_top8_config(self, auto: bool = False):
        html = self._top8_html_text.toPlainText()

        def patch_style(h, elem_id, props):
            def repl(m):
                style = m.group(2)
                for prop, val, unit in props:
                    if unit == "color":
                        style = re.sub(r'(color:\s*)#[0-9a-fA-F]+', rf'\g<1>{val}', style)
                    elif unit in ("%", "px"):
                        if not val.strip():
                            # An empty box must leave the declaration alone. Writing
                            # "top: %" would break the number regex below, so the next
                            # value typed could never be applied and the field stayed
                            # stuck empty.
                            continue
                        # The number is matched with * rather than + so a file already
                        # left in that broken state is repaired by the next edit.
                        style = re.sub(rf'({re.escape(prop)}:\s*)[\d.]*({re.escape(unit)})', rf'\g<1>{val}\2', style)
                    elif unit == "keyword":
                        # Drop any existing declaration, then re-add unless val is
                        # None (None = inherit the class default, e.g. nowrap).
                        style = re.sub(rf'\s*{re.escape(prop)}:\s*[^;]*;?', '', style)
                        if val is not None:
                            style = style.rstrip()
                            if style and not style.endswith(';'):
                                style += ';'
                            style = (style + f' {prop}: {val};').strip()
                return m.group(1) + style + '"'
            return re.sub(rf'(id="{re.escape(elem_id)}"[^>]*?style=")([^"]*)"', repl, h)

        label_color = self._d8_label_color.value()
        sponsor_color = self._d8_sponsor_color.value()
        html = re.sub(r'(#canvas \.label \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{label_color}', html, flags=re.DOTALL)
        html = re.sub(r'(#canvas \.sponsor \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{sponsor_color}', html, flags=re.DOTALL)

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            f = self._d8_event[i]
            props = [("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                     ("font-size", f["size"].text(), "px")]
            if "color" in f:
                props.append(("color", f["color"].value(), "color"))
            html = patch_style(html, eid, props)

        for i in range(8):
            n = i + 1
            f = self._d8_renders[i]
            html = patch_style(html, f"place-{n}-render", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("height", f["height"].text(), "%")])
            f = self._d8_nums[i]
            html = patch_style(html, f"place-{n}-num", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px")])
            f = self._d8_names[i]
            html = patch_style(html, f"place-{n}-name", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px"),
                ("white-space", "normal" if f["wrap"].isChecked() else None, "keyword")])
            f = self._d8_sponsors[i]
            html = patch_style(html, f"place-{n}-sponsor", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px")])

        prev = self._top8_suppress_autosave
        self._top8_suppress_autosave = True
        try:
            self._top8_html_text.setPlainText(html)
        finally:
            self._top8_suppress_autosave = prev
        self._save_top8_html(auto=auto)

    def _ensure_http_server(self) -> int:
        """Start the local preview server if needed; return its port.

        The page fetches its data file and the player CSV, which fetch() refuses
        to do over file://, so both the browser button and the embedded preview
        go through here.
        """
        if not self._http_server:
            handler = functools.partial(_PreviewHTTPRequestHandler,
                                        directory=str(ROOT))
            # Threaded, and loopback-only. This used to be a single-threaded
            # TCPServer, which a browser reliably wedged: it opens several
            # sockets at once (parallel asset fetches, keep-alive, and
            # speculative preconnects that send no request at all). One idle
            # socket blocked the only handler thread, the 5-deep listen backlog
            # filled, and Windows then refused every further connection -- the
            # page just never loaded. Binding 127.0.0.1 instead of "" also stops
            # the whole generator folder being served to the local network; the
            # URL is localhost either way.
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            server.daemon_threads = True
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True,
                             name="top8-http-server").start()
            self._http_server = server
            self._http_server_port = port
            self._log(f"[Local server started on port {port}]\n")
        return self._http_server_port

    def _top8_preview_url(self, name: str) -> str:
        """Server URL for one Top 8 HTML file.

        Event names carry spaces, and can carry "#" or "&" -- all of which change
        what the browser asks for unless the path is encoded here.
        """
        port = self._ensure_http_server()
        return f"http://localhost:{port}/Top_8_Results/{urllib.parse.quote(name)}"

    def _open_top8_html_in_browser(self):
        name = self._top8_html_file.currentText()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return
        url = self._top8_preview_url(name)
        webbrowser.open(url)
        self._log(f"[Opened {url}]\n")

    # ================================================================== #
    #  Tab: Generate Posts                                              #
    # ================================================================== #
    def _build_posts_tab(self):
        lay = self._scroll_tab("Generate Posts")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._posts_series = QtWidgets.QComboBox()
        self._posts_series.setMinimumWidth(220)
        row1.addWidget(self._posts_series)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh event list")
        rb.clicked.connect(self._refresh_posts_events)
        row1.addWidget(rb)
        row1.addSpacing(12)
        posts_num_lbl = QtWidgets.QLabel("# / Label:")
        posts_num_lbl.setToolTip("What replaces {n} in the series name -- an "
                                 "event number, or a word such as Doubles.")
        row1.addWidget(posts_num_lbl)
        self._posts_num = _hline("", 160)
        row1.addWidget(self._posts_num)
        row1.addStretch(1)
        v.addLayout(row1)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        self._posts_event_name = QtWidgets.QLineEdit()
        self._posts_event_name.setReadOnly(True)
        self._posts_event_name.setMinimumWidth(320)
        row2.addWidget(self._posts_event_name)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        cfgbox = QtWidgets.QGroupBox("Post Settings")
        cv = QtWidgets.QVBoxLayout(cfgbox)
        rn = QtWidgets.QHBoxLayout()
        self._posts_has_next = QtWidgets.QCheckBox("Next Event")
        self._posts_has_next.setChecked(True)
        self._posts_has_next.toggled.connect(self._update_posts_next_state)
        rn.addWidget(self._posts_has_next)
        rn.addSpacing(8)
        rn.addWidget(QtWidgets.QLabel("Date:"))
        self._posts_date = QtWidgets.QDateEdit()
        self._posts_date.setCalendarPopup(True)
        self._posts_date.setDisplayFormat("yyyy-MM-dd")
        self._posts_date.setDate(QtCore.QDate.currentDate())
        rn.addWidget(self._posts_date)
        rn.addSpacing(16)
        rn.addWidget(QtWidgets.QLabel("Link:"))
        self._posts_next_link = QtWidgets.QLineEdit()
        self._posts_next_link.setMinimumWidth(260)
        rn.addWidget(self._posts_next_link)
        rn.addStretch(1)
        cv.addLayout(rn)

        rv = QtWidgets.QHBoxLayout()
        rv.addWidget(QtWidgets.QLabel("Vods link:"))
        self._posts_vods = QtWidgets.QLineEdit()
        self._posts_vods.setMinimumWidth(420)
        rv.addWidget(self._posts_vods)
        rv.addStretch(1)
        cv.addLayout(rv)

        rb2 = QtWidgets.QHBoxLayout()
        # Which fetch buttons exist depends on the provider, so they live in
        # their own container that _rebuild_posts_buttons() repopulates.
        self._posts_btns = QtWidgets.QWidget()
        self._posts_btns_lay = QtWidgets.QHBoxLayout(self._posts_btns)
        self._posts_btns_lay.setContentsMargins(0, 0, 0, 0)
        rb2.addWidget(self._posts_btns)
        rb2.addSpacing(16)
        sv = QtWidgets.QPushButton("Save")
        sv.clicked.connect(self._save_post_file)
        rb2.addWidget(sv)
        cp = QtWidgets.QPushButton("Copy")
        cp.clicked.connect(self._copy_post_text)
        rb2.addWidget(cp)
        rb2.addStretch(1)
        cv.addLayout(rb2)
        self._posts_provider_note = _muted("")
        self._posts_provider_note.setVisible(False)
        cv.addWidget(self._posts_provider_note)
        lay.addWidget(cfgbox)

        ctext = CollapsibleBox("Post Text", collapsed=False)
        lay.addWidget(ctext)
        self._posts_text = QtWidgets.QPlainTextEdit()
        self._posts_text.setMinimumHeight(300)
        ctext.addWidget(self._posts_text)

        self._build_notes_section(lay)
        lay.addStretch(1)

        self._posts_active_file = None
        self._posts_event_map = {}
        self._posts_series.currentTextChanged.connect(self._on_posts_series_change)
        self._posts_num.textChanged.connect(self._update_posts_name)
        self._posts_next_link.textChanged.connect(self._save_settings)
        self._posts_vods.textChanged.connect(self._save_settings)
        self._posts_has_next.toggled.connect(self._save_settings)
        self._refresh_posts_events()

    def _build_notes_section(self, parent_layout):
        """A free-form scratchpad kept per series, beside that series' post text.

        Deliberately unstructured -- it exists for whatever doesn't fit the
        generated post (running order, a recurring caster note, a reminder for
        next week). Keyed to the series, not the event number, so it carries over
        from one week's event to the next instead of starting empty every time.
        It saves to Results_Posts/{Series} Notes.txt, next to the post files.
        """
        box = CollapsibleBox("Notes", collapsed=False)
        parent_layout.addWidget(box)

        self._notes_path_label = _muted("")
        box.addWidget(self._notes_path_label)

        self._notes_text = QtWidgets.QPlainTextEdit()
        self._notes_text.setMinimumHeight(500)
        self._notes_text.setPlaceholderText(
            "Notes for this series — saved automatically, one file per series, "
            "kept across event numbers.")
        box.addWidget(self._notes_text)

        row = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save")
        save.setToolTip("Write the notes now (they also save on their own as you type)")
        save.clicked.connect(lambda: self._save_notes())
        row.addWidget(save)
        row.addStretch(1)
        box.addLayout(row)

        # The path the buffer was loaded from. Every write goes here rather than
        # to whatever series the form currently shows, so a debounced save that
        # lands after the user switches series cannot write one series' notes
        # into another's file.
        self._notes_path = None
        self._notes_suppress_autosave = False
        self._notes_save_timer = QtCore.QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(800)
        self._notes_save_timer.timeout.connect(lambda: self._save_notes(auto=True))
        self._notes_text.textChanged.connect(self._on_notes_edit)

    def _notes_path_for(self, series: str):
        return ROOT / "Results_Posts" / f"{series} Notes.txt"

    def _on_notes_edit(self):
        if self._notes_suppress_autosave or self._notes_path is None:
            return
        self._notes_save_timer.start()

    def _flush_notes_autosave(self):
        """Write immediately if a debounced save is still pending."""
        timer = getattr(self, "_notes_save_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self._save_notes(auto=True)

    def _save_notes(self, auto: bool = False):
        path = self._notes_path
        if path is None:
            if not auto:
                self._log("[Error: no event selected]\n")
            return
        text = self._notes_text.toPlainText()
        # An emptied note should remove the file rather than leave a blank one
        # lying next to the post files.
        if not text.strip():
            if path.exists():
                path.unlink()
                self._log(f"[Removed empty {path.name}]\n")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        self._log(f"[{'Auto-saved' if auto else 'Saved'}: {path.name}]\n")

    def _load_notes(self):
        """Point the scratchpad at the selected series' notes file.

        Called from _update_posts_name, which also runs on every keystroke in the
        event-number box -- but the notes belong to the series, so re-reading then
        would throw away what is being typed and move the cursor. Reloading only
        when the path actually changes keeps the buffer alone, and is also where
        the outgoing series' pending save gets committed.
        """
        if not hasattr(self, "_notes_text"):
            return
        series = self._posts_series.currentText().strip()
        path = self._notes_path_for(series) if series else None
        if path == self._notes_path:
            return
        self._flush_notes_autosave()
        self._notes_suppress_autosave = True
        try:
            self._notes_path = path
            if path is None:
                self._notes_text.clear()
                self._notes_path_label.setText("Select a series to keep notes for it.")
                return
            self._notes_text.setPlainText(
                path.read_text(encoding="utf-8").rstrip() if path.exists() else "")
            self._notes_path_label.setText(f"Results_Posts/{path.name}")
        finally:
            self._notes_suppress_autosave = False

    def _update_posts_next_state(self):
        en = self._posts_has_next.isChecked()
        self._posts_date.setEnabled(en)
        self._posts_next_link.setEnabled(en)

    def _posts_entry(self):
        """``(entry, provider)`` for the selected posts series.

        The Posts tab lists every saved event whatever fetched it, so the
        provider has to be read off the entry rather than from the Fetch
        tab's dropdown. A built-in row is always start.gg.
        """
        series = self._posts_series.currentText()
        entry = next((c for c in FETCH_EVENTS if c["label"] == series), None)
        if entry is None:
            entry = next((e for e in self._custom_events
                          if e.get("label") == series), None)
        return entry, provider_of(entry or {})

    def _rebuild_posts_buttons(self):
        """Fit the fetch buttons to what the selected series' site can do."""
        cfg = self._provider_cfg(self._posts_entry()[1])
        while self._posts_btns_lay.count():
            w = self._posts_btns_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for platform, label in cfg["posts_platforms"]:
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(
                lambda _=False, pf=platform: self._run_fetch_post(pf))
            self._posts_btns_lay.addWidget(b)
        note = cfg.get("posts_note", "")
        self._posts_provider_note.setText(note)
        self._posts_provider_note.setVisible(bool(note))

    def _refresh_posts_events(self):
        events = load_thumbnail_events()
        self._posts_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        for entry in self._custom_events:
            label = entry.get("label", "")
            name_tmpl = entry.get("name_template", "")
            if label and name_tmpl and label not in self._posts_event_map:
                self._posts_event_map[label] = name_tmpl
                names.append(label)
        cur = self._posts_series.currentText()
        self._posts_series.blockSignals(True)
        self._posts_series.clear()
        self._posts_series.addItems(names)
        if names:
            last = self._settings.get("last_posts_series")
            if last in names:
                self._posts_series.setCurrentText(last)
            elif cur in names:
                self._posts_series.setCurrentText(cur)
            else:
                self._posts_series.setCurrentIndex(0)
        self._posts_series.blockSignals(False)
        self._on_posts_series_change()

    def _on_posts_series_change(self):
        self._loading = True
        series = self._posts_series.currentText()
        widgets = self._fetch_widgets.get(series)
        if widgets:
            self._posts_num.setText(widgets["num"].text())
        else:
            custom = next((e for e in self._custom_events if e.get("label") == series), None)
            if custom:
                self._posts_num.setText(custom.get("current_num", ""))
            else:
                saved = self._settings.get("last_event_nums", {}).get(series)
                if saved:
                    self._posts_num.setText(saved)
        saved_cfg = self._settings.get("posts_cfg", {}).get(series, {})
        saved_date = saved_cfg.get("next_date", "")
        if saved_date:
            qd = QtCore.QDate.fromString(saved_date, "yyyy-MM-dd")
            if qd.isValid():
                self._posts_date.setDate(qd)
        default_link = next((c.get("tweet_link", "") for c in FETCH_EVENTS if c["label"] == series), "")
        self._posts_next_link.setText(saved_cfg.get("next_link", default_link))
        self._posts_vods.setText(saved_cfg.get("vods", ""))
        self._posts_has_next.setChecked(saved_cfg.get("has_next", True))
        self._update_posts_next_state()
        self._loading = False
        self._rebuild_posts_buttons()
        self._update_posts_name()
        self._save_settings()

    def _update_posts_name(self):
        template = self._posts_event_map.get(self._posts_series.currentText(), "{n}")
        num = self._posts_num.text().strip()
        name = template.format(n=num)
        if not num:  # see _update_thumb_name
            name = re.sub(r"\s{2,}", " ", name).strip()
        self._posts_event_name.setText(name)
        self._posts_load_file()
        self._load_notes()

    def _posts_load_file(self):
        event_name = self._posts_event_name.text().strip()
        if not event_name:
            return
        folder = ROOT / "Results_Posts"
        # "" is the generic (no-socials) post, whose file carries no
        # platform in its name -- a Challonge series only ever writes that one.
        for platform in ("twitter", "discord", ""):
            stem = (event_name + " " + platform.capitalize()).strip()
            path = folder / (stem + " Post.txt")
            if path.exists():
                self._posts_active_file = path
                self._posts_text.setPlainText(path.read_text(encoding="utf-8").rstrip())
                return
        self._posts_active_file = None
        self._posts_text.clear()

    def _run_fetch_post(self, platform: str):
        n = self._posts_num.text().strip()
        event_name = self._posts_event_name.text().strip()
        if not event_name:
            self._log("[Error: no event selected]" + chr(10))
            return
        entry, provider = self._posts_entry()
        if not entry:
            self._log("[Error: no slug found for this event series]" + chr(10))
            return
        if entry in FETCH_EVENTS:
            slug = entry["slug_template"].format(n=n)
        else:
            slug = entry["slug_template"].replace("{n}", n)
        pcfg = self._provider_cfg(provider)
        # "generic" is the no-socials post: one button, no --platform flag,
        # and a filename without a platform in it.
        suffix = "Post" if platform == "generic" else (
            platform.capitalize() + " Post")
        out_path = ROOT / "Results_Posts" / (event_name + " " + suffix + ".txt")
        self._posts_active_file = out_path
        cmd = [PYTHON,
               str(ROOT / "Python_Scripts" / pcfg["posts_script"]),
               slug, "--name", event_name, "--out", str(out_path)]
        if platform != "generic":
            cmd += ["--platform", platform]
        if pcfg["needs_event_index"]:
            cmd += ["--event", str(entry.get("event", "0")).strip() or "0"]
        if self._posts_has_next.isChecked():
            next_link = self._posts_next_link.text().strip()
            if next_link:
                cmd += ["--link", next_link]
            next_date = _ordinal_date(self._posts_date.date().toPython())
            if next_date:
                cmd += ["--next", next_date]
        vods = self._posts_vods.text().strip()
        if vods:
            cmd += ["--vods", vods]

        def _done():
            if out_path.exists():
                self._posts_text.setPlainText(
                    out_path.read_text(encoding="utf-8").rstrip())
        self._run(cmd, on_done=_done)

    def _save_post_file(self):
        if not self._posts_active_file:
            event_name = self._posts_event_name.text().strip()
            if not event_name:
                self._log("[Error: no event selected]\n")
                return
            self._posts_active_file = ROOT / "Results_Posts" / f"{event_name} Post.txt"
        self._posts_active_file.parent.mkdir(parents=True, exist_ok=True)
        self._posts_active_file.write_text(self._posts_text.toPlainText() + "\n", encoding="utf-8")
        self._log(f"[Saved {self._posts_active_file.name}]\n")

    def _copy_post_text(self):
        content = self._posts_text.toPlainText()
        if content.strip():
            QtWidgets.QApplication.clipboard().setText(content)
            self._log("[Copied post to clipboard]\n")
        else:
            self._log("[Nothing to copy — fetch a post first]\n")

    # ================================================================== #
    #  Tab: Character Renders                                           #
    # ================================================================== #
    def _build_renders_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        box = QtWidgets.QGroupBox("Character Renders")
        v = QtWidgets.QVBoxLayout(box)
        v.addWidget(_muted("Open the full character render folder in File Explorer."))
        open_full = QtWidgets.QPushButton("Open Full Renders")
        open_full.setMaximumWidth(220)
        open_full.clicked.connect(
            lambda: self._open_dir(FULL_RENDERS_DIR, "Full Renders"))
        v.addWidget(open_full)
        outer.addWidget(box)
        outer.addStretch(1)
        self.tabs.addTab(tab, "Character Renders")

    def _open_dir(self, folder, label: str):
        if not folder.is_dir():
            self._log(f"[Error: {label} folder not found: {folder}]\n")
            return
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"[Error opening folder: {exc}]\n")

    # ================================================================== #
    #  Tab: Player Database                                             #
    # ================================================================== #
    def _build_player_db_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        self._db_header: list[str] = []
        self._db_players: dict[str, list[tuple[str, str]]] = {}
        self._db_selected_player: str | None = None
        self._db_selected_char_idx: int | None = None
        self._char_suggestions = get_characters_from_renders()

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        hl = QtWidgets.QLabel("Players")
        hl.setObjectName("heading")
        lv.addWidget(hl)
        self._player_search = QtWidgets.QLineEdit()
        self._player_search.setPlaceholderText("Search players...")
        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._refresh_player_list)
        self._player_search.textChanged.connect(lambda: self._search_timer.start())
        lv.addWidget(self._player_search)
        self._player_list = QtWidgets.QListWidget()
        self._player_list.currentItemChanged.connect(self._on_player_select)
        lv.addWidget(self._player_list)
        np_row = QtWidgets.QHBoxLayout()
        np_row.addWidget(QtWidgets.QLabel("Name:"))
        self._new_player = QtWidgets.QLineEdit()
        self._new_player.setPlaceholderText("Player name...")
        self._new_player.returnPressed.connect(self._confirm_add_player)
        np_row.addWidget(self._new_player)
        lv.addLayout(np_row)
        pb_row = QtWidgets.QHBoxLayout()
        addb = QtWidgets.QPushButton("+ Add")
        addb.clicked.connect(self._confirm_add_player)
        pb_row.addWidget(addb)
        remb = QtWidgets.QPushButton("- Remove")
        remb.clicked.connect(self._remove_player)
        pb_row.addWidget(remb)
        lv.addLayout(pb_row)
        splitter.addWidget(left)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self._editing_label = QtWidgets.QLabel("Select a player")
        self._editing_label.setObjectName("heading")
        rv.addWidget(self._editing_label)

        self._char_tree = QtWidgets.QTreeWidget()
        self._char_tree.setColumnCount(3)
        self._char_tree.setHeaderLabels(["Character", "Alt #", "Preferred"])
        self._char_tree.setColumnWidth(0, 180)
        self._char_tree.setColumnWidth(1, 120)
        self._char_tree.setColumnWidth(2, 80)
        self._char_tree.setRootIsDecorated(False)
        # Guards the itemChanged handler while we rebuild rows ourselves.
        self._char_tree_updating = False
        self._char_tree.currentItemChanged.connect(self._on_char_tree_select)
        self._char_tree.itemChanged.connect(self._on_char_tree_check)
        rv.addWidget(self._char_tree)

        tb = QtWidgets.QHBoxLayout()
        eb = QtWidgets.QPushButton("Edit Selected")
        eb.clicked.connect(self._edit_char_entry)
        tb.addWidget(eb)
        rmb = QtWidgets.QPushButton("Remove Selected")
        rmb.clicked.connect(self._remove_char_entry)
        tb.addWidget(rmb)
        prefb = QtWidgets.QPushButton("Set Preferred")
        prefb.setToolTip("Use this costume whenever a VOD line doesn't name one for "
                         "this character (same as ticking its Preferred box)")
        prefb.clicked.connect(self._set_preferred_entry)
        tb.addWidget(prefb)
        tb.addStretch(1)
        up = QtWidgets.QPushButton("Move Up")
        up.clicked.connect(lambda: self._move_char_entry(-1))
        tb.addWidget(up)
        dn = QtWidgets.QPushButton("Move Down")
        dn.clicked.connect(lambda: self._move_char_entry(1))
        tb.addWidget(dn)
        rv.addLayout(tb)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BG3};")
        rv.addWidget(sep)

        ael = QtWidgets.QLabel("Add / Edit Entry")
        ael.setStyleSheet("font-weight: 600;")
        rv.addWidget(ael)

        form_section = QtWidgets.QHBoxLayout()
        form_left = QtWidgets.QVBoxLayout()
        form_row = QtWidgets.QHBoxLayout()
        form_row.addWidget(QtWidgets.QLabel("Character:"))
        self._form_char = QtWidgets.QComboBox()
        self._form_char.setEditable(True)
        self._form_char.setMinimumWidth(200)
        self._form_char.addItems([""] + self._char_suggestions)
        self._form_char.currentTextChanged.connect(self._on_form_char_change)
        form_row.addWidget(self._form_char)
        form_row.addSpacing(12)
        form_row.addWidget(QtWidgets.QLabel("Alt #:"))
        self._form_alt = QtWidgets.QComboBox()
        self._form_alt.setMinimumWidth(70)
        self._form_alt.currentTextChanged.connect(self._on_form_alt_change)
        form_row.addWidget(self._form_alt)
        form_left.addLayout(form_row)
        fb = QtWidgets.QHBoxLayout()
        self._form_add_btn = QtWidgets.QPushButton("Add Entry")
        self._form_add_btn.clicked.connect(self._add_char_entry)
        fb.addWidget(self._form_add_btn)
        self._form_edit_btn = QtWidgets.QPushButton("Update Entry")
        self._form_edit_btn.setEnabled(False)
        self._form_edit_btn.clicked.connect(self._update_char_entry)
        fb.addWidget(self._form_edit_btn)
        clf = QtWidgets.QPushButton("Clear Form")
        clf.clicked.connect(self._clear_form)
        fb.addWidget(clf)
        fb.addStretch(1)
        form_left.addLayout(fb)
        form_left.addStretch(1)

        self._preview_label = QtWidgets.QLabel()
        self._preview_label.setFixedSize(220, 220)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(f"background-color: {_BG3}; border-radius: 4px;")
        form_section.addWidget(self._preview_label, 0, Qt.AlignmentFlag.AlignTop)
        form_section.addSpacing(16)
        form_section.addLayout(form_left, 0)
        form_section.addStretch(1)
        rv.addLayout(form_section)

        save_row = QtWidgets.QHBoxLayout()
        sb = QtWidgets.QPushButton("Save Player Database")
        sb.setObjectName("accent")
        sb.clicked.connect(self._save_player_db)
        save_row.addWidget(sb)
        rl = QtWidgets.QPushButton("Reload from File")
        rl.clicked.connect(self._reload_player_db)
        save_row.addWidget(rl)
        save_row.addStretch(1)
        rv.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([220, 760])
        self.tabs.addTab(tab, "Player Database")
        self._reload_player_db()

    def _reload_player_db(self):
        self._db_header, self._db_players = load_player_db()
        self._refresh_player_list()
        self._char_tree.clear()
        self._editing_label.setText("Select a player")
        self._db_selected_player = None
        # Which players exist gates Add Missing Costumes on the other tab.
        self._update_import_btn()

    def _refresh_player_list(self):
        query = self._player_search.text().lower()
        self._player_list.blockSignals(True)
        self._player_list.clear()
        for name in sorted(self._db_players, key=str.casefold):
            if query in name.lower():
                self._player_list.addItem(name)
        self._player_list.blockSignals(False)

    def _on_player_select(self, current, _prev=None):
        if current is None:
            return
        name = current.text()
        self._db_selected_player = name
        self._editing_label.setText(f"Editing: {name}")
        self._populate_char_tree(name)
        self._clear_form()

    def _sort_char_entries(self, name: str):
        """Group a player's rows by character, in place.

        The sort is stable, so a character's own costumes keep their relative
        order -- which matters, because the first of them is the fallback
        default when none is marked preferred. Sorting the model rather than
        just the view keeps tree row indexes usable as model indexes.
        """
        entries = self._db_players.get(name)
        if entries:
            entries.sort(key=lambda e: e[0].casefold())

    def _populate_char_tree(self, name: str):
        """List a player's character/costume rows, checking the preferred one.

        A character listed more than once has several costumes available for
        per-set use; the checked row (or the first, if none is starred) is the
        one used when a VOD line doesn't name a costume.
        """
        self._sort_char_entries(name)
        self._char_tree.clear()
        entries = self._db_players.get(name, [])
        # Which row wins for each character, mirroring skin_utils.preferred_stem
        winner: dict[str, int] = {}
        for idx, (char, alt) in enumerate(entries):
            _stem, is_pref = split_pref(alt)
            key = char.upper()
            if is_pref and key not in winner:
                winner[key] = idx
        for idx, (char, alt) in enumerate(entries):
            key = char.upper()
            if key not in winner:
                winner[key] = idx
        counts: dict[str, int] = {}
        for char, _ in entries:
            counts[char.upper()] = counts.get(char.upper(), 0) + 1
        # Rebuilding rows fires itemChanged for every setCheckState; ignore those.
        self._char_tree_updating = True
        try:
            for idx, (char, alt) in enumerate(entries):
                stem, _ = split_pref(alt)
                lbl = stem if stem else "(none)"
                key = char.upper()
                item = QtWidgets.QTreeWidgetItem(self._char_tree, [char, lbl])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # Exactly one row per character is checked: the explicitly
                # preferred one, else the first listed. Something always wins,
                # so the box shows which costume is actually in use.
                chosen = winner.get(key) == idx
                item.setCheckState(
                    2, Qt.CheckState.Checked if chosen else Qt.CheckState.Unchecked)
                item.setToolTip(2, (
                    "This costume is used when a VOD line doesn't name one"
                    if chosen else
                    f"Tick to make this {char}'s default costume"))
                if chosen and counts[key] > 1:
                    font = item.font(1)
                    font.setBold(True)
                    item.setFont(1, font)
        finally:
            self._char_tree_updating = False

    def _on_char_tree_check(self, item, column):
        """Tick a Preferred box to make that costume the character's default.

        Both outcomes rebuild the tree, which deletes every QTreeWidgetItem --
        including the one Qt is still inside ``setData`` on while it delivers
        this signal. Doing that synchronously is a use-after-free that crashes
        the process outright (no traceback), and it only shows up once a
        character has a second costume to tick. So the row index is taken here
        and the rebuild is deferred to the next event-loop turn, by which point
        Qt has finished with the item."""
        if column != 2 or self._char_tree_updating:
            return
        idx = self._char_tree.indexOfTopLevelItem(item)
        if idx < 0:
            return
        checked = item.checkState(2) == Qt.CheckState.Checked
        player = self._db_selected_player
        QtCore.QTimer.singleShot(
            0, lambda: self._apply_char_tree_check(player, idx, checked))

    def _apply_char_tree_check(self, player, idx: int, checked: bool):
        """Deferred half of :meth:`_on_char_tree_check` (see why it is deferred).

        The player may have changed in the meantime -- a tick is only ever
        applied to the player it was made on."""
        if player is None or player != self._db_selected_player:
            return
        if not checked:
            # Every character always has a default, so a box can't simply be
            # cleared -- pick a different row instead. Restore what we drew.
            self._populate_char_tree(player)
            return
        self._set_preferred_index(idx)

    def _set_preferred_entry(self):
        """Button path: make the selected row its character's default costume."""
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            self._log("[Select a costume row first]\n")
            return
        self._set_preferred_index(idx)

    def _set_preferred_index(self, idx: int):
        """Mark entry ``idx`` preferred, clearing the character's other rows.

        Shared by the Preferred checkbox and the Set Preferred button so the two
        can't drift apart.
        """
        entries = self._db_players.get(self._db_selected_player or "")
        if not entries or not (0 <= idx < len(entries)):
            return
        char = entries[idx][0]
        for i, (c, alt) in enumerate(entries):
            if c.upper() != char.upper():
                continue
            stem, _ = split_pref(alt)
            entries[i] = (c, join_pref(stem, i == idx))
        self._populate_char_tree(self._db_selected_player)
        self._char_tree.setCurrentItem(self._char_tree.topLevelItem(idx))
        self._autosave_player_db()
        self._log(f"[Preferred costume for {char}: "
                  f"{split_pref(entries[idx][1])[0]}]\n")

    def _confirm_add_player(self):
        name = self._new_player.text().strip()
        if not name:
            return
        if name in self._db_players:
            self._log(f"[Player '{name}' already exists]\n")
            self._new_player.clear()
            return
        self._db_players[name] = []
        self._new_player.clear()
        self._player_search.clear()
        self._refresh_player_list()
        items = self._player_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self._player_list.setCurrentItem(items[0])
        self._autosave_player_db()

    def _remove_player(self):
        if not self._db_selected_player or self._db_selected_player not in self._db_players:
            return
        del self._db_players[self._db_selected_player]
        self._db_selected_player = None
        self._refresh_player_list()
        self._char_tree.clear()
        self._editing_label.setText("Select a player")
        self._autosave_player_db()

    def _on_form_char_change(self, *_):
        char = self._form_char.currentText().strip()
        alts = get_alts_for_char(char)
        self._form_alt.blockSignals(True)
        self._form_alt.clear()
        self._form_alt.addItems(alts)
        self._form_alt.blockSignals(False)
        if alts:
            self._form_alt.setCurrentIndex(0)
        self._on_form_alt_change()

    def _on_form_alt_change(self, *_):
        char = self._form_char.currentText().strip()
        alt = self._form_alt.currentText().strip()
        self._show_preview(skin_utils.render_stem(char, alt) if char and alt else "")

    def _on_char_tree_select(self, current, _prev=None):
        if current is None:
            return
        char = current.text(0)
        alt = current.text(1)
        if alt == "(none)":
            alt = ""
        self._show_preview(skin_utils.render_stem(char, alt) if char and alt else "")

    def _show_preview(self, stem: str, label: QtWidgets.QLabel | None = None):
        """Draw a render into a preview label (the Player Database one by default).

        ``stem`` is a render filename without the extension, "Mario (5)" --
        build it with skin_utils.render_stem rather than by hand.

        The cache is keyed by size as well as stem, because the tabs show the
        same renders at different sizes and a scaled pixmap can't be reused
        across them without blurring.
        """
        label = label if label is not None else self._preview_label
        if not stem:
            label.clear()
            return
        size = label.size()
        key = (stem, size.width(), size.height())
        if key in self._preview_cache:
            label.setPixmap(self._preview_cache[key])
            return
        path = RENDERS_DIR / f"{stem}.png"
        if not path.exists():
            label.clear()
            return
        pix = QtGui.QPixmap(str(path))
        if pix.isNull():
            label.clear()
            return
        scaled = pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        self._preview_cache[key] = scaled
        label.setPixmap(scaled)

    def _add_char_entry(self):
        if not self._db_selected_player:
            self._log("[Select a player first]\n")
            return
        char = self._form_char.currentText().strip()
        if not char:
            self._log("[Select a character]\n")
            return
        alt = self._form_alt.currentText().strip()
        entries = self._db_players[self._db_selected_player]
        # Adding a second costume for a character makes the default ambiguous, so
        # pin the one that was already winning. Behaviour is then unchanged until
        # the user explicitly stars a different one.
        same = [i for i, (c, _) in enumerate(entries) if c.upper() == char.upper()]
        if same and not any(split_pref(entries[i][1])[1] for i in same):
            c0, a0 = entries[same[0]]
            entries[same[0]] = (c0, join_pref(split_pref(a0)[0], True))
            self._log(f"[{char} now has {len(same) + 1} costumes - "
                      f"{split_pref(a0)[0]} kept as preferred]\n")
        entries.append((char, alt))
        self._populate_char_tree(self._db_selected_player)
        self._autosave_player_db()

    def _edit_char_entry(self):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        if idx >= len(chars):
            return
        char, alt = chars[idx]
        self._form_char.setCurrentText(char)
        # The star is a property of the row, not something to edit by hand.
        self._form_alt.setCurrentText(split_pref(alt)[0])
        self._db_selected_char_idx = idx
        self._form_add_btn.setEnabled(False)
        self._form_edit_btn.setEnabled(True)

    def _update_char_entry(self):
        if self._db_selected_char_idx is None or not self._db_selected_player:
            return
        char = self._form_char.currentText().strip()
        alt = self._form_alt.currentText().strip()
        chars = self._db_players[self._db_selected_player]
        if self._db_selected_char_idx < len(chars):
            # Editing a row must not silently demote it: keep whatever preferred
            # state it already had.
            _old, was_pref = split_pref(chars[self._db_selected_char_idx][1])
            chars[self._db_selected_char_idx] = (char, join_pref(alt, was_pref))
        self._populate_char_tree(self._db_selected_player)
        self._clear_form()
        self._autosave_player_db()

    def _remove_char_entry(self):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        if idx < len(chars):
            chars.pop(idx)
        self._populate_char_tree(self._db_selected_player)
        self._autosave_player_db()

    def _move_char_entry(self, direction: int):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        new_idx = idx + direction
        if not (0 <= new_idx < len(chars)):
            return
        # Rows are grouped by character now, so a swap across two characters
        # would just be undone by the sort on the next repopulate. Reordering a
        # character's own costumes -- which decides the fallback default when
        # none is starred -- still works, and is what this is mainly for.
        if chars[idx][0].upper() != chars[new_idx][0].upper():
            self._log("[Rows are grouped by character; reorder a character's own "
                      "costumes instead]\n")
            return
        chars[idx], chars[new_idx] = chars[new_idx], chars[idx]
        self._populate_char_tree(self._db_selected_player)
        self._char_tree.setCurrentItem(self._char_tree.topLevelItem(new_idx))
        self._autosave_player_db()

    def _clear_form(self):
        self._form_char.setCurrentText("")
        self._form_alt.clear()
        self._form_add_btn.setEnabled(True)
        self._form_edit_btn.setEnabled(False)
        self._db_selected_char_idx = None
        self._preview_label.clear()

    def _save_player_db(self):
        try:
            save_player_db(self._db_header, self._db_players)
            self._log("[Player database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving player database: {exc}]\n")

    def _autosave_player_db(self):
        try:
            save_player_db(self._db_header, self._db_players)
            self._log("[Auto-saved: player database]\n")
        except Exception as exc:
            self._log(f"[Error auto-saving player database: {exc}]\n")
        # Adding a player here can unblock Add Missing Costumes on the other tab.
        self._update_import_btn()

    # ================================================================== #
    #  Tab: Character Database (two-column alias -> filename)           #
    # ================================================================== #
    def _build_char_db_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        self._cdb_headers: list[str] = []
        self._cdb_sel_idx: int | None = None

        hl = QtWidgets.QLabel("Characters")
        hl.setObjectName("heading")
        outer.addWidget(hl)
        outer.addWidget(_muted(
            "Maps an alias used in VOD names to the character's render filename "
            "(without the ' (N)' costume suffix)."))

        self._cdb_tree = QtWidgets.QTreeWidget()
        self._cdb_tree.setColumnCount(2)
        self._cdb_tree.setHeaderLabels(["Alias (in VOD names)", "Filename (in renders folder)"])
        self._cdb_tree.setColumnWidth(0, 220)
        self._cdb_tree.setRootIsDecorated(False)
        self._cdb_tree.currentItemChanged.connect(self._cdb_on_select)
        outer.addWidget(self._cdb_tree)

        form = QtWidgets.QGroupBox("Add / Edit Entry")
        fr = QtWidgets.QHBoxLayout(form)
        fr.addWidget(QtWidgets.QLabel("Alias:"))
        self._cdb_alias = QtWidgets.QLineEdit()
        self._cdb_alias.setMinimumWidth(160)
        fr.addWidget(self._cdb_alias)
        fr.addSpacing(10)
        fr.addWidget(QtWidgets.QLabel("Filename:"))
        self._cdb_filename = QtWidgets.QLineEdit()
        self._cdb_filename.setMinimumWidth(220)
        fr.addWidget(self._cdb_filename)
        fr.addStretch(1)
        outer.addWidget(form)

        br = QtWidgets.QHBoxLayout()
        self._cdb_add_btn = QtWidgets.QPushButton("Add Entry")
        self._cdb_add_btn.clicked.connect(self._cdb_add)
        br.addWidget(self._cdb_add_btn)
        self._cdb_update_btn = QtWidgets.QPushButton("Update Entry")
        self._cdb_update_btn.setEnabled(False)
        self._cdb_update_btn.clicked.connect(self._cdb_update)
        br.addWidget(self._cdb_update_btn)
        rmb = QtWidgets.QPushButton("Remove Selected")
        rmb.clicked.connect(self._cdb_remove)
        br.addWidget(rmb)
        clf = QtWidgets.QPushButton("Clear Form")
        clf.clicked.connect(self._cdb_clear_form)
        br.addWidget(clf)
        br.addStretch(1)
        outer.addLayout(br)

        sr = QtWidgets.QHBoxLayout()
        sb = QtWidgets.QPushButton("Save Character Database")
        sb.setObjectName("accent")
        sb.clicked.connect(self._cdb_save)
        sr.addWidget(sb)
        rl = QtWidgets.QPushButton("Reload from File")
        rl.clicked.connect(self._cdb_reload)
        sr.addWidget(rl)
        sr.addStretch(1)
        outer.addLayout(sr)

        self.tabs.addTab(tab, "Character Database")
        self._cdb_reload()

    def _cdb_reload(self):
        self._cdb_headers, entries = load_char_db()
        self._cdb_tree.clear()
        for alias, filename in entries:
            QtWidgets.QTreeWidgetItem(self._cdb_tree, [alias, filename])
        self._cdb_clear_form()

    def _cdb_entries(self) -> list[tuple[str, str]]:
        out = []
        for i in range(self._cdb_tree.topLevelItemCount()):
            it = self._cdb_tree.topLevelItem(i)
            out.append((it.text(0), it.text(1)))
        return out

    def _cdb_on_select(self, current, _prev=None):
        if current is None:
            return
        self._cdb_sel_idx = self._cdb_tree.indexOfTopLevelItem(current)
        self._cdb_alias.setText(current.text(0))
        self._cdb_filename.setText(current.text(1))
        self._cdb_add_btn.setEnabled(False)
        self._cdb_update_btn.setEnabled(True)

    def _cdb_add(self):
        alias = self._cdb_alias.text().strip()
        filename = self._cdb_filename.text().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        item = QtWidgets.QTreeWidgetItem(self._cdb_tree, [alias, filename])
        self._cdb_tree.setCurrentItem(item)
        self._cdb_tree.scrollToItem(item)

    def _cdb_update(self):
        if self._cdb_sel_idx is None:
            return
        alias = self._cdb_alias.text().strip()
        filename = self._cdb_filename.text().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        it = self._cdb_tree.topLevelItem(self._cdb_sel_idx)
        if it:
            it.setText(0, alias)
            it.setText(1, filename)
        self._cdb_clear_form()

    def _cdb_remove(self):
        idx = self._cdb_tree.indexOfTopLevelItem(self._cdb_tree.currentItem())
        if idx < 0:
            return
        self._cdb_tree.takeTopLevelItem(idx)
        self._cdb_clear_form()

    def _cdb_clear_form(self):
        self._cdb_alias.clear()
        self._cdb_filename.clear()
        self._cdb_sel_idx = None
        self._cdb_add_btn.setEnabled(True)
        self._cdb_update_btn.setEnabled(False)

    def _cdb_save(self):
        try:
            save_char_db(self._cdb_headers, self._cdb_entries())
            self._log("[Character database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving character database: {exc}]\n")

    # ================================================================== #
    #  Tab: Update                                                      #
    # ================================================================== #
    def _build_update_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        box = QtWidgets.QGroupBox("Update Melee Generator")
        v = QtWidgets.QVBoxLayout(box)
        v.addWidget(_muted(
            "Check GitHub for a newer version of this generator and apply it. "
            "Only the Melee_Generator folder is updated — your player "
            "database and settings are preserved. Restart the app after updating "
            "to load the new version."))

        self._update_status = QtWidgets.QLabel("Status: not checked yet.")
        self._update_status.setObjectName("heading")
        v.addWidget(self._update_status)

        row = QtWidgets.QHBoxLayout()
        self._check_update_btn = QtWidgets.QPushButton("Check for Updates")
        self._check_update_btn.clicked.connect(self._on_check_updates)
        row.addWidget(self._check_update_btn)
        self._do_update_btn = QtWidgets.QPushButton("Update Now")
        self._do_update_btn.setObjectName("accent")
        self._do_update_btn.clicked.connect(self._on_do_update)
        row.addWidget(self._do_update_btn)
        row.addStretch(1)
        v.addLayout(row)

        outer.addWidget(box)
        outer.addStretch(1)
        self.tabs.addTab(tab, "Update")

    def _run_git(self, args: list, echo: bool = True):
        cmd = ["git"] + args
        if echo:
            self._log("> " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), capture_output=True,
                text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self._log("[Error: git not found. Install Git for Windows to enable updates.]\n")
            return 1, ""
        out = (proc.stdout or "") + (proc.stderr or "")
        if echo and out.strip():
            self._log(out if out.endswith("\n") else out + "\n")
        return proc.returncode, (proc.stdout or "")

    def _on_check_updates(self):
        if getattr(self, "_update_running", False):
            return
        self._update_running = True
        self.update_status_signal.emit("Checking…", "busy")
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _on_do_update(self):
        if getattr(self, "_update_running", False):
            return
        resp = QtWidgets.QMessageBox.question(
            self, "Update Generator",
            "Update this generator to the latest version from GitHub?\n\n"
            "Your player database and settings will be preserved. "
            "Restart the app afterwards to load the new version.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No)
        if resp != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._update_running = True
        self.update_status_signal.emit("Updating…", "busy")
        threading.Thread(target=self._apply_update_worker, daemon=True).start()

    def _check_updates_worker(self):
        try:
            if self._run_git(["rev-parse", "--is-inside-work-tree"], echo=False)[0] != 0:
                self.update_status_signal.emit(
                    "Not a git checkout — updates unavailable. "
                    "Re-clone from GitHub to enable updating.", "err")
                return
            if self._run_git(["fetch", "origin", "main"])[0] != 0:
                self.update_status_signal.emit(
                    "Could not reach GitHub. Check your internet connection.", "err")
                return
            remote = self._run_git(
                ["rev-parse", "FETCH_HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
            head = self._run_git(
                ["rev-parse", "HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
            marker = self._settings.get("last_update_tree", "")
            if not remote:
                self.update_status_signal.emit(
                    "Could not determine update status.", "err")
            elif remote == head or remote == marker:
                self.update_status_signal.emit("Up to date.", "ok")
            else:
                self.update_status_signal.emit(
                    "Update available! Click “Update Now” to install.", "avail")
        finally:
            self._update_running = False

    def _apply_update_worker(self):
        try:
            self._log("\n=== Updating " + GENERATOR_DIR + " ===\n")
            if self._run_git(["rev-parse", "--is-inside-work-tree"], echo=False)[0] != 0:
                self._log("[Not a git checkout — cannot update.]\n\n")
                self.update_done_signal.emit(False, "")
                return

            dirty = bool(self._run_git(
                ["status", "--porcelain", "--", GENERATOR_DIR], echo=False)[1].strip())
            stashed = False
            if dirty:
                self._log("Stashing your local changes…\n")
                stashed = self._run_git(
                    ["stash", "push", "--include-untracked",
                     "-m", "pre-update (GUI)", "--", GENERATOR_DIR])[0] == 0

            if self._run_git(["fetch", "origin", "main"])[0] != 0:
                if stashed:
                    self._run_git(["stash", "pop"])
                self.update_done_signal.emit(False, "")
                return

            ok = self._run_git(
                ["checkout", "FETCH_HEAD", "--", GENERATOR_DIR])[0] == 0

            if stashed:
                self._log("Restoring your local changes…\n")
                if self._run_git(["stash", "pop"])[0] != 0:
                    self._log("[Warning: could not auto-restore local changes due to a "
                              "conflict. Run 'git stash pop' manually to resolve.]\n")

            if ok:
                sha = self._run_git(
                    ["rev-parse", "FETCH_HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
                self.update_done_signal.emit(True, sha)
            else:
                self.update_done_signal.emit(False, "")
        finally:
            self._update_running = False

    def _on_update_status(self, msg: str, level: str):
        colors = {"ok": "#3FB950", "avail": "#E08000",
                  "err": "#E5534B", "busy": _MUTED}
        self._update_status.setText("Status: " + msg)
        self._update_status.setStyleSheet(
            "font-weight: 600; font-size: 11pt; color: %s;"
            % colors.get(level, _FG))
        busy = (level == "busy")
        self._check_update_btn.setEnabled(not busy)
        self._do_update_btn.setEnabled(not busy)

    def _on_update_done(self, success: bool, sha: str):
        if success:
            if sha:
                self._settings["last_update_tree"] = sha
                self._save_settings()
            self._log("[Update complete. Restart the generator to load the new version.]\n\n")
            self.update_status_signal.emit(
                "Updated! Restart the app to load the new version.", "ok")
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            box.setWindowTitle("Update Complete")
            box.setText("The generator was updated successfully.\n\n"
                        "Restart the app now to load the new version.")
            restart_btn = box.addButton("Restart Now",
                                        QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Later", QtWidgets.QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restart_btn:
                self._restart_app()
        else:
            self._log("[Update failed. See messages above.]\n\n")
            self.update_status_signal.emit(
                "Update failed. See the console for details.", "err")

    def _restart_app(self):
        """Relaunch this app with the same interpreter/arguments, then quit."""
        self._log("[Restarting…]\n")
        QProcess.startDetached(sys.executable, sys.argv[:])
        QtWidgets.QApplication.quit()

    # ================================================================== #
    #  Process runners (QProcess; streams output to the console)        #
    # ================================================================== #
    def _run(self, cmd: list, on_done=None):
        proc = QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._log("> " + " ".join(str(c) for c in cmd) + "\n")
        proc.readyReadStandardOutput.connect(lambda p=proc: self._read_proc(p))

        def _fin(code, _status, p=proc, cb=on_done):
            self._read_proc(p)
            self._log(f"[Done — exit {code}]\n\n")
            if code == 0 and cb:
                cb()
            self._procs.discard(p)
        proc.finished.connect(_fin)
        proc.errorOccurred.connect(
            lambda _e, p=proc: self._log(f"[Error: {p.errorString()}]\n\n"))
        self._procs.add(proc)
        proc.start(str(cmd[0]), [str(c) for c in cmd[1:]])

    def _read_proc(self, proc: QProcess):
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if data:
            self._log(data)

    # ------------------------------------------------------------------ #
    #  Console                                                           #
    # ------------------------------------------------------------------ #
    def _log(self, text: str):
        self.log_signal.emit(text)

    def _append_console(self, text: str):
        self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _clear_console(self):
        self.console.clear()

    def closeEvent(self, event):
        self._flush_vod_autosave()
        self._flush_notes_autosave()
        super().closeEvent(event)


def _init_web_engine() -> None:
    """Prepare QtWebEngine before the QApplication exists.

    Qt requires AA_ShareOpenGLContexts to be set before the application is
    constructed, and wants the module imported up front. Leaving it until the
    first web view is created makes Qt reconfigure the top-level window at that
    moment: on Windows the native window is destroyed and recreated, which looks
    to the user like the whole app closing and reopening.

    The import costs about 0.1s and starts no Chromium process -- that still
    waits until a page is actually created, so the Top 8 preview stays as lazy
    as it was.
    """
    QtCore.QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401  -- imported for its side effects
    except ImportError:
        pass  # the preview reports this itself; nothing else in the GUI needs it


def main():
    _init_web_engine()
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    # The Fusion combo-popup delegate paints the hovered/selected row from the
    # palette's Highlight role, ignoring ::item stylesheet rules -- so set a
    # bright Highlight here to make dropdown hovering clearly visible.
    pal = app.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(_HILITE))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(pal)

    app.setStyleSheet(STYLESHEET)
    win = MeleeWindow()
    # Before show(): see prewarm_top8_preview.
    win.prewarm_top8_preview()

    if "--selftest" in sys.argv:
        # Construct, show briefly, then quit 0 -- used to validate the build.
        QtCore.QTimer.singleShot(0, app.quit)
        win.show()
        return app.exec()

    win.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
