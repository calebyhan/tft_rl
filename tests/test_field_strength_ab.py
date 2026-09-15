"""The field-strength A/B must vary seats 5-7 and nothing else (doc 99 entry 160.153)."""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.opponents import DEFAULT_FIELD, FAST8, GreedyPolicy  # noqa: E402
from rl.teacher_seat import TeacherSeat  # noqa: E402
from scripts.field_strength_ab import (  # noqa: E402
    ARMS,
    FIELDS,
    REPLACED_SEATS,
    opponent_factory,
    summarise,
)
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    logging.disable(logging.WARNING)
    yield load_all(REAL_DATA_DIR)
    logging.disable(logging.NOTSET)


def test_replaced_seats_are_the_reroll_archetypes():
    assert {DEFAULT_FIELD[s].name for s in REPLACED_SEATS} == {"slowroll6", "hyperroll"}
    assert all(DEFAULT_FIELD[s].name not in {"slowroll6", "hyperroll"}
               for s in range(8) if s not in REPLACED_SEATS)


@pytest.mark.parametrize("field", FIELDS)
def test_fields_differ_only_in_the_replaced_seats(data, field):
    factory = opponent_factory(data, field, seed=85_000)
    for seat in range(1, 8):
        policy = factory(seat)
        if field == "default" or seat not in REPLACED_SEATS:
            assert isinstance(policy, GreedyPolicy)
            assert policy.econ is DEFAULT_FIELD[seat]
        elif field == "bots":
            assert isinstance(policy, GreedyPolicy)
            assert policy.econ is FAST8
        else:
            assert isinstance(policy, TeacherSeat)
            assert policy.view.seat == seat


def test_teacher_seats_do_not_share_a_search_stream(data):
    factory = opponent_factory(data, "teachers", seed=85_000)
    streams = [factory(seat).policy.rng.random() for seat in REPLACED_SEATS]
    assert len(set(streams)) == len(streams)


def test_unknown_field_is_refused(data):
    with pytest.raises(ValueError):
        opponent_factory(data, "stronger", seed=0)


def test_a_single_game_per_condition_summarises():
    """Regression: the one-game smoke run crashed in ``stdev`` after playing."""
    records = [
        {"field": f, "arm": a, "seed": 0, "placement": 4 if a == "greedy" else 2,
         "beat_replaced_seats": 0, "cpu_seconds": 0.0, "fight_calls": 0}
        for f in FIELDS for a in ARMS
    ]
    _, comparisons = summarise(records)
    assert comparisons["default: full minus greedy"]["delta"] == -2
    assert math.isnan(comparisons["default: full minus greedy"]["se"])


def test_gap_difference_is_positive_when_the_edge_shrinks():
    placements = {
        ("default", "greedy"): [5, 6, 4], ("default", "full"): [2, 2, 1],
        ("bots", "greedy"): [5, 5, 6], ("bots", "full"): [3, 2, 4],
        ("teachers", "greedy"): [6, 5, 7], ("teachers", "full"): [6, 5, 6],
    }
    records = [
        {"field": f, "arm": a, "seed": i, "placement": p,
         "beat_replaced_seats": 0, "cpu_seconds": 0.0, "fight_calls": 0}
        for (f, a), column in placements.items() for i, p in enumerate(column)
    ]
    assert {r["arm"] for r in records} == set(ARMS)
    _, comparisons = summarise(records)
    assert comparisons["default: full minus greedy"]["delta"] == pytest.approx(-10 / 3)
    assert comparisons["teachers gap minus default gap"]["delta"] == pytest.approx(3.0)
    assert comparisons["bots gap minus default gap"]["delta"] == pytest.approx(1.0)
