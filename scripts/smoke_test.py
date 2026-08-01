"""End-to-end engine smoke test (milestone 5, doc 03 sec 4).

Runs full 8-player games with scripted policies and checks that each one
terminates with a sane winner, conserves the champion pool, and produces
consistent placements.

    python scripts/smoke_test.py [--games N] [--seed N] [--policy greedy|random|mixed]
    python scripts/smoke_test.py --trace          # print a round-by-round table
"""

from __future__ import annotations

import argparse
import collections
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from engine.shop import SharedPool  # noqa: E402
from rl.opponents import GreedyPolicy, RandomPolicy  # noqa: E402

POLICIES = {
    "greedy": lambda seat, seed: GreedyPolicy(seed=seed * 100 + seat),
    "random": lambda seat, seed: RandomPolicy(seed=seed * 100 + seat),
    "mixed": lambda seat, seed: (
        GreedyPolicy(seed=seed * 100 + seat)
        if seat % 2 == 0
        else RandomPolicy(seed=seed * 100 + seat)
    ),
}


def check_match(match: Match, result, reference_pool_total: int) -> list[str]:
    """Assert the invariants a finished game must satisfy."""
    problems: list[str] = []
    n = match.structure.players

    placements = sorted(result.placements.values())
    if placements != list(range(1, n + 1)):
        problems.append(f"placements are not a permutation of 1..{n}: {placements}")
    if result.winner is None:
        problems.append("no winner assigned")
    elif not match.players[result.winner].alive:
        problems.append(f"winner {result.winner} is not alive")

    alive = [p.player_id for p in match.players if p.alive]
    if len(alive) > 1 and match.round_id.stage <= match.structure.max_stages:
        problems.append(f"game ended with {len(alive)} players alive: {alive}")

    for player in match.players:
        if player.hp < 0:
            problems.append(f"player {player.player_id} has negative hp {player.hp}")
        if player.alive and player.placement != 1 and len(alive) == 1:
            problems.append(f"survivor {player.player_id} did not place 1st")
        if len(player.board) > player.max_board_units:
            problems.append(
                f"player {player.player_id} fields {len(player.board)} units "
                f"at level {player.level}"
            )
        if len(player.bench) != player.config.bench_size:
            problems.append(
                f"player {player.player_id} bench has {len(player.bench)} slots"
            )

    held = sum(u.pool_copies for p in match.players for u in p.all_units)
    in_shops = sum(1 for p in match.players for s in p.shop.slots if s is not None)
    total = match.pool.total_remaining + held + in_shops
    if total != reference_pool_total:
        problems.append(
            f"champion pool leaked: {match.pool.total_remaining} free + {held} held "
            f"+ {in_shops} in shops = {total}, expected {reference_pool_total}"
        )
    return problems


def trace(match: Match, result) -> None:
    print(f"\n{'round':>6} " + " ".join(f"{'P' + str(i):>13}" for i in range(len(match.players))))
    by_round: dict[str, dict[int, str]] = collections.defaultdict(dict)
    for report in result.reports:
        mark = "W" if report.won else "L"
        by_round[str(report.round_id)][report.player_id] = (
            f"{mark} hp{report.hp_after:>3} g{report.gold_after:>2} L{report.level_after}"
        )
    for round_text, row in by_round.items():
        cells = " ".join(f"{row.get(i, '-- eliminated'):>13}" for i in range(len(match.players)))
        print(f"{round_text:>6} {cells}")
    print("\nfinal placements:")
    for player_id, placement in sorted(result.placements.items(), key=lambda kv: kv[1]):
        p = match.players[player_id]
        board = ", ".join(sorted(u.name for u in p.board_units)) or "(empty)"
        print(f"  {placement}. P{player_id}  hp {p.hp:>3}  lvl {p.level}  {board}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--policy", choices=sorted(POLICIES), default="mixed")
    parser.add_argument("--trace", action="store_true", help="print a round table for game 1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.ERROR,
        format="%(levelname)s %(name)s: %(message)s",
    )

    data = load_all()
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    reference_pool_total = SharedPool(data).total_remaining
    factory = POLICIES[args.policy]

    wins: collections.Counter[int] = collections.Counter()
    placements: dict[int, list[int]] = collections.defaultdict(list)
    rounds: list[int] = []
    all_problems: list[str] = []
    started = time.perf_counter()

    for game in range(args.games):
        seed = args.seed + game
        policies = [factory(seat, seed) for seat in range(data.config.round_structure.players)]
        match = Match(data, policies, seed=seed, registry=registry)
        result = match.run()

        problems = check_match(match, result, reference_pool_total)
        for problem in problems:
            all_problems.append(f"game {game} (seed {seed}): {problem}")

        wins[result.winner] += 1
        for player_id, placement in result.placements.items():
            placements[player_id].append(placement)
        rounds.append(result.rounds_played)

        if args.trace and game == 0:
            trace(match, result)

    elapsed = time.perf_counter() - started
    print(f"\n=== {args.games} games, policy={args.policy}, seeds {args.seed}..{args.seed + args.games - 1} ===")
    print(f"completed in {elapsed:.1f}s ({elapsed / args.games:.2f}s per game)")
    print(f"rounds per game: min {min(rounds)}  mean {sum(rounds) / len(rounds):.1f}  max {max(rounds)}")
    print("\nseat  wins  avg placement")
    for player_id in sorted(placements):
        avg = sum(placements[player_id]) / len(placements[player_id])
        print(f"  P{player_id}  {wins[player_id]:>4}  {avg:>13.2f}")

    if all_problems:
        print(f"\nFAILED -- {len(all_problems)} invariant violation(s):")
        for problem in all_problems[:20]:
            print(f"  - {problem}")
        return 1
    print("\nOK -- all invariants held across every game.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
