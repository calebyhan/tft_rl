r"""Does pushing one action drag REROLL up with it? (doc 99 entry 62)

Entry 61 measured REROLL's advantage as **negative** in both the warm start
(-0.0107, n=139) and the collapsed policy (-0.0042, n=1071), yet PPO converges
onto it. The drift is not the optimiser following the signal.

The remaining hypothesis is structural. The slot head has per-kind heads
(`sell_head`, `place_head`, `buy_head`, ...) but a single **`global_net`
producing END_PLANNING, BUY_XP and REROLL together**. Both of REROLL's siblings
carry *positive* advantage. If pushing `global_net` toward them also lifts
REROLL, the collapse is a shared-parameter side effect rather than anything
about reward.

**This tests the mechanism directly rather than its downstream consequence.**
The alternative -- retraining with `--no-slot-head` and comparing collapses --
costs an hour and confounds the head change with a separately-produced warm
start. Here one gradient step is applied and the *same* network is measured
before and after.

Arms, all from the identical starting weights:

* ``end``    -- ascend log-prob of END_PLANNING (shares `global_net` with REROLL)
* ``buy_xp`` -- ascend log-prob of BUY_XP       (shares `global_net` with REROLL)
* ``buy``    -- ascend log-prob of BUY          (separate `buy_head`) -- CONTROL
* ``place``  -- ascend log-prob of PLACE        (separate `place_head`) -- CONTROL

If the coupling is real, REROLL's log-prob rises under `end`/`buy_xp` and moves
much less under `buy`/`place`. If it rises everywhere, this is generic drift and
the slot head is exonerated.

    .venv/bin/python scripts/coupling_probe.py runs/ws1200
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ARMS = ("end", "buy_xp", "buy", "place")
SHARES_GLOBAL_NET = {"end": True, "buy_xp": True, "buy": False, "place": False}


def collect_states(model, env, space, n_states: int):
    """Roll out under the policy, keeping observations and their masks."""
    observations, masks = [], []
    obs, _ = env.reset(seed=0)
    while len(observations) < n_states:
        mask = env.action_masks()
        observations.append(np.array(obs, dtype=np.float32))
        masks.append(np.array(mask, dtype=bool))
        action, _ = model.predict(obs, action_masks=mask, deterministic=False)
        obs, _, terminated, truncated, _ = env.step(int(action))
        if terminated or truncated:
            obs, _ = env.reset(seed=len(observations))
    return np.array(observations), np.array(masks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--states", type=int, default=3000)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from scripts.train_ppo import ENV_DEFAULTS, build_env

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(2)

    saved = json.loads((args.run / "metadata.json").read_text())["hyperparameters"]
    # From the sidecar, never module defaults (doc 99 entries 45.2, 61.3).
    ENV_DEFAULTS.update({
        "copy_counts": saved["copy_counts"],
        "champion_encoding": saved["champion_encoding"],
        "scouting": saved["scouting"],
    })
    data = load_all()
    env = build_env(data)
    space = env.action_space_helper

    model = MaskablePPO.load(args.run / "model", device="cpu")
    print(f"loaded {args.run.name}; collecting {args.states} states")
    observations, masks = collect_states(model, env, space, args.states)

    kind_index: dict[str, list[int]] = {}
    for index in range(space.n):
        kind_index.setdefault(space.decode(index).kind.name, []).append(index)
    reroll = kind_index["REROLL"]
    targets = {
        "end": kind_index["END_PLANNING"],
        "buy_xp": kind_index["BUY_XP"],
        "buy": kind_index["BUY"],
        "place": kind_index["PLACE"],
    }

    obs_t = torch.as_tensor(observations)
    mask_t = torch.as_tensor(masks)

    def reroll_logprob(policy) -> float:
        """Mean log-prob of REROLL over states where it is legal."""
        with torch.no_grad():
            distribution = policy.get_distribution(obs_t, action_masks=mask_t)
            logits = distribution.distribution.logits
        legal = mask_t[:, reroll].any(dim=1)
        if not bool(legal.any()):
            raise SystemExit("REROLL is never legal in these states")
        return float(logits[legal][:, reroll].mean())

    baseline_state = {k: v.detach().clone()
                      for k, v in model.policy.state_dict().items()}
    baseline = reroll_logprob(model.policy)
    legal_fraction = float(mask_t[:, reroll].any(dim=1).float().mean())
    print(f"baseline REROLL log-prob {baseline:+.4f} "
          f"(legal in {legal_fraction:.1%} of states)\n")

    print(f"{'arm':<10}{'shares global_net':>19}{'REROLL logp':>14}"
          f"{'delta':>11}")
    results = {}
    for arm in ARMS:
        model.policy.load_state_dict(baseline_state)
        indices = torch.as_tensor(targets[arm])
        # Only states where the target is legal; ascending a masked action's
        # log-prob is meaningless.
        rows = mask_t[:, indices].any(dim=1)
        optimiser = torch.optim.Adam(model.policy.parameters(), lr=args.lr)
        for _ in range(args.steps):
            distribution = model.policy.get_distribution(
                obs_t[rows], action_masks=mask_t[rows]
            )
            logits = distribution.distribution.logits
            loss = -logits[:, indices].logsumexp(dim=1).mean()
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
        after = reroll_logprob(model.policy)
        results[arm] = {"after": after, "delta": after - baseline,
                        "shares_global_net": SHARES_GLOBAL_NET[arm]}
        print(f"{arm:<10}{str(SHARES_GLOBAL_NET[arm]):>19}{after:>14.4f}"
              f"{after - baseline:>+11.4f}")

    model.policy.load_state_dict(baseline_state)

    shared = [results[a]["delta"] for a in ARMS if SHARES_GLOBAL_NET[a]]
    separate = [results[a]["delta"] for a in ARMS if not SHARES_GLOBAL_NET[a]]
    mean_shared = sum(shared) / len(shared)
    mean_separate = sum(separate) / len(separate)
    print(f"\nshared-head arms {mean_shared:+.4f} vs separate-head arms "
          f"{mean_separate:+.4f}")
    if mean_shared > 0 and mean_shared > mean_separate + 0.05:
        print(
            "  -> COUPLING CONFIRMED. Pushing REROLL's `global_net` siblings "
            "lifts it despite its own negative advantage; the collapse is a "
            "shared-parameter artefact, not a reward problem."
        )
    elif mean_shared > 0 and mean_separate > 0:
        print(
            "  -> REROLL rises under every arm. Generic drift, not a slot-head "
            "artefact; the head is exonerated."
        )
    else:
        print(
            "  -> no lift from the shared head. The coupling hypothesis does "
            "not survive, and the drift is still unexplained."
        )

    if args.json:
        args.json.write_text(json.dumps(
            {"baseline": baseline, "arms": results}, indent=1))


if __name__ == "__main__":
    main()
