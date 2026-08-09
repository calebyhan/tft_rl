"""Reduce fetched real-TFT matches to the four fidelity reference distributions.

The reference side of doc 99 entry 96.5's question: is `slowroll6`'s shortfall
**the window** (the seat dies before it can roll enough) or **the payoff** (a
3-star is worth less here than in real TFT, because the combat constants that
price it are `engine_artifact` guesses)?

Four distributions, and what each one discriminates:

===  ===========================================  ==========
 #   distribution                                 tests
===  ===========================================  ==========
 1   elimination round, over participants         window
 2   game length, over matches                    window
 3   level / gold at elimination, keyed by round  window
 4   3-star holder rate, and **placement          payoff
     conditional on holding one**
===  ===========================================  ==========

Row 4 is the one entry 76 could not do: it prices a 3-star against real
outcomes rather than against the engine's own combat.

`scripts/engine_profile.py --fidelity-json` emits the identical schema from the
simulator, and `scripts/fidelity_compare.py` pairs them.

Usage::

    python scripts/reference_profile.py data/reference/matches_challenger_*.json
    python scripts/reference_profile.py <file> --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------------
# Round labelling
#
# Riot reports `last_round` as a flat 1-based index over the whole game. Every
# window conclusion is keyed by it, so an off-by-one here shifts the entire
# finding by a round while still producing a plausible table. The structure
# comes from `data/config.json` rather than being hardcoded, and
# `validate_round_labels` checks the result against real data instead of
# trusting the arithmetic.
# --------------------------------------------------------------------------

def round_structure() -> tuple[int, int]:
    config = json.loads((REPO_ROOT / "data" / "config.json").read_text())
    structure = config["round_structure"]
    return structure["stage_one_rounds"], structure["rounds_per_stage"]


def last_round_to_label(index: int, stage_one: int, per_stage: int) -> str:
    """Flat 1-based round index -> `stage-round` label.

    Stage 1 is short (4 rounds in Set 17); every later stage has `per_stage`.
    Index 1 is 1-1, index `stage_one` is 1-4, index `stage_one + 1` is 2-1.
    """
    if index < 1:
        raise ValueError(f"round index must be >= 1, got {index}")
    if index <= stage_one:
        return f"1-{index}"
    offset = index - stage_one - 1
    return f"{2 + offset // per_stage}-{offset % per_stage + 1}"


def label_sort_key(label: str) -> tuple[int, int]:
    stage, round_ = label.split("-")
    return int(stage), int(round_)


def validate_round_labels(indices: Iterable[int], stage_one: int,
                          per_stage: int) -> list[str]:
    """Sanity checks on the mapping, reported rather than asserted.

    The convention is inferred, not documented, so this states what the data
    implies and leaves the judgement visible instead of encoding an assumption
    behind a passing test.
    """
    values = sorted(indices)
    problems = []
    if not values:
        return ["no round indices at all"]
    lowest, highest = values[0], values[-1]
    # Nobody can be eliminated before 2-1: stage 1 is PvE. A minimum inside
    # stage 1 means the index is offset differently than assumed.
    if lowest <= stage_one:
        problems.append(
            f"minimum last_round {lowest} falls in stage 1 "
            f"({last_round_to_label(lowest, stage_one, per_stage)}), but "
            "stage 1 is PvE and cannot eliminate anyone -- the index origin "
            "is probably not 1"
        )
    top = last_round_to_label(highest, stage_one, per_stage)
    if int(top.split("-")[0]) > 7:
        problems.append(
            f"maximum last_round {highest} maps to {top}, later than real "
            "games reach -- the stage structure may be wrong"
        )
    return problems


# --------------------------------------------------------------------------
# Cost resolution
# --------------------------------------------------------------------------

def champion_costs() -> dict[str, int]:
    """`character_id` -> cost, from our own Set 17 data.

    Riot's per-unit `rarity` is 0-based and irregular at the top of the range
    (5-costs report 6). Resolving against `champions.json` avoids that and,
    more importantly, puts both sides of the comparison on one definition of
    cost rather than two that agree by inspection.
    """
    payload = json.loads((REPO_ROOT / "data" / "champions.json").read_text())
    champions = payload["champions"] if isinstance(payload, dict) else payload
    if isinstance(champions, dict):
        champions = list(champions.values())
    return {c["id"]: c["cost"] for c in champions}


def unit_cost(unit: dict, costs: dict[str, int]) -> int | None:
    """Cost of a unit, or None if it is not a shop champion at all.

    Riot's `units` list carries summons and PvE monsters alongside the board:
    `TFT17_Summon` appeared 312 times in the first 200 matches, plus
    `TFT17_PVE_ElderDragon`, `tft17_bardfollower` and `TFT17_Enemy_Aatrox`.
    Their `rarity` is junk (9, 9, 0, 6), so an earlier `rarity + 1` fallback
    invented cost tiers of 7 and 10 and produced a plausible-looking row of
    "17 holders of a cost-10 3-star". The engine's `board_units` holds shop
    champions only, so anything unresolvable is dropped and counted instead --
    which also means a genuinely missing champion shows up as a number rather
    than as a silently wrong cost.
    """
    return costs.get(unit.get("character_id"))


# --------------------------------------------------------------------------
# Reduction
# --------------------------------------------------------------------------

def mean(values) -> float:
    return statistics.mean(values) if values else 0.0


def sd(values) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def summarise_rows(rows: list[dict]) -> dict:
    """One at-elimination cell, with the spread `fidelity_compare` needs.

    Both `scripts/engine_profile.py` and this module call it, so the two arms
    of the comparison cannot drift apart in how they aggregate -- a difference
    in aggregation would read as a difference in the game.
    """
    cell: dict[str, float] = {"n": len(rows)}
    for key in ("level", "gold", "units"):
        values = [r[key] for r in rows if r.get(key) is not None]
        cell[key] = mean(values)
        cell[f"{key}_sd"] = sd(values)
    return cell


def reduce_matches(matches: list[dict]) -> dict:
    stage_one, per_stage = round_structure()
    costs = champion_costs()

    elimination_round: Counter[str] = Counter()
    game_length_rounds: list[int] = []
    at_elimination: dict[str, list[dict]] = defaultdict(list)
    raw_last_rounds: list[int] = []

    placements_all: list[int] = []
    holder_placements: list[int] = []
    placement_by_cost: dict[int, list[int]] = defaultdict(list)
    holders_by_cost: Counter[int] = Counter()
    non_champion_ids: Counter[str] = Counter()
    n_participants = 0

    for match in matches:
        participants = match.get("participants", [])
        if not participants:
            continue
        rounds = [p["last_round"] for p in participants
                  if p.get("last_round") is not None]
        if rounds:
            game_length_rounds.append(max(rounds))
        raw_last_rounds.extend(rounds)

        for participant in participants:
            n_participants += 1
            placement = participant.get("placement")
            index = participant.get("last_round")
            if placement is not None:
                placements_all.append(placement)

            board = []
            for unit in participant.get("units", []):
                if unit_cost(unit, costs) is None:
                    non_champion_ids[unit.get("character_id")] += 1
                    continue
                board.append(unit)

            if index is not None:
                label = last_round_to_label(index, stage_one, per_stage)
                # The winner is not "eliminated"; counting them would put a
                # spike at the last round of every game in a distribution that
                # is meant to describe how long losing seats survive.
                if placement != 1:
                    elimination_round[label] += 1
                    at_elimination[label].append({
                        "level": participant.get("level"),
                        "gold": participant.get("gold_left"),
                        "units": len(board),
                        "placement": placement,
                    })

            three_star_costs = {
                unit_cost(unit, costs) for unit in board if unit.get("tier") == 3
            }
            if three_star_costs and placement is not None:
                holder_placements.append(placement)
                for cost in three_star_costs:
                    holders_by_cost[cost] += 1
                    placement_by_cost[cost].append(placement)

    return {
        "source": "riot",
        "n_matches": len(matches),
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
            "holders_by_cost": {str(c): n for c, n in sorted(holders_by_cost.items())},
            "placement_by_cost": {
                str(cost): mean(values)
                for cost, values in sorted(placement_by_cost.items())
            },
            "unknown_units": sum(non_champion_ids.values()),
            "non_champion_ids": dict(non_champion_ids.most_common(10)),
        },
        "_round_label_warnings": validate_round_labels(
            raw_last_rounds, stage_one, per_stage
        ),
    }


def report(profile: dict, provenance: dict | None = None) -> None:
    if provenance:
        print(f"band {provenance.get('band')} / {provenance.get('platform')} "
              f"/ queue {provenance.get('queue_id')} "
              f"/ set {provenance.get('set_filter')}")
    print(f"{profile['n_matches']} matches, "
          f"{profile['n_participants']} participants\n")

    for warning in profile["_round_label_warnings"]:
        print(f"  !! round labelling: {warning}")
    if profile["_round_label_warnings"]:
        print()

    print("eliminations by round (excluding the winner):")
    total = sum(profile["elimination_round"].values()) or 1
    at_elim = profile["at_elimination"]
    print(f"{'round':>7}{'n':>7}{'share':>8}{'cum':>8}{'level':>7}{'gold':>7}"
          f"{'units':>7}")
    cumulative = 0
    for label in sorted(profile["elimination_round"], key=label_sort_key):
        count = profile["elimination_round"][label]
        cumulative += count
        row = at_elim.get(label, {})
        print(f"{label:>7}{count:>7}{count / total:>8.1%}"
              f"{cumulative / total:>8.1%}"
              f"{row.get('level', 0):>7.2f}{row.get('gold', 0):>7.1f}"
              f"{row.get('units', 0):>7.2f}")

    lengths = profile["game_length_rounds"]
    stage_one, per_stage = round_structure()
    if lengths:
        print(f"\ngame length: {mean(lengths):.1f} rounds "
              f"(min {min(lengths)} = "
              f"{last_round_to_label(min(lengths), stage_one, per_stage)}, "
              f"max {max(lengths)} = "
              f"{last_round_to_label(max(lengths), stage_one, per_stage)})")

    three = profile["three_star"]
    print(f"\n3-star holders: {three['n_holders']} "
          f"({three['holder_rate']:.1%} of participants)")
    print(f"  placement, all participants: {three['placement_all']:.3f}")
    print(f"  placement, 3-star holders:   {three['placement_holders']:.3f}")
    print(f"{'cost':>7}{'holders':>9}{'placement':>11}")
    for cost, placement in three["placement_by_cost"].items():
        print(f"{cost:>7}{three['holders_by_cost'].get(cost, 0):>9}"
              f"{placement:>11.3f}")
    if three.get("unknown_units"):
        print(f"  dropped {three['unknown_units']} non-champion unit rows "
              f"(summons, PvE): {three.get('non_champion_ids', {})}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matches", type=Path,
                        help="a file written by scripts/fetch_riot_matches.py")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = json.loads(args.matches.read_text())
    profile = reduce_matches(payload["matches"])
    profile["provenance"] = payload.get("provenance", {})
    report(profile, profile["provenance"])

    if args.json:
        args.json.write_text(json.dumps(profile, indent=1))
        print(f"\nwritten to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
