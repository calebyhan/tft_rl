"""Does the search teacher's edge survive a field that also searches?

Doc 99 entry 160.153. Every search increment in this project was measured
against ``DEFAULT_FIELD``, whose seats 5-7 run ``slowroll6``/``hyperroll`` --
the archetypes entry 73.5 found about 0.8 placement weaker than the rest.
Entry 74 is the precedent: a teacher that looked strong against a weak field
had the sign of its edge wrong against a fair one.

Two agent arms, both on the FAST8 greedy scheduler:

* ``greedy`` -- no search.
* ``full`` -- the established 160.152 teacher: buy, swap, items, move.

Three fields, which differ only in seats 5-7:

* ``default`` -- ``DEFAULT_FIELD`` unchanged.
* ``bots`` -- the teacher's own base: ``GreedyPolicy`` on FAST8, no search.
* ``teachers`` -- the 160.144 search teacher (buy, swap, items), seated
  through :class:`rl.teacher_seat.TeacherSeat`.

``default -> bots`` removes the weak seats; ``bots -> teachers`` adds search
and nothing else, because ``GreedyActionPolicy`` replays ``GreedyPolicy``.
"""

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

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import rl.search as search_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    LP_BY_PLACEMENT,
    SEARCH_SEED_OFFSET,
    greedy_action_policy,
)
from rl.opponents import FAST8, GreedyPolicy, default_opponent  # noqa: E402
from rl.search import search_item_greedy_policy  # noqa: E402
from rl.teacher_seat import TeacherSeat  # noqa: E402

ARMS = ("greedy", "full")
FIELDS = ("default", "bots", "teachers")

# DEFAULT_FIELD's SLOWROLL6, SLOWROLL6, HYPERROLL.
REPLACED_SEATS = (5, 6, 7)

# The 160.144 swap and 160.152 move budgets, unchanged.
SWAP_KWARGS = {"max_candidates": 4, "panel_size": 2, "trials": 2, "margin": 0.5}
MOVE_KWARGS = {"max_candidates": 6, "panel_size": 2, "trials": 2, "margin": 0.5}

_DATA = None


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/match.py",
        "engine/player.py",
        "engine/unit.py",
        "rl/action.py",
        "rl/env.py",
        "rl/evaluate.py",
        "rl/greedy_action.py",
        "rl/opponents.py",
        "rl/search.py",
        "rl/teacher_seat.py",
        "scripts/field_strength_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def search_teacher(env, rng_seed: int, *, move: bool):
    """The 160.144 teacher, plus 160.152's positioning search when ``move``."""
    return search_item_greedy_policy(
        env,
        econ=FAST8,
        rng_seed=rng_seed,
        depth=1,
        panel_size=2,
        trials=2,
        margin=0.25,
        buy_search=True,
        swap_search=True,
        swap_kwargs=dict(SWAP_KWARGS),
        swap_before_items=True,
        move_search=move,
        move_kwargs=dict(MOVE_KWARGS) if move else None,
    )


def opponent_factory(data, field: str, seed: int):
    if field not in FIELDS:
        raise ValueError(f"unknown field {field!r}")

    def factory(seat: int):
        if field == "default" or seat not in REPLACED_SEATS:
            return default_opponent(seat)
        if field == "bots":
            return GreedyPolicy(seed=seat, econ=FAST8)
        # Offset by seat so no two searchers in one game share a stream.
        return TeacherSeat(
            data,
            lambda view: search_teacher(
                view, seed + SEARCH_SEED_OFFSET + seat, move=False
            ),
            seat=seat,
        )

    return factory


def agent_policy(env, arm: str, seed: int):
    if arm == "greedy":
        return greedy_action_policy(env, econ=FAST8)
    if arm == "full":
        return search_teacher(env, seed + SEARCH_SEED_OFFSET, move=True)
    raise ValueError(f"unknown arm {arm!r}")


def play_one(job: tuple[str, str, int]) -> dict:
    field, arm, seed = job
    if _DATA is None:
        raise RuntimeError("evaluation worker was not initialized")
    env = TFTEnv(
        _DATA,
        scouting="tokens",
        max_actions_per_round=600,
        opponent_factory=opponent_factory(_DATA, field, seed),
    )
    policy = agent_policy(env, arm, seed)
    original_fight = search_mod.fight_value
    fight_calls = 0

    def counted_fight(*args, **kwargs):
        nonlocal fight_calls
        fight_calls += 1
        return original_fight(*args, **kwargs)

    search_mod.fight_value = counted_fight
    started = time.process_time()
    try:
        observation, _ = env.reset(seed=seed)
        info = {}
        for _step in range(200_000):
            action = int(policy(observation, env.action_masks()))
            observation, _reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        else:
            raise RuntimeError(f"{field}/{arm} did not terminate on seed {seed}")
    finally:
        search_mod.fight_value = original_fight

    placement = info.get("placement") or env.n_players
    # Seats still alive when the episode ends finished above the agent; the
    # game is not played on past it, so their exact placement is unknown.
    beat = {
        seat: (env.match.placements.get(seat) or 0) > placement
        for seat in REPLACED_SEATS
    }
    return {
        "field": field,
        "arm": arm,
        "seed": seed,
        "placement": placement,
        "beat_replaced_seats": sum(beat.values()),
        "cpu_seconds": time.process_time() - started,
        "fight_calls": fight_calls,
    }


def paired(first: list[float], second: list[float]) -> dict[str, float]:
    differences = [b - a for a, b in zip(first, second, strict=True)]
    mean = statistics.fmean(differences)
    # A smoke run of one game has no spread; report that rather than crash
    # after the games have already been paid for.
    enough = len(differences) > 1
    se = (
        statistics.stdev(differences) / math.sqrt(len(differences))
        if enough else math.nan
    )
    half = len(differences) // 2
    return {
        "delta": mean,
        "se": se,
        "t": mean / se if enough and se else 0.0,
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
        "first_half": statistics.fmean(differences[:half]) if enough else math.nan,
        "second_half": statistics.fmean(differences[half:]) if enough else math.nan,
    }


def summarise(records: list[dict]) -> tuple[dict, dict]:
    grouped: dict[tuple[str, str], list[dict]] = {
        (field, arm): [] for field in FIELDS for arm in ARMS
    }
    for record in records:
        grouped[(record["field"], record["arm"])].append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["seed"])

    summary = {}
    for (field, arm), rows in grouped.items():
        if not rows:
            continue
        placements = [row["placement"] for row in rows]
        histogram = Counter(placements)
        summary[f"{field}/{arm}"] = {
            "n": len(rows),
            "placement": statistics.fmean(placements),
            "lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "first": histogram[1] / len(rows),
            "top4": sum(p <= 4 for p in placements) / len(rows),
            "eighth": histogram[8] / len(rows),
            "histogram": [histogram[p] for p in range(1, 9)],
            "beat_replaced_seats": statistics.fmean(
                row["beat_replaced_seats"] for row in rows
            ) / len(REPLACED_SEATS),
            "cpu_seconds": statistics.fmean(row["cpu_seconds"] for row in rows),
            "fight_calls": statistics.fmean(row["fight_calls"] for row in rows),
            "placements": placements,
        }

    def column(field, arm, key=lambda p: p):
        return [key(p) for p in summary[f"{field}/{arm}"]["placements"]]

    comparisons = {}
    present = [f for f in FIELDS if all(f"{f}/{a}" in summary for a in ARMS)]
    for field in present:
        comparisons[f"{field}: full minus greedy"] = paired(
            column(field, "greedy"), column(field, "full")
        )
        comparisons[f"{field}: full minus greedy, top-four rate"] = paired(
            column(field, "greedy", lambda p: float(p <= 4)),
            column(field, "full", lambda p: float(p <= 4)),
        )
    if "default" in present:
        base_gap = [
            f - g for g, f in zip(
                column("default", "greedy"), column("default", "full"), strict=True
            )
        ]
        for field in present:
            if field == "default":
                continue
            gap = [
                f - g for g, f in zip(
                    column(field, "greedy"), column(field, "full"), strict=True
                )
            ]
            # Positive means the search edge is smaller in this field.
            comparisons[f"{field} gap minus default gap"] = paired(base_gap, gap)
    return summary, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--seed0", type=int, default=85_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--fields", nargs="+", default=list(FIELDS), choices=FIELDS)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    before = source_fingerprint()
    started = time.perf_counter()
    jobs = [
        (field, arm, args.seed0 + game)
        for game in range(args.games)
        for field in args.fields
        for arm in ARMS
    ]
    context = get_context("spawn")
    with context.Pool(args.workers, initializer=_init_worker) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    if args.json:
        # Hours of games must survive a failure in the arithmetic below.
        args.json.write_text(json.dumps({"records": records}, indent=2))
    summary, comparisons = summarise(records)
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")
    payload = {
        "source_fingerprint": before,
        "swap_kwargs": SWAP_KWARGS,
        "move_kwargs": MOVE_KWARGS,
        "replaced_seats": REPLACED_SEATS,
        "games": args.games,
        "seed0": args.seed0,
        "workers": args.workers,
        "fields": args.fields,
        "wall_seconds": time.perf_counter() - started,
        "summary": summary,
        "comparisons": comparisons,
        "records": records,
    }
    text = json.dumps(payload, indent=2)
    if args.json:
        args.json.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
