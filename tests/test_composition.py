"""The real-data composition advisor (doc 99 entry 148).

These guard the two mistakes that would make the advice wrong rather than
merely weak: controlling on a variable that encodes the label (147.1), and
recommending champions the player already holds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.composition import (  # noqa: E402
    KNOWABLE,
    champion_weights,
    load_seats,
    what_winners_added,
)


@pytest.fixture(scope="module")
def seats():
    try:
        return load_seats("challenger")
    except FileNotFoundError:
        pytest.skip("no reference sample checked out")


def test_controls_exclude_the_outcome_proxies():
    """`last_round` and `players_eliminated` are the label in disguise.

    Entry 147.1: controlling on them scores R^2 0.844 by itself and made
    composition look worth -0.001, i.e. worthless. Using what a player knows
    while deciding gives +0.198 instead. This pins the control set so the
    inversion cannot come back silently.
    """
    assert "last_round" not in KNOWABLE
    assert "players_eliminated" not in KNOWABLE
    assert set(KNOWABLE) == {"level", "gold_left"}


def test_weights_drop_rare_champions(seats):
    """A tier list built on a handful of observations is worse than none."""
    weights = champion_weights(seats, min_count=100)
    assert weights, "no champions scored at all"
    assert all(support >= 100 for _weight, support in weights.values())
    strict = champion_weights(seats, min_count=2000)
    assert len(strict) < len(weights), (
        "raising min_count did not drop anyone -- the filter is not applied"
    )


def test_winners_never_suggest_what_you_already_hold(seats):
    """The whole output is "what to add", so held units must not appear."""
    weights = champion_weights(seats)
    mine = {c for c, _ in sorted(weights.items(), key=lambda kv: kv[1][0])[:3]}
    rows, matched, winners = what_winners_added(seats, mine, min_overlap=2)
    assert matched > 0 and winners > 0, "no comparable real boards found"
    suggested = {champion for champion, _count, _share in rows}
    assert not (suggested & mine), (
        f"suggested champions the player already holds: {suggested & mine}"
    )


def test_support_counts_are_reported(seats):
    """`n` travels with every recommendation, or the reader cannot judge it."""
    weights = champion_weights(seats)
    champion = next(iter(weights))
    rows, matched, winners = what_winners_added(seats, {champion}, min_overlap=1)
    assert matched >= winners >= 0
    for _champion, count, share in rows:
        assert count > 0 and 0 < share <= 1.0
