"""Is slow-rolling viable in this engine, specified correctly this time?

Doc 99 entry 67 is flagged ⚠️ because the arm it labelled "slow roll" was
``level_at_gold=80``, which starves levelling from stage 1. That tests *never
level*, and its t=+9.70 largely re-measures entry 67's own finding that board
size dominates. Real slow-rolling levels normally to 6-7, **stops there**, and
rolls the surplus.

Separating those needs a knob that caps the destination without delaying the
journey. `scripted_policy` did not have one; ``level_cap`` is it.

The arms, all on the **teacher configuration** (``sell_bench`` plus the three
expert flags -- the policy that scores 3.030, not `expert_ab.py`'s bare
control):

* ``control``            -- must reproduce **3.030**, or nothing below reads.
* ``roll@6``             -- must reproduce entry 66.1's **3.257**. This is the
  arm the session brief asked for; it already exists, and replicating it is
  what licenses treating the capped arms as the new information.
* ``cap7`` / ``cap8``    -- the cap alone. **The load-bearing control**: entry
  67 says slots decide fights, so capping costs something. Without this arm a
  capped-and-rolling result cannot be split into "the cap cost X" and "rolling
  gained Y".
* ``cap7+roll@6`` etc.   -- the conjunction that has never been run.

Reading it: the conjunction beats control only if rolling gains more than the
cap costs. If ``cap7+roll@6`` lands at ``cap7`` it means rolling converts
nothing and the gold sink is genuinely absent; if it lands at control it means
rolling exactly pays for the slots it costs.

No training seed is involved, so these need no replication caveat (entry 65).

**Do not edit engine or `rl/` source while this is running.** Arms are
evaluated in `spawn`ed workers that re-import from disk, so a source file
touched mid-run silently changes the policy between arms. The first run of this
script overlapped a mutation test that rewrote `rl/evaluate.py`, and two arms
were measured against deliberately broken code while the table still printed a
plausible-looking number. `--verify-source` guards against the repeat.

    .venv/bin/python scripts/slowroll_ab.py --episodes 300 --workers 10
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.evaluate import evaluate_scripted_parallel  # noqa: E402
from rl.timing import timed  # noqa: E402

# The teacher every 3.030 in doc 99 was measured on: --expert-sell plus
# --expert-flags, level_at_gold=30, no rolling. Named here rather than
# defaulted, because `scripted_policy`'s own defaults are the *historical*
# policy (~4.9), and confusing the two is how an arm gets compared to the
# wrong control.
TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}

ARMS: dict[str, dict] = {
    "control": {},
    "roll@6": {"roll_at_level": 6},
    "cap7": {"level_cap": 7},
    "cap7+roll@6": {"level_cap": 7, "roll_at_level": 6},
    "cap8": {"level_cap": 8},
    "cap8+roll@7": {"level_cap": 8, "roll_at_level": 7},
}


def source_fingerprint() -> str:
    """Hash of every `engine/` and `rl/` source file.

    Workers are `spawn`ed per arm and re-import from disk, so an edit landing
    between two arms changes the policy without changing the table's headings.
    Comparing this across arms turns that into a loud failure instead of a
    quiet one.
    """
    import hashlib

    root = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("engine/**/*.py")) + sorted(root.glob("rl/**/*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def paired_t(a: list[int], b: list[int]) -> tuple[float, float]:
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    if n < 2:
        return mean, 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, (mean / math.sqrt(var / n) if var > 0 else 0.0)


def mechanism(flags: dict, episodes: int, env_kwargs: dict | None = None) -> dict:
    """Gold, board size, level and star distribution for one arm.

    Placement alone cannot distinguish "rolling is bad play" from "the reroll
    branch burns gold without converting it" (entry 37.2 outcome D), and entry
    66.3's finding -- gold at 107.8 by round 28 with ~0% 3-stars -- is the whole
    reason this arm exists. Measured on the agent seat only, sampled at the same
    checkpoints 66.3 used so the numbers are comparable to it.
    """
    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy

    # Stars are sampled at the checkpoints, *not* at episode end. A dead seat
    # holds no units, so an end-of-episode tally silently reads 0% for both
    # 2- and 3-star on exactly the arms that place worst -- a vacuous zero that
    # looks identical to "rolling converts nothing".
    checkpoints = (12, 20, 28)
    acc = {r: {"gold": 0.0, "board": 0.0, "level": 0.0, "n": 0} for r in checkpoints}
    stars: Counter[int] = Counter()
    star_games = 0
    rerolls = 0

    data = load_all()
    env = TFTEnv(data=data, **(env_kwargs or {}))
    policy = scripted_policy(env, **flags)
    space = env.action_space_helper

    for seed in range(episodes):
        obs, info = env.reset(seed=seed)
        seen: set[int] = set()
        done = False
        while not done:
            mask = env.action_masks()
            action = policy(obs, mask)
            if action == space.reroll_index:
                rerolls += 1
            obs, _reward, done, _trunc, _info = env.step(action)
            assert env.match is not None
            played = env.match.rounds_played
            if played in checkpoints and played not in seen and env.player.alive:
                seen.add(played)
                row = acc[played]
                row["gold"] += env.player.gold
                row["board"] += len(env.player.board)
                row["level"] += env.player.level
                row["n"] += 1
                if played == checkpoints[-1]:
                    star_games += 1
                    for unit in env.player.all_units:
                        stars[unit.star_level] += 1

    total = sum(stars.values())
    return {
        "checkpoints": {
            r: {
                "gold": row["gold"] / row["n"],
                "board": row["board"] / row["n"],
                "level": row["level"] / row["n"],
                "n": row["n"],
            }
            for r, row in acc.items()
            if row["n"]
        },
        # None rather than 0.0 when no game reached the checkpoint alive, so a
        # missing measurement cannot be read as a measured zero.
        "star3_rate": (stars[3] / total) if total else None,
        "star2_rate": (stars[2] / total) if total else None,
        "star_games": star_games,
        "units_seen": total,
        "rerolls_per_game": rerolls / episodes,
    }


def _pct(value: float | None) -> str:
    """'-' for an unmeasured rate, so it cannot be misread as a measured zero."""
    return f"{value:.1%}" if value is not None else "-"


def _cell(checkpoints: dict):
    """Formatter for one arm's checkpoint row; '-' where no game reached it."""
    def cell(round_number: int, key: str) -> str:
        row = checkpoints.get(round_number)
        return f"{row[key]:.1f}" if row else "-"

    return cell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--mechanism-episodes",
        type=int,
        default=30,
        help=(
            "games per arm for the gold/star pass, which is serial and cheap. "
            "0 skips it and reports placement only"
        ),
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--arms",
        nargs="*",
        default=None,
        help="subset of arm names to run; control is always included",
    )
    parser.add_argument(
        "--budgets",
        type=int,
        nargs="*",
        default=[],
        help=(
            "also run every arm at these `max_actions_per_round` values. The "
            "agent seat spends one action per reroll out of a budget of 12 "
            "shared with buying, selling and placing, while the seven "
            "`GreedyPolicy` bots plan a whole phase at once and are not "
            "capped at all. Real slow-rolling spends 40-60 rolls in a single "
            "round, which 12 forecloses -- so this asks whether the missing "
            "gold sink of entry 66.3 is a fact about the game or about the "
            "wrapper"
        ),
    )
    args = parser.parse_args()

    arms = ARMS
    if args.arms:
        arms = {"control": {}} | {k: v for k, v in ARMS.items() if k in args.arms}

    # (label, arm flags, env kwargs). The default budget carries no suffix so
    # its rows stay comparable to every figure already in doc 99.
    plan: list[tuple[str, dict, dict]] = [(n, f, {}) for n, f in arms.items()]
    for budget in args.budgets:
        plan += [
            (f"{n}/a{budget}", f, {"max_actions_per_round": budget})
            for n, f in arms.items()
        ]

    seeds = list(range(args.episodes))
    results = {}
    env_for = {}
    fingerprint = source_fingerprint()
    print(f"source fingerprint: {fingerprint}")
    with timed("slowroll_ab", episodes=args.episodes,
               arms=len(plan), workers=args.workers):
        for name, flags, env_kwargs in plan:
            env_for[name] = env_kwargs
            results[name] = evaluate_scripted_parallel(
                seeds, workers=args.workers, env_kwargs=env_kwargs,
                **(TEACHER | flags)
            )
            now = source_fingerprint()
            if now != fingerprint:
                raise SystemExit(
                    f"engine/rl source changed mid-run ({fingerprint} -> {now}) "
                    f"while evaluating '{name}'. Workers re-import from disk, so "
                    "arms before and after ran different code and this table is "
                    "not internally comparable. Re-run on a quiet tree."
                )
            print(f"  {name:<16}{results[name].avg_placement:.3f}", flush=True)

    control = results["control"]
    print(f"\n{'arm':<16}{'place':>8}{'ci95':>7}{'LP':>8}{'1st':>7}{'top4':>7}"
          f"{'8th':>7}{'vs control (paired)':>24}")
    for name, r in results.items():
        hist = Counter(r.placements)
        last = hist[8] / len(r.placements)
        if name == "control":
            delta = ""
        else:
            mean, t = paired_t(control.placements, r.placements)
            delta = f"{mean:+.3f}  t={t:+.2f}"
        print(f"{name:<16}{r.avg_placement:>8.3f}{r.ci95:>7.3f}{r.avg_lp:>8.2f}"
              f"{r.win_rate:>7.1%}{r.top4_rate:>7.1%}{last:>7.1%}{delta:>24}")

    # The two validity anchors. Stated as pass/fail rather than left to the
    # reader, because an arm table that silently drifted off its own control is
    # exactly what entry 65 was about.
    print()
    got = control.avg_placement
    ok = abs(got - 3.030) < 0.20
    print(f"ANCHOR control = {got:.3f} vs doc 99's 3.030 -- "
          f"{'ok' if ok else '!! MISMATCH, no arm below is comparable to doc 99'}")
    if "roll@6" in results:
        got6 = results["roll@6"].avg_placement
        ok6 = abs(got6 - 3.257) < 0.20
        print(f"ANCHOR roll@6  = {got6:.3f} vs entry 66.1's 3.257 -- "
              f"{'ok' if ok6 else '!! MISMATCH'}")

    mech = {}
    if args.mechanism_episodes:
        print(f"\nmechanism ({args.mechanism_episodes} games/arm, agent seat)")
        print(f"{'arm':<16}{'r12 gold':>10}{'r20 gold':>10}{'r28 gold':>10}"
              f"{'r28 board':>11}{'r28 lvl':>9}{'2-star':>8}{'3-star':>8}"
              f"{'alive':>7}{'rolls/g':>9}")
        for name, flags, env_kwargs in plan:
            m = mechanism(TEACHER | flags, args.mechanism_episodes, env_kwargs)
            mech[name] = m
            g = _cell(m["checkpoints"])
            print(f"{name:<16}{g(12, 'gold'):>10}{g(20, 'gold'):>10}"
                  f"{g(28, 'gold'):>10}{g(28, 'board'):>11}{g(28, 'level'):>9}"
                  f"{_pct(m['star2_rate']):>8}{_pct(m['star3_rate']):>8}"
                  f"{m['star_games']:>7}{m['rerolls_per_game']:>9.1f}")
        print("\nAgent seat only, so NOT comparable to entry 66.3's 42.6/72.0/")
        print("107.8 -- those averaged all living seats, which run GreedyPolicy")
        print("with a different econ rule. Read these arm-against-arm.")
        print("An arm that rolls but leaves 3-star near 0% is burning gold")
        print("without converting it (entry 37.2 outcome D).")

    if args.json:
        args.json.write_text(json.dumps(
            {name: r.as_dict() | {"placements": r.placements,
                                  "mechanism": mech.get(name)}
             for name, r in results.items()}, indent=1))
        print(f"\nper-episode results: {args.json}")


if __name__ == "__main__":
    main()
