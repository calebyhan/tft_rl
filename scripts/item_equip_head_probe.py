"""Can an action-conditioned head learn the repaired item teacher?

This is the offline gate predeclared in doc 99 entry 160.116. It collects the
first real EQUIP emitted whenever the depth-1 item planner evaluates more than
one final loadout. Whole episodes are split before fitting. No model drives an
environment and no placement result is produced.

    .venv/bin/python scripts/item_equip_head_probe.py --workers 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import random
import sys
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8, _strength  # noqa: E402
from rl.scout_policy import ScoutSetExtractor  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402

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
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    _DATA = load_all()


def _shipped_equip_label(env: TFTEnv) -> int:
    """Relative EQUIP label from the unchanged first-item/strongest-unit rule."""
    player = env.player
    space = env.action_space_helper
    targets = [
        (hex_, unit)
        for hex_, unit in player.board.items()
        if len(unit.items) < player.config.max_items_per_unit
        and player.can_equip_from_bag(player.item_bag[0].id, unit)
    ]
    if not targets:
        raise RuntimeError("searchable item state has no shipped legal target")
    target_hex, _unit = max(targets, key=lambda pair: _strength(pair[1]))
    return space.slot_for_hex(target_hex)


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
        mask = env.action_masks()
        before = dict(policy.item_search_stats)
        action = int(policy(observation, mask))
        after = policy.item_search_stats
        if after["search_decisions"] > before["search_decisions"]:
            decoded = env.action_space_helper.decode(action)
            if decoded.kind is not ActionKind.EQUIP:
                searched_no_equip += 1
                observation, _reward, terminated, truncated, _info = env.step(action)
                if terminated or truncated:
                    break
                continue
            space = env.action_space_helper
            equip_mask = mask[space.equip_offset:space.augment_offset].reshape(
                space.item_bag_slots, space.unit_slots
            )
            rows.append(
                {
                    "observation": {
                        name: value.copy() for name, value in observation.items()
                    },
                    "mask": equip_mask.copy(),
                    "label": action - space.equip_offset,
                    "changed": (
                        after["changed_layouts"] > before["changed_layouts"]
                    ),
                    "shipped": _shipped_equip_label(env),
                }
            )
        observation, _reward, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            break
    return {"rows": rows, "searched_no_equip": searched_no_equip}


def collect_with_diagnostics(seeds: range, workers: int) -> tuple[list[dict], dict]:
    context = get_context("spawn")
    with context.Pool(workers, initializer=_init_worker) as pool:
        episodes = pool.map(collect_episode, seeds, chunksize=1)
    return (
        [row for episode in episodes for row in episode["rows"]],
        {
            "games": len(episodes),
            "searched_no_equip": sum(
                episode["searched_no_equip"] for episode in episodes
            ),
        },
    )


def collect(seeds: range, workers: int) -> list[dict]:
    rows, _diagnostics = collect_with_diagnostics(seeds, workers)
    return rows


def stack_rows(rows: list[dict]) -> dict:
    if not rows:
        raise RuntimeError("no searchable item decisions collected")
    names = rows[0]["observation"]
    return {
        "observations": {
            name: np.stack([row["observation"][name] for row in rows])
            for name in names
        },
        "masks": np.stack([row["mask"] for row in rows]).reshape(len(rows), -1),
        "labels": np.asarray([row["label"] for row in rows], dtype=np.int64),
        "changed": np.asarray([row["changed"] for row in rows], dtype=bool),
        "shipped": np.asarray([row["shipped"] for row in rows], dtype=np.int64),
    }


class MonolithicEquipHead(nn.Module):
    def __init__(self, observation_space, n_actions: int, width: int) -> None:
        super().__init__()
        self.context = ScoutSetExtractor(observation_space)
        self.head = nn.Sequential(
            nn.Linear(self.context.features_dim, width),
            nn.ReLU(),
            nn.Linear(width, n_actions),
        )

    def forward(self, observations: dict[str, torch.Tensor]) -> torch.Tensor:
        return self.head(self.context(observations))


class RelationalEquipHead(nn.Module):
    """Shared scorer over candidate bag item and target unit/loadout."""

    def __init__(self, observation_space, spec, item_slots: int, width: int = 128):
        super().__init__()
        self.context = ScoutSetExtractor(observation_space)
        self.spec = spec
        self.item_slots = item_slots
        self.unit_slots = spec.board_slots + spec.bench_slots
        self.unit_width = spec.unit_width
        local_width = 12 + item_slots * 12 + self.unit_width
        self.score = nn.Sequential(
            nn.Linear(self.context.features_dim + local_width, width),
            nn.ReLU(),
            nn.Linear(width, width),
            nn.ReLU(),
            nn.Linear(width, 1),
        )

    def _unit_features(self, global_observation: torch.Tensor) -> torch.Tensor:
        board_start = self.spec.offset_of("board")
        bench_start = self.spec.offset_of("bench")
        board = global_observation[
            :, board_start:bench_start
        ].reshape(-1, self.spec.board_slots, self.unit_width)
        shop_start = self.spec.offset_of("shop")
        bench = global_observation[
            :, bench_start:shop_start
        ].reshape(-1, self.spec.bench_slots, self.unit_width)
        return torch.cat((board, bench), dim=1)

    def forward(self, observations: dict[str, torch.Tensor]) -> torch.Tensor:
        context = self.context(observations)
        bag = self.context.item_embedding(observations["item_bag"].long())
        held = self.context.item_embedding(observations["own_items"].long()).flatten(2)
        unit = self._unit_features(observations["global"].float())
        batch, bag_slots, _embedding = bag.shape

        context = context[:, None, None, :].expand(
            batch, bag_slots, self.unit_slots, -1
        )
        bag = bag[:, :, None, :].expand(batch, bag_slots, self.unit_slots, -1)
        held = held[:, None, :, :].expand(batch, bag_slots, self.unit_slots, -1)
        unit = unit[:, None, :, :].expand(batch, bag_slots, self.unit_slots, -1)
        return self.score(torch.cat((context, bag, held, unit), dim=-1)).reshape(
            batch, -1
        )


def tensors(dataset: dict, device: torch.device) -> tuple[dict, torch.Tensor, torch.Tensor]:
    observations = {
        name: torch.as_tensor(value, device=device)
        for name, value in dataset["observations"].items()
    }
    return (
        observations,
        torch.as_tensor(dataset["masks"], device=device, dtype=torch.bool),
        torch.as_tensor(dataset["labels"], device=device),
    )


def accuracy(model, dataset: dict, subset: np.ndarray | None = None) -> float:
    device = next(model.parameters()).device
    observations, masks, labels = tensors(dataset, device)
    model.eval()
    with torch.no_grad():
        logits = model(observations).masked_fill(~masks, -1e9)
        correct = logits.argmax(dim=-1).eq(labels).cpu().numpy()
    if subset is not None:
        correct = correct[subset]
    return float(correct.mean()) if len(correct) else math.nan


def fit(model, train: dict, *, seed: int, epochs: int, batch_size: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device("cpu")
    model.to(device)
    observations, masks, labels = tensors(train, device)
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)
    generator = torch.Generator().manual_seed(seed)
    for _epoch in range(epochs):
        order = torch.randperm(len(labels), generator=generator)
        model.train()
        for start in range(0, len(order), batch_size):
            rows = order[start:start + batch_size]
            batch = {name: value[rows] for name, value in observations.items()}
            logits = model(batch).masked_fill(~masks[rows], -1e9)
            loss = nn.functional.cross_entropy(logits, labels[rows])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()


def parameters(model) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def baseline_metrics(dataset: dict) -> dict:
    first = dataset["masks"].argmax(axis=1)
    labels = dataset["labels"]
    changed = dataset["changed"]
    shipped = dataset["shipped"]
    return {
        "first_legal": float(np.mean(first == labels)),
        "first_legal_changed": float(np.mean(first[changed] == labels[changed])),
        "shipped": float(np.mean(shipped == labels)),
        "shipped_changed": float(np.mean(shipped[changed] == labels[changed])),
    }


def dataset_summary(dataset: dict) -> dict:
    labels = dataset["labels"]
    return {
        "rows": len(labels),
        "changed_rows": int(dataset["changed"].sum()),
        "classes": len(set(labels.tolist())),
        "top_classes": Counter(labels.tolist()).most_common(10),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-games", type=int, default=80)
    parser.add_argument("--holdout-games", type=int, default=40)
    parser.add_argument("--train-seed", type=int, default=54_000)
    parser.add_argument("--holdout-seed", type=int, default=55_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    train = stack_rows(collect(
        range(args.train_seed, args.train_seed + args.train_games), args.workers
    ))
    holdout = stack_rows(collect(
        range(args.holdout_seed, args.holdout_seed + args.holdout_games), args.workers
    ))

    env = TFTEnv(load_all(), scouting="tokens", max_actions_per_round=600)
    space = env.action_space_helper
    n_actions = space.item_bag_slots * space.unit_slots
    factories = {
        "monolithic": lambda: MonolithicEquipHead(env.observation_space, n_actions, 128),
        "monolithic-wide": lambda: MonolithicEquipHead(
            env.observation_space, n_actions, 256
        ),
        "relational": lambda: RelationalEquipHead(
            env.observation_space,
            env.encoder.spec,
            env.config.max_items_per_unit,
        ),
    }
    results = {}
    for name, factory in factories.items():
        fits = []
        for fit_seed in range(args.fits):
            torch.manual_seed(fit_seed)
            model = factory()
            fit(
                model,
                train,
                seed=fit_seed,
                epochs=args.epochs,
                batch_size=args.batch_size,
            )
            fits.append(
                {
                    "seed": fit_seed,
                    "parameters": parameters(model),
                    "train": accuracy(model, train),
                    "train_changed": accuracy(model, train, train["changed"]),
                    "holdout": accuracy(model, holdout),
                    "holdout_changed": accuracy(
                        model, holdout, holdout["changed"]
                    ),
                }
            )
        results[name] = fits

    payload = {
        "source_fingerprint": before,
        "config": vars(args) | {"json": str(args.json) if args.json else None},
        "train": dataset_summary(train),
        "holdout": dataset_summary(holdout),
        "holdout_baselines": baseline_metrics(holdout),
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
