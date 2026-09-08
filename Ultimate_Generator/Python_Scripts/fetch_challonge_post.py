#!/usr/bin/env python3
"""
Write a results post for a Challonge tournament.

Usage:
  python fetch_challonge_post.py <tournament-slug> [--name "My Tournament"]
    [--intro "..."] [--next "June 17th"] [--link "https://..."]
    [--vods "https://youtube..."] [--top 8] [--out path.txt]

Challonge has no social accounts of any kind -- no Twitter, no Discord, not
even a user object to hang them on; a participant is a name string typed by the
organiser. So there is nothing to fetch per platform and no --platform flag:
this always writes the generic post, emoji placements against plain tags. That
is the whole difference from the other two providers.

Standings come from ``final_rank``, which Challonge fills in only once the
bracket is **finalized**. An un-finalized tournament has no standings at all
and is reported as such rather than guessed at.
"""
import sys
import argparse

from challonge_api import (
    attrs, get_participants, get_tournament, load_credentials,
    missing_credentials_message, normalize_slug, resource_id, warn,
)
from fetch_challonge_top8 import collect_placements
import results_post

results_post.force_utf8_stdout()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Challonge standings and generate a results post.")
    parser.add_argument("slug", help="Tournament slug, e.g. my-weekly-42 "
                                     "(or the challonge.com URL)")
    results_post.add_common_args(parser)
    parser.add_argument("--props", default=None,
                        help="Path to app.properties")
    args = parser.parse_args()

    from challonge_api import PROPS_FILE
    props = args.props or PROPS_FILE

    creds = load_credentials(props)
    if not creds:
        warn("ERROR: " + missing_credentials_message(props))
        return 1

    slug = normalize_slug(args.slug)
    warn(f"Fetching tournament: {slug}")
    tournament = get_tournament(slug, creds)
    t_attrs = attrs(tournament)
    tournament_id = resource_id(tournament) or slug
    name = args.name or (t_attrs.get("name") or "").strip()

    participants = get_participants(tournament_id, creds)
    placements = collect_placements(participants, args.top)

    if not placements:
        state = (t_attrs.get("state") or "").strip()
        warn(f"ERROR: no standings -- no participant has a final_rank "
             f"(tournament state: {state or 'unknown'}). Challonge only fills "
             f"those in once the bracket is finalized; finalize it on "
             f"challonge.com and fetch again.")
        return 1

    warn(f"Found {len(placements)} placements")
    warn("NOTE: Challonge has no social accounts, so this post lists plain "
         "tags. Add handles by hand if you want them.")

    entries = [(rank, tag) for rank, tag, _sponsor in placements]
    post = results_post.build_post(name, entries, args.intro, args.next,
                                   args.link, args.vods)
    results_post.emit(post, args.out, "generic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
