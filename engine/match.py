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
from engine.augments import AugmentOffer
from engine.combat import CombatLog, CombatResult, CombatSimulator
from engine.economy import RoundId
from engine.hexgrid import Board, axial_to_offset
from engine.items import ItemRegistry
from engine.player import PlayerState
from engine.schema import CreepWave, GameData, RealmOffering
from engine.shop import SharedPool
from engine.unit import UnitInstance

log = logging.getLogger(__name__)


class Policy(Protocol):
    """What a seat must implement to play its planning phase."""

    def plan(self, player: PlayerState, context: "PlanningContext") -> None:
        """Take planning-phase actions. Exceptions propagate -- policies should
        use the ``can_*`` predicates rather than relying on caught errors."""

    # Three optional hooks, none required, so every existing policy keeps
    # working and simply takes the default:
    #   choose_augment(player, offers) -> int      -- augment reveal
    #   choose_component(player, offered) -> str   -- low-HP anvil pick
    #   choose_offering(player, offerings) -> int  -- realm-of-the-gods draft


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
        self.augment_offer = AugmentOffer(data)
        self.players = [
            PlayerState(data, self.registry, player_id=i) for i in range(structure.players)
        ]
        self.round_id = RoundId(1, 1)
        self.rounds_played = 0
        self.placements: dict[int, int] = {}
        self.reports: list[RoundReport] = []
        self._recent_opponents: dict[int, list[int]] = {i: [] for i in range(structure.players)}
        # Realm draft state: the shared line-up still on the table, and the
        # seats yet to pick from it, in HP order.
        self._realm_offerings: list[RealmOffering] = []
        self._realm_queue: list[int] = []

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
        if self.is_realm_round:
            self._realm_phase()
            self._planning_phase(is_pve=False)
            # A carousel round has no fight (doc 01 sec 1: 2-4/3-4/4-4 sit
            # between combats), so nobody takes damage and no streak moves --
            # but income is still paid.
            for player in self.living_players:
                player.award_income(self.round_id)
            self.rounds_played += 1
            self.round_id = self.round_id.next(
                self.structure.rounds_in_stage(self.round_id.stage)
            )
            return []

        is_pve = self.structure.is_pve(self.round_id.stage, self.round_id.round)
        self._planning_phase(is_pve)
        reports = self._combat_phase(is_pve)
        self._resolution_phase(reports)
        self.rounds_played += 1
        self.round_id = self.round_id.next(
            self.structure.rounds_in_stage(self.round_id.stage)
        )
        return reports

    # -- realm of the gods (the carousel draft) ---------------------------

    @property
    def is_realm_round(self) -> bool:
        return self.config.realm.is_realm_round(
            self.round_id.stage, self.round_id.round
        )

    def _realm_phase(self) -> bool:
        """Run the draft: lowest HP picks first, from one shared line-up.

        This is the only place in the engine where seats **contest** a shared
        resource in a fixed order -- every other planning action is independent
        per seat. An early picker genuinely denies a later one, which is what
        makes the HP ordering a comeback mechanic rather than a formality
        (doc 01 sec 1, doc 99 entry 21).

        Returns ``True`` if the draft paused waiting on an externally-driven
        seat (the RL env), which must then call :meth:`resume_realm`.
        """
        tier = self.config.realm.cost_tier_at(
            self.round_id.stage, self.round_id.round
        )
        if tier is None:
            return False
        order = sorted(self.living_players, key=lambda p: (p.hp, p.player_id))
        self._realm_offerings = self._generate_offerings(len(order), tier)
        self._realm_queue = [p.player_id for p in order]
        return self.resume_realm()

    def resume_realm(self) -> bool:
        """Advance the draft queue until it finishes or hits a deferring seat."""
        while self._realm_queue:
            player = self.players[self._realm_queue[0]]

            # Reconcile a pick already made by an externally-driven seat.
            if player.taken_offering is not None:
                self._remove_offering(player.taken_offering)
                player.taken_offering = None
                self._realm_queue.pop(0)
                continue

            if not player.alive or not self._realm_offerings:
                self._realm_queue.pop(0)
                player.realm_offer = ()
                continue

            player.offer_realm(self._realm_offerings)
            if getattr(self.policies[player.player_id], "defers_realm_pick", False):
                return True

            self._realm_queue.pop(0)
            index = self._ask_for_offering(player)
            player.pick_offering(index)
            self._remove_offering(player.taken_offering)
            player.taken_offering = None

        self._release_undrafted()
        return False

    def _release_undrafted(self) -> None:
        """Return the un-taken line-up to the shared pool.

        The draft always puts out more offerings than there are seats, so some
        are always left over. Without this they vanish from the pool for the
        rest of the game -- a leak the smoke test's pool-conservation invariant
        caught at exactly ``extra_offerings`` copies per realm round.
        """
        for offering in self._realm_offerings:
            self.pool.return_to_pool(offering.champion_id, 1)
        self._realm_offerings = []

    def _remove_offering(self, offering: "RealmOffering | None") -> None:
        if offering is not None and offering in self._realm_offerings:
            self._realm_offerings.remove(offering)

    def _generate_offerings(self, seats: int, tier: int) -> list["RealmOffering"]:
        """Draw the shared line-up: one champion per offering, each with a component.

        Champions come out of the **shared pool**, so a drafted unit is one
        fewer copy available in everyone's shop -- exactly as in TFT. Real
        carousels put one more champion out than there are players, so the last
        picker still gets a choice rather than a leftover.
        """
        count = seats + self.config.realm.extra_offerings
        components = tuple(sorted(i.id for i in self.registry.components))
        offerings: list[RealmOffering] = []
        for _ in range(count):
            champion_id = self.pool.draw(tier, self.rng)
            if champion_id is None:
                break
            offerings.append(
                RealmOffering(
                    champion_id=champion_id,
                    component_id=self.rng.choice(list(components)) if components else None,
                )
            )
        return offerings

    def _ask_for_offering(self, player: PlayerState) -> int:
        """Let the seat's policy choose, defaulting to the first offering."""
        chooser = getattr(self.policies[player.player_id], "choose_offering", None)
        if chooser is None:
            return 0
        try:
            index = int(chooser(player, tuple(player.realm_offer)))
        except (TypeError, ValueError) as exc:
            log.warning(
                "policy for player %d returned an unusable offering choice (%s); "
                "taking the first offering", player.player_id, exc,
            )
            return 0
        if not 0 <= index < len(player.realm_offer):
            log.warning(
                "policy for player %d chose offering %d of %d; taking the first",
                player.player_id, index, len(player.realm_offer),
            )
            return 0
        return index

    # -- phases -----------------------------------------------------------

    def _planning_phase(self, is_pve: bool) -> None:
        context = PlanningContext(self, self.round_id, self.pool, self.rng, is_pve)
        tier = self.config.augments.tier_at(self.round_id.stage, self.round_id.round)
        for player in self.living_players:
            if tier is not None:
                player.offer_augments(
                    self.augment_offer.offer(tier, self.rng, exclude=player.augments)
                )
            player.roll_shop(self.pool, self.rng)
            self.policies[player.player_id].plan(player, context)
            self._resolve_augment_pick(player)

    def _resolve_augment_pick(self, player: PlayerState) -> None:
        """Ensure a revealed augment is actually taken.

        Real TFT forces the choice -- there is no "decline". A policy that
        ignores the offer would otherwise silently fall behind every seat that
        picked, so an unanswered offer defaults to the first choice. Policies
        that *do* care implement ``choose_augment`` (see
        :meth:`_ask_for_augment`).
        """
        if not player.has_pending_augment:
            return
        # A seat driven from outside the match loop -- the RL env -- picks
        # through its own action space over several steps, so it must be left
        # holding the offer. It is responsible for resolving it before combat.
        if getattr(self.policies[player.player_id], "defers_augment_pick", False):
            return
        player.pick_augment(self._ask_for_augment(player))

    def _ask_for_augment(self, player: PlayerState) -> int:
        """Let the seat's policy choose, falling back to the first offer."""
        policy = self.policies[player.player_id]
        chooser = getattr(policy, "choose_augment", None)
        if chooser is None:
            return 0
        try:
            index = int(chooser(player, tuple(player.augment_offer)))
        except (TypeError, ValueError) as exc:
            log.warning(
                "policy for player %d returned an unusable augment choice (%s); "
                "defaulting to the first offer",
                player.player_id,
                exc,
            )
            return 0
        if not 0 <= index < len(player.augment_offer):
            log.warning(
                "policy for player %d chose augment %d of %d offered; "
                "defaulting to the first offer",
                player.player_id,
                index,
                len(player.augment_offer),
            )
            return 0
        return index

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
        """PvE round: a real fight against the round's creep wave.

        Doc 01 sec 1 permitted stubbing stage 1 as a fixed sequence, and that
        stub used to resolve *every* PvE round as a free win. Two consequences
        made it untenable: a weak board could never be punished (real TFT lets
        you lose to Krugs), and nothing ever dropped loot, which left the whole
        item system unreachable in a real game.

        With no ``creeps.json`` loaded the old free-win behaviour is kept, so a
        dataset without creep data still runs.
        """
        wave = self.data.wave_for(self.round_id.stage, self.round_id.round)
        if wave is None:
            return self._free_win(player)

        team0 = player.deploy_for_combat(0, self.board)
        team1 = self._deploy_creeps(wave)
        result = self._simulate(team0, team1)
        won = result.winner == 0

        damage = 0
        if not won:
            # Doc 01 sec 7: PvE loss damage is "smaller/fixed" rather than
            # scaled by surviving units, so the stage base is used directly
            # instead of economy.round_damage's per-survivor formula.
            damage = self.config.stage_base_damage.get(
                min(self.round_id.stage, max(self.config.stage_base_damage)), 0
            )
        taken = player.take_damage(damage)
        if won:
            self._award_loot(player, wave)

        return RoundReport(
            round_id=self.round_id,
            player_id=player.player_id,
            opponent_id=None,
            is_pve=True,
            won=won,
            damage_taken=taken,
            hp_after=player.hp,
            gold_after=player.gold,
            level_after=player.level,
            combat_duration=result.duration,
        )

    def _free_win(self, player: PlayerState) -> RoundReport:
        """The pre-creep-data behaviour: PvE is a walkover paying no loot."""
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

    def _deploy_creeps(self, wave: CreepWave) -> list[UnitInstance]:
        """Build the monster board for ``wave`` on team 1."""
        units: list[UnitInstance] = []
        for placement in wave.units:
            creep = self.data.creeps[placement.creep_id]
            unit = UnitInstance(creep, 1, registry=self.registry)
            unit.position = self.board.to_combat(1, placement.row, placement.col)
            unit.team = 1
            units.append(unit)
        return units

    def _award_loot(self, player: PlayerState, wave: CreepWave) -> None:
        """Pay out a beaten wave's drop (doc 01 sec 5).

        Components are drawn from the component pool. Lower-HP players get a
        *chosen* component rather than a random one -- Set 17's catch-up rule
        gives them component anvils on PvE rounds instead of random components
        (doc 99 entry 20.3). The choice is delegated to the seat's policy via
        an optional ``choose_component`` hook, defaulting to a random draw.
        """
        option = wave.pick_loot(self.rng)
        if option is None:
            return
        if option.gold:
            player.gold += option.gold
        if not option.components:
            return
        components = tuple(sorted(i.id for i in self.registry.components))
        if not components:
            return
        anvil = self._has_anvil_priority(player)
        for _ in range(option.components):
            player.add_item(self._pick_component(player, components, anvil))

    def _has_anvil_priority(self, player: PlayerState) -> bool:
        """Whether ``player`` is low enough in the standings to get anvils.

        Set 17's stated catch-up rule: players lower in the HP standings
        receive component anvils rather than random components. Modelled as
        the bottom half of living players, which is the same population the
        carousel's lowest-HP-first ordering favours.
        """
        living = sorted(self.living_players, key=lambda p: (p.hp, p.player_id))
        if len(living) < 2:
            return False
        cutoff = len(living) // 2
        return player.player_id in {p.player_id for p in living[:cutoff]}

    def _pick_component(
        self, player: PlayerState, components: Sequence[str], anvil: bool
    ) -> str:
        """A random component, or the policy's choice when it is an anvil."""
        if not anvil:
            return self.rng.choice(list(components))
        chooser = getattr(self.policies[player.player_id], "choose_component", None)
        if chooser is None:
            return self.rng.choice(list(components))
        try:
            chosen = chooser(player, tuple(components))
        except (TypeError, ValueError) as exc:
            log.warning(
                "policy for player %d returned an unusable component choice (%s); "
                "drawing at random", player.player_id, exc,
            )
            return self.rng.choice(list(components))
        if chosen not in components:
            log.warning(
                "policy for player %d chose component %r, which is not on offer; "
                "drawing at random", player.player_id, chosen,
            )
            return self.rng.choice(list(components))
        return chosen

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
        owner_bonuses = source.augment_bonuses()
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
            # A ghost is a copy of the *player*, augments included -- omitting
            # them would make ghost fights systematically easier than the real
            # board they are standing in for.
            clone.set_owner_bonuses(owner_bonuses)
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
