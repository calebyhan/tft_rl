"""Bounded BC gate for the token scout state (doc 99 entry 160).

This is intentionally a small feasibility probe, not a PPO run or a placement
claim.  Its teacher and token policy are constructed fresh for each episode so
the search RNG stream matches the direct teacher's per-match lifetime.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.scout_policy import ScoutSetExtractor  # noqa: E402
from rl.search import search_buy_greedy_policy  # noqa: E402


def _copy_observation(observation: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {name: value.copy() for name, value in observation.items()}


def collect(data, seeds: range) -> dict:
    """Collect search-teacher labels with one policy/RNG stream per episode."""
    observations: dict[str, list[np.ndarray]] = defaultdict(list)
    masks, actions, families = [], [], []
    for seed in seeds:
        env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
        teacher = search_buy_greedy_policy(env, econ=FAST8)
        env.register_external_policy(teacher)
        observation, _ = env.reset(seed=seed)
        terminated = False
        while not terminated:
            mask = env.action_masks()
            action = teacher(observation, mask)
            if not mask[action]:
                raise AssertionError(f"teacher emitted illegal action {action} on seed {seed}")
            for name, value in _copy_observation(observation).items():
                observations[name].append(value)
            masks.append(mask.copy())
            actions.append(action)
            kind = env.action_space_helper.decode(action).kind.name
            families.append(
                "SEARCH_BUY"
                if kind == "BUY" and teacher.last_search_buy_slot is not None
                else kind
            )
            observation, _reward, terminated, truncated, _info = env.step(action)
            terminated = terminated or truncated
    return {
        "observations": {name: np.stack(rows) for name, rows in observations.items()},
        "masks": np.stack(masks),
        "actions": np.asarray(actions, dtype=np.int64),
        "families": np.asarray(families),
    }


def _tensors(dataset: dict, rows, device):
    return (
        {
            name: torch.as_tensor(values[rows], device=device)
            for name, values in dataset["observations"].items()
        },
        torch.as_tensor(dataset["masks"][rows], dtype=torch.bool, device=device),
        torch.as_tensor(dataset["actions"][rows], dtype=torch.long, device=device),
    )


def action_match(model, dataset: dict) -> dict[str, dict[str, float | int]]:
    rows = np.arange(len(dataset["actions"]))
    observations, masks, labels = _tensors(dataset, rows, model.device)
    with torch.no_grad():
        distribution = model.policy.get_distribution(observations, action_masks=masks)
        predicted = distribution.distribution.logits.argmax(dim=-1).cpu().numpy()
    result: dict[str, dict[str, float | int]] = {}
    for family in sorted(set(dataset["families"])):
        family_rows = dataset["families"] == family
        result[family] = {
            "n": int(family_rows.sum()),
            "match": float((predicted[family_rows] == dataset["actions"][family_rows]).mean()),
        }
    result["ALL"] = {"n": len(predicted), "match": float((predicted == dataset["actions"]).mean())}
    return result


def fit(model, dataset: dict, epochs: int, batch_size: int, learning_rate: float) -> list[dict]:
    optimiser = torch.optim.AdamW(model.policy.parameters(), lr=learning_rate)
    count = len(dataset["actions"])
    history = []
    for epoch in range(epochs):
        order = np.random.permutation(count)
        losses = []
        for start in range(0, count, batch_size):
            rows = order[start : start + batch_size]
            observations, masks, labels = _tensors(dataset, rows, model.device)
            distribution = model.policy.get_distribution(observations, action_masks=masks)
            loss = -distribution.log_prob(labels).mean()
            optimiser.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.policy.parameters(), model.max_grad_norm)
            optimiser.step()
            losses.append(float(loss.detach()))
        history.append({"epoch": epoch + 1, "loss": float(np.mean(losses))})
    return history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-episodes", type=int, default=4)
    parser.add_argument("--holdout-episodes", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--holdout-offset", type=int, default=10_000)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    np.random.seed(args.seed)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    data = load_all()
    train = collect(data, range(args.seed, args.seed + args.train_episodes))
    holdout = collect(
        data,
        range(args.holdout_offset, args.holdout_offset + args.holdout_episodes),
    )

    from sb3_contrib import MaskablePPO

    model_env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
    model = MaskablePPO(
        "MultiInputPolicy",
        model_env,
        n_steps=64,
        batch_size=64,
        seed=args.seed,
        device="cpu",
        policy_kwargs={"features_extractor_class": ScoutSetExtractor},
    )
    before = {"train": action_match(model, train), "holdout": action_match(model, holdout)}
    history = fit(model, train, args.epochs, args.batch_size, args.learning_rate)
    after = {"train": action_match(model, train), "holdout": action_match(model, holdout)}
    payload = {
        "train_transitions": len(train["actions"]),
        "holdout_transitions": len(holdout["actions"]),
        "epochs": args.epochs,
        "before": before,
        "after": after,
        "history": history,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
