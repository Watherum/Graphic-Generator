#!/usr/bin/env python3
"""Shared pieces of a results post, used by every provider's post fetcher.

The three fetchers (``fetch_results_tweet.py`` for start.gg,
``fetch_parrygg_post.py``, ``fetch_challonge_post.py``) differ only in how they
get standings and handles out of their API. The *post* itself -- the intro line,
the emoji placement list, the "next bracket" and vods footers -- must read
identically whichever site the bracket came from, so it lives here rather than
being reimplemented three times and drifting.

A fetcher's job is to produce ``(rank, display)`` pairs; ``build_post`` does the
rest. ``display`` is already resolved to a handle or a plain tag, because only
the fetcher knows which its API can offer.
"""
import argparse

#: Standard double-elim top 8: 5th/6th both show 5th, 7th/8th both show 7th.
PLACEMENT_EMOJIS = {
    1: "\U0001F947",   # gold
    2: "\U0001F948",   # silver
    3: "\U0001F949",   # bronze
    4: "4\uFE0F\u20E3",
    5: "5\uFE0F\u20E3",
    6: "5\uFE0F\u20E3",
    7: "7\uFE0F\u20E3",
    8: "7\uFE0F\u20E3",
}


def placement_emoji(rank: int) -> str:
    """The emoji for a placement, or "N." past the top 8."""
    return PLACEMENT_EMOJIS.get(rank, f"{rank}.")


def strip_sponsor(name: str) -> str:
    """"TSM | Leffen" -> "Leffen"."""
    if " | " in name:
        return name.split(" | ", 1)[1]
    return name


def build_post(tournament_name: str, entries, intro_tmpl: str,
               next_date: str, series_link: str, vods_link: str) -> str:
    """The finished post text.

    ``entries`` is an iterable of ``(rank, display)``. It is sorted by rank
    here, so a fetcher may hand them over in whatever order its API returned.
    """
    lines = [intro_tmpl.replace("{name}", tournament_name), ""]

    for rank, display in sorted(entries, key=lambda e: (e[0] or 999)):
        lines.append(f"{placement_emoji(rank)} {display}")

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


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """The post-shaping flags every fetcher takes, spelled the same way.

    The GUI builds one command line per provider from the same widgets, so a
    flag renamed in one script and not the others breaks that tab quietly.
    """
    parser.add_argument("--name", "-n", default="",
                        help="Tournament display name")
    parser.add_argument("--intro",
                        default="Thank you to everyone who came out for {name}!",
                        help="Intro line template ({name} is replaced)")
    parser.add_argument("--next", default="",
                        help="Next event date string, e.g. 'June 17th'")
    parser.add_argument("--link", default="", help="Series link")
    parser.add_argument("--vods", default="", help="YouTube VODs playlist link")
    parser.add_argument("--top", "-t", type=int, default=8,
                        help="Number of top placements (default: 8)")
    parser.add_argument("--out", "-o", default="",
                        help="Output file path (default: stdout only)")


def emit(post: str, out_path: str, platform_label: str) -> None:
    """Write the post where the GUI expects it, and echo it to the console."""
    import sys
    from pathlib import Path
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(post + "\n", encoding="utf-8")
        print(f"Wrote to {out_path}", file=sys.stderr)
    # Always printed: the GUI mirrors stdout into its console pane.
    print(f"\n--- Results Post ({platform_label}) ---")
    print(post)
    print("-------------------------------")


def force_utf8_stdout() -> None:
    """Emoji must not crash a Windows console."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
