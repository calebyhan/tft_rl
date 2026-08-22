"""Does a direct GreedyPolicy planning trace replay through the action space?

Doc 99 entry 153 found that the existing ``scripted_policy`` is a different
control flow from ``GreedyPolicy``.  That does not establish an action-space
limitation: all direct mutations appear to have legal action counterparts.

This script makes that claim executable.  It prepares two independently
constructed but identical seeded planning states, runs the direct policy on
one while recording calls to PlayerState primitives, maps each call to an action-space action (a direct board move
becomes SELECT then PLACE), and replays the resulting sequence on the original
state.  Equality includes the player, shop, and shared pool.

Outcomes, named before the run:

* exact replay -- action expressiveness is established; port the stronger
  search policy on top of this scheduler rather than the unrelated teacher;
* an unrepresentable primitive -- this is the exact missing action/state;
* a legal trace that reaches a different state -- isolate mutable ordering or
  RNG before any search placement measurement.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from rl.action import Action, ActionKind  # noqa: E402
from rl.opponents import FAST8, STANDARD, EconStrategy, GreedyPolicy  # noqa: E402
from scripts.policy_conformance import (  # noqa: E402
    first_difference,
    prepare,
    snapshot,
)


def slot_of(env, player, unit) -> int:
    """Action-space slot of a unit before a direct primitive mutates it."""
    space = env.action_space_helper
    for slot in range(space.unit_slots):
        if env.executor.unit_at(player, slot) is unit:
            return slot
    raise AssertionError(f"unit {unit.name!r} has no action-space slot")


def trace(env, econ: EconStrategy) -> tuple[list[Action], list[dict], dict]:
    """Produce direct-policy actions from a deep-copied planning state."""
    assert env.match is not None
    shadow_match = env.match
    shadow_player = env.player
    space = env.action_space_helper
    out: list[Action] = []
    steps: list[dict] = []

    def record(name, convert):
        original = getattr(shadow_player, name)

        def wrapped(*args, **kwargs):
            actions = convert(*args, **kwargs)
            out.extend(actions)
            result = original(*args, **kwargs)
            steps.append({"actions": actions, "state": snapshot(env)})
            return result

        setattr(shadow_player, name, wrapped)

    record("buy", lambda shop_slot, _pool: [Action(ActionKind.BUY, shop_slot)])
    record("sell", lambda unit, _pool: [Action(ActionKind.SELL, slot_of(env, shadow_player, unit))])
    record("reroll", lambda _pool, _rng: [Action(ActionKind.REROLL)])
    record("buy_xp", lambda: [Action(ActionKind.BUY_XP)])
    record(
        "move_to_board",
        lambda bench_index, target: [
            Action(ActionKind.SELECT, space.slot_for_bench(bench_index)),
            Action(ActionKind.PLACE, space.slot_for_hex(target)),
        ],
    )

    def equip(item_id, unit):
        item_index = next(
            i for i, item in enumerate(shadow_player.item_bag) if item.id == item_id
        )
        return [Action(ActionKind.EQUIP, item_index, slot_of(env, shadow_player, unit))]

    record("equip_from_bag", equip)

    policy = GreedyPolicy(seed=0, econ=econ)
    if shadow_player.has_pending_offering:
        index = policy.choose_offering(shadow_player, shadow_player.realm_offer)
        out.append(Action(ActionKind.PICK_OFFERING, index))
        shadow_player.pick_offering(index)
        steps.append({"actions": [out[-1]], "state": snapshot(env)})
    if shadow_player.has_pending_augment:
        out.append(Action(ActionKind.PICK_AUGMENT, 0))
        shadow_player.pick_augment(0)
        steps.append({"actions": [out[-1]], "state": snapshot(env)})

    from engine.match import PlanningContext

    context = PlanningContext(
        shadow_match,
        shadow_match.round_id,
        shadow_match.pool,
        shadow_match.rng,
        env._pending_pve,
    )
    policy.plan(shadow_player, context)
    return out, steps, snapshot(env)


def replay(env, steps: list[dict], rng_mode: str) -> tuple[dict, tuple | None]:
    """Replay groups of traced actions and check each direct transition."""
    assert env.match is not None
    # The Gym path passes match.rng to every executor action.  The direct
    # teacher currently passes GreedyPolicy.rng to rerolls instead.  Keeping
    # both streams selectable makes that hidden difference measurable.
    rng = env.match.rng if rng_mode == "match" else random.Random(0)
    index = 0
    for group, step in enumerate(steps):
        for action in step["actions"]:
            encoded = env.action_space_helper.encode(action)
            if not env.action_masks()[encoded]:
                return snapshot(env), (index, repr(action), "masked")
            try:
                _decoded, finished = env.executor.apply(
                    env.player, encoded, env.match.pool, rng
                )
            except Exception as exc:  # the mask/executor agreement under test
                return snapshot(env), (index, repr(action), type(exc).__name__)
            if finished:
                return snapshot(env), (index, repr(action), "ended planning/game")
            index += 1
        difference = first_difference(step["state"], snapshot(env))
        if difference is not None:
            return snapshot(env), (group, [repr(action) for action in step["actions"]], difference)
    return snapshot(env), None


def run(data, seed: int, phase: int, econ: EconStrategy, rng_mode: str) -> dict:
    planner = prepare(data, seed, phase, econ)
    live = prepare(data, seed, phase, econ)
    if planner.match is None or planner.match.finished or not planner.player.alive:
        return {"seed": seed, "phase": phase, "skipped": "agent eliminated before target phase"}
    initial = first_difference(snapshot(planner), snapshot(live))
    if initial is not None:
        raise AssertionError(f"prefix is not common: {initial}")
    actions, steps, expected = trace(planner, econ)
    actual, failure = replay(live, steps, rng_mode)
    return {
        "seed": seed,
        "phase": phase,
        "rng_mode": rng_mode,
        "actions": [repr(action) for action in actions],
        "legal_failure": failure,
        "same_state": failure is None and first_difference(expected, actual) is None,
        "difference": first_difference(expected, actual),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--econ", choices=("standard", "fast8"), default="fast8")
    parser.add_argument("--phases", default="0,5,15,25")
    parser.add_argument("--rng", choices=("match", "policy"), default="match")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    from engine.loader import load_all

    data = load_all()
    econ = {"standard": STANDARD, "fast8": FAST8}[args.econ]
    phases = [int(value) for value in args.phases.split(",")]
    rows = [
        run(data, seed, phase, econ, args.rng)
        for phase in phases
        for seed in range(args.seed, args.seed + args.seeds)
    ]
    usable = [row for row in rows if "skipped" not in row]
    print(f"trace replay: {sum(row['same_state'] for row in usable)}/{len(usable)} exact")
    for row in usable:
        if row["same_state"]:
            continue
        print(f"phase {row['phase']:>2} seed {row['seed']:>4}: "
              f"failure={row['legal_failure']} diff={row['difference']}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
