#!/usr/bin/env python3
"""Shared skin/render helpers for the Rivals_2_Generator.

These used to live inside ``rivals_gui.py``. The thumbnail generator needs the
same logic to resolve a per-set skin named in a VOD line, so they moved here and
both modules import them (keeping one implementation, one set of conventions).

Two vocabularies show up throughout:

* **stem**  -- the render filename without ``.png``, e.g. ``T_Ran_Panther_Neutral_CSP``
* **label** -- the friendly form shown in the GUI and written into VOD lines,
  e.g. ``Panther``.  ``skin_label()`` converts stem -> label.

The player database may prefix a stem with ``*`` to mark it as that player's
preferred skin for the character (see ``split_pref``).
"""
from __future__ import annotations

import re as _re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Rivals_2_Full_Renders"

#: Marks the preferred skin when it prefixes a stem in Player_database.csv.
#: ``*`` cannot appear in a Windows filename, so it can never collide with a
#: real stem.
PREFERRED_MARK = "*"


def char_abbrev(char_name: str) -> str:
    """The 3-letter prefix the devs use in render filenames (T_<Abbrev>_..._CSP.png).

    By convention the prefix is the first three letters of the character name with
    spaces removed (Absa->Abs, La Reina->Lar). Deriving it here means new characters
    work with no code changes as long as their CSPs follow that naming."""
    return char_name.replace(" ", "")[:3]


def get_skins_for_char(char_name: str) -> list[str]:
    if not RENDERS_DIR.exists():
        return []
    if char_name == "Random":
        return sorted(
            f.stem for f in RENDERS_DIR.glob("T_Ran_*.png")
            if not f.stem.endswith("_CSP")
        )
    prefix = f"t_{char_abbrev(char_name)}_".lower()
    return sorted(
        f.stem for f in RENDERS_DIR.glob("T_*_CSP.png")
        if f.stem.lower().startswith(prefix)
    )


def skin_label(stem: str) -> str:
    """T_Abs_Default_Blue_CSP -> Default Blue"""
    parts = stem.split("_", 2)
    if len(parts) < 3:
        return stem
    inner = parts[2]
    if inner.endswith("_CSP"):
        inner = inner[:-4]
    return inner.replace("_", " ")


def neutral_skin_for(char: str) -> str:
    """Return the default-neutral skin stem for a character, or '' if none found."""
    skins = get_skins_for_char(char)
    for s in skins:
        if "default" in s.lower() and "neutral" in s.lower():
            return s
    for s in skins:
        if "neutral" in s.lower():
            return s
    return skins[0] if skins else ""


# --------------------------------------------------------------------------- #
#  Preferred-skin marker                                                      #
# --------------------------------------------------------------------------- #
def split_pref(field: str) -> tuple[str, bool]:
    """``'*T_Ran_Panther_Neutral_CSP'`` -> ``('T_Ran_Panther_Neutral_CSP', True)``.

    The single chokepoint every reader of Player_database.csv goes through. A raw
    ``*`` must never reach a filesystem path or the ``^(T_[A-Za-z]+)_`` prefix
    regexes, both of which fail silently rather than loudly on it.
    """
    field = (field or "").strip()
    if field.startswith(PREFERRED_MARK):
        return field[len(PREFERRED_MARK):].strip(), True
    return field, False


def join_pref(stem: str, is_preferred: bool) -> str:
    """Inverse of :func:`split_pref`, for writing the CSV back out."""
    return (PREFERRED_MARK + stem) if (is_preferred and stem) else stem


def preferred_stem(entries) -> str | None:
    """Pick a player's default skin from their rows for one character.

    ``entries`` is a list of ``(stem, is_preferred)``. The first starred entry
    wins; with no star we fall back to the first listed, which is what every
    pre-existing single-skin row does.
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
#  Label -> stem resolution (per-set skins named in VOD lines)                 #
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Fold case and collapse spaces/underscores so hand-typed labels still match."""
    return " ".join(str(text).replace("_", " ").split()).casefold()


def stem_for_label(char: str, label: str, candidates=None) -> str | None:
    """Resolve a friendly skin label to a render stem.

    Searches ``candidates`` (the player's own stems, so their entries win) before
    falling back to every skin on disk for the character -- that fallback is what
    lets a one-off skin be used in a VOD line without editing the player database.
    Also accepts a full stem in place of a label. Returns ``None`` on no match.
    """
    if not label:
        return None
    wanted = _norm(label)

    pools = []
    if candidates:
        pools.append([split_pref(c)[0] if isinstance(c, str) else c[0]
                      for c in candidates])
    pools.append(get_skins_for_char(char))

    for pool in pools:
        for stem in pool:
            if not stem:
                continue
            if _norm(skin_label(stem)) == wanted or _norm(stem) == wanted:
                return stem

    # No exact hit. Labels carry the colour variant ("Panther Neutral"), so accept
    # a shorter hand-typed prefix ("Panther") -- but only when it is unambiguous,
    # otherwise we would silently pick an arbitrary colour.
    for pool in pools:
        hits = [s for s in pool
                if s and _norm(skin_label(s)).split() and
                _norm(skin_label(s)).startswith(wanted)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None
    return None


def strip_skins(line: str) -> str:
    """Remove every ``:Skin`` from a match line's character parentheses.

    Skins are an internal rendering detail, not part of the YouTube title, so
    they are stripped wherever a line is copied for publishing or turned into an
    output filename (``:`` is not even legal in a Windows filename).

    Only text inside parentheses is touched, and only when a colon is present,
    so a line without skins is returned byte-for-byte unchanged -- separators and
    spacing included.
    """
    if ':' not in line:
        return line
    return _PARENS_RE.sub(
        lambda m: '(' + _SKIN_SUFFIX_RE.sub('', m.group(1)) + ')',
        line)


_PARENS_RE = _re.compile(r'\(([^)]*)\)')
_SKIN_SUFFIX_RE = _re.compile(r'\s*:[^,)]*')


def split_char_skin(token: str) -> tuple[str, str | None]:
    """``'Ranno:Panther'`` -> ``('Ranno', 'Panther')``; ``'Ranno'`` -> ``('Ranno', None)``.

    Splits on the first ``:``. Character names never contain a colon, and skin
    labels may contain spaces, so callers must split the parenthesised character
    list on ``,`` first and hand each element here.
    """
    token = (token or "").strip()
    if ":" not in token:
        return token, None
    char, _, skin = token.partition(":")
    skin = skin.strip()
    return char.strip(), (skin or None)
