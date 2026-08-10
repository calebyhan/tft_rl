"""Do reroll lines actually place well in real TFT? (doc 99 entry 100)

Ten entries rest on a premise nobody measured. `slowroll6` places **+0.553
(t=+3.54) worse** than `standard` in this engine (100), and that has been
treated throughout as a *defect* because reroll lines are mainstream, viable
play in real TFT. The viability half came from general knowledge of the game,
not from data — and `data/reference/` has held 2,000 ranked Set 17 matches
since entry 97 that can settle it.

Lesson 24: an external reference has its own spread and must be measured before
any gap against it is quoted. This is the same rule one step earlier — measure
whether the reference exhibits the phenomenon at all.

**The survival confound cannot be removed, so it is made to cancel instead.** A
seat that lives longer rolls more shops, so it holds more 3-stars *and* places
better; splitting on "has a 3-star" recovers that as much as the archetype. The
obvious repair — stratify on `last_round` — is *worse*, not better: elimination
order essentially determines placement in TFT (measured here: round 27 → 6.88,
round 37 → 1.68), so conditioning on it conditions on the outcome and collapses
every within-stratum delta toward zero by construction. That table is printed
with a warning, and is not evidence of anything.

What does work is the design the reference programme was built for: run the
**engine** through the identical classifier and the identical statistic. A bias
present in both arms cancels in the comparison between them, which is why
`summarise_rows` is shared between `reference_profile` and `engine_profile`. So
the number to read is the *difference of differences*: reroll-minus-other in
real TFT, against reroll-minus-other in the engine.

    .venv/bin/python scripts/reroll_reference.py
    .venv/bin/python scripts/reroll_reference.py --engine-games 200
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.reference_profile import champion_costs, unit_cost  # noqa: E402

# `slowroll6` targets three cost-2 units (rl/opponents.py). A real seat running
# that line is identified by its *payoff*, a 3-star at that cost, because the
# line is not otherwise visible in end-of-game state: Riot reports no roll
# counts and no level history.
REROLL_COST = 2
THREE_STAR = 3


def load_participants(paths: list[str]) -> list[dict]:
    rows = []
    for path in paths:
        payload = json.loads(Path(path).read_text())
        for match in payload["matches"]:
            rows.extend(match["participants"])
    return rows


def classify(participant: dict, costs: dict[str, int]) -> str:
    """`reroll` if the seat holds a 3-star at the reroll cost, else `other`.

    Units whose cost cannot be resolved are skipped rather than guessed. Entry
    97 invented cost tiers of 7 and 10 from summons by falling back to
    `rarity + 1`, and produced a plausible table of "cost-10 3-stars".
    """
    for unit in participant.get("units", []):
        if unit.get("tier") != THREE_STAR:
            continue
        cost = unit_cost(unit, costs)
        if cost == REROLL_COST:
            return "reroll"
    return "other"


def engine_arms(games: int, seed0: int = 0) -> tuple[list[int], list[int]]:
    """The engine's seats, classified by the same rule as the reference.

    Uses `DEFAULT_FIELD` (3 standard, 2 fast8, 2 slowroll6, 1 hyperroll) rather
    than eight identical economies: a real lobby is a mixture, and it is also
    the field the RL environment trains against. Seats are classified by their
    *board at elimination*, exactly as Riot reports and exactly as
    `engine_profile._snapshot` reads it -- `board_units`, so a 3-star on the
    bench counts in neither arm.
    """
    from engine.loader import load_all
    from engine.match import Match
    from rl.opponents import default_opponent

    data = load_all()
    reroll: list[int] = []
    other: list[int] = []
    for game in range(games):
        match = Match(data, [default_opponent(seat) for seat in range(8)],
                      seed=seed0 + game)
        final: dict[int, bool] = {}
        while not match.finished:
            for player in match.living_players:
                final[player.player_id] = any(
                    unit.star_level == THREE_STAR
                    and unit.champion.cost == REROLL_COST
                    for unit in player.board_units
                )
            match.play_round()
        # See engine_profile: `finished` does not place the survivor.
        match._finalise_placements()
        for player in match.players:
            placement = match.placements.get(player.player_id)
            if placement is None:
                continue
            (reroll if final.get(player.player_id) else other).append(placement)
    return other, reroll


def welch(a: list[int], b: list[int]) -> tuple[float, float]:
    """Difference of means and Welch t. The two arms are unpaired here."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0, 0.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    return mb - ma, ((mb - ma) / se if se > 0 else 0.0)


def summarise(placements: list[int]) -> str:
    n = len(placements)
    if not n:
        return "        --"
    top4 = sum(1 for p in placements if p <= 4) / n
    first = sum(1 for p in placements if p == 1) / n
    return (f"{sum(placements) / n:6.3f}  {first:5.1%}  {top4:5.1%}  "
            f"n={n:>5}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glob", default="data/reference/matches_*.json")
    parser.add_argument("--min-stratum", type=int, default=200,
                        help="skip last_round strata thinner than this")
    parser.add_argument("--engine-games", type=int, default=0,
                        help="also run N engine games through the same "
                             "classifier; this is the comparison that matters")
    args = parser.parse_args()

    paths = sorted(glob.glob(args.glob))
    if not paths:
        sys.exit(f"no reference files match {args.glob}")
    print("reference files: " + ", ".join(Path(p).name for p in paths))

    costs = champion_costs()
    rows = load_participants(paths)
    print(f"{len(rows)} participants\n")

    arms: dict[str, list[int]] = defaultdict(list)
    by_round: dict[int, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list))
    for row in rows:
        arm = classify(row, costs)
        arms[arm].append(row["placement"])
        by_round[row.get("last_round", -1)][arm].append(row["placement"])

    share = len(arms["reroll"]) / max(len(rows), 1)
    print(f"seats holding a cost-{REROLL_COST} 3-star: {share:.1%}\n")

    print(f"{'arm':<10}{'place':>7}{'1st':>8}{'top4':>7}{'n':>9}")
    for arm in ("other", "reroll"):
        print(f"{arm:<10}{summarise(arms[arm])}")
    # Named distinctly from the stratified loop's locals below: an earlier
    # version reused `t`, and the loop silently overwrote the pooled value so
    # the difference-of-differences block printed +3.04 for a statistic that
    # was -9.58 six lines earlier.
    pooled_delta, pooled_t = welch(arms["other"], arms["reroll"])
    print(f"\npooled reroll - other: {pooled_delta:+.3f}  "
          f"(Welch t={pooled_t:+.2f})")
    print("  ^ CONFOUNDED by survival: a seat that lives longer rolls more "
          "shops, so it\n    both 3-stars more often and places better. The "
          "stratified table is the one\n    to read.")

    print(f"\nconditioned on last_round (strata with >= {args.min_stratum} "
          "seats in each arm):")
    print(f"{'round':>6}{'other':>9}{'reroll':>9}{'delta':>9}{'t':>8}"
          f"{'n_other':>9}{'n_reroll':>10}")
    weighted, weight = 0.0, 0
    for last_round in sorted(by_round):
        other = by_round[last_round]["other"]
        reroll = by_round[last_round]["reroll"]
        if min(len(other), len(reroll)) < args.min_stratum:
            continue
        d, t = welch(other, reroll)
        n = len(other) + len(reroll)
        weighted += d * n
        weight += n
        print(f"{last_round:>6}{sum(other) / len(other):>9.3f}"
              f"{sum(reroll) / len(reroll):>9.3f}{d:>+9.3f}{t:>+8.2f}"
              f"{len(other):>9}{len(reroll):>10}")
    if weight:
        print(f"\nsurvival-controlled mean delta: {weighted / weight:+.3f} "
              f"placement, over {weight} seats")
        print("  negative = the reroll seat places BETTER at equal elimination "
              "round")

    counts = Counter(len(v["reroll"]) for v in by_round.values())
    if not counts:
        print("\n!! no strata at all -- check last_round is populated")

    if not args.engine_games:
        print("\nRun with --engine-games to get the comparison that matters; "
              "the numbers\nabove are one arm of a difference of differences.")
        return

    print(f"\n=== engine, {args.engine_games} games, same classifier ===")
    eng_other, eng_reroll = engine_arms(args.engine_games)
    print(f"{'arm':<10}{'place':>7}{'1st':>8}{'top4':>7}{'n':>9}")
    print(f"{'other':<10}{summarise(eng_other)}")
    print(f"{'reroll':<10}{summarise(eng_reroll)}")
    eng_delta, eng_t = welch(eng_other, eng_reroll)
    eng_share = len(eng_reroll) / max(len(eng_other) + len(eng_reroll), 1)
    print(f"\nseats holding a cost-{REROLL_COST} 3-star: {eng_share:.1%} "
          f"(real: {share:.1%})")
    print(f"engine reroll - other: {eng_delta:+.3f}  (Welch t={eng_t:+.2f})")

    print("\n--- difference of differences ---")
    print(f"  real   reroll - other: {pooled_delta:+.3f}  (t={pooled_t:+.2f})")
    print(f"  engine reroll - other: {eng_delta:+.3f}  (t={eng_t:+.2f})")
    print(f"  engine - real        : {eng_delta - pooled_delta:+.3f}")
    print("\nThe survival confound sits in both arms and cancels here. A large "
          "positive\nengine-minus-real is the reroll mispricing, stated as a "
          "number for the first\ntime. Near zero means the engine prices the "
          "line as reality does and the\npremise behind entries 96-103 was "
          "wrong.")


if __name__ == "__main__":
    main()
