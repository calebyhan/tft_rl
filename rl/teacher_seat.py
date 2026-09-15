"""An action-space teacher playing a seat other than the agent's.

Every teacher in :mod:`rl.search` and :mod:`rl.greedy_action` is written
against ``TFTEnv``: it reads ``env.player``, ``env.match`` and
``env.action_space_helper``, and registers resolution-time hooks with
``env.register_external_policy``. A ``Match`` seat is handed a whole planning
phase through ``plan(player, context)`` instead. :class:`TeacherSeat` bridges
the two so a teacher can sit in an opponent seat.

**The contract is replay, not resemblance.** Seat 0 played through this
adapter inside a plain ``Match`` must leave every player in the same state
after every round as the same teacher driven through ``TFTEnv``
(``tests/test_teacher_seat.py``). Doc 99 entry 160.101 is why that bar is
byte-level: a shadow env that dropped one resolution hook resolved items
differently, played a different game, and nothing crashed.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from engine.match import Match, PlanningContext
from engine.player import PlayerState
from engine.schema import GameData
from rl.action import ActionExecutor, ActionSpace
from rl.opponents import GreedyPolicy

PolicyFn = Callable[[Any, np.ndarray], int]


class SeatView:
    """The slice of ``TFTEnv`` an action-space teacher reads, bound to one seat."""

    def __init__(self, seat: int, space: ActionSpace) -> None:
        self.seat = seat
        self.action_space_helper = space
        self.executor = ActionExecutor(space)
        self.match: Match | None = None
        self.external_policy: Any | None = None

    @property
    def player(self) -> PlayerState:
        assert self.match is not None
        return self.match.players[self.seat]

    def action_masks(self) -> np.ndarray:
        return np.array(self.executor.legal_mask(self.player), dtype=bool)

    def register_external_policy(self, policy: Any) -> None:
        self.external_policy = policy


class _SilentSeat:
    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        pass


class TeacherSeat:
    """Run a teacher's action loop for one full planning phase per ``plan``.

    ``build_policy`` receives the :class:`SeatView` in place of an env, so the
    existing factories (``greedy_action_policy``,
    ``search_item_greedy_policy``) work unchanged.
    """

    # No ``defers_augment_pick``: the scheduler emits PICK_AUGMENT itself
    # before it can end the phase, and on an exhausted budget Match's default
    # (the first offer) is TFTEnv._advance_round's rule. Mutation-tested --
    # setting the flag changes no trace.

    def __init__(
        self,
        data: GameData,
        build_policy: Callable[[SeatView], PolicyFn],
        *,
        seat: int,
        max_actions_per_round: int = 600,
    ) -> None:
        players = data.config.round_structure.players
        if not 0 <= seat < players:
            raise ValueError(f"seat must be 0..{players - 1}, got {seat}")
        # Every seat's own hexes are team 0's half (PlayerState._own_hexes),
        # so one action-space binding serves any seat, exactly as in TFTEnv.
        hexes = tuple(sorted(Match(
            data, [_SilentSeat() for _ in range(players)]
        ).board.half_board_hexes(0)))
        space = ActionSpace(data.config)
        space.bind_board(hexes)
        self.view = SeatView(seat, space)
        self.policy = build_policy(self.view)
        self.max_actions_per_round = max_actions_per_round
        self.actions_taken = 0
        # ``Match.play_round`` cannot pause a carousel for an external seat the
        # way TFTEnv does, so the pick is answered synchronously. The
        # scheduler's PICK_OFFERING applies this same rule, and it reads no
        # rng, so answering it here is the same pick in the same draft order.
        self._offering_rule = GreedyPolicy()

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        if player.player_id != self.view.seat:
            raise ValueError(
                f"TeacherSeat for seat {self.view.seat} asked to plan "
                f"seat {player.player_id}"
            )
        self.view.match = context.match
        self.view.executor.reset()
        for _ in range(self.max_actions_per_round):
            action = int(self.policy(None, self.view.action_masks()))
            self.actions_taken += 1
            _, finished = self.view.executor.apply(
                player, action, context.pool, context.rng
            )
            if finished:
                break

    def choose_offering(self, player: PlayerState, offerings) -> int:
        return self._offering_rule.choose_offering(player, offerings)

    def __getattr__(self, name: str):
        """Expose the teacher's anvil hook, as ``rl.env._AgentSeat`` does."""
        view = self.__dict__.get("view")
        if name == "choose_component" and view is not None:
            chooser = getattr(view.external_policy, name, None)
            if chooser is not None:
                return chooser
        raise AttributeError(name)
