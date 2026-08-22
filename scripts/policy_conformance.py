"""Can the action space faithfully express the match-level teacher?

Entry 151 withdrew the apparent explanation for the search-teacher port gap:
``GreedyPolicy`` and ``scripted_policy`` are not the same policy expressed in
two harnesses.  Placement cannot localise that difference -- it averages an
entire game after the two policies have already diverged -- so this script
compares one *planning phase* from an identical seeded state.

The direct arm calls ``GreedyPolicy.plan`` through ``PlanningContext``.  The
action arm repeatedly asks ``scripted_policy`` for legal actions, but stops
*before* ``END_PLANNING``: combat must not be allowed to mask a planning-state
difference.  Both environments use a deliberately high per-round action cap,
so an action budget result cannot be mistaken for an expression result.

Outcomes, named before the first run:

* identical snapshots over representative rounds -- the present action policy
  is a faithful port and the search gap lies above it;
* mismatches only after the action cap -- the port is expressible, but the
  environment's cap prevents it;
* earlier mismatches -- the two control flows are distinct.  The first action
  and state field that differ identify the smallest candidate to port before
  any search or cloning measurement.

This is a diagnostic, not a placement evaluation.  It intentionally starts
with the current best-effort action policy; its purpose is to measure the gap,
not to call that policy a faithful implementation by assertion.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.match import PlanningContext  # noqa: E402
from engine.schema import GameData  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy, scripted_policy  # noqa: E402
from rl.opponents import FAST8, STANDARD, EconStrategy, GreedyPolicy  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402

ACTION_CAP = 600
FLAGS = dict(
    sell_bench=True,
    buy_synergy=True,
    match_items=True,
    corner_carry=True,
)


def unit_snapshot(unit) -> dict[str, Any]:
    return {
        "champion": unit.champion.id,
        "star": unit.star_level,
        "items": [item.id for item in unit.items],
    }


def snapshot(env: TFTEnv) -> dict[str, Any]:
    """All planning-phase state either policy can mutate, canonically ordered."""
    player = env.player
    assert env.match is not None
    return {
        "round": str(env.match.round_id),
        "gold": player.gold,
        "level": player.level,
        "xp": player.xp,
        "hp": player.hp,
        "board": [
            {"hex": (hex_.q, hex_.r), **unit_snapshot(unit)}
            for hex_, unit in sorted(player.board.items())
        ],
        "bench": [unit_snapshot(unit) if unit is not None else None for unit in player.bench],
        "item_bag": [item.id for item in player.item_bag],
        "shop": list(player.shop.slots),
        "augments": [augment.id for augment in player.augments],
        "pool": env.match.pool.snapshot(),
        # A shop roll consumes this stream; two states can display identically
        # yet draw different shops if it is omitted from a replay assertion.
        "match_rng": hashlib.sha256(repr(env.match.rng.getstate()).encode()).hexdigest(),
    }


def first_difference(left: Any, right: Any, path: str = "") -> tuple[str, Any, Any] | None:
    """First structural difference in two JSON-shaped snapshots."""
    if type(left) is not type(right):
        return path or "<root>", left, right
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}" if path else key, left.get(key), right.get(key)
            found = first_difference(left[key], right[key], f"{path}.{key}" if path else key)
            if found is not None:
                return found
        return None
    if isinstance(left, list):
        for index, (a, b) in enumerate(zip(left, right, strict=False)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found is not None:
                return found
        if len(left) != len(right):
            return f"{path}.length", len(left), len(right)
        return None
    return None if left == right else (path or "<root>", left, right)


def _direct_policy(name: str, econ: EconStrategy):
    if name == "greedy":
        return GreedyPolicy(seed=0, econ=econ)
    if name == "search_buy":
        from scripts.search_teacher_ab import SearchBuyPolicy

        return SearchBuyPolicy(seed=0, econ=econ)
    raise ValueError(f"unknown direct policy {name!r}")


def direct_plan(
    env: TFTEnv, econ: EconStrategy, direct_policy: str = "greedy"
) -> tuple[list[str], dict[str, Any]]:
    """Run one direct planning phase without allowing combat to begin."""
    assert env.match is not None
    match = env.match
    policy = _direct_policy(direct_policy, econ)
    trace: list[str] = []
    # ``GreedyPolicy`` calls the same PlayerState primitives as the executor.
    # Recording those calls makes a final-state mismatch attributable to a
    # planning decision rather than to one of the two harnesses.
    originals = {}
    for name in ("buy", "sell", "reroll", "buy_xp", "move_to_board", "equip_from_bag"):
        original = getattr(env.player, name)
        originals[name] = original

        def record(*args, _name=name, _original=original, **kwargs):
            result = _original(*args, **kwargs)
            trace.append(_name)
            return result

        setattr(env.player, name, record)
    # In a real Match these choices happen immediately before ``plan``.  The
    # environment deliberately pauses there for the agent, so reproduce the
    # same boundary explicitly; comparing a player who picked its carousel
    # unit to one who has not is an input error, not a policy difference.
    if env.player.has_pending_offering:
        env.player.pick_offering(
            policy.choose_offering(env.player, env.player.realm_offer)
        )
        trace.append("pick_offering")
    if env.player.has_pending_augment:
        env.player.pick_augment(0)
        trace.append("pick_augment")
    context = PlanningContext(
        match, match.round_id, match.pool, match.rng, env._pending_pve
    )
    try:
        policy.plan(env.player, context)
    finally:
        for name, original in originals.items():
            setattr(env.player, name, original)
    return trace, snapshot(env)


def action_plan(
    env: TFTEnv, econ: EconStrategy, action_policy: str = "scripted"
) -> tuple[list[str], dict[str, Any], bool]:
    """Run action policy until its end action, retaining the pre-combat state."""
    if action_policy == "scripted":
        policy = scripted_policy(env, econ=econ, **FLAGS)
    elif action_policy == "greedy":
        policy = greedy_action_policy(env, econ=econ)
    elif action_policy == "search_buy":
        policy = search_buy_greedy_policy(env, econ=econ)
    else:
        raise ValueError(f"unknown action policy {action_policy!r}")
    obs = env._observe()
    actions: list[str] = []
    for _ in range(ACTION_CAP):
        action = int(policy(obs, env.action_masks()))
        decoded = env.action_space_helper.decode(action)
        if decoded.kind.name == "END_PLANNING":
            return actions, snapshot(env), False
        actions.append(repr(decoded))
        obs, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            raise AssertionError("planning phase ended before END_PLANNING")
        if env.actions_left == 0:
            return actions, snapshot(env), True
    raise AssertionError(f"policy did not end planning within {ACTION_CAP} actions")


def prepare(
    data: GameData, seed: int, phases: int, econ: EconStrategy,
    direct_policy: str = "greedy",
) -> TFTEnv:
    """Reach a planning phase by a common direct-policy prefix.

    A target phase must be an identical state in both arms.  Advancing one
    environment through actions and the other through direct calls would make
    every later difference tautological, so both prefixes deliberately use
    the direct policy.  The comparison begins only after the common prefix.
    """
    env = TFTEnv(data=data, max_actions_per_round=ACTION_CAP)
    env.reset(seed=seed)
    for _ in range(phases):
        if env.match is None or env.match.finished or not env.player.alive:
            break
        direct_plan(env, econ, direct_policy)
        env._advance_round()
        if not env.match.finished and env.player.alive:
            env._begin_planning()
    return env


def run_round(
    data: GameData,
    seed: int,
    target_round: int,
    econ: EconStrategy,
    action_policy: str = "scripted",
    direct_policy: str = "greedy",
) -> dict[str, Any]:
    """Compare the two paths at one planning phase of a seeded game.

    Advancing earlier rounds with the action policy would make the two inputs
    differ by construction.  This probe therefore samples the target phase
    after the common match machinery has prepared it, before either seat acts.
    Target round 0 is the opening.  Later rounds are reached by accepting the
    direct policy for both arms *only to create a common input*; the match RNG
    and pool are therefore part of the tested input rather than reconstructed.
    """
    direct = prepare(data, seed, target_round, econ, direct_policy)
    action = prepare(data, seed, target_round, econ, direct_policy)
    if direct.match is None or direct.match.finished or not direct.player.alive:
        return {
            "seed": seed,
            "phase": target_round,
            "econ": econ.name,
            "skipped": "agent eliminated before target phase",
        }
    initial = first_difference(snapshot(direct), snapshot(action))
    if initial is not None:
        raise AssertionError(f"same seed did not produce a common input: {initial}")
    direct_actions, direct_state = direct_plan(direct, econ, direct_policy)
    actions, action_state, hit_cap = action_plan(action, econ, action_policy)
    difference = first_difference(direct_state, action_state)
    return {
        "seed": seed,
        "phase": target_round,
        "econ": econ.name,
        "action_policy": action_policy,
        "direct_policy": direct_policy,
        "actions": actions,
        "direct_actions": direct_actions,
        "actions_taken": len(actions),
        "hit_action_cap": hit_cap,
        "same_state": difference is None,
        "difference": difference,
        "direct_digest": hashlib.sha256(json.dumps(direct_state, sort_keys=True).encode()).hexdigest(),
        "action_digest": hashlib.sha256(json.dumps(action_state, sort_keys=True).encode()).hexdigest(),
    }


def run_panel(
    data: GameData, seeds: range, phases: list[int], econ: EconStrategy,
    action_policy: str, direct_policy: str,
) -> list[dict[str, Any]]:
    """Run the requested panel, advancing each expensive search prefix once."""
    def clone_common(env: TFTEnv) -> TFTEnv:
        memo: dict[int, object] = {}
        seen: set[int] = set()

        def preserve(value) -> None:
            identity = id(value)
            if identity in seen:
                return
            seen.add(identity)
            if isinstance(value, MappingProxyType):
                memo[identity] = value
                return
            if isinstance(value, dict):
                for child in value.values():
                    preserve(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    preserve(child)
            elif hasattr(value, "__dict__"):
                for child in vars(value).values():
                    preserve(child)

        preserve(env)
        return copy.deepcopy(env, memo)

    wanted, rows = set(phases), []
    for seed in seeds:
        common = TFTEnv(data=data, max_actions_per_round=ACTION_CAP)
        common.reset(seed=seed)
        for phase in range(max(phases) + 1):
            if common.match is None or common.match.finished or not common.player.alive:
                break
            if phase in wanted:
                direct, action = clone_common(common), clone_common(common)
                direct_actions, direct_state = direct_plan(direct, econ, direct_policy)
                actions, action_state, hit_cap = action_plan(action, econ, action_policy)
                difference = first_difference(direct_state, action_state)
                rows.append({"seed": seed, "phase": phase, "econ": econ.name,
                             "action_policy": action_policy, "direct_policy": direct_policy,
                             "actions": actions, "direct_actions": direct_actions,
                             "actions_taken": len(actions), "hit_action_cap": hit_cap,
                             "same_state": difference is None, "difference": difference})
            direct_plan(common, econ, direct_policy)
            common._advance_round()
            if not common.match.finished and common.player.alive:
                common._begin_planning()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--econ", choices=("standard", "fast8"), default="fast8")
    parser.add_argument(
        "--action-policy", choices=("scripted", "greedy", "search_buy"), default="scripted",
        help="scheduler to compare with direct GreedyPolicy",
    )
    parser.add_argument(
        "--direct-policy", choices=("greedy", "search_buy"), default="greedy",
        help="direct policy whose planning state is the oracle",
    )
    parser.add_argument(
        "--phases", default="0,5,15,25",
        help="comma-separated zero-based planning phases to compare",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    from engine.loader import load_all

    econ = {"standard": STANDARD, "fast8": FAST8}[args.econ]
    data = load_all()
    phases = [int(value) for value in args.phases.split(",")]
    rows = run_panel(
        data, range(args.seed, args.seed + args.seeds), phases, econ,
        args.action_policy, args.direct_policy,
    )
    usable = [row for row in rows if "skipped" not in row]
    matching = sum(row["same_state"] for row in usable)
    capped = sum(row["hit_action_cap"] for row in usable)
    print(f"planning phases: {matching}/{len(usable)} exact matches; action cap hit: {capped}")
    for row in rows:
        if "skipped" in row:
            continue
        if row["same_state"]:
            continue
        path, direct_value, action_value = row["difference"]
        print(f"phase {row['phase']:>2} seed {row['seed']:>4}: first diff {path}: direct={direct_value!r} action={action_value!r} "
              f"({row['actions_taken']} actions)")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
