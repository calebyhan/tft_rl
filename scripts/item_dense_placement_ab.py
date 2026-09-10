"""Retrain and place-test the dense item ensemble (doc 99 entry 160.127).

The distilled arm generates item candidates but never simulates a fight. Its
three relational heads are reproduced from the frozen 160.125 fit/calibration
episodes, checkpointed, and then evaluated beside shipped and search-teacher
action policies on paired fresh games.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    LP_BY_PLACEMENT,
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
)
from rl.opponents import FAST8  # noqa: E402
from rl.search import (  # noqa: E402
    item_candidate_layouts,
    search_item_greedy_policy,
    search_policy,
)
from scripts.item_dense_scale_probe import (  # noqa: E402
    choose_threshold,
    model_scores,
)
from scripts.item_dense_value_probe import collect, fit_dense, stack_rows  # noqa: E402
from scripts.item_equip_head_probe import (  # noqa: E402
    RelationalEquipHead,
    _shipped_equip_label,
)

ARMS = ("control", "distilled", "search")
_DATA = None
_MODELS = None
_THRESHOLD = None


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
        "scripts/item_residual_probe.py",
        "scripts/item_dense_value_probe.py",
        "scripts/item_dense_scale_probe.py",
        "scripts/item_dense_placement_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _new_model(env: TFTEnv) -> RelationalEquipHead:
    return RelationalEquipHead(
        env.observation_space,
        env.encoder.spec,
        env.config.max_items_per_unit,
    )


def train_checkpoint(args, fingerprint: str) -> dict:
    print("collecting frozen fit episodes", flush=True)
    train_rows, train_collection = collect(
        range(args.fit_seed, args.fit_seed + args.fit_games), args.workers
    )
    print("collecting frozen calibration episodes", flush=True)
    calibration_rows, calibration_collection = collect(
        range(
            args.calibration_seed,
            args.calibration_seed + args.calibration_games,
        ),
        args.workers,
    )
    train = stack_rows(train_rows)
    calibration = stack_rows(calibration_rows)
    env = TFTEnv(load_all(), scouting="tokens", max_actions_per_round=600)
    states = []
    calibration_scores = []
    for fit_seed in range(args.fits):
        print(f"fitting dense head {fit_seed + 1}/{args.fits}", flush=True)
        torch.manual_seed(fit_seed)
        model = _new_model(env)
        fit_dense(
            model,
            train,
            seed=fit_seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
        calibration_scores.append(model_scores(model, calibration))
        states.append({name: value.cpu() for name, value in model.state_dict().items()})

    ensemble_scores = np.mean(calibration_scores, axis=0)
    threshold, calibration_grid = choose_threshold(ensemble_scores, calibration)
    if not args.skip_threshold_check and threshold != args.required_threshold:
        raise RuntimeError(
            f"calibration threshold {threshold} did not reproduce required "
            f"{args.required_threshold}"
        )
    payload = {
        "source_fingerprint": fingerprint,
        "fit_seed": args.fit_seed,
        "fit_games": args.fit_games,
        "calibration_seed": args.calibration_seed,
        "calibration_games": args.calibration_games,
        "fits": args.fits,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "threshold": threshold,
        "calibration_selected": next(
            row for row in calibration_grid if row["threshold"] == threshold
        ),
        "train_collection": train_collection,
        "calibration_collection": calibration_collection,
        "model_states": states,
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, args.checkpoint)
    return payload


def load_models(checkpoint: dict, env: TFTEnv) -> list[RelationalEquipHead]:
    models = []
    for state in checkpoint["model_states"]:
        model = _new_model(env)
        model.load_state_dict(state)
        model.eval()
        models.append(model)
    return models


def distilled_item_policy(
    env: TFTEnv,
    models: list[RelationalEquipHead],
    threshold: float,
    *,
    econ=FAST8,
    buy_search: bool = False,
    rng_seed: int = 0,
    buy_kwargs: dict | None = None,
):
    stats = {
        "decisions": 0,
        "overrides": 0,
        "candidate_actions": 0,
        "fight_calls": 0,
    }

    def planner():
        assert env.match is not None
        player = env.player
        space = env.action_space_helper
        layouts, _completions = item_candidate_layouts(
            player,
            env.match,
            depth=1,
            max_items=space.item_bag_slots,
        )
        if len(layouts) <= 1:
            return []
        shipped = _shipped_equip_label(env)
        action_to_prefix = {shipped: ()}
        legal = env.action_masks()[space.equip_offset:space.augment_offset]
        for prefix in layouts.values():
            if not prefix:
                continue
            token, own_hex = prefix[0]
            relative = token * space.unit_slots + space.slot_for_hex(own_hex)
            if legal[relative]:
                action_to_prefix.setdefault(relative, prefix)
        if len(action_to_prefix) <= 1:
            return []

        observation = env._observe()
        batch = {
            name: torch.as_tensor(value[None])
            for name, value in observation.items()
        }
        with torch.no_grad():
            scores = torch.stack([model(batch)[0] for model in models]).mean(0)
        candidate_mask = torch.zeros_like(scores, dtype=torch.bool)
        candidate_mask[list(action_to_prefix)] = True
        scores = scores.masked_fill(~candidate_mask, -1e9)
        probabilities = scores.softmax(dim=0)
        proposed = int(scores.argmax())
        confidence = float(probabilities[proposed] - probabilities[shipped])

        stats["decisions"] += 1
        stats["candidate_actions"] += len(action_to_prefix)
        if proposed == shipped or confidence < threshold:
            return []
        stats["overrides"] += 1
        prefix = action_to_prefix[proposed]
        token, own_hex = prefix[0]
        return [(player.item_bag[token].id, own_hex)]

    item_policy = greedy_action_policy(env, econ=econ, item_planner=planner)
    policy = item_policy
    if buy_search:
        policy = search_policy(
            env,
            rng_seed=rng_seed,
            base=item_policy,
            mode="none",
            buy_search=True,
            buy_kwargs=buy_kwargs,
        )
        from rl.opponents import _carry_unit

        def choose_component(player, offered):
            carry = _carry_unit(player)
            if carry is not None:
                for component in (
                    item for item in carry.items if item.is_component
                ):
                    completions = [
                        candidate
                        for candidate in offered
                        if player.registry.combine(component.id, candidate)
                        is not None
                    ]
                    if completions:
                        return policy.rng.choice(sorted(completions))
            return policy.rng.choice(sorted(offered))

        policy.choose_component = choose_component
        env.register_external_policy(policy)
    policy.item_distill_stats = stats
    policy.item_distill_models = models
    return policy


def _init_evaluation(checkpoint_path: str) -> None:
    global _DATA, _MODELS, _THRESHOLD
    torch.set_num_threads(1)
    _DATA = load_all()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    template = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    _MODELS = load_models(checkpoint, template)
    _THRESHOLD = float(checkpoint["threshold"])


def play_one(job) -> dict:
    arm, seed = job
    if _DATA is None or _MODELS is None or _THRESHOLD is None:
        raise RuntimeError("evaluation worker was not initialized")
    env = TFTEnv(_DATA, scouting="tokens", max_actions_per_round=600)
    if arm == "control":
        policy = greedy_action_policy(env, econ=FAST8)
    elif arm == "distilled":
        policy = distilled_item_policy(env, _MODELS, _THRESHOLD)
    else:
        policy = search_item_greedy_policy(
            env,
            econ=FAST8,
            rng_seed=seed + SEARCH_SEED_OFFSET,
            depth=1,
            panel_size=2,
            trials=2,
        )

    started = time.perf_counter()
    observation, _ = env.reset(seed=seed)
    info = {}
    for _step in range(200_000):
        action = int(policy(observation, env.action_masks()))
        observation, _reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    else:
        raise RuntimeError(f"{arm} did not terminate on seed {seed}")

    diagnostics = {
        "decisions": 0,
        "overrides": 0,
        "candidate_actions": 0,
        "fight_calls": 0,
    }
    if arm == "distilled":
        diagnostics.update(policy.item_distill_stats)
    elif arm == "search":
        search = policy.item_search_stats
        diagnostics.update(
            decisions=search["search_decisions"],
            overrides=search["changed_layouts"],
            candidate_actions=search["candidate_boards"],
            fight_calls=search["fight_calls"],
        )
    return {
        "arm": arm,
        "seed": seed,
        "placement": info.get("placement") or env.n_players,
        "seconds": time.perf_counter() - started,
        **diagnostics,
    }


def paired(control: list[int], treatment: list[int]) -> dict[str, float]:
    differences = [b - a for a, b in zip(control, treatment, strict=True)]
    mean = statistics.fmean(differences)
    sd = statistics.stdev(differences)
    se = sd / math.sqrt(len(differences))
    return {
        "delta": mean,
        "sd": sd,
        "se": se,
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
        counts = Counter(placements)
        summary[arm] = {
            "n": len(rows),
            "placement": statistics.fmean(placements),
            "lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "first": counts[1] / len(rows),
            "top4": sum(p <= 4 for p in placements) / len(rows),
            "eighth": counts[8] / len(rows),
            "histogram": [counts[p] for p in range(1, 9)],
            "placements": placements,
        }
        for field in (
            "seconds",
            "decisions",
            "overrides",
            "candidate_actions",
            "fight_calls",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in rows)

    comparisons = {
        "distilled minus control": paired(
            summary["control"]["placements"],
            summary["distilled"]["placements"],
        ),
        "search minus control": paired(
            summary["control"]["placements"],
            summary["search"]["placements"],
        ),
        "distilled minus search": paired(
            summary["search"]["placements"],
            summary["distilled"]["placements"],
        ),
    }
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-games", type=int, default=320)
    parser.add_argument("--calibration-games", type=int, default=80)
    parser.add_argument("--fit-seed", type=int, default=65_000)
    parser.add_argument("--calibration-seed", type=int, default=66_000)
    parser.add_argument("--fits", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--games", type=int, default=400)
    parser.add_argument("--seed0", type=int, default=68_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "runs/item_dense_ensemble_160_127.pt",
    )
    parser.add_argument("--required-threshold", type=float, default=0.0)
    parser.add_argument("--skip-threshold-check", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    torch.set_num_threads(1)
    before = source_fingerprint()
    started = time.perf_counter()
    checkpoint = train_checkpoint(args, before)
    checkpoint_sha = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()[:12]
    print(
        f"checkpoint={args.checkpoint} sha={checkpoint_sha} "
        f"threshold={checkpoint['threshold']}",
        flush=True,
    )

    jobs = [
        (arm, args.seed0 + game)
        for arm in ARMS
        for game in range(args.games)
    ]
    context = get_context("spawn")
    with context.Pool(
        args.workers,
        initializer=_init_evaluation,
        initargs=(str(args.checkpoint),),
    ) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    summary, comparisons = summarise(records)
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")

    payload = {
        "source_fingerprint": before,
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha": checkpoint_sha,
        "threshold": checkpoint["threshold"],
        "calibration_selected": checkpoint["calibration_selected"],
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
