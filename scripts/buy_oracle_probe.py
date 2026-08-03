"""Is the expert's BUY rule recoverable at all, given its own quantities?

Doc 99 28.3 left the architecture probe unable to discriminate: the fat heads
memorised, the lean ones could not fit. Before designing a fair probe -- or
redesigning the observation, or the expert -- one question has to be settled:

    Given exactly the quantities `_buy_phase` reads, is the choice predictable?

Per candidate slot this supplies the sort key itself -- ``owned``, ``synergy``,
``cost`` -- plus the economy gate ``cost <= _spendable`` that 28.1 showed drives
a third of the decisions, plus the slot index that breaks ties. A tiny model on
five hand-computed features per slot.

* If it reaches ~100%, the label function is simple *in the right coordinates*
  and the difficulty is purely representational: the observation does not
  expose these quantities and the network cannot derive them. That justifies
  either a feature change or an architecture that can compute them.
* If it does not, the rule depends on state not captured here -- most likely
  the within-phase purchase sequence, since `_buy_phase` has no ``break`` and
  buys repeatedly as gold drains -- and the expert is simply a poor imitation
  target, which argues for fixing the expert rather than the agent.

    python scripts/buy_oracle_probe.py --episodes 200
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
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402

FEATURES = ("owned", "synergy", "cost", "affordable", "slot")


def spendable(player, keep_interest: bool = True) -> int:
    """Mirror of ``GreedyPolicy._spendable`` (rl/opponents.py)."""
    if not keep_interest:
        return player.gold
    per = player.config.interest_per_gold
    cap = player.config.interest_cap * per
    floor = min(player.gold - (player.gold % per), cap)
    return max(player.gold - floor, 0)


def collect(data, episodes: int, seed_offset: int = 300_000):
    env = TFTEnv(data=data, seed=1)
    policy = scripted_policy(env)
    space = env.action_space_helper
    slots = data.config.shop_slots

    rows, masks, labels = [], [], []
    for seed in range(episodes):
        obs, _ = env.reset(seed=seed_offset + seed)
        done = False
        while not done:
            mask = env.action_mask()
            action = policy(obs, mask)
            decoded = space.decode(int(action))
            if decoded.kind is ActionKind.BUY:
                player = env.player
                counts = trait_counts(player.all_units)
                held = {u.champion.id for u in player.all_units}
                budget = max(spendable(player), 0)
                per_slot = np.zeros((slots, len(FEATURES)), dtype=np.float32)
                legal = np.zeros(slots, dtype=bool)
                for slot in range(slots):
                    champion_id = player.shop.peek(slot)
                    if champion_id is None or not player.can_buy(slot):
                        continue
                    champion = data.champions[champion_id]
                    per_slot[slot] = (
                        float(champion_id in held),
                        float(sum(counts.get(t, 0) for t in champion.traits)),
                        float(champion.cost),
                        float(champion.cost <= budget),
                        float(slot),
                    )
                    legal[slot] = True
                if legal.sum() >= 2:
                    rows.append(per_slot)
                    masks.append(legal)
                    labels.append(decoded.a)
            obs, _, done, _, _ = env.step(action)
    return (
        np.asarray(rows),
        np.asarray(masks),
        np.asarray(labels, dtype=np.int64),
    )


class SlotScorer(nn.Module):
    """A shared MLP scoring each slot from its five features. ~2k parameters."""

    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def evaluate(model, x, mask, y):
    with torch.no_grad():
        logits = model(x).masked_fill(~mask, -1e9)
        return float((logits.argmax(dim=-1) == y).float().mean())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument("--drop", nargs="*", default=[], help="feature names to ablate")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    data = load_all()
    x, mask, y = collect(data, args.episodes)
    kept = [i for i, f in enumerate(FEATURES) if f not in args.drop]
    names = [FEATURES[i] for i in kept]
    x = x[:, :, kept]
    print(f"\nBUY decisions with >=2 candidates: {len(y)}")
    print(f"features per slot: {', '.join(names)}")

    first = float(np.mean(y == np.argmax(mask, axis=1)))
    print(f"always-pick-first-candidate: {first:.1%}")

    split = int(0.8 * len(y))
    xt = torch.as_tensor(x)
    mt = torch.as_tensor(mask)
    yt = torch.as_tensor(y)
    train = (xt[:split], mt[:split], yt[:split])
    test = (xt[split:], mt[split:], yt[split:])

    model = SlotScorer(len(kept))
    optimiser = torch.optim.Adam(model.parameters(), lr=3e-3)
    n = split
    for _epoch in range(args.epochs):
        order = torch.randperm(n)
        for start in range(0, n, 256):
            batch = order[start : start + 256]
            logits = model(train[0][batch]).masked_fill(~train[1][batch], -1e9)
            loss = nn.functional.cross_entropy(logits, train[2][batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

    print(f"\nslot scorer on oracle features ({sum(p.numel() for p in model.parameters())} params)")
    print(f"  train {evaluate(model, *train):.1%}   test {evaluate(model, *test):.1%}")
    print("\nvalidated argmax-rule ceiling: 67.7% (doc 99 28.1)")


if __name__ == "__main__":
    main()
