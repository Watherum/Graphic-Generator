#!/usr/bin/env python3
"""
Write a results post for a parry.gg event, with social handles.

Usage:
  python fetch_parrygg_post.py <tournament-slug> [--event 0]
    [--platform twitter|discord] [--name "My Tournament"] [--intro "..."]
    [--next "June 17th"] [--link "https://..."] [--vods "..."]
    [--top 8] [--out path.txt] [--debug]

Where the handles come from
---------------------------
A parry.gg User carries a ``linkedAccounts`` list, and the placements response
already embeds it -- so no extra call per player is needed. Two providers exist
in practice, and only two:

* ``LINKED_ACCOUNT_PROVIDER_DISCORD`` -- ``username`` is the handle directly.
* ``LINKED_ACCOUNT_PROVIDER_STARTGG`` -- carries the player's start.gg ``slug``
  ("user/12e1b7a2").

There is **no Twitter provider on parry.gg**, which is why a Twitter post is not
simply the Discord path with a different key. It is reached by *bridging*: the
start.gg linked account gives a user slug, and start.gg's own ``authorizations``
query turns that slug into the Twitter handle -- the same query
``fetch_results_tweet.py`` already uses, so the handles match what a start.gg
fetch of the same player would produce. A player who linked neither start.gg nor
a Twitter account on start.gg falls back to their plain tag.

The bridge costs one start.gg request for the whole post (the slugs are batched
into a single aliased query), and start.gg needs no API key for it.
"""
import sys
import json
import argparse

import requests

from fetch_parrygg_top8 import (
    PROPS_FILE, REQUEST_TIMEOUT, bracket_ids_from_event, get_bracket_placements,
    get_tournament, load_api_key, normalize_slug,
)
import results_post

results_post.force_utf8_stdout()

STARTGG_API_URL = "https://www.start.gg/api/-/gql"
STARTGG_HEADERS = {
    "Content-Type": "application/json",
    "client-version": "20",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    ),
}

DISCORD_PROVIDER = "LINKED_ACCOUNT_PROVIDER_DISCORD"
STARTGG_PROVIDER = "LINKED_ACCOUNT_PROVIDER_STARTGG"


def warn(message: str) -> None:
    print(message, file=sys.stderr)


def linked_accounts(user: dict) -> list:
    return user.get("linkedAccounts") or []


def account_of(user: dict, provider: str) -> dict:
    for acc in linked_accounts(user):
        if (acc.get("provider") or "") == provider:
            return acc
    return {}


def placement_users(placement: dict) -> list:
    """The User objects behind a placement (several for a doubles team)."""
    entrant = (placement.get("eventEntrant") or {}).get("entrant") or {}
    return entrant.get("users") or []


def entrant_tag(placement: dict) -> str:
    """The entrant's display name -- the gamer tags of everyone on it."""
    tags = [(u.get("gamerTag") or "").strip() for u in placement_users(placement)]
    tags = [t for t in tags if t]
    # Matches how a doubles entrant is written everywhere else in the project.
    return ",".join(tags) if tags else "?"


def startgg_twitter_handles(slugs: list) -> dict:
    """``{start.gg user slug: "handle"}`` for the slugs that have one.

    One aliased query for every slug at once: a post is at most a handful of
    players, and a request per player would be needlessly slow and rude.
    """
    slugs = [s for s in slugs if s]
    if not slugs:
        return {}
    parts, variables = [], {}
    for i, slug in enumerate(slugs):
        parts.append("u%d: user(slug: $s%d) { authorizations(types: [TWITTER])"
                     " { externalUsername } }" % (i, i))
        variables["s%d" % i] = slug
    arg_defs = ", ".join("$s%d: String!" % i for i in range(len(slugs)))
    query = "query BridgeTwitter(%s) { %s }" % (arg_defs, " ".join(parts))
    try:
        r = requests.post(STARTGG_API_URL,
                          json={"query": query, "variables": variables},
                          headers=STARTGG_HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            warn("Warning: start.gg bridge failed (HTTP %d); falling back to "
                 "plain tags." % r.status_code)
            return {}
        data = (r.json() or {}).get("data") or {}
    except (requests.RequestException, ValueError) as exc:
        warn("Warning: start.gg bridge failed (%s); falling back to plain tags."
             % exc)
        return {}

    out = {}
    for i, slug in enumerate(slugs):
        node = data.get("u%d" % i) or {}
        for auth in (node.get("authorizations") or []):
            handle = (auth.get("externalUsername") or "").strip()
            if handle:
                out[slug] = handle
                break
    return out


def resolve_displays(placements: list, platform: str) -> list:
    """``[(rank, display), ...]``, a handle where one exists, else the tag."""
    handles_by_slug = {}
    if platform == "twitter":
        # Collect every start.gg slug first so the bridge is one request.
        slugs = []
        for p in placements:
            for u in placement_users(p):
                slug = account_of(u, STARTGG_PROVIDER).get("slug") or ""
                if slug:
                    slugs.append(slug)
        handles_by_slug = startgg_twitter_handles(slugs)

    entries, found = [], 0
    for p in placements:
        rank = p.get("placement") or 0
        handle = ""
        for u in placement_users(p):
            if platform == "discord":
                handle = (account_of(u, DISCORD_PROVIDER).get("username") or "").strip()
            else:
                slug = account_of(u, STARTGG_PROVIDER).get("slug") or ""
                handle = handles_by_slug.get(slug, "")
            if handle:
                break
        if handle:
            found += 1
            entries.append((rank, "@" + handle))
        else:
            entries.append((rank, entrant_tag(p)))
    warn("%s handles found: %d/%d" % (platform.capitalize(), found, len(placements)))
    return entries


def pick_event(events: list, wanted: str):
    """The event named by ``--event``: a 0-based index, or an event slug."""
    try:
        index = int(wanted)
    except (ValueError, TypeError):
        return next((e for e in events if e.get("slug") == wanted), None)
    if 0 <= index < len(events):
        return events[index]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch parry.gg standings and generate a results post.")
    parser.add_argument("slug", help="Tournament slug, e.g. my-weekly-019c9aeb "
                                     "(or the parry.gg URL)")
    parser.add_argument("--event", default="0",
                        help="Event within the tournament: 0-based index, or "
                             "an event slug (default: 0)")
    parser.add_argument("--platform", default="twitter",
                        choices=["twitter", "discord"],
                        help="Social platform to resolve handles for")
    results_post.add_common_args(parser)
    parser.add_argument("--props", default=PROPS_FILE,
                        help="Path to app.properties")
    parser.add_argument("--debug", action="store_true",
                        help="Dump the first placement, to check the shape")
    args = parser.parse_args()

    api_key = load_api_key(args.props)
    if not api_key:
        warn("ERROR: no parrygg.api.key in %s" % args.props)
        return 1

    slug = normalize_slug(args.slug)
    warn("Fetching %s standings: %s" % (args.platform, slug))
    tournament = get_tournament(slug, api_key)
    events = tournament.get("events") or []
    if not events:
        warn("ERROR: tournament has no events")
        return 1

    event = pick_event(events, args.event)
    if event is None:
        warn("ERROR: no event matching %r (tournament has %d)"
             % (args.event, len(events)))
        return 1

    placements = []
    for bracket_id in bracket_ids_from_event(event):
        placements = get_bracket_placements(bracket_id, api_key) or []
        if placements:
            break

    if not placements:
        warn("ERROR: no standings returned for this event -- the bracket may "
             "not be finished.")
        return 1

    if args.debug:
        warn("--- first placement ---")
        warn(json.dumps(placements[0], indent=2)[:2000])

    placements = sorted(placements, key=lambda p: p.get("placement") or 999)
    placements = placements[:args.top]
    warn("Found %d placements" % len(placements))

    name = args.name or (tournament.get("name") or "").strip()
    entries = resolve_displays(placements, args.platform)
    post = results_post.build_post(name, entries, args.intro, args.next,
                                   args.link, args.vods)
    results_post.emit(post, args.out, args.platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
