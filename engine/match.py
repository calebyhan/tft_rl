"""Orchestrates 8 players through a full game (doc 01 sec 1, doc 03 sec 2.11).

Each round runs: planning phase (every seat's policy acts) -> pairing ->
combat -> damage and elimination. Seat behaviour is supplied as a list of
policies, so the same class serves "all 8 seats scripted" (self-play training)
and "seat 0 is the agent, 7 are bots" (evaluation) without special-casing
player 0.

Stage 1 is PvE; later stages are PvP with periodic creep rounds, per
``config.round_structure``. All randomness comes from a seeded
``random.Random`` so a whole match replays from its seed.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

from engine import economy
from engine.combat import CombatLog, CombatResult, CombatSimulator
from engine.economy import RoundId
from engine.hexgrid import Board, axial_to_offset
from engine.items import ItemRegistry
from engine.player import PlayerState
from engine.schema import GameData
from engine.shop import SharedPool
from engine.unit import UnitInstance

log = logging.getLogger(__name__)


class Policy(Protocol):
    """What a seat must implement to play its planning phase."""

    def plan(self, player: PlayerState, context: "PlanningContext") -> None:
        """Take planning-phase actions. Exceptions propagate -- policies should
        use the ``can_*`` predicates rather than relying on caught errors."""


@dataclass
class PlanningContext:
    """Everything a policy is allowed to see during its planning phase."""

    match: "Match"
    round_id: RoundId
    pool: SharedPool
    rng: random.Random
    is_pve: bool

    @property
    def data(self) -> GameData:
        return self.match.data

    def opponents(self, player: PlayerState) -> list[PlayerState]:
        """Public info on other seats (HP/level/streak only, per doc 03 sec 3.1)."""
        return [p for p in self.match.living_players if p.player_id != player.player_id]


@dataclass
class RoundReport:
    """What happened to one player in one round."""

    round_id: RoundId
    player_id: int
    opponent_id: int | None
    is_pve: bool
    won: bool
    damage_taken: int
    hp_after: int
    gold_after: int
    level_after: int
    combat_duration: float


@dataclass
class MatchResult:
    placements: dict[int, int]
    rounds_played: int
    final_round: RoundId
    reports: list[RoundReport] = field(default_factory=list)

    @property
    def winner(self) -> int | None:
        for player_id, placement in self.placements.items():
            if placement == 1:
                return player_id
        return None

    def placement_of(self, player_id: int) -> int:
        return self.placements[player_id]


class Match:
    """One full game."""

    def __init__(
        self,
        data: GameData,
        policies: Sequence[Policy],
        *,
        seed: int = 0,
        registry: ItemRegistry | None = None,
    ) -> None:
        structure = data.config.round_structure
        if len(policies) != structure.players:
            raise ValueError(
                f"expected {structure.players} seat policies, got {len(policies)}"
            )
        self.data = data
        self.config = data.config
        self.structure = structure
        self.policies = list(policies)
        self.rng = random.Random(seed)
        self.seed = seed
        self.registry = registry or ItemRegistry(data.items, self.config.max_items_per_unit)
        self.board = Board()
        self.pool = SharedPool(data)
        self.players = [
            PlayerState(data, self.registry, player_id=i) for i in range(structure.players)
        ]
        self.round_id = RoundId(1, 1)
        self.rounds_played = 0
        self.placements: dict[int, int] = {}
        self.reports: list[RoundReport] = []
        self._recent_opponents: dict[int, list[int]] = {i: [] for i in range(structure.players)}

    # -- state ------------------------------------------------------------

    @property
    def living_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.alive]

    @property
    def finished(self) -> bool:
        return len(self.living_players) <= 1 or self.round_id.stage > self.structure.max_stages

    # -- driving ----------------------------------------------------------

    def run(self) -> MatchResult:
        """Play until one player remains or the stage cap is reached."""
        while not self.finished:
            self.play_round()
        self._finalise_placements()
        return MatchResult(
            placements=dict(self.placements),
            rounds_played=self.rounds_played,
            final_round=self.round_id,
            reports=list(self.reports),
        )

    def play_round(self) -> list[RoundReport]:
        is_pve = self.structure.is_pve(self.round_id.stage, self.round_id.round)
        self._planning_phase(is_pve)
        reports = self._combat_phase(is_pve)
        self._resolution_phase(reports)
        self.rounds_played += 1
        self.round_id = self.round_id.next(
            self.structure.rounds_in_stage(self.round_id.stage)
        )
        return reports

    # -- phases -----------------------------------------------------------

    def _planning_phase(self, is_pve: bool) -> None:
        context = PlanningContext(self, self.round_id, self.pool, self.rng, is_pve)
        for player in self.living_players:
            player.roll_shop(self.pool, self.rng)
            self.policies[player.player_id].plan(player, context)

    def _combat_phase(self, is_pve: bool) -> list[RoundReport]:
        if is_pve:
            return [self._fight_creeps(p) for p in self.living_players]
        return self._fight_pvp()

    def _resolution_phase(self, reports: Sequence[RoundReport]) -> None:
        for report in reports:
            player = self.players[report.player_id]
            if not report.is_pve:
                player.record_result(report.won)
            player.award_income(self.round_id, won_pvp=report.won and not report.is_pve)
        self.reports.extend(reports)
        self._eliminate_dead()

    # -- pairing ----------------------------------------------------------

    def _pair_players(self) -> list[tuple[PlayerState, PlayerState | None]]:
        """Pair living players, preferring opponents not recently faced.

        With an odd number of players one seat faces a *ghost* -- a copy of
        another player's board, as in TFT -- represented by a ``None`` partner
        that :meth:`_fight_pvp` fills in.
        """
        players = list(self.living_players)
        self.rng.shuffle(players)
        pairs: list[tuple[PlayerState, PlayerState | None]] = []
        unpaired = list(players)

        while len(unpaired) >= 2:
            player = unpaired.pop(0)
            recent = self._recent_opponents[player.player_id]
            fresh = [p for p in unpaired if p.player_id not in recent]
            opponent = fresh[0] if fresh else unpaired[0]
            unpaired.remove(opponent)
            pairs.append((player, opponent))

        if unpaired:
            pairs.append((unpaired[0], None))
        return pairs

    def _remember_pairing(self, a: int, b: int, keep: int = 2) -> None:
        for owner, other in ((a, b), (b, a)):
            history = self._recent_opponents[owner]
            history.append(other)
            del history[:-keep]

    # -- fights -----------------------------------------------------------

    def _fight_pvp(self) -> list[RoundReport]:
        reports: list[RoundReport] = []
        for player, opponent in self._pair_players():
            if opponent is None:
                reports.append(self._fight_ghost(player))
                continue
            self._remember_pairing(player.player_id, opponent.player_id)
            reports.extend(self._resolve_fight(player, opponent))
        return reports

    def _resolve_fight(
        self, player: PlayerState, opponent: PlayerState
    ) -> list[RoundReport]:
        team0 = player.deploy_for_combat(0, self.board)
        team1 = opponent.deploy_for_combat(1, self.board)
        result = self._simulate(team0, team1)

        winner_side = result.winner
        reports = []
        for side, (me, foe) in enumerate(((player, opponent), (opponent, player))):
            won = winner_side == side
            damage = 0
            if winner_side is not None and not won:
                damage = self._damage_from(result, winner_side)
            elif winner_side is None:
                damage = self.config.stage_base_damage.get(
                    min(self.round_id.stage, max(self.config.stage_base_damage)), 0
                )
            taken = me.take_damage(damage)
            reports.append(
                RoundReport(
                    round_id=self.round_id,
                    player_id=me.player_id,
                    opponent_id=foe.player_id,
                    is_pve=False,
                    won=won,
                    damage_taken=taken,
                    hp_after=me.hp,
                    gold_after=me.gold,
                    level_after=me.level,
                    combat_duration=result.duration,
                )
            )
        return reports

    def _fight_ghost(self, player: PlayerState) -> RoundReport:
        """Fight a copy of another living player's board (odd-player-count bye)."""
        others = [p for p in self.living_players if p.player_id != player.player_id]
        if not others:
            return RoundReport(
                self.round_id, player.player_id, None, False, True, 0,
                player.hp, player.gold, player.level, 0.0,
            )
        source = self.rng.choice(others)
        team0 = player.deploy_for_combat(0, self.board)
        team1 = self._clone_board(source, team=1)
        result = self._simulate(team0, team1)

        won = result.winner == 0
        damage = self._damage_from(result, 1) if result.winner == 1 else 0
        taken = player.take_damage(damage)
        return RoundReport(
            round_id=self.round_id,
            player_id=player.player_id,
            opponent_id=None,
            is_pve=False,
            won=won,
            damage_taken=taken,
            hp_after=player.hp,
            gold_after=player.gold,
            level_after=player.level,
            combat_duration=result.duration,
        )

    def _fight_creeps(self, player: PlayerState) -> RoundReport:
        """PvE round.

        Doc 01 sec 1 treats stage 1 as a stubbable fixed sequence; creep boards
        are not part of the champion data, so v1 resolves PvE as a free win
        that still pays income and grants no streak. Real creep boards slot in
        here without touching anything else.
        """
        return RoundReport(
            round_id=self.round_id,
            player_id=player.player_id,
            opponent_id=None,
            is_pve=True,
            won=True,
            damage_taken=0,
            hp_after=player.hp,
            gold_after=player.gold,
            level_after=player.level,
            combat_duration=0.0,
        )

    def _simulate(
        self, team0: list[UnitInstance], team1: list[UnitInstance]
    ) -> CombatResult:
        if not team0 and not team1:
            return _empty_result()
        sim = CombatSimulator(
            team0, team1, self.data, seed=self.rng.randrange(2**31), board=self.board
        )
        return sim.run()

    def _damage_from(self, result: CombatResult, winner_side: int) -> int:
        survivors = [
            (u.champion.cost, u.star_level)
            for u in result.survivors
            if u.team == winner_side
        ]
        return economy.round_damage(self.config, self.round_id, survivors)

    def _clone_board(self, source: PlayerState, team: int) -> list[UnitInstance]:
        """Copy a player's fielded board so a ghost fight cannot touch the original.

        Positions are derived from the source's own-frame hexes directly rather
        than by calling ``deploy_for_combat``, which would move the real units.
        """
        clones: list[UnitInstance] = []
        for own_hex in sorted(source.board):
            original = source.board[own_hex]
            clone = UnitInstance(
                original.champion,
                original.star_level,
                original.items,
                registry=self.registry,
            )
            row, col = axial_to_offset(own_hex)
            clone.position = self.board.to_combat(team, row - self.board.half_rows, col)
            clone.team = team
            clones.append(clone)
        return clones

    # -- elimination ------------------------------------------------------

    def _eliminate_dead(self) -> None:
        newly_dead = [
            p for p in self.players if not p.alive and p.placement is None
        ]
        if not newly_dead:
            return
        # Everyone knocked out this round shares the next placements down; ties
        # break by remaining HP (all zero here) then seat, deterministically.
        remaining = len([p for p in self.players if p.placement is None])
        newly_dead.sort(key=lambda p: p.player_id)
        for offset, player in enumerate(newly_dead):
            placement = remaining - offset
            player.placement = placement
            self.placements[player.player_id] = placement
            player.release_all_to_pool(self.pool)
            log.debug("player %d eliminated in %s at placement %d",
                      player.player_id, self.round_id, placement)

    def _finalise_placements(self) -> None:
        survivors = [p for p in self.players if p.placement is None]
        # Highest HP first; seat id breaks ties so results stay reproducible.
        survivors.sort(key=lambda p: (-p.hp, p.player_id))
        for offset, player in enumerate(survivors):
            player.placement = offset + 1
            self.placements[player.player_id] = player.placement

    def __repr__(self) -> str:
        return f"<Match round={self.round_id} alive={len(self.living_players)}>"


def _empty_result() -> CombatResult:
    """Result of a fight where neither side fielded anything."""
    return CombatResult(
        winner=None, survivors=(), duration=0.0, ticks=0,
        log=CombatLog(), timed_out=False,
    )


# --- convenience ---------------------------------------------------------


def run_match(
    data: GameData,
    policy_factory: Callable[[int], Policy],
    *,
    seed: int = 0,
    registry: ItemRegistry | None = None,
) -> MatchResult:
    """Build 8 seats from ``policy_factory(seat_index)`` and play a full game."""
    structure = data.config.round_structure
    policies = [policy_factory(i) for i in range(structure.players)]
    return Match(data, policies, seed=seed, registry=registry).run()
