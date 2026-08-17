"""`ObservedState` -> ranked, legal, human-readable recommendations (doc 04 m3).

Pure compute and read-only: this suggests moves to a person, it does not make
them. Doc 04 sec 0 -- nothing here synthesises input into a client.

Two seams make this possible without a running simulation, and they are why the
bridge is an adapter rather than a rewrite (entry 131.2):

* `ObservationEncoder.encode` takes `(player, round_id, opponents, board_hexes)`
  and no `Match`.
* `ActionExecutor.legal_mask` takes a `PlayerState` and no `Match`.

So a recommendation is always **legal by construction** -- it comes from the
engine's own mask rather than from a re-implementation of the rules. Doc 03
sec 2.10's discipline applies here too: if the mask and the executor ever
disagree, the mask is the bug.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bridge.adapter import to_player_state
from bridge.state import ObservedState
from engine.hexgrid import Board
from rl.action import ActionExecutor, ActionKind, ActionSpace
from rl.observation import ObservationEncoder


@dataclass(frozen=True)
class Recommendation:
    """One suggested action, ranked."""

    index: int
    kind: str
    detail: str
    probability: float

    def __str__(self) -> str:
        return f"{self.kind:<14}{self.detail:<34}{self.probability:6.1%}"


class Advisor:
    """Turns an observation into ranked advice for a human to act on."""

    def __init__(self, data, model=None, env_options: dict | None = None):
        self.data = data
        self.model = model
        options = dict(env_options or {})
        # `Board()` directly, not via a `Match`: the whole claim of this
        # module is that no simulation is needed behind a real game, and
        # borrowing a Match for its geometry would quietly falsify it.
        self.board_hexes = tuple(sorted(Board().half_board_hexes(0)))
        self.space = ActionSpace(data.config)
        self.space.bind_board(self.board_hexes)
        # `legal_mask` lives on the executor, which owns the one piece of
        # interaction state the space needs (the selected unit).
        self.executor = ActionExecutor(self.space)
        # The encoder MUST be built with the options the run was trained
        # with. Defaulting them silently produces a differently-shaped or
        # differently-meaning observation and the model's output becomes
        # nonsense that still looks like advice -- the same failure mode
        # `teacher_config` exists to prevent for the teacher (doc 99 entry 74).
        self.encoder = ObservationEncoder(
            data,
            len(self.board_hexes),
            data.config.round_structure.players - 1,
            champion_encoding=options.get("champion_encoding", "index"),
            scouting=options.get("scouting", "summary"),
            copy_counts=bool(options.get("copy_counts", False)),
            unit_range=bool(options.get("unit_range", False)),
        )
        self.registry = None

    # -- rendering ---------------------------------------------------------

    def _describe(self, index: int, player) -> tuple[str, str]:
        """Human-readable action. Names champions rather than printing slots.

        A recommendation a person cannot execute is worthless, so this resolves
        every operand to something visible on their screen -- "BUY Ornn" beats
        "BUY(3)".
        """
        action = self.space.decode(index)
        kind = action.kind.name
        hexes = self.board_hexes
        bench = player.bench

        def owned(slot: int) -> str:
            """Board hexes first, then bench, matching the action layout."""
            if slot < len(hexes):
                unit = player.board.get(hexes[slot])
                where = f"board {hexes[slot].q},{hexes[slot].r}"
            else:
                index_ = slot - len(hexes)
                unit = bench[index_] if index_ < len(bench) else None
                where = f"bench {index_}"
            if unit is None:
                return f"(empty {where})"
            stars = "*" * unit.star_level
            return f"{unit.champion.id}{stars} @ {where}"

        if action.kind is ActionKind.BUY:
            champ = (player.shop.slots[action.a]
                     if action.a < len(player.shop.slots) else None)
            return kind, f"{champ or '(empty)'} from shop slot {action.a}"
        if action.kind in (ActionKind.SELL, ActionKind.SELECT):
            return kind, owned(action.a)
        if action.kind is ActionKind.PLACE:
            hex_ = hexes[action.a] if action.a < len(hexes) else None
            return kind, ("(no hex)" if hex_ is None
                          else f"to board {hex_.q},{hex_.r}")
        if action.kind is ActionKind.EQUIP:
            item = (player.item_bag[action.a].id
                    if action.a < len(player.item_bag) else "(no item)")
            return kind, f"{item} onto {owned(action.b)}"
        return kind, ""

    # -- the service -------------------------------------------------------

    def recommend(self, state: ObservedState, top_k: int = 5
                  ) -> list[Recommendation]:
        """Ranked legal actions for this observation, best first."""
        if self.registry is None:
            self.registry = _registry_for(self.data)
        player, round_id, opponents = to_player_state(
            state, self.data, self.registry)
        # Reset the interaction state before masking. The executor remembers
        # which unit is "selected", and that carries across calls -- without
        # this, a SELECT from a previous `recommend` leaks in and PLACE is
        # advised when the person has nothing picked up. Caught by
        # `test_every_recommendation_is_legal_and_executes`.
        #
        # The consequence is deliberate: advice is always for a **clean**
        # interaction state, so a SELECT-then-PLACE move is recommended one
        # step at a time rather than as a pair. `ObservedState` has no
        # selection field because a live observer has no reliable way to see
        # one, and inventing it would put the mask and reality out of step.
        self.executor.reset()
        mask = np.asarray(self.executor.legal_mask(player), dtype=bool)
        if not mask.any():
            return []

        obs = self.encoder.encode(player, round_id, opponents,
                                  self.board_hexes)
        scores = self._scores(obs, mask)
        order = np.argsort(-scores)
        out = []
        for index in order[:top_k]:
            if not mask[index]:
                continue
            kind, detail = self._describe(int(index), player)
            out.append(Recommendation(int(index), kind, detail,
                                      float(scores[index])))
        return out

    def _scores(self, obs, mask) -> np.ndarray:
        """Policy probabilities over legal actions.

        Without a model this returns a uniform distribution over legal actions,
        which is deliberately useless as advice and obviously so -- a silent
        fallback that *looked* like a policy would be worse than none.
        """
        if self.model is None:
            uniform = mask.astype(np.float64)
            return uniform / uniform.sum()
        import torch

        with torch.no_grad():
            tensor, _ = self.model.policy.obs_to_tensor(obs)
            dist = self.model.policy.get_distribution(
                tensor, action_masks=torch.as_tensor(mask).unsqueeze(0))
            probs = dist.distribution.probs.squeeze(0).cpu().numpy()
        return probs


def _registry_for(data):
    """The engine builds this per player; the bridge needs exactly one."""
    from engine.items import ItemRegistry

    return ItemRegistry(data.items, data.config.max_items_per_unit)


def load_advisor(data, run_dir=None) -> Advisor:
    """`Advisor` backed by a trained run, or by nothing (uniform advice).

    Reads the run's sidecar for its observation options rather than assuming
    defaults, so the encoder matches the weights being loaded.
    """
    if run_dir is None:
        return Advisor(data)
    from sb3_contrib import MaskablePPO

    from scripts.teacher_gap import teacher_config

    _expert, env_options, _search = teacher_config(run_dir)
    model = MaskablePPO.load(str(run_dir / "model"), device="cpu")
    advisor = Advisor(data, model=model, env_options=env_options)
    expected = model.observation_space.shape[0]
    if advisor.encoder.size != expected:
        raise ValueError(
            f"observation size mismatch: run {run_dir.name} expects "
            f"{expected}, this encoder builds {advisor.encoder.size}. The "
            "sidecar's observation options do not describe these weights."
        )
    return advisor


class _Seat:
    """A policy that is never asked to plan; `Match` only needs eight objects."""

    def plan(self, player, context):  # pragma: no cover - never invoked
        raise AssertionError("the bridge never steps a Match")


def battle_shim(state: ObservedState, data, registry):
    """A `Match` shell around observed seats, for `rl/search.py` (entry 135).

    The board search is the strongest decision-maker this repo has, and it is
    the one a person most wants: "field this unit or that one?" It needs a
    `Match`, but only as a holder -- `Match._clone_board` reads the match's
    `registry` and `board` geometry and takes the player explicitly, and
    `opponent_panel` reads `match.players`. Nothing here is ever stepped, which
    `_Seat` enforces by raising if it ever is.

    Returns `(shim, hero)` where `shim` has the `.player` / `.match` attributes
    `best_board` expects of an env.
    """
    from types import SimpleNamespace

    from engine.match import Match

    hero, _round_id, opponents = to_player_state(state, data, registry)
    match = Match(data, [_Seat() for _ in range(8)], seed=0, registry=registry)
    # Observed seats replace the ones Match built for itself. `_clone_board`
    # and `opponent_panel` are the only consumers and both read this list.
    match.players = [hero, *opponents]
    for index, player in enumerate(match.players):
        player.player_id = index
    return SimpleNamespace(player=hero, match=match), hero


# The advisor's search budget, re-derived for *this* regime (entry 136.2).
# `best_board`'s own defaults were tuned for a teacher inside a training loop
# (106), where the search fires tens of thousands of times; an advisor fires
# once for a person who is already waiting. Widening the panel takes the search
# from 81% to 97% of a large-budget reference for about a second.
#
# `margin` **must** move with `panel_size`: `best_board.score()` divides by
# `trials` but not by the panel, so margin is a threshold on the summed margin
# over the panel, not the per-fight one (136.3). Leaving it at 0.5 here would
# halve the firing threshold as a side effect of widening the panel.
MARGIN_PER_FIGHT = 0.25
ADVISOR_SEARCH = {"panel_size": 4, "margin": MARGIN_PER_FIGHT * 4}


def mirror_panel(match, player, size):
    """Fight a copy of the player's own board; needs no opponent information.

    `clone_board(match, player, 1)` mirrors the player's board onto the enemy
    half, so the hero itself is the panel member and no new object is built.
    `best_board` clones team 0 (candidate swaps applied and restored) before
    cloning team 1, so the mirror is always the *unmodified* board.

    Retains 70% of true-field advice value at n=80 (137.1). The missing 30% is
    opponent **diversity**, not simulation volume -- 137.1 controlled for fight
    count and the gap did not close.
    """
    return [player]


def board_advice(state: ObservedState, data, registry, *, seed: int = 0,
                 **search_kwargs) -> list[tuple[str, str]]:
    """Which bench units to field, decided by simulated combat.

    Returns `(champion, destination)` pairs, empty when the search finds no
    change worth its `margin` -- which is a real answer ("your board is fine"),
    not a failure.

    This is the one place the engine is used as a **combat surrogate** at
    inference rather than as a training environment, which is what entry 105
    noted Riot itself does. It needs no cloning, so entries 106-110's
    transmission problem does not apply: the search is *run*, not learned.
    """
    import random

    from rl.search import best_board

    shim, hero = battle_shim(state, data, registry)
    options = {**ADVISOR_SEARCH, **search_kwargs}
    if not any(seat.board for seat in state.opponents):
        # Nobody entered any opponents, so fight a mirror of the player's own
        # board rather than returning nothing. Worth **70% of the value** of
        # searching against the real field (137.1), which is the difference
        # between typing one board per round and typing eight.
        options["panel_fn"] = mirror_panel
        options["margin"] = MARGIN_PER_FIGHT
    swaps = best_board(shim, random.Random(seed), **options)
    if not swaps:
        return []
    out = []
    for unit, own_hex in swaps:
        stars = "*" * unit.star_level
        out.append((f"{unit.champion.id}{stars}",
                    f"board {own_hex.q},{own_hex.r}"))
    return out

def _panel_for(state: ObservedState, shim, size: int):
    """The opponents to fight, and the per-fight margin scale that goes with it.

    Mirrors `board_advice`'s rule so both answers are grounded the same way: a
    real field when one was entered, otherwise a mirror of the player's own
    board (137.2), which retains 70% of true-field value.
    """
    from rl.search import opponent_panel

    if any(seat.board for seat in state.opponents):
        return opponent_panel(shim.match, shim.player, size)
    return mirror_panel(shim.match, shim.player, size)


def _score_board(shim, panel, seeds, extra=(), drops=()) -> float:
    """Mean survivor margin per fight of a hypothetical board.

    Normalised by panel *and* trials, unlike `rl.search`'s internal scorer,
    whose `margin` is a threshold on the panel-summed value (entry 136.3).
    Here the number is reported to a person, so it has to mean one thing.
    """
    from rl.search import clone_board, fight_value

    player, match = shim.player, shim.match
    board, data = player.hex_board, player.data
    total = 0.0
    for other, trial_seeds in zip(panel, seeds[:len(panel)], strict=True):
        for seed in trial_seeds:
            total += fight_value(
                data, board,
                clone_board(match, player, 0, extra=extra, drops=drops),
                clone_board(match, other, 1), seed)
    return total / (len(panel) * len(seeds[0]))


def _copies_held(player, champion_id: str) -> int:
    """1-star copies on board and bench -- what a purchase would combine with."""
    units = [*player.board.values(), *[u for u in player.bench if u is not None]]
    return sum(1 for u in units
               if u.champion.id == champion_id and u.star_level == 1)


def shop_advice(state: ObservedState, data, registry, *, seed: int = 0,
                trials: int = 3, panel_size: int = 4):
    """Which shop unit to buy, decided by simulated combat.

    Returns `(champion, cost, value)` ranked by value, where `value` is the
    survivor margin per fight the purchase would add to the best board it can
    reach. Only affordable, recognised units are considered.

    The clone ranks buys too, but it is a policy measured at roughly field
    average, while this evaluates the purchase the way the game does -- by
    fighting with it. Same combat-surrogate argument as `board_advice`
    (entry 135.1): the search is run, not learned, so 106-110's transmission
    problem does not apply.

    **A purchase that completes a pair is worth far more than one that does
    not**, so the candidate is built at the star level it would actually reach:
    holding two 1-star copies already makes the third a 2-star, and the two
    are consumed rather than kept.
    """
    import random

    from engine.unit import UnitInstance

    shim, hero = battle_shim(state, data, registry)
    panel = _panel_for(state, shim, panel_size)
    if not panel or not hero.board:
        return []

    rng = random.Random(seed)
    seeds = [[rng.randrange(2**31) for _ in range(trials)]
             for _ in range(len(panel))]
    baseline = _score_board(shim, panel, seeds)

    free = [h for h in sorted(hero._own_hexes) if h not in hero.board]
    weakest = min(hero.board,
                  key=lambda h: (hero.board[h].star_level,
                                 hero.board[h].champion.cost)) if hero.board else None

    out = []
    for champion_id in state.shop:
        if champion_id is None or champion_id not in data.champions:
            continue
        champion = data.champions[champion_id]
        if champion.cost > hero.gold:
            continue
        copies = _copies_held(hero, champion_id)
        star = 2 if copies >= 2 else 1
        unit = UnitInstance(champion, star, [], registry=registry)

        # Fielding it means either filling a slot or replacing the weakest
        # unit; a purchase that cannot reach the board is scored where it can.
        if len(hero.board) < hero.max_board_units and free:
            extra, drops = ((unit, free[0]),), ()
        elif weakest is not None:
            extra, drops = ((unit, weakest),), (weakest,)
        else:
            continue
        # Combining consumes the two held copies, so a board copy would leave
        # the board. Modelled by dropping it when the pair completes there.
        if star == 2:
            held = [h for h, u in hero.board.items()
                    if u.champion.id == champion_id and u.star_level == 1]
            drops = tuple({*drops, *held[:2]})
        value = _score_board(shim, panel, seeds, extra=extra, drops=drops)
        out.append((f"{champion_id}{'*' * star}", champion.cost,
                    value - baseline))
    out.sort(key=lambda row: -row[2])
    return out
