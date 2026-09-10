"""Does frozen learned item value add to exact buy search?"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import statistics
import sys
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import LP_BY_PLACEMENT, SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import FAST8  # noqa: E402
from rl.search import search_buy_greedy_policy, search_item_greedy_policy  # noqa: E402
from scripts.item_dense_placement_ab import (  # noqa: E402
    distilled_item_policy,
    load_models,
)

ARMS = ("buy", "distilled", "exact")
_DATA = None
_MODELS = None
_THRESHOLD = None


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/player.py",
        "engine/unit.py",
        "rl/action.py",
        "rl/env.py",
        "rl/evaluate.py",
        "rl/greedy_action.py",
        "rl/observation.py",
        "rl/opponents.py",
        "rl/scout_policy.py",
        "rl/search.py",
        "scripts/item_equip_head_probe.py",
        "scripts/item_dense_value_probe.py",
        "scripts/item_dense_scale_probe.py",
        "scripts/item_dense_placement_ab.py",
        "scripts/search_buy_distilled_item_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker(checkpoint_path: str) -> None:
    global _DATA, _MODELS, _THRESHOLD
    logging.disable(logging.WARNING)
    torch.set_num_threads(1)
    _DATA = load_all()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    template = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    _MODELS = load_models(checkpoint, template)
    _THRESHOLD = float(checkpoint["threshold"])


def _policy(env: TFTEnv, arm: str, seed: int):
    search_seed = seed + SEARCH_SEED_OFFSET
    if arm == "buy":
        return search_buy_greedy_policy(env, econ=FAST8, rng_seed=search_seed)
    if arm == "distilled":
        return distilled_item_policy(
            env,
            _MODELS,
            _THRESHOLD,
            econ=FAST8,
            buy_search=True,
            rng_seed=search_seed,
        )
    return search_item_greedy_policy(
        env,
        econ=FAST8,
        rng_seed=search_seed,
        depth=1,
        panel_size=2,
        trials=2,
        margin=0.25,
        buy_search=True,
    )


def play_one(job: tuple[str, int]) -> dict:
    arm, seed = job
    if _DATA is None or _MODELS is None or _THRESHOLD is None:
        raise RuntimeError("evaluation worker was not initialized")
    env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    policy = _policy(env, arm, seed)
    original_fight = search_mod.fight_value
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    search_mod.fight_value = counted_fight
    started = time.perf_counter()
    buy_decisions = 0
    try:
        observation, _ = env.reset(seed=seed)
        info = {}
        for _step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            buy_decisions += int(
                getattr(policy, "last_search_buy_slot", None) is not None
            )
            observation, _reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        else:
            raise RuntimeError(f"{arm} did not terminate on seed {seed}")
    finally:
        search_mod.fight_value = original_fight

    exact_stats = getattr(policy, "item_search_stats", {})
    learned_stats = getattr(policy, "item_distill_stats", {})
    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
        "seconds": time.perf_counter() - started,
        "fight_calls": fight_calls,
        "buy_decisions": buy_decisions,
        "item_decisions": exact_stats.get(
            "search_decisions", learned_stats.get("decisions", 0)
        ),
        "item_changes": exact_stats.get(
            "changed_layouts", learned_stats.get("overrides", 0)
        ),
        "item_candidates": learned_stats.get("candidate_actions", 0),
        "item_fight_calls": exact_stats.get(
            "fight_calls", learned_stats.get("fight_calls", 0)
        ),
    }


def paired(first: list[float], second: list[float]) -> dict[str, float]:
    differences = [b - a for a, b in zip(first, second, strict=True)]
    mean = statistics.fmean(differences)
    sd = statistics.stdev(differences)
    se = sd / math.sqrt(len(differences))
    return {
        "delta": mean,
        "t": mean / se if se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
    }


def summarise(records: list[dict]) -> tuple[dict, dict]:
    grouped = {arm: [] for arm in ARMS}
    for record in records:
        grouped[record["arm"]].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["seed"])

    summary = {}
    for arm, rows in grouped.items():
        placements = [row["placement"] for row in rows]
        histogram = Counter(placements)
        summary[arm] = {
            "n": len(rows),
            "placement": statistics.fmean(placements),
            "lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "first": histogram[1] / len(rows),
            "top4": sum(p <= 4 for p in placements) / len(rows),
            "eighth": histogram[8] / len(rows),
            "histogram": [histogram[p] for p in range(1, 9)],
            "placements": placements,
        }
        for field in (
            "seconds",
            "fight_calls",
            "buy_decisions",
            "item_decisions",
            "item_changes",
            "item_candidates",
            "item_fight_calls",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    comparisons = {
        "distilled minus buy": paired(
            summary["buy"]["placements"], summary["distilled"]["placements"]
        ),
        "exact minus buy": paired(
            summary["buy"]["placements"], summary["exact"]["placements"]
        ),
        "distilled minus exact": paired(
            summary["exact"]["placements"], summary["distilled"]["placements"]
        ),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--seed0", type=int, default=77_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "runs/item_dense_ensemble_160_127.pt",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    checkpoint_before = file_sha(args.checkpoint)
    if not checkpoint_before.startswith("5d30b6e11e15"):
        raise RuntimeError(f"unexpected checkpoint SHA: {checkpoint_before}")
    started = time.perf_counter()
    jobs = [
        (arm, args.seed0 + game)
        for game in range(args.games)
        for arm in ARMS
    ]
    context = get_context("spawn")
    with context.Pool(
        args.workers,
        initializer=_init_worker,
        initargs=(str(args.checkpoint),),
    ) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    summary, comparisons = summarise(records)
    after = source_fingerprint()
    checkpoint_after = file_sha(args.checkpoint)
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    if checkpoint_after != checkpoint_before:
        raise RuntimeError("checkpoint changed during run")
    payload = {
        "source_fingerprint": before,
        "checkpoint_sha": checkpoint_before,
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "wall_seconds": time.perf_counter() - started,
        "summary": summary,
        "comparisons": comparisons,
        "records": records,
    }
    print(json.dumps(payload, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
