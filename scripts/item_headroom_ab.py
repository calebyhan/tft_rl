"""Measure post-board item-allocation headroom (doc 99 entry 160.108).

The control is the shipped ``GreedyPolicy`` item phase: after the board is
settled, take bag slot zero and put it on the strongest fielded unit with room.
The treatment differs only at that point.  It exact-simulates alternative item
and target choices, then lets the shipped rule finish any items it did not
choose itself.

The ceiling arm jointly searches up to the first two equips.  This is not a
claim of globally optimal itemisation; it is a deliberately expensive ceiling
for the two decisions the old item search attempted, with both item order and
target now variable and with real component-combination semantics.

Pilot (placement is discarded):

    .venv/bin/python scripts/item_headroom_ab.py --games 2 --workers 2

The real run should be launched only after the pilot's cost and diagnostics
have been written to doc 99.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.evaluate import LP_BY_PLACEMENT, SEARCH_SEED_OFFSET  # noqa: E402
from rl.opponents import (  # noqa: E402
    FAST8,
    GreedyPolicy,
    _equip_phase,
    _fill_board,
    _strength,
    default_opponent,
)
from rl.search import best_item_prefix  # noqa: E402

_DATA = None


@dataclass(frozen=True)
class SearchBudget:
    depth: int
    panel_size: int
    trials: int
    state_seeded: bool = True


ARMS = {
    "control": None,
    "repaired": SearchBudget(depth=1, panel_size=2, trials=2),
    "ceiling": SearchBudget(depth=2, panel_size=4, trials=6),
}


def _init() -> None:
    global _DATA
    _DATA = load_all()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in (
        "engine/player.py",
        "engine/unit.py",
        "rl/opponents.py",
        "rl/search.py",
        "scripts/item_headroom_ab.py",
    ):
        digest.update((REPO_ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


class ItemHeadroomPolicy(GreedyPolicy):
    """Greedy planning with an optional exact item-assignment finaliser."""

    def __init__(self, *args, budget: SearchBudget | None, search_seed: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget
        # Never share this with GreedyPolicy.rng: search cost or candidate order
        # must not perturb later fielding or anvil choices.
        self.search_rng = random.Random(search_seed)
        self.search_decisions = 0
        self.changed_layouts = 0
        self.component_candidates = 0
        self.component_completions = 0
        self.candidate_boards = 0
        self.fight_calls = 0

    def plan(self, player, context) -> None:
        # GreedyPolicy.plan verbatim through board settlement. Keeping the item
        # finaliser outside the parent is what makes the ordering under test
        # explicit and prevents a searched item landing on a soon-benched unit.
        if self.econ is not None:
            self._econ_plan(player, context)
        else:
            self._legacy_plan(player, context)
        self._sell_surplus(player, context)
        _fill_board(player, self.rng, key=_strength)

        if self.budget is None:
            _equip_phase(player)
            return
        self._search_items(player, context)

    def _search_items(self, player, context) -> None:
        best_prefix, diagnostics = best_item_prefix(
            player,
            context.match,
            self.search_rng,
            depth=self.budget.depth,
            panel_size=self.budget.panel_size,
            trials=self.budget.trials,
            state_seeded=self.budget.state_seeded,
        )
        for field in (
            "search_decisions",
            "changed_layouts",
            "component_candidates",
            "component_completions",
            "candidate_boards",
            "fight_calls",
        ):
            setattr(self, field, getattr(self, field) + diagnostics[field])

        original_bag = tuple(player.item_bag)
        for token, own_hex in best_prefix:
            item = original_bag[token]
            player.equip_from_bag(item.id, player.board[own_hex])
        _equip_phase(player)


def play_one(job) -> dict:
    arm, seed = job
    data = _DATA if _DATA is not None else load_all()
    policy = ItemHeadroomPolicy(
        seed=0,
        econ=FAST8,
        budget=ARMS[arm],
        search_seed=seed + SEARCH_SEED_OFFSET,
    )
    policies = [policy] + [default_opponent(i) for i in range(1, 8)]
    started = time.perf_counter()
    result = Match(data, policies, seed=seed).run()
    return {
        "arm": arm,
        "seed": seed,
        "placement": result.placement_of(0),
        "seconds": time.perf_counter() - started,
        "search_decisions": policy.search_decisions,
        "changed_layouts": policy.changed_layouts,
        "component_candidates": policy.component_candidates,
        "component_completions": policy.component_completions,
        "candidate_boards": policy.candidate_boards,
        "fight_calls": policy.fight_calls,
    }


def paired_t(control: list[float], treatment: list[float]) -> tuple[float, float]:
    diffs = [b - a for a, b in zip(control, treatment, strict=True)]
    mean = statistics.fmean(diffs)
    if len(diffs) < 2:
        return mean, 0.0
    sd = statistics.stdev(diffs)
    return mean, mean / (sd / math.sqrt(len(diffs))) if sd else 0.0


def summarise(records: list[dict], arms: tuple[str, ...]) -> dict:
    grouped = {arm: [] for arm in arms}
    for record in records:
        grouped[record["arm"]].append(record)
    for group in grouped.values():
        group.sort(key=lambda row: row["seed"])

    summary = {}
    for arm, group in grouped.items():
        placements = [row["placement"] for row in group]
        counts = Counter(placements)
        summary[arm] = {
            "n": len(group),
            "placement": statistics.fmean(placements),
            "avg_lp": statistics.fmean(LP_BY_PLACEMENT[p] for p in placements),
            "win_rate": counts[1] / len(group),
            "top4": sum(p <= 4 for p in placements) / len(group),
            "last": counts[8] / len(group),
            "distribution": {str(p): counts[p] for p in range(1, 9)},
            "placements": placements,
        }
        for field in (
            "seconds",
            "search_decisions",
            "changed_layouts",
            "component_candidates",
            "component_completions",
            "candidate_boards",
            "fight_calls",
        ):
            summary[arm][field] = statistics.fmean(row[field] for row in group)

    control = summary.get("control")
    if control is not None:
        for arm in arms:
            if arm == "control":
                continue
            delta, t_value = paired_t(control["placements"], summary[arm]["placements"])
            summary[arm]["vs_control"] = delta
            summary[arm]["paired_t"] = t_value
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed0", type=int, default=51_000)
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help=f"comma-separated subset of {','.join(ARMS)}",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    arms = tuple(part.strip() for part in args.arms.split(",") if part.strip())
    unknown = set(arms) - set(ARMS)
    if unknown:
        parser.error(f"unknown arms: {', '.join(sorted(unknown))}")
    if "control" not in arms:
        parser.error("control must be included for paired interpretation")

    before = source_fingerprint()
    print(f"source fingerprint: {before}", flush=True)
    jobs = [(arm, args.seed0 + game) for arm in arms for game in range(args.games)]
    started = time.perf_counter()
    with Pool(args.workers, initializer=_init) as pool:
        records = pool.map(play_one, jobs, chunksize=1)
    elapsed = time.perf_counter() - started
    after = source_fingerprint()
    if after != before:
        raise RuntimeError(f"source changed during run: {before} -> {after}")

    summary = summarise(records, arms)
    print(
        f"{'arm':<10}{'place':>8}{'LP':>8}{'1st':>7}{'top4':>7}{'8th':>7}"
        f"{'search':>9}{'changed':>9}{'comb':>8}{'boards':>10}{'fights':>10}{'sec':>9}"
    )
    for arm in arms:
        row = summary[arm]
        print(
            f"{arm:<10}{row['placement']:>8.3f}{row['avg_lp']:>8.2f}"
            f"{row['win_rate']:>7.1%}{row['top4']:>7.1%}{row['last']:>7.1%}"
            f"{row['search_decisions']:>9.1f}{row['changed_layouts']:>9.1f}"
            f"{row['component_completions']:>8.1f}{row['candidate_boards']:>10.1f}"
            f"{row['fight_calls']:>10.1f}{row['seconds']:>9.1f}"
        )
        if arm != "control":
            print(
                f"  {arm} minus control: {row['vs_control']:+.3f} placement "
                f"(t={row['paired_t']:+.2f}, n={row['n']}); "
                f"component candidates/game={row['component_candidates']:.1f}"
            )
    print(f"wall={elapsed:.1f}s fingerprint={after}")

    payload = {
        "source_fingerprint": after,
        "seed0": args.seed0,
        "games": args.games,
        "workers": args.workers,
        "wall_seconds": elapsed,
        "arms": {
            arm: None if ARMS[arm] is None else ARMS[arm].__dict__
            for arm in arms
        },
        "summary": summary,
        "records": records,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
