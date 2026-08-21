"""What real challenger boards say you should be building (doc 99 entry 148).

Everything else in `bridge/` decides by simulating fights in an engine whose
fidelity to real TFT is limited (111-128). This module never touches the
engine. It reads `data/reference/` -- 8,000 real challenger seats -- and answers
the question that data can actually answer: **boards like yours placed how, and
what did the good ones hold?**

Two views, deliberately separate because they fail in different ways:

* `champion_weights` -- a per-champion association with placement, controlling
  for level and gold (entry 147.1, +0.198 R² over those alone). Linear, so it
  cannot see synergy: it scores champions, not boards.
* `similar_boards` -- real seats sharing units with yours, and what the ones
  that top-foured were holding. Captures synergy because it never decomposes
  the board, but needs enough matching seats to mean anything, so it always
  reports `n`.

**Association, not causation.** Strong players pick strong compositions *and*
play well, so a champion's weight conflates the unit with the skill of the
people who field it. This is a tier list -- which is what real players use --
and it must be described that way.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "reference"

# What a player knows while deciding. `last_round` and `players_eliminated` are
# excluded deliberately: they encode the placement almost exactly, and using
# them as controls made composition look worthless (entry 147.1).
KNOWABLE = ("level", "gold_left")


@dataclass
class Suggestion:
    champion_id: str
    weight: float
    support: int

    def __str__(self) -> str:
        return f"{self.champion_id} ({self.weight:+.2f}, n={self.support})"


def load_seats(band: str = "challenger") -> list[dict]:
    found = sorted(REFERENCE.glob(f"matches_{band}_*.json"))
    if not found:
        raise FileNotFoundError(
            f"no {band} sample in {REFERENCE}; run scripts/fetch_riot_matches.py")
    payload = json.loads(found[-1].read_text())
    return [p for m in payload["matches"] for p in m["participants"]]


def champion_weights(seats: list[dict], min_count: int = 100
                     ) -> dict[str, tuple[float, int]]:
    """Per-champion placement association, holding level and gold fixed.

    Negative is better -- placement is 1..8 and 1 wins. Champions below
    `min_count` appearances are dropped: their weights are noise, and a tier
    list built on twelve observations is worse than no tier list.
    """
    counts: Counter = Counter()
    for seat in seats:
        for unit in seat.get("units", []):
            counts[unit["character_id"]] += 1
    index = {c: i for i, c in enumerate(sorted(c for c, n in counts.items()
                                               if n >= min_count))}
    if not index:
        return {}

    rows = np.zeros((len(seats), len(KNOWABLE) + len(index)))
    y = np.zeros(len(seats))
    for i, seat in enumerate(seats):
        for k, key in enumerate(KNOWABLE):
            rows[i, k] = float(seat[key])
        for unit in seat.get("units", []):
            j = index.get(unit["character_id"])
            if j is not None:
                # Star level, not presence: a 1-star and a 3-star of the same
                # champion are different units and a flat indicator erases that.
                col = len(KNOWABLE) + j
                rows[i, col] = max(rows[i, col], float(unit.get("tier", 1)))
        y[i] = float(seat["placement"])

    design = np.hstack([rows, np.ones((len(rows), 1))])
    ridge = design.T @ design + np.eye(design.shape[1])
    weights = np.linalg.solve(ridge, design.T @ y)
    return {c: (float(weights[len(KNOWABLE) + i]), counts[c])
            for c, i in index.items()}


def similar_boards(seats: list[dict], champions: set[str],
                   min_overlap: int = 3) -> tuple[list[dict], int]:
    """Real seats sharing at least `min_overlap` champions with yours."""
    matched = []
    for seat in seats:
        held = {u["character_id"] for u in seat.get("units", [])}
        if len(held & champions) >= min_overlap:
            matched.append(seat)
    return matched, len(matched)


def what_winners_added(seats: list[dict], champions: set[str],
                       min_overlap: int = 3, top: int = 8):
    """Champions the *top-four* boards like yours held and you do not.

    Returns `(rows, matched, winners)`. `matched` and `winners` are reported by
    every caller: a recommendation drawn from nine seats is noise, and the
    reader cannot tell without the counts.
    """
    matched, n = similar_boards(seats, champions, min_overlap)
    winners = [s for s in matched if s["placement"] <= 4]
    if not winners:
        return [], n, 0
    extra: Counter = Counter()
    for seat in winners:
        for unit in seat.get("units", []):
            if unit["character_id"] not in champions:
                extra[unit["character_id"]] += 1
    rows = [(champion, count, count / len(winners))
            for champion, count in extra.most_common(top)]
    return rows, n, len(winners)
