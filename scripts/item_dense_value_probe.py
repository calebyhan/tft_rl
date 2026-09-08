"""Learn the item teacher from every searched candidate value (doc 99 160.123)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402
from scripts.item_equip_head_probe import (  # noqa: E402
    RelationalEquipHead,
    _shipped_equip_label,
    baseline_metrics,
    parameters,
    tensors,
)
from scripts.item_residual_probe import (  # noqa: E402
    choose_threshold,
    prediction_metrics,
    unconditional_metrics,
)

_DATA = None


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/player.py",
        "engine/unit.py",
        "rl/action.py",
        "rl/env.py",
        "rl/greedy_action.py",
        "rl/observation.py",
        "rl/scout_policy.py",
        "rl/search.py",
        "scripts/item_equip_head_probe.py",
        "scripts/item_residual_probe.py",
        "scripts/item_dense_value_probe.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    _DATA = load_all()


def collect_episode(seed: int) -> dict:
    data = _DATA if _DATA is not None else load_all()
    env = TFTEnv(data=data, scouting="tokens", max_actions_per_round=600)
    policy = search_item_greedy_policy(
        env,
        econ=FAST8,
        rng_seed=seed + SEARCH_SEED_OFFSET,
        depth=1,
        panel_size=2,
        trials=2,
    )
    observation, _ = env.reset(seed=seed)
    rows = []
    searched_no_equip = 0
    for _step in range(200_000):
        action_mask = env.action_masks()
        before = dict(policy.item_search_stats)
        action = int(policy(observation, action_mask))
        after = policy.item_search_stats
        if after["search_decisions"] > before["search_decisions"]:
            decoded = env.action_space_helper.decode(action)
            if decoded.kind is not ActionKind.EQUIP:
                searched_no_equip += 1
            else:
                space = env.action_space_helper
                n_actions = space.item_bag_slots * space.unit_slots
                legal = action_mask[
                    space.equip_offset:space.augment_offset
                ].reshape(-1)
                shipped = _shipped_equip_label(env)
                raw_by_action: dict[int, float] = {}
                baseline = None
                for prefix, value in policy.item_search_trace:
                    if prefix:
                        token, own_hex = prefix[0]
                        relative = token * space.unit_slots + space.slot_for_hex(
                            own_hex
                        )
                    else:
                        relative = shipped
                        baseline = value
                    raw_by_action[relative] = max(
                        value, raw_by_action.get(relative, -np.inf)
                    )
                if baseline is None:
                    raise AssertionError("searched item trace has no baseline")
                candidate_values = np.asarray(list(raw_by_action.values()))
                scale = max(float(candidate_values.std()), 1.0)
                targets = np.zeros(n_actions, dtype=np.float32)
                candidates = np.zeros(n_actions, dtype=bool)
                for relative, value in raw_by_action.items():
                    if not legal[relative]:
                        raise AssertionError("search produced an illegal EQUIP")
                    candidates[relative] = True
                    targets[relative] = (value - baseline) / scale
                label = action - space.equip_offset
                if not candidates[label]:
                    raise AssertionError("teacher action absent from dense candidates")
                best_value = max(raw_by_action.values())
                rows.append(
                    {
                        "observation": {
                            name: value.copy()
                            for name, value in observation.items()
                        },
                        "mask": legal.copy(),
                        "candidate_mask": candidates,
                        "targets": targets,
                        "label": label,
                        "changed": after["changed_layouts"]
                        > before["changed_layouts"],
                        "shipped": shipped,
                        "candidate_count": int(candidates.sum()),
                        "winner_ties": sum(
                            value == best_value for value in raw_by_action.values()
                        ),
                        "episode_seed": seed,
                    }
                )
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    return {"rows": rows, "searched_no_equip": searched_no_equip}


def collect(seeds: range, workers: int) -> tuple[list[dict], dict]:
    context = get_context("spawn")
    with context.Pool(workers, initializer=_init_worker) as pool:
        episodes = pool.map(collect_episode, seeds, chunksize=1)
    rows = [row for episode in episodes for row in episode["rows"]]
    return rows, {
        "games": len(episodes),
        "searched_no_equip": sum(
            episode["searched_no_equip"] for episode in episodes
        ),
    }


def stack_rows(rows: list[dict]) -> dict:
    if not rows:
        raise RuntimeError("no dense item decisions collected")
    names = rows[0]["observation"]
    return {
        "observations": {
            name: np.stack([row["observation"][name] for row in rows])
            for name in names
        },
        "masks": np.stack([row["mask"] for row in rows]),
        "candidate_masks": np.stack([row["candidate_mask"] for row in rows]),
        "targets": np.stack([row["targets"] for row in rows]),
        "labels": np.asarray([row["label"] for row in rows], dtype=np.int64),
        "changed": np.asarray([row["changed"] for row in rows], dtype=bool),
        "shipped": np.asarray([row["shipped"] for row in rows], dtype=np.int64),
        "candidate_counts": np.asarray([row["candidate_count"] for row in rows]),
        "winner_ties": np.asarray([row["winner_ties"] for row in rows]),
        "episode_seeds": np.asarray([row["episode_seed"] for row in rows]),
    }


def fit_dense(
    model,
    train: dict,
    *,
    seed: int,
    epochs: int,
    batch_size: int,
) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device("cpu")
    model.to(device)
    observations, _legal, _labels = tensors(train, device)
    masks = torch.as_tensor(train["candidate_masks"], device=device)
    targets = torch.as_tensor(train["targets"], device=device)
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = torch.Generator().manual_seed(seed)
    for _epoch in range(epochs):
        order = torch.randperm(len(targets), generator=generator)
        model.train()
        for start in range(0, len(order), batch_size):
            selected = order[start:start + batch_size]
            batch = {name: value[selected] for name, value in observations.items()}
            errors = (model(batch) - targets[selected]).square()
            loss = errors[masks[selected]].mean()
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()


def model_outputs(model, dataset: dict) -> tuple[np.ndarray, np.ndarray]:
    device = next(model.parameters()).device
    observations, _legal, _labels = tensors(dataset, device)
    masks = torch.as_tensor(dataset["candidate_masks"], device=device)
    model.eval()
    with torch.no_grad():
        logits = model(observations).masked_fill(~masks, -1e9)
        probabilities = logits.softmax(dim=-1)
        proposed = logits.argmax(dim=-1)
        rows = torch.arange(len(proposed), device=device)
        shipped = torch.as_tensor(dataset["shipped"], device=device)
        advantage = probabilities[rows, proposed] - probabilities[rows, shipped]
    return proposed.cpu().numpy(), advantage.cpu().numpy()


def dataset_summary(dataset: dict, collection: dict) -> dict:
    counts = dataset["candidate_counts"]
    ties = dataset["winner_ties"]
    return {
        "rows": len(counts),
        "changed_rows": int(dataset["changed"].sum()),
        "classes": len(set(dataset["labels"].tolist())),
        "candidate_targets": int(counts.sum()),
        "mean_candidates": float(counts.mean()),
        "multiwinner_rows": int((ties > 1).sum()),
        "mean_winner_ties": float(ties.mean()),
        "collection": collection,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=80)
    parser.add_argument("--calibration-games", type=int, default=40)
    parser.add_argument("--test-games", type=int, default=40)
    parser.add_argument("--fit-seed", type=int, default=62_000)
    parser.add_argument("--calibration-seed", type=int, default=63_000)
    parser.add_argument("--test-seed", type=int, default=64_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    train_rows, train_collection = collect(
        range(args.fit_seed, args.fit_seed + args.fit_games), args.workers
    )
    calibration_rows, calibration_collection = collect(
        range(
            args.calibration_seed,
            args.calibration_seed + args.calibration_games,
        ),
        args.workers,
    )
    test_rows, test_collection = collect(
        range(args.test_seed, args.test_seed + args.test_games), args.workers
    )
    train = stack_rows(train_rows)
    calibration = stack_rows(calibration_rows)
    test = stack_rows(test_rows)

    env = TFTEnv(load_all(), scouting="tokens", max_actions_per_round=600)
    results = []
    for fit_seed in range(args.fits):
        torch.manual_seed(fit_seed)
        model = RelationalEquipHead(
            env.observation_space,
            env.encoder.spec,
            env.config.max_items_per_unit,
        )
        fit_dense(
            model,
            train,
            seed=fit_seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
        calibration_proposed, calibration_advantage = model_outputs(
            model, calibration
        )
        threshold, calibration_grid = choose_threshold(
            calibration, calibration_proposed, calibration_advantage
        )
        test_proposed, test_advantage = model_outputs(model, test)
        train_proposed, _train_advantage = model_outputs(model, train)
        results.append(
            {
                "seed": fit_seed,
                "parameters": parameters(model),
                "threshold": threshold,
                "train": unconditional_metrics(train, train_proposed),
                "calibration_unconditional": unconditional_metrics(
                    calibration, calibration_proposed
                ),
                "calibration_grid": calibration_grid,
                "test_unconditional": unconditional_metrics(test, test_proposed),
                "test_residual": prediction_metrics(
                    test, test_proposed, test_advantage, threshold
                ),
            }
        )

    payload = {
        "source_fingerprint": before,
        "config": vars(args) | {"json": str(args.json) if args.json else None},
        "datasets": {
            "fit": dataset_summary(train, train_collection),
            "calibration": dataset_summary(
                calibration, calibration_collection
            ),
            "test": dataset_summary(test, test_collection),
        },
        "test_baselines": baseline_metrics(test),
        "models": results,
    }
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
