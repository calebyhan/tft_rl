"""What wins in *real* TFT? Learned from real seats, not from the engine.

Everything measured in this log until now is placement against seven scripted
`GreedyPolicy` bots inside an engine whose fidelity to real TFT was measured
and found wanting -- 3-cost reroll is 10.1% of real challenger seats and 0.003
of engine seats (124, 125). Advice validated there is advice about the engine.

`data/reference/` holds **16,000 real seats** (8,000 challenger, 8,000 diamond)
with final units, star levels, level, gold left and placement. This asks what
they say, with no simulator in the loop.

**The confound, named first.** A final board is an *outcome*, not a decision:
seats that place well survive longer and therefore have more rounds to build a
bigger board. "3-stars place well" is partly reverse causality. So the model is
scored against a baseline of **survival proxies alone** (level, last_round,
players_eliminated, gold_left). The question is not "does composition predict
placement" -- it trivially does -- but **"does composition predict placement
beyond how long you survived?"** Only the increment is decision-relevant.

    .venv/bin/python scripts/real_placement.py --band challenger
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

REFERENCE = REPO_ROOT / "data" / "reference"

# **`last_round` and `players_eliminated` are the label in disguise**: a seat
# eliminated 8th played the fewest rounds, so they encode placement almost
# exactly. A first version used them as the control and reported R^2 0.846 with
# composition adding -0.001 -- a meaningless comparison, because nothing can add
# to a baseline that already *is* the answer. The control has to be what a
# player knows while deciding.
SURVIVAL = ["level", "gold_left"]
TAUTOLOGICAL = ["last_round", "players_eliminated"]


def seats(band: str) -> list[dict]:
    found = sorted(REFERENCE.glob(f"matches_{band}_*.json"))
    if not found:
        raise SystemExit(f"no {band} sample in {REFERENCE}")
    payload = json.loads(found[-1].read_text())
    return [p for m in payload["matches"] for p in m["participants"]]


def champion_index(rows: list[dict], min_count: int) -> dict[str, int]:
    """Champions common enough to estimate. Rare ones are noise, not signal."""
    counts: Counter = Counter()
    for seat in rows:
        for unit in seat.get("units", []):
            counts[unit["character_id"]] += 1
    common = sorted(c for c, n in counts.items() if n >= min_count)
    return {c: i for i, c in enumerate(common)}


def featurise(rows: list[dict], index: dict[str, int]):
    """Survival block, then a per-champion star-weighted block."""
    surv = np.array([[float(s[k]) for k in SURVIVAL] for s in rows])
    taut = np.array([[float(s[k]) for k in TAUTOLOGICAL] for s in rows])
    comp = np.zeros((len(rows), len(index)))
    for i, seat in enumerate(rows):
        for unit in seat.get("units", []):
            j = index.get(unit["character_id"])
            if j is not None:
                # Star level matters more than presence; 1/2/3 stars are very
                # different units, and a flat indicator would erase that.
                comp[i, j] = max(comp[i, j], float(unit.get("tier", 1)))
    y = np.array([float(s["placement"]) for s in rows])
    return surv, comp, y, taut


def ridge(X, y, lam=1.0):
    Xb = np.hstack([X, np.ones((len(X), 1))])
    A = Xb.T @ Xb + lam * np.eye(Xb.shape[1])
    return np.linalg.solve(A, Xb.T @ y)


def score(w, X, y) -> float:
    Xb = np.hstack([X, np.ones((len(X), 1))])
    pred = Xb @ w
    return 1 - float(((pred - y) ** 2).mean()) / float(((y - y.mean()) ** 2).mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", default="challenger",
                        choices=["challenger", "diamond"])
    parser.add_argument("--min-count", type=int, default=100)
    args = parser.parse_args()

    rows = seats(args.band)
    index = champion_index(rows, args.min_count)
    surv, comp, y, taut = featurise(rows, index)
    print(f"{len(rows)} real {args.band} seats, "
          f"{len(index)} champions above {args.min_count} appearances")
    print(f"placement mean {y.mean():.2f} (4.50 by construction), "
          f"sd {y.std():.2f}")

    cut = int(0.8 * len(rows))
    blocks = {
        "last_round + elims (near-tautological)": taut,
        "knowable only (level, gold)": surv,
        "composition only (star-weighted)": comp,
        "knowable + composition": np.hstack([surv, comp]),
    }
    print(f"\n{'features':>44}{'test R^2':>10}")
    scores = {}
    for name, X in blocks.items():
        w = ridge(X[:cut], y[:cut])
        scores[name] = score(w, X[cut:], y[cut:])
        print(f"{name:>44}{scores[name]:>10.3f}")

    gain = (scores["knowable + composition"]
            - scores["knowable only (level, gold)"])
    print(f"\ncomposition's increment over survival alone: {gain:+.3f} R^2")
    print("that increment is the decision-relevant part. The tautological row "
          "is printed to show what a\nbaseline containing the label looks "
          "like -- it is not a legitimate control.")

    # Which champions carry it, once survival is held fixed.
    X = np.hstack([surv, comp])
    w = ridge(X[:cut], y[:cut])
    weights = w[len(SURVIVAL):len(SURVIVAL) + len(index)]
    names = {i: c for c, i in index.items()}
    order = np.argsort(weights)
    print(f"\n{'best (lower placement)':>34}{'weight':>9}    "
          f"{'worst':>26}{'weight':>9}")
    for k in range(8):
        good, bad = order[k], order[-(k + 1)]
        print(f"{names[good]:>34}{weights[good]:>9.3f}    "
              f"{names[bad]:>26}{weights[bad]:>9.3f}")


if __name__ == "__main__":
    main()
