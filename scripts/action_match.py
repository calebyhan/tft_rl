"""Where does the clone actually disagree with its teacher? (doc 99 24.2)

Aggregate action match is a lossy summary. DAgger raised it 81.8% -> 88.7%
without moving placement at all, which is only explicable if the residual
disagreement is concentrated on decisions that matter disproportionately.
Section 15 localised the original mismatch to BUY (52.7%) and PLACE (75.3%) --
the "what is a good board" judgements -- so the question is whether those
improved along with the average, or whether the average improved *around* them.

Reports match per ``ActionKind``, on two state distributions:

* **expert states** -- what behaviour cloning trained on.
* **student states** -- what the policy actually faces at evaluation time,
  reached by letting the model drive while the expert still labels.

    python scripts/action_match.py runs/m14_bc400/model.zip runs/m14_dagger/model.zip
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.action import ActionSpace  # noqa: E402
from scripts.train_ppo import (  # noqa: E402
    ENV_DEFAULTS,
    build_env,
    collect_expert_data,
    student_actor,
)


def match_by_kind(
    model, data, episodes: int, on_student_states: bool,
    expert_kwargs: dict | None = None,
) -> dict:
    """Agreement with the expert, bucketed by the kind of action it chose."""
    actor = student_actor(model) if on_student_states else None
    obs, masks, expert_actions, _ = collect_expert_data(
        data, episodes, actor=actor, seed_offset=90_000,
        expert_kwargs=expert_kwargs,
    )

    env = build_env(data)
    space: ActionSpace = env.action_space_helper

    predicted, _ = model.predict(obs, action_masks=masks, deterministic=True)
    predicted = np.asarray(predicted).reshape(-1)

    hits: dict[str, int] = defaultdict(int)
    totals: dict[str, int] = defaultdict(int)
    for expert_action, guess in zip(expert_actions, predicted, strict=True):
        kind = space.decode(int(expert_action)).kind.name
        totals[kind] += 1
        hits[kind] += int(expert_action == guess)
    return {
        kind: (hits[kind], totals[kind], hits[kind] / totals[kind])
        for kind in sorted(totals, key=lambda k: -totals[k])
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--episodes", type=int, default=40)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--expert-flags",
        action="store_true",
        help="label with buy_synergy + match_items + corner_carry as well",
    )
    parser.add_argument(
        "--copy-counts",
        action="store_true",
        help=(
            "must match what the model was trained with. Like "
            "--champion-encoding, a mismatch is a shape error rather than a "
            "helpful message (doc 99 entry 38.9)"
        ),
    )
    parser.add_argument(
        "--expert-sell",
        action="store_true",
        help=(
            "label with the sell-capable teacher. Must match the teacher the "
            "model was cloned from, or the disagreement measured is with a "
            "policy it never saw (doc 99 entry 37.4)"
        ),
    )
    parser.add_argument(
        "--champion-encoding",
        default="index",
        help=(
            "must match what the model was trained with -- a mismatch is an "
            "opaque torch shape error, not a helpful message"
        ),
    )
    args = parser.parse_args()
    ENV_DEFAULTS["champion_encoding"] = args.champion_encoding
    ENV_DEFAULTS["copy_counts"] = args.copy_counts

    from sb3_contrib import MaskablePPO

    data = load_all(args.data)
    for path in args.models:
        model = MaskablePPO.load(path, device="cpu")
        print(f"\n=== {path} ===")
        for label, on_student in (("expert states", False), ("student states", True)):
            table = match_by_kind(
                model, data, args.episodes, on_student,
                expert_kwargs={
                    "sell_bench": args.expert_sell,
                    "buy_synergy": args.expert_flags,
                    "match_items": args.expert_flags,
                    "corner_carry": args.expert_flags,
                },
            )
            total_hits = sum(h for h, _, _ in table.values())
            total_n = sum(n for _, n, _ in table.values())
            print(f"\n  -- {label} (n={total_n}, overall {total_hits / total_n:.1%})")
            for kind, (hit, n, rate) in table.items():
                bar = "#" * int(rate * 30)
                print(f"     {kind:<14} {rate:>6.1%}  ({hit:>5}/{n:<5}) {bar}")


if __name__ == "__main__":
    main()
