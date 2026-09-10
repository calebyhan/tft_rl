"""Learn when the frozen dense item ensemble should override shipped (160.129)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from scripts.item_dense_placement_ab import load_models  # noqa: E402
from scripts.item_dense_scale_probe import (  # noqa: E402
    _t_critical_975,
    model_scores,
)
from scripts.item_dense_value_probe import (  # noqa: E402
    collect,
    dataset_summary,
    stack_rows,
)

COVERAGES = tuple(value / 20 for value in range(21))


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
        "scripts/item_dense_placement_ab.py",
        "scripts/item_advantage_gate_probe.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _probabilities(scores: np.ndarray, masks: np.ndarray) -> np.ndarray:
    stable = scores - scores.max(axis=1, keepdims=True)
    exponent = np.exp(stable) * masks
    return exponent / exponent.sum(axis=1, keepdims=True)


def gate_examples(models, dataset: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scores = np.stack([model_scores(model, dataset) for model in models])
    ensemble = scores.mean(axis=0)
    proposed = ensemble.argmax(axis=1)
    shipped = dataset["shipped"]
    rows = np.arange(len(proposed))
    features = []
    for head_scores in scores:
        probabilities = _probabilities(head_scores, dataset["candidate_masks"])
        features.extend(
            (
                head_scores[rows, proposed] - head_scores[rows, shipped],
                probabilities[rows, proposed] - probabilities[rows, shipped],
                (head_scores.argmax(axis=1) == proposed).astype(np.float32),
            )
        )
    ensemble_probabilities = _probabilities(
        ensemble, dataset["candidate_masks"]
    )
    features.extend(
        (
            ensemble[rows, proposed] - ensemble[rows, shipped],
            ensemble_probabilities[rows, proposed]
            - ensemble_probabilities[rows, shipped],
            dataset["candidate_counts"].astype(np.float32),
        )
    )
    targets = (
        dataset["targets"][rows, proposed]
        - dataset["targets"][rows, shipped]
    )
    return np.stack(features, axis=1).astype(np.float32), targets, proposed


class AdvantageGate(nn.Module):
    def __init__(self, n_features: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(n_features, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(-1)


def fit_gate(
    features: np.ndarray,
    targets: np.ndarray,
    *,
    seed: int,
    epochs: int,
    batch_size: int,
) -> AdvantageGate:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    x = torch.as_tensor(features)
    y = torch.as_tensor(targets)
    model = AdvantageGate(features.shape[1])
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = torch.Generator().manual_seed(seed)
    for _epoch in range(epochs):
        order = torch.randperm(len(y), generator=generator)
        model.train()
        for start in range(0, len(order), batch_size):
            rows = order[start:start + batch_size]
            loss = nn.functional.smooth_l1_loss(model(x[rows]), y[rows])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
    model.eval()
    return model


def gate_predictions(models, features: np.ndarray) -> np.ndarray:
    x = torch.as_tensor(features)
    with torch.no_grad():
        return torch.stack([model(x) for model in models]).mean(0).numpy()


def threshold_for_coverage(
    predictions: np.ndarray,
    eligible: np.ndarray,
    coverage: float,
) -> float:
    count = min(round(coverage * len(predictions)), int(eligible.sum()))
    if count <= 0:
        return math.inf
    ordered = np.sort(predictions[eligible])[::-1]
    return float(ordered[count - 1])


def metrics(
    dataset: dict,
    proposed: np.ndarray,
    true_advantage: np.ndarray,
    predictions: np.ndarray,
    threshold: float,
) -> dict:
    shipped = dataset["shipped"]
    eligible = proposed != shipped
    override = eligible & (predictions >= threshold)
    selected_action = np.where(override, proposed, shipped)
    selected_value = np.where(override, true_advantage, 0.0)
    rows = np.arange(len(proposed))
    best_value = np.where(
        dataset["candidate_masks"], dataset["targets"], -np.inf
    ).max(axis=1)
    actual_value = dataset["targets"][rows, selected_action]
    labels = dataset["labels"]
    changed = dataset["changed"]
    correct = selected_action == labels
    episodes = np.unique(dataset["episode_seeds"])
    episode_means = np.asarray(
        [
            selected_value[dataset["episode_seeds"] == episode].mean()
            for episode in episodes
        ]
    )
    episode_mean = float(episode_means.mean())
    if len(episode_means) > 1:
        sem = float(episode_means.std(ddof=1) / math.sqrt(len(episode_means)))
        critical = _t_critical_975(len(episode_means) - 1)
        ci = [episode_mean - critical * sem, episode_mean + critical * sem]
    else:
        ci = [math.nan, math.nan]
    available = float(best_value.mean())

    def mean(values: np.ndarray) -> float:
        return float(values.mean()) if len(values) else math.nan

    return {
        "score_threshold": threshold,
        "mean_value_advantage": mean(selected_value),
        "episode_mean_value_advantage": episode_mean,
        "episode_value_ci95": ci,
        "teacher_available_advantage": available,
        "fraction_available_captured": (
            mean(selected_value) / available if available > 0 else math.nan
        ),
        "value_optimal_rate": mean(np.isclose(actual_value, best_value)),
        "accuracy": mean(correct),
        "changed_accuracy": mean(correct[changed]),
        "override_rows": int(override.sum()),
        "override_coverage": mean(override),
        "changed_override_coverage": mean(override[changed]),
        "positive_value_precision": mean(true_advantage[override] > 0),
        "mean_override_value": mean(true_advantage[override]),
    }


def calibrate(
    dataset: dict,
    proposed: np.ndarray,
    true_advantage: np.ndarray,
    predictions: np.ndarray,
) -> tuple[dict, list[dict]]:
    eligible = proposed != dataset["shipped"]
    grid = []
    for coverage in COVERAGES:
        threshold = threshold_for_coverage(predictions, eligible, coverage)
        row = metrics(
            dataset, proposed, true_advantage, predictions, threshold
        )
        row["requested_coverage"] = coverage
        grid.append(row)
    selected = max(
        grid,
        key=lambda row: (
            row["mean_value_advantage"],
            -row["requested_coverage"],
        ),
    )
    return selected, grid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=320)
    parser.add_argument("--calibration-games", type=int, default=80)
    parser.add_argument("--test-games", type=int, default=80)
    parser.add_argument("--fit-seed", type=int, default=69_000)
    parser.add_argument("--calibration-seed", type=int, default=70_000)
    parser.add_argument("--test-seed", type=int, default=71_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument(
        "--action-checkpoint",
        type=Path,
        default=REPO_ROOT / "runs/item_dense_ensemble_160_127.pt",
    )
    parser.add_argument("--checkpoint-sha", default="5d30b6e11e15")
    parser.add_argument("--gate-checkpoint", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    checkpoint_sha = hashlib.sha256(args.action_checkpoint.read_bytes()).hexdigest()[:12]
    if checkpoint_sha != args.checkpoint_sha:
        raise RuntimeError(
            f"action checkpoint changed: {checkpoint_sha} != {args.checkpoint_sha}"
        )
    checkpoint = torch.load(
        args.action_checkpoint, map_location="cpu", weights_only=True
    )
    env = TFTEnv(load_all(), scouting="tokens", max_actions_per_round=600)
    action_models = load_models(checkpoint, env)

    datasets = {}
    collections = {}
    for name, seed, games in (
        ("fit", args.fit_seed, args.fit_games),
        ("calibration", args.calibration_seed, args.calibration_games),
        ("test", args.test_seed, args.test_games),
    ):
        print(f"collecting {name}: seeds {seed}..{seed + games - 1}", flush=True)
        rows, collections[name] = collect(range(seed, seed + games), args.workers)
        datasets[name] = stack_rows(rows)

    examples = {
        name: gate_examples(action_models, dataset)
        for name, dataset in datasets.items()
    }
    fit_features = examples["fit"][0]
    feature_mean = fit_features.mean(axis=0)
    feature_std = fit_features.std(axis=0)
    feature_std[feature_std < 1e-6] = 1.0

    def standardized(name: str) -> np.ndarray:
        return (examples[name][0] - feature_mean) / feature_std

    gates = [
        fit_gate(
            standardized("fit"),
            examples["fit"][1],
            seed=seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
        for seed in range(args.fits)
    ]
    calibration_predictions = gate_predictions(
        gates, standardized("calibration")
    )
    selected, calibration_grid = calibrate(
        datasets["calibration"],
        examples["calibration"][2],
        examples["calibration"][1],
        calibration_predictions,
    )
    test_predictions = gate_predictions(gates, standardized("test"))
    test = metrics(
        datasets["test"],
        examples["test"][2],
        examples["test"][1],
        test_predictions,
        selected["score_threshold"],
    )
    ungated = metrics(
        datasets["test"],
        examples["test"][2],
        examples["test"][1],
        np.ones(len(test_predictions)),
        0.0,
    )
    payload = {
        "source_fingerprint": before,
        "action_checkpoint": str(args.action_checkpoint),
        "action_checkpoint_sha": checkpoint_sha,
        "config": vars(args)
        | {
            "action_checkpoint": str(args.action_checkpoint),
            "gate_checkpoint": (
                str(args.gate_checkpoint) if args.gate_checkpoint else None
            ),
            "json": str(args.json) if args.json else None,
        },
        "datasets": {
            name: dataset_summary(dataset, collections[name])
            for name, dataset in datasets.items()
        },
        "fit_target": {
            "mean": float(examples["fit"][1].mean()),
            "positive_rate": float((examples["fit"][1] > 0).mean()),
        },
        "calibration_selected": selected,
        "calibration_grid": calibration_grid,
        "test_ungated": ungated,
        "test_gated": test,
    }
    if args.gate_checkpoint:
        args.gate_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "source_fingerprint": before,
                "action_checkpoint_sha": checkpoint_sha,
                "feature_mean": feature_mean,
                "feature_std": feature_std,
                "score_threshold": selected["score_threshold"],
                "requested_coverage": selected["requested_coverage"],
                "model_states": [gate.state_dict() for gate in gates],
            },
            args.gate_checkpoint,
        )
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
