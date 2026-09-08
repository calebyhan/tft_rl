"""Scaled ensemble gate for dense item-value distillation (doc 99 160.125)."""

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
from scripts.item_dense_value_probe import (  # noqa: E402
    collect,
    dataset_summary,
    fit_dense,
    stack_rows,
)
from scripts.item_equip_head_probe import (  # noqa: E402
    RelationalEquipHead,
    baseline_metrics,
    parameters,
    tensors,
)
from scripts.item_residual_probe import THRESHOLDS  # noqa: E402


def _t_critical_975(degrees_of_freedom: int) -> float:
    """Cornish-Fisher expansion of the two-sided 95% Student-t critical."""
    z = 1.959963984540054
    df = float(degrees_of_freedom)
    return (
        z
        + (z**3 + z) / (4 * df)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
        + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
    )


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
        "scripts/item_dense_scale_probe.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def model_scores(model, dataset: dict) -> np.ndarray:
    device = next(model.parameters()).device
    observations, _legal, _labels = tensors(dataset, device)
    masks = torch.as_tensor(dataset["candidate_masks"], device=device)
    model.eval()
    with torch.no_grad():
        scores = model(observations).masked_fill(~masks, -1e9)
    return scores.cpu().numpy()


def residual_predictions(
    scores: np.ndarray, dataset: dict, threshold: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    candidates = dataset["candidate_masks"]
    stable = scores - scores.max(axis=1, keepdims=True)
    exponent = np.exp(stable) * candidates
    probabilities = exponent / exponent.sum(axis=1, keepdims=True)
    proposed = scores.argmax(axis=1)
    rows = np.arange(len(proposed))
    shipped = dataset["shipped"]
    advantage = probabilities[rows, proposed] - probabilities[rows, shipped]
    override = (proposed != shipped) & (advantage >= threshold)
    return np.where(override, proposed, shipped), override, proposed


def value_metrics(scores: np.ndarray, dataset: dict, threshold: float) -> dict:
    prediction, override, proposed = residual_predictions(
        scores, dataset, threshold
    )
    rows = np.arange(len(prediction))
    targets = dataset["targets"]
    candidate_mask = dataset["candidate_masks"]
    labels = dataset["labels"]
    changed = dataset["changed"]
    shipped = dataset["shipped"]
    selected = targets[rows, prediction]
    shipped_value = targets[rows, shipped]
    advantage = selected - shipped_value
    best = np.where(candidate_mask, targets, -np.inf).max(axis=1)
    available = best - shipped_value
    correct = prediction == labels

    episode_values = np.asarray(
        [
            advantage[dataset["episode_seeds"] == episode].mean()
            for episode in np.unique(dataset["episode_seeds"])
        ]
    )
    mean_episode = float(episode_values.mean())
    if len(episode_values) > 1:
        sem = float(episode_values.std(ddof=1) / math.sqrt(len(episode_values)))
        critical = _t_critical_975(len(episode_values) - 1)
        ci = [mean_episode - critical * sem, mean_episode + critical * sem]
    else:
        ci = [math.nan, math.nan]

    def mean(values: np.ndarray) -> float:
        return float(values.mean()) if len(values) else math.nan

    mean_available = mean(available)
    return {
        "threshold": threshold,
        "mean_value_advantage": mean(advantage),
        "episode_mean_value_advantage": mean_episode,
        "episode_value_ci95": ci,
        "teacher_available_advantage": mean_available,
        "fraction_available_captured": (
            mean(advantage) / mean_available if mean_available > 0 else math.nan
        ),
        "value_optimal_rate": mean(np.isclose(selected, best)),
        "accuracy": mean(correct),
        "changed_accuracy": mean(correct[changed]),
        "override_rows": int(override.sum()),
        "override_coverage": mean(override),
        "changed_override_coverage": mean(override[changed]),
        "override_precision": mean(correct[override]),
        "changed_override_precision": mean(correct[override & changed]),
        "unconditional_accuracy": mean(proposed == labels),
        "unconditional_changed_accuracy": mean(proposed[changed] == labels[changed]),
    }


def choose_threshold(scores: np.ndarray, dataset: dict) -> tuple[float, list[dict]]:
    grid = [value_metrics(scores, dataset, threshold) for threshold in THRESHOLDS]
    selected = max(
        grid,
        key=lambda row: (row["mean_value_advantage"], row["threshold"]),
    )
    return float(selected["threshold"]), grid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=320)
    parser.add_argument("--calibration-games", type=int, default=80)
    parser.add_argument("--test-games", type=int, default=80)
    parser.add_argument("--fit-seed", type=int, default=65_000)
    parser.add_argument("--calibration-seed", type=int, default=66_000)
    parser.add_argument("--test-seed", type=int, default=67_000)
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
    individual = []
    calibration_scores = []
    test_scores = []
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
        fit_calibration_scores = model_scores(model, calibration)
        fit_test_scores = model_scores(model, test)
        threshold, calibration_grid = choose_threshold(
            fit_calibration_scores, calibration
        )
        individual.append(
            {
                "seed": fit_seed,
                "parameters": parameters(model),
                "threshold": threshold,
                "calibration_grid": calibration_grid,
                "test": value_metrics(fit_test_scores, test, threshold),
            }
        )
        calibration_scores.append(fit_calibration_scores)
        test_scores.append(fit_test_scores)

    ensemble_calibration = np.mean(calibration_scores, axis=0)
    ensemble_test = np.mean(test_scores, axis=0)
    ensemble_threshold, ensemble_grid = choose_threshold(
        ensemble_calibration, calibration
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
        "individual": individual,
        "ensemble": {
            "threshold": ensemble_threshold,
            "calibration_grid": ensemble_grid,
            "test": value_metrics(ensemble_test, test, ensemble_threshold),
        },
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
