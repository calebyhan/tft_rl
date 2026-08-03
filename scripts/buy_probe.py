"""Can any architecture learn the expert's BUY rule? (doc 99 27.2)

BUY sits at ~48% against a 90.7% ceiling and ignores everything: 3.75x the
data, an explicit trait multi-hot per shop slot, and DAgger's on-distribution
labels all move it under 2.5 points, while every other action kind responds
normally (doc 99 25-27).

Entry 27.2's surviving explanation is structural rather than informational:
BUY is a *relational argmax over a candidate set* -- score each affordable shop
slot against the board, take the best -- and a flat MLP whose action head is a
linear layer over all 501 actions computes the logit for ``BUY(slot i)`` from
pooled features rather than from slot *i*'s own token.

This probe tests that offline, in isolation, before anything invasive is built
into the sb3 policy. Three heads on identical inputs and identical data:

* ``flat``    -- MLP over the whole observation. Must reproduce ~48%, which is
                 what makes the probe faithful rather than a different problem.
* ``shared``  -- one scorer applied per slot: ``[slot token ; context] -> scalar``.
                 Isolates per-slot scoring from attention.
* ``pointer`` -- attention over unit/shop tokens, then a per-slot scalar. The
                 full architecture claim.

If ``pointer`` moves toward 90.7% while ``flat`` stays at ~48%, the mechanism is
confirmed and a custom policy class is justified. If nothing beats ~48%, the
mechanism is wrong and that was learned for an afternoon of compute rather than
after rewriting the policy.

    python scripts/buy_probe.py --episodes 400
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
from rl.action import ActionKind  # noqa: E402
from scripts.train_ppo import ENV_DEFAULTS, build_env  # noqa: E402


def collect_buy_decisions(data, episodes: int):
    """Every BUY decision the expert made, as (obs, candidate mask, chosen slot)."""
    obs, masks, actions, owned_by_slot = collect_with_owned(data, episodes)
    env = build_env(data)
    space = env.action_space_helper
    shop_slots = space.shop_slots

    rows, candidates, labels, owned_flags = [], [], [], []
    for o, m, a in zip(obs, masks, actions, strict=True):
        if space.decode(int(a)).kind is not ActionKind.BUY:
            continue
        legal = np.array(
            [bool(m[space.buy_offset + s]) for s in range(shop_slots)], dtype=bool
        )
        if legal.sum() < 2:
            continue  # forced or impossible -- carries no signal either way
        rows.append(o)
        candidates.append(legal)
        labels.append(space.decode(int(a)).a)
        owned_flags.append(owned_by_slot[len(rows) - 1])
    return (
        np.asarray(rows, dtype=np.float32),
        np.asarray(candidates),
        np.asarray(labels, dtype=np.int64),
        np.asarray(owned_flags, dtype=np.float32),
        env,
    )


def collect_with_owned(data, episodes: int):
    """Expert rollout that also records, per shop slot, whether it is owned.

    Taken from the engine rather than the observation, deliberately: the point
    is to measure what the observation would need to expose, so the ground
    truth has to come from outside it.
    """
    env = build_env(data)
    from rl.evaluate import scripted_policy

    policy = scripted_policy(env)
    observations, masks, actions, owned = [], [], [], []
    for seed in range(episodes):
        o, _ = env.reset(seed=200_000 + seed)
        done = False
        while not done:
            mask = env.action_mask()
            player = env.player
            held = {u.champion.id for u in player.all_units}
            flags = [
                float(player.shop.peek(slot) in held)
                for slot in range(player.data.config.shop_slots)
            ]
            observations.append(o.copy())
            masks.append(mask.copy())
            actions.append(policy(o, mask))
            owned.append(flags)
            o, _, done, _, _ = env.step(actions[-1])
    return (
        np.asarray(observations, dtype=np.float32),
        np.asarray(masks),
        np.asarray(actions),
        np.asarray(owned, dtype=np.float32),
    )


class FlatHead(nn.Module):
    """Baseline: the current architecture. Pooled features -> one logit per slot."""

    def __init__(self, obs_dim: int, slots: int, hidden: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, slots),
        )

    def forward(self, obs, tokens):
        return self.net(obs)


class SharedScorerHead(nn.Module):
    """One scorer, applied to each slot in turn: [token ; context] -> scalar.

    No attention. Isolates "score candidates independently with shared weights"
    from "let candidates see each other", so a win here would localise the fix
    to weight sharing rather than to attention.
    """

    def __init__(self, obs_dim: int, token_dim: int, hidden: int = 256):
        super().__init__()
        self.context = nn.Sequential(nn.Linear(obs_dim, hidden), nn.ReLU())
        self.score = nn.Sequential(
            nn.Linear(token_dim + hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, obs, tokens):
        context = self.context(obs)                          # (B, H)
        n = tokens.shape[1]
        paired = torch.cat(
            [tokens, context.unsqueeze(1).expand(-1, n, -1)], dim=-1
        )
        return self.score(paired).squeeze(-1)                 # (B, slots)


class PointerHead(nn.Module):
    """Attention over the shop tokens, then a per-slot scalar.

    The shop slots attend to each other and to a context vector, so a slot's
    logit depends on what the alternatives are -- which is what "argmax over a
    candidate set" needs and what a flat linear head cannot express.
    """

    def __init__(self, obs_dim: int, token_dim: int, hidden: int = 128, heads: int = 4):
        super().__init__()
        self.embed = nn.Linear(token_dim, hidden)
        self.context = nn.Sequential(nn.Linear(obs_dim, hidden), nn.ReLU())
        self.attn = nn.MultiheadAttention(hidden, heads, batch_first=True)
        self.norm = nn.LayerNorm(hidden)
        self.score = nn.Sequential(
            nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1)
        )

    def forward(self, obs, tokens):
        embedded = self.embed(tokens)                         # (B, slots, H)
        context = self.context(obs).unsqueeze(1)              # (B, 1, H)
        sequence = torch.cat([context, embedded], dim=1)      # context is slot 0
        attended, _ = self.attn(sequence, sequence, sequence)
        attended = self.norm(attended + sequence)
        return self.score(attended[:, 1:, :]).squeeze(-1)     # drop the context slot


class LeanScorerHead(nn.Module):
    """Per-slot scorer over a *lean* input: the slot token plus the trait counts.

    The three fat heads all reached 100% train accuracy at ~48% test -- they
    memorised. The context path handed them all 2154 dims, which is capacity to
    memorise 6872 samples rather than pressure to learn the rule. This restricts
    the input to what the expert's rule actually reads: the champion's own
    features (traits included) and the board's trait counts.
    """

    def __init__(self, token_dim: int, context_dim: int, hidden: int = 64):
        super().__init__()
        self.score = nn.Sequential(
            nn.Linear(token_dim + context_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, obs, tokens, context):
        n = tokens.shape[1]
        paired = torch.cat([tokens, context.unsqueeze(1).expand(-1, n, -1)], dim=-1)
        return self.score(paired).squeeze(-1)


class BilinearHead(nn.Module):
    """Lean input plus an explicit dot-product interaction term.

    ``synergy`` in the expert's rule is literally sum_t (champion has trait t) *
    (board count of trait t) -- an elementwise product summed, which a ReLU MLP
    approximates only awkwardly. Supplying the product as a feature tests
    whether the missing ingredient is that specific inductive bias. If this
    works and LeanScorer does not, the answer is precise: the architecture needs
    a multiplicative champion-by-board interaction, not more capacity.
    """

    def __init__(self, token_dim: int, context_dim: int, trait_dim: int, hidden: int = 64):
        super().__init__()
        self.trait_dim = trait_dim
        self.score = nn.Sequential(
            nn.Linear(token_dim + context_dim + trait_dim + 1, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, obs, tokens, context):
        n = tokens.shape[1]
        # The champion's trait multi-hot sits at the tail of its token.
        champion_traits = tokens[:, :, -self.trait_dim :]
        board_traits = context[:, -self.trait_dim :].unsqueeze(1).expand(-1, n, -1)
        product = champion_traits * board_traits
        synergy = product.sum(dim=-1, keepdim=True)
        paired = torch.cat(
            [tokens, context.unsqueeze(1).expand(-1, n, -1), product, synergy], dim=-1
        )
        return self.score(paired).squeeze(-1)


class OracleHead(nn.Module):
    """Lean input plus the ``owned`` flag, supplied from the engine.

    ``owned`` is the *primary* key in the expert's sort and requires matching
    each shop champion's identity against every board and bench unit. If this
    head fits where LeanScorer cannot, the missing ingredient is identified
    exactly: a shop-slot-to-roster identity comparison.
    """

    def __init__(self, token_dim: int, context_dim: int, trait_dim: int, hidden: int = 64):
        super().__init__()
        self.trait_dim = trait_dim
        self.score = nn.Sequential(
            nn.Linear(token_dim + context_dim + 2, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, obs, tokens, context, owned):
        n = tokens.shape[1]
        champion_traits = tokens[:, :, -self.trait_dim :]
        board_traits = context[:, -self.trait_dim :].unsqueeze(1).expand(-1, n, -1)
        synergy = (champion_traits * board_traits).sum(dim=-1, keepdim=True)
        paired = torch.cat(
            [tokens, context.unsqueeze(1).expand(-1, n, -1), synergy,
             owned.unsqueeze(-1)],
            dim=-1,
        )
        return self.score(paired).squeeze(-1)


def run(name, model, train, test, epochs: int, lr: float = 1e-3):
    obs_tr, tok_tr, ctx_tr, own_tr, cand_tr, y_tr = train
    obs_te, tok_te, ctx_te, own_te, cand_te, y_te = test
    if isinstance(model, OracleHead):
        call = lambda o, t, c, w: model(o, t, c, w)          # noqa: E731
    elif isinstance(model, (LeanScorerHead, BilinearHead)):
        call = lambda o, t, c, w: model(o, t, c)             # noqa: E731
    else:
        call = lambda o, t, c, w: model(o, t)                # noqa: E731
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    n = len(y_tr)
    for _epoch in range(epochs):
        model.train()
        order = torch.randperm(n)
        for start in range(0, n, 256):
            batch = order[start : start + 256]
            logits = call(obs_tr[batch], tok_tr[batch], ctx_tr[batch], own_tr[batch])
            logits = logits.masked_fill(~cand_tr[batch], -1e9)
            loss = nn.functional.cross_entropy(logits, y_tr[batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
    model.eval()
    with torch.no_grad():
        logits = call(obs_te, tok_te, ctx_te, own_te).masked_fill(~cand_te, -1e9)
        accuracy = float((logits.argmax(dim=-1) == y_te).float().mean())
        train_logits = call(obs_tr, tok_tr, ctx_tr, own_tr).masked_fill(~cand_tr, -1e9)
        train_accuracy = float((train_logits.argmax(dim=-1) == y_tr).float().mean())
    print(f"  {name:<9} test {accuracy:>6.1%}   (train {train_accuracy:.1%})")
    return accuracy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=400)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--encoding", default="features", choices=["features", "index"])
    parser.add_argument("--seed", type=int, default=21)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    ENV_DEFAULTS["champion_encoding"] = args.encoding
    data = load_all()

    obs, candidates, labels, owned, env = collect_buy_decisions(data, args.episodes)
    spec = env.encoder.spec
    shop_start = spec.offset_of("shop")
    width = spec.shop_width
    slots = spec.shop_slots
    tokens = obs[:, shop_start : shop_start + slots * width].reshape(-1, slots, width)

    print(f"\nBUY decisions with >=2 candidates: {len(labels)}")
    print(f"encoding={args.encoding}  obs={obs.shape[1]}  shop token width={width}")
    majority = float(np.mean(labels == np.argmax(candidates, axis=1)))
    print(f"always-pick-first-candidate baseline: {majority:.1%}")

    trait_start = spec.offset_of("traits")
    n_traits = spec.n_traits
    context = np.concatenate(
        [obs[:, : spec.offset_of("selection")],
         obs[:, trait_start : trait_start + n_traits]],
        axis=1,
    )
    print(f"lean context width: {context.shape[1]} "
          f"(self scalars + {n_traits} board trait counts)")

    split = int(0.8 * len(labels))
    to_t = lambda a, dtype=torch.float32: torch.as_tensor(a, dtype=dtype)  # noqa: E731
    train = (
        to_t(obs[:split]), to_t(tokens[:split]), to_t(context[:split]),
        to_t(owned[:split]),
        to_t(candidates[:split], torch.bool), to_t(labels[:split], torch.long),
    )
    test = (
        to_t(obs[split:]), to_t(tokens[split:]), to_t(context[split:]),
        to_t(owned[split:]),
        to_t(candidates[split:], torch.bool), to_t(labels[split:], torch.long),
    )

    print(f"\ntrain {split} / test {len(labels) - split}, {args.epochs} epochs")
    obs_dim, token_dim = obs.shape[1], width
    run("flat", FlatHead(obs_dim, slots), train, test, args.epochs)
    run("shared", SharedScorerHead(obs_dim, token_dim), train, test, args.epochs)
    run("pointer", PointerHead(obs_dim, token_dim), train, test, args.epochs)
    context_dim = context.shape[1]
    run("lean", LeanScorerHead(token_dim, context_dim), train, test, args.epochs)
    run("bilinear", BilinearHead(token_dim, context_dim, n_traits), train, test, args.epochs)
    run("oracle", OracleHead(token_dim, context_dim, n_traits), train, test, args.epochs)
    print("\nceiling for a model that cannot see slot index: 90.7% (doc 99 26.1)")


if __name__ == "__main__":
    main()
