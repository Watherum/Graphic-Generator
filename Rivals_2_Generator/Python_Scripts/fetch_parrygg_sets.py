#!/usr/bin/env python3
"""
Fetch completed sets from a parry.gg event and print them in the VOD naming format:
  {Tournament} - {Round} - {Player1} ({Chars}) Vs {Player2} ({Chars}) - {Game}

Output matches fetch_sets.py exactly, `# ABBREV:` header included, so a VOD file
is handled identically downstream whichever site it came from.

Usage:
  python fetch_parrygg_sets.py <tournament-slug> [--event 0] [--name "My Tournament"]
                               [--abbrev "MT 3"] [--out sets.txt]

Unlike start.gg, the slug names a *tournament*; --event picks the event inside it
by 0-based index (or by event slug).

Slug example:
  immortal-fight-night-274
"""
import sys
import re
import argparse
import requests
from pathlib import Path
from typing import Optional

import team_utils

# Mirrors MAX_LINE_LEN in fetch_sets.py and the GUI: the length past which
# a copied VOD line gets the abbreviation swapped in.
MAX_LINE_LEN = 100

BASE_URL = "https://grpcweb.parry.gg"
REQUEST_TIMEOUT = 20.0
PAGE_SIZE = 50

# app.properties lives two levels up from this script (Graphic Generator root)
_SCRIPT_DIR = Path(__file__).resolve().parent
PROPS_FILE = str(_SCRIPT_DIR.parent.parent / "app.properties")


def load_api_key(props_path: str) -> str:
    try:
        with open(props_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("parrygg.api.key"):
                    _, _, val = line.partition("=")
                    return val.strip()
    except FileNotFoundError:
        pass
    return ""


def parry_post(endpoint: str, body: dict, api_key: str) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }
    for attempt in range(5):
        r = requests.post(url, json=body, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if attempt == 4:
            raise RuntimeError(f"Request to {endpoint} failed (HTTP {r.status_code}): {r.text[:200]}")
    return {}


def normalize_slug(value: str) -> str:
    """Reduce a pasted parry.gg URL to the bare tournament slug.

    A copied bracket URL carries extra path segments after the slug
    ("<slug>/bracket/main"), and the tournament lookup matches on the slug
    alone -- with the suffix attached, custom_slug misses, the trailing-hex
    strip cannot fire (it is anchored to the end of the string), and the
    name fallback searches for 'Bracket Main'.
    """
    slug = re.sub(r"^https?://(?:www[.])?parry[.]gg/", "", value.strip())
    slug = slug.split("?")[0].strip("/")
    return slug.split("/")[0]


def get_tournament(slug: str, api_key: str) -> dict:
    slug = normalize_slug(slug)
    # Try the slug as-is first, then without any trailing hex ID (e.g. "-019c9aeb")
    slugs_to_try = [slug]
    stripped = re.sub(r"-[0-9a-f]{8}$", "", slug)
    if stripped != slug:
        slugs_to_try.append(stripped)

    for attempt_slug in slugs_to_try:
        data = parry_post(
            "parrygg.services.TournamentService/GetTournaments",
            {"filter": {"custom_slug": attempt_slug}},
            api_key,
        )
        tournaments = data.get("tournaments") or []
        if tournaments:
            return tournaments[0]

    # Fall back: search by name derived from slug (strip trailing short UUID, replace hyphens)
    name_guess = re.sub(r"-[0-9a-f]{8}$", "", slug).replace("-", " ").title()
    print(f"Slug lookup failed — trying name search: {name_guess!r}", file=sys.stderr)
    data = parry_post(
        "parrygg.services.TournamentService/GetTournaments",
        {"filter": {"name": name_guess}},
        api_key,
    )
    tournaments = data.get("tournaments") or []
    if tournaments:
        return tournaments[0]

    raise RuntimeError(
        f"No tournament found for slug: {slug!r}\n"
        f"Check the slug in the parry.gg URL — it should be the part after https://parry.gg/"
    )


def get_all_matches(event_id: str, api_key: str) -> list:
    all_matches = []
    cursor = ""
    while True:
        pagination = {"pageSize": PAGE_SIZE}
        if cursor:
            pagination["cursor"] = cursor

        data = parry_post(
            "parrygg.services.MatchService/GetMatches",
            {
                "filter": {"event": {"id": event_id}},
                "pagination": pagination,
            },
            api_key,
        )
        matches = data.get("matches") or []
        all_matches.extend(matches)

        page_info = data.get("pagination") or {}
        if not page_info.get("hasMore"):
            break
        cursor = page_info.get("nextCursor", "")
        if not cursor:
            break

    return all_matches


def strip_sponsor(name: str) -> str:
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def format_entrant(name: str, count=None) -> str:
    """Strip each team member's sponsor tag and rejoin the team with a comma.

    ``count`` is how many users the entrant actually has, which is what keeps a
    lone player whose tag contains a separator from being read as a team -- see
    team_utils.split_entrant.
    """
    members = team_utils.split_entrant(name, count)
    cleaned = [team_utils.drop_separators(strip_sponsor(m)) for m in members]
    return team_utils.join_team(cleaned) or team_utils.drop_separators(
        strip_sponsor(name))


def build_seed_map(seeds: list) -> dict:
    """Map seed_id -> (display name, [(user_id, gamer_tag), ...]).

    ``Entrant.users`` is documented as "1 for singles, 2+ for teams", so a team
    of any size -- doubles, 3v3 -- comes back the same way and is joined with a
    comma to survive into the VOD line (see team_utils). The members are kept
    alongside the name because their order *is* the character order: the game
    data reports characters per user id, and character *i* must end up belonging
    to member *i*.
    """
    result = {}
    for seed in seeds:
        seed_id = seed.get("id") or ""
        entrant = ((seed.get("eventEntrant") or {}).get("entrant") or {})
        users = entrant.get("users") or []
        members = [((u.get("id") or "").strip(), (u.get("gamerTag") or "").strip())
                   for u in users]
        name = team_utils.join_team(tag for _, tag in members) or "?"
        if seed_id:
            result[seed_id] = (name, members)
    return result


def slug_to_name(slug: str) -> str:
    """Convert a character slug like 'ranno' or 'fleet-nixie' to 'Ranno' / 'Fleet Nixie'."""
    return slug.replace("-", " ").title()


def character_name(char_obj: dict) -> str:
    """The display name of a character entry on a match game.

    parry.gg returns the whole Character here -- ``{"name": "Ranno", "slug":
    "ranno", ...}`` -- so ``name`` is authoritative and already cased the way the
    character database spells it. Reading only ``characterSlug`` (the older,
    flatter shape this used to expect) matched nothing against the current API,
    which is why every parry line came back with empty parentheses even for a
    tournament whose organiser had reported game data. The slug is kept as a
    fallback, and title-casing it is a last resort for a name we were not given.
    """
    name = (char_obj.get("name") or "").strip()
    if name:
        return name
    slug = (char_obj.get("slug")
            or char_obj.get("characterSlug")
            or char_obj.get("character_slug") or "").strip()
    return slug_to_name(slug) if slug else ""


def get_chars_for_slot(slot_index: int, games: list, members=()) -> list:
    """Characters played in this slot, grouped per team member and in their order.

    ``members`` is what :func:`build_seed_map` recorded for the entrant --
    ``[(user_id, gamer_tag), ...]``. A singles entrant has one, so the result is
    the flat list it always was; a team of any size gets one group per member.

    Grouping matters because the characters cannot simply be pooled and
    deduplicated: two teammates on the same character would collapse to one
    entry, and a teammate counterpicking would append a character the line then
    attributes to whoever holds the last slot. ``MatchGameParticipant.user_id``
    is what ties a participant back to a member; when it is missing (older data)
    the participant's position in the slot is used instead.
    """
    groups = {}
    order = []
    for game in games:
        game_slots = game.get("slots") or []
        if slot_index >= len(game_slots):
            continue
        participants = game_slots[slot_index].get("participants") or []
        for position, participant in enumerate(participants):
            user_id = (participant.get("userId") or participant.get("user_id") or "").strip()
            key = user_id or "#%d" % position
            if key not in groups:
                groups[key] = (user_id, "", [])
                order.append(key)
            for char_obj in (participant.get("characters") or []):
                char_name = character_name(char_obj)
                if char_name:
                    groups[key][2].append(char_name)
    return team_utils.order_chars_by_member(list(members), [groups[k] for k in order])


def abbreviate_round(label: str) -> str:
    return (label
        .replace("Winners", "Wnrs")
        .replace("Losers", "Lsrs")
        .replace("Round", "Rd")
        .replace("Quarter-Final", "Qrts")
        .replace("Semi-Final", "Semi")
    )


def format_match(match_ctx: dict, tournament_name: str, game_name: str) -> Optional[str]:
    match = match_ctx.get("match") or {}
    round_obj = match_ctx.get("round") or {}
    seeds = match_ctx.get("seeds") or []

    round_label = abbreviate_round((round_obj.get("label") or "").strip())
    seed_map = build_seed_map(seeds)

    slots = match.get("slots") or []
    if len(slots) < 2:
        return None

    games = match.get("matchGames") or []

    players = []
    for i, slot in enumerate(slots[:2]):
        seed_id = slot.get("seedId") or ""
        entrant_name, members = seed_map.get(seed_id, ("?", []))
        # Entrant.users is one entry per player, so its length is authoritative
        # -- no need to infer team-ness from the punctuation in the name.
        player_name = format_entrant(entrant_name, len(members) or None)
        chars = get_chars_for_slot(i, games, members)
        char_str = ", ".join(chars) if chars else ""
        players.append(f"{player_name} ({char_str})")

    matchup = f"{players[0]} Vs {players[1]}"
    prefix = " - ".join(p for p in [tournament_name, round_label] if p)
    line = f"{prefix} - {matchup}"
    if game_name:
        line += f" - {game_name}"
    return line


def main():
    parser = argparse.ArgumentParser(
        description="Fetch parry.gg event sets and print in VOD naming format."
    )
    parser.add_argument("slug", help="Tournament custom slug, e.g. immortal-fight-night-274")
    parser.add_argument(
        "--event", "-e", default="0",
        help="Event index (0-based) or event slug to select (default: 0)",
    )
    parser.add_argument(
        "--name", "-n", default="",
        help="Tournament short name override (default: tournament name from API)",
    )
    parser.add_argument(
        "--abbrev", "-a", default="",
        help="Abbreviated tournament name. Recorded in the '# ABBREV:' header "
             f"and used by the GUI when copying a line longer than {MAX_LINE_LEN} "
             "characters; the lines themselves always spell the event out in full",
    )
    parser.add_argument(
        "--out", "-o", default="",
        help="Write output to this file instead of stdout",
    )
    parser.add_argument(
        "--props", default=PROPS_FILE,
        help=f"Path to app.properties (default: {PROPS_FILE})",
    )
    args = parser.parse_args()

    api_key = load_api_key(args.props)
    if not api_key:
        print(f"WARNING: No parrygg.api.key found in {args.props}", file=sys.stderr)
    print(f"Fetching tournament: {args.slug}", file=sys.stderr)
    tournament = get_tournament(args.slug, api_key)
    tournament_name = args.name or tournament.get("name", "")

    events = tournament.get("events") or []
    if not events:
        raise RuntimeError("Tournament has no events.")

    # Select event by index or slug
    event = None
    try:
        idx = int(args.event)
        event = events[idx]
    except (ValueError, IndexError):
        for ev in events:
            if ev.get("slug") == args.event:
                event = ev
                break
        if event is None:
            print("Available events:", file=sys.stderr)
            for i, ev in enumerate(events):
                print(f"  [{i}] {ev.get('slug')} — {(ev.get('game') or {}).get('name', '')}", file=sys.stderr)
            raise RuntimeError(f"Event not found: {args.event!r}")

    event_id = event.get("id") or ""
    game_name = (event.get("game") or {}).get("name", "")
    game_name_out = (game_name
        .replace("Rivals of Aether II", "RoA II")
        .replace("Super Smash Bros. Ultimate", "SSBU")
        .replace("Super Smash Bros. Melee", "SSBM")
    )

    print(f"Event: {event.get('slug')}  |  Game: {game_name}  |  ID: {event_id}", file=sys.stderr)
    print(f"Fetching matches...", file=sys.stderr)

    match_contexts = get_all_matches(event_id, api_key)
    print(f"Raw matches: {len(match_contexts)}", file=sys.stderr)

    lines = []
    for ctx in match_contexts:
        line = format_match(ctx, tournament_name, game_name_out)
        if line:
            lines.append(line)

    print(f"Formatted sets: {len(lines)}", file=sys.stderr)

    # Record the abbreviation as a header comment. It is what the GUI shortens
    # a copied line with, and what lets the generator recognise an abbreviated
    # line as the same event. Same contract as fetch_sets.py -- a VOD file must
    # look identical whichever provider it came from.
    header = f"# ABBREV: {args.abbrev}\n" if args.abbrev else ""

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(header + output + "\n")
        print(f"Wrote to {args.out}", file=sys.stderr)
    else:
        print(header + output)


if __name__ == "__main__":
    main()
