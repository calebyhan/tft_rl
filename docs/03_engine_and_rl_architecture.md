# Engine & RL Architecture

Purpose: how to actually structure the codebase. Written for a coding agent
to execute against directly. Python-only, per the earlier stack decision.
Pairs with doc 01 (mechanics rules) and doc 02 (data schema/sourcing).

## 1. Repo layout

```
tft-rl/
  data/
    champions.json / traits.json / items.json / VERSION.json   (doc 02)
  engine/
    hexgrid.py       # coordinates, distance, neighbors, pathing
    schema.py        # dataclasses mirroring doc 02's clean schema
    loader.py         # load + validate data/*.json into schema objects
    unit.py           # UnitInstance: a placed/benched champion + derived stats
    effects.py        # ability/item effect_id -> callable registry (doc 02 sec 2)
    traits.py         # trait activation counting + bonus application
    items.py           # component combination table, item application
    economy.py        # gold income, interest, streak, XP table, leveling
    shop.py            # shared champion pool, roll odds, shop state
    combat.py          # the tick-based combat simulator (doc 01 sec 3)
    player.py          # PlayerState: board, bench, gold, HP, level, items, streak
    match.py           # orchestrates 8 players across rounds/stages (doc 01 sec 1)
  rl/
    env.py             # Gym-style environment wrapping match.py
    observation.py      # state -> feature vector encoding
    action.py          # action space definition + action -> engine-call mapping
    opponents.py       # scripted/heuristic bot policies for the other 7 seats
  scripts/
    fetch_cdragon.py    # doc 02 section 1.1
    smoke_test.py        # scripted game loop, no RL, sanity-checks the engine
  tests/
    test_hexgrid.py, test_combat.py, test_economy.py, test_shop.py, ...
  README.md
```

## 2. Module responsibilities (detail)

### 2.1 `hexgrid.py`
- Axial coordinate class `Hex(q, r)` with `distance(a, b)`, `neighbors(h)`,
  `line(a, b)` (for line-shaped abilities), `ring(center, radius)` and
  `spread(center, radius)` (for AoE abilities).
- `Board` grid definition: valid hex set for a 7-wide x 4-row player
  half-board, plus the mirrored full 7x8 combat grid (doc 01 sec 2).
- Simple BFS pathfinding for unit movement that treats occupied hexes as
  obstacles, returns next-step hex toward a target.

### 2.2 `schema.py` + `loader.py`
- Frozen dataclasses: `ChampionDef`, `TraitDef`, `ItemDef`,
  `AbilityDef` mirroring doc 02 section 2 exactly.
- `loader.load_all(data_dir) -> GameData` returns a bundle of dicts keyed by
  id; raises a clear error listing any item/champion that failed schema
  validation rather than silently skipping (so bad fetch output is loud).

### 2.3 `unit.py`
- `UnitInstance`: wraps a `ChampionDef` reference + `star_level` (1-3) +
  equipped items (list of up to 3 `ItemDef`, 4 if a trait/effect grants a
  slot) + live combat state (`current_hp`, `current_mana`, `position`,
  `status_effects: list[StatusEffect]`, `attack_timer`, `target_id`).
- `derived_stats()` computes final stats = base stats at current star level
  + flat item stat bonuses + active trait bonuses (from `traits.py`) +
  any temporary status-effect modifiers. Compute lazily/cached per combat
  tick rather than per access.

### 2.4 `effects.py`
- A plain dict registry: `EFFECTS: dict[str, Callable]`.
- Signature convention: `def effect_fn(caster: UnitInstance, board: CombatBoard,
  context: EffectContext) -> None` — mutates state (deals damage, applies
  shields/buffs/CC, spawns projectiles) via a small set of primitive helper
  functions (`deal_damage`, `apply_shield`, `apply_stun`, `heal`, `spawn_projectile`)
  defined once in this module so every ability/item effect composes from the
  same primitives (keeps damage-type/mitigation logic centralized in one
  place per doc 01 sec 3.3, instead of reimplemented per ability).
- Missing `effect_id` (not yet implemented) should log once and no-op, not
  crash — lets partial data/ability coverage still run full matches.

### 2.5 `traits.py`
- `active_traits(board: list[UnitInstance]) -> dict[trait_id, breakpoint]`
  counts fielded (board-only, not bench) units per trait id, finds the
  highest breakpoint met per `TraitDef.breakpoints`.
- `apply_trait_bonuses(board, active)` — applies the corresponding
  `effect_id` per active breakpoint the same way item effects apply,
  reusing `effects.py`'s primitives.

### 2.6 `items.py`
- `combine(component_a_id, component_b_id) -> item_id | None` — table
  lookup, order-independent (sort pair before lookup).
- `apply_item_stats(unit, item)` — adds `item.stats` flat bonuses into the
  unit's derived-stat computation; effect-hook items also register into
  `effects.py`'s per-combat trigger hooks (on-attack, on-cast, on-death,
  periodic) as needed — define a small `EffectTrigger` enum for this.

### 2.7 `economy.py`
- Pure functions: `base_income(round_id) -> int`, `interest(gold: int) ->
  int`, `streak_bonus(streak_count: int, streak_type: "win"|"loss") -> int`,
  `xp_cost_to_buy(amount: int) -> int` (fixed 1:1 gold:xp per doc 01 sec 4),
  `passive_xp_per_round() -> int`, `level_thresholds: list[int]` (loaded
  from data, not hardcoded — see doc 02 open item on XP table).
- `sell_value(champion_cost, star_level, is_one_cost_one_star) -> int`
  per doc 01 sec 4's penalty rule.

### 2.8 `shop.py`
- `SharedPool`: tracks remaining copies per champion id (init from doc 02
  sec 4 pool sizes), `draw(cost_tier) -> champion_id`, `return_to_pool(id,
  count)` on sell/elimination.
- `roll_shop(player_level, pool) -> list[champion_id]` (5 slots) using the
  odds table (doc 01 sec 5), loaded from data rather than hardcoded so a
  future set's different table is a data change, not a code change.

### 2.9 `combat.py`
- The tick loop from doc 01 section 3. Structure as a `CombatSimulator`
  class taking two `list[UnitInstance]` (already positioned) and stepping
  until one side is empty or a max-tick safety cap is hit.
- Emit a structured **combat log** (list of timestamped events: moves,
  attacks, casts, deaths) — not just the final result. This is valuable for
  (a) debugging/visualizing fights, (b) potentially feeding richer
  observations to the RL agent later, (c) unit-testing individual
  mechanics deterministically with a fixed RNG seed.
- Must be deterministic given a fixed RNG seed (crit rolls, targeting
  tie-breaks) — seed it explicitly, don't rely on global random state, so
  training runs and tests are reproducible.

### 2.10 `player.py`
- `PlayerState`: gold, level, xp, hp, streak (count + type), board
  (dict[Hex, UnitInstance]), bench (list[UnitInstance | None], fixed size),
  item bag (unattached components/completed items).
- Methods for the planning-phase actions in section 3 below (buy, sell,
  move, reroll, level-up, equip item) — these are the same primitives the
  RL action space calls into, and the same ones a human-facing UI would
  call if one is ever built, so keep them as clean, validated,
  single-responsibility methods (raise on illegal actions rather than
  silently ignoring, so the RL wrapper can catch-and-mask illegal actions
  cleanly).

### 2.11 `match.py`
- Orchestrates 8 `PlayerState`s through the round/stage structure (doc 01
  sec 1): planning phase (calls into each player's/policy's action
  selection), PvP pairing, combat resolution via `combat.py`, damage
  application, elimination checks, end-of-game result.
- Should support **both** "all 8 seats are RL/scripted policies" (for
  self-play training) and "1 seat is the RL agent, 7 are scripted bots"
  (for evaluation against fixed opponents) — parameterize seat policies as
  a list rather than hardcoding player 0 as special.

## 3. RL environment (`rl/env.py`)

Gym-style API (`reset()`, `step(action) -> (obs, reward, terminated,
truncated, info)`), wrapping one seat of a `match.py` game while the other
7 seats run `opponents.py` policies (start with simple heuristics: e.g.
"buy the highest-cost affordable unit that fits current traits, level up
on a fixed curve, always reroll at 0 planning-phase actions remaining" —
this gives a non-trivial but not superhuman training partner; self-play
against copies of the learning policy is a natural v2 step).

### 3.1 Observation space
Flatten into a fixed-size vector (or a dict-of-arrays if using an
attention/set-based network later):
- Self state: gold, level, xp, hp, streak, round number, stage number.
- Bench: fixed-size slots, each encoded as (champion_id embedding index,
  star_level, item_ids x3).
- Board: fixed-size hex slots (28), each encoded the same as bench slots
  plus position.
- Shop: 5 slots, each a champion_id (or "empty").
- Active traits: fixed-size vector over all trait ids, each entry = current
  breakpoint tier active (0 if inactive).
- Opponent summary (simplified, not full board visibility — real TFT lets
  you scout other boards, but for v1 expose only: opponent HP, level,
  streak, for all 7 opponents; full-board scouting is a reasonable v2
  addition once the basic loop trains).

### 3.2 Action space
Recommend a **discrete multi-action-per-turn** design rather than a single
flat discrete action, since a real planning phase involves several
sub-decisions per round:
- `BUY(shop_slot: 0-4)`
- `SELL(board_or_bench_slot)`
- `MOVE(from_slot, to_slot)` (board<->board, board<->bench)
- `EQUIP_ITEM(item_id, target_slot)`
- `REROLL_SHOP`
- `BUY_XP`
- `END_PLANNING` (locks in current board/bench/items and proceeds to combat)

Simplest correct v1: treat the planning phase as a small fixed number of
sequential action picks (e.g. up to 8 actions per round) from the action
list above, each returning a new observation immediately (so it behaves
like a short multi-step sub-episode within the round), terminating early if
`END_PLANNING` is chosen. This avoids needing a combinatorial "joint action"
space and is straightforward to mask (illegal actions, e.g. selling an
empty slot, are simply excluded from the valid-action mask each step).

### 3.3 Reward
- Primary: **placement-based terminal reward** at game end (e.g. `+1` for
  1st down to some negative value for 8th, or a smoother
  `(9 - placement) / 8` shaping) — this directly optimizes what actually
  matters (final standing) and avoids reward-hacking sub-goals.
- Optional dense shaping (use cautiously, weight small relative to
  terminal reward to avoid distorting the objective): small reward for
  surviving each round, small penalty for HP lost, small reward for
  completing a trait breakpoint or completing an item. Recommend starting
  **without** shaping (sparse terminal-only reward) and only adding shaping
  if training is too slow/unstable, since shaping is easy to get subtly
  wrong (e.g. over-rewarding hoarding gold).

### 3.4 Algorithm recommendation
- **PPO** (e.g. via `stable-baselines3` or a custom implementation) is the
  standard fit here: works well with the multi-step-per-round discrete
  action structure above, handles the large-but-structured observation
  space reasonably, and is far more forgiving of reward sparsity than
  vanilla Q-learning for a game this long-horizon (a full match is ~30+
  rounds).
- Self-play (periodically snapshotting the current policy as one of the 7
  opponent seats) is the natural path to superhuman play once the
  fixed-heuristic-bot baseline is beaten consistently — flag this as a
  milestone 4+ concern, not v1.

## 4. Build order / milestones

Recommended sequence (each should be independently testable before moving
on):

1. **`hexgrid.py` + `schema.py` + `loader.py`** — load the starter sample
   dataset (doc 02 sec 5), print/validate it loads correctly. No combat yet.
2. **`unit.py` + `traits.py` + `items.py`** — derived-stat computation for a
   hand-placed board, verified against hand-calculated expected stats.
3. **`combat.py`** — get a single scripted 1v1 fight running deterministically
   with a fixed seed, verify via the combat log that movement/targeting/
   attack-timers/mana/casts all behave per doc 01 sec 3. This is the
   highest-risk, most time-consuming module — budget the most iteration
   time here.
4. **`economy.py` + `shop.py` + `player.py`** — a single player's full
   planning-phase loop (buy/sell/reroll/level) against the real odds
   tables, unit-tested against doc 01 sec 4-5's numbers.
5. **`match.py`** — wire 8 scripted/random-policy players through a full
   game end to end (`scripts/smoke_test.py`), confirm it terminates with a
   sane winner and no crashes over many random seeds.
6. **`rl/env.py` + `rl/opponents.py`** — Gym wrapper + heuristic bots,
   confirm `reset()`/`step()` work and random-action rollouts complete.
7. **PPO training loop** — first training run against the heuristic bots,
   track win rate / average placement over time as the core success metric.
8. **Full data swap** — run `scripts/fetch_cdragon.py`, replace starter
   sample data with the real Set 17 dataset, re-run the smoke test and
   retrain; expect to spend time fixing `effect_id` gaps (abilities/items
   not yet implemented) surfaced by the real data's larger champion pool.
9. **(Stretch) Augments, self-play, full board-scouting observations.**
