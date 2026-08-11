"""Is the swap teacher's SELECT decision expressible in the observation?
(doc 99 entry 108)

Entry 108.3 localised the whole search-imitation failure to one decision kind.
Cloning `best_swap` leaves PLACE at 76.0% (against 79.6% with no search at all,
because its target hex is deterministic) while SELECT sits at **54.7%** against
86.3%. The decision is *is this benched unit worth fielding?*, and `best_swap`
answers it by simulating the fight against a panel of opponents.

54.7% is a rate without a stated maximum, which is the error 79.3 made with
47.4% and lesson 6 exists to prevent. Two very different worlds produce it:

1. **the observation cannot express the comparison** -- the labels are a
   function of something the vector does not carry, and no amount of fitting
   reaches them; or
2. **behaviour cloning is leaving fit on the table** -- the labels *are*
   expressible and 50 epochs of BC against ten other action kinds simply does
   not extract them.

They have opposite remedies: (1) is a feature-engineering problem, (2) is a
training problem, and widening the observation would be wasted work under (2).

This separates them without inventing a single feature. It trains a probe on
**nothing but the same observation the clone sees**, on **only** the SELECT
decisions, and compares it against the clone's 54.7%.

**Read the held-out number, not the training fit.** CLAUDE.md's rule -- a probe
that cannot fit its own training set is a statement about the feature set --
needs the training set to be unfittable by memorisation before it says
anything, and it is not here: the observation is 381 continuous floats, so
every row is unique (`duplicate_label_ceiling` reports 100.0% with zero
collisions) and the probe reaches 100% train fit on 6836 rows regardless. The
clone's 54.7% is itself measured on fresh episodes, so held-out is also the
comparable quantity.

`--teacher plain` is the control, and it is not optional. The plain rule is
``max(benched, key=(star_level, cost))`` over quantities the observation
already carries per slot, and the no-search clone fits it at **86.3%**. If the
probe scores similarly on both teachers the number is about the probe; only a
large split isolates the swap rule as the inexpressible one.

    .venv/bin/python scripts/select_probe.py --episodes 150
    .venv/bin/python scripts/select_probe.py --episodes 150 --teacher plain
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from engine.loader import load_all  # noqa: E402
from engine.traits import active_traits  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.search import opponent_panel, search_policy  # noqa: E402

# The teacher entry 108 cloned: `--expert-sell --expert-flags --expert-econ
# standard` wrapped in `best_swap` at c4/p2. Read from here rather than
# hand-passed, because a probe measuring a teacher nobody trained on is the
# defect 79.5 records shipping three times.
TEACHER = dict(sell_bench=True, buy_synergy=True, match_items=True,
               corner_carry=True)
SEARCH = dict(mode="swap", max_candidates=4, panel_size=2)


def candidate_features(env, n_slots: int) -> np.ndarray:
    """Hand-computed relational features, appended per unit slot (doc 99 109.4).

    Every relational feature the observation already carries is
    **self-referential**: `owned` and `synergy` compare a shop slot to the
    player's own roster, `star_rank` / `cost_rank` / `copies` compare the
    player's units to each other. Nothing compares the player's board to an
    *opponent's*. `best_swap` decides by simulating a fight against a panel, so
    its label depends on exactly the comparison that is missing.

    Two families, both of which the TFT client shows a player directly:

    * **trait delta, per unit slot** -- how many trait breakpoints the board
      would gain (or lose) if this unit were fielded. Hovering a unit in the
      real client displays this. It is a dot product between the champion's
      traits and the board's counts followed by a *threshold* against the
      breakpoint table -- an identity match plus a threshold across slots,
      which is the operation entry 29 and 38.6 both measured a flat MLP failing
      to derive.
    * **board versus panel, global** -- unit count, total value, best star and
      active-trait-tier count, each as *our value minus theirs*, against the
      same panel `best_swap` uses. Scouting is legal in TFT and these are the
      numbers a player reads off an opponent's board.

    Deliberately **not** included: the simulated fight margin itself. That is
    `best_swap`'s computation, and supplying it would hand over the teacher's
    policy rather than a fact about the board (CLAUDE.md). The whole question is
    whether the *inputs* to that judgement suffice.
    """
    player, match = env.player, env.match
    board = list(player.board_units)
    base_tiers = len(active_traits(board, player.data))

    per_slot = np.zeros((n_slots, 1), dtype=np.float32)
    space = env.action_space_helper
    for slot in range(n_slots):
        hex_ = space.hex_for_slot(slot)
        index = space.bench_index_for_slot(slot)
        if hex_ is not None:
            unit = player.board.get(hex_)
            if unit is None:
                continue
            # For a fielded unit the comparable quantity is what is lost by
            # removing it, so the two halves are on one scale.
            others = [u for u in board if u is not unit]
            per_slot[slot, 0] = base_tiers - len(
                active_traits(others, player.data))
        elif index is not None:
            unit = player.bench[index]
            if unit is None:
                continue
            per_slot[slot, 0] = len(
                active_traits([*board, unit], player.data)) - base_tiers

    panel = opponent_panel(match, player, 2) if match is not None else []
    if panel:
        def summarise(units):
            return np.array([
                len(units),
                sum(u.champion.cost * (3 ** (u.star_level - 1)) for u in units),
                max((u.star_level for u in units), default=0),
                len(active_traits(list(units), player.data)),
            ], dtype=np.float32)

        ours = summarise(board)
        theirs = np.mean([summarise(list(p.board_units)) for p in panel], axis=0)
        # Normalised so no single term dominates the input scale: counts by 9
        # (the level cap), value by 30, stars by 3, tiers by 8.
        delta = (ours - theirs) / np.array([9.0, 30.0, 3.0, 8.0], np.float32)
    else:
        delta = np.zeros(4, dtype=np.float32)

    return np.concatenate([per_slot.ravel(), delta])


def collect(data, episodes: int, teacher: str = "swap", features: bool = False,
            seed_offset: int = 0):
    """SELECT decisions from the swap teacher: (observation, chosen slot, mask).

    Only states where the mask offers **more than one** legal SELECT are kept.
    A forced choice is fitted by any model and would dilute the rate this exists
    to measure -- the same reason 101 measured against an achievable maximum
    rather than 100%.
    """
    from rl.opponents import STRATEGIES

    env = TFTEnv(data=data)
    base = scripted_policy(env, econ=STRATEGIES["standard"], **TEACHER)
    # The control shares *everything* but the search wrapper -- same flags,
    # same econ, same seeds -- so a split between the two arms cannot be the
    # teacher configuration.
    policy = base if teacher == "plain" else search_policy(
        env, rng_seed=0, mode="swap", base=base,
        **{k: v for k, v in SEARCH.items() if k != "mode"})
    space = env.action_space_helper
    rows, labels, masks = [], [], []
    for episode in range(episodes):
        obs, _info = env.reset(seed=seed_offset + episode)
        done = False
        while not done:
            mask = env.action_masks()
            action = int(policy(obs, mask))
            if space.decode(action).kind is ActionKind.SELECT:
                legal = np.flatnonzero(
                    mask[space.select_offset:space.select_offset + space.unit_slots]
                )
                if len(legal) > 1:
                    row = np.asarray(obs, dtype=np.float32)
                    if features:
                        row = np.concatenate(
                            [row, candidate_features(env, space.unit_slots)])
                    rows.append(row)
                    labels.append(action - space.select_offset)
                    m = np.zeros(space.unit_slots, dtype=bool)
                    m[legal] = True
                    masks.append(m)
            obs, _r, term, trunc, _i = env.step(action)
            done = term or trunc
    return (np.stack(rows), np.asarray(labels), np.stack(masks),
            space.unit_slots)


def duplicate_label_ceiling(x: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    """The rate an oracle reaches by memorising the observation.

    Identical observation vectors carrying different labels are unfittable by
    anything reading only the observation. Grouping on exact bytes is a *lower
    bound* on the collision rate -- near-identical states are not caught -- so a
    ceiling below 100% here is decisive, while 100% proves nothing on its own.
    """
    groups: dict[bytes, Counter] = {}
    for row, label in zip(x, y, strict=True):
        groups.setdefault(row.tobytes(), Counter())[int(label)] += 1
    hits = sum(c.most_common(1)[0][1] for c in groups.values())
    collisions = sum(1 for c in groups.values() if len(c) > 1)
    return hits / len(y), collisions


def fit(x, y, masks, n_slots, hidden, epochs, lr, holdout):
    torch.manual_seed(0)
    n_hold = int(len(y) * holdout)
    xt = torch.from_numpy(x)
    yt = torch.from_numpy(y).long()
    mt = torch.from_numpy(masks)
    tr = slice(n_hold, None)
    ho = slice(0, n_hold)

    model = nn.Sequential(
        nn.Linear(x.shape[1], hidden), nn.ReLU(),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, n_slots),
    )
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()

    def accuracy(sl):
        with torch.no_grad():
            logits = model(xt[sl]).masked_fill(~mt[sl], -1e9)
            return (logits.argmax(1) == yt[sl]).float().mean().item()

    for epoch in range(epochs):
        opt.zero_grad()
        # The mask is applied in training too: the clone chooses among legal
        # slots, so a probe scored on the unmasked argmax would be answering a
        # harder question than the one being compared against.
        logits = model(xt[tr]).masked_fill(~mt[tr], -1e9)
        loss = loss_fn(logits, yt[tr])
        loss.backward()
        opt.step()
        if (epoch + 1) % max(epochs // 10, 1) == 0:
            print(f"  epoch {epoch + 1:>5}/{epochs}: loss={loss.item():.4f} "
                  f"train={accuracy(tr):.1%} holdout={accuracy(ho):.1%}")
    return accuracy(tr), accuracy(ho)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=150)
    parser.add_argument("--teacher", choices=("swap", "plain"), default="swap")
    parser.add_argument("--features", action="store_true",
                        help="append the candidate relational features (109.4)")
    parser.add_argument("--hidden", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=3000)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--holdout", type=float, default=0.2)
    args = parser.parse_args()

    data = load_all()
    print(f"collecting SELECT decisions from {args.episodes} episodes "
          f"of the {args.teacher} teacher")
    x, y, masks, n_slots = collect(data, args.episodes, teacher=args.teacher,
                                   features=args.features)
    legal_mean = masks.sum(1).mean()
    print(f"  {len(y)} contested SELECT decisions, obs width {x.shape[1]}, "
          f"{n_slots} slots, {legal_mean:.1f} legal on average")

    ceiling, collisions = duplicate_label_ceiling(x, y)
    print(f"  exact-duplicate ceiling: {ceiling:.1%} "
          f"({collisions} observations carry more than one label)")

    majority = Counter(int(v) for v in y).most_common(1)[0][1] / len(y)
    print(f"  majority-slot baseline:  {majority:.1%}")

    print(f"\nprobe: {args.hidden} hidden, {args.epochs} epochs, full-batch")
    train_acc, hold_acc = fit(x, y, masks, n_slots, args.hidden, args.epochs,
                              args.lr, args.holdout)

    clone = 54.7 if args.teacher == "swap" else 86.3
    print(f"\n  probe train fit : {train_acc:.1%}  (memorisation; not "
          "informative -- see the module docstring)")
    print(f"  probe HELD OUT  : {hold_acc:.1%}")
    print(f"  clone SELECT    : {clone:.1f}%   (doc 99 entry 108.3, "
          f"{args.teacher} arm, expert states)")
    print(
        "\nRun both teachers. Similar held-out scores mean the number is about "
        "the probe; a large split isolates the swap rule as the one the "
        "observation cannot express."
    )


if __name__ == "__main__":
    main()
