"""Can the surrogate *choose*, not just predict? (doc 99 entry 146)

145.4 named this the gate on everything downstream. R² 0.53 on absolute fight
value says nothing about whether the model **ranks near-identical candidate
boards** the way real simulation does, and ranking is the only thing a search
consumes. A model can score respectably on fight value and still be useless
inside a search, because the candidates a search compares differ by one unit
while the fight values it was trained on differ by whole boards.

Method: at real mid-game states, build the candidate boards `best_board` would
consider, score each by **real simulation at high budget** (the ground truth)
and by the surrogate, then ask what a chooser using the surrogate actually
loses.

The decision-relevant metric is **regret**: the true value of the pick the
surrogate makes, against the true value of the best available candidate. Rank
correlation is reported too, but regret is what a search pays.

Baselines, because a regret number alone is uninterpretable:

* **oracle** -- picks the true best. Regret 0 by construction.
* **random** -- picks uniformly. The ceiling on how bad it can get.
* **greedy (star, cost)** -- the teacher's own lexicographic rule, which is
  what the surrogate has to beat to be worth anything.

    .venv/bin/python scripts/surrogate_decisions.py --states 60 --model X.pt
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.search import clone_board, fight_value, opponent_panel  # noqa: E402
from scripts.combat_surrogate import features  # noqa: E402
from scripts.search_budget import sweep  # noqa: E402

TRUTH_PANEL = 4
TRUTH_TRIALS = 8


def load_model(path):
    import torch

    blob = torch.load(path, weights_only=False)
    model = torch.nn.Sequential(
        torch.nn.Linear(len(blob["mu"]), 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 1))
    model.load_state_dict(blob["state"])
    model.eval()
    return model, np.asarray(blob["mu"]), np.asarray(blob["sd"])


def candidates(player):
    """The swaps `best_board` would consider: each benched unit onto the board."""
    bench = [u for u in player.bench if u is not None]
    bench.sort(key=lambda u: (-u.star_level, -u.champion.cost))
    free = [h for h in sorted(player._own_hexes) if h not in player.board]
    weakest = min(player.board,
                  key=lambda h: (player.board[h].star_level,
                                 player.board[h].champion.cost))
    out = [((), (), None)]                       # leave the board alone
    for unit in bench[:6]:
        if len(player.board) < player.max_board_units and free:
            out.append((((unit, free[0]),), (), unit))
        else:
            out.append((((unit, weakest),), (weakest,), unit))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=int, default=60)
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import torch

    data = load_all()
    model, mu, sd = load_model(args.model)
    rows = {name: [] for name in ("oracle", "surrogate", "greedy", "random")}
    spearman, top1 = [], []

    def visit(index, shim):
        player, match = shim.player, shim.match
        panel = opponent_panel(match, player, TRUTH_PANEL)
        if not panel or not any(u is not None for u in player.bench):
            return
        rng = random.Random(index)
        seeds = [[rng.randrange(2**31) for _ in range(TRUTH_TRIALS)]
                 for _ in panel]
        options = candidates(player)
        if len(options) < 3:
            return

        truth, guess = [], []
        for extra, drops, _unit in options:
            total = 0.0
            for other, trial_seeds in zip(panel, seeds, strict=True):
                for seed in trial_seeds:
                    total += fight_value(
                        data, player.hex_board,
                        clone_board(match, player, 0, extra=extra, drops=drops),
                        clone_board(match, other, 1), seed)
            truth.append(total / (len(panel) * TRUTH_TRIALS))

            # The surrogate sees the same hypothetical board, scored against
            # the same panel, so the only difference is how it is judged.
            preds = []
            for other in panel:
                x = features(
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1), data)
                preds.append(float(model(torch.tensor(
                    (x - mu) / sd, dtype=torch.float32)).item()))
            guess.append(statistics.mean(preds))

        best = max(truth)
        rows["oracle"].append(0.0)
        rows["surrogate"].append(best - truth[int(np.argmax(guess))])
        rows["random"].append(best - truth[rng.randrange(len(truth))])
        # The teacher's rule: field the strongest bench unit, else leave it.
        rows["greedy"].append(best - truth[1 if len(truth) > 1 else 0])

        order_t = np.argsort(np.argsort(truth))
        order_g = np.argsort(np.argsort(guess))
        n = len(truth)
        d2 = float(((order_t - order_g) ** 2).sum())
        spearman.append(1 - 6 * d2 / (n * (n * n - 1)) if n > 1 else 0.0)
        top1.append(float(int(np.argmax(guess)) == int(np.argmax(truth))))
        if len(top1) % 10 == 0:
            print(f"  {len(top1)} states", flush=True)

    sweep(data, args.games, args.states, args.seed, visit)
    n = len(rows["oracle"])
    print(f"\n{n} states; truth = {TRUTH_PANEL} opponents x {TRUTH_TRIALS} "
          f"fights per candidate\n")
    print(f"{'chooser':>14}{'mean regret':>13}{'vs random':>11}")
    rand = statistics.mean(rows["random"])
    for name in ("oracle", "surrogate", "greedy", "random"):
        mean = statistics.mean(rows[name])
        share = f"{1 - mean / rand:>10.0%}" if rand else f"{'--':>10}"
        print(f"{name:>14}{mean:>13.3f}{share:>11}")
    print(f"\ntop-1 agreement with truth: {statistics.mean(top1):.1%}"
          f"   mean Spearman: {statistics.mean(spearman):+.2f}")
    print("'vs random' is the share of random's regret eliminated; "
          "the oracle eliminates 100%.")


if __name__ == "__main__":
    main()
