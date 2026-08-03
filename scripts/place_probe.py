"""Are SELECT and PLACE predictable from the quantities their rule reads?

The BUY investigation (doc 99 25-29) converged on a procedure worth reusing:
read the expert's rule, hand-compute exactly what it reads, and check whether a
tiny model predicts the choice. Establishing that the label is trivial *in the
right coordinates* turned an open architecture question into ten floats.

SELECT and PLACE are now the largest defects (21.9% and 52.1% on the student
distribution, doc 99 29.2). Their rules:

* ``SELECT`` -- ``max(benched, key=(star_level, cost))``. An argmax over a set,
  like BUY. Unlike BUY, both quantities are *already* encoded per unit slot,
  so if this probe fits easily the observation is not the problem.
* ``PLACE`` -- ``_preferred_hex``: melee (``attack_range <= 1``) to the front
  rows, ranged to the back, among free hexes. Needs the held unit's range,
  which the selection block already carries, and the target hex's row, which is
  positional.

Caveat carried from 29.2: SELECT/PLACE rates were measured on a *shifted*
distribution (sample count 258 -> 1180 once the agent started buying properly),
so this first establishes whether a defect exists before anything is fixed.

    python scripts/place_probe.py --episodes 150
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from engine.hexgrid import axial_to_offset  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402

SELECT_FEATURES = ("star", "cost", "on_bench", "slot")
PLACE_FEATURES = (
    "is_hex", "row", "occupied", "melee", "melee_x_row",
    # The swap regime: when the board is full the expert does not field into an
    # empty hex at all, it evicts the weakest fielded unit. Without the
    # occupant's strength and a flag for which regime applies, half the labels
    # are unexplainable -- the first pass fit 42.5% on its own training set.
    "occupant_star", "occupant_cost", "board_full", "held_beats_occupant",
)


def collect(data, episodes: int, seed_offset: int = 400_000):
    env = TFTEnv(data=data, seed=1)
    policy = scripted_policy(env)
    space = env.action_space_helper
    executor = env.executor
    n_slots = space.unit_slots

    sel_x, sel_m, sel_y = [], [], []
    place_x, place_m, place_y = [], [], []

    for seed in range(episodes):
        obs, _ = env.reset(seed=seed_offset + seed)
        done = False
        while not done:
            mask = env.action_mask()
            action = policy(obs, mask)
            decoded = space.decode(int(action))
            player = env.player

            if decoded.kind is ActionKind.SELECT:
                feats = np.zeros((n_slots, len(SELECT_FEATURES)), dtype=np.float32)
                legal = np.zeros(n_slots, dtype=bool)
                for slot in range(n_slots):
                    if not mask[space.select_offset + slot]:
                        continue
                    unit = executor.unit_at(player, slot)
                    if unit is None:
                        continue
                    # Normalised: a raw slot index (0-36) is an order of
                    # magnitude larger than star/cost and dominates the fit.
                    feats[slot] = (
                        unit.star_level / 3.0,
                        unit.champion.cost / 5.0,
                        float(space.hex_for_slot(slot) is None),
                        slot / max(n_slots - 1, 1),
                    )
                    legal[slot] = True
                if legal.sum() >= 2:
                    sel_x.append(feats)
                    sel_m.append(legal)
                    sel_y.append(decoded.a)

            elif decoded.kind is ActionKind.PLACE:
                held = (
                    executor.unit_at(player, executor.selected)
                    if executor.selected is not None
                    else None
                )
                melee = (
                    float(held.derived_stats().attack_range <= 1)
                    if held is not None
                    else 0.0
                )
                half = player.hex_board.half_rows
                rows = player.hex_board.rows
                board_full = float(len(player.board) >= player.max_board_units)
                held_key = (
                    (held.star_level, held.champion.cost) if held is not None else (0, 0)
                )
                feats = np.zeros((n_slots, len(PLACE_FEATURES)), dtype=np.float32)
                legal = np.zeros(n_slots, dtype=bool)
                for slot in range(n_slots):
                    if not mask[space.place_offset + slot]:
                        continue
                    hex_ = space.hex_for_slot(slot)
                    occupant = executor.unit_at(player, slot)
                    occupant_key = (
                        (occupant.star_level, occupant.champion.cost)
                        if occupant is not None
                        else (0, 0)
                    )
                    if hex_ is None:
                        feats[slot] = (
                            0.0, 0.0, 0.0, melee, 0.0,
                            occupant_key[0] / 3.0, occupant_key[1] / 5.0,
                            board_full, 0.0,
                        )
                    else:
                        # The expert sorts empty hexes by (row - half_rows) and
                        # takes the last for ranged, the first for melee -- so
                        # the *ordering* matters, not a front/back boolean.
                        depth = (row_offset := axial_to_offset(hex_)[0]) - half
                        normalised = depth / max(rows - 1, 1)
                        del row_offset
                        feats[slot] = (
                            1.0,
                            normalised,
                            float(occupant is not None),
                            melee,
                            melee * normalised,
                            occupant_key[0] / 3.0,
                            occupant_key[1] / 5.0,
                            board_full,
                            float(held_key > occupant_key),
                        )
                    legal[slot] = True
                if legal.sum() >= 2:
                    place_x.append(feats)
                    place_m.append(legal)
                    place_y.append(decoded.a)

            obs, _, done, _, _ = env.step(action)

    pack = lambda x, m, y: (  # noqa: E731
        np.asarray(x), np.asarray(m), np.asarray(y, dtype=np.int64)
    )
    return pack(sel_x, sel_m, sel_y), pack(place_x, place_m, place_y)


class SlotScorer(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def fit_and_report(name, features, dataset, epochs: int):
    x, m, y = dataset
    if len(y) < 50:
        print(f"\n{name}: only {len(y)} decisions -- too few to probe")
        return
    print(f"\n{name}: {len(y)} decisions, features: {', '.join(features)}")
    first = float(np.mean(y == np.argmax(m, axis=1)))
    print(f"  always-pick-first-candidate: {first:.1%}")

    split = int(0.8 * len(y))
    xt, mt, yt = torch.as_tensor(x), torch.as_tensor(m), torch.as_tensor(y)
    model = SlotScorer(x.shape[-1])
    optimiser = torch.optim.Adam(model.parameters(), lr=3e-3)
    for _epoch in range(epochs):
        order = torch.randperm(split)
        for start in range(0, split, 256):
            batch = order[start : start + 256]
            logits = model(xt[batch]).masked_fill(~mt[batch], -1e9)
            loss = nn.functional.cross_entropy(logits, yt[batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

    def accuracy(lo, hi):
        with torch.no_grad():
            logits = model(xt[lo:hi]).masked_fill(~mt[lo:hi], -1e9)
            return float((logits.argmax(dim=-1) == yt[lo:hi]).float().mean())

    print(f"  slot scorer: train {accuracy(0, split):.1%}   test {accuracy(split, len(y)):.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=150)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--seed", type=int, default=21)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    data = load_all()
    select, place = collect(data, args.episodes)
    fit_and_report("SELECT", SELECT_FEATURES, select, args.epochs)
    fit_and_report("PLACE", PLACE_FEATURES, place, args.epochs)
    print("\nagent on the student distribution: SELECT 21.9%, PLACE 52.1% (doc 99 29.2)")


if __name__ == "__main__":
    main()
