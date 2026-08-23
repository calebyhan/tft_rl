"""Can the current observation determine a search-buy teacher's choice?

The action teacher evaluates full opponent boards through combat simulation.
``scouting="full"`` exposes only opponent summaries, while ``tokens`` omits
seat identity. This probe holds every encoded feature and legal-action mask
fixed, counterfactually swaps either two positions/item loadouts, replaces one
opponent unit with a summary-preserving champion, or swaps a tied pair's hidden
player ids/augment sets. It then asks whether ``best_buy`` changes its
recommendation. One
changed recommendation is a counterexample: no policy reading this observation
can reproduce both labels.

This is an observability test, not a placement test. It deliberately performs
the counterfactual on the live environment only temporarily, restores it before
the teacher acts, and restores the search RNG so the episode itself stays on
its ordinary trajectory.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import opponent_panel, search_buy_greedy_policy  # noqa: E402


def visible_tiebreak_panel(match, player, size: int):
    """Keep the teacher's strength rank, replacing only its hidden id tie-break.

    This is deliberately local to the probe until the counterfactual confirms
    that it removes the collision.  Every component of ``board_signature`` is
    already present in a scout token; no policy score or combat result leaks
    into the rank.
    """
    def board_signature(opponent):
        return tuple(
            (
                hex_.q,
                hex_.r,
                unit.champion.id,
                unit.star_level,
                tuple(item.id for item in unit.items),
            )
            for hex_, unit in sorted(opponent.board.items())
        )

    others = [
        p for p in match.players
        if p.player_id != player.player_id and p.alive and p.board
    ]
    others.sort(key=lambda p: (-len(p.board), -p.hp, board_signature(p)))
    return others[:size]


def hidden_counterfactual(
    env: TFTEnv,
    rng: random.Random,
    original,
    *,
    mutation: str,
    max_swaps: int,
):
    """Return the first hidden board mutation that changes ``best_buy``, if any."""
    player, match = env.player, env.match
    assert match is not None
    panel = opponent_panel(match, player, 2)
    if not player.board or not player.free_bench_slots or not panel:
        return False, None
    opponents = [
        p for p in match.players
        if p.player_id != player.player_id and p.alive and p.board
    ]
    opponent = panel[0]
    occupied = sorted(opponent.board)
    if mutation in ("position", "item", "identity") and len(occupied) < 2:
        return False, None

    rng_state = rng.getstate()
    baseline = original(env, rng)
    rng.setstate(rng_state)
    observation = env._observe()
    observation = (
        {key: value.copy() for key, value in observation.items()}
        if isinstance(observation, dict)
        else observation.copy()
    )
    mask = env.action_masks().copy()

    def observation_is_unchanged() -> bool:
        current = env._observe()
        if isinstance(observation, dict):
            return (
                isinstance(current, dict)
                and observation.keys() == current.keys()
                and all(np.array_equal(observation[key], current[key]) for key in observation)
            )
        return np.array_equal(observation, current)

    if mutation == "position":
        candidates = list(itertools.combinations(occupied, 2))
    elif mutation == "item":
        candidates = [
            (left, right)
            for left, right in itertools.combinations(occupied, 2)
            if opponent.board[left].items != opponent.board[right].items
        ]
    elif mutation == "identity":
        candidates = []
        for hex_ in occupied:
            unit = opponent.board[hex_]
            original_champion = unit.champion
            for champion in sorted(player.data.champions.values(), key=lambda c: c.id):
                if champion.id == original_champion.id or champion.cost != original_champion.cost:
                    continue
                unit.champion = champion
                unit._invalidate()
                try:
                    # Exact equality is stronger than attempting to derive
                    # which trait substitutions preserve active breakpoints.
                    # It permits a hidden identity mutation only when the
                    # actual shipped observer cannot tell it happened.
                    if (observation_is_unchanged()
                            and np.array_equal(mask, env.action_masks())):
                        candidates.append((hex_, champion))
                finally:
                    unit.champion = original_champion
                    unit._invalidate()
    elif mutation == "panel_tie":
        candidates = [
            (left, right)
            for left, right in itertools.combinations(opponents, 2)
            if len(left.board) == len(right.board) and left.hp == right.hp
        ]
    else:
        # Swapping two actual live loadouts stays within configurations the
        # match generated. Neither shipped scout encoding carries opponent
        # augments, but combat clones apply their owner bonuses.
        candidates = [
            (left, right)
            for left, right in itertools.combinations(opponents, 2)
            if (left in panel or right in panel)
            and tuple(augment.id for augment in left.augments)
            != tuple(augment.id for augment in right.augments)
        ]
    if not candidates:
        return False, None

    for swap_index, (left, right) in enumerate(candidates):
        if swap_index >= max_swaps:
            break
        if mutation == "position":
            opponent.board[left], opponent.board[right] = (
                opponent.board[right], opponent.board[left],
            )
        elif mutation == "item":
            left_unit, right_unit = opponent.board[left], opponent.board[right]
            left_items, right_items = list(left_unit.items), list(right_unit.items)
            left_unit._items, right_unit._items = right_items, left_items
            left_unit._invalidate()
            right_unit._invalidate()
        elif mutation == "identity":
            unit, champion = opponent.board[left], right
            original_champion = unit.champion
            unit.champion = champion
            unit._invalidate()
        elif mutation == "panel_tie":
            left_player, right_player = left, right
            original_ids = (left_player.player_id, right_player.player_id)
            left_player.player_id, right_player.player_id = original_ids[::-1]
        else:
            left_player, right_player = left, right
            original_augments = (list(left_player.augments), list(right_player.augments))
            left_player.augments, right_player.augments = original_augments[::-1]
        try:
            # The selected scouting mode intentionally omits the mutated fact.
            # This invariant makes a differing label a proof rather than a
            # correlation claim.
            assert observation_is_unchanged()
            assert np.array_equal(mask, env.action_masks())
            alternative = original(env, rng)
        finally:
            if mutation == "position":
                opponent.board[left], opponent.board[right] = (
                    opponent.board[right], opponent.board[left],
                )
            elif mutation == "item":
                left_unit._items, right_unit._items = left_items, right_items
                left_unit._invalidate()
                right_unit._invalidate()
            elif mutation == "identity":
                unit.champion = original_champion
                unit._invalidate()
            elif mutation == "panel_tie":
                left_player.player_id, right_player.player_id = original_ids
            else:
                left_player.augments, right_player.augments = original_augments
            rng.setstate(rng_state)
        if alternative != baseline:
            details = {"mutation": mutation}
            if mutation == "identity":
                details["hex"] = (left.q, left.r)
                details["champions"] = {
                    "before": original_champion.id,
                    "after": champion.id,
                }
            elif mutation in ("position", "item"):
                details["hexes"] = ((left.q, left.r), (right.q, right.r))
            elif mutation == "panel_tie":
                details.update({
                    "player_ids": {"before": original_ids, "after": original_ids[::-1]},
                    "board_size": len(left_player.board),
                    "hp": left_player.hp,
                })
            else:
                details["augment_ids"] = {
                    "before": [
                        [augment.id for augment in original_augments[0]],
                        [augment.id for augment in original_augments[1]],
                    ],
                    "after": [
                        [augment.id for augment in original_augments[1]],
                        [augment.id for augment in original_augments[0]],
                    ],
                }
            if mutation == "item":
                details["item_ids"] = {
                    "before": ([item.id for item in left_items],
                               [item.id for item in right_items]),
                    "after": ([item.id for item in right_items],
                              [item.id for item in left_items]),
                }
            return True, {
                "baseline": baseline,
                "alternative": alternative,
                "opponent": opponent.player_id,
                "swap": details,
            }
    return True, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--scouting", choices=("summary", "full", "tokens"), default="summary")
    parser.add_argument(
        "--mutation",
        choices=("position", "item", "identity", "panel_tie", "augment"),
        default="position",
    )
    parser.add_argument(
        "--panel-tie-break",
        choices=("current", "visible"),
        default="current",
        help="use the current hidden-id rank or test a token-visible tie-break",
    )
    parser.add_argument(
        "--max-search-calls",
        type=int,
        default=6,
        help="eligible search states to counterfactually evaluate",
    )
    parser.add_argument(
        "--max-swaps",
        type=int,
        default=6,
        help="hidden counterfactuals evaluated per eligible search state",
    )
    parser.add_argument(
        "--continue-after-change",
        action="store_true",
        help="measure every budgeted state instead of stopping at the first collision",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = load_all()
    original = search_mod.best_buy
    original_panel = search_mod.opponent_panel
    if args.panel_tie_break == "visible":
        search_mod.opponent_panel = visible_tiebreak_panel
    tested = 0
    changed: list[dict] = []
    stop = False

    try:
        for seed in range(args.seed, args.seed + args.games):
            env = TFTEnv(data=data, max_actions_per_round=600, scouting=args.scouting)
            obs, _ = env.reset(seed=seed)
            policy = search_buy_greedy_policy(env, econ=FAST8)

            def wrapped(probe_env, rng, _seed=seed, **kwargs):
                nonlocal stop, tested
                if stop:
                    return original(probe_env, rng, **kwargs)
                eligible, result = hidden_counterfactual(
                    probe_env,
                    rng,
                    original,
                    mutation=args.mutation,
                    max_swaps=args.max_swaps,
                )
                if eligible:
                    tested += 1
                if result is not None:
                    result["seed"] = _seed
                    result["round"] = str(probe_env.match.round_id)
                    changed.append(result)
                    if not args.continue_after_change:
                        stop = True
                if tested >= args.max_search_calls:
                    stop = True
                return original(probe_env, rng, **kwargs)

            search_mod.best_buy = wrapped
            try:
                terminated = False
                while not terminated:
                    action = policy(obs, env.action_masks())
                    obs, _reward, terminated, truncated, _info = env.step(action)
                    terminated = terminated or truncated
                    if stop:
                        break
            finally:
                search_mod.best_buy = original
            if stop:
                break
    finally:
        search_mod.opponent_panel = original_panel

    payload = {
        "games": args.games,
        "scouting": args.scouting,
        "mutation": args.mutation,
        "panel_tie_break": args.panel_tie_break,
        "max_search_calls": args.max_search_calls,
        "max_swaps": args.max_swaps,
        "search_calls": tested,
        "changed_states": len(changed),
        "examples": changed[:10],
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
