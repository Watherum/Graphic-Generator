#!/usr/bin/env python3
"""
Fetch completed sets from a Challonge tournament and print them in the VOD
naming format:
  {Tournament} - {Round} - {Player1} () Vs {Player2} () - {Game}

Output matches fetch_sets.py exactly, `# ABBREV:` header included, so a VOD file
is handled identically downstream whichever site it came from.

Usage:
  python fetch_challonge_sets.py <tournament-slug> [--name "My Tournament"]
                                 [--abbrev "MT 3"] [--out sets.txt]

Slug examples:
  my-weekly-42                      (challonge.com/my-weekly-42)
  myorg-my-weekly-42                (challonge.com/myorg/my-weekly-42)

Two things Challonge cannot give us
-----------------------------------
**Characters.** Challonge has no game model at all -- no character selections,
no per-game reporting beyond scores -- so every line comes back with empty
parentheses, permanently. This is not the "the TO didn't report games" case that
start.gg and parry.gg have; there is nothing to report. Fill the characters in
from the GUI (the Thumbnails tab flags lines with no character data in red, and
right-click -> Set skins... edits them).

**Round names.** A Challonge match carries only a signed integer round, so the
names are derived positionally -- see challonge_rounds.py.

Teams are also a known weak point: Challonge exposes no participant *count*, so
whether "A / B" is a doubles team or one player with a punctuated tag can only
be guessed from the name. See --no-teams below.
"""
import sys
import json
import argparse

import team_utils
import challonge_rounds
from challonge_api import (
    attrs, get_matches, get_participants, get_tournament, load_credentials,
    match_player_ids, missing_credentials_message, normalize_slug,
    participant_name, rel_id,
    resource_id, strip_sponsor, warn, PROPS_FILE,
)

# Mirrors MAX_LINE_LEN in fetch_sets.py and the GUI: the length past which
# a copied VOD line gets the abbreviation swapped in.
MAX_LINE_LEN = 100

#: Challonge's own game names -> the suffix the VOD lines use, matching the
#: substitutions fetch_sets.py and fetch_parrygg_sets.py make.
GAME_SUFFIXES = {
    "rivals of aether ii": "RoA II",
    "rivals of aether 2": "RoA II",
    "rivals 2": "RoA II",
    "super smash bros. ultimate": "SSBU",
    "super smash bros ultimate": "SSBU",
    "super smash bros. melee": "SSBM",
    "super smash bros melee": "SSBM",
}


def game_suffix(name: str) -> str:
    """The short game name for a VOD line, or the name as given."""
    return GAME_SUFFIXES.get((name or "").strip().lower(), (name or "").strip())


def format_entrant(name: str, split_teams: bool = True) -> tuple:
    """``(display name, was_split)`` for one Challonge entrant.

    The sponsor tag is stripped from the whole name **first**, which is what
    keeps the documented ``"NG/POA | Azul"`` failure from arising here at all:
    the part before " | " is the sponsor, slashes and all, and dropping it
    leaves a bare "Azul" with nothing left to split on.

    Only after that is the remainder split into team members, each of which may
    carry its own sponsor tag ("NG | A / POA | B"). Challonge has no
    participant count -- the guard start.gg's ``participants`` and parry.gg's
    ``users`` give -- so the split is a guess from punctuation, and every one is
    reported so it can be eyeballed. ``split_teams=False`` turns it off and
    treats every entrant as one player.
    """
    base = strip_sponsor((name or "").strip())
    if not split_teams:
        return team_utils.drop_separators(base), False
    members = team_utils.split_team(base)
    if len(members) < 2:
        return team_utils.drop_separators(base), False
    cleaned = [team_utils.drop_separators(strip_sponsor(m)) for m in members]
    return team_utils.join_team(cleaned) or team_utils.drop_separators(base), True


def build_participant_map(participants: list, split_teams: bool) -> tuple:
    """``({participant id: display name}, [names that were split])``.

    A Challonge participant id is also referenced by ``group_player_ids`` in a
    two-stage tournament, where the bracket matches point at the *group* player
    id rather than the top-level one. Both are mapped to the same name so a
    two-stage bracket resolves its players instead of printing "?".
    """
    names = {}
    split = []
    for p in participants:
        pid = resource_id(p)
        raw = participant_name(p)
        if not raw:
            continue
        display, was_split = format_entrant(raw, split_teams)
        if was_split:
            split.append(f"{raw}  ->  {display}")
        if pid:
            names[pid] = display
        for gid in (attrs(p).get("group_player_ids") or []):
            names[str(gid)] = display
    return names, split


def is_complete(match: dict) -> bool:
    """Whether the set was actually played out.

    Only completed sets belong in a VOD file: an open or pending match has no
    result and, in the bracket's later rounds, not even both players yet.
    """
    state = (attrs(match).get("state") or "").strip().lower()
    return state in ("complete", "completed")


def format_match(match: dict, label: str, names: dict, tournament_name: str,
                 game_name: str) -> str:
    """One VOD line, or "" when the match has no two identifiable players."""
    id1, id2 = match_player_ids(match)
    p1 = names.get(id1, "")
    p2 = names.get(id2, "")
    if not p1 or not p2:
        return ""
    # The empty parentheses are deliberate and are the shape the rest of the
    # pipeline expects; Challonge has no character data to put in them.
    matchup = f"{p1} () Vs {p2} ()"
    prefix = " - ".join(p for p in [tournament_name, label] if p)
    line = f"{prefix} - {matchup}"
    if game_name:
        line += f" - {game_name}"
    return line


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Challonge tournament sets and print in VOD naming format."
    )
    parser.add_argument("slug", help="Tournament slug, e.g. my-weekly-42 "
                                     "(or the challonge.com URL)")
    parser.add_argument("--name", "-n", default="",
                        help="Tournament short name override (default: the "
                             "tournament name from the API)")
    parser.add_argument(
        "--abbrev", "-a", default="",
        help="Abbreviated tournament name. Recorded in the '# ABBREV:' header "
             f"and used by the GUI when copying a line longer than {MAX_LINE_LEN} "
             "characters; the lines themselves always spell the event out in full")
    parser.add_argument("--out", "-o", default="",
                        help="Write output to this file instead of stdout")
    parser.add_argument("--game", "-g", default="",
                        help="Game suffix override, e.g. 'RoA II' (default: "
                             "derived from the tournament's game name)")
    parser.add_argument("--all", action="store_true",
                        help="Include matches that are not yet complete")
    parser.add_argument(
        "--no-teams", action="store_true",
        help="Treat every entrant as a single player. Challonge reports no "
             "participant count, so a doubles team can only be guessed from "
             "punctuation in the name; use this for a singles bracket whose "
             "tags contain '/' or ','")
    parser.add_argument("--props", default=PROPS_FILE,
                        help=f"Path to app.properties (default: {PROPS_FILE})")
    parser.add_argument("--debug", action="store_true",
                        help="Dump the first raw participant and match, to "
                             "check the API's response shape")
    args = parser.parse_args()

    creds = load_credentials(args.props)
    if not creds:
        warn("ERROR: " + missing_credentials_message(args.props))
        return 1

    slug = normalize_slug(args.slug)
    warn(f"Fetching tournament: {slug}")
    tournament = get_tournament(slug, creds)
    t_attrs = attrs(tournament)
    tournament_id = resource_id(tournament) or slug
    tournament_name = args.name or (t_attrs.get("name") or "").strip()
    ttype = t_attrs.get("tournament_type") or ""
    game_name = args.game or game_suffix(t_attrs.get("game_name") or "")

    warn(f"Tournament: {tournament_name}  |  Type: {ttype}  |  "
         f"Game: {game_name or '(none)'}  |  ID: {tournament_id}")

    participants = get_participants(tournament_id, creds)
    matches = get_matches(tournament_id, creds)
    warn(f"Participants: {len(participants)}  |  Raw matches: {len(matches)}")

    if args.debug:
        if participants:
            warn("--- first participant ---")
            warn(json.dumps(participants[0], indent=2)[:2000])
        if matches:
            warn("--- first match ---")
            warn(json.dumps(matches[0], indent=2)[:2000])

    names, split = build_participant_map(participants, not args.no_teams)
    if split:
        warn(f"WARNING: {len(split)} entrant name(s) were read as teams. "
             f"Challonge reports no participant count, so this is a guess from "
             f"the punctuation in the name -- check these, and re-run with "
             f"--no-teams if any is really one player:")
        for line in split:
            warn(f"  {line}")

    infos = [challonge_rounds.from_resource(m) for m in matches]
    labels = challonge_rounds.label_rounds(infos, ttype)

    # Bracket order, not API order. Challonge does not promise any particular
    # order for the match list, and suggested_play_order is exactly the order
    # the bracket was played in -- which is the order the VOD file wants, since
    # it is edited by deleting the off-stream sets from top to bottom.
    pairs = sorted(zip(matches, infos),
                   key=lambda pair: (pair[1].order, pair[1].round,
                                     pair[1].identifier, pair[1].key))

    lines = []
    skipped = 0
    for match, info in pairs:
        if not args.all and not is_complete(match):
            skipped += 1
            continue
        line = format_match(match, labels.get(info.key, ""), names,
                            tournament_name, game_name)
        if line:
            lines.append(line)

    warn(f"Formatted sets: {len(lines)}"
         + (f"  ({skipped} not complete)" if skipped else ""))
    warn("NOTE: Challonge has no character data, so every line has empty "
         "parentheses. Fill them in on the Generate Thumbnails tab.")

    # Record the abbreviation as a header comment -- the contract the GUI's
    # copy step and Len column depend on. Same as the other two fetchers: a VOD
    # file must look identical whichever provider it came from.
    header = f"# ABBREV: {args.abbrev}\n" if args.abbrev else ""

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(header + output + "\n")
        warn(f"Wrote to {args.out}")
    else:
        print(header + output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
