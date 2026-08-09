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
    .venv/bin/python scripts/engine_profile.py --games 300 --fidelity-json e.json

`--fidelity-json` emits a second, differently-conditioned profile in the schema
`scripts/reference_profile.py` produces from real Riot matches, for doc 99
entry 97's comparison. It is separate from the table above because Riot's
match-v1 gives only *end-of-game state per participant* -- there is no
reference counterpart to "mean gold at 4-3 over living players". What there is
is a cross-section of players at the moment they died, so the fidelity view
snapshots each player going into the round they were eliminated in. The two
views answer different questions and are not interchangeable; comparing the
living-player table against Riot's dying-player cross-section would be a
mismatched comparison wearing a table.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts

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


# --------------------------------------------------------------------------
# The fidelity view: same conditioning as Riot's match-v1 cross-section.
# --------------------------------------------------------------------------

def _snapshot(player) -> dict:
    """A player's state as they go into a round -- the board they fight with.

    Taken *before* `play_round`, because `Match._eliminate_dead` releases a
    dead player's units back to the pool: after the round there is nothing left
    to read, and their last surviving snapshot would be the previous round's.
    """
    # `board_units`, not `all_units`: Riot's per-participant `units` list is
    # the fielded board. Counting the bench too reads 16-17 units against a
    # real-data 8-9 and would show up as a fabricated board-size discrepancy,
    # and a 3-star sitting on the bench would be counted here and invisible
    # there.
    board = player.board_units
    return {
        "level": player.level,
        "gold": player.gold,
        "units": len(board),
        "three_star_costs": sorted({
            unit.champion.cost for unit in board if unit.star_level == 3
        }),
    }


def fidelity_profile(data, games: int, seed0: int = 0, econ=None,
                     mixed_field: bool = False) -> dict:
    """The engine's side of doc 99 entry 97, in `reference_profile`'s schema.

    `mixed_field` fills the eight seats from `rl.opponents.DEFAULT_FIELD` (3
    standard, 2 fast8, 2 slowroll6, 1 hyperroll) instead of giving every seat
    the same plan. A real ranked lobby is a mixture of archetypes, so eight
    identical economies is the wrong comparator for a real elimination curve
    -- and it is also the field the RL environment actually trains against.
    """
    from rl.opponents import default_opponent  # noqa: PLC0415

    def seats():
        if mixed_field:
            return [default_opponent(seat) for seat in range(8)]
        return [GreedyPolicy(seed=seat, econ=econ) for seat in range(8)]
    from reference_profile import (  # noqa: PLC0415 -- sibling script
        last_round_to_label,
        round_structure,
        sd,
        summarise_rows,
    )

    stage_one, per_stage = round_structure()

    def flat_index(stage: int, round_: int) -> int:
        return (round_ if stage == 1
                else stage_one + per_stage * (stage - 2) + round_)

    elimination_round: Counter[str] = Counter()
    game_length_rounds: list[int] = []
    at_elimination: dict[str, list[dict]] = defaultdict(list)

    placements_all: list[int] = []
    holder_placements: list[int] = []
    placement_by_cost: dict[int, list[int]] = defaultdict(list)
    holders_by_cost: Counter[int] = Counter()
    n_participants = 0

    for game in range(games):
        match = Match(data, seats(), seed=seed0 + game)
        # The state each player last went into a round with. For the eliminated
        # that is the board they died on; for survivors, the board they end on
        # -- which is exactly what Riot reports for each.
        final: dict[int, tuple[str, dict]] = {}
        alive_before = {p.player_id for p in match.living_players}

        while not match.finished:
            label = f"{match.round_id.stage}-{match.round_id.round}"
            for player in match.living_players:
                final[player.player_id] = (label, _snapshot(player))
            match.play_round()

            alive_now = {p.player_id for p in match.living_players}
            for player_id in alive_before - alive_now:
                eliminated_at, snapshot = final[player_id]
                elimination_round[eliminated_at] += 1
                at_elimination[eliminated_at].append(snapshot)
            alive_before = alive_now

        # `Match.finished` going true does not place the survivor -- only
        # `Match.run()` finalises, and this loop cannot use it because the
        # per-round snapshots have to happen between rounds. `rl/env.py:402`
        # does the same thing for the same reason. Without it the winner is
        # absent from `placements` and mean placement reads 5.000, not 4.5.
        match._finalise_placements()

        last = match.round_id
        game_length_rounds.append(flat_index(last.stage, last.round))

        for player in match.players:
            n_participants += 1
            placement = match.placements.get(player.player_id)
            if placement is None:
                continue
            placements_all.append(placement)
            _, snapshot = final.get(player.player_id, ("", {}))
            costs = snapshot.get("three_star_costs", [])
            if costs:
                holder_placements.append(placement)
                for cost in costs:
                    holders_by_cost[cost] += 1
                    placement_by_cost[cost].append(placement)

    return {
        "source": "engine",
        "n_matches": games,
        "n_participants": n_participants,
        "elimination_round": dict(elimination_round),
        "game_length_rounds": game_length_rounds,
        "at_elimination": {
            label: summarise_rows(rows) for label, rows in at_elimination.items()
        },
        "three_star": {
            "n_holders": len(holder_placements),
            "holder_rate": (len(holder_placements) / n_participants
                            if n_participants else 0.0),
            "placement_all": mean(placements_all),
            "placement_all_sd": sd(placements_all),
            "placement_holders": mean(holder_placements),
            "placement_holders_sd": sd(holder_placements),
            "holders_by_cost": {str(c): n
                                for c, n in sorted(holders_by_cost.items())},
            "placement_by_cost": {
                str(cost): mean(values)
                for cost, values in sorted(placement_by_cost.items())
            },
            "unknown_units": 0,
        },
        "_round_label_warnings": [],
        # `last_round_to_label` is imported to keep the two scripts on one
        # definition of the mapping; referencing it here makes that explicit.
        "_label_of_first_round": last_round_to_label(1, stage_one, per_stage),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--fidelity-json", type=Path, default=None,
        help="write the reference-comparable profile (doc 99 entry 97) here "
             "and skip the living-player table",
    )
    parser.add_argument(
        "--econ",
        default=None,
        help="economy strategy for all 8 seats: standard, fast8, slowroll6, "
             "hyperroll, or 'mixed' for rl.opponents.DEFAULT_FIELD. Omit for "
             "the legacy one-purchase-per-round plan",
    )
    args = parser.parse_args()

    from rl.opponents import STRATEGIES

    mixed = args.econ == "mixed"
    econ = STRATEGIES[args.econ] if args.econ and not mixed else None
    data = load_all()

    if args.fidelity_json:
        from reference_profile import report as reference_report

        fidelity = fidelity_profile(data, args.games, econ=econ,
                                    mixed_field=mixed)
        fidelity["provenance"] = {
            "band": f"engine/GreedyPolicy econ={args.econ or 'legacy'}",
            "platform": "-", "queue_id": "-", "set_filter": 17,
        }
        reference_report(fidelity, fidelity["provenance"])
        args.fidelity_json.write_text(json.dumps(fidelity, indent=1))
        print(f"\nwritten to {args.fidelity_json}")
        return

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
