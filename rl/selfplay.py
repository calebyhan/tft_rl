"""Self-play: past policy snapshots as opponent seats (doc 03 sec 3.4, milestone 9).

Doc 03 sec 3.4 names self-play -- "periodically snapshotting the current policy
as one of the 7 opponent seats" -- as the path beyond the fixed heuristic bots.
This module supplies the two pieces that needs.

:class:`SnapshotPolicy`
    Plays a *seat* using a trained model. :class:`~rl.env.TFTEnv` drives the
    agent one action per ``step``; a seat policy is instead handed a whole
    planning phase at once, so this runs the same select/act/apply loop
    internally against the same :class:`~rl.action.ActionExecutor`.

:class:`SnapshotPool`
    Holds past snapshots and samples which one fills each seat.

**Why sample from a pool rather than always using the latest policy.** Training
only against your current self is the classic route to a cycling,
non-transitive policy: the agent overfits one specific opponent, that opponent
moves, and earlier weaknesses come back. Sampling across historical snapshots
keeps the opponent distribution wide, which is the standard fix (the same
reason AlphaStar and OpenAI Five kept league/past-opponent pools).

**Cost.** A snapshot seat is a forward pass per action, against a scripted
seat's few hundred microseconds. Measured over 10 episodes with a trained
policy in every seat: 4.1s at ``mix=0``, 5.0s at ``mix=0.5``, 7.7s at
``mix=1.0`` -- so full self-play is about **1.9x** slower, not the order of
magnitude the arithmetic above suggests. The gap is smaller than it looks
because a policy that ends its planning phase early takes far fewer than
``max_actions_per_round`` forward passes. ``mix`` still exists to trade
opponent diversity against wall time.

**What it is measured to do.** Filed as *inert* after milestone 9 (-0.147, CI
spanning zero) against a control that did not visibly degrade. On the frozen
engine the control degrades badly, and the same null becomes the result: this
is the **only** arm that ends level with its warm start (+0.040 vs BC, t=0.25)
while every other arm loses ~0.6 placement to PPO. It does not make the agent
better; it stops PPO making it worse.

**The mechanism is not known.** The obvious story -- snapshot opponents are
weaker, so the agent wins more -- does not obviously explain a *protective*
effect, since evaluation is always against the fixed scripted bots. Single
training seed. See doc 99 entries 22.3 and 22.4.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Callable, Sequence

import numpy as np

from engine.match import PlanningContext
from engine.player import IllegalAction, PlayerState
from engine.schema import GameData
from rl.action import ActionExecutor, ActionSpace
from rl.observation import ObservationEncoder
from rl.opponents import GreedyPolicy

log = logging.getLogger(__name__)


class SnapshotPolicy:
    """A seat played by a trained model, one full planning phase per call.

    The model, action space and observation encoder must all agree with the
    training environment's. :func:`snapshot_factory` builds them from one
    ``TFTEnv`` so they cannot drift apart.
    """

    # This policy resolves its own augment picks inside ``plan``; if it does
    # not use them, the match's default pick applies as usual.
    defers_augment_pick = False

    def __init__(
        self,
        model: Any,
        data: GameData,
        board_hexes: Sequence,
        *,
        max_actions_per_round: int = 12,
        deterministic: bool = False,
        champion_encoding: str = "index",
        scouting: str = "summary",
        copy_counts: bool = False,
        n_opponents: int = 7,
    ) -> None:
        self.model = model
        self.data = data
        self.board_hexes = tuple(sorted(board_hexes))
        self.max_actions_per_round = max_actions_per_round
        # Stochastic by default: a deterministic opponent is a fixed target the
        # learner can memorise a single counter to.
        self.deterministic = deterministic
        self.space = ActionSpace(data.config)
        self.space.bind_board(self.board_hexes)
        self.executor = ActionExecutor(self.space)
        self.encoder = ObservationEncoder(
            data,
            len(self.board_hexes),
            n_opponents,
            champion_encoding=champion_encoding,
            scouting=scouting,
            copy_counts=copy_counts,
        )

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        self.executor.reset()
        opponents = [
            p for p in context.match.players if p.player_id != player.player_id
        ]
        for step in range(self.max_actions_per_round):
            mask = np.array(self.executor.legal_mask(player), dtype=bool)
            obs = self._observe(player, context, opponents, step)
            action = self._predict(obs, mask)
            try:
                _, finished = self.executor.apply(
                    player, action, context.pool, context.rng
                )
            except IllegalAction as exc:
                # A snapshot trained against a different observation or action
                # layout can emit something illegal. Ending its turn is the
                # honest response -- silently retrying would let a stale
                # snapshot act as a much weaker opponent without saying so.
                log.warning(
                    "snapshot seat %d produced an illegal action (%s); "
                    "ending its planning phase",
                    player.player_id,
                    exc,
                )
                return
            if finished:
                return

    def _observe(
        self,
        player: PlayerState,
        context: PlanningContext,
        opponents: list[PlayerState],
        step: int,
    ) -> np.ndarray:
        selected = self.executor.selected
        held = (
            self.executor.unit_at(player, selected) if selected is not None else None
        )
        return self.encoder.encode(
            player,
            context.round_id,
            opponents,
            self.board_hexes,
            actions_remaining=self.max_actions_per_round - step,
            max_actions=self.max_actions_per_round,
            selected_slot=selected,
            selected_unit=held,
        )

    def _predict(self, obs: np.ndarray, mask: np.ndarray) -> int:
        action, _ = self.model.predict(
            obs, action_masks=mask, deterministic=self.deterministic
        )
        return int(action)


class SnapshotPool:
    """Past policy snapshots, sampled to fill opponent seats.

    Empty until the first snapshot is added, so training starts against the
    scripted bots and only shifts to self-play once there is something to play
    against.
    """

    def __init__(self, capacity: int = 5) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self.capacity = capacity
        self.snapshots: list[Any] = []

    def add(self, model: Any) -> None:
        """Add a snapshot, evicting the oldest once at capacity."""
        self.snapshots.append(model)
        del self.snapshots[: -self.capacity]

    def sample(self, rng: random.Random) -> Any | None:
        if not self.snapshots:
            return None
        return rng.choice(self.snapshots)

    def __len__(self) -> int:
        return len(self.snapshots)


def snapshot_factory(
    pool: SnapshotPool,
    env,
    *,
    mix: float = 1.0,
    seed: int = 0,
    deterministic: bool = False,
) -> Callable[[int], Any]:
    """Build an ``opponent_factory`` that fills seats from ``pool``.

    ``mix`` is the fraction of opponent seats played by snapshots; the rest
    stay :class:`~rl.opponents.GreedyPolicy`. A seat also falls back to the
    scripted bot whenever the pool is still empty, so this is safe to pass from
    the very start of training.

    Every setting the snapshot needs is read off ``env``, so a snapshot seat
    always shares the learner's observation and action layout.
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError(f"mix must be in [0, 1], got {mix}")
    rng = random.Random(seed)

    def factory(seat: int):
        model = pool.sample(rng) if rng.random() < mix else None
        if model is None:
            return GreedyPolicy(seed=seed * 1000 + seat)
        # Copy the layout wholesale via `layout_settings()` rather than naming
        # options one at a time. Naming them is what broke: `copy_counts` was
        # added to the encoder and not here, so snapshot seats encoded 381
        # floats for a policy expecting 418 and self-play died several minutes
        # into every run (doc 99 entry 48).
        seat_policy = SnapshotPolicy(
            model,
            env.data,
            env._board_hexes,
            max_actions_per_round=env.max_actions_per_round,
            deterministic=deterministic,
            n_opponents=env.n_players - 1,
            **env.encoder.layout_settings(),
        )
        if seat_policy.encoder.size != env.encoder.size:
            raise ValueError(
                f"snapshot seat encodes {seat_policy.encoder.size} floats but "
                f"the learner's env encodes {env.encoder.size}; the seat's "
                "observation layout does not match the policy's"
            )
        return seat_policy

    return factory
