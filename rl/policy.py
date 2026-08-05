"""A policy head that scores unit slots with shared weights (doc 99 entry 39).

The default `MlpPolicy` maps a flat latent to one logit per action through a
single `Linear`, so every slot-typed action gets its own independent row of
weights. Nothing ties slot 3's logit to slot 3's features, and a comparison
across slots -- "which of these units is weakest" -- has to be relearned
separately for every slot from a concatenated vector.

Measured (doc 99 entry 39.1): reading the *same* observation with one shared
per-slot scorer predicts the teacher's SELL choice at 99.9% and its SELECT at
100.0% on held-out data, against 49.1% and 80.6% for a monolithic MLP over the
identical floats. The information was never missing; the architecture could not
express the comparison.

This head therefore:

* slices the board and bench sections into one block per unit slot,
* appends two positional floats per slot -- `on_bench` and normalised index --
  because a shared scorer sees each slot in isolation and would otherwise be
  unable to tell a board slot from a bench one, or break ties by index. Both
  are free to a monolithic head, which reads them from *where* the numbers sit,
* embeds every slot through **one** shared network,
* and reads SELL / SELECT / PLACE / EQUIP logits off those embeddings.

Everything else -- BUY, BUY_XP, REROLL, END_PLANNING, augments, offerings --
comes from a global trunk over the whole observation, unchanged in spirit from
the default head. Slot-typed actions are 48% of the expert's decisions.

The observation and the action space are untouched, so every prior measurement
stays comparable.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from sb3_contrib.common.maskable.policies import MaskableActorCriticPolicy


class SlotScoringHead(nn.Module):
    """Produces the full action-logit vector, slot actions via shared weights."""

    def __init__(
        self,
        obs_dim: int,
        n_actions: int,
        board_start: int,
        unit_width: int,
        n_slots: int,
        board_slots: int,
        slot_rows,
        offsets: dict[str, int],
        item_bag_slots: int,
        shop_start: int,
        shop_width: int,
        n_shop: int,
        hidden: int = 128,
        global_hidden: int = 256,
        context_dim: int = 64,
        use_slot_index: bool = False,
    ) -> None:
        super().__init__()
        self.board_start = board_start
        self.unit_width = unit_width
        self.n_slots = n_slots
        self.offsets = offsets
        self.item_bag_slots = item_bag_slots
        self.n_actions = n_actions

        # Constant per-slot position. `on_bench` is always supplied: a scorer
        # seeing one slot at a time cannot otherwise tell a fielded unit from
        # a benched one, and SELECT's rule reads the strongest *bench* unit.
        #
        # The normalised slot index is **off by default**, and that is a
        # judgement call rather than an oversight. Supplying it lifts SELL
        # match from the 82.0% tie ceiling to 99.9% (doc 99 entry 39.1), but
        # every one of those points comes from reproducing the teacher's
        # arbitrary "lowest bench index wins" tiebreak. Units tied on
        # `(star, cost)` are equivalent *to the teacher*, not to the game --
        # they differ in traits, which the teacher ignores and a learner need
        # not. Copying the tiebreak would be imitating an implementation
        # detail, and it costs the head its permutation-equivariance across
        # slots, which is the property this whole change exists to obtain.
        # Two positional facts, and they are different in kind. `on_bench`
        # distinguishes a fielded unit from a benched one. `row` is how far up
        # the board a hex sits, normalised -- and PLACE's whole rule is melee
        # to the front rows, ranged to the back.
        #
        # Removing the raw slot index was right: it encodes the teacher's
        # arbitrary lowest-index tiebreak. Removing the *row* with it was not,
        # and conflating the two cost 36 points of PLACE match (74.2% ->
        # 37.9%, doc 99 entry 45.5). A shared scorer that cannot tell the
        # front row from the back cannot express the placement rule at all.
        self.use_slot_index = use_slot_index
        width = 3 if use_slot_index else 2
        position = torch.zeros(n_slots, width)
        for slot in range(n_slots):
            position[slot, 0] = float(slot >= board_slots)
            position[slot, 1] = float(slot_rows[slot])
            if use_slot_index:
                position[slot, 2] = slot / max(n_slots - 1, 1)
        self.register_buffer("position", position)

        # Every slot is scored from its own block, its position, **and** a
        # learned embedding of the whole observation.
        #
        # Without the context term this head is strictly weaker than a
        # monolithic MLP for any decision whose rule reads something outside
        # the slot, and two of the four slot-typed kinds do: PLACE is a
        # function of the *held* unit's attack range and the target hex's row,
        # and SELECT switches regime on whether the board is full. Measured
        # without it (doc 99 entry 41.2): PLACE 68.8% -> 44.0%, SELECT
        # 66.7% -> 37.0%, and placement 3.760 -> 5.147. EQUIP, the one
        # slot-typed decision that genuinely depends on nothing else, went the
        # other way: 58.7% -> 83.4%.
        self.context_net = nn.Sequential(
            nn.Linear(obs_dim, global_hidden), nn.ReLU(),
            nn.Linear(global_hidden, context_dim), nn.ReLU(),
        )
        self.slot_net = nn.Sequential(
            nn.Linear(unit_width + width + context_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        # One scalar per slot for each single-slot action kind...
        self.sell_head = nn.Linear(hidden, 1)
        self.select_head = nn.Linear(hidden, 1)
        self.place_head = nn.Linear(hidden, 1)
        # ...and one per (item, slot) pair for EQUIP.
        self.equip_head = nn.Linear(hidden, item_bag_slots)

        # BUY is the same shape of decision -- an argmax over slots -- but over
        # the shop section, which the first version of this head did not touch.
        # Probed (doc 99 entry 45): the teacher's (owned, synergy, cost) rule is
        # readable at 92.3% from three hand-computed floats and at 91.8% ceiling,
        # while a monolithic MLP over the real observation manages 68.1% and a
        # shared-weight reader of the *same* floats reaches 84.4%.
        self.shop_start = shop_start
        self.shop_width = shop_width
        self.n_shop = n_shop
        # No positional feature here, unlike unit slots. `on_bench` is a real
        # distinction between board and bench; a shop slot's index means
        # nothing at all, and the teacher's `max()` breaking ties on the lowest
        # index is an implementation detail rather than a fact about the game.
        self.shop_net = nn.Sequential(
            nn.Linear(shop_width + context_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.buy_head = nn.Linear(hidden, 1)

        self.global_net = nn.Sequential(
            nn.Linear(obs_dim, global_hidden), nn.ReLU(),
            nn.Linear(global_hidden, global_hidden), nn.ReLU(),
            nn.Linear(global_hidden, n_actions),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        logits = self.global_net(obs)

        block = self.board_start + self.n_slots * self.unit_width
        slots = obs[:, self.board_start : block]
        slots = slots.view(-1, self.n_slots, self.unit_width)
        position = self.position.unsqueeze(0).expand(slots.shape[0], -1, -1)
        # The same context vector is broadcast to every slot, so the scoring
        # function stays shared -- slots are still interchangeable, they simply
        # all know what game is being played.
        context = self.context_net(obs).unsqueeze(1).expand(-1, self.n_slots, -1)
        embedded = self.slot_net(torch.cat([slots, position, context], dim=-1))

        # Overwrite the slot-typed ranges of the global head's output. The
        # global trunk still produces values there; replacing them keeps the
        # action layout identical to the default policy's, so nothing
        # downstream -- masking, distributions, the action space -- changes.
        logits = logits.clone()
        for name, head in (
            ("sell", self.sell_head),
            ("select", self.select_head),
            ("place", self.place_head),
        ):
            start = self.offsets[name]
            logits[:, start : start + self.n_slots] = head(embedded).squeeze(-1)

        start = self.offsets["equip"]
        # EQUIP index is equip_offset + item * n_slots + slot, so the item axis
        # is the outer one and has to lead after the transpose.
        equip = self.equip_head(embedded).transpose(1, 2).reshape(
            -1, self.item_bag_slots * self.n_slots
        )
        logits[:, start : start + equip.shape[1]] = equip

        shop_end = self.shop_start + self.n_shop * self.shop_width
        shop = obs[:, self.shop_start : shop_end].view(
            -1, self.n_shop, self.shop_width
        )
        shop_context = context[:, : self.n_shop, :]
        shop_embedded = self.shop_net(torch.cat([shop, shop_context], dim=-1))
        buy = self.offsets["buy"]
        logits[:, buy : buy + self.n_shop] = self.buy_head(shop_embedded).squeeze(-1)
        return logits


def make_slot_policy(env, use_slot_index: bool = False):
    """Build a policy class bound to ``env``'s observation and action layout.

    The offsets are read from the env rather than recomputed here: if the
    observation or action space ever changes shape, this must move with it or
    it will silently score the wrong floats.
    """
    spec = env.encoder.spec
    space = env.action_space_helper
    board_start = spec.offset_of("board")
    n_slots = space.unit_slots

    if spec.board_slots + spec.bench_slots != n_slots:
        raise ValueError(
            f"observation has {spec.board_slots}+{spec.bench_slots} unit slots "
            f"but the action space has {n_slots}; the slot head would score "
            "the wrong blocks"
        )

    # Normalised board row per slot; bench slots get 0. Read from the board
    # geometry rather than assumed, so a differently shaped board stays correct.
    from engine.hexgrid import axial_to_offset

    rows = [axial_to_offset(space.hex_for_slot(s))[0]
            for s in range(spec.board_slots)]
    span = max(max(rows) - min(rows), 1) if rows else 1
    low = min(rows) if rows else 0
    slot_rows = [(r - low) / span for r in rows] + [0.0] * spec.bench_slots

    offsets = {
        "buy": space.buy_offset,
        "sell": space.sell_offset,
        "select": space.select_offset,
        "place": space.place_offset,
        "equip": space.equip_offset,
    }
    item_bag_slots = space.item_bag_slots
    obs_dim = env.encoder.size
    n_actions = space.n
    unit_width = spec.unit_width

    class SlotPolicy(MaskableActorCriticPolicy):
        """`net_arch` gives the actor no trunk, so `action_net` receives the
        observation itself and can slice it. The critic keeps a normal MLP."""

        def __init__(self, *args, **kwargs):
            kwargs["net_arch"] = dict(pi=[], vf=[256, 256])
            super().__init__(*args, **kwargs)

        def _build(self, lr_schedule) -> None:
            super()._build(lr_schedule)
            self.action_net = SlotScoringHead(
                obs_dim=obs_dim,
                n_actions=n_actions,
                board_start=board_start,
                unit_width=unit_width,
                n_slots=n_slots,
                board_slots=spec.board_slots,
                slot_rows=slot_rows,
                offsets=offsets,
                item_bag_slots=item_bag_slots,
                shop_start=spec.offset_of("shop"),
                shop_width=spec.shop_width,
                n_shop=spec.shop_slots,
                use_slot_index=use_slot_index,
            )
            # `_build` wires the optimiser before this replacement, so it has
            # to be rebuilt or the new head's parameters never receive updates.
            self.optimizer = self.optimizer_class(
                self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs
            )

    return SlotPolicy
