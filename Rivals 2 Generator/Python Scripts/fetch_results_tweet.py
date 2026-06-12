#!/usr/bin/env python3
"""
Fetch top N standings from a start.gg event and write a results post text file.

Usage:
  python fetch_results_tweet.py <event-slug> [--name "My Tournament"]
    [--platform twitter|discord]
    [--intro "Thank you to everyone who came out for {name}!"]
    [--next "June 17th"] [--link "https://start.gg/SITA"]
    [--vods "https://www.youtube.com/..."] [--top 8] [--out path.txt]
"""
import sys
import argparse
import requests
from pathlib import Path

# Force UTF-8 output so emoji characters don't crash on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

STANDINGS_QUERY_TWITTER = """
query FetchStandingsTwitter($slug: String!, $top: Int!) {
  event(slug: $slug) {
    name
    standings(query: { page: 1, perPage: $top }) {
      nodes {
        placement
        entrant {
          name
          participants {
            user {
              authorizations(types: [TWITTER]) {
                externalUsername
              }
            }
          }
        }
      }
    }
  }
}
"""

STANDINGS_QUERY_DISCORD = """
query FetchStandingsDiscord($slug: String!, $top: Int!) {
  event(slug: $slug) {
    name
    standings(query: { page: 1, perPage: $top }) {
      nodes {
        placement
        entrant {
          name
          participants {
            user {
              authorizations(types: [DISCORD]) {
                externalUsername
              }
            }
          }
        }
      }
    }
  }
}
"""

STANDINGS_QUERY_PLAIN = """
query FetchStandingsPlain($slug: String!, $top: Int!) {
  event(slug: $slug) {
    name
    standings(query: { page: 1, perPage: $top }) {
      nodes {
        placement
        entrant { name }
      }
    }
  }
}
"""

# Standard double-elim top 8: 5th/6th both show 5th, 7th/8th both show 7th.
PLACEMENT_EMOJIS = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
    4: "4️⃣",
    5: "5️⃣",
    6: "5️⃣",
    7: "7️⃣",
    8: "7️⃣",
}

PLATFORM_QUERY = {
    "twitter": ("FetchStandingsTwitter", STANDINGS_QUERY_TWITTER),
    "discord": ("FetchStandingsDiscord", STANDINGS_QUERY_DISCORD),
}


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


def fetch_standings(slug: str, top: int, platform: str) -> tuple[str, list]:
    """Fetch standings with social handles; falls back to plain names on API error."""
    op_name, query = PLATFORM_QUERY.get(platform, PLATFORM_QUERY["twitter"])
    payload = {
        "operationName": op_name,
        "variables": {"slug": slug, "top": top},
        "query": query,
    }
    try:
        out = gql_post(payload)
        ev = (out.get("data") or {}).get("event") or {}
        nodes = (ev.get("standings") or {}).get("nodes") or []
        event_name = ev.get("name", "")
        if nodes:
            return event_name, nodes
    except RuntimeError as exc:
        print(f"Warning: social query failed ({exc}), retrying without handles.", file=sys.stderr)

    # Fallback: plain standings without social handles
    payload_plain = {
        "operationName": "FetchStandingsPlain",
        "variables": {"slug": slug, "top": top},
        "query": STANDINGS_QUERY_PLAIN,
    }
    out = gql_post(payload_plain)
    ev = (out.get("data") or {}).get("event") or {}
    nodes = (ev.get("standings") or {}).get("nodes") or []
    return ev.get("name", ""), nodes


def strip_sponsor(name: str) -> str:
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def get_social_handle(entrant_node: dict, platform: str) -> str:
    """Return '@handle' if the player has linked the platform account; otherwise empty string."""
    entrant = entrant_node.get("entrant") or {}
    for participant in (entrant.get("participants") or []):
        user = participant.get("user") or {}
        for auth in (user.get("authorizations") or []):
            username = (auth.get("externalUsername") or "").strip()
            if username:
                return f"@{username}"
    return ""


def placement_emoji(rank: int) -> str:
    return PLACEMENT_EMOJIS.get(rank, f"{rank}.")


def build_post(tournament_name: str, nodes: list, platform: str,
               intro_tmpl: str, next_date: str, series_link: str, vods_link: str) -> str:
    lines = []

    intro = intro_tmpl.replace("{name}", tournament_name)
    lines.append(intro)
    lines.append("")

    nodes_sorted = sorted(nodes, key=lambda n: n.get("placement", 999))
    for node in nodes_sorted:
        rank = node.get("placement", 0)
        raw_name = (node.get("entrant") or {}).get("name") or "?"
        player = strip_sponsor(raw_name)
        handle = get_social_handle(node, platform)
        display = handle if handle else player
        emoji = placement_emoji(rank)
        lines.append(f"{emoji} {display}")

    lines.append("")
    if next_date and series_link:
        lines.append(f"The next bracket is {next_date}! {series_link}")
    elif next_date:
        lines.append(f"The next bracket is {next_date}!")
    elif series_link:
        lines.append(series_link)

    if vods_link:
        lines.append("")
        lines.append(f"Vods: {vods_link}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch start.gg standings and generate a results post."
    )
    parser.add_argument("slug", help="Event slug, e.g. tournament/my-event/event/singles")
    parser.add_argument("--name", "-n", default="", help="Tournament display name")
    parser.add_argument("--platform", default="twitter", choices=["twitter", "discord"],
                        help="Social platform to fetch handles for (default: twitter)")
    parser.add_argument(
        "--intro", default="Thank you to everyone who came out for {name}!",
        help="Intro line template ({name} is replaced with the event name)"
    )
    parser.add_argument("--next", default="", help="Next event date string, e.g. 'June 17th'")
    parser.add_argument("--link", default="", help="Series start.gg link, e.g. https://start.gg/SITA")
    parser.add_argument("--vods", default="", help="YouTube VODs playlist link")
    parser.add_argument("--top", "-t", type=int, default=8, help="Number of top placements (default: 8)")
    parser.add_argument("--out", "-o", default="", help="Output file path (default: stdout)")
    args = parser.parse_args()

    print(f"Fetching {args.platform} standings: {args.slug}", file=sys.stderr)
    event_name, nodes = fetch_standings(args.slug, args.top, args.platform)
    print(f"Found {len(nodes)} placements", file=sys.stderr)

    handle_count = sum(1 for n in nodes if get_social_handle(n, args.platform))
    print(f"{args.platform.capitalize()} handles found: {handle_count}/{len(nodes)}", file=sys.stderr)

    tournament_name = args.name or event_name
    post = build_post(tournament_name, nodes, args.platform,
                      args.intro, args.next, args.link, args.vods)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(post + "\n", encoding="utf-8")
        print(f"Wrote to {args.out}", file=sys.stderr)

    # Always print post to stdout so it appears in GUI console
    print(f"\n--- Results Post ({args.platform}) ---")
    print(post)
    print("-------------------------------")


if __name__ == "__main__":
    main()
