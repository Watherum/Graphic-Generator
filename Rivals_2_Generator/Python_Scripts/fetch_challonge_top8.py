#!/usr/bin/env python3
"""
Fetch top N standings from a Challonge tournament and write a Top 8 HTML txt
file, in the same format as fetch_startgg_top8.py and fetch_parrygg_top8.py.

Usage:
  python fetch_challonge_top8.py <tournament-slug> [--name "My Tournament"]
      [--link "https://challonge.com/..."] [--top 8] [--out path.txt] [--debug]

Standings come from each participant's ``final_rank``, which Challonge fills in
once the bracket is finalized. That is authoritative, so this needs none of the
bracket-walking guesswork the parry.gg fetcher required -- but it also means an
unfinished (or un-finalized) tournament has no standings at all, which is
reported rather than guessed at.

Characters come from Player_database.csv, because Challonge has no game model
and reports none. Set them per line on the Top 8 tab, where the Character/Skin
pickers copy a "Character:Skin" token ready to paste.
"""
import sys
import json
import argparse
from pathlib import Path

from challonge_api import (
    attrs, get_participants, get_tournament, load_credentials,
    missing_credentials_message, normalize_slug, participant_name,
    resource_id, warn, PROPS_FILE,
)
import team_utils

_SCRIPT_DIR = Path(__file__).resolve().parent
PLAYER_DB_PATH = str(_SCRIPT_DIR.parent / "Resources" / "Player_database.csv")


def load_player_db(path: str) -> dict:
    """``{tag_lower: main character}`` from Player_database.csv."""
    result = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    tag = parts[0].strip().lower()
                    char = parts[1].strip().lstrip("*")
                    if tag and char:
                        result[tag] = char
    except FileNotFoundError:
        pass
    return result


def split_sponsor(name: str) -> tuple:
    """``"NG | Azul"`` -> ``("Azul", "NG")``; an unsponsored tag -> ``(tag, "")``."""
    if " | " in name:
        sponsor, _, tag = name.partition(" | ")
        return tag.strip(), sponsor.strip()
    return name.strip(), ""


def clean_tag(tag: str) -> str:
    """Strip separators out of a Top 8 name.

    The Top 8 data files are **comma separated**, so a comma in a name would
    silently shift every field after it -- which is exactly why doubles is not
    supported on these files (see CLAUDE.md). A slash is dropped for the same
    reason it is in a VOD line.
    """
    return team_utils.drop_separators(tag)


def format_date(value) -> str:
    """M/D/YYYY from an ISO 8601 string or a unix timestamp, or "".

    Challonge sends ISO 8601 with an offset ("2026-09-06T00:30:00-05:00"), but
    the field it arrives in has moved between API versions, so this accepts
    either form -- and treats the epoch as "no date", since printing 1/1/1970 on
    a Top 8 graphic is worse than printing nothing.
    """
    if not value:
        return ""
    from datetime import datetime, timezone
    dt = None
    try:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError):
        text = str(value).strip().replace("Z", "+00:00")
        for candidate in (text, text[:10]):
            try:
                dt = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
    if dt is None or dt.year <= 1970:
        return ""
    return f"{dt.month}/{dt.day}/{dt.year}"


def tournament_date(t_attrs: dict) -> str:
    """The tournament's date, from whichever field carries it.

    v1 used flat ``started_at``/``start_at``; v2.1 groups them under
    ``timestamps``. Both are checked, started-at first, because a tournament
    that ran is dated by when it ran rather than by when it was scheduled.
    """
    stamps = t_attrs.get("timestamps")
    bags = [t_attrs, stamps if isinstance(stamps, dict) else {}]
    for key in ("started_at", "starts_at", "start_at", "completed_at",
                "created_at"):
        for bag in bags:
            value = bag.get(key)
            if value:
                formatted = format_date(value)
                if formatted:
                    return formatted
    return ""


def collect_placements(participants: list, top: int) -> list:
    """``[(place, tag, sponsor), ...]`` sorted best first, from ``final_rank``.

    Challonge fills ``final_rank`` in when the bracket is finalized and shares
    it across tied placements (5,5,7,7), so the list is truncated at ``top``
    entries rather than at rank ``top`` -- a bracket with four 5th places would
    otherwise print nine rows for a top 8.
    """
    rows = []
    for p in participants:
        bag = attrs(p)
        rank = bag.get("final_rank")
        if rank is None:
            continue
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            continue
        raw = participant_name(p)
        if not raw:
            continue
        tag, sponsor = split_sponsor(raw)
        rows.append((rank, clean_tag(tag), sponsor, bag.get("seed") or 0))
    # Seed breaks a tie so the order is stable between runs; Challonge lists
    # participants in whatever order it likes.
    rows.sort(key=lambda r: (r[0], r[3]))
    return [(rank, tag, sponsor) for rank, tag, sponsor, _ in rows[:top]]


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Challonge standings and write a Top 8 data file.")
    parser.add_argument("slug", help="Tournament slug, e.g. my-weekly-42 "
                                     "(or the challonge.com URL)")
    parser.add_argument("--name", "-n", default="",
                        help="Tournament display name override")
    parser.add_argument("--link", "-l", default="",
                        help="Event link URL for the graphic")
    parser.add_argument("--top", "-t", type=int, default=8,
                        help="How many placements to write (default: 8)")
    parser.add_argument("--out", "-o", default="",
                        help="Output file path (default: stdout)")
    parser.add_argument("--props", default=PROPS_FILE,
                        help=f"Path to app.properties (default: {PROPS_FILE})")
    parser.add_argument("--player-db", default=PLAYER_DB_PATH,
                        help="Player_database.csv, used for the character "
                             "column Challonge cannot supply")
    parser.add_argument("--debug", action="store_true",
                        help="Dump the raw tournament and first participant, "
                             "to check the API's response shape")
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
    state = (t_attrs.get("state") or "").strip()

    participants = get_participants(tournament_id, creds)
    if args.debug:
        warn("--- tournament ---")
        warn(json.dumps(tournament, indent=2)[:2000])
        if participants:
            warn("--- first participant ---")
            warn(json.dumps(participants[0], indent=2)[:2000])

    num_entrants = t_attrs.get("participants_count") or len(participants)
    date_str = tournament_date(t_attrs)
    placements = collect_placements(participants, args.top)

    if not placements:
        warn(f"WARNING: no final_rank on any participant (tournament state: "
             f"{state or 'unknown'}). Challonge only fills placements in once "
             f"the bracket is finalized -- finalize it on Challonge and fetch "
             f"again.")
    else:
        for place, tag, sponsor in placements:
            warn(f"  Place {place}: {tag}" + (f"  [{sponsor}]" if sponsor else ""))

    player_db = load_player_db(args.player_db)

    lines = [
        "# Top 8 Graphic example",
        "# All information is tab deliminated",
        "",
        "#Graphic Information",
        f"Event name:\t{tournament_name}",
        f"Event link: {args.link}",
        f"Event entrants:\t{num_entrants or '?'} Competitors",
        f"Event date:\t{date_str}",
        "",
        "# Placements",
        "# place, name, sponsor, characters",
    ]
    missing_chars = 0
    for place, tag, sponsor in placements:
        char = player_db.get(tag.lower(), "")
        if not char:
            missing_chars += 1
        lines.append(f"{place},{tag},{sponsor},{char}")

    if missing_chars:
        warn(f"NOTE: {missing_chars} placement(s) have no character -- Challonge "
             f"reports none, and these players are not in Player_database.csv. "
             f"Set them on the Top 8 tab.")

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        warn(f"Wrote to {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
