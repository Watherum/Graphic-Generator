#!/usr/bin/env python3
"""Turn Challonge's numeric match rounds into the round *names* a VOD line needs.

Challonge is a bracket tool with no notion of "Grand Final": a match carries a
signed integer ``round`` (positive = winners side, negative = losers side) and
an ``identifier`` letter, and nothing else. start.gg hands over
``fullRoundText`` ready-made and parry.gg a ``round.label``; on Challonge the
names have to be derived, which is what this module does.

The derivation is **positional**: a round is named by how far it sits from the
end of its side of the bracket, not by its number. Round 3 is the winners final
of an 8-player bracket and a middling round of a 128-player one, so counting
back from the last round is the only thing that generalises.

Output style matches the other two fetchers, which abbreviate as they write
("Winners" -> "Wnrs", "Quarter-Final" -> "Qrts"), so a Challonge VOD file reads
the same as a start.gg one and the same abbreviations reach the thumbnails.

Run this file directly to execute its self-test::

    py -3.12 challonge_rounds.py
"""
from __future__ import annotations

from collections import defaultdict

SINGLE_ELIM = "single elimination"
DOUBLE_ELIM = "double elimination"
ROUND_ROBIN = "round robin"
SWISS = "swiss"

#: Depth from the last round of a side -> its name. Anything deeper falls back
#: to "Rd {n}", which is what start.gg's own labels do.
_WINNERS_DEPTH = {0: "Wnrs Final", 1: "Wnrs Semi", 2: "Wnrs Qrts"}
_LOSERS_DEPTH = {0: "Lsrs Final", 1: "Lsrs Semi", 2: "Lsrs Qrts"}
_SINGLE_DEPTH = {0: "Grand Final", 1: "Semi", 2: "Qrts"}


def normalize_type(value: str) -> str:
    """``"double elimination"`` / ``"double_elimination"`` -> a canonical name."""
    text = (value or "").strip().lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    if "double" in text:
        return DOUBLE_ELIM
    if "swiss" in text:
        return SWISS
    if "round robin" in text or "roundrobin" in text:
        return ROUND_ROBIN
    if "single" in text:
        return SINGLE_ELIM
    return text


class MatchInfo:
    """The fields of a Challonge match this module reasons about.

    Kept as a plain object rather than the raw JSON so the derivation can be
    unit-tested without inventing JSON:API envelopes, and so the two fetchers
    do the extraction in one place (:func:`from_resource`).
    """

    __slots__ = ("key", "round", "order", "group_id", "player1", "player2",
                 "winner", "loser", "identifier")

    def __init__(self, key, round_, order=0, group_id="", player1="",
                 player2="", winner="", loser="", identifier=""):
        self.key = key
        self.round = round_
        self.order = order
        self.group_id = group_id or ""
        self.player1 = player1 or ""
        self.player2 = player2 or ""
        self.winner = winner or ""
        self.loser = loser or ""
        self.identifier = identifier or ""

    def losing_player(self) -> str:
        """Who lost, from ``loser`` if given or by elimination from the pair."""
        if self.loser:
            return self.loser
        if self.winner:
            if self.winner == self.player1:
                return self.player2
            if self.winner == self.player2:
                return self.player1
        return ""


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def from_resource(match: dict) -> MatchInfo:
    """Build a :class:`MatchInfo` from a v2.1 match resource.

    Imported lazily so this module stays importable (and self-testable) without
    ``requests`` installed.
    """
    from challonge_api import attrs, match_player_ids, rel_id, resource_id

    bag = attrs(match)
    _ids = match_player_ids(match)
    return MatchInfo(
        key=resource_id(match) or str(bag.get("identifier") or id(match)),
        round_=_int(bag.get("round")),
        order=_int(bag.get("suggested_play_order")),
        group_id=str(bag.get("group_id") or ""),
        player1=_ids[0],
        player2=_ids[1],
        winner=rel_id(match, "winner"),
        loser=rel_id(match, "loser"),
        identifier=str(bag.get("identifier") or ""),
    )


def _winners_final_round(counts: dict) -> int:
    """The winners-bracket round that is the winners final.

    A double-elimination bracket narrows 8 -> 4 -> 2 -> 1 and then keeps
    producing single-match rounds for the grand final (and its reset), so the
    round *number* of the winners final varies and cannot be assumed to be the
    highest. The winners final is the **first** single-match round: everything
    above it is a grand final, whether Challonge puts the reset on the same
    round number as the grand final or on the next one.

    ``counts`` is ``{round: number of matches}`` for the winners side only.
    """
    singles = sorted(r for r, n in counts.items() if n == 1)
    for r in singles:
        # The round below it either does not exist (a two-entrant bracket) or
        # had more than one match, which is what makes this the point the
        # bracket stopped narrowing.
        if counts.get(r - 1, 0) != 1:
            return r
    return max(counts) if counts else 0


def _third_place_key(finalists: list, previous: list):
    """Which of two final-round matches is the 3rd place match, or None.

    Single elimination with a bronze match puts it in the **same round** as the
    final, with nothing marking which is which. The two are told apart by where
    their players came from: the 3rd place match is contested by the two players
    who *lost* the semi-finals, while the final is contested by their winners.

    That needs the semis to have been reported. When they have not, the fallback
    is play order -- the final is the last match of the bracket, so the other
    one is the bronze match.
    """
    losers = {m.losing_player() for m in previous if m.losing_player()}
    if losers:
        scored = [m for m in finalists
                  if m.player1 in losers and m.player2 in losers]
        if len(scored) == 1:
            return scored[0].key
    ordered = sorted(finalists, key=lambda m: (m.order, m.identifier, m.key))
    return ordered[0].key if len(ordered) > 1 else None


def label_rounds(matches, tournament_type: str = "") -> dict:
    """``{match key: round name}`` for every match given.

    ``matches`` is an iterable of :class:`MatchInfo`. ``tournament_type`` is the
    tournament's own ``tournament_type`` attribute; it is only advisory -- the
    presence of negative rounds is what actually decides that a bracket is
    double elimination, since that is a fact about the data rather than about a
    string whose spelling has changed between API versions.
    """
    matches = list(matches)
    kind = normalize_type(tournament_type)
    labels: dict = {}

    # Two-stage tournaments run a group stage first; its matches carry a
    # group_id and its rounds count from 1 within each group, so they cannot
    # share the elimination bracket's positional maths.
    group_stage = [m for m in matches if m.group_id]
    bracket = [m for m in matches if not m.group_id]
    for m in group_stage:
        labels[m.key] = f"Pools Rd {m.round}" if m.round > 0 else "Pools"

    if kind == ROUND_ROBIN:
        for m in bracket:
            labels[m.key] = "Rnd Rbn"
        return labels
    if kind == SWISS:
        for m in bracket:
            labels[m.key] = f"Swiss Rd {m.round}" if m.round > 0 else "Swiss"
        return labels

    winners = [m for m in bracket if m.round > 0]
    losers = [m for m in bracket if m.round < 0]
    for m in bracket:
        if m.round == 0:
            labels[m.key] = ""

    # A losers side is proof of double elimination; the declared type is only
    # consulted for a bracket that has not been played out yet.
    is_double = bool(losers) or kind == DOUBLE_ELIM

    if losers:
        deepest = max(-m.round for m in losers)
        for m in losers:
            depth = deepest - (-m.round)
            labels[m.key] = _LOSERS_DEPTH.get(depth, f"Lsrs Rd {-m.round}")

    if not winners:
        return labels

    counts: dict = defaultdict(int)
    for m in winners:
        counts[m.round] += 1

    if is_double:
        wf = _winners_final_round(counts)
        finals = sorted((m for m in winners if m.round > wf),
                        key=lambda m: (m.order, m.identifier, m.key))
        for i, m in enumerate(finals):
            labels[m.key] = "Grand Final Reset" if i else "Grand Final"
        for m in winners:
            if m.round > wf:
                continue
            depth = wf - m.round
            labels[m.key] = _WINNERS_DEPTH.get(depth, f"Wnrs Rd {m.round}")
        return labels

    # Single elimination: the last round is the final, and may also hold a
    # 3rd place match.
    last = max(counts)
    finalists = [m for m in winners if m.round == last]
    bronze = None
    if len(finalists) > 1:
        bronze = _third_place_key(
            finalists, [m for m in winners if m.round == last - 1])
    for m in winners:
        if m.key == bronze:
            labels[m.key] = "3rd Place"
            continue
        depth = last - m.round
        labels[m.key] = _SINGLE_DEPTH.get(depth, f"Rd {m.round}")
    return labels


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest():
    def m(key, rnd, order=0, **kw):
        return MatchInfo(key, rnd, order=order, **kw)

    # 8-player double elimination: winners 1..3 (3 = winners final),
    # grand final on round 4 with a reset sharing that round.
    de = [
        m("w1a", 1), m("w1b", 1), m("w1c", 1), m("w1d", 1),
        m("w2a", 2), m("w2b", 2),
        m("wf", 3),
        m("gf", 4, order=14), m("gfr", 4, order=15),
        m("l1a", -1), m("l1b", -1),
        m("l2a", -2), m("l2b", -2),
        m("l3", -3),
        m("lf", -4),
    ]
    got = label_rounds(de, "double elimination")
    # 8 players: round 1 is four matches, i.e. the quarter-finals.
    assert got["w1a"] == "Wnrs Qrts", got["w1a"]
    assert got["w2a"] == "Wnrs Semi", got["w2a"]
    assert got["wf"] == "Wnrs Final", got["wf"]
    assert got["gf"] == "Grand Final", got["gf"]
    assert got["gfr"] == "Grand Final Reset", got["gfr"]
    assert got["l1a"] == "Lsrs Rd 1", got["l1a"]
    assert got["l2a"] == "Lsrs Qrts", got["l2a"]
    assert got["l3"] == "Lsrs Semi", got["l3"]
    assert got["lf"] == "Lsrs Final", got["lf"]

    # Same bracket, but Challonge numbering the reset as its own round.
    de2 = [m("wf", 3), m("gf", 4), m("gfr", 5), m("w2a", 2), m("w2b", 2),
           m("lf", -4)]
    got = label_rounds(de2, "double elimination")
    assert got["wf"] == "Wnrs Final", got["wf"]
    assert got["gf"] == "Grand Final", got["gf"]
    assert got["gfr"] == "Grand Final Reset", got["gfr"]

    # A larger winners side keeps counting back from the winners final.
    de3 = [m("r1", 1), m("r1b", 1), m("r1c", 1), m("r1d", 1),
           m("r1e", 1), m("r1f", 1), m("r1g", 1), m("r1h", 1),
           m("q1", 2), m("q2", 2), m("q3", 2), m("q4", 2),
           m("s1", 3), m("s2", 3), m("wf", 4), m("gf", 5), m("lf", -5)]
    got = label_rounds(de3, "double elimination")
    assert got["q1"] == "Wnrs Qrts", got["q1"]
    assert got["s1"] == "Wnrs Semi", got["s1"]
    assert got["r1"] == "Wnrs Rd 1", got["r1"]

    # Single elimination with a bronze match, told apart by the semi losers.
    se = [
        m("s1", 2, player1="a", player2="b", winner="a"),
        m("s2", 2, player1="c", player2="d", winner="c"),
        m("f", 3, order=7, player1="a", player2="c"),
        m("b", 3, order=6, player1="b", player2="d"),
        m("q1", 1), m("q2", 1), m("q3", 1), m("q4", 1),
    ]
    got = label_rounds(se, "single elimination")
    assert got["f"] == "Grand Final", got["f"]
    assert got["b"] == "3rd Place", got["b"]
    assert got["s1"] == "Semi", got["s1"]
    assert got["q1"] == "Qrts", got["q1"]

    # Same, with the semis unreported: play order is the fallback.
    se2 = [m("f", 3, order=7), m("b", 3, order=6), m("s1", 2), m("s2", 2)]
    got = label_rounds(se2, "single elimination")
    assert got["f"] == "Grand Final", got["f"]
    assert got["b"] == "3rd Place", got["b"]

    # Round robin and swiss ignore the positional maths entirely.
    assert label_rounds([m("a", 1), m("b", 2)], "round robin")["b"] == "Rnd Rbn"
    assert label_rounds([m("a", 3)], "swiss")["a"] == "Swiss Rd 3"

    # Two-stage: pool matches are named by their own round, and the bracket
    # that follows is still derived normally.
    two = [m("p1", 1, group_id="9"), m("p2", 2, group_id="9"),
           m("wf", 1), m("gf", 2), m("lf", -1)]
    got = label_rounds(two, "double elimination")
    assert got["p1"] == "Pools Rd 1", got["p1"]
    assert got["wf"] == "Wnrs Final", got["wf"]
    assert got["gf"] == "Grand Final", got["gf"]

    # A bracket with no negative rounds but declared double elimination still
    # reserves its last single-match round for the grand final.
    assert label_rounds([m("wf", 1), m("gf", 2)], "double elimination")["gf"] \
        == "Grand Final"

    print("challonge_rounds: all self-tests passed")


if __name__ == "__main__":
    _selftest()
