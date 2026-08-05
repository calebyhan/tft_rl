"""Gymnasium environment wrapping one seat of a :class:`~engine.match.Match`.

The agent plays one seat; the other seats run :mod:`rl.opponents` policies
(doc 03 sec 3). One ``step`` is one *planning-phase action*, not one round --
the planning phase behaves as a short sub-episode that ends when the agent
picks ``END_PLANNING`` or exhausts its action budget, at which point the
environment advances the whole match by a round before returning control
(doc 03 sec 3.2).

Reward is sparse and terminal by default: ``(9 - placement) / 8`` at game end,
nothing in between. Doc 03 sec 3.3 recommends starting without shaping because
shaping is easy to get subtly wrong; optional shaping is available behind
``reward_shaping=True`` and stays small relative to the terminal reward.

The environment drives ``Match`` one round at a time rather than calling
``Match.run()``, so the agent's planning phase can be interleaved.
"""

from __future__ import annotations

import random
from typing import Any, Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from engine.items import ItemRegistry
from engine.loader import DEFAULT_DATA_DIR, load_all
from engine.match import Match, PlanningContext
from engine.player import IllegalAction, PlayerState
from engine.schema import GameData
from rl.action import ActionExecutor, ActionKind, ActionSpace
from rl.observation import ObservationEncoder
from rl.opponents import GreedyPolicy

DEFAULT_MAX_ACTIONS_PER_ROUND = 12

# How dense shaping is computed. "potential" is policy-invariant; "bonus"
# is the earlier standing-payment form, kept only for comparison.
SHAPING_MODES = ("potential", "bonus")


class _AgentSeat:
    """A no-op policy for the agent's seat.

    The agent acts through ``env.step``, so when ``Match`` runs the planning
    phase this policy does nothing and simply records that it was called.
    """

    # The agent picks augments and realm offerings through its own actions,
    # so the match must not resolve either on its behalf.
    defers_augment_pick = True
    defers_realm_pick = True

    def __init__(self) -> None:
        self.pending_context: PlanningContext | None = None

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        self.pending_context = context


class TFTEnv(gym.Env):
    """One seat of a full 8-player TFT game, as a Gymnasium environment."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(
        self,
        data: GameData | None = None,
        *,
        agent_seat: int = 0,
        opponent_factory: Callable[[int], Any] | None = None,
        max_actions_per_round: int = DEFAULT_MAX_ACTIONS_PER_ROUND,
        reward_shaping: bool = False,
        board_reward_weight: float = 0.03,
        survival_reward_weight: float = 0.01,
        strict_actions: bool = False,
        invalid_action_penalty: float = 0.0,
        champion_encoding: str = "index",
        scouting: str = "summary",
        copy_counts: bool = False,
        shaping_mode: str = "potential",
        shaping_gamma: float = 0.999,
        seed: int | None = None,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        self.data = data or load_all(DEFAULT_DATA_DIR)
        self.config = self.data.config
        self.registry = ItemRegistry(self.data.items, self.config.max_items_per_unit)
        self.n_players = self.config.round_structure.players
        if not 0 <= agent_seat < self.n_players:
            raise ValueError(f"agent_seat must be 0..{self.n_players - 1}")
        self.agent_seat = agent_seat
        self.opponent_factory = opponent_factory or (lambda seat: GreedyPolicy(seed=seat))
        self.max_actions_per_round = max_actions_per_round
        self.reward_shaping = reward_shaping
        self.board_reward_weight = board_reward_weight
        self.survival_reward_weight = survival_reward_weight
        if shaping_mode not in SHAPING_MODES:
            raise ValueError(
                f"shaping_mode must be one of {SHAPING_MODES}, got {shaping_mode!r}"
            )
        self.shaping_mode = shaping_mode
        # Must match the training gamma for the telescoping guarantee to hold.
        self.shaping_gamma = shaping_gamma
        self._last_potential = 0.0
        # A 'good' average unit for normalising board strength: mid-cost, 2-star.
        tiers = sorted(self.config.pool_sizes) or [1]
        self._reference_unit_value = (sum(tiers) / len(tiers)) * 2
        self.strict_actions = strict_actions
        self.invalid_action_penalty = invalid_action_penalty
        self.render_mode = render_mode

        self._board_hexes = tuple(sorted(Match(
            self.data, [_AgentSeat() for _ in range(self.n_players)], registry=self.registry
        ).board.half_board_hexes(0)))

        self.action_space_helper = ActionSpace(self.config)
        self.action_space_helper.bind_board(self._board_hexes)
        self.executor = ActionExecutor(self.action_space_helper)
        self.encoder = ObservationEncoder(
            self.data,
            len(self._board_hexes),
            self.n_players - 1,
            champion_encoding=champion_encoding,
            scouting=scouting,
            copy_counts=copy_counts,
        )

        self.action_space = spaces.Discrete(self.action_space_helper.n)
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.encoder.size,), dtype=np.float32
        )

        self._seed = seed
        self.match: Match | None = None
        self.actions_left = 0
        self._pending_realm = False
        self._last_hp = 0
        self._episode_reward = 0.0

    # -- gym api ----------------------------------------------------------

    def reset(
        self, *, seed: int | None = None, options: dict | None = None
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        match_seed = seed if seed is not None else self._seed
        if match_seed is None:
            match_seed = random.randrange(2**31)
        self._seed = None  # a fixed seed applies to the first reset only

        policies = [
            _AgentSeat() if i == self.agent_seat else self.opponent_factory(i)
            for i in range(self.n_players)
        ]
        self.match = Match(self.data, policies, seed=match_seed, registry=self.registry)
        self.executor.reset()
        self.actions_left = self.max_actions_per_round
        self._episode_reward = 0.0

        # Run the match up to the agent's first planning phase.
        self._begin_planning()
        self._last_hp = self.player.hp
        self._last_potential = self._potential()
        return self._observe(), self._info()

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        if self.match is None:
            raise RuntimeError("call reset() before step()")

        reward = 0.0
        illegal = False
        # Doc 03 sec 2.10: the engine raises on illegal actions so *this*
        # wrapper can catch and mask them. An unmasked agent (or Gymnasium's
        # API checker, which samples the raw space) therefore gets a scored
        # no-op rather than a crash. Set strict_actions=True to surface the
        # error instead -- useful when debugging a policy that ignores the mask.
        try:
            decoded, finished_planning = self.executor.apply(
                self.player, int(action), self.match.pool, self.match.rng
            )
        except IllegalAction:
            if self.strict_actions:
                raise
            illegal = True
            decoded = self.action_space_helper.decode(int(action))
            finished_planning = False
            reward += self.invalid_action_penalty
        self.actions_left -= 1

        if finished_planning or self.actions_left <= 0:
            reward += self._advance_round()
            if not self.match.finished and self.player.alive:
                self._begin_planning()

        terminated = self.match.finished or not self.player.alive
        if terminated:
            reward += self._terminal_reward()

        self._episode_reward += reward
        info = self._info(decoded)
        info["illegal_action"] = illegal
        return self._observe(), reward, terminated, False, info

    def render(self) -> str | None:
        if self.render_mode != "ansi" or self.match is None:
            return None
        player = self.player
        board = ", ".join(sorted(u.name for u in player.board_units)) or "(empty)"
        shop = ", ".join(
            self.data.champions[c].display_name if c else "-" for c in player.shop.slots
        )
        return (
            f"[{self.match.round_id}] seat {self.agent_seat}  hp={player.hp} "
            f"gold={player.gold} lvl={player.level} actions_left={self.actions_left}\n"
            f"  board: {board}\n  shop:  {shop}"
        )

    # -- internals --------------------------------------------------------

    @property
    def player(self) -> PlayerState:
        assert self.match is not None
        return self.match.players[self.agent_seat]

    def _begin_planning(self) -> None:
        """Advance the match until the agent's seat is mid-planning-phase.

        ``Match._planning_phase`` calls every seat's policy including the
        agent's no-op seat, so after it returns the agent's shop is rolled and
        the opponents have already acted.
        """
        assert self.match is not None
        while not self.match.finished and self.player.alive:
            match = self.match
            self._pending_realm = match.is_realm_round
            if self._pending_realm:
                # Seats with less HP than the agent draft *before* it; the
                # draft then pauses on the agent's turn, and resume_realm()
                # finishes the rest once the agent has picked.
                match._realm_phase()
            is_pve = match.structure.is_pve(
                match.round_id.stage, match.round_id.round
            )
            match._planning_phase(is_pve)
            self._pending_pve = is_pve
            self.executor.reset()
            self.actions_left = self.max_actions_per_round
            return

    def _advance_round(self) -> float:
        """Resolve combat for the round the agent just finished planning."""
        assert self.match is not None
        match = self.match
        hp_before = self.player.hp

        # The action mask blocks END_PLANNING while an offer is pending, but
        # exhausting the action budget still lands here. TFT does not allow
        # declining either kind of pick, so take the first rather than carrying
        # a live offer into combat.
        if self.player.has_pending_augment:
            self.player.pick_augment(0)
        if self.player.has_pending_offering:
            self.player.pick_offering(0)
        if self._pending_realm:
            # Let the seats above the agent in HP order take what is left.
            match.resume_realm()
            # A realm round has no fight; income is still paid.
            for player in match.living_players:
                player.award_income(match.round_id)
            match.rounds_played += 1
            match.round_id = match.round_id.next(
                match.structure.rounds_in_stage(match.round_id.stage)
            )
            self._last_hp = self.player.hp
            self._pending_realm = False
            if not self.reward_shaping:
                return 0.0
            return self._shaping_reward(hp_before)

        reports = match._combat_phase(self._pending_pve)
        match._resolution_phase(reports)
        match.rounds_played += 1
        match.round_id = match.round_id.next(
            match.structure.rounds_in_stage(match.round_id.stage)
        )

        self._last_hp = self.player.hp
        if not self.reward_shaping:
            return 0.0
        return self._shaping_reward(hp_before)

    def _potential(self) -> float:
        """State value used by potential-based shaping: board strength + HP.

        Board strength is fielded units weighted by cost and star level,
        normalised against a plausible strong board for the current level.
        """
        player = self.player
        strength = sum(
            unit.champion.cost * unit.star_level for unit in player.board_units
        )
        reference = max(player.max_board_units * self._reference_unit_value, 1)
        board = self.board_reward_weight * min(strength / reference, 1.5)
        survival = self.survival_reward_weight * (
            player.hp / max(self.config.starting_hp, 1)
        )
        return board + survival

    def _shaping_reward(self, hp_before: int) -> float:
        """Dense per-round shaping (doc 03 sec 3.3).

        Sparse terminal reward alone gives PPO almost no gradient: an agent
        that does nothing and one that acts randomly both die around round
        13-14, so episode reward variance is ~1%.

        ``shaping_mode="potential"`` (default) uses potential-based shaping,
        ``F = gamma * phi(s') - phi(s)`` (Ng, Harada & Russell 1999). Because
        the per-round terms telescope, total shaping over an episode collapses
        to a boundary term, so it **cannot change which policy is optimal** --
        it only redistributes credit earlier in the episode.

        ``shaping_mode="bonus"`` is the earlier form: a standing per-round
        payment for holding a strong board. It is kept for comparison but is
        **not recommended** -- it was measured rewarding the agent for
        accruing board value rather than for winning. Over a 150k-step run
        episode reward rose 22% while average placement stayed flat, and 77%
        of that gain came from shaping rather than from placing better
        (doc 99 entry 6c.3).
        """
        if self.shaping_mode == "bonus":
            player = self.player
            hp_lost = max(hp_before - player.hp, 0)
            strength = sum(
                unit.champion.cost * unit.star_level for unit in player.board_units
            )
            reference = max(player.max_board_units * self._reference_unit_value, 1)
            board_term = self.board_reward_weight * min(strength / reference, 1.5)
            survival_term = self.survival_reward_weight * (
                1.0 - hp_lost / max(self.config.starting_hp, 1)
            )
            return board_term + survival_term

        # Potential-based. A terminal state has potential 0 by convention,
        # which is what makes the telescoping sum collapse cleanly.
        terminal = self.match.finished or not self.player.alive
        after = 0.0 if terminal else self._potential()
        shaped = self.shaping_gamma * after - self._last_potential
        self._last_potential = after
        return shaped

    def _terminal_reward(self) -> float:
        """Placement-based terminal reward, ``(9 - placement) / 8``."""
        assert self.match is not None
        if self.player.placement is None:
            self.match._finalise_placements()
        placement = self.player.placement or self.n_players
        return (self.n_players + 1 - placement) / self.n_players

    def _observe(self) -> np.ndarray:
        assert self.match is not None
        opponents = [
            p for p in self.match.players if p.player_id != self.agent_seat
        ]
        selected = self.executor.selected
        held = (
            self.executor.unit_at(self.player, selected) if selected is not None else None
        )
        return self.encoder.encode(
            self.player,
            self.match.round_id,
            opponents,
            self._board_hexes,
            actions_remaining=self.actions_left,
            max_actions=self.max_actions_per_round,
            selected_slot=selected,
            selected_unit=held,
        )

    def action_mask(self) -> np.ndarray:
        """Boolean mask of currently-legal actions (doc 03 sec 3.2).

        Exposed as a method so maskable-PPO wrappers can find it, and so a
        random policy can sample only legal actions.
        """
        if self.match is None or not self.player.alive:
            mask = np.zeros(self.action_space_helper.n, dtype=bool)
            mask[self.action_space_helper.end_index] = True
            return mask
        return np.array(self.executor.legal_mask(self.player), dtype=bool)

    def action_masks(self) -> np.ndarray:
        """Alias for :meth:`action_mask`.

        ``sb3_contrib``'s MaskablePPO discovers masks by calling a method with
        exactly this name, so the alias is what wires the mask into training.
        """
        return self.action_mask()

    def sample_legal_action(self, rng: random.Random | None = None) -> int:
        """Uniformly sample a legal action. The random-policy baseline."""
        mask = self.action_mask()
        legal = np.flatnonzero(mask)
        if len(legal) == 0:
            return self.action_space_helper.end_index
        chooser = rng or random
        return int(chooser.choice(list(legal)))

    def _info(self, action=None) -> dict:
        assert self.match is not None
        info = {
            "round": str(self.match.round_id),
            "hp": self.player.hp,
            "gold": self.player.gold,
            "level": self.player.level,
            "board_units": len(self.player.board),
            "alive_players": len(self.match.living_players),
            "action_mask": self.action_mask(),
        }
        if action is not None:
            info["action"] = repr(action)
        if self.match.finished or not self.player.alive:
            info["placement"] = self.player.placement
            info["episode_reward"] = self._episode_reward
        return info


def make_env(**kwargs) -> TFTEnv:
    """Factory for vectorised training runs."""
    return TFTEnv(**kwargs)


def rollout(env: TFTEnv, policy=None, seed: int | None = None) -> dict:
    """Play one episode, returning summary stats. Used by tests and scripts."""
    rng = random.Random(seed)
    obs, info = env.reset(seed=seed)
    total_reward = 0.0
    steps = 0
    terminated = False
    while not terminated:
        action = (
            policy(obs, env.action_mask()) if policy else env.sample_legal_action(rng)
        )
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        steps += 1
        if steps > 5000:
            raise RuntimeError("episode did not terminate within 5000 steps")
    return {
        "steps": steps,
        "reward": total_reward,
        "placement": info.get("placement"),
        "rounds": env.match.rounds_played if env.match else 0,
    }


__all__ = ["TFTEnv", "make_env", "rollout", "ActionKind", "IllegalAction"]
