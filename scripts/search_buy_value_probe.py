"""Can a supervised candidate value model rank `best_buy`'s real choices?

This is deliberately not next-action behaviour cloning.  Every captured
search-buy state becomes a small ranking problem: no buy plus each legal shop
purchase are scored by the same opponent panel and matched combat seeds.  A
model sees only relational features of the resulting candidate board against
the visible opponent boards and predicts its value delta from no buy.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.hexgrid import distance  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.traits import trait_counts  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import (  # noqa: E402
    buy_candidates,
    clone_board,
    fight_value,
    opponent_panel,
)
from scripts.combat_surrogate import features  # noqa: E402


def score(data, player, match, panel, seeds, extra=(), drops=()) -> float:
    total = 0.0
    for other, trial_seeds in zip(panel, seeds, strict=True):
        for seed in trial_seeds:
            total += fight_value(
                data, player.hex_board,
                clone_board(match, player, 0, extra=extra, drops=drops),
                clone_board(match, other, 1), seed,
            )
    return total / max(len(seeds[0]), 1)


def candidate_features(data, player, match, panel, extra=(), drops=()) -> np.ndarray:
    ours = clone_board(match, player, 0, extra=extra, drops=drops)
    rows = [
        candidate_opponent_features(ours, clone_board(match, other, 1), data)
        for other in panel
    ]
    # A present flag distinguishes a late-game missing board from an opponent
    # whose relational values happen to be zero. The row order remains
    # non-semantic; the model pools it as a set.
    values = np.zeros((2, len(rows[0]) + 1), dtype=float)
    for index, row in enumerate(rows):
        values[index, :-1] = row
        values[index, -1] = 1.0
    return values


def candidate_opponent_features(ours, theirs, data) -> np.ndarray:
    """Relational combat facts for one hypothetical candidate/opponent pair."""
    base = features(ours, theirs, data)
    trait_ids = tuple(sorted(data.traits))
    ours_traits, theirs_traits = trait_counts(ours), trait_counts(theirs)
    ours_trait_values = np.array([ours_traits.get(trait_id, 0) for trait_id in trait_ids])
    theirs_trait_values = np.array([theirs_traits.get(trait_id, 0) for trait_id in trait_ids])
    trait_diff = ours_trait_values - theirs_trait_values
    trait_ratio = trait_diff / np.where(ours_trait_values + theirs_trait_values, ours_trait_values + theirs_trait_values, 1)

    def cast_values(units):
        stats = [unit.champion.stats for unit in units]
        cooldowns = [
            unit.champion.ability.cooldown_seconds or 0.0
            for unit in units if unit.champion.ability is not None
        ]
        return np.array([
            sum(stat.starting_mana for stat in stats),
            sum(stat.max_mana for stat in stats),
            sum(stat.mana_per_attack for stat in stats),
            sum(unit.champion.ability is not None and unit.champion.ability.cast_mode == "cooldown" for unit in units),
            sum(cooldowns),
        ], dtype=float)

    ours_cast, theirs_cast = cast_values(ours), cast_values(theirs)
    cast_diff = ours_cast - theirs_cast
    cast_ratio = cast_diff / np.where(ours_cast + theirs_cast, ours_cast + theirs_cast, 1.0)

    pair_distances = [distance(our.position, their.position) for our in ours for their in theirs]
    ours_in_range = sum(
        any(distance(our.position, their.position) <= our.derived_stats().attack_range for their in theirs)
        for our in ours
    )
    theirs_in_range = sum(
        any(distance(their.position, our.position) <= their.derived_stats().attack_range for our in ours)
        for their in theirs
    )
    geometry = np.array([
        min(pair_distances), np.mean(pair_distances), ours_in_range, theirs_in_range,
    ], dtype=float)
    return np.concatenate((base, trait_diff, trait_ratio, cast_diff, cast_ratio, geometry))


def collect(data, seeds: range, trials: int) -> dict:
    xs, ys, groups = [], [], []
    group = 0
    original = search_mod.best_buy
    for episode_seed in seeds:
        env = TFTEnv(data, scouting="tokens", max_actions_per_round=600)
        policy = search_mod.search_buy_greedy_policy(env, econ=FAST8)
        env.register_external_policy(policy)
        observation, _ = env.reset(seed=episode_seed)
        calls = 0

        def wrapped(probe_env, teacher_rng, _episode_seed=episode_seed, **kwargs):
            nonlocal group, calls
            player, match = probe_env.player, probe_env.match
            assert match is not None
            panel = opponent_panel(match, player, kwargs.get("panel_size", 2))
            candidates = list(buy_candidates(player, match, kwargs.get("max_candidates", 5))) if (
                player.board and player.free_bench_slots and panel
            ) else []
            if candidates:
                label_rng = random.Random(((_episode_seed + 1) * 100_000) + calls)
                seeds_for_state = [
                    [label_rng.randrange(2**31) for _ in range(trials)] for _ in panel
                ]
                baseline = score(data, player, match, panel, seeds_for_state)
                options = [((), (), None), *[(extra, drops, slot) for slot, extra, drops in candidates]]
                for extra, drops, _slot in options:
                    xs.append(candidate_features(data, player, match, panel, extra, drops))
                    ys.append(score(data, player, match, panel, seeds_for_state, extra, drops) - baseline)
                    groups.append(group)
                group += 1
            calls += 1
            return original(probe_env, teacher_rng, **kwargs)

        search_mod.best_buy = wrapped
        try:
            terminated = False
            while not terminated:
                action = policy(observation, env.action_masks())
                observation, _reward, terminated, truncated, _info = env.step(action)
                terminated = terminated or truncated
        finally:
            search_mod.best_buy = original
    return {"x": np.stack(xs), "y": np.asarray(ys), "group": np.asarray(groups)}


def grouped_metrics(pred, dataset, rng: random.Random) -> dict:
    regrets, random_regrets, top1, top2, top3, top4, candidates = [], [], [], [], [], [], []
    hybrid_regrets = {2: [], 3: [], 4: []}
    baseline_top3_regrets = []
    for group in np.unique(dataset["group"]):
        rows = dataset["group"] == group
        truth, guess = dataset["y"][rows], pred[rows]
        best = float(truth.max())
        picked = int(np.argmax(guess))
        regrets.append(best - float(truth[picked]))
        random_regrets.append(best - float(truth[rng.randrange(len(truth))]))
        truth_best = int(np.argmax(truth))
        top1.append(float(picked == truth_best))
        top2.append(float(truth_best in np.argsort(guess)[-min(2, len(guess)):]))
        top3.append(float(truth_best in np.argsort(guess)[-min(3, len(guess)):]))
        top4.append(float(truth_best in np.argsort(guess)[-min(4, len(guess)):]))
        # Replay the proposed hybrid exactly: the learned value model makes
        # only the shortlist, then the matched simulator picks within it.
        for k in hybrid_regrets:
            shortlisted = np.argsort(guess)[-min(k, len(guess)):]
            hybrid_regrets[k].append(best - float(truth[shortlisted].max()))
        # A live buyer cannot omit no-buy: it needs that simulated value to
        # apply best_buy's margin.  With a four-fight budget it can therefore
        # retain baseline plus the three highest predicted *buy* candidates.
        # `collect` deliberately writes no-buy first in every group.
        assert len(truth) >= 1
        buy_indices = np.arange(1, len(truth))
        predicted_buys = buy_indices[np.argsort(guess[buy_indices])[-min(3, len(buy_indices)):]]
        deployable = np.concatenate((np.array([0]), predicted_buys))
        baseline_top3_regrets.append(best - float(truth[deployable].max()))
        candidates.append(len(truth))
    random_regret = float(np.mean(random_regrets))
    regret = float(np.mean(regrets))
    return {
        "states": len(regrets), "regret": regret, "random_regret": random_regret,
        "random_regret_eliminated": 1 - regret / random_regret if random_regret else 0.0,
        "top1": float(np.mean(top1)), "top2_recall": float(np.mean(top2)),
        "top3_recall": float(np.mean(top3)), "top4_recall": float(np.mean(top4)),
        **{
            f"hybrid_top{k}_regret": float(np.mean(values))
            for k, values in hybrid_regrets.items()
        },
        "hybrid_baseline_top3_regret": float(np.mean(baseline_top3_regrets)),
        "mean_candidates": float(np.mean(candidates)),
    }


class OpponentSetValueNet(torch.nn.Module):
    """Shared opponent encoder followed by permutation-invariant pooling."""

    def __init__(self, feature_dim: int) -> None:
        super().__init__()
        self.opponent = torch.nn.Sequential(
            torch.nn.Linear(feature_dim, 64), torch.nn.ReLU(),
            torch.nn.Linear(64, 64), torch.nn.ReLU(),
        )
        self.head = torch.nn.Sequential(
            torch.nn.Linear(64, 64), torch.nn.ReLU(), torch.nn.Linear(64, 1)
        )

    def forward(self, values):
        present = values[..., -1:]
        encoded = self.opponent(values) * present
        return self.head(encoded.sum(dim=1) / present.sum(dim=1).clamp(min=1))


def train_value_model(train: dict, epochs: int, seed: int, representation: str):
    """Fit the candidate regressor and return its normalisation contract."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if representation == "mean_std":
        def transform(values):
            return np.concatenate((values[..., :-1].mean(axis=1), values[..., :-1].std(axis=1)), axis=1)
        train_x = transform(train["x"])
        mu, sd = train_x.mean(axis=0), train_x.std(axis=0) + 1e-8
        xtr = torch.tensor((train_x - mu) / sd, dtype=torch.float32)
        model = torch.nn.Sequential(
            torch.nn.Linear(xtr.shape[1], 96), torch.nn.ReLU(),
            torch.nn.Linear(96, 64), torch.nn.ReLU(), torch.nn.Linear(64, 1),
        )
    else:
        # Normalise only the relational dimensions, retaining the binary
        # present flag exactly as an indicator.
        mu = train["x"][..., :-1].mean(axis=(0, 1))
        raw_sd = train["x"][..., :-1].std(axis=(0, 1))
        # A dimension absent from a small training corpus can occur in a
        # held-out board (for example an otherwise unseen trait relation).
        # Dividing it by 1e-8 turns an ordinary finite feature into a 1e8-sigma
        # outlier and lets ReLUs extrapolate arbitrarily. Keep such dimensions
        # centred but give them unit natural scale instead (doc 99 160.56).
        sd = np.where(raw_sd < 1e-6, 1.0, raw_sd)
        def normalise(values):
            result = values.copy()
            result[..., :-1] = (result[..., :-1] - mu) / sd
            return result
        xtr = torch.tensor(normalise(train["x"]), dtype=torch.float32)
        model = OpponentSetValueNet(xtr.shape[-1])
    ytr = torch.tensor(train["y"], dtype=torch.float32).unsqueeze(1)
    optimiser = torch.optim.AdamW(model.parameters(), lr=1e-3)
    for _ in range(epochs):
        order = torch.randperm(len(xtr))
        for start in range(0, len(xtr), 256):
            rows = order[start:start + 256]
            loss = torch.nn.functional.mse_loss(model(xtr[rows]), ytr[rows])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
    return model.eval(), mu, sd


def predict_value_model(model, values: np.ndarray, mu, sd, representation: str) -> np.ndarray:
    """Predict candidate deltas using only the frozen feature/model contract."""
    if representation == "mean_std":
        inputs = np.concatenate(
            (values[..., :-1].mean(axis=1), values[..., :-1].std(axis=1)), axis=1,
        )
    else:
        inputs = values.copy()
        inputs[..., :-1] = (inputs[..., :-1] - mu) / sd
    with torch.no_grad():
        return model(torch.tensor(inputs, dtype=torch.float32)).squeeze(1).numpy()


def fit(train: dict, holdout: dict, epochs: int, seed: int, representation: str) -> dict:
    model, mu, sd = train_value_model(train, epochs, seed, representation)
    train_pred = predict_value_model(model, train["x"], mu, sd, representation)
    holdout_pred = predict_value_model(model, holdout["x"], mu, sd, representation)
    return {
        "train_mse": float(np.mean((train_pred - train["y"]) ** 2)),
        "holdout_mse": float(np.mean((holdout_pred - holdout["y"]) ** 2)),
        "train": grouped_metrics(train_pred, train, random.Random(seed)),
        "holdout": grouped_metrics(holdout_pred, holdout, random.Random(seed + 1)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-episodes", type=int, default=12)
    parser.add_argument("--holdout-episodes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--holdout-offset", type=int, default=10_000)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--representation", choices=("mean_std", "deepset"), default="mean_std")
    parser.add_argument(
        "--cache", type=Path,
        help="persist/load the expensive labelled candidate corpus",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    data = load_all()
    if args.cache and args.cache.exists():
        blob = np.load(args.cache)
        train = {name: blob[f"train_{name}"] for name in ("x", "y", "group")}
        holdout = {name: blob[f"holdout_{name}"] for name in ("x", "y", "group")}
    else:
        train = collect(data, range(args.seed, args.seed + args.train_episodes), args.trials)
        holdout = collect(
            data, range(args.holdout_offset, args.holdout_offset + args.holdout_episodes),
            args.trials,
        )
        if args.cache:
            np.savez(
                args.cache,
                **{f"train_{name}": value for name, value in train.items()},
                **{f"holdout_{name}": value for name, value in holdout.items()},
            )
    result = fit(train, holdout, args.epochs, args.seed, args.representation)
    payload = {
        "train_candidates": len(train["y"]), "holdout_candidates": len(holdout["y"]),
        "train_states": len(set(train["group"])), "holdout_states": len(set(holdout["group"])),
        "trials": args.trials, "epochs": args.epochs, "representation": args.representation, **result,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
