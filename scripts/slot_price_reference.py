"""Does real TFT price a board slot the way this engine does? (doc 99 entry 115)

Entry 114 measured the engine's exchange rate: a board slot is worth ~2.2
survivors and a star-up ~0.78, so **a slot is worth 2.9 star-ups**, and those
two prices predict 90% of `slowroll6`'s combat deficit. 114.4 was explicit that
this does not make 2.9x *wrong* — it is the engine's rate, and whether reality
differs is a separate measurement. 111.2's **+0.379 (t=+4.82)** says only that
something differs.

This measures the same exchange rate on both sides in the same units.

Survivor margin does not exist in Riot's data, so the common currency is
**placement**: fit `placement ~ b0 + b_units * units + b_stars * three_stars`
per arm and read `b_units / b_stars`. Neither coefficient is causal — a seat
that survives longer has more units, more 3-stars *and* a better placement, the
confound entry 111.1 documents — but the confound sits in both arms, so the
comparison of *ratios* is the same difference-of-differences design that
produced 111.2's number.

Both arms are conditioned identically: the board at elimination (for the winner,
the final board), `board_units` only, and units whose cost cannot be resolved
are dropped rather than guessed (entry 97's cost-10 3-stars).

    .venv/bin/python scripts/slot_price_reference.py --engine-games 400
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from scripts.reference_profile import champion_costs, unit_cost  # noqa: E402

THREE_STAR = 3


def fit(rows: list[tuple[int, int, int]]) -> tuple[float, float, float, int]:
    """Least squares of placement on (units, three_stars).

    Returns (b_units, b_stars, ratio, n). Both coefficients should be negative:
    more units and more 3-stars are both good, and placement is better when
    lower.
    """
    if len(rows) < 10:
        return float("nan"), float("nan"), float("nan"), len(rows)
    units = np.array([r[0] for r in rows], dtype=float)
    stars = np.array([r[1] for r in rows], dtype=float)
    place = np.array([r[2] for r in rows], dtype=float)
    design = np.column_stack([np.ones_like(units), units, stars])
    coef, *_ = np.linalg.lstsq(design, place, rcond=None)
    b_units, b_stars = coef[1], coef[2]
    ratio = b_units / b_stars if b_stars else float("nan")
    return b_units, b_stars, ratio, len(rows)


def reference_rows(pattern: str) -> list[tuple[int, int, int]]:
    costs = champion_costs()
    rows = []
    for path in sorted(glob.glob(pattern)):
        payload = json.loads(Path(path).read_text())
        for match in payload["matches"]:
            for participant in match["participants"]:
                units = [u for u in participant.get("units", [])
                         if unit_cost(u, costs) is not None]
                if not units:
                    continue
                rows.append((
                    len(units),
                    sum(1 for u in units if u.get("tier") == THREE_STAR),
                    participant["placement"],
                ))
    return rows


def engine_rows(games: int) -> list[tuple[int, int, int]]:
    from engine.loader import load_all
    from engine.match import Match
    from rl.opponents import DEFAULT_FIELD, GreedyPolicy

    data = load_all()
    rows = []
    for game in range(games):
        match = Match(
            data,
            [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s]) for s in range(8)],
            seed=game,
        )
        final: dict[int, tuple[int, int]] = {}
        while not match.finished:
            for player in match.living_players:
                board = list(player.board_units)
                final[player.player_id] = (
                    len(board),
                    sum(1 for u in board if u.star_level == THREE_STAR),
                )
            match.play_round()
        # `finished` does not place the survivor; only `run()` finalises.
        match._finalise_placements()
        for player in match.players:
            placement = match.placements.get(player.player_id)
            snapshot = final.get(player.player_id)
            if placement is None or snapshot is None or snapshot[0] == 0:
                continue
            rows.append((snapshot[0], snapshot[1], placement))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glob", default="data/reference/matches_*.json")
    parser.add_argument("--engine-games", type=int, default=400)
    args = parser.parse_args()

    print("fitting placement ~ units + three_stars, per arm\n")
    print(f"{'arm':<12}{'b_units':>10}{'b_stars':>10}"
          f"{'slots per star-up':>20}{'n':>9}")

    real = reference_rows(args.glob)
    bu_r, bs_r, ratio_r, n_r = fit(real)
    print(f"{'real':<12}{bu_r:>+10.3f}{bs_r:>+10.3f}{ratio_r:>20.2f}{n_r:>9}")

    engine = engine_rows(args.engine_games)
    bu_e, bs_e, ratio_e, n_e = fit(engine)
    print(f"{'engine':<12}{bu_e:>+10.3f}{bs_e:>+10.3f}{ratio_e:>20.2f}{n_e:>9}")

    print("\n`slots per star-up` is b_units / b_stars: how many board slots buy "
          "the same\nplacement as one 3-star. The engine's combat probe put it "
          "at 2.9 (entry 114.2).")
    print("\nBoth coefficients should be negative (more is better, lower "
          "placement is better).\nA positive one means the fit is dominated by "
          "the survival confound rather than\nby the quantity, and the ratio is "
          "not interpretable.")

    mean_units_r = sum(r[0] for r in real) / len(real)
    mean_stars_r = sum(r[1] for r in real) / len(real)
    mean_units_e = sum(r[0] for r in engine) / len(engine)
    mean_stars_e = sum(r[1] for r in engine) / len(engine)
    print(f"\nmean units  real {mean_units_r:.2f}  engine {mean_units_e:.2f}")
    print(f"mean 3-stars real {mean_stars_r:.2f}  engine {mean_stars_e:.2f}")


if __name__ == "__main__":
    main()
