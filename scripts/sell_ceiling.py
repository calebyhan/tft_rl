"""Why does the clone only match 24% of the teacher's SELL actions?

Three readings, and the aggregate rate cannot tell them apart (doc 99 lesson 6:
a rate is uninterpretable without its achievable maximum).

1. The clone does not know it should sell -- it picks some other kind entirely.
2. It knows to sell but picks the wrong unit.
3. It picks a *tied* unit: the teacher sells the weakest bench unit by
   ``(star, cost)`` and breaks ties by bench index, so when several units tie
   the teacher's specific choice is arbitrary and unlearnable except as
   "lowest index wins".

Reading 3 sets the achievable ceiling for a model that learned the rule
perfectly but not the positional tiebreak.

    .venv/bin/python scripts/sell_ceiling.py runs/reclone-sellteacher/model.zip
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from scripts.train_ppo import build_env, collect_expert_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--episodes", type=int, default=25)
    args = parser.parse_args()

    from sb3_contrib import MaskablePPO

    data = load_all()
    obs, masks, expert_actions, _ = collect_expert_data(
        data, args.episodes, seed_offset=90_000, expert_kwargs={"sell_bench": True}
    )
    space = build_env(data).action_space_helper
    model = MaskablePPO.load(args.model, device="cpu")
    predicted, _ = model.predict(obs, action_masks=masks, deterministic=True)
    predicted = np.asarray(predicted).reshape(-1)

    exact = same_kind = total = 0
    for expert_action, guess in zip(expert_actions, predicted, strict=True):
        if space.decode(int(expert_action)).kind is not ActionKind.SELL:
            continue
        total += 1
        exact += int(expert_action == guess)
        same_kind += int(space.decode(int(guess)).kind is ActionKind.SELL)

    print(f"\nexpert SELL decisions: {total}")
    print(f"  clone chose SELL at all : {same_kind / total:>6.1%}")
    print(f"  clone chose the same unit: {exact / total:>6.1%}")
    if same_kind:
        print(f"  ...of the times it sold : {exact / same_kind:>6.1%} were the right unit")


if __name__ == "__main__":
    main()
