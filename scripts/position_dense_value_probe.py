"""Action-conditioned dense value distillation for positioning (160.131)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import random
import sys
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET, greedy_action_policy  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.scout_policy import ScoutSetExtractor  # noqa: E402
from rl.search import search_policy  # noqa: E402
from scripts.item_dense_scale_probe import _t_critical_975  # noqa: E402

THRESHOLDS = tuple(value / 20 for value in range(20)) + (1.01,)
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
        "scripts/position_dense_value_probe.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def collect_episode(seed: int) -> list[dict]:
    data = _DATA if _DATA is not None else load_all()
    env = TFTEnv(data=data, scouting="tokens", max_actions_per_round=600)
    trace: list = []
    policy = search_policy(
        env,
        rng_seed=seed + SEARCH_SEED_OFFSET,
        base=greedy_action_policy(env, econ=FAST8),
        mode="move",
        max_candidates=6,
        panel_size=1,
        trials=3,
        state_seeded=True,
        trace_callback=trace.extend,
    )
    env.register_external_policy(policy)
    observation, _ = env.reset(seed=seed)
    rows = []
    for _step in range(200_000):
        trace.clear()
        action = int(policy(observation, env.action_masks()))
        if trace:
            baseline_move, baseline = trace[0]
            if baseline_move is not None:
                raise AssertionError("first positional trace row is not baseline")
            moves = trace[1:]
            if len(moves) != 6:
                raise AssertionError(f"expected six move candidates, got {len(moves)}")
            raw = np.asarray([value for _move, value in trace], dtype=np.float32)
            scale = max(float(raw.std()), 1.0)
            indices = []
            for move, _value in moves:
                source, target = move
                indices.append(
                    env.action_space_helper.slot_for_hex(source) * 28
                    + env.action_space_helper.slot_for_hex(target)
                )
            targets = (raw[1:] - baseline) / scale
            rows.append(
                {
                    "observation": {
                        name: value.copy()
                        for name, value in observation.items()
                    },
                    "indices": np.asarray(indices, dtype=np.int64),
                    "targets": targets,
                    "episode_seed": seed,
                }
            )
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    return rows


def collect(seeds: range, workers: int) -> dict:
    context = get_context("spawn")
    with context.Pool(workers, initializer=_init_worker) as pool:
        episodes = pool.map(collect_episode, seeds, chunksize=1)
    rows = [row for episode in episodes for row in episode]
    if not rows:
        raise RuntimeError("position search produced no dense rows")
    names = rows[0]["observation"]
    return {
        "observations": {
            name: np.stack([row["observation"][name] for row in rows])
            for name in names
        },
        "indices": np.stack([row["indices"] for row in rows]),
        "targets": np.stack([row["targets"] for row in rows]),
        "episode_seeds": np.asarray([row["episode_seed"] for row in rows]),
    }


class RelationalMoveHead(nn.Module):
    """Shared scorer over an observed source unit and destination board slot."""

    def __init__(self, observation_space, spec, width: int = 128) -> None:
        super().__init__()
        self.context = ScoutSetExtractor(observation_space)
        self.spec = spec
        self.board_slots = spec.board_slots
        self.unit_width = spec.unit_width
        self.register_buffer("slot_one_hot", torch.eye(self.board_slots))
        local_width = 2 * self.unit_width + 2 * self.board_slots + 1
        self.score = nn.Sequential(
            nn.Linear(self.context.features_dim + local_width, width),
            nn.ReLU(),
            nn.Linear(width, width),
            nn.ReLU(),
            nn.Linear(width, 1),
        )

    def forward(
        self,
        observations: dict[str, torch.Tensor],
        indices: torch.Tensor,
    ) -> torch.Tensor:
        context = self.context(observations)
        global_observation = observations["global"].float()
        board_start = self.spec.offset_of("board")
        bench_start = self.spec.offset_of("bench")
        board = global_observation[:, board_start:bench_start].reshape(
            -1, self.board_slots, self.unit_width
        )
        source_indices = indices // self.board_slots
        target_indices = indices % self.board_slots
        batch_rows = torch.arange(len(board), device=board.device)[:, None]
        source = board[batch_rows, source_indices]
        target = board[batch_rows, target_indices]
        occupied = target.abs().sum(dim=-1, keepdim=True).gt(0).float()
        count = indices.shape[1]
        context = context[:, None, :].expand(-1, count, -1)
        local = torch.cat(
            (
                source,
                target,
                self.slot_one_hot[source_indices],
                self.slot_one_hot[target_indices],
                occupied,
            ),
            dim=-1,
        )
        return self.score(torch.cat((context, local), dim=-1)).squeeze(-1)


def _tensors(dataset: dict) -> tuple[dict, torch.Tensor, torch.Tensor]:
    return (
        {
            name: torch.as_tensor(value)
            for name, value in dataset["observations"].items()
        },
        torch.as_tensor(dataset["indices"]),
        torch.as_tensor(dataset["targets"]),
    )


def fit_head(
    model: RelationalMoveHead,
    dataset: dict,
    *,
    seed: int,
    epochs: int,
    batch_size: int,
) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    observations, indices, targets = _tensors(dataset)
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = torch.Generator().manual_seed(seed)
    for _epoch in range(epochs):
        order = torch.randperm(len(targets), generator=generator)
        model.train()
        for start in range(0, len(order), batch_size):
            selected = order[start:start + batch_size]
            batch = {name: value[selected] for name, value in observations.items()}
            loss = nn.functional.mse_loss(
                model(batch, indices[selected]), targets[selected]
            )
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
    model.eval()


def scores(models: list[RelationalMoveHead], dataset: dict) -> np.ndarray:
    observations, indices, _targets = _tensors(dataset)
    with torch.no_grad():
        return torch.stack(
            [model(observations, indices) for model in models]
        ).mean(0).numpy()


def proposed_actions(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    proposed = values.argmax(axis=1)
    stable = np.maximum(values.max(axis=1), 0.0)
    move_exp = np.exp(values - stable[:, None])
    baseline_exp = np.exp(-stable)
    denominator = move_exp.sum(axis=1) + baseline_exp
    rows = np.arange(len(values))
    advantage = move_exp[rows, proposed] / denominator - baseline_exp / denominator
    return proposed, advantage


def policy_metrics(
    dataset: dict,
    model_scores: np.ndarray,
    threshold: float,
) -> dict:
    targets = dataset["targets"]
    proposed, advantage = proposed_actions(model_scores)
    rows = np.arange(len(targets))
    override = advantage >= threshold
    selected = np.where(override, targets[rows, proposed], 0.0)
    available = np.maximum(targets.max(axis=1), 0.0)
    episodes = np.unique(dataset["episode_seeds"])
    episode_values = np.asarray(
        [
            selected[dataset["episode_seeds"] == episode].mean()
            for episode in episodes
        ]
    )
    episode_mean = float(episode_values.mean())
    if len(episode_values) > 1:
        sem = float(episode_values.std(ddof=1) / math.sqrt(len(episode_values)))
        critical = _t_critical_975(len(episode_values) - 1)
        ci = [episode_mean - critical * sem, episode_mean + critical * sem]
    else:
        ci = [math.nan, math.nan]
    mean_value = float(selected.mean())
    mean_available = float(available.mean())
    return {
        "threshold": threshold,
        "mean_value_advantage": mean_value,
        "episode_mean_value_advantage": episode_mean,
        "episode_value_ci95": ci,
        "teacher_available_advantage": mean_available,
        "fraction_available_captured": (
            mean_value / mean_available if mean_available > 0 else math.nan
        ),
        "value_optimal_rate": float(np.isclose(selected, available).mean()),
        "override_coverage": float(override.mean()),
        "positive_value_precision": (
            float((targets[rows, proposed][override] > 0).mean())
            if override.any()
            else math.nan
        ),
    }


def calibrate(dataset: dict, model_scores: np.ndarray) -> tuple[dict, list[dict]]:
    grid = [policy_metrics(dataset, model_scores, threshold) for threshold in THRESHOLDS]
    selected = max(grid, key=lambda row: (row["mean_value_advantage"], row["threshold"]))
    return selected, grid


def shortlist_metrics(dataset: dict, model_scores: np.ndarray, seed: int) -> dict:
    targets = dataset["targets"]
    rng = random.Random(seed)
    available = np.maximum(targets.max(axis=1), 0.0)
    shortlisted_values = []
    random_values = []
    for truth, guesses in zip(targets, model_scores, strict=True):
        top = np.argsort(guesses)[-3:]
        shortlisted_values.append(max(0.0, float(truth[top].max())))
        random_index = rng.randrange(len(truth) + 1)
        random_values.append(0.0 if random_index == len(truth) else truth[random_index])
    shortlisted = np.asarray(shortlisted_values)
    random_selected = np.asarray(random_values)
    random_regret = float((available - random_selected).mean())
    shortlist_regret = float((available - shortlisted).mean())
    return {
        "mean_value_advantage": float(shortlisted.mean()),
        "fraction_available_captured": float(shortlisted.mean() / available.mean()),
        "regret": shortlist_regret,
        "random_pick_regret": random_regret,
        "random_regret_eliminated": (
            1 - shortlist_regret / random_regret if random_regret > 0 else math.nan
        ),
    }


def dataset_summary(dataset: dict) -> dict:
    return {
        "rows": len(dataset["targets"]),
        "candidate_targets": int(dataset["targets"].size),
        "positive_target_rate": float((dataset["targets"] > 0).mean()),
        "mean_teacher_available": float(
            np.maximum(dataset["targets"].max(axis=1), 0.0).mean()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=320)
    parser.add_argument("--calibration-games", type=int, default=80)
    parser.add_argument("--test-games", type=int, default=80)
    parser.add_argument("--fit-seed", type=int, default=72_000)
    parser.add_argument("--calibration-seed", type=int, default=73_000)
    parser.add_argument("--test-seed", type=int, default=74_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "runs/position_dense_ensemble_160_131.pt",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    datasets = {}
    for name, seed, games in (
        ("fit", args.fit_seed, args.fit_games),
        ("calibration", args.calibration_seed, args.calibration_games),
        ("test", args.test_seed, args.test_games),
    ):
        print(f"collecting {name}: seeds {seed}..{seed + games - 1}", flush=True)
        datasets[name] = collect(range(seed, seed + games), args.workers)

    env = TFTEnv(load_all(), scouting="tokens", max_actions_per_round=600)
    models = []
    for seed in range(args.fits):
        torch.manual_seed(seed)
        model = RelationalMoveHead(env.observation_space, env.encoder.spec)
        fit_head(
            model,
            datasets["fit"],
            seed=seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
        models.append(model)

    calibration_scores = scores(models, datasets["calibration"])
    selected, calibration_grid = calibrate(
        datasets["calibration"], calibration_scores
    )
    test_scores = scores(models, datasets["test"])
    test = policy_metrics(
        datasets["test"], test_scores, selected["threshold"]
    )
    shortlist = shortlist_metrics(datasets["test"], test_scores, args.test_seed)
    payload = {
        "source_fingerprint": before,
        "config": vars(args)
        | {
            "checkpoint": str(args.checkpoint),
            "json": str(args.json) if args.json else None,
        },
        "datasets": {
            name: dataset_summary(dataset) for name, dataset in datasets.items()
        },
        "calibration_selected": selected,
        "calibration_grid": calibration_grid,
        "test_direct": test,
        "test_shortlist": shortlist,
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "source_fingerprint": before,
            "score_threshold": selected["threshold"],
            "model_states": [model.state_dict() for model in models],
        },
        args.checkpoint,
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
