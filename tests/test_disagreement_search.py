"""The buy-search exemption in `disagreement_cost` (doc 99 entry 160.97)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.disagreement_cost import _W, _init, check_substitutable  # noqa: E402


def test_no_search_is_substitutable():
    check_substitutable(None)


def test_buy_search_only_is_substitutable():
    # mode="none" queues nothing: the teacher's extra decision is one BUY.
    check_substitutable({"mode": "none", "buy_search": True})


@pytest.mark.parametrize("mode", ["swap", "move", "board"])
def test_positional_search_is_refused(mode):
    with pytest.raises(SystemExit):
        check_substitutable({"mode": mode, "max_candidates": 6})


def test_init_wraps_the_teacher_in_buy_search(tmp_path):
    """`_init` must build the *search* teacher, not its bare base.

    Without the wrapper every counterfactual would substitute the base
    policy's buy, and the probe would measure a teacher that never labelled
    anything -- the failure `teacher_gap`'s search_config note describes.
    """
    from sb3_contrib import MaskablePPO

    import rl.search as search_module

    _W.clear()
    seen: list[dict] = []
    real_search = search_module.search_policy
    real_load = MaskablePPO.load

    def spy(env, **kwargs):
        seen.append(kwargs)
        return real_search(env, **kwargs)

    # The model is irrelevant here and loading one would dominate the runtime;
    # `sb3_policy` only closes over it.
    search_module.search_policy = spy
    MaskablePPO.load = classmethod(lambda cls, *a, **k: object())
    try:
        _init(str(tmp_path / "missing"), {}, {"econ": None},
              search_kwargs={"mode": "none", "buy_search": True})
    finally:
        search_module.search_policy = real_search
        MaskablePPO.load = real_load

    assert seen, "teacher was not wrapped in a buy search"
    assert seen[0]["mode"] == "none"
    assert seen[0]["buy_search"] is True
    assert getattr(_W["teacher"], "rng", None) is not None


def test_undefined_threshold_is_a_constant_not_a_knob():
    """160.99 declared 5% before the run; a later edit to fit an output is the
    failure this pins."""
    from scripts.disagreement_cost import MAX_UNDEFINED_RATE

    assert MAX_UNDEFINED_RATE == 0.05


def test_teacher_opinion_is_none_while_a_unit_is_held():
    """Every SELECT is masked while `executor.selected` is set, so a scheduler
    asking to field a bench unit is refused. The probe must skip, not invent a
    disagreement."""
    from scripts.disagreement_cost import _W, _teacher_opinion

    class FakeEnv:
        class executor:
            selected = 3

        def action_masks(self):  # pragma: no cover - must not be reached
            raise AssertionError("teacher was queried while holding a unit")

    _W["teacher"] = lambda obs, mask: 0
    assert _teacher_opinion(FakeEnv(), None) == "held"


def test_teacher_opinion_swallows_a_scheduler_assertion():
    """A fresh plan can still be illegal. Counting it keeps the rate visible
    instead of crashing a 9-minute run on one state."""
    from scripts.disagreement_cost import _W, _teacher_opinion

    class FakeEnv:
        class executor:
            selected = None

        def action_masks(self):
            return None

    def boom(obs, mask):
        raise AssertionError("Greedy scheduler emitted masked action")

    _W["teacher"] = boom
    assert _teacher_opinion(FakeEnv(), None) == "stuck"


def test_held_and_stuck_are_distinguishable():
    """They are counted separately and only one gates the report; collapsing
    them back to a single reason is the mistake 160.100 corrects."""
    from scripts.disagreement_cost import _W, _teacher_opinion

    class Held:
        class executor:
            selected = 1

    class Stuck:
        class executor:
            selected = None

        def action_masks(self):
            return None

    def boom(obs, mask):
        raise AssertionError("Greedy scheduler emitted masked action")

    _W["teacher"] = boom
    assert _teacher_opinion(Held(), None) != _teacher_opinion(Stuck(), None)


def test_init_clears_resolution_hooks_from_the_shadow_env(tmp_path):
    """The shadow env must be the *same game* as the clone's.

    `greedy_action_policy` registers anvil/component hooks on the seat it is
    built for; `scripted_policy` does not. Leaving them installed made the
    shadow env resolve items differently and terminate first in 8 of 10
    episodes, so the baseline rollout returned no placement and 91% of
    counterfactuals were silently dropped (doc 99 entry 160.101).
    """
    from sb3_contrib import MaskablePPO

    from rl.opponents import FAST8

    _W.clear()
    real_load = MaskablePPO.load
    MaskablePPO.load = classmethod(lambda cls, *a, **k: object())
    try:
        _init(str(tmp_path / "missing"), {},
              {"econ": FAST8, "expert_base": "greedy"},
              search_kwargs={"mode": "none", "buy_search": True})
    finally:
        MaskablePPO.load = real_load

    tenv = _W["teacher_env"]
    assert tenv._external_policy is None, (
        "teacher hooks left on the shadow env -- it is a different game "
        "from the clone's"
    )
