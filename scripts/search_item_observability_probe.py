"""Find conflicting item-teacher labels under one clone observation.

The richest shipped observation (``scouting="tokens"``) describes a bag only
by its length and an owned unit's loadout only by its item count.  This probe
reaches a real equip state, substitutes one legal component for another while
holding every encoded value and mask fixed, and asks the validated depth-1
item teacher for its first real ``EQUIP`` action.

Two distinct labels prove that the teacher is not a function of the clone's
input.  This is an observability test, not a placement experiment; the live
episode is never advanced from a counterfactual state.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import Action, ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import greedy_action_policy  # noqa: E402
from rl.opponents import FAST8, _strength  # noqa: E402
from rl.search import best_item_prefix  # noqa: E402


def observations_equal(left, right) -> bool:
    if isinstance(left, dict):
        return (
            isinstance(right, dict)
            and left.keys() == right.keys()
            and all(np.array_equal(left[key], right[key]) for key in left)
        )
    return np.array_equal(left, right)


def first_equip_label(
    env: TFTEnv, rng_seed: int, *, state_seeded: bool = True
) -> tuple[int, dict]:
    """Convert the search prefix (including its empty fallback) to an action."""
    player = env.player
    space = env.action_space_helper
    assert env.match is not None
    prefix, diagnostics = best_item_prefix(
        player,
        env.match,
        random.Random(rng_seed),
        depth=1,
        panel_size=2,
        trials=2,
        max_items=space.item_bag_slots,
        state_seeded=state_seeded,
    )
    if prefix:
        item_index, target_hex = prefix[0]
    else:
        targets = [
            (hex_, unit)
            for hex_, unit in player.board.items()
            if len(unit.items) < player.config.max_items_per_unit
            and player.can_equip_from_bag(player.item_bag[0].id, unit)
        ]
        if not targets:
            raise RuntimeError("teacher produced no searchable or fallback equip")
        target_hex, _unit = max(targets, key=lambda pair: _strength(pair[1]))
        item_index = 0
    action = Action(
        ActionKind.EQUIP,
        item_index,
        space.slot_for_hex(target_hex),
    )
    return space.encode(action), diagnostics


def probe_state(env: TFTEnv, rng_seed: int) -> dict:
    """Vary only bag item identity and group byte-identical inputs by label."""
    player = env.player
    original_item = player.item_bag[0]
    reference_observation = env._observe()
    reference_mask = env.action_masks().copy()
    groups: dict[int, list[dict]] = {}
    observation_changes = 0
    mask_changes = 0
    candidates = 0
    try:
        for item in sorted(env.data.items.values(), key=lambda candidate: candidate.id):
            # Components are naturally bagged and reachable.  Excluding unique
            # items also avoids using a mask difference as an identity side-channel.
            if not item.is_component or item.unique:
                continue
            candidates += 1
            player.item_bag[0] = item
            observation = env._observe()
            mask = env.action_masks()
            observation_changed = not observations_equal(
                reference_observation, observation
            )
            mask_changed = not np.array_equal(reference_mask, mask)
            observation_changes += observation_changed
            mask_changes += mask_changed
            if observation_changed or mask_changed:
                continue
            label, diagnostics = first_equip_label(env, rng_seed)
            decoded = env.action_space_helper.decode(label)
            target_hex = env.action_space_helper.hex_for_slot(decoded.b)
            groups.setdefault(label, []).append(
                {
                    "item_id": item.id,
                    "target": [target_hex.q, target_hex.r],
                    "bag_index": decoded.a,
                    "candidate_boards": diagnostics["candidate_boards"],
                }
            )
    finally:
        player.item_bag[0] = original_item

    return {
        "reference_item_id": original_item.id,
        "components_considered": candidates,
        "observation_changes": observation_changes,
        "mask_changes": mask_changes,
        "identical_input_candidates": sum(map(len, groups.values())),
        "distinct_labels": len(groups),
        "label_groups": {str(label): rows for label, rows in groups.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--search-seed", type=int, default=987_654_321)
    parser.add_argument("--rng-trials", type=int, default=64)
    args = parser.parse_args()

    data = load_all()
    audited_states = []
    collision = None
    rng_audit = None
    for seed in range(args.seed, args.seed + args.games):
        env = TFTEnv(data=data, max_actions_per_round=600, scouting="tokens")
        observation, _ = env.reset(seed=seed)
        policy = greedy_action_policy(env, econ=FAST8)
        for step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            if env.action_space_helper.decode(action).kind is ActionKind.EQUIP:
                candidate = probe_state(env, args.search_seed)
                candidate.update(
                    {"seed": seed, "round": str(env.match.round_id), "step": step}
                )
                audited_states.append(candidate)
                candidate_boards = max(
                    (
                        row["candidate_boards"]
                        for rows in candidate["label_groups"].values()
                        for row in rows
                    ),
                    default=0,
                )
                if rng_audit is None and candidate_boards > 1:
                    stream_labels: dict[int, list[int]] = {}
                    for rng_seed in range(args.rng_trials):
                        label, _diagnostics = first_equip_label(
                            env, rng_seed, state_seeded=False
                        )
                        stream_labels.setdefault(label, []).append(rng_seed)
                    # Record the first state that demonstrates the old
                    # one-to-many map, not merely the first searchable state.
                    if len(stream_labels) > 1:
                        state_labels: dict[int, list[int]] = {}
                        for rng_seed in range(args.rng_trials):
                            label, _diagnostics = first_equip_label(
                                env, rng_seed, state_seeded=True
                            )
                            state_labels.setdefault(label, []).append(rng_seed)
                        rng_audit = {
                            "seed": seed,
                            "round": str(env.match.round_id),
                            "trials": args.rng_trials,
                            "label_groups": {
                                "stream": stream_labels,
                                "state": state_labels,
                            },
                        }
                if candidate["distinct_labels"] > 1:
                    collision = candidate
                    break
            observation, _reward, terminated, truncated, _info = env.step(action)
            if terminated or truncated:
                break
        if collision is not None:
            break

    payload = {
        "scouting": "tokens",
        "games_budgeted": args.games,
        "collision_found": collision is not None,
        "collision": collision,
        "rng_audit": rng_audit,
        "audited_states": audited_states,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
