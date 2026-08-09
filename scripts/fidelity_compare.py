"""Pair the engine's profile against a real-TFT reference sample.

Doc 99 entry 97. The two profiles come from `scripts/engine_profile.py
--fidelity-json` and `scripts/reference_profile.py --json`, which share their
schema and their aggregation helpers so the arms cannot drift apart.

**The outcomes were named before the first run**, so a story cannot be fitted
to whatever appeared:

1. engine eliminations markedly earlier, or games shorter -> **window**: the
   seat dies before it can roll.
2. elimination timing and game length match, but 3-star incidence is far
   below real -> **window** by another route: pacing is right, accumulation
   is not.
3. 3-star incidence matches but holders gain less placement here than in real
   TFT -> **payoff**: the `engine_artifact` combat constants under-price a
   3-star, which entry 76 structurally could not detect.
4. all four match -> the mispricing is not on these axes, and `slowroll6`
   sitting 0.653 behind `standard` may simply be correct.

Usage::

    python scripts/fidelity_compare.py engine.json reference.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reference_profile import label_sort_key  # noqa: E402


def welch_t(mean_a: float, sd_a: float, n_a: int,
            mean_b: float, sd_b: float, n_b: int) -> float:
    """Welch's t for two independent means. 0.0 when it is undefined."""
    if n_a < 2 or n_b < 2:
        return 0.0
    variance = sd_a ** 2 / n_a + sd_b ** 2 / n_b
    if variance <= 0:
        return 0.0
    return (mean_a - mean_b) / math.sqrt(variance)


def proportion_z(hits_a: int, n_a: int, hits_b: int, n_b: int) -> float:
    """Two-proportion z, pooled."""
    if not n_a or not n_b:
        return 0.0
    pooled = (hits_a + hits_b) / (n_a + n_b)
    variance = pooled * (1 - pooled) * (1 / n_a + 1 / n_b)
    if variance <= 0:
        return 0.0
    return (hits_a / n_a - hits_b / n_b) / math.sqrt(variance)


def distribution_stats(counts: dict[str, int]) -> tuple[float, float, int]:
    """Mean, sd and n of a round-labelled elimination histogram.

    The label is ordinal, so the flat round index is the thing to average --
    `label_sort_key` gives the ordering and the index is recovered from the
    cumulative position, but the simplest faithful summary is the mean over
    the expanded sample, which is exact from counts.
    """
    from reference_profile import round_structure

    stage_one, per_stage = round_structure()

    def flat(label: str) -> int:
        stage, round_ = label_sort_key(label)
        return (round_ if stage == 1
                else stage_one + per_stage * (stage - 2) + round_)

    total = sum(counts.values())
    if not total:
        return 0.0, 0.0, 0
    mean = sum(flat(label) * n for label, n in counts.items()) / total
    variance = sum(n * (flat(label) - mean) ** 2
                   for label, n in counts.items()) / max(total - 1, 1)
    return mean, math.sqrt(variance), total


def cumulative(counts: dict[str, int], labels: list[str]) -> dict[str, float]:
    """Cumulative share, evaluated over a shared label axis.

    `labels` must be the union of both sides' rounds. Building it from one
    side's own keys and then reading it with `.get(label, 0.0)` makes a label
    that side never saw read as 0% cumulative rather than carrying the running
    total forward -- which reported a KS statistic of 1.000 and a -98.3% gap on
    a round where the two distributions actually agree.
    """
    total = sum(counts.values()) or 1
    running = 0
    out = {}
    for label in labels:
        running += counts.get(label, 0)
        out[label] = running / total
    return out


def compare(engine: dict, reference: dict) -> None:
    print(f"engine    : {engine['n_matches']} games, "
          f"{engine['n_participants']} seats  "
          f"({engine.get('provenance', {}).get('band', '?')})")
    print(f"reference : {reference['n_matches']} matches, "
          f"{reference['n_participants']} seats  "
          f"({reference.get('provenance', {}).get('band', '?')})\n")

    # -- 1. elimination timing --------------------------------------------
    eng_mean, eng_sd, eng_n = distribution_stats(engine["elimination_round"])
    ref_mean, ref_sd, ref_n = distribution_stats(reference["elimination_round"])
    t = welch_t(eng_mean, eng_sd, eng_n, ref_mean, ref_sd, ref_n)
    print("1. ELIMINATION ROUND (window)")
    print(f"   engine {eng_mean:.2f} +/- {eng_sd:.2f} (n={eng_n})   "
          f"reference {ref_mean:.2f} +/- {ref_sd:.2f} (n={ref_n})   "
          f"delta {eng_mean - ref_mean:+.2f}, t={t:+.2f}")

    labels = sorted(set(engine["elimination_round"])
                    | set(reference["elimination_round"]), key=label_sort_key)
    eng_cum = cumulative(engine["elimination_round"], labels)
    ref_cum = cumulative(reference["elimination_round"], labels)
    ks = max((abs(eng_cum[x] - ref_cum[x]) for x in labels), default=0.0)
    print(f"   max cumulative gap (KS) {ks:.3f}\n")
    print(f"   {'round':>7}{'eng n':>8}{'eng cum':>9}{'ref cum':>9}{'gap':>8}")
    for label in labels:
        print(f"   {label:>7}{engine['elimination_round'].get(label, 0):>8}"
              f"{eng_cum[label]:>9.1%}{ref_cum[label]:>9.1%}"
              f"{eng_cum[label] - ref_cum[label]:>+8.1%}")

    # -- 2. game length ----------------------------------------------------
    from reference_profile import mean as avg
    from reference_profile import sd as spread

    eng_len, ref_len = engine["game_length_rounds"], reference["game_length_rounds"]
    t = welch_t(avg(eng_len), spread(eng_len), len(eng_len),
                avg(ref_len), spread(ref_len), len(ref_len))
    print(f"\n2. GAME LENGTH (window)\n"
          f"   engine {avg(eng_len):.2f} +/- {spread(eng_len):.2f}   "
          f"reference {avg(ref_len):.2f} +/- {spread(ref_len):.2f}   "
          f"delta {avg(eng_len) - avg(ref_len):+.2f}, t={t:+.2f}")

    # -- 3. state at elimination ------------------------------------------
    print("\n3. STATE AT ELIMINATION (window)")
    print(f"   {'round':>7}{'eng lvl':>9}{'ref lvl':>9}{'t':>7}"
          f"{'eng gold':>10}{'ref gold':>10}{'t':>7}"
          f"{'eng brd':>9}{'ref brd':>9}")
    for label in labels:
        e = engine["at_elimination"].get(label)
        r = reference["at_elimination"].get(label)
        if not e or not r or e["n"] < 5 or r["n"] < 5:
            continue
        t_level = welch_t(e["level"], e["level_sd"], e["n"],
                          r["level"], r["level_sd"], r["n"])
        t_gold = welch_t(e["gold"], e["gold_sd"], e["n"],
                         r["gold"], r["gold_sd"], r["n"])
        print(f"   {label:>7}{e['level']:>9.2f}{r['level']:>9.2f}{t_level:>+7.1f}"
              f"{e['gold']:>10.1f}{r['gold']:>10.1f}{t_gold:>+7.1f}"
              f"{e['units']:>9.2f}{r['units']:>9.2f}")

    # -- 4. the 3-star payoff ---------------------------------------------
    eng3, ref3 = engine["three_star"], reference["three_star"]
    z = proportion_z(eng3["n_holders"], engine["n_participants"],
                     ref3["n_holders"], reference["n_participants"])
    print("\n4. THREE-STAR (payoff)")
    print(f"   holder rate: engine {eng3['holder_rate']:.1%} "
          f"({eng3['n_holders']}) vs reference {ref3['holder_rate']:.1%} "
          f"({ref3['n_holders']}), z={z:+.2f}")

    # The comparable quantity is the *edge* a 3-star confers, not the raw
    # placement: both sides average 4.5 over all seats by construction, so
    # only the gap between holders and the field carries information.
    eng_edge = eng3["placement_holders"] - eng3["placement_all"]
    ref_edge = ref3["placement_holders"] - ref3["placement_all"]
    t = welch_t(eng3["placement_holders"], eng3.get("placement_holders_sd", 0.0),
                eng3["n_holders"],
                ref3["placement_holders"], ref3.get("placement_holders_sd", 0.0),
                ref3["n_holders"])
    print(f"   placement of holders: engine {eng3['placement_holders']:.3f} "
          f"vs reference {ref3['placement_holders']:.3f}, t={t:+.2f}")
    print(f"   edge over the field:  engine {eng_edge:+.3f} "
          f"vs reference {ref_edge:+.3f}   "
          f"(negative is better; the engine {'over' if eng_edge < ref_edge else 'under'}-prices it)")
    print(f"\n   {'cost':>7}{'eng n':>8}{'eng plc':>9}{'ref n':>8}{'ref plc':>9}")
    costs = sorted(set(eng3["placement_by_cost"]) | set(ref3["placement_by_cost"]),
                   key=int)
    for cost in costs:
        print(f"   {cost:>7}"
              f"{eng3['holders_by_cost'].get(cost, 0):>8}"
              f"{eng3['placement_by_cost'].get(cost, float('nan')):>9.3f}"
              f"{ref3['holders_by_cost'].get(cost, 0):>8}"
              f"{ref3['placement_by_cost'].get(cost, float('nan')):>9.3f}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    compare(json.loads(args.engine.read_text()),
            json.loads(args.reference.read_text()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
