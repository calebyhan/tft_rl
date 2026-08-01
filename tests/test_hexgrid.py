"""Tests for engine.hexgrid (doc 01 sec 2, doc 03 sec 2.1)."""

from __future__ import annotations

import pytest

from engine.hexgrid import (
    BOARD_COLS,
    COMBAT_ROWS,
    HALF_ROWS,
    Board,
    Hex,
    axial_to_offset,
    distance,
    line,
    neighbors,
    offset_to_axial,
    ring,
    spread,
)

# --- coordinate math -----------------------------------------------------


def test_hex_is_hashable_and_value_equal():
    assert Hex(1, 2) == Hex(1, 2)
    assert len({Hex(1, 2), Hex(1, 2), Hex(2, 1)}) == 2


def test_cube_coordinates_sum_to_zero():
    for h in (Hex(0, 0), Hex(3, -1), Hex(-2, 5)):
        assert h.q + h.r + h.s == 0


def test_distance_to_self_is_zero():
    assert distance(Hex(4, -2), Hex(4, -2)) == 0


def test_all_six_neighbors_are_distance_one():
    center = Hex(2, 3)
    ns = neighbors(center)
    assert len(ns) == 6
    assert len(set(ns)) == 6
    assert all(distance(center, n) == 1 for n in ns)


def test_neighbor_order_is_stable():
    """Combat tie-breaks depend on iteration order, so it must not drift."""
    assert neighbors(Hex(0, 0)) == [
        Hex(1, 0),
        Hex(1, -1),
        Hex(0, -1),
        Hex(-1, 0),
        Hex(-1, 1),
        Hex(0, 1),
    ]


def test_distance_is_symmetric_and_triangle_inequality_holds():
    a, b, c = Hex(0, 0), Hex(3, -1), Hex(-2, 4)
    assert distance(a, b) == distance(b, a)
    assert distance(a, c) <= distance(a, b) + distance(b, c)


def test_distance_along_a_straight_axis():
    assert distance(Hex(0, 0), Hex(3, 0)) == 3
    assert distance(Hex(0, 0), Hex(0, -3)) == 3
    assert distance(Hex(0, 0), Hex(3, -3)) == 3
    # Off-axis: moving +q and +r partially cancels in cube space.
    assert distance(Hex(0, 0), Hex(2, 2)) == 4


def test_ring_size_and_membership():
    center = Hex(1, 1)
    for radius in (1, 2, 3):
        r = ring(center, radius)
        assert len(r) == 6 * radius
        assert len(set(r)) == 6 * radius
        assert all(distance(center, h) == radius for h in r)


def test_ring_radius_zero_is_just_the_center():
    assert ring(Hex(2, -1), 0) == [Hex(2, -1)]


def test_negative_radius_rejected():
    with pytest.raises(ValueError):
        ring(Hex(0, 0), -1)
    with pytest.raises(ValueError):
        spread(Hex(0, 0), -1)


def test_spread_is_the_union_of_all_rings():
    center = Hex(0, 0)
    radius = 3
    got = set(spread(center, radius))
    expected = {h for r in range(radius + 1) for h in ring(center, r)}
    assert got == expected
    # Hex-number formula: 1 + 3r(r+1)
    assert len(got) == 1 + 3 * radius * (radius + 1)


def test_line_endpoints_and_length():
    a, b = Hex(0, 0), Hex(3, -1)
    path = line(a, b)
    assert path[0] == a
    assert path[-1] == b
    assert len(path) == distance(a, b) + 1
    # Each step advances exactly one hex.
    assert all(distance(path[i], path[i + 1]) == 1 for i in range(len(path) - 1))


def test_line_to_self_is_single_hex():
    assert line(Hex(1, 1), Hex(1, 1)) == [Hex(1, 1)]


def test_offset_axial_round_trip():
    for row in range(COMBAT_ROWS):
        for col in range(BOARD_COLS):
            assert axial_to_offset(offset_to_axial(row, col)) == (row, col)


def test_offset_rows_are_staggered():
    """Odd rows sit half a hex right, so a unit is adjacent to two on the next row."""
    a = offset_to_axial(0, 3)
    below = {offset_to_axial(1, 2), offset_to_axial(1, 3)}
    assert below.issubset(set(neighbors(a)))


# --- board ---------------------------------------------------------------


@pytest.fixture
def board() -> Board:
    return Board()


def test_board_dimensions(board):
    assert len(board) == BOARD_COLS * COMBAT_ROWS == 56
    assert len(set(board.hexes)) == len(board)


def test_half_board_is_28_hexes_and_halves_are_disjoint(board):
    bottom = set(board.half_board_hexes(0))
    top = set(board.half_board_hexes(1))
    assert len(bottom) == len(top) == BOARD_COLS * HALF_ROWS == 28
    assert bottom.isdisjoint(top)
    assert bottom | top == set(board.hexes)


def test_front_rows_of_the_two_teams_are_adjacent(board):
    """Row 0 of each half-board must meet across the centre line."""
    for col in range(BOARD_COLS):
        friendly_front = board.to_combat(0, 0, col)
        assert friendly_front.r == HALF_ROWS
        # Some enemy front-row hex is adjacent to each friendly front-row hex.
        enemy_front = {board.to_combat(1, 0, c) for c in range(BOARD_COLS)}
        assert enemy_front & set(neighbors(friendly_front))


def test_team_one_half_is_mirrored(board):
    """Team 1's board is rotated 180 degrees, not merely translated."""
    # Columns are flipped: team 1's slot col 0 lands on battlefield col 6.
    assert axial_to_offset(board.to_combat(1, 0, 0))[1] == BOARD_COLS - 1
    assert axial_to_offset(board.to_combat(0, 0, 0))[1] == 0
    # Rows count away from the centre line in opposite directions.
    assert axial_to_offset(board.to_combat(1, 0, 0))[0] == HALF_ROWS - 1
    assert axial_to_offset(board.to_combat(1, 3, 0))[0] == 0
    assert axial_to_offset(board.to_combat(0, 3, 0))[0] == COMBAT_ROWS - 1


def test_back_rows_are_farther_apart_than_front_rows(board):
    front = distance(board.to_combat(0, 0, 3), board.to_combat(1, 0, 3))
    back = distance(board.to_combat(0, 3, 3), board.to_combat(1, 3, 3))
    assert back > front


def test_to_combat_rejects_out_of_range_slots(board):
    with pytest.raises(ValueError):
        board.to_combat(0, HALF_ROWS, 0)
    with pytest.raises(ValueError):
        board.to_combat(0, 0, BOARD_COLS)
    with pytest.raises(ValueError):
        board.to_combat(2, 0, 0)


def test_board_neighbors_are_clipped_to_the_grid(board):
    corner = offset_to_axial(0, 0)
    assert len(board.neighbors(corner)) < 6
    assert all(n in board for n in board.neighbors(corner))


# --- pathfinding ---------------------------------------------------------


def test_path_to_self_is_empty(board):
    assert board.find_path(offset_to_axial(0, 0), offset_to_axial(0, 0)) == []


def test_path_length_matches_hex_distance_when_unobstructed(board):
    start = board.to_combat(0, 3, 0)
    goal = board.to_combat(1, 3, 0)
    path = board.find_path(start, goal)
    assert path is not None
    assert len(path) == distance(start, goal)
    assert path[-1] == goal


def test_path_steps_are_contiguous_and_on_board(board):
    start = offset_to_axial(0, 0)
    goal = offset_to_axial(7, 6)
    path = board.find_path(start, goal)
    assert path is not None
    prev = start
    for step in path:
        assert step in board
        assert distance(prev, step) == 1
        prev = step


def test_path_routes_around_blockers(board):
    start = offset_to_axial(0, 3)
    goal = offset_to_axial(2, 3)
    blocked = [offset_to_axial(1, c) for c in range(BOARD_COLS) if c != 6]
    path = board.find_path(start, goal, blocked)
    assert path is not None
    assert not set(path) & set(blocked)
    # The detour through the one open column is longer than the direct route.
    assert len(path) > distance(start, goal)


def test_path_returns_none_when_fully_walled_off(board):
    start = offset_to_axial(0, 3)
    goal = offset_to_axial(2, 3)
    blocked = [offset_to_axial(1, c) for c in range(BOARD_COLS)]
    assert board.find_path(start, goal, blocked) is None


def test_goal_is_enterable_even_when_blocked(board):
    """A unit must be able to path *to* the hex its target stands on."""
    start = offset_to_axial(0, 0)
    goal = offset_to_axial(0, 3)
    path = board.find_path(start, goal, blocked=[goal])
    assert path is not None and path[-1] == goal


def test_next_step_toward_advances_one_hex_closer(board):
    start = offset_to_axial(7, 0)
    goal = offset_to_axial(0, 6)
    step = board.next_step_toward(start, goal)
    assert step is not None
    assert distance(step, goal) == distance(start, goal) - 1


def test_next_step_is_none_when_already_adjacent_to_a_blocking_target(board):
    """Standing next to an occupied target hex means there is nowhere to step."""
    start = offset_to_axial(3, 3)
    goal = neighbors(start)[0]
    assert board.next_step_toward(start, goal, blocked=[goal]) is None


def test_next_step_is_none_at_the_goal(board):
    h = offset_to_axial(2, 2)
    assert board.next_step_toward(h, h) is None


def test_pathfinding_rejects_off_board_coordinates(board):
    off_board = Hex(99, 99)
    with pytest.raises(ValueError):
        board.find_path(off_board, offset_to_axial(0, 0))
    with pytest.raises(ValueError):
        board.find_path(offset_to_axial(0, 0), off_board)


def test_pathfinding_is_deterministic(board):
    start, goal = offset_to_axial(7, 0), offset_to_axial(0, 6)
    blocked = [offset_to_axial(4, 2), offset_to_axial(3, 4)]
    first = board.find_path(start, goal, blocked)
    assert all(board.find_path(start, goal, blocked) == first for _ in range(5))
