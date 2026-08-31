"""The surplus roll-down arms must differ, and must not mutate what ships.

Doc 99 entry 160.75. A treatment built by mutating ``rl.opponents``' module
level strategies would silently change every other experiment in the repo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.opponents import DEFAULT_FIELD, HYPERROLL, STANDARD  # noqa: E402
from scripts import surplus_roll_ab as probe  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_building_the_arms_does_not_touch_the_shipped_strategies():
    before = dict(HYPERROLL.roll_floors), dict(STANDARD.roll_floors)
    probe.arms()
    assert (dict(HYPERROLL.roll_floors), dict(STANDARD.roll_floors)) == before
    assert "5-1" not in HYPERROLL.roll_floors
    assert "5-1" not in STANDARD.roll_floors


def test_treatment_adds_the_surplus_floor_and_keeps_the_base_plan():
    built = probe.arms()
    treatment = built["hyperroll+5-1"]
    assert treatment.roll_floors["5-1"] == 0
    for round_label, floor in HYPERROLL.roll_floors.items():
        assert treatment.roll_floors[round_label] == floor
    assert treatment.level_targets == HYPERROLL.level_targets


def test_field_variants_change_only_contention_and_not_the_shipped_field():
    """Doc 99 entry 160.79: vary rivals for the 1-cost pool, nothing else."""
    before = tuple(DEFAULT_FIELD)
    built = probe.fields()
    assert tuple(DEFAULT_FIELD) == before
    assert built["default"] == before

    # Seat 0 always carries the arm, so rivals are counted over seats 1-7.
    def rivals(field):
        return sum(1 for econ in field[1:] if econ is HYPERROLL)

    assert rivals(built["default"]) == 1
    assert rivals(built["uncontested"]) == 0
    assert rivals(built["contested"]) == 3

    # Only the intended seats move.
    for name, moved in (("uncontested", {7}), ("contested", {5, 6})):
        differing = {
            seat for seat, (a, b) in enumerate(
                zip(built["default"], built[name], strict=True)
            ) if a is not b
        }
        assert differing == moved


def test_rival_fields_vary_target_cost_only(loaded_free=None):
    """160.81's axis: equally strong rivals aimed at different pools."""
    built = probe.fields()
    for rivals in (0, 1, 3):
        seats = built[f"rivals{rivals}"]
        assert seats[:5] == DEFAULT_FIELD[:5]
        aiming = [econ for econ in seats[5:8] if econ.target_cost == 1]
        assert len(aiming) == rivals
        # Every rival seat runs the same plan; only the pool it drains differs.
        for econ in seats[5:8]:
            assert econ.level_targets == HYPERROLL.level_targets
            assert econ.roll_floors == HYPERROLL.roll_floors
            assert econ.save_floor == HYPERROLL.save_floor
            assert econ.target_cost in (1, 2)


def test_paired_t_matches_a_hand_computed_case():
    mean, t = probe.paired_t([1.0, 2.0, 3.0], [2.0, 3.0, 4.0])
    assert mean == pytest.approx(1.0)
    assert t == 0.0  # zero variance in the differences

    # diffs [-1, +1, -1, -3]: mean -1, deviations [0, 2, 0, -2],
    # sample variance 8/3, standard error sqrt(8/3/4).
    mean, t = probe.paired_t([4.0, 4.0, 4.0, 4.0], [3.0, 5.0, 3.0, 1.0])
    assert mean == pytest.approx(-1.0)
    assert t == pytest.approx(-1.0 / ((8 / 3 / 4) ** 0.5))


@pytest.fixture(scope="module")
def loaded():
    probe._DATA = load_all(REAL_DATA_DIR)
    yield probe._DATA
    probe._DATA = None


def test_decaying_floor_restores_the_save_floor_the_next_round():
    """The decaying arm must be a one-round breakpoint, not a standing floor."""
    built = probe.arms()
    decaying = built["hyperroll+5-1r"]
    assert decaying.roll_floors["5-1"] == 0
    assert decaying.roll_floors["5-2"] == HYPERROLL.save_floor
    standing = built["hyperroll+5-1"]
    assert "5-2" not in standing.roll_floors

    from engine.economy import RoundId
    assert decaying.roll_floor(RoundId(5, 1)) == 0
    assert decaying.roll_floor(RoundId(5, 2)) == HYPERROLL.save_floor
    assert decaying.roll_floor(RoundId(6, 1)) == HYPERROLL.save_floor
    assert standing.roll_floor(RoundId(6, 1)) == 0


def test_the_surplus_floor_actually_binds(loaded):
    """Control must never roll after 5-1; treatment must (160.75's diagnostic).

    Without this the study could report a null produced by a treatment that
    never fired.
    """
    seeds = range(3)
    control = [probe.play_one(("hyperroll", seed)) for seed in seeds]
    standing = [probe.play_one(("hyperroll+5-1", seed)) for seed in seeds]
    decaying = [probe.play_one(("hyperroll+5-1r", seed)) for seed in seeds]

    def rolls_after(records):
        return sum(record["rolls_after_surplus"] or 0 for record in records)

    assert any(record["reached_surplus"] for record in control)
    assert all(record["rolls_after_surplus"] in (0, None) for record in control)
    # The decaying floor must roll -- but strictly less than the standing one,
    # or the restore entry is not taking effect (doc 99 entry 160.77).
    assert 0 < rolls_after(decaying) < rolls_after(standing)
