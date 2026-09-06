#!/usr/bin/env python3
"""Doubles/team name helpers shared by the fetchers, the GUI and the generator.

start.gg reports a doubles entrant as ``"shane / THE PIZZA GUY"``. That slash is
the reason doubles could not be generated at all: a match title becomes the
output thumbnail's filename, and ``/`` is a path separator on Windows rather
than a legal filename character. Teams are therefore written with a comma
between the members -- ``"shane,THE PIZZA GUY"`` -- everywhere a VOD name is
produced.

Both separators are accepted on the way in (:func:`split_team`), so VOD files
written before this change still parse; the generator normalises them as it
reads, so an old file renders without being edited.

The comma is safe in a VOD line because a player name is only ever read as
"everything before the ``(``" -- the commas that matter to the parser are the
ones *inside* the character parentheses. It is **not** safe in the Top 8 data
files, whose fields are comma separated, so nothing here is applied to those.
"""
from __future__ import annotations

import re as _re

#: What a team looks like once written out. No space, so the comma costs a
#: single character against the 100-char VOD line budget.
TEAM_SEPARATOR = ","

#: Accepts either separator, with or without surrounding spaces, so a
#: hand-typed "A, B" and a start.gg "A / B" both split the same way.
_SPLIT_RE = _re.compile(r'\s*[/,]\s*')


def split_team(name: str) -> list[str]:
    """``"shane / THE PIZZA GUY"`` -> ``['shane', 'THE PIZZA GUY']``.

    A singles tag comes back as a one-element list, so callers can treat both
    the same way. Empty pieces are dropped, which is what keeps a trailing
    separator from inventing a nameless member.
    """
    if not name:
        return []
    return [p for p in (part.strip() for part in _SPLIT_RE.split(name.strip())) if p]


def join_team(members) -> str:
    """Inverse of :func:`split_team`."""
    return TEAM_SEPARATOR.join(m.strip() for m in members if m and m.strip())


def is_team(name: str) -> bool:
    return len(split_team(name)) > 1


def normalize_team(name: str) -> str:
    """Rewrite a team name into the comma form; leave a singles tag alone.

    A tag is only rebuilt when it actually names more than one player, so a
    single name keeps whatever spacing it had (and a tag that happens to contain
    a slash is left untouched only if it does not split -- see the module
    docstring for why that trade is acceptable here).
    """
    members = split_team(name)
    if len(members) < 2:
        return name.strip() if name else name
    return join_team(members)


def member_for_index(name: str, index: int) -> str:
    """The team member who owns slot ``index`` (character *i* is member *i*).

    Falls back to the whole name for a singles tag, and to the last member when
    a team fields more characters than players.
    """
    members = split_team(name)
    if len(members) < 2:
        return name
    if index < len(members):
        return members[index]
    return members[-1]
