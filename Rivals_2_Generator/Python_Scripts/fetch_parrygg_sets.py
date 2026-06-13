#!/usr/bin/env python3
"""
Fetch completed sets from a parry.gg event and print them in the VOD naming format:
  {Tournament} {Round} - {Player1} ({Chars}) Vs {Player2} ({Chars}) - {Game}

Usage:
  python fetch_parrygg_sets.py <tournament-slug> [--event 0] [--name "My Tournament"] [--out sets.txt]

Slug example:
  immortal-fight-night-274
"""
import sys
import argparse
import requests
from pathlib import Path
from typing import Optional

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


def get_tournament(slug: str, api_key: str) -> dict:
    # Try the slug as-is first, then without any trailing hex ID (e.g. "-019c9aeb")
    slugs_to_try = [slug]
    import re
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


def build_seed_map(seeds: list) -> dict:
    """Map seed_id -> player display name."""
    result = {}
    for seed in seeds:
        seed_id = seed.get("id") or ""
        entrant = ((seed.get("eventEntrant") or {}).get("entrant") or {})
        users = entrant.get("users") or []
        name = users[0].get("gamerTag", "?").strip() if users else "?"
        if seed_id:
            result[seed_id] = name
    return result


def slug_to_name(slug: str) -> str:
    """Convert a character slug like 'ranno' or 'fleet-nixie' to 'Ranno' / 'Fleet Nixie'."""
    return slug.replace("-", " ").title()


def get_chars_for_slot(slot_index: int, games: list) -> list:
    """Collect unique characters played by the player in slot_index across all games."""
    chars = []
    for game in games:
        game_slots = game.get("slots") or []
        if slot_index >= len(game_slots):
            continue
        participants = game_slots[slot_index].get("participants") or []
        for participant in participants:
            for char_obj in (participant.get("characters") or []):
                # API returns characterSlug (camelCase) per proto CharacterSelection
                slug = char_obj.get("characterSlug") or char_obj.get("character_slug") or ""
                char_name = slug_to_name(slug) if slug else ""
                if char_name and char_name not in chars:
                    chars.append(char_name)
    return chars


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
        player_name = strip_sponsor(seed_map.get(seed_id, "?"))
        chars = get_chars_for_slot(i, games)
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

    if not api_key:
        print("WARNING: No parrygg.api.key found in app.properties", file=sys.stderr)
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

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Wrote to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
