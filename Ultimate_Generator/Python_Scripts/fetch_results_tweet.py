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

import results_post
from results_post import strip_sponsor

results_post.force_utf8_stdout()

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


def build_post(tournament_name: str, nodes: list, platform: str,
               intro_tmpl: str, next_date: str, series_link: str,
               vods_link: str) -> str:
    """Adapt start.gg standings nodes to the shared post builder."""
    entries = []
    for node in nodes:
        raw_name = (node.get("entrant") or {}).get("name") or "?"
        handle = get_social_handle(node, platform)
        entries.append((node.get("placement", 0),
                        handle if handle else strip_sponsor(raw_name)))
    return results_post.build_post(tournament_name, entries, intro_tmpl,
                                   next_date, series_link, vods_link)


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

    results_post.emit(post, args.out, args.platform)


if __name__ == "__main__":
    main()
