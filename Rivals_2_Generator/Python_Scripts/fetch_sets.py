#!/usr/bin/env python3
"""
Fetch completed sets from a start.gg event and print them in the VOD naming format:
  {Tournament} {Round} - {Player1} ({Chars}) Vs {Player2} ({Chars}) - {Game}

Usage:
  python fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

Slug examples:
  tournament/my-tournament-name/event/singles
"""
import sys
import argparse
import requests
from typing import Optional

import team_utils

API_URL = "https://www.start.gg/api/-/gql"
REQUEST_TIMEOUT = 20.0
HEADERS = {
    "Content-Type": "application/json",
    "client-version": "20",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    ),
}

QUERY = """
query FetchSets($slug: String!, $page: Int!) {
  event(slug: $slug) {
    name
    videogame { name }
    sets(page: $page, perPage: 50, sortType: RECENT) {
      pageInfo { totalPages }
      nodes {
        id
        startedAt
        completedAt
        fullRoundText
        phaseGroup { bracketType }
        station { number }
        slots {
          entrant { name }
        }
        games {
          selections {
            entrant { id name }
            character { name }
          }
        }
      }
    }
  }
}
"""


def fetch_all_sets(slug: str) -> tuple[dict, list]:
    all_nodes = []
    event_info = {}
    page = 1
    total_pages = 1

    while page <= total_pages:
        payload = {
            "operationName": "FetchSets",
            "variables": {"slug": slug, "page": page},
            "query": QUERY,
        }
        for attempt in range(5):
            r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                if attempt == 4:
                    raise RuntimeError(f"Request failed (HTTP {r.status_code})")
                continue
            out = r.json()
            if out.get("errors"):
                raise RuntimeError("GraphQL error: " + str(out["errors"]))
            ev = (out.get("data") or {}).get("event")
            if not ev:
                raise RuntimeError("Event not found — check your slug.")
            if not event_info:
                event_info = {
                    "name": ev.get("name", ""),
                    "game": (ev.get("videogame") or {}).get("name", ""),
                }
            sets_block = ev.get("sets") or {}
            total_pages = (sets_block.get("pageInfo") or {}).get("totalPages") or 1
            all_nodes.extend(sets_block.get("nodes") or [])
            break
        page += 1

    return event_info, all_nodes


def strip_sponsor(name: str) -> str:
    """Remove sponsor tag prefix e.g. 'Sponsor | Player' -> 'Player'."""
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def format_entrant(name: str) -> str:
    """Clean up an entrant name, singles or doubles.

    start.gg writes a doubles entrant as "Sponsor | shane / Other | pizza": the
    members are slash separated and each carries its own sponsor tag. Every
    member is stripped, and the team is rejoined with a comma -- a slash cannot
    be part of the thumbnail filename the title turns into.
    """
    return team_utils.join_team(
        strip_sponsor(member) for member in team_utils.split_team(name)
    ) or strip_sponsor(name)


def build_entrant_characters(games: list) -> dict[str, list[str]]:
    """Collect unique characters per entrant across all games, in first-appearance order."""
    entrant_chars: dict[str, list[str]] = {}
    for game in games:
        for sel in (game.get("selections") or []):
            entrant = (sel.get("entrant") or {}).get("name") or "?"
            char = (sel.get("character") or {}).get("name") or "?"
            if entrant not in entrant_chars:
                entrant_chars[entrant] = []
            if char not in entrant_chars[entrant]:
                entrant_chars[entrant].append(char)
    return entrant_chars


MAX_LINE_LEN = 100


def format_set(set_node: dict, tournament_name: str, game_name: str) -> Optional[str]:
    games = set_node.get("games") or []
    entrant_chars = build_entrant_characters(games)

    if len(entrant_chars) >= 2:
        entrants = list(entrant_chars.keys())
        p1 = f"{format_entrant(entrants[0])} ({', '.join(entrant_chars[entrants[0]])})"
        p2 = f"{format_entrant(entrants[1])} ({', '.join(entrant_chars[entrants[1]])})"
    else:
        # Fall back to slot entrant names when game data is absent
        slots = [
            (s.get("entrant") or {}).get("name")
            for s in (set_node.get("slots") or [])
            if (s.get("entrant") or {}).get("name")
        ]
        if len(slots) < 2:
            return None
        p1 = f"{format_entrant(slots[0])} ()"
        p2 = f"{format_entrant(slots[1])} ()"

    matchup = f"{p1} Vs {p2}"

    bracket_type = ((set_node.get("phaseGroup") or {}).get("bracketType") or "")
    if bracket_type == "ROUND_ROBIN":
        round_text = "Rnd Rbn"
    else:
        round_text = (set_node.get("fullRoundText") or "").strip()
        round_text = (round_text
            .replace("Winners", "Wnrs")
            .replace("Losers", "Lsrs")
            .replace("Round", "Rd")
            .replace("Quarter-Final", "Qrts")
            .replace("Semi-Final", "Semi")
        )

    # Always the full tournament name. The abbreviation is a *publishing*
    # step, applied by the GUI's Copy button to a line that would otherwise
    # exceed MAX_LINE_LEN; writing it into the file instead left the editor
    # showing shortened lines that could not be read back to the full name, and
    # mixed two spellings of one event within a single file. The abbreviation
    # still reaches the GUI and the generator through the '# ABBREV:' header.
    prefix = " - ".join(p for p in [tournament_name, round_text] if p)
    line = f"{prefix} - {matchup}"
    if game_name:
        line += f" - {game_name}"
    return line


def main():
    parser = argparse.ArgumentParser(
        description="Fetch start.gg event sets and print in VOD naming format."
    )
    parser.add_argument("slug", help="Event slug, e.g. tournament/my-event/event/singles")
    parser.add_argument(
        "--name", "-n", default="",
        help="Tournament short name (default: event name from API)",
    )
    parser.add_argument(
        "--abbrev", "-a", default="",
        help="Abbreviated tournament name. Recorded in the '# ABBREV:' header "
             f"and used by the GUI when copying a line longer than {MAX_LINE_LEN} "
             "characters; the lines themselves always spell the event out in full",
    )
    parser.add_argument(
        "--station", "-s", type=int, default=None,
        help="Only include sets played on this station number",
    )
    parser.add_argument(
        "--out", "-o", default="",
        help="Write output to this file instead of stdout",
    )
    args = parser.parse_args()

    print(f"Fetching: {args.slug}", file=sys.stderr)
    event_info, nodes = fetch_all_sets(args.slug)

    tournament_name = args.name or event_info.get("name", "")
    game_name = event_info.get("game", "")

    print(
        f"Event : {event_info.get('name')}  |  Game: {game_name}  |  Raw sets: {len(nodes)}",
        file=sys.stderr,
    )

    if args.station is not None:
        nodes = [n for n in nodes if (n.get("station") or {}).get("number") == args.station]
        print(f"After station filter: {len(nodes)}", file=sys.stderr)

    def sort_key(n):
        v = n.get("startedAt")
        if not v:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            from datetime import datetime, timezone
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    nodes.sort(key=sort_key)

    game_name_out = (game_name
        .replace("Rivals of Aether II", "RoA II")
        .replace("Super Smash Bros. Ultimate", "SSBU")
        .replace("Super Smash Bros. Melee", "SSBM")
    )

    lines = []
    for node in nodes:
        line = format_set(node, tournament_name, game_name_out)
        if line:
            lines.append(line)

    print(f"Formatted sets: {len(lines)}", file=sys.stderr)

    # Record the abbreviation as a header comment. It is what the GUI shortens
    # a copied line with, and what lets the generator recognise an abbreviated
    # line (hand-written, or from an older fetch) as the same event.
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
