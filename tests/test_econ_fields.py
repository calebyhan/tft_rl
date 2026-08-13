"""Every EconStrategy field must actually reach the teacher (doc 99 entry 86).

`EconStrategy` declares six fields. `GreedyPolicy` honoured all of them; the
*teacher* silently ignored `target_cost` and `target_count`, so `slowroll6`
rolled the shop and bought by generic strength -- 0 three-stars in the agent
seat against 100% in the field, from the same archetype. Implementing them was
worth **-1.210 placement** (entry 86.3).

Nothing warned, and nothing could have: the teacher reads `level_targets` and
`roll_floors` through `econ.target_level()` / `econ.roll_floor()` accessors
rather than by name, so a textual audit reports zero references for fields that
*are* used and cannot distinguish them from fields that are not.

So this is behavioural. For each field, build a variant that must change what
the teacher does, and assert the action sequence differs. A field the teacher
ignores produces an identical sequence.

**Known limitation, established by mutation test.** This detects a field
reaching the teacher *at all*, not that every consumer honours it. Reverting
entry 86's buy-side targeting alone leaves these cases passing, because
`target_cost` still reaches the bench-sell guard. Only reverting both use sites
-- the actual pre-86 state -- fails `target_cost` and `target_count`. A field
gaining a second consumer that ignores it would not be caught here.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.opponents import SLOWROLL6  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

FLAGS = dict(sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True)

# A variant per field that *must* change the teacher's behaviour. `name` is
# excluded: it is a label, not a rule.
VARIANTS = {
    "level_targets": {},                    # never level at all
    # NOT `{}`: the teacher falls back to `save_floor` when no override
    # applies, and SLOWROLL6's only entry (3-2 -> 50) *equals* its save_floor
    # of 50 -- so clearing the map changes nothing and the case would assert
    # nothing while looking like coverage. Roll everything from 2-1 instead.
    "roll_floors": {"2-1": 0},
    "save_floor": 0,                        # spend below the interest floor
    "target_cost": 0,                       # abandon the reroll commitment
    "target_count": 1,                      # commit to one carry, not three
    # 100 is above `starting_hp`, so the seat is "desperate" from 1-1 and rolls
    # its whole bank every round. A realistic 20 would only bite in the last
    # rounds before death, which a single game may not reach -- the case would
    # then assert nothing while reading as coverage (doc 99 entry 99).
    "desperation_hp": 100,
    # "1-1" so the pivot is live from the first round a target could exist,
    # rather than at a realistic 4-2 which a single game might reach only after
    # the seat has already hit -- the case would then assert nothing while
    # reading as coverage, the same trap `desperation_hp` and `roll_floors`
    # above each document (doc 99 entry 111.5).
    "pivot_at": "1-1",
    # Inert unless `pivot_at` is set, so this variant sets both. 0 makes a
    # pivoted seat roll its whole bank instead of banking at 50, which is the
    # opposite of what the field is for and therefore certain to change the
    # action sequence if it is read at all.
    "pivot_floor": 0,
    # SLOWROLL6's curve reaches 6 at 3-2 and 7 at 5-1; capping at 4 until the
    # line hits bites from the first round the curve would raise it, and the
    # fixture seat does not 3-star a cost-2 immediately. A cap of 6 or 7 would
    # coincide with the curve for most of the game and could assert nothing
    # while reading as coverage -- the trap `roll_floors` and `desperation_hp`
    # each document above (doc 99 entry 119).
    "commit_level": 4,
}
# `pivot_floor` alone changes nothing -- it is only consulted once a plan has
# pivoted -- so its variant needs the trigger set too.
VARIANT_COMPANIONS = {"pivot_floor": {"pivot_at": "1-1"}}


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def _actions(data, econ, steps: int = 5000, seed: int = 0) -> list[int]:
    env = TFTEnv(data=data)
    policy = scripted_policy(env, econ=econ, **FLAGS)
    obs, _info = env.reset(seed=seed)
    out = []
    # A whole game: SLOWROLL6 only begins rolling in stage 4, so a truncated
    # budget compares two identical openings and passes on fields it never
    # exercised.
    for _ in range(steps):
        action = int(policy(obs, env.action_masks()))
        out.append(action)
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            break
    return out


def test_the_baseline_plan_is_reproducible(data):
    """Guards the comparison itself: identical config, identical sequence.

    Without this a flaky teacher would make every case below pass for the
    wrong reason -- any two sequences would differ.
    """
    assert _actions(data, SLOWROLL6) == _actions(data, SLOWROLL6)


@pytest.mark.parametrize("field_name", sorted(VARIANTS))
def test_each_econ_field_changes_what_the_teacher_does(data, field_name):
    base = _actions(data, SLOWROLL6)
    changes = {field_name: VARIANTS[field_name],
               **VARIANT_COMPANIONS.get(field_name, {})}
    variant = dataclasses.replace(SLOWROLL6, **changes)
    assert _actions(data, variant) != base, (
        f"EconStrategy.{field_name} does not reach the teacher: changing it to "
        f"{VARIANTS[field_name]!r} produced an identical action sequence. "
        "GreedyPolicy may still honour it -- that divergence is doc 99 entry 86."
    )


def test_every_econ_field_is_covered_by_the_parametrisation():
    """A field added to the dataclass but never exercised here."""
    fields = {f.name for f in dataclasses.fields(SLOWROLL6)} - {"name"}
    assert fields == set(VARIANTS), (
        f"EconStrategy fields {fields} but VARIANTS covers {set(VARIANTS)}; "
        "an unexercised field can be silently ignored by a consumer"
    )
