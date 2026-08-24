"""Measure a simulator-finalised learned shortlist against full buy search.

The learned model never chooses a buy by itself.  It simulates no-buy plus its
three highest-ranked legal purchases, then applies the same exact score/margin
rule as full ``best_buy``.  Entry 160.48 requires this four-simulation contract.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match, PlanningContext  # noqa: E402
from rl.opponents import FAST8, GreedyPolicy, default_opponent  # noqa: E402
from rl.search import (  # noqa: E402
    buy_candidates,
    clone_board,
    fight_value,
    opponent_panel,
)
from scripts.search_buy_value_probe import (  # noqa: E402
    candidate_features,
    predict_value_model,
    train_value_model,
)

PANEL = 2
TRIALS = 2
MARGIN = 0.25
SHORTLIST_BUYS = 3

_DATA = None
_MODEL = None
_MU = None
_SD = None


def hybrid_best_buy(env, rng, panel_size: int = PANEL, trials: int = TRIALS,
                    margin: float = MARGIN, max_candidates: int = 5) -> int | None:
    """Action-space callable for the frozen baseline-plus-top-three contract."""
    if _MODEL is None or _MU is None or _SD is None:
        raise RuntimeError("call _init() before using the hybrid buyer")
    player, match = env.player, env.match
    if match is None or not player.board or not player.free_bench_slots:
        return None
    panel = opponent_panel(match, player, panel_size)
    candidates = list(buy_candidates(player, match, max_candidates)) if panel else []
    if not candidates:
        return None
    values = np.stack([
        candidate_features(player.data, player, match, panel),
        *[
            candidate_features(player.data, player, match, panel, extra, drops)
            for _slot, extra, drops in candidates
        ],
    ])
    predicted = predict_value_model(_MODEL, values, _MU, _SD, "deepset")
    chosen_rows = np.argsort(predicted[1:])[-min(SHORTLIST_BUYS, len(candidates)):]
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]

    def score(extra=(), drops=()) -> float:
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    player.data, player.hex_board,
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1), seed,
                )
        return total / max(trials, 1)

    baseline = score()
    best_value, best_slot = baseline, None
    for row in chosen_rows:
        slot, extra, drops = candidates[int(row)]
        value = score(extra, drops)
        if value > best_value:
            best_value, best_slot = value, slot
    if best_slot is None or best_value <= baseline + margin * len(panel):
        return None
    return best_slot


class CountingBuyPolicy(GreedyPolicy):
    """Common greedy base with a measurable once-per-round combat search."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fight_calls = 0
        self.search_calls = 0
        self.search_buys = 0

    def plan(self, player, context: PlanningContext) -> None:
        self._search_buy(player, context)
        super().plan(player, context)

    def _score(self, player, match, panel, seeds, extra=(), drops=()) -> float:
        self.fight_calls += len(panel) * len(seeds[0])
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    player.data, player.hex_board,
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1), seed,
                )
        return total / max(len(seeds[0]), 1)

    def _choose(self, player, match, panel, candidates, seeds) -> int | None:
        raise NotImplementedError

    def _search_buy(self, player, context: PlanningContext) -> None:
        match = context.match
        if not player.board or not player.free_bench_slots:
            return
        panel = opponent_panel(match, player, PANEL)
        candidates = list(buy_candidates(player, match)) if panel else []
        if not candidates:
            return
        self.search_calls += 1
        seeds = [[self.rng.randrange(2**31) for _ in range(TRIALS)] for _ in panel]
        slot = self._choose(player, match, panel, candidates, seeds)
        if slot is not None:
            player.buy(slot, context.pool)
            self.search_buys += 1


class FullSearchBuyPolicy(CountingBuyPolicy):
    """Exact control: baseline and every legal first-shop purchase."""

    def _choose(self, player, match, panel, candidates, seeds) -> int | None:
        baseline = self._score(player, match, panel, seeds)
        best_value, best_slot = baseline, None
        for slot, extra, drops in candidates:
            value = self._score(player, match, panel, seeds, extra, drops)
            if value > best_value:
                best_value, best_slot = value, slot
        if best_slot is None or best_value <= baseline + MARGIN * len(panel):
            return None
        return best_slot


class HybridSearchBuyPolicy(CountingBuyPolicy):
    """Exact baseline plus the trained model's top three purchases."""

    def _choose(self, player, match, panel, candidates, seeds) -> int | None:
        values = np.stack([
            candidate_features(_DATA, player, match, panel),
            *[
                candidate_features(_DATA, player, match, panel, extra, drops)
                for _slot, extra, drops in candidates
            ],
        ])
        predicted = predict_value_model(_MODEL, values, _MU, _SD, "deepset")
        buy_rows = np.argsort(predicted[1:])[-min(SHORTLIST_BUYS, len(candidates)):]
        baseline = self._score(player, match, panel, seeds)
        best_value, best_slot = baseline, None
        for row in buy_rows:
            slot, extra, drops = candidates[int(row)]
            value = self._score(player, match, panel, seeds, extra, drops)
            if value > best_value:
                best_value, best_slot = value, slot
        if best_slot is None or best_value <= baseline + MARGIN * len(panel):
            return None
        return best_slot


def _init(cache: str) -> None:
    global _DATA, _MODEL, _MU, _SD
    _DATA = load_all()
    blob = np.load(cache)
    train = {name: blob[f"train_{name}"] for name in ("x", "y", "group")}
    # Cache comes from the frozen replica: seed 20,000, 400 epochs, DeepSets.
    _MODEL, _MU, _SD = train_value_model(train, 400, 20_000, "deepset")


def _play(job) -> dict:
    kind, seed = job
    policy_type = {"full": FullSearchBuyPolicy, "hybrid": HybridSearchBuyPolicy}[kind]
    policy = policy_type(seed=0, econ=FAST8)
    match = Match(
        _DATA, [policy] + [default_opponent(seat) for seat in range(1, 8)], seed=seed,
    )
    while not match.finished:
        match.play_round()
    match._finalise_placements()
    return {
        "seed": seed, "placement": match.placements[0],
        "fight_calls": policy.fight_calls, "search_calls": policy.search_calls,
        "search_buys": policy.search_buys,
    }


def paired_t(full: list[dict], hybrid: list[dict]) -> tuple[float, float]:
    diffs = [b["placement"] - a["placement"] for a, b in zip(full, hybrid, strict=True)]
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    return mean, mean / (sd / math.sqrt(len(diffs))) if sd else 0.0


def summarize(rows: list[dict]) -> dict:
    keys = ("placement", "fight_calls", "search_calls", "search_buys")
    return {key: statistics.mean(row[key] for row in rows) for key in keys} | {
        "distribution": {
            str(place): sum(row["placement"] == place for row in rows) for place in range(1, 9)
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=32)
    parser.add_argument("--seed", type=int, default=40_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--cache", type=Path,
        default=Path("/private/tmp/search_buy_value_features_replica_12x4.npz"),
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if not args.cache.exists():
        raise FileNotFoundError(f"missing frozen replica cache: {args.cache}")
    jobs = [(kind, seed) for kind in ("full", "hybrid")
            for seed in range(args.seed, args.seed + args.games)]
    with mp.get_context("spawn").Pool(args.workers, _init, (str(args.cache),)) as pool:
        rows = pool.map(_play, jobs, chunksize=1)
    # ``Pool.map`` preserves job order, so rows have full then hybrid arms.
    full, hybrid = rows[:args.games], rows[args.games:]
    delta, t_value = paired_t(full, hybrid)
    output = {
        "games": args.games, "seed": args.seed,
        "full": summarize(full), "hybrid": summarize(hybrid),
        "hybrid_minus_full_placement": delta, "paired_t": t_value,
        "fight_call_reduction": 1 - (
            statistics.mean(row["fight_calls"] for row in hybrid)
            / statistics.mean(row["fight_calls"] for row in full)
        ),
    }
    print(json.dumps(output, indent=2))
    if args.json:
        args.json.write_text(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
