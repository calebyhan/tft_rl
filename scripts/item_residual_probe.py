"""Calibrate a conservative residual override for the relational EQUIP head.

This is the offline gate predeclared in doc 99 entry 160.121. Whole episodes
are split into fit, calibration, and untouched test sets. No learned model
drives an environment and no placement result is produced.

    .venv/bin/python scripts/item_residual_probe.py --workers 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from scripts.item_equip_head_probe import (  # noqa: E402
    RelationalEquipHead,
    baseline_metrics,
    collect_with_diagnostics,
    dataset_summary,
    fit,
    parameters,
    stack_rows,
    tensors,
)

THRESHOLDS = tuple(round(value * 0.05, 2) for value in range(20)) + (1.01,)


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
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def model_outputs(model, dataset: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return proposed actions and their probability advantage over shipped."""
    device = next(model.parameters()).device
    observations, masks, _labels = tensors(dataset, device)
    model.eval()
    with torch.no_grad():
        logits = model(observations).masked_fill(~masks, -1e9)
        probabilities = logits.softmax(dim=-1)
        proposed = probabilities.argmax(dim=-1)
        rows = torch.arange(len(proposed), device=device)
        shipped = torch.as_tensor(dataset["shipped"], device=device)
        advantage = probabilities[rows, proposed] - probabilities[rows, shipped]
    return proposed.cpu().numpy(), advantage.cpu().numpy()


def prediction_metrics(
    dataset: dict,
    proposed: np.ndarray,
    advantage: np.ndarray,
    threshold: float,
) -> dict[str, float | int]:
    labels = dataset["labels"]
    shipped = dataset["shipped"]
    changed = dataset["changed"]
    override = (proposed != shipped) & (advantage >= threshold)
    prediction = np.where(override, proposed, shipped)
    correct = prediction == labels

    def mean(values: np.ndarray) -> float:
        return float(values.mean()) if len(values) else math.nan

    return {
        "threshold": threshold,
        "accuracy": mean(correct),
        "changed_accuracy": mean(correct[changed]),
        "override_rows": int(override.sum()),
        "override_coverage": mean(override),
        "changed_override_coverage": mean(override[changed]),
        "override_precision": mean(correct[override]),
        "changed_override_precision": mean(correct[override & changed]),
    }


def unconditional_metrics(dataset: dict, proposed: np.ndarray) -> dict[str, float]:
    correct = proposed == dataset["labels"]
    changed = dataset["changed"]
    return {
        "accuracy": float(correct.mean()),
        "changed_accuracy": float(correct[changed].mean()),
    }


def choose_threshold(
    dataset: dict, proposed: np.ndarray, advantage: np.ndarray
) -> tuple[float, list[dict[str, float | int]]]:
    grid = [
        prediction_metrics(dataset, proposed, advantage, threshold)
        for threshold in THRESHOLDS
    ]
    best = max(grid, key=lambda row: (row["accuracy"], row["threshold"]))
    return float(best["threshold"]), grid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=80)
    parser.add_argument("--calibration-games", type=int, default=40)
    parser.add_argument("--test-games", type=int, default=40)
    parser.add_argument("--fit-seed", type=int, default=59_000)
    parser.add_argument("--calibration-seed", type=int, default=60_000)
    parser.add_argument("--test-seed", type=int, default=61_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    train_rows, train_collection = collect_with_diagnostics(
        range(args.fit_seed, args.fit_seed + args.fit_games), args.workers
    )
    train = stack_rows(train_rows)
    calibration_rows, calibration_collection = collect_with_diagnostics(
        range(
            args.calibration_seed,
            args.calibration_seed + args.calibration_games,
        ),
        args.workers,
    )
    calibration = stack_rows(calibration_rows)
    test_rows, test_collection = collect_with_diagnostics(
        range(args.test_seed, args.test_seed + args.test_games), args.workers
    )
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
        fit(
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
        results.append(
            {
                "seed": fit_seed,
                "parameters": parameters(model),
                "threshold": threshold,
                "train": unconditional_metrics(
                    train, model_outputs(model, train)[0]
                ),
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
        "threshold_grid": THRESHOLDS,
        "datasets": {
            "fit": dataset_summary(train) | {"collection": train_collection},
            "calibration": dataset_summary(calibration)
            | {"collection": calibration_collection},
            "test": dataset_summary(test) | {"collection": test_collection},
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
