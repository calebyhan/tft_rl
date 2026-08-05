"""Is "which bench unit is weakest" recoverable from the observation?

The clone matches only 26.2% of the teacher's SELL *unit* choices while
choosing to sell at all 93.1% of the time, and 70% of those decisions have a
unique correct answer, so ties cap an ideal-but-tiebreak-blind model at 81.8%
(doc 99 entry 38.3). Something stops it identifying the weakest bench unit.

Two candidate explanations, and placement cannot separate them:

* the observation does not carry the comparison, so no model reading it could
  choose correctly; or
* it does, and the clone's capacity, objective or optimisation is at fault.

This is the project's standard discriminator (doc 99 25-29, `place_probe.py`):
**a probe that cannot fit its own training set is a statement about the feature
set, not the model.** Two probes on identical labels --

* ``observation`` -- the real 381-float vector the clone sees, into a head with
  enough capacity to memorise. Failure to fit *training* data means the
  information is not extractable from what the agent is given.
* ``hand-computed`` -- per-slot ``(star, cost, slot)``, the quantities the
  teacher's rule actually reads. The control: it establishes the label is
  trivial in the right coordinates, so a failure above is about coordinates
  rather than about the label being hard.

SELECT is collected too. It is also a cross-slot comparison and also low
(22.1% on student states), so if both fail together that is one mechanism with
two symptoms rather than a story about selling.

    .venv/bin/python scripts/sell_probe.py --episodes 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from engine.loader import load_all  # noqa: E402
from engine.traits import trait_counts  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import _copies_owned, _unit_strength, scripted_policy  # noqa: E402

SLOT_FEATURES = ("star", "cost", "slot", "on_bench", "copies")


def collect(data, episodes: int, seed_offset: int = 700_000, copy_counts: bool = False):
    """Record every SELL and SELECT decision the sell-capable teacher makes."""
    env = TFTEnv(data=data, seed=1, copy_counts=copy_counts)
    policy = scripted_policy(
        env, sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True
    )
    space = env.action_space_helper
    executor = env.executor
    n_slots = space.unit_slots

    out = {
        kind: {
            "obs": [], "feats": [], "slices": [], "mask": [], "label": [],
            "tied": [],
        }
        for kind in ("SELL", "SELECT", "BUY")
    }

    # Where each action slot's unit block sits in the observation. The board
    # section is written in sorted own-frame hex order and the bench in slot
    # order, which is the same ordering the action space uses -- so slot i's
    # block is the i-th block of the two sections concatenated.
    spec = env.encoder.spec
    board_start = spec.offset_of("board")
    unit_width = spec.unit_width
    shop_start = spec.offset_of("shop")
    shop_width = spec.shop_width
    n_shop = space.shop_slots

    for seed in range(episodes):
        obs, _ = env.reset(seed=seed_offset + seed)
        done = False
        while not done:
            mask = env.action_mask()
            action = policy(obs, mask)
            decoded = space.decode(int(action))
            player = env.player
            kind = decoded.kind.name

            if kind in out:
                offset = (
                    space.sell_offset if kind == "SELL" else space.select_offset
                )
                feats = np.zeros((n_slots, len(SLOT_FEATURES)), dtype=np.float32)
                legal = np.zeros(n_slots, dtype=bool)
                # Every legal slot is a candidate for the *model*: the mask
                # permits selling fielded units too, so "only ever sell from
                # the bench" is part of what has to be learned.
                #
                # The *ceiling* is a different set. It must be the teacher's
                # own candidates -- bench only, skipping combine progress --
                # or it counts ties among units the teacher never considered
                # and reports a ceiling for a rule nobody follows.
                strengths = {}
                for slot in range(n_slots):
                    if not mask[offset + slot]:
                        continue
                    unit = executor.unit_at(player, slot)
                    if unit is None:
                        continue
                    on_bench = space.hex_for_slot(slot) is None
                    feats[slot] = (
                        unit.star_level / 3.0,
                        unit.champion.cost / 5.0,
                        slot / max(n_slots - 1, 1),
                        float(on_bench),
                        # How many copies of this champion the player holds at
                        # this star level. The teacher refuses to sell combine
                        # progress, and without this the rule is not a function
                        # of the features at all -- the first version of this
                        # probe fitted 34.7% of its own training set.
                        #
                        # It is also an *identity match across slots*: counting
                        # copies means comparing champion ids between units in
                        # different slots, which is exactly the operation doc 99
                        # says a flat MLP will not derive.
                        _copies_owned(player, unit) / 3.0,
                    )
                    legal[slot] = True
                    if on_bench and not (
                        kind == "SELL" and _copies_owned(player, unit) >= 2
                    ):
                        strengths[slot] = _unit_strength(unit)

                if legal.sum() >= 2 and decoded.a in strengths:
                    best = (
                        max(strengths.values())
                        if kind == "SELECT"
                        else min(strengths.values())
                    )
                    record = out[kind]
                    # The *same numbers* the monolithic head reads, merely
                    # arranged per slot. If a shared-weight scorer fits these
                    # and the monolithic head does not, the residual gap is
                    # architecture rather than features.
                    # Two positional floats are appended per slot. A
                    # shared-weight scorer sees each slot in isolation and so
                    # structurally cannot tell a board slot from a bench one,
                    # nor break ties by index -- both of which the monolithic
                    # head gets for free from the position of the numbers in
                    # its input. Without them the comparison measures the loss
                    # of position, not the gain from weight sharing: SELECT
                    # scored 41.1% against the monolithic head's 79.1%,
                    # because its rule reads the strongest *bench* unit while
                    # the strongest unit overall is usually fielded.
                    sliced = np.zeros((n_slots, unit_width + 2), dtype=np.float32)
                    for slot in range(n_slots):
                        start = board_start + slot * unit_width
                        sliced[slot, :unit_width] = obs[start : start + unit_width]
                        sliced[slot, unit_width] = float(
                            space.hex_for_slot(slot) is None
                        )
                        sliced[slot, unit_width + 1] = slot / max(n_slots - 1, 1)
                    record["slices"].append(sliced)
                    record["obs"].append(obs.copy())
                    record["feats"].append(feats)
                    record["mask"].append(legal)
                    record["label"].append(decoded.a)
                    record["tied"].append(
                        sum(1 for v in strengths.values() if v == best)
                    )

            if kind == "BUY":
                # The teacher shops on (owned, synergy, cost) -- an argmax over
                # shop slots, the same shape as SELL and SELECT but over a
                # different section. `owned` and `synergy` are already encoded
                # per shop slot (SHOP_DERIVED_FEATURES), so unlike SELL this is
                # not a missing-quantity question from the start.
                counts = trait_counts(player.all_units)
                feats = np.zeros((n_shop, 3), dtype=np.float32)
                legal = np.zeros(n_shop, dtype=bool)
                keys = {}
                for slot in range(n_shop):
                    champion_id = (
                        player.shop.slots[slot]
                        if slot < len(player.shop.slots) else None
                    )
                    if champion_id is None or not mask[slot]:
                        continue
                    champion = player.data.champions[champion_id]
                    owned = any(
                        u.champion.id == champion_id for u in player.all_units
                    )
                    synergy = sum(counts.get(t, 0) for t in champion.traits)
                    feats[slot] = (
                        float(owned), synergy / 10.0, champion.cost / 5.0
                    )
                    legal[slot] = True
                    keys[slot] = (owned, synergy, champion.cost)

                if legal.sum() >= 2 and decoded.a in keys:
                    best = max(keys.values())
                    sliced = np.zeros((n_shop, shop_width + 1), dtype=np.float32)
                    for slot in range(n_shop):
                        start = shop_start + slot * shop_width
                        sliced[slot, :shop_width] = obs[start : start + shop_width]
                        sliced[slot, shop_width] = slot / max(n_shop - 1, 1)
                    record = out["BUY"]
                    record["obs"].append(obs.copy())
                    record["feats"].append(feats)
                    record["slices"].append(sliced)
                    record["mask"].append(legal)
                    record["label"].append(decoded.a)
                    record["tied"].append(
                        sum(1 for v in keys.values() if v == best)
                    )

            obs, _, done, _, _ = env.step(action)

    return out


class SlotScorer(nn.Module):
    """Scores each slot from its own features. Shared weights across slots."""

    def __init__(self, n_features: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


class ObservationHead(nn.Module):
    """Reads the whole observation, emits one logit per slot.

    Deliberately wider and deeper than the policy network. The question is
    whether the information is *there*, so the probe must not fail for want of
    capacity -- if this cannot fit the training set, nothing reading this
    observation can.
    """

    def __init__(self, obs_size: int, n_slots: int, hidden: int = 512):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_size, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, n_slots),
        )

    def forward(self, x):
        return self.net(x)


def fit(model, inputs, masks, labels, split, epochs, lr):
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    for _epoch in range(epochs):
        order = torch.randperm(split)
        for start in range(0, split, 256):
            batch = order[start : start + 256]
            logits = model(inputs[batch]).masked_fill(~masks[batch], -1e9)
            loss = nn.functional.cross_entropy(logits, labels[batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

    def accuracy(lo, hi):
        with torch.no_grad():
            logits = model(inputs[lo:hi]).masked_fill(~masks[lo:hi], -1e9)
            return float((logits.argmax(dim=-1) == labels[lo:hi]).float().mean())

    return accuracy(0, split), accuracy(split, len(labels))


def report(kind: str, record: dict, epochs: int) -> None:
    labels = np.asarray(record["label"], dtype=np.int64)
    if len(labels) < 50:
        print(f"\n{kind}: only {len(labels)} decisions -- too few to probe")
        return

    masks = np.asarray(record["mask"])
    tied = np.asarray(record["tied"], dtype=np.float32)
    ceiling = float(np.mean(1.0 / tied))
    first = float(np.mean(labels == np.argmax(masks, axis=1)))

    print(f"\n=== {kind}: {len(labels)} decisions ===")
    print(f"  always-pick-first-legal-slot : {first:>6.1%}")
    print(f"  rule-but-random-tiebreak ceiling: {ceiling:>6.1%}")

    mt = torch.as_tensor(masks)
    yt = torch.as_tensor(labels)
    split = int(0.8 * len(labels))

    hand = torch.as_tensor(np.asarray(record["feats"], dtype=np.float32))
    train, test = fit(
        SlotScorer(hand.shape[-1]), hand, mt, yt, split, epochs, lr=3e-3
    )
    names = ", ".join(
        ("owned", "synergy", "cost") if kind == "BUY" else SLOT_FEATURES
    )
    print(f"  hand-computed ({names}): train {train:>6.1%}  test {test:>6.1%}")

    obs = torch.as_tensor(np.asarray(record["obs"], dtype=np.float32))
    train, test = fit(
        ObservationHead(obs.shape[-1], masks.shape[-1]),
        obs, mt, yt, split, epochs, lr=1e-3,
    )
    pad = " " * (len(names) - 4)
    print(f"  the real observation{pad}: train {train:>6.1%}  test {test:>6.1%}")

    sliced = torch.as_tensor(np.asarray(record["slices"], dtype=np.float32))
    train, test = fit(
        SlotScorer(sliced.shape[-1]), sliced, mt, yt, split, epochs, lr=3e-3
    )
    pad = " " * (len(names) - 15)
    print(f"  same, per-slot + shared weights{pad}: train {train:>6.1%}  test {test:>6.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=60)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument(
        "--copy-counts",
        action="store_true",
        help="encode copies-held per unit slot -- the identity match the SELL "
             "rule needs (doc 99 entry 38.7)",
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    data = load_all()
    collected = collect(data, args.episodes, copy_counts=args.copy_counts)
    for kind in ("SELL", "SELECT", "BUY"):
        report(kind, collected[kind], args.epochs)

    print("\nThe clone scores 26.2% on SELL unit choice (doc 99 entry 38.2).")
    print("A probe that cannot fit its own training set indicts the features,")
    print("not the model (doc 99 entry 38.5 item 1).")


if __name__ == "__main__":
    main()
