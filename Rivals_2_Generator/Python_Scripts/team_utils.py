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


def drop_separators(name: str) -> str:
    """Strip separator characters out of a single player's name.

    A name reaches a thumbnail filename, so a ``/`` in it is a path separator on
    Windows, and a ``,`` would read back as a second team member. Neither can be
    kept, and this is only ever applied to a name already known to be *one*
    player, so nothing is being flattened away.
    """
    if not name:
        return name
    cleaned = _SPLIT_RE.sub(" ", name.strip())
    return " ".join(cleaned.split())


def split_entrant(name: str, member_count=None) -> list[str]:
    """The members of an entrant, preferring the bracket software's own count.

    Punctuation alone cannot tell a doubles team from a singles player whose
    *sponsor* carries a slash: start.gg reports a real entrant as
    ``"NG/POA | Azul"``, and reading that as a team invents a player called
    "NG" and attributes half the set to them. When the source says how many
    participants an entrant has -- start.gg's ``Entrant.participants``,
    parry.gg's ``Entrant.users`` -- that count decides, because one participant
    is one player whatever the tag looks like.

    ``member_count`` of ``None`` means "not known", and falls back to splitting
    on the separator, which is what a hand-typed VOD line still needs.
    """
    if member_count is not None and member_count < 2:
        stripped = (name or "").strip()
        return [stripped] if stripped else []
    return split_team(name)


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


def order_chars_by_member(members, groups):
    """Flatten per-participant character lists into one list in member order.

    A team's characters are reported by the bracket software per *participant*,
    in whatever order it happens to list them. The VOD line needs them in the
    order the team name spells its members out, because character *i* belongs to
    member *i* -- that is the rule the generator's ``resolvePlayerForChar`` and
    the GUI's ``_expand_team`` both resolve a doubles line by.

    ``members`` is ``[(member_id, member_name), ...]`` in the order the name
    lists them; either half may be empty when the source does not supply it.
    ``groups`` is ``[(participant_id, participant_name, [char, ...]), ...]`` in
    API order. A group is claimed by id first, then by name (case-insensitively),
    and failing both by position -- so a source that supplies neither still
    yields API order, which is what singles has always done.

    Characters are deduplicated **within** a member and never across the team:
    two members who both pick Ranno must produce two Rannos, or every character
    after them belongs to the wrong member. A member the API said nothing about
    contributes nothing, so the positions shift; the generator recovers from that
    by falling back to whichever member's database row owns the character.

    Team size is not fixed at two anywhere here -- a 3v3 flattens the same way.
    """
    groups = [(gid or "", gname or "", list(chars)) for gid, gname, chars in groups]
    claimed = [False] * len(groups)
    ordered = []

    def _claim(match):
        for i, group in enumerate(groups):
            if not claimed[i] and match(group):
                claimed[i] = True
                return group
        return None

    for member_id, member_name in members:
        group = None
        if member_id:
            group = _claim(lambda g, k=member_id: g[0] == k)
        if group is None and member_name:
            key = member_name.strip().upper()
            group = _claim(lambda g, k=key: g[1].strip().upper() == k)
        if group is None:
            group = _claim(lambda g: True)
        if group is not None:
            ordered.append(group)
    # A participant matching no member is still someone who played: keep them at
    # the end rather than dropping their characters off the line entirely.
    ordered.extend(g for i, g in enumerate(groups) if not claimed[i])

    out = []
    for _, _, chars in ordered:
        seen = set()
        for a_char in chars:
            if a_char and a_char.upper() not in seen:
                seen.add(a_char.upper())
                out.append(a_char)
    return out
