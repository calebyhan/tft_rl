"""Permutation-aware feature extractor for the scouted-board observation.

The extractor deliberately has no player-slot or token-row embedding.  Unit
hexes are values in the token, so a permutation of how tokens are stored cannot
change the representation.  Units pool into their own board before boards pool
into the opponent context; flattening all units would lose that grouping.

Own item tensors retain their action-aligned order: bag position names EQUIP's
item operand and board/bench position names its target operand. They are
embedded and flattened rather than pooled so the extractor cannot erase that
relation (doc 99 entry 160.115).
"""

from __future__ import annotations

import torch
import torch.nn as nn
from gymnasium import spaces
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor


class ScoutSetExtractor(BaseFeaturesExtractor):
    """Encode unit tokens -> board tokens -> an unordered opponent context."""

    def __init__(
        self,
        observation_space: spaces.Dict,
        unit_dim: int = 64,
        board_dim: int = 96,
        own_item_dim: int = 96,
        global_dim: int = 128,
        features_dim: int = 256,
    ) -> None:
        if not isinstance(observation_space, spaces.Dict):
            raise TypeError("ScoutSetExtractor requires a Dict observation space")
        required = {
            "global",
            "item_bag",
            "own_items",
            "opponent_units",
            "opponent_board",
            "opponent_augments",
        }
        if set(observation_space.spaces) != required:
            raise ValueError(
                f"scout observation keys must be {sorted(required)}, got "
                f"{sorted(observation_space.spaces)}"
            )
        super().__init__(observation_space, features_dim)
        unit_space = observation_space["opponent_units"]
        board_space = observation_space["opponent_board"]
        augment_space = observation_space["opponent_augments"]
        global_space = observation_space["global"]
        bag_space = observation_space["item_bag"]
        own_item_space = observation_space["own_items"]
        if len(unit_space.shape) != 3 or unit_space.shape[-1] != 8:
            raise ValueError("opponent_units must have shape (boards, slots, 8)")
        if len(board_space.shape) != 2 or board_space.shape[-1] != 5:
            raise ValueError("opponent_board must have shape (boards, 5)")
        if len(augment_space.shape) != 2 or augment_space.shape[0] != board_space.shape[0]:
            raise ValueError("opponent_augments must have shape (boards, augment_slots)")
        if len(bag_space.shape) != 1:
            raise ValueError("item_bag must have shape (bag_slots,)")
        if len(own_item_space.shape) != 2:
            raise ValueError("own_items must have shape (unit_slots, item_slots)")

        max_token_id = int(unit_space.high.max()) + 1
        self.champion_embedding = nn.Embedding(max_token_id, 24)
        self.star_embedding = nn.Embedding(4, 6)
        self.item_embedding = nn.Embedding(max_token_id, 12, padding_idx=0)
        self.augment_embedding = nn.Embedding(int(augment_space.high.max()) + 1, 16)
        self.q_embedding = nn.Embedding(max_token_id, 6)
        self.r_embedding = nn.Embedding(max_token_id, 6)
        self.unit_net = nn.Sequential(
            nn.Linear(24 + 6 + 12 + 6 + 6, unit_dim),
            nn.ReLU(),
            nn.Linear(unit_dim, unit_dim),
            nn.ReLU(),
        )
        self.board_net = nn.Sequential(
            nn.Linear(unit_dim + 16 + board_space.shape[-1], board_dim),
            nn.ReLU(),
            nn.Linear(board_dim, board_dim),
            nn.ReLU(),
        )
        self.opponent_net = nn.Sequential(
            nn.Linear(board_dim, board_dim),
            nn.ReLU(),
        )
        self.global_net = nn.Sequential(
            nn.Linear(global_space.shape[0], global_dim),
            nn.ReLU(),
            nn.Linear(global_dim, global_dim),
            nn.ReLU(),
        )
        own_item_width = (bag_space.shape[0] + own_item_space.shape[0]
                          * own_item_space.shape[1]) * 12
        self.own_item_net = nn.Sequential(
            nn.Linear(own_item_width, own_item_dim),
            nn.ReLU(),
            nn.Linear(own_item_dim, own_item_dim),
            nn.ReLU(),
        )
        self.output_net = nn.Sequential(
            nn.Linear(global_dim + board_dim + own_item_dim, features_dim),
            nn.ReLU(),
        )

    def forward(self, observations: dict[str, torch.Tensor]) -> torch.Tensor:
        tokens = observations["opponent_units"].long()
        board_scalars = observations["opponent_board"].float()
        augment_tokens = observations["opponent_augments"].long()
        bag_tokens = observations["item_bag"].long()
        own_item_tokens = observations["own_items"].long()
        present = tokens[..., 0].bool()

        champion = self.champion_embedding(tokens[..., 1])
        star = self.star_embedding(tokens[..., 2].clamp(max=3))
        items = self.item_embedding(tokens[..., 3:6]).sum(dim=-2)
        q = self.q_embedding(tokens[..., 6])
        r = self.r_embedding(tokens[..., 7])
        unit = self.unit_net(torch.cat((champion, star, items, q, r), dim=-1))
        unit = unit * present.unsqueeze(-1)
        unit_count = present.sum(dim=-1, keepdim=True).clamp(min=1)
        pooled_units = unit.sum(dim=-2) / unit_count

        augment_present = augment_tokens.ne(0)
        augment = self.augment_embedding(augment_tokens)
        augment = augment * augment_present.unsqueeze(-1)
        augment_count = augment_present.sum(dim=-1, keepdim=True).clamp(min=1)
        pooled_augments = augment.sum(dim=-2) / augment_count

        boards = self.board_net(
            torch.cat((pooled_units, pooled_augments, board_scalars), dim=-1)
        )
        # A dead/missing opponent is not a board to attend to.  The denominator
        # is clamped so terminal states with no opponents remain finite.
        alive = board_scalars[..., 4:5]
        boards = self.opponent_net(boards) * alive
        board_count = alive.sum(dim=-2).clamp(min=1)
        opponent_context = boards.sum(dim=-2) / board_count
        global_context = self.global_net(observations["global"].float())
        own_items = torch.cat(
            (
                self.item_embedding(bag_tokens).flatten(start_dim=1),
                self.item_embedding(own_item_tokens).flatten(start_dim=1),
            ),
            dim=-1,
        )
        own_item_context = self.own_item_net(own_items)
        return self.output_net(
            torch.cat((global_context, opponent_context, own_item_context), dim=-1)
        )
