"""The teacher's base policy must be selectable and honestly recorded.

Doc 99 entry 160.93. Exact buy search is worth −1.095 placement over `greedy`
and −0.095 over `scripted` (160.92), so a run that does not record which base
it cloned cannot be scored against the policy that labelled it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import expert_base_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from scripts.teacher_gap import teacher_config  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def env():
    return TFTEnv(load_all(REAL_DATA_DIR), max_actions_per_round=600)


def test_both_bases_build_and_are_different_objects(env):
    scripted = expert_base_policy(
        env, "scripted", econ=FAST8, sell_bench=True, buy_synergy=True)
    greedy = expert_base_policy(env, "greedy", econ=FAST8)
    assert type(scripted) is not type(greedy) or scripted is not greedy


def test_greedy_base_refuses_scripted_only_flags(env):
    """Silently dropping them would make the sidecar lie about the teacher."""
    for flag in ("sell_bench", "buy_synergy", "match_items", "corner_carry"):
        with pytest.raises(ValueError, match="does not take"):
            expert_base_policy(env, "greedy", econ=FAST8, **{flag: True})
    # Flags left at their falsey defaults are not a conflict.
    assert expert_base_policy(env, "greedy", econ=FAST8, sell_bench=False)


def test_unknown_base_is_rejected(env):
    with pytest.raises(ValueError, match="unknown expert base"):
        expert_base_policy(env, "search")


def test_sidecar_round_trips_the_expert_base(tmp_path):
    run = tmp_path / "run"
    run.mkdir()

    def written(**hyper):
        (run / "metadata.json").write_text(json.dumps({"hyperparameters": hyper}))
        return teacher_config(run)[0]["expert_base"]

    # Runs predating the flag were all scripted-based and must rebuild as such.
    assert written() == "scripted"
    assert written(expert_base="greedy") == "greedy"
    assert written(expert_base="scripted") == "scripted"
