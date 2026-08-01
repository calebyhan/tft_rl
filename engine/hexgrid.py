"""Hex coordinate math, board geometry, and pathfinding.

Coordinates are axial ``(q, r)`` per doc 01 sec 2. Board layout uses an
``odd-r`` offset grid (pointy-top hexes, odd rows shifted half a hex right),
which matches TFT's alternating-row visual layout; ``Board`` converts between
the human-facing ``(row, col)`` offset form and axial for the actual math.

Row 0 of a player's half-board is the **front** row (closest to the enemy).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Iterator

# Standard TFT geometry (doc 01 sec 2). These are board-layout constants, not
# set-specific balance data, so they live here rather than in config.json.
BOARD_COLS = 7
HALF_ROWS = 4
COMBAT_ROWS = HALF_ROWS * 2


@dataclass(frozen=True, order=True)
class Hex:
    """An axial hex coordinate."""

    q: int
    r: int

    @property
    def s(self) -> int:
        """The third cube coordinate, implied by ``q + r + s == 0``."""
        return -self.q - self.r

    def __add__(self, other: "Hex") -> "Hex":
        return Hex(self.q + other.q, self.r + other.r)

    def __sub__(self, other: "Hex") -> "Hex":
        return Hex(self.q - other.q, self.r - other.r)

    def __repr__(self) -> str:  # keeps combat logs readable
        return f"Hex({self.q},{self.r})"


# Fixed neighbour ordering. Combat tie-breaks resolve by iteration order, so
# this sequence must stay stable for runs to be reproducible.
HEX_DIRECTIONS: tuple[Hex, ...] = (
    Hex(+1, 0),
    Hex(+1, -1),
    Hex(0, -1),
    Hex(-1, 0),
    Hex(-1, +1),
    Hex(0, +1),
)


def distance(a: Hex, b: Hex) -> int:
    """Hex distance between two axial coordinates."""
    dq = a.q - b.q
    dr = a.r - b.r
    return (abs(dq) + abs(dq + dr) + abs(dr)) // 2


def neighbors(h: Hex) -> list[Hex]:
    """The 6 hexes adjacent to ``h``, in fixed ``HEX_DIRECTIONS`` order."""
    return [h + d for d in HEX_DIRECTIONS]


def ring(center: Hex, radius: int) -> list[Hex]:
    """Hexes at exactly ``radius`` from ``center`` (clockwise from one corner)."""
    if radius < 0:
        raise ValueError(f"radius must be >= 0, got {radius}")
    if radius == 0:
        return [center]

    results: list[Hex] = []
    # Walk to a corner of the ring, then trace each of the 6 edges.
    current = center + Hex(
        HEX_DIRECTIONS[4].q * radius, HEX_DIRECTIONS[4].r * radius
    )
    for direction in HEX_DIRECTIONS:
        for _ in range(radius):
            results.append(current)
            current = current + direction
    return results


def spread(center: Hex, radius: int) -> list[Hex]:
    """All hexes within ``radius`` of ``center``, including ``center`` itself."""
    if radius < 0:
        raise ValueError(f"radius must be >= 0, got {radius}")
    results: list[Hex] = []
    for q in range(-radius, radius + 1):
        r_min = max(-radius, -q - radius)
        r_max = min(radius, -q + radius)
        for r in range(r_min, r_max + 1):
            results.append(Hex(center.q + q, center.r + r))
    return results


def _cube_round(q: float, r: float) -> Hex:
    """Round fractional cube coordinates to the nearest valid hex."""
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return Hex(int(rq), int(rr))


def line(a: Hex, b: Hex) -> list[Hex]:
    """Hexes along the straight line from ``a`` to ``b``, inclusive.

    Used for line-shaped abilities. The epsilon nudge keeps results
    deterministic when the line passes exactly along a hex edge.
    """
    n = distance(a, b)
    if n == 0:
        return [a]
    results: list[Hex] = []
    for i in range(n + 1):
        t = i / n
        results.append(
            _cube_round(
                a.q + (b.q - a.q) * t + 1e-6,
                a.r + (b.r - a.r) * t + 2e-6,
            )
        )
    return results


def offset_to_axial(row: int, col: int) -> Hex:
    """Convert an ``odd-r`` offset ``(row, col)`` to axial coordinates."""
    return Hex(col - ((row - (row & 1)) // 2), row)


def axial_to_offset(h: Hex) -> tuple[int, int]:
    """Convert axial coordinates back to ``odd-r`` offset ``(row, col)``."""
    row = h.r
    col = h.q + ((row - (row & 1)) // 2)
    return row, col


class Board:
    """The 7-wide x 8-row combat battlefield and its two 4-row half-boards.

    Team 0 sits on the bottom half (combat rows 4-7), team 1 on the top half
    (rows 0-3). A planning-phase position is given as ``(row, col)`` with
    row 0 = front row; :meth:`to_combat` maps it onto the shared battlefield,
    mirroring team 1's half 180 degrees so the two front rows face each other.
    """

    def __init__(self, cols: int = BOARD_COLS, half_rows: int = HALF_ROWS) -> None:
        if cols < 1 or half_rows < 1:
            raise ValueError("cols and half_rows must both be >= 1")
        self.cols = cols
        self.half_rows = half_rows
        self.rows = half_rows * 2
        self._hexes: tuple[Hex, ...] = tuple(
            offset_to_axial(row, col)
            for row in range(self.rows)
            for col in range(self.cols)
        )
        self._hex_set: frozenset[Hex] = frozenset(self._hexes)

    # -- geometry ---------------------------------------------------------

    @property
    def hexes(self) -> tuple[Hex, ...]:
        """Every valid battlefield hex, in row-major order."""
        return self._hexes

    def __contains__(self, h: object) -> bool:
        return h in self._hex_set

    def __iter__(self) -> Iterator[Hex]:
        return iter(self._hexes)

    def __len__(self) -> int:
        return len(self._hexes)

    def half_board_hexes(self, team: int) -> tuple[Hex, ...]:
        """The battlefield hexes belonging to ``team`` (0 = bottom, 1 = top)."""
        self._check_team(team)
        rows = (
            range(self.half_rows, self.rows)
            if team == 0
            else range(self.half_rows)
        )
        return tuple(
            offset_to_axial(row, col) for row in rows for col in range(self.cols)
        )

    def to_combat(self, team: int, row: int, col: int) -> Hex:
        """Map a planning-phase ``(row, col)`` slot to a battlefield hex.

        ``row`` is 0-indexed from the player's own front line.
        """
        self._check_team(team)
        if not (0 <= row < self.half_rows and 0 <= col < self.cols):
            raise ValueError(
                f"slot (row={row}, col={col}) is outside the "
                f"{self.cols}x{self.half_rows} half-board"
            )
        if team == 0:
            return offset_to_axial(self.half_rows + row, col)
        # Team 1 is rotated 180 degrees: rows count back from the centre line
        # and columns are mirrored.
        return offset_to_axial(self.half_rows - 1 - row, self.cols - 1 - col)

    def neighbors(self, h: Hex) -> list[Hex]:
        """Neighbours of ``h`` that are on the battlefield."""
        return [n for n in neighbors(h) if n in self._hex_set]

    def _check_team(self, team: int) -> None:
        if team not in (0, 1):
            raise ValueError(f"team must be 0 or 1, got {team}")

    # -- pathfinding ------------------------------------------------------

    def find_path(
        self, start: Hex, goal: Hex, blocked: Iterable[Hex] = ()
    ) -> list[Hex] | None:
        """Shortest path from ``start`` to ``goal``, or ``None`` if unreachable.

        The returned list excludes ``start`` and ends with ``goal``. ``goal``
        itself is always treated as enterable even when listed in ``blocked``,
        so a unit can path toward the hex its target occupies and stop once in
        range. BFS over a fixed neighbour ordering makes ties deterministic.
        """
        if start not in self._hex_set:
            raise ValueError(f"start {start} is not on the board")
        if goal not in self._hex_set:
            raise ValueError(f"goal {goal} is not on the board")
        if start == goal:
            return []

        blocked_set = set(blocked)
        blocked_set.discard(goal)
        blocked_set.discard(start)

        came_from: dict[Hex, Hex] = {start: start}
        queue: deque[Hex] = deque([start])
        while queue:
            current = queue.popleft()
            for nxt in self.neighbors(current):
                if nxt in came_from or nxt in blocked_set:
                    continue
                came_from[nxt] = current
                if nxt == goal:
                    return self._reconstruct(came_from, start, goal)
                queue.append(nxt)
        return None

    def next_step_toward(
        self, start: Hex, goal: Hex, blocked: Iterable[Hex] = ()
    ) -> Hex | None:
        """The single hex to move into this step, or ``None`` if stuck.

        Returns ``None`` when ``start == goal``, when no path exists, or when
        the only path step is into ``goal`` itself while ``goal`` is blocked
        (i.e. the unit is already adjacent to a blocking target).
        """
        path = self.find_path(start, goal, blocked)
        if not path:
            return None
        step = path[0]
        if step == goal and goal in set(blocked):
            return None
        return step

    @staticmethod
    def _reconstruct(
        came_from: dict[Hex, Hex], start: Hex, goal: Hex
    ) -> list[Hex]:
        path: list[Hex] = []
        current = goal
        while current != start:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path
