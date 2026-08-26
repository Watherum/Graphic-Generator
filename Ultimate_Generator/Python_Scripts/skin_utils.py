#!/usr/bin/env python3
"""Shared skin/render helpers for the Ultimate_Generator.

Ported from ``Rivals_2_Generator/Python_Scripts/skin_utils.py`` so the thumbnail
generator and the GUI resolve a per-set costume the same way, from one
implementation. The function names match the Rivals module deliberately -- the
GUI code that calls them is otherwise identical between the two games.

Two vocabularies show up throughout, as in the Rivals module, but this game
collapses them almost to nothing:

* **stem**  -- what Player_database.csv stores for a costume. Here that is the
  bare alt number, ``"5"``. (In Rivals it is a whole render filename.)
* **label** -- the friendly form shown in the GUI and written into VOD lines.
  Also ``"5"``.

So ``skin_label()`` is nearly an identity function, and the render *filename* is
built separately by :func:`render_stem` -- ``render_stem("Mario", "5")`` ->
``"Mario (5)"``. Keep that distinction: a stem here is not a filename.

The player database may prefix an alt with ``*`` to mark it as that player's
preferred costume for the character (see ``split_pref``).
"""
from __future__ import annotations

import re as _re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Ultimate_Body_render"

#: Marks the preferred costume when it prefixes an alt in Player_database.csv.
#: ``*`` cannot appear in a Windows filename, so it can never collide with a
#: real alt.
PREFERRED_MARK = "*"

#: Alts are always a single digit in the render filenames for both this game and
#: Melee, which is what lets the legacy ``"Mario 5"`` VOD syntax be unambiguous.
ALT_DIGITS = "12345678"

_STEM_RE = _re.compile(r"^(?P<char>.*?)\s*\((?P<alt>\d+)\)$")


def render_stem(char_name: str, alt: str) -> str:
    """``("Mario", "5")`` -> ``"Mario (5)"`` -- the render filename without ``.png``.

    ``char_name`` must already be the *filename* form from Character_database.csv
    (``Banjo & Kazooie``, not the ``Banjo`` alias), because that is what the
    render files are named after.
    """
    return "{c} ({a})".format(c=char_name, a=alt)


def get_skins_for_char(char_name: str) -> list[str]:
    """Available alt numbers for a character, read from the renders folder.

    Returns stems in this module's sense -- bare alt numbers, ordered
    numerically. Falls back to 1-8 when the character has no render files yet so
    a costume can still be assigned. Mirrors ``get_alts_for_char`` in the GUI,
    which now delegates here.
    """
    if not char_name:
        return []
    alts: list[int] = []
    if RENDERS_DIR.exists():
        for f in RENDERS_DIR.glob("{c} (*).png".format(c=char_name)):
            m = _STEM_RE.match(f.stem)
            if m:
                alts.append(int(m.group("alt")))
    if not alts:
        return [str(i) for i in range(1, 9)]
    return [str(n) for n in sorted(set(alts))]


def skin_label(stem: str) -> str:
    """``"5"`` -> ``"5"``; also accepts a whole render stem, ``"Mario (5)"`` -> ``"5"``.

    Accepting both means GUI code ported from Rivals -- which hands whatever the
    player database gave it straight to this function -- keeps working.
    """
    stem = (stem or "").strip()
    m = _STEM_RE.match(stem)
    if m:
        return m.group("alt")
    return stem


def neutral_skin_for(char: str) -> str:
    """The default costume for a character: alt 1.

    Falls back to the lowest alt that actually exists, then to ``""``. Alt 1 is
    what the generator has always assumed when a line names no costume, so this
    only makes the existing behaviour explicit.
    """
    skins = get_skins_for_char(char)
    if "1" in skins:
        return "1"
    return skins[0] if skins else ""


# --------------------------------------------------------------------------- #
#  Preferred-skin marker                                                      #
# --------------------------------------------------------------------------- #
def split_pref(field: str) -> tuple[str, bool]:
    """``'*5'`` -> ``('5', True)``.

    The single chokepoint every reader of Player_database.csv goes through. A raw
    ``*`` must never reach a filesystem path, where it would fail silently rather
    than loudly.
    """
    field = (field or "").strip()
    if field.startswith(PREFERRED_MARK):
        return field[len(PREFERRED_MARK):].strip(), True
    return field, False


def join_pref(stem: str, is_preferred: bool) -> str:
    """Inverse of :func:`split_pref`, for writing the CSV back out."""
    return (PREFERRED_MARK + stem) if (is_preferred and stem) else stem


def preferred_stem(entries) -> str | None:
    """Pick a player's default costume from their rows for one character.

    ``entries`` is a list of ``(alt, is_preferred)``. The first starred entry
    wins; with no star we fall back to the first listed, which is what every
    pre-existing single-costume row does.
    """
    first = None
    for stem, is_pref in entries:
        if not stem:
            continue
        if is_pref:
            return stem
        if first is None:
            first = stem
    return first


# --------------------------------------------------------------------------- #
#  Label -> stem resolution (per-set costumes named in VOD lines)              #
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Fold case and collapse spaces/underscores so hand-typed labels still match."""
    return " ".join(str(text).replace("_", " ").split()).casefold()


def stem_for_label(char: str, label: str, candidates=None) -> str | None:
    """Resolve a costume label from a VOD line to an alt number.

    Searches ``candidates`` (the player's own alts, so their entries win) before
    falling back to every alt on disk for the character -- that fallback is what
    lets a one-off costume be used in a VOD line without editing the player
    database. Accepts ``"5"``, ``"(5)"`` or a full ``"Mario (5)"`` stem. Returns
    ``None`` on no match.
    """
    if not label:
        return None
    wanted = _norm(skin_label(str(label).strip().strip("()")))

    pools = []
    if candidates:
        pools.append([split_pref(c)[0] if isinstance(c, str) else c[0]
                      for c in candidates])
    pools.append(get_skins_for_char(char))

    for pool in pools:
        for stem in pool:
            if not stem:
                continue
            if _norm(skin_label(stem)) == wanted:
                return skin_label(stem)
    return None


def strip_skins(line: str) -> str:
    """Remove every per-set costume from a match line's character parentheses.

    Costumes are an internal rendering detail, not part of the YouTube title, so
    they are stripped wherever a line is copied for publishing or turned into an
    output filename (``:`` is not even legal in a Windows filename).

    Both syntaxes go: the ``Mario:5`` form this generator gained alongside
    Rivals, and the legacy ``Mario 5`` form that predates it. Only text inside
    parentheses is touched, so a line carrying neither is returned byte-for-byte
    unchanged -- separators and spacing included.
    """
    if ':' not in line and not _LEGACY_ALT_RE.search(line):
        return line
    return _PARENS_RE.sub(
        lambda m: '(' + _LEGACY_ALT_RE.sub(
            '', _SKIN_SUFFIX_RE.sub('', m.group(1))) + ')',
        line)


_PARENS_RE = _re.compile(r'\(([^)]*)\)')
_SKIN_SUFFIX_RE = _re.compile(r'\s*:[^,)]*')
#: The legacy inline alt: a space and one digit ending a character token. No
#: character in either game's roster ends in a digit, so this cannot eat a name.
#:
#: A token ends at a comma or the end of the string when this runs against the
#: parenthesised contents, and at ')' when strip_skins runs it against the whole
#: line as a cheap "anything to do?" guard -- all three must be in the lookahead
#: or that guard silently skips lines whose only costume is the last one.
_LEGACY_ALT_RE = _re.compile(r'(?<=[^\s,(])\s+[' + ALT_DIGITS + r'](?=\s*(?:,|\)|$))')


def split_char_skin(token: str) -> tuple[str, str | None]:
    """``'Mario:5'`` -> ``('Mario', '5')``; ``'Mario'`` -> ``('Mario', None)``.

    Splits on the first ``:``. Character names never contain a colon. The legacy
    ``'Mario 5'`` form has no colon and so comes back whole, for the caller's
    legacy branch to handle -- see :func:`split_legacy_alt`.
    """
    token = (token or "").strip()
    if ":" not in token:
        return token, None
    char, _, skin = token.partition(":")
    skin = skin.strip()
    return char.strip(), (skin or None)


def split_legacy_alt(token: str) -> tuple[str, str | None]:
    """``'Mario 5'`` -> ``('Mario', '5')``; ``'Mario'`` -> ``('Mario', None)``.

    The pre-existing inline syntax, kept so VOD files written before per-set
    costumes still resolve. Unlike the old inline check this cannot raise on a
    one-character token.
    """
    token = (token or "").strip()
    if len(token) >= 3 and token[-2] == ' ' and token[-1] in ALT_DIGITS:
        return token[:-2].strip(), token[-1]
    return token, None
