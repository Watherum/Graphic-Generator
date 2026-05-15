#!/usr/bin/env python3
"""
Fetch top N standings from a parry.gg event and write a Top 8 HTML txt file.

Usage:
  python fetch_parrygg_top8.py <tournament-slug> [--event 0] [--name "My Tournament"]
      [--link "https://parry.gg/..."] [--top 8] [--out path.txt] [--debug]

Slug example:
  immortal-fight-night-274
  al-rivals-2-4-2-2026-019d4e84

Winner/loser detection: parry.gg Slot.placement == 1 means winner within that match
(there is no winningSeedId field on Match per the API proto docs).
"""
import sys
import re
import json
import argparse
import requests
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

BASE_URL = "https://grpcweb.parry.gg"
REQUEST_TIMEOUT = 20.0
PAGE_SIZE = 50

_SCRIPT_DIR = Path(__file__).resolve().parent
PROPS_FILE = str(_SCRIPT_DIR.parent.parent / "app.properties")
PLAYER_DB_PATH = str(_SCRIPT_DIR.parent / "Resources" / "Player_database.csv")

DEFAULT_BRACKET_SLUG = "main"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

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


def parry_post(endpoint: str, body: dict, api_key: str) -> Optional[dict]:
    url = f"{BASE_URL}/{endpoint}"
    headers = {"Content-Type": "application/json", "X-API-KEY": api_key}
    for attempt in range(5):
        r = requests.post(url, json=body, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (404, 405, 501):
            return None
        if attempt == 4:
            raise RuntimeError(f"Request to {endpoint} failed (HTTP {r.status_code}): {r.text[:200]}")
    return None


def parry_post_required(endpoint: str, body: dict, api_key: str) -> dict:
    result = parry_post(endpoint, body, api_key)
    if result is None:
        raise RuntimeError(f"Endpoint not available: {endpoint}")
    return result


def get_tournament(slug: str, api_key: str) -> dict:
    slugs_to_try = [slug]
    stripped = re.sub(r"-[0-9a-f]{8}$", "", slug)
    if stripped != slug:
        slugs_to_try.append(stripped)

    for attempt_slug in slugs_to_try:
        data = parry_post_required(
            "parrygg.services.TournamentService/GetTournaments",
            {"filter": {"custom_slug": attempt_slug}},
            api_key,
        )
        tournaments = data.get("tournaments") or []
        if tournaments:
            return tournaments[0]

    name_guess = re.sub(r"-[0-9a-f]{8}$", "", slug).replace("-", " ").title()
    print(f"Slug lookup failed — trying name search: {name_guess!r}", file=sys.stderr)
    data = parry_post_required(
        "parrygg.services.TournamentService/GetTournaments",
        {"filter": {"name": name_guess}},
        api_key,
    )
    tournaments = data.get("tournaments") or []
    if tournaments:
        return tournaments[0]

    raise RuntimeError(
        f"No tournament found for slug: {slug!r}\n"
        "Check the slug in the parry.gg URL (the part after https://parry.gg/)"
    )


def get_all_matches(event_id: str, api_key: str) -> list:
    all_matches = []
    cursor = ""
    while True:
        pagination = {"pageSize": PAGE_SIZE}
        if cursor:
            pagination["cursor"] = cursor
        data = parry_post_required(
            "parrygg.services.MatchService/GetMatches",
            {"filter": {"event": {"id": event_id}}, "pagination": pagination},
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


def get_bracket_id(tournament_slug: str, bracket_slug: str, api_key: str) -> Optional[str]:
    """Return bracket UUID by slug, or None if lookup fails."""
    data = parry_post(
        "parrygg.services.BracketService/GetBracket",
        {"slugId": {
            "tournamentSlug": tournament_slug,
            "bracketSlug": bracket_slug,
        }},
        api_key,
    )
    if data is None:
        return None
    bracket = data.get("bracket") or {}
    return bracket.get("id") or None


def get_bracket_placements(bracket_id: str, api_key: str) -> Optional[list]:
    """Call BracketService/GetBracketPlacements. Returns raw placements list or None."""
    data = parry_post(
        "parrygg.services.BracketService/GetBracketPlacements",
        {"id": bracket_id},
        api_key,
    )
    if data is None:
        return None
    return data.get("placements") or None


# ---------------------------------------------------------------------------
# Seed / player data extraction
# ---------------------------------------------------------------------------

def extract_seed_info(seed: dict) -> tuple:
    """Return (gamer_tag, sponsor_name) from a Seed object.

    Tries in order:
      1. seed.eventEntrant.entrant.users[0].gamerTag  (User.gamer_tag, primary)
      2. seed.eventEntrant.name                        (EventEntrant display name, fallback)
    Sponsor from seed.eventEntrant.entrant.users[0].sponsorName (User.sponsor_name).
    """
    event_entrant = seed.get("eventEntrant") or {}
    entrant = event_entrant.get("entrant") or {}
    users = entrant.get("users") or []

    tag = ""
    sponsor = ""

    if users:
        user = users[0]
        tag = (user.get("gamerTag") or user.get("gamer_tag") or "").strip()
        sponsor = (user.get("sponsorName") or user.get("sponsor_name") or "").strip()

    # Fallback: EventEntrant.name is the display name for this entrant in the event
    if not tag:
        tag = (event_entrant.get("name") or "").strip()

    return (tag or "?", sponsor)


def build_seed_map(match_contexts: list) -> dict:
    """Return {seed_id: (tag, sponsor)} from all match contexts."""
    result = {}
    for ctx in match_contexts:
        for seed in (ctx.get("seeds") or []):
            seed_id = seed.get("id") or ""
            if seed_id and seed_id not in result:
                result[seed_id] = extract_seed_info(seed)
    return result


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def build_char_counts(match_contexts: list, seed_map: dict) -> dict:
    """Return {tag: Counter of character names} from parry.gg game-by-game data."""
    counts = {}
    for ctx in match_contexts:
        match = ctx.get("match") or {}
        games = match.get("matchGames") or []
        slots = match.get("slots") or []
        for i, slot in enumerate(slots[:2]):
            seed_id = slot.get("seedId") or ""
            info = seed_map.get(seed_id)
            if not info:
                continue
            tag, _ = info
            if tag == "?" or not tag:
                continue
            if tag not in counts:
                counts[tag] = Counter()
            for game in games:
                game_slots = game.get("slots") or []
                if i >= len(game_slots):
                    continue
                for participant in (game_slots[i].get("participants") or []):
                    for char_obj in (participant.get("characters") or []):
                        cslug = (
                            char_obj.get("characterSlug")
                            or char_obj.get("character_slug")
                            or ""
                        )
                        if cslug:
                            counts[tag][slug_to_name(cslug)] += 1
    return counts


# ---------------------------------------------------------------------------
# Player database fallback for character lookup
# ---------------------------------------------------------------------------

def load_player_db(path: str) -> dict:
    """Return {tag_lower: main_character} from Player_database.csv."""
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
                    char = parts[1].strip()
                    if tag and char:
                        result[tag] = char
    except FileNotFoundError:
        pass
    return result


# ---------------------------------------------------------------------------
# Bracket-aware standings derivation
# ---------------------------------------------------------------------------

def _round_depth(label: str, is_single_elim: bool) -> int:
    """Higher = eliminated later = better placement."""
    lower = label.lower()
    is_losers = "losers" in lower or "lower" in lower

    if "grand" in lower:
        return 1000

    if is_single_elim:
        if "final" in lower and "semi" not in lower and "quarter" not in lower:
            return 1000
        if "semi" in lower:
            return 900
        if "quarter" in lower:
            return 800
        m = re.search(r"(\d+)", label)
        n = int(m.group(1)) if m else 1
        return max(10, 700 - n * 50)

    # Double elimination
    if is_losers:
        if "final" in lower and "semi" not in lower and "quarter" not in lower:
            return 900
        if "semi" in lower:
            return 800
        if "quarter" in lower:
            return 700
        m = re.search(r"(\d+)", label)
        n = int(m.group(1)) if m else 1
        return max(10, 600 - n * 50)

    return 5  # Winners bracket in DE: not a permanent elimination round


def _resolve_winner_loser(slots: list) -> tuple:
    """
    Return (winner_seed_id, loser_seed_id) from two slots.

    parry.gg Slot has no placement field — winner is determined by comparing
    the `score` field (games won). Higher score = winner.

    Returns ("", "") if the match result cannot be determined (unplayed/bye).
    """
    if len(slots) < 2:
        return ("", "")

    s0, s1 = slots[0], slots[1]

    # Primary: score field (games won)
    sc0 = s0.get("score")
    sc1 = s1.get("score")
    if sc0 is not None and sc1 is not None:
        try:
            i0, i1 = int(sc0), int(sc1)
            if i0 > i1:
                return (s0.get("seedId") or "", s1.get("seedId") or "")
            if i1 > i0:
                return (s1.get("seedId") or "", s0.get("seedId") or "")
        except (TypeError, ValueError):
            pass

    # Fallback: other possible score/result field names
    for score_key in ("wins", "gamesWon", "games_won", "result"):
        sc0 = s0.get(score_key)
        sc1 = s1.get(score_key)
        if sc0 is not None and sc1 is not None:
            try:
                if int(sc0) > int(sc1):
                    return (s0.get("seedId") or "", s1.get("seedId") or "")
                if int(sc1) > int(sc0):
                    return (s1.get("seedId") or "", s0.get("seedId") or "")
            except (TypeError, ValueError):
                pass

    return ("", "")


def derive_standings_from_bracket(match_contexts: list, seed_map: dict, top: int) -> list:
    """
    Derive placements from bracket structure.

    Primary: use Match.losers_placement / Match.winners_placement integer fields when
    present — these are guaranteed placement values from the bracket graph.
    Fallback: compare slot scores (higher score = winner) and use round-depth heuristic.

    Returns list of (placement, seed_id) tuples.
    """
    # Phase 1: collect all round labels so we can detect SE vs DE
    all_labels = set()
    for ctx in match_contexts:
        round_obj = ctx.get("round") or {}
        label = (round_obj.get("label") or "").strip() or "Unknown Round"
        all_labels.add(label)

    is_se = not any("losers" in l.lower() or "lower" in l.lower() for l in all_labels)
    print(
        f"Bracket: {len(match_contexts)} matches total  "
        f"| Format: {'single' if is_se else 'double'} elimination  "
        f"| Round labels: {sorted(all_labels)}",
        file=sys.stderr,
    )

    # Phase 2: process all matches
    results = []
    participant_depths = defaultdict(set)
    # seed_id -> guaranteed loser placement from match proto fields (best = lowest number)
    guaranteed_loser_placement = {}

    for ctx in match_contexts:
        match = ctx.get("match") or {}
        round_obj = ctx.get("round") or {}
        label = (round_obj.get("label") or "").strip() or "Unknown Round"
        depth = _round_depth(label, is_se)

        loser_place = match.get("losersPlacement") or match.get("losers_placement")
        winner_place = match.get("winnersPlacement") or match.get("winners_placement")

        slots = match.get("slots") or []
        for slot in slots:
            sid = slot.get("seedId") or ""
            if sid:
                participant_depths[sid].add(depth)

        if len(slots) < 2:
            continue

        winner_id, loser_id = _resolve_winner_loser(slots)
        if winner_id and loser_id:
            results.append({
                "label": label,
                "depth": depth,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "loser_place": loser_place,
                "winner_place": winner_place,
            })
        elif loser_place is not None:
            # Match unresolved (equal scores) but we know the guaranteed placement for the
            # loser of this match — record for both participants as candidates.
            for slot in slots:
                sid = slot.get("seedId") or ""
                if sid:
                    cur = guaranteed_loser_placement.get(sid)
                    p = int(loser_place)
                    if cur is None or p < cur:
                        guaranteed_loser_placement[sid] = p

    print(f"Resolved: {len(results)}/{len(match_contexts)} matches had scoreable results", file=sys.stderr)

    if not results and not participant_depths:
        return []

    # Phase 3: build player_deepest_loss from resolved results
    player_deepest_loss = {}
    player_guaranteed_place = {}  # seed_id -> integer placement from proto fields
    all_ids = set()

    for r in results:
        all_ids.add(r["winner_id"])
        all_ids.add(r["loser_id"])
        lid, d = r["loser_id"], r["depth"]
        if lid not in player_deepest_loss or d > player_deepest_loss[lid]:
            player_deepest_loss[lid] = d
        if r["loser_place"] is not None:
            p = int(r["loser_place"])
            cur = player_guaranteed_place.get(lid)
            if cur is None or p < cur:
                player_guaranteed_place[lid] = p
        if r["winner_place"] is not None:
            wid = r["winner_id"]
            p = int(r["winner_place"])
            cur = player_guaranteed_place.get(wid)
            if cur is None or p < cur:
                player_guaranteed_place[wid] = p

    max_depth = max((r["depth"] for r in results), default=0)
    gf_winner_id = next(
        (r["winner_id"] for r in reversed(results) if r["depth"] == max_depth),
        None,
    )

    # Phase 4: infer placements for players only in unresolved matches
    for sid, depths in participant_depths.items():
        if sid in all_ids or sid == gf_winner_id:
            continue
        max_participation = max(depths)
        if max_participation > 5 or is_se:
            player_deepest_loss[sid] = max_participation
            all_ids.add(sid)
        if sid in guaranteed_loser_placement:
            player_guaranteed_place[sid] = guaranteed_loser_placement[sid]
            all_ids.add(sid)

    # Phase 5: assign placements
    result = []
    if gf_winner_id:
        result.append((player_guaranteed_place.get(gf_winner_id, 1), gf_winner_id))

    placed = {gf_winner_id} if gf_winner_id else set()

    if player_guaranteed_place:
        print(f"Using proto placement fields for {len(player_guaranteed_place)} players", file=sys.stderr)
        place_groups = defaultdict(list)
        unplaced = []
        for pid in all_ids:
            if pid in placed:
                continue
            p = player_guaranteed_place.get(pid)
            if p is not None:
                place_groups[p].append(pid)
                placed.add(pid)
            else:
                unplaced.append(pid)
        for p_val in sorted(place_groups.keys()):
            for pid in sorted(place_groups[p_val]):
                result.append((p_val, pid))
        # depth-based fallback for players with no proto placement
        depth_groups = defaultdict(list)
        for pid in unplaced:
            depth_groups[player_deepest_loss.get(pid, 0)].append(pid)
        next_place = (max(p for p, _ in result) + 1) if result else 2
        for d in sorted(depth_groups.keys(), reverse=True):
            for pid in sorted(depth_groups[d]):
                result.append((next_place, pid))
            next_place += len(depth_groups[d])
    else:
        depth_groups = defaultdict(list)
        for pid in all_ids:
            if pid in placed:
                continue
            depth_groups[player_deepest_loss.get(pid, 0)].append(pid)
        next_place = 2
        for d in sorted(depth_groups.keys(), reverse=True):
            for pid in sorted(depth_groups[d]):
                result.append((next_place, pid))
            next_place += len(depth_groups[d])

    return sorted(result, key=lambda x: x[0])[:top]


# ---------------------------------------------------------------------------
# Standings API path (attempted before bracket derivation)
# ---------------------------------------------------------------------------

def parse_bracket_placements(entries: list, seed_map: dict) -> list:
    """Parse GetBracketPlacements response into (place_int, seed_id_or_tag) tuples.

    The API returns one entry per match played, so deduplicate by keeping the best
    (lowest) placement per player.
    """
    best = {}  # player_key -> (place, player_key)
    for entry in entries:
        place = entry.get("placement") or entry.get("place")
        if place is None:
            continue
        try:
            place = int(place)
        except (TypeError, ValueError):
            continue
        seed = entry.get("seed") or {}
        seed_id = seed.get("id") or ""
        if seed_id and seed_id in seed_map:
            key = seed_id
        else:
            event_entrant = entry.get("eventEntrant") or seed.get("eventEntrant") or {}
            entrant = event_entrant.get("entrant") or {}
            users = entrant.get("users") or []
            tag = ""
            if users:
                tag = (users[0].get("gamerTag") or "").strip()
            if not tag:
                tag = event_entrant.get("name") or "?"
            key = tag
        cur = best.get(key)
        if cur is None or place < cur[0]:
            best[key] = (place, key)
    return sorted(best.values(), key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def format_date(ts) -> str:
    if not ts:
        return ""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return f"{dt.month}/{dt.day}/{dt.year}"
    except Exception:
        return str(ts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch parry.gg top N standings and write a Top 8 HTML txt file."
    )
    parser.add_argument("slug", help="Tournament slug, e.g. immortal-fight-night-274")
    parser.add_argument("--event", "-e", default="0",
                        help="Event index (0-based) or event slug (default: 0)")
    parser.add_argument("--name", "-n", default="", help="Tournament display name override")
    parser.add_argument("--link", "-l", default="", help="Event link URL for the graphic")
    parser.add_argument("--top", "-t", type=int, default=8,
                        help="Number of placements to include (default: 8)")
    parser.add_argument("--out", "-o", default="", help="Output file path (default: stdout)")
    parser.add_argument("--props", default=PROPS_FILE,
                        help=f"Path to app.properties (default: {PROPS_FILE})")
    parser.add_argument("--bracket", "-b", default=DEFAULT_BRACKET_SLUG,
                        help=f"Bracket slug (default: {DEFAULT_BRACKET_SLUG!r})")
    parser.add_argument("--debug", action="store_true",
                        help="Dump raw match JSON to stderr")
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
                print(f"  [{i}] {ev.get('slug')} — {(ev.get('game') or {}).get('name', '')}",
                      file=sys.stderr)
            raise RuntimeError(f"Event not found: {args.event!r}")

    event_id = event.get("id") or ""
    num_entrants = (
        event.get("numEntrants") or event.get("num_entrants")
        or event.get("entrantCount") or 0
    )
    start_at = (
        event.get("startAt") or event.get("start_at")
        or tournament.get("startAt") or tournament.get("start_at")
    )
    date_str = format_date(start_at)

    print(f"Event: {event.get('slug')}  |  ID: {event_id}", file=sys.stderr)
    print("Fetching matches...", file=sys.stderr)
    match_contexts = get_all_matches(event_id, api_key)
    print(f"Fetched {len(match_contexts)} matches", file=sys.stderr)

    if args.debug:
        print("=== RAW MATCH DATA ===", file=sys.stderr)
        for i, ctx in enumerate(match_contexts):
            match = ctx.get("match") or {}
            print(f"\n--- Match {i} ---", file=sys.stderr)
            print(f"  round: {json.dumps(ctx.get('round'))}", file=sys.stderr)
            print(f"  slots: {json.dumps(match.get('slots'))}", file=sys.stderr)
            seeds_summary = [
                {"id": s.get("id"), "gamerTag": extract_seed_info(s)[0]}
                for s in (ctx.get("seeds") or [])
            ]
            print(f"  seeds: {json.dumps(seeds_summary)}", file=sys.stderr)
        print("=== END RAW DATA ===", file=sys.stderr)

    seed_map = build_seed_map(match_contexts)
    char_counts = build_char_counts(match_contexts, seed_map)
    player_db = load_player_db(PLAYER_DB_PATH)

    print("Fetching standings...", file=sys.stderr)
    placements = None

    bracket_id = get_bracket_id(args.slug, args.bracket, api_key)
    if bracket_id:
        print(f"Bracket ID: {bracket_id}", file=sys.stderr)
        raw_placements = get_bracket_placements(bracket_id, api_key)
        if raw_placements:
            print(f"Got {len(raw_placements)} placements from BracketService/GetBracketPlacements", file=sys.stderr)
            placements = parse_bracket_placements(raw_placements, seed_map)[:args.top]
        else:
            print("GetBracketPlacements returned empty — deriving from bracket.", file=sys.stderr)
    else:
        print("Bracket ID lookup failed — deriving from bracket.", file=sys.stderr)

    if not placements:
        placements = derive_standings_from_bracket(match_contexts, seed_map, args.top)

    if not placements:
        print("WARNING: No placement data found. Run with --debug to inspect match data.",
              file=sys.stderr)

    for placement, pid in placements:
        tag = seed_map[pid][0] if pid in seed_map else pid
        print(f"  Place {placement}: {tag}  (seed_id={pid[:8]}...)", file=sys.stderr)

    lines = []
    lines.append("# Top 8 Graphic example")
    lines.append("# All information is tab deliminated")
    lines.append("")
    lines.append("#Graphic Information")
    lines.append(f"Event name:\t{tournament_name}")
    lines.append(f"Event link: {args.link}")
    lines.append(f"Event entrants:\t{num_entrants or '?'} Competitors")
    lines.append(f"Event date:\t{date_str}")
    lines.append("")
    lines.append("# Placements")
    lines.append("# place, name, sponsor, characters")

    for placement, pid in placements:
        # pid may be a seed_id (UUID) or a raw name string
        if pid in seed_map:
            tag, sponsor = seed_map[pid]
        else:
            tag = pid  # raw name fallback
            sponsor = ""

        # Character: parry.gg game data → Player Database fallback
        counter = char_counts.get(tag, Counter())
        if counter:
            char = counter.most_common(1)[0][0]
        else:
            char = player_db.get(tag.lower(), "")

        lines.append(f"{placement},{tag},{sponsor},{char}")

    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Wrote to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
