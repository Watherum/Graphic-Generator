#!/usr/bin/env python3
"""
Fetch top N standings from a start.gg event and write a Top 8 HTML txt file.

Usage:
  python fetch_top8.py <event-slug> [--name "My Tournament"] [--link "https://start.gg/..."] [--top 8] [--out path.txt]

Slug examples:
  tournament/ultimate-immortal-fight-night-274/event/ultimate-singles
"""
import sys
import argparse
import requests
from collections import Counter
from datetime import datetime, timezone

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

STANDINGS_QUERY = """
query FetchStandings($slug: String!, $top: Int!) {
  event(slug: $slug) {
    name
    startAt
    numEntrants
    standings(query: { page: 1, perPage: $top }) {
      nodes {
        placement
        entrant { name }
      }
    }
  }
}
"""

SETS_QUERY = """
query FetchSets($slug: String!, $page: Int!) {
  event(slug: $slug) {
    sets(page: $page, perPage: 50, sortType: RECENT) {
      pageInfo { totalPages }
      nodes {
        slots {
          entrant { name }
        }
        games {
          selections {
            entrant { name }
            character { name }
          }
        }
      }
    }
  }
}
"""


def gql_post(payload: dict) -> dict:
    for attempt in range(5):
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            out = r.json()
            if out.get("errors"):
                raise RuntimeError("GraphQL error: " + str(out["errors"]))
            return out
        if attempt == 4:
            raise RuntimeError(f"Request failed (HTTP {r.status_code})")
    return {}


def fetch_standings(slug: str, top: int) -> tuple[dict, list]:
    payload = {
        "operationName": "FetchStandings",
        "variables": {"slug": slug, "top": top},
        "query": STANDINGS_QUERY,
    }
    out = gql_post(payload)
    ev = (out.get("data") or {}).get("event") or {}
    event_info = {
        "name": ev.get("name", ""),
        "startAt": ev.get("startAt"),
        "numEntrants": ev.get("numEntrants", 0),
    }
    nodes = (ev.get("standings") or {}).get("nodes") or []
    return event_info, nodes


def fetch_all_sets(slug: str) -> list:
    all_nodes = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        payload = {
            "operationName": "FetchSets",
            "variables": {"slug": slug, "page": page},
            "query": SETS_QUERY,
        }
        out = gql_post(payload)
        ev = (out.get("data") or {}).get("event") or {}
        sets_block = ev.get("sets") or {}
        total_pages = (sets_block.get("pageInfo") or {}).get("totalPages") or 1
        all_nodes.extend(sets_block.get("nodes") or [])
        page += 1
    return all_nodes


def strip_sponsor(name: str) -> str:
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def parse_sponsor(name: str) -> str:
    if " | " in name:
        return name.split(" | ", 1)[0].strip()
    return ""


def build_char_counts(sets: list) -> dict:
    """Return {entrant_name: Counter of character names} across all sets."""
    counts = {}
    for s in sets:
        for game in (s.get("games") or []):
            for sel in (game.get("selections") or []):
                entrant_name = (sel.get("entrant") or {}).get("name") or ""
                char_name = (sel.get("character") or {}).get("name") or ""
                if entrant_name and char_name:
                    if entrant_name not in counts:
                        counts[entrant_name] = Counter()
                    counts[entrant_name][char_name] += 1
    return counts


def format_date(start_at) -> str:
    if not start_at:
        return ""
    try:
        dt = datetime.fromtimestamp(float(start_at), tz=timezone.utc)
        return f"{dt.month}/{dt.day}/{dt.year}"
    except Exception:
        return str(start_at)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch start.gg top N standings and write a Top 8 HTML txt file."
    )
    parser.add_argument("slug", help="Event slug, e.g. tournament/my-event/event/singles")
    parser.add_argument("--name", "-n", default="", help="Tournament display name")
    parser.add_argument("--link", "-l", default="", help="Event link (e.g. https://start.gg/UIFN274)")
    parser.add_argument("--top", "-t", type=int, default=8, help="Number of top placements to include (default: 8)")
    parser.add_argument("--out", "-o", default="", help="Output file path (default: stdout)")
    args = parser.parse_args()

    print(f"Fetching standings: {args.slug}", file=sys.stderr)
    event_info, standing_nodes = fetch_standings(args.slug, args.top)
    print(f"Found {len(standing_nodes)} placements", file=sys.stderr)

    print("Fetching sets for character data...", file=sys.stderr)
    sets = fetch_all_sets(args.slug)
    print(f"Fetched {len(sets)} sets", file=sys.stderr)

    char_counts = build_char_counts(sets)

    tournament_name = args.name or event_info.get("name", "")
    num_entrants = event_info.get("numEntrants", 0)
    date_str = format_date(event_info.get("startAt"))

    lines = []
    lines.append("# Top 8 Graphic example")
    lines.append("# All information is tab deliminated")
    lines.append("")
    lines.append("#Graphic Information")
    lines.append(f"Event name:\t{tournament_name}")
    lines.append(f"Event link: {args.link}")
    lines.append(f"Event entrants:\t{num_entrants} Competitors")
    lines.append(f"Event date:\t{date_str}")
    lines.append("")
    lines.append("# Placements")
    lines.append("# place, name, sponsor, characters")

    for node in standing_nodes:
        placement = node.get("placement", "?")
        entrant_name = (node.get("entrant") or {}).get("name") or "?"
        player = strip_sponsor(entrant_name)
        sponsor = parse_sponsor(entrant_name)
        counter = char_counts.get(entrant_name, Counter())
        char = counter.most_common(1)[0][0] if counter else ""
        lines.append(f"{placement},{player},{sponsor},{char}")

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Wrote to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
