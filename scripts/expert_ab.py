"""Can the scripted teacher be made better than the bots it plays against?

Doc 99 §8's binding constraint: the clone is at parity with `scripted_policy`
(4.567 vs 4.620) and imitation caps at its teacher by construction. The seven
opponents run the *same* heuristic (`rl.opponents.GreedyPolicy`), so average
placement is pinned near 4.5 -- 4.5 being the average of eight -- unless the
teacher is made better than them specifically.

Each arm is one flag, evaluated over the same seeds. **No training**: an arm is
seconds to minutes, against ~75 minutes for a PPO arm, so the cheap search
happens here before anything is cloned.

    python scripts/expert_ab.py --episodes 300
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    evaluate,
    evaluate_scripted_parallel,
    scripted_policy,
)
from rl.timing import human, timed  # noqa: E402

ARMS: dict[str, dict] = {
    "control": {},
    "buy_synergy": {"buy_synergy": True},
    "match_items": {"match_items": True},
    "corner_carry": {"corner_carry": True},
    "all_three": {"buy_synergy": True, "match_items": True, "corner_carry": True},
}


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    """Paired difference b-a and its t-statistic.

    Arms share seeds, so the comparison is paired -- considerably more
    sensitive than treating them as independent samples (doc 99 entry 18.6).
    """
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n)
    return mean, (mean / se if se > 0 else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--level-at-gold", type=int, nargs="*", default=[])
    parser.add_argument("--roll-at-level", type=int, nargs="*", default=[])
    parser.add_argument(
        "--sell",
        action="store_true",
        help="add a sell-the-full-bench arm, and enable selling in the roll arms",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "evaluate seeds across N processes. 97%% of measurement time is "
            "pure-Python combat ticks and games are independent and "
            "deterministic per seed, so this is close to linear "
            "(doc 99 entry 37.8). 1 keeps the serial path"
        ),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help=(
            "write per-arm placements here. Without it only the table survives "
            "the run, and any pairing not printed -- arm against arm rather "
            "than arm against control -- cannot be recovered afterwards"
        ),
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help=(
            "add a one-ply board-search arm: at the end of planning, simulate "
            "candidate boards against a panel of opponents and field the swap "
            "that wins by more (doc 99 entry 46)"
        ),
    )
    parser.add_argument(
        "--position-search",
        action="store_true",
        help="add an arm that searches where units stand (doc 99 entry 47)",
    )
    parser.add_argument(
        "--position-candidates",
        type=int,
        default=6,
        help=(
            "moves sampled per planning phase. 6 covers ~3.6%% of the ~168 "
            "legal moves on a typical board (doc 99 entry 47.6), so this is "
            "the search's budget rather than a tuning detail"
        ),
    )
    parser.add_argument(
        "--position-panel",
        type=int,
        default=1,
        help=(
            "opponents each candidate move is scored against. More budget on "
            "candidates bought nothing (doc 99 entry 47.7); the remaining "
            "question is whether a move that beats one board generalises"
        ),
    )
    parser.add_argument(
        "--base-sell",
        action="store_true",
        help=(
            "give every arm the sell branch. The flag sweep in doc 99 34.13 "
            "ran on a teacher that could not sell and whose bench filled after "
            "a few rounds, so buy_synergy/match_items/corner_carry have never "
            "been measured on a teacher playing a normal game (doc 99 42.4)"
        ),
    )
    parser.add_argument(
        "--only-sweeps",
        action="store_true",
        help="skip the five flag arms; run only the econ sweeps against control",
    )
    args = parser.parse_args()

    data = load_all()
    seeds = range(args.episodes)
    results = {}

    def run(name: str, **flags) -> None:
        """Evaluate one arm, serially or across processes."""
        import time as _time

        started = _time.perf_counter()
        if args.base_sell:
            flags.setdefault("sell_bench", True)
        search_kwargs = flags.pop("search_kwargs", None)
        if args.workers > 1:
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, search_kwargs=search_kwargs, **flags
            )
        else:
            env = TFTEnv(data=data)
            policy = scripted_policy(env, **flags)
            if search_kwargs is not None:
                from rl.search import search_policy

                policy = search_policy(env, base=policy, **search_kwargs)
            results[name] = evaluate(env, policy, seeds=seeds)
        print(
            f"  {name:<15} done  ({human(_time.perf_counter() - started)})",
            flush=True,
        )

    n_arms = (1 if args.only_sweeps else len(ARMS)) + len(args.level_at_gold) \
        + len(args.roll_at_level) + int(args.sell) + int(args.search) \
        + int(args.position_search)

    arms = {"control": {}} if args.only_sweeps else ARMS
    # Search arms cost several times a plain arm -- each candidate board is a
    # full combat simulation, times `trials`. Keeping them under a separate
    # kind stops one from poisoning the estimate for the other.
    timer = timed(
        "expert_ab+search" if (args.search or args.position_search) else "expert_ab",
        episodes=args.episodes,
        arms=n_arms,
        workers=args.workers,
    )
    timer.__enter__()
    for name, flags in arms.items():
        run(name, **flags)

    # Econ is a scalar sweep rather than a flag, so it is opt-in.
    for gold in args.level_at_gold:
        run(f"level@{gold}g", level_at_gold=gold)

    # Rolling is the other unbounded gold sink. Until doc 99 entry 36.6 the
    # expert had no reroll branch at all, so every econ arm ever measured
    # played a game in which levelling was the only thing to spend on.
    # Selling is measured on its own as well as under the roll arms, because
    # a full bench masks every buy action: without it the reroll branch spins
    # on a shop it cannot buy from (doc 99 entry 37.4).
    if args.sell:
        run("sell", sell_bench=True)

    for level in args.roll_at_level:
        name = f"roll@{level}+sell" if args.sell else f"roll@{level}"
        run(name, roll_at_level=level, sell_bench=args.sell)

    if args.search:
        run("search", search_kwargs={})
    if args.position_search:
        # The axis doc 99 entry 47.2 measured: rearranging the same units is
        # worth 2.8x the engine's own noise, against an incumbent rule two
        # lines long.
        run(
            f"position@{args.position_candidates}p{args.position_panel}",
            search_kwargs={
                "mode": "move",
                "max_candidates": args.position_candidates,
                "panel_size": args.position_panel,
            },
        )

    timer.__exit__(None, None, None)

    control = results["control"]
    print(
        f"\n{'arm':<15}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
        f"{'vs control (paired)':>24}"
    )
    for name, r in results.items():
        if name == "control":
            delta = ""
        else:
            mean, t = paired_t(control.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(
            f"{name:<15}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
            f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{delta:>24}"
        )
    if args.json:
        args.json.write_text(
            json.dumps(
                {name: r.as_dict() | {"placements": r.placements}
                 for name, r in results.items()},
                indent=2,
            )
        )
        print(f"\nplacements written to {args.json}")

    print("\n4.500 = parity with the seven bots, which run the same heuristic.")
    print("Negative deltas are better (lower placement).")


if __name__ == "__main__":
    main()
