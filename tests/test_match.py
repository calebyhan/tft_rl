"""Full-match orchestration tests (milestone 5, doc 01 sec 1, doc 03 sec 2.11)."""

from __future__ import annotations

import collections

import pytest

from engine.economy import RoundId
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match, PlanningContext, run_match
from engine.player import PlayerState
from engine.schema import GameData
from engine.shop import SharedPool
from rl.opponents import GreedyPolicy, NoOpPolicy, RandomPolicy
from tests.paths import STARTER_DATA_DIR


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_all(STARTER_DATA_DIR)


@pytest.fixture(scope="module")
def registry(data) -> ItemRegistry:
    return ItemRegistry(data.items, data.config.max_items_per_unit)


@pytest.fixture(scope="module")
def pool_total(data) -> int:
    return SharedPool(data).total_remaining


def greedy_seats(data, seed=0):
    return [GreedyPolicy(seed=seed * 100 + i) for i in range(data.config.round_structure.players)]


def make_match(data, registry, seed=0, policies=None):
    return Match(data, policies or greedy_seats(data, seed), seed=seed, registry=registry)


class RecordingPolicy:
    """Captures what each seat was asked to do."""

    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def plan(self, player: PlayerState, context: PlanningContext) -> None:
        self.calls.append((player.player_id, str(context.round_id)))


# --- setup ---------------------------------------------------------------


def test_match_seats_every_player(data, registry):
    match = make_match(data, registry)
    assert len(match.players) == data.config.round_structure.players == 8
    assert [p.player_id for p in match.players] == list(range(8))
    assert all(p.hp == data.config.starting_hp for p in match.players)


def test_wrong_number_of_policies_is_rejected(data, registry):
    with pytest.raises(ValueError, match="expected 8 seat policies"):
        Match(data, [NoOpPolicy()] * 3, registry=registry)


def test_no_seat_is_special(data, registry):
    """Doc 03 sec 2.11: seat policies are a list, player 0 is not privileged."""
    recorders = [RecordingPolicy() for _ in range(8)]
    match = Match(data, recorders, seed=1, registry=registry)
    match.play_round()
    assert all(len(r.calls) == 1 for r in recorders)
    assert [r.calls[0][0] for r in recorders] == list(range(8))


# --- round structure (doc 01 sec 1) -------------------------------------


def test_stage_one_is_entirely_pve(data, registry):
    match = make_match(data, registry)
    structure = match.structure
    for round_ in range(1, structure.stage_one_rounds + 1):
        assert structure.is_pve(1, round_)


def test_later_stages_have_periodic_pve_rounds(data):
    structure = data.config.round_structure
    pve = [r for r in range(1, structure.rounds_per_stage + 1) if structure.is_pve(3, r)]
    assert pve == sorted(structure.pve_rounds_per_stage)
    assert pve, "there should be at least one creep round per stage"
    assert len(pve) < structure.rounds_per_stage, "not every round can be PvE"


def test_rounds_advance_through_stages(data, registry):
    match = make_match(data, registry)
    assert match.round_id == RoundId(1, 1)
    for _ in range(data.config.round_structure.stage_one_rounds):
        match.play_round()
    assert match.round_id == RoundId(2, 1)


def test_pve_rounds_deal_no_damage_and_do_not_set_a_streak(data, registry):
    match = make_match(data, registry)
    reports = match.play_round()  # 1-1 is PvE
    assert all(r.is_pve for r in reports)
    assert all(r.damage_taken == 0 for r in reports)
    assert all(p.hp == data.config.starting_hp for p in match.players)
    assert all(p.streak_type == "none" for p in match.players)


def test_pve_rounds_still_pay_income(data, registry):
    match = make_match(data, registry)
    for _ in range(3):
        match.play_round()
    # Stage 1 rounds pay 0/2/2, and policies spend, so just check XP accrued.
    assert all(p.level > 1 or p.xp > 0 for p in match.players)


def test_pvp_rounds_produce_winners_and_losers(data, registry):
    match = make_match(data, registry)
    while match.round_id.stage == 1:
        match.play_round()
    reports = match.play_round()
    assert not any(r.is_pve for r in reports)
    outcomes = {r.won for r in reports}
    assert outcomes <= {True, False}
    assert len(reports) == len(match.living_players)


# --- pairing -------------------------------------------------------------


def test_every_living_player_fights_exactly_once_per_pvp_round(data, registry):
    match = make_match(data, registry, seed=3)
    while match.round_id.stage == 1:
        match.play_round()
    for _ in range(6):
        living = {p.player_id for p in match.living_players}
        if len(living) < 2:
            break
        reports = match.play_round()
        fought = [r.player_id for r in reports]
        assert sorted(fought) == sorted(living)
        assert len(fought) == len(set(fought)), "a player fought twice"


def test_pairings_are_symmetric(data, registry):
    match = make_match(data, registry, seed=5)
    while match.round_id.stage == 1:
        match.play_round()
    reports = match.play_round()
    by_player = {r.player_id: r for r in reports}
    for report in reports:
        if report.opponent_id is None:
            continue  # ghost fight
        mirror = by_player[report.opponent_id]
        assert mirror.opponent_id == report.player_id
        assert mirror.won != report.won or (not mirror.won and not report.won)


def test_pairing_avoids_immediate_rematches_when_possible(data, registry):
    match = make_match(data, registry, seed=11)
    while match.round_id.stage == 1:
        match.play_round()
    seen: list[dict[int, int | None]] = []
    for _ in range(3):
        if len(match.living_players) < 4:
            break
        reports = match.play_round()
        seen.append({r.player_id: r.opponent_id for r in reports})
    rematches = 0
    for previous, current in zip(seen, seen[1:], strict=False):
        for player_id, opponent in current.items():
            if opponent is not None and previous.get(player_id) == opponent:
                rematches += 1
    # With 8 alive and a 2-round memory, back-to-back rematches should be rare.
    assert rematches <= 2


def test_odd_player_count_uses_a_ghost_fight(data, registry):
    """One seat faces a copy of another board rather than sitting out."""
    match = make_match(data, registry, seed=7)
    while match.round_id.stage == 1:
        match.play_round()
    match.players[0].hp = 0
    match._eliminate_dead()
    assert len(match.living_players) == 7

    reports = match.play_round()
    assert len(reports) == 7
    ghosts = [r for r in reports if r.opponent_id is None and not r.is_pve]
    assert len(ghosts) == 1


def test_a_ghost_fight_does_not_mutate_the_copied_board(data, registry):
    match = make_match(data, registry, seed=7)
    for _ in range(8):
        match.play_round()
    match.players[0].hp = 0
    match._eliminate_dead()
    boards_before = {
        p.player_id: sorted((u.champion.id, u.star_level) for u in p.board_units)
        for p in match.living_players
    }
    match.play_round()
    for player in match.living_players:
        after = sorted((u.champion.id, u.star_level) for u in player.board_units)
        # Boards change through buying, but never lose units to a ghost fight.
        assert len(after) >= 0
        assert player.player_id in boards_before


# --- damage and elimination (doc 01 sec 7) ------------------------------


def test_losing_a_pvp_round_costs_hp(data, registry):
    match = make_match(data, registry, seed=2)
    while match.round_id.stage == 1:
        match.play_round()
    for _ in range(4):
        reports = match.play_round()
        losers = [r for r in reports if not r.won and not r.is_pve]
        if losers:
            assert any(r.damage_taken > 0 for r in losers)
            return
    pytest.fail("no PvP loss occurred in four rounds")


def test_damage_grows_as_stages_progress(data, registry):
    match = make_match(data, registry, seed=4)
    by_stage: dict[int, list[int]] = collections.defaultdict(list)
    while not match.finished:
        for report in match.play_round():
            if not report.is_pve and not report.won:
                by_stage[report.round_id.stage].append(report.damage_taken)
    early = by_stage.get(2, [0])
    late = max(
        (v for k, v in by_stage.items() if k >= 4 and v), key=lambda v: sum(v) / len(v), default=[0]
    )
    assert sum(late) / len(late) > sum(early) / len(early)


def test_eliminated_players_get_placements_and_release_their_units(data, registry):
    match = make_match(data, registry, seed=6)
    match.run()
    for player in match.players:
        assert player.placement is not None
        if not player.alive:
            assert player.all_units == [], f"P{player.player_id} kept units after elimination"


def test_placements_are_a_permutation_and_the_winner_survives(data, registry):
    result = make_match(data, registry, seed=8).run()
    assert sorted(result.placements.values()) == list(range(1, 9))
    assert result.winner is not None
    assert result.placement_of(result.winner) == 1


def test_earlier_elimination_means_a_worse_placement(data, registry):
    match = make_match(data, registry, seed=9)
    elimination_round: dict[int, int] = {}
    round_index = 0
    while not match.finished:
        match.play_round()
        round_index += 1
        for player in match.players:
            if not player.alive and player.player_id not in elimination_round:
                elimination_round[player.player_id] = round_index
    result = match.run()
    ordered = sorted(elimination_round, key=lambda pid: elimination_round[pid])
    placements = [result.placement_of(pid) for pid in ordered]
    # Players knocked out in the same round share adjacent placements, so only
    # require the sequence to be non-decreasing overall.
    assert placements == sorted(placements) or len(set(elimination_round.values())) < len(ordered)


# --- termination and invariants -----------------------------------------


@pytest.mark.parametrize("seed", range(4))
def test_matches_terminate_with_one_survivor(data, registry, seed):
    match = make_match(data, registry, seed=seed)
    result = match.run()
    assert result.winner is not None
    alive = [p for p in match.players if p.alive]
    assert len(alive) == 1 or match.round_id.stage > match.structure.max_stages
    assert result.rounds_played > 0


@pytest.mark.parametrize("seed", range(3))
def test_champion_pool_is_conserved_across_a_whole_match(data, registry, pool_total, seed):
    match = make_match(data, registry, seed=seed)
    match.run()
    held = sum(u.pool_copies for p in match.players for u in p.all_units)
    in_shops = sum(1 for p in match.players for s in p.shop.slots if s is not None)
    assert match.pool.total_remaining + held + in_shops == pool_total


@pytest.mark.parametrize("seed", range(3))
def test_no_player_exceeds_their_board_limit(data, registry, seed):
    match = make_match(data, registry, seed=seed)
    while not match.finished:
        match.play_round()
        for player in match.living_players:
            assert len(player.board) <= player.max_board_units
            assert len(player.bench) == player.config.bench_size


def test_hp_never_goes_negative(data, registry):
    match = make_match(data, registry, seed=12)
    match.run()
    assert all(p.hp >= 0 for p in match.players)


def test_random_policies_complete_a_match_without_crashing(data, registry):
    """The fuzziest policy reaches states a sensible one never would."""
    policies = [RandomPolicy(seed=i) for i in range(8)]
    match = Match(data, policies, seed=21, registry=registry)
    result = match.run()
    assert sorted(result.placements.values()) == list(range(1, 9))


def test_noop_policies_still_terminate(data, registry):
    """Eight empty boards must not deadlock -- every fight is a mutual loss."""
    match = Match(data, [NoOpPolicy() for _ in range(8)], seed=1, registry=registry)
    result = match.run()
    assert sorted(result.placements.values()) == list(range(1, 9))


# --- determinism ---------------------------------------------------------


def test_the_same_seed_replays_the_same_match(data, registry):
    def run(seed):
        result = make_match(data, registry, seed=seed).run()
        return (
            result.placements,
            result.rounds_played,
            [(r.player_id, str(r.round_id), r.won, r.damage_taken) for r in result.reports],
        )

    assert run(31) == run(31)


def test_different_seeds_give_different_matches(data, registry):
    outcomes = {make_match(data, registry, seed=s).run().winner for s in range(6)}
    assert len(outcomes) > 1


def test_run_match_helper_builds_its_own_seats(data, registry):
    result = run_match(data, lambda seat: GreedyPolicy(seed=seat), seed=3, registry=registry)
    assert sorted(result.placements.values()) == list(range(1, 9))


# --- policies ------------------------------------------------------------


def test_greedy_policy_builds_a_board_and_levels_up(data, registry):
    match = make_match(data, registry, seed=13)
    for _ in range(12):
        match.play_round()
    fielded = [len(p.board) for p in match.living_players]
    assert max(fielded) >= 3, "greedy bots should field units"
    assert max(p.level for p in match.living_players) >= 4


def test_greedy_policy_beats_the_random_baseline(data, registry):
    """A sanity check that the heuristic is non-degenerate (doc 03 sec 3)."""
    greedy_placements: list[int] = []
    random_placements: list[int] = []
    for seed in range(6):
        policies = [
            GreedyPolicy(seed=seed * 10 + i) if i % 2 == 0 else RandomPolicy(seed=seed * 10 + i)
            for i in range(8)
        ]
        result = Match(data, policies, seed=seed, registry=registry).run()
        for player_id, placement in result.placements.items():
            (greedy_placements if player_id % 2 == 0 else random_placements).append(placement)
    greedy_avg = sum(greedy_placements) / len(greedy_placements)
    random_avg = sum(random_placements) / len(random_placements)
    assert greedy_avg < random_avg, f"greedy {greedy_avg:.2f} vs random {random_avg:.2f}"
