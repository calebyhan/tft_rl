"""Can the engine judge human boards? Real final fights as labelled outcomes.

Doc 99 entry 160.162. Any anchor from this simulator to human rank ("the
teacher's boards are as strong as a diamond player's") trusts the engine to
judge human boards, and 111-113 found it misprices lines humans play. This
tests that trust where the answer is known. In a ranked game the last two
players fight each other every round until one dies, so the first- and
second-place final boards are exactly the two boards that fought, and the
first-place board won.

Each such pair fights ``TRIALS`` times in the engine, the real winner taking
team 0 on even trials and team 1 on odd ones. With P_i the engine's share of
fights won by the real winner (draws count a half):

* ``A`` = mean P_i -- how much probability the engine puts on what happened.
* ``C`` = mean [P_i² + (1 − P_i)²], estimated without bias -- what A would be
  if real fights were drawn from the engine's own odds. That is the ceiling:
  an engine cannot be expected to call a fight it itself calls a coin flip.
* ``S`` = (A − 0.5) / (C − 0.5) -- the share of that achievable skill the
  engine realises. 0 is no information; 1 is as good as its own noise allows.

Positions are not in the payload. Both sides are placed by entry 113's rule
(melee front row, everything else back row), whose symmetry controls read
50%, and a winner-vs-itself control is re-run here.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import statistics
import sys
from multiprocessing import get_context
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402

TRIALS = 20
CONTROL_PAIRS = 200
SEED_BASE = 162_000
BOOTSTRAP_RESAMPLES = 10_000

# place_team: row 0 is the front line for both teams; to_combat mirrors.
FRONT = [(0, c) for c in range(7)]
BACK = [(1, c) for c in range(7)]

_DATA = None


def spec_of(seat: dict, data, counts: dict) -> list[tuple[str, int, tuple[str, ...]]]:
    """A seat's final board as (champion, star, items), keeping what the engine knows.

    Unknown champions (summons, PvE units) and unknown items are dropped; 4-star
    units are clamped to 3 (132.4). Every drop and clamp is counted.
    """
    cap = data.config.max_items_per_unit
    out = []
    for unit in seat.get("units", []):
        champion = unit.get("character_id")
        if champion not in data.champions:
            counts["unknown_units"] += 1
            continue
        star = unit.get("tier") or 1
        if star > 3:
            counts["clamped_4_stars"] += 1
            star = 3
        items = []
        for item in unit.get("items", []):
            if item in data.items and len(items) < cap:
                items.append(item)
            else:
                counts["dropped_items"] += 1
        counts["kept_items"] += len(items)
        out.append((champion, star, tuple(items)))
    return out


def final_pairs(matches: list[dict], data) -> tuple[list[dict], dict]:
    """(winner, loser) final boards from every game whose top two ended together."""
    counts = {"matches": len(matches), "unequal_last_round": 0, "empty_or_oversized": 0,
              "unknown_units": 0, "clamped_4_stars": 0, "dropped_items": 0,
              "kept_items": 0}
    pairs = []
    slots = len(FRONT) + len(BACK)
    for match in matches:
        by_place = {seat.get("placement"): seat for seat in match.get("participants", [])}
        if 1 not in by_place or 2 not in by_place:
            continue
        if by_place[1].get("last_round") != by_place[2].get("last_round"):
            counts["unequal_last_round"] += 1
            continue
        winner = spec_of(by_place[1], data, counts)
        loser = spec_of(by_place[2], data, counts)
        if not winner or not loser or len(winner) > slots or len(loser) > slots:
            counts["empty_or_oversized"] += 1
            continue
        pairs.append({"match_id": match.get("match_id"), "winner": winner, "loser": loser})
    counts["pairs"] = len(pairs)
    return pairs, counts


def build(spec, data, registry, board, team) -> list[UnitInstance]:
    """Entry 113's placement: melee to the front row, the rest behind."""
    units, slots = [], []
    front = back = 0
    for champion_id, star, item_ids in spec:
        champion = data.champions[champion_id]
        if champion.stats.attack_range <= 1 and front < len(FRONT):
            slots.append(FRONT[front])
            front += 1
        elif back < len(BACK):
            slots.append(BACK[back])
            back += 1
        else:
            slots.append(FRONT[front])
            front += 1
        units.append(UnitInstance(
            champion, star, [data.items[i] for i in item_ids], registry=registry))
    return place_team(units, slots, team=team, board=board)


def fight(data, left, right, seed: int) -> float:
    """1 if ``left`` wins, 0 if it loses, 0.5 on a draw, by survivors."""
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    board = Board()
    team0 = build(left, data, registry, board, 0)
    team1 = build(right, data, registry, board, 1)
    CombatSimulator(team0, team1, data, seed=seed, board=board).run()
    ours = sum(1 for unit in team0 if unit.alive)
    theirs = sum(1 for unit in team1 if unit.alive)
    return 1.0 if ours > theirs else 0.5 if ours == theirs else 0.0


def judge(data, winner, loser, trials: int, seed: int) -> list[float]:
    """The real winner's result in each trial, alternating which team it plays."""
    out = []
    for trial in range(trials):
        if trial % 2 == 0:
            out.append(fight(data, winner, loser, seed + trial))
        else:
            out.append(1.0 - fight(data, loser, winner, seed + trial))
    return out


def unbiased_square(xs: list[float]) -> float:
    """Unbiased estimate of (E x)² from iid samples: (S² − Σx²) / (n(n − 1))."""
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two trials")
    total = sum(xs)
    return (total * total - sum(x * x for x in xs)) / (n * (n - 1))


def skill(outcomes: list[list[float]], resamples: int = BOOTSTRAP_RESAMPLES,
          seed: int = 0) -> dict[str, float]:
    """A, C and S over matches, with normal / delta-method intervals.

    The bootstrap interval is reported as a check only; 160.161 showed a
    percentile endpoint moving with the resampling seed.
    """
    p = [statistics.fmean(xs) for xs in outcomes]
    c = [unbiased_square(xs) + unbiased_square([1.0 - x for x in xs]) for xs in outcomes]
    n = len(p)
    a_mean, c_mean = statistics.fmean(p), statistics.fmean(c)
    a_se = statistics.stdev(p) / math.sqrt(n)
    s = (a_mean - 0.5) / (c_mean - 0.5) if c_mean != 0.5 else math.nan
    # Delta method for a ratio of two correlated means.
    var_a, var_c = statistics.variance(p), statistics.variance(c)
    cov = sum((x - a_mean) * (y - c_mean) for x, y in zip(p, c, strict=True)) / (n - 1)
    d = c_mean - 0.5
    s_var = (var_a / d**2 + (a_mean - 0.5) ** 2 * var_c / d**4
             - 2 * (a_mean - 0.5) * cov / d**3) / n
    s_se = math.sqrt(max(s_var, 0.0))

    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        index = [rng.randrange(n) for _ in range(n)]
        denominator = sum(c[i] for i in index) / n - 0.5
        if denominator:
            draws.append((sum(p[i] for i in index) / n - 0.5) / denominator)
    draws.sort()
    return {
        "n": n,
        "A": a_mean, "A_ci_low": a_mean - 1.96 * a_se, "A_ci_high": a_mean + 1.96 * a_se,
        "C": c_mean,
        "S": s, "S_ci_low": s - 1.96 * s_se, "S_ci_high": s + 1.96 * s_se,
        "S_bootstrap_low": draws[int(0.025 * (len(draws) - 1))] if draws else math.nan,
        "S_bootstrap_high": draws[math.ceil(0.975 * (len(draws) - 1))] if draws else math.nan,
        "agreement": statistics.fmean(1.0 if x > 0.5 else 0.5 if x == 0.5 else 0.0
                                      for x in p),
    }


def _init_worker() -> None:
    global _DATA
    logging.disable(logging.WARNING)
    _DATA = load_all()


def _job(job) -> list[float]:
    index, winner, loser, trials = job
    return judge(_DATA, winner, loser, trials, SEED_BASE + index * trials)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--trials", type=int, default=TRIALS)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    data = load_all()
    report = {"trials": args.trials, "seed_base": SEED_BASE, "files": {}}
    context = get_context("spawn")
    with context.Pool(args.workers, initializer=_init_worker) as pool:
        for path in args.files:
            matches = json.loads(path.read_text())["matches"]
            pairs, counts = final_pairs(matches, data)
            pairs = pairs[: args.limit] if args.limit else pairs
            jobs = [(i, pr["winner"], pr["loser"], args.trials) for i, pr in enumerate(pairs)]
            outcomes = pool.map(_job, jobs, chunksize=4)
            controls = pool.map(_job, [
                (i, pr["winner"], pr["winner"], args.trials)
                for i, pr in enumerate(pairs[:CONTROL_PAIRS])
            ], chunksize=4)
            control = [x for xs in controls for x in xs]
            result = {
                "counts": counts,
                "skill": skill(outcomes),
                "control_mean": statistics.fmean(control),
                "control_se": statistics.stdev(control) / math.sqrt(len(control)),
                "outcomes": outcomes,
            }
            report["files"][path.name] = result
            summary = result["skill"]
            print(f"{path.name}: pairs {summary['n']}  A {summary['A']:.3f} "
                  f"[{summary['A_ci_low']:.3f}, {summary['A_ci_high']:.3f}]  C {summary['C']:.3f}  "
                  f"S {summary['S']:.3f} [{summary['S_ci_low']:.3f}, {summary['S_ci_high']:.3f}]  "
                  f"agree {summary['agreement']:.3f}  control {result['control_mean']:.3f}")
            print(f"  counts: {counts}")
    if len(args.files) > 1:
        pooled = skill([xs for result in report["files"].values()
                        for xs in result["outcomes"]])
        report["pooled"] = pooled
        print(f"pooled: pairs {pooled['n']}  A {pooled['A']:.3f}  C {pooled['C']:.3f}  "
              f"S {pooled['S']:.3f} [{pooled['S_ci_low']:.3f}, {pooled['S_ci_high']:.3f}]  "
              f"bootstrap [{pooled['S_bootstrap_low']:.3f}, {pooled['S_bootstrap_high']:.3f}]")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
