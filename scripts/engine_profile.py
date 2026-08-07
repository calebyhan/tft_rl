"""What does this engine's economy actually look like, round by round?

Doc 99 entry 69.4's open item, and the one thing never done in 69 entries:
**every ceiling in this log is measured against the engine's own economy.**
Entries 66-69 concluded that gold accumulates without a sink, that 3-stars
never occur, and that the action budget gates the whole thing -- all judged
against the engine itself. Whether the engine's economy resembles real TFT has
never been checked, so the tuning has been optimising an unvalidated model.

This emits the engine's side of that comparison: a distributional profile keyed
by **stage-round label** (`3-2`, `4-1`), which is the form real TFT benchmarks
are published in.

**Eight `GreedyPolicy` seats driving `Match` directly, not the RL wrapper.**
`max_actions_per_round` does not apply to `GreedyPolicy`, which plans a whole
phase at once. That is deliberate: entry 69 showed the 12-action budget gates
the agent's economy, so profiling *through* the wrapper would measure the
wrapper and call it the engine. This measures what the simulator does when
nothing is throttling it, which is what real TFT statistics are comparable to.

Sampled after each round completes (post-combat, post-income), over living
players only -- a dead seat has no economy, and averaging it in would drag
every late-game figure toward zero.

    .venv/bin/python scripts/engine_profile.py --games 60
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from rl.opponents import GreedyPolicy  # noqa: E402


def profile(data, games: int, seed0: int = 0, econ=None) -> dict:
    rows: dict[str, list[dict]] = defaultdict(list)
    game_length: list[int] = []
    final_stage: list[int] = []
    # Peak star level any player reached in each game, and when a 3-star first
    # appeared. 66.3 reported "~0% 3-star" from a single late checkpoint; a
    # first-occurrence tally cannot miss one that appeared and was then sold.
    peak_star: list[int] = []
    three_star_round: list[str] = []
    elimination_stage: list[int] = []

    for game in range(games):
        policies = [GreedyPolicy(seed=seat, econ=econ) for seat in range(8)]
        match = Match(data, policies, seed=seed0 + game)
        alive_before = {p.player_id for p in match.living_players}
        best_star = 1
        first_three: str | None = None

        while not match.finished:
            label = f"{match.round_id.stage}-{match.round_id.round}"
            stage = match.round_id.stage
            match.play_round()

            for player in match.living_players:
                stars = Counter(u.star_level for u in player.all_units)
                total = sum(stars.values())
                best_star = max(best_star, max(stars, default=1))
                if first_three is None and stars.get(3):
                    first_three = label
                rows[label].append({
                    "level": player.level,
                    "gold": player.gold,
                    "board": len(player.board_units),
                    "max_board": player.max_board_units,
                    "hp": player.hp,
                    "units": total,
                    "star1": stars.get(1, 0),
                    "star2": stars.get(2, 0),
                    "star3": stars.get(3, 0),
                })

            alive_now = {p.player_id for p in match.living_players}
            for _ in alive_before - alive_now:
                elimination_stage.append(stage)
            alive_before = alive_now

        game_length.append(match.rounds_played)
        final_stage.append(match.round_id.stage)
        peak_star.append(best_star)
        if first_three:
            three_star_round.append(first_three)

    return {
        "rows": rows,
        "game_length": game_length,
        "final_stage": final_stage,
        "peak_star": peak_star,
        "three_star_round": three_star_round,
        "elimination_stage": elimination_stage,
        "games": games,
    }


def mean(values) -> float:
    return statistics.mean(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--econ",
        default=None,
        help="economy strategy for all 8 seats: standard, fast8, slowroll6, "
             "hyperroll. Omit for the legacy one-purchase-per-round plan",
    )
    args = parser.parse_args()

    from rl.opponents import STRATEGIES

    econ = STRATEGIES[args.econ] if args.econ else None
    data = load_all()
    result = profile(data, args.games, econ=econ)
    print(f"econ strategy: {args.econ or 'legacy (one purchase per round)'}")
    rows = result["rows"]

    def sort_key(label: str) -> tuple[int, int]:
        stage, round_ = label.split("-")
        return int(stage), int(round_)

    print(f"{args.games} games, 8 GreedyPolicy seats, living players only\n")
    print(f"{'round':>7}{'alive':>7}{'level':>7}{'gold':>7}{'board':>7}"
          f"{'cap':>5}{'hp':>7}{'1*':>7}{'2*':>7}{'3*':>7}")
    for label in sorted(rows, key=sort_key):
        sample = rows[label]
        units = sum(r["units"] for r in sample) or 1
        print(f"{label:>7}"
              f"{len(sample) / args.games:>7.2f}"
              f"{mean([r['level'] for r in sample]):>7.2f}"
              f"{mean([r['gold'] for r in sample]):>7.1f}"
              f"{mean([r['board'] for r in sample]):>7.2f}"
              f"{mean([r['max_board'] for r in sample]):>5.1f}"
              f"{mean([r['hp'] for r in sample]):>7.1f}"
              f"{sum(r['star1'] for r in sample) / units:>7.1%}"
              f"{sum(r['star2'] for r in sample) / units:>7.1%}"
              f"{sum(r['star3'] for r in sample) / units:>7.1%}")

    length = result["game_length"]
    peak = result["peak_star"]
    three = result["three_star_round"]
    print(f"\ngame length: {mean(length):.1f} rounds "
          f"(min {min(length)}, max {max(length)}); "
          f"final stage {mean(result['final_stage']):.2f}")
    print(f"games where any player reached a 3-star: "
          f"{len(three)}/{args.games} ({len(three) / args.games:.1%})")
    if three:
        print(f"  first 3-star round: {Counter(three).most_common(5)}")
    print(f"peak star level across games: {Counter(peak).most_common()}")
    print(f"eliminations by stage: "
          f"{sorted(Counter(result['elimination_stage']).items())}")

    if args.json:
        args.json.write_text(json.dumps({
            "per_round": {
                label: {
                    "n": len(sample),
                    "alive": len(sample) / args.games,
                    "level": mean([r["level"] for r in sample]),
                    "gold": mean([r["gold"] for r in sample]),
                    "board": mean([r["board"] for r in sample]),
                    "max_board": mean([r["max_board"] for r in sample]),
                    "hp": mean([r["hp"] for r in sample]),
                    "star1": sum(r["star1"] for r in sample),
                    "star2": sum(r["star2"] for r in sample),
                    "star3": sum(r["star3"] for r in sample),
                }
                for label, sample in rows.items()
            },
            "game_length": length,
            "three_star_games": len(three),
            "games": args.games,
        }, indent=1))
        print(f"\nwritten to {args.json}")


if __name__ == "__main__":
    main()
