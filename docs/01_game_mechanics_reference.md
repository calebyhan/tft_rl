# TFT Game Mechanics Reference

Purpose: this is the ground-truth rules doc for the simulator. It is mostly
set-independent (applies across patches); set-specific numbers (champion
stats, trait breakpoints, item effects) live in doc 02 (Data Schema & Sourcing)
because they change every set/patch and must be pulled from source data, not
hardcoded from this doc.

Researched from: LoL Wiki (TFT:Gold), TFTPad mana mechanics writeup, TFT.Ninja
Set 17 econ guide, and Set 17 shop-odds aggregator sites, current as of
2026-07-31 (patch 17.8). Numbers here reflect that patch; re-verify if the
engine targets a different one.

## 1. Match structure

- 8 players, free-for-all, last one standing (or highest HP when time runs out
  in modes with a clock).
- Players start at 100 HP (Hyper Roll and other modes vary; assume standard
  Ranked/Normal for v1).
- The game proceeds in **rounds**, grouped into **stages** (e.g. stage 2,
  round 1 = "2-1").
  - Stage 1: PvE "creep" rounds only (no combat customization yet, minimal
    econ) — treat as a fixed sequence for v1; can be stubbed.
  - From stage 2 onward: alternating pattern of PvP rounds and periodic PvE
    rounds (creep rounds). Set 17 replaces the classic shared-carousel draft
    with the **Realm of the Gods** mechanic: at stages 2-4, 3-4, and 4-4,
    each player picks a Minor Blessing from one of two Gods assigned that
    game (each pick is a "vote" toward that God; players who pick the same
    God at least twice get a tailored God Boon treasure shop at 4-7). Lower
    HP players still get priority/catch-up treatment (higher-cost offerings,
    component anvils on PvE rounds instead of random components) — the
    lowest-HP-picks-first spirit of the old carousel is preserved even
    though the underlying pick mechanic changed; model this as its own
    system rather than a champion-carousel stub.
  - Rounds increase in stage number (2-1, 2-2, ... 2-7, 3-1, ...).
- Each round has:
  1. **Planning phase** (~30s in real game): buy/sell champions, buy XP,
     reroll shop, move units on board/bench, manage items.
  2. **Combat phase**: two players (or a player vs. a PvE encounter) are
     matched, boards face off, combat resolves automatically (see Section 3).
  3. **Resolution**: losing side takes damage based on surviving enemy units'
     star levels/costs (roughly: base round damage + sum of surviving enemy
     unit costs, scaled by star level), gold/streak awarded, players at 0 HP
     are eliminated.
- PvP pairing algorithm in the real game avoids repeat matchups where
  possible and pairs by proximity in standings; a simplified round-robin-ish
  or random-avoid-repeats scheme is a reasonable v1 approximation.

## 2. The hex board

- Play area is a hex grid. Each player's own board is **7 hexes wide x 4 rows
  deep** (28 placeable hexes) during planning; during combat your 4 rows face
  the opponent's mirrored 4 rows across the center, giving an effective
  7-wide x 8-row battlefield for that fight.
- Use **axial or offset coordinates** for hexes; axial (q, r) is recommended
  for clean distance/neighbor math. Each row is horizontally offset by half a
  hex from the row above/below (flat-top or pointy-top hex layout — TFT uses
  a layout where rows offset alternately; verify visually against a real
  board screenshot before finalizing orientation, but for gameplay purposes
  what matters is: each hex has up to 6 neighbors, hex distance is used for
  range/AoE checks, and "row" (deployment depth) determines who is "front
  line" vs "back line" at combat start).
- Bench is separate from the board: a fixed number of slots (9 in modern
  sets) where owned-but-unplaced units sit; bench units do not fight.

## 3. Combat resolution (full-physics tick simulation)

Real TFT combat is continuous, but a **discrete time-step simulation**
(e.g. 30-100ms ticks) reproduces it faithfully enough for both visualization
and RL while being tractable to implement. Recommended approach:

### 3.1 Per-tick unit state machine
Each unit each tick is in one of: `idle/seeking`, `moving`, `attacking`,
`casting`, `stunned/CC'd`, `dead`. Loop per tick:
1. Apply any active status effects (DoTs, HoTs, stuns, shields decaying,
   attack-speed/CC durations ticking down).
2. If stunned/CC'd (rooted/disarmed as relevant), skip action selection.
3. Target selection: if current target is dead/out of range and no
   "locked" targeting effect applies, pick nearest enemy by hex distance
   (real TFT default targeting is nearest-enemy; some units/items override
   this to lowest-HP, highest-attack-damage, etc. — model as a per-unit
   `targeting_rule` field, default `nearest`).
4. If target is out of attack range: move 1 hex per movement tick toward it
   along the shortest path (simple BFS/A* on the hex grid honoring occupied
   hexes as obstacles) — movement speed is roughly fixed per unit in TFT
   (no per-champion movement stat in modern sets; treat as a constant tiles/
   sec, tune against observed match footage/community data if precision
   matters).
5. If target is in range: progress an attack-timer based on **attack speed**
   (attacks/sec). When the timer completes, resolve an **auto-attack**:
   - Roll crit (crit chance/damage stats).
   - Compute physical damage: `AD * (100 / (100 + target_armor))` roughly
     (verify exact TFT armor formula against current patch — the general
     shape is a diminishing-returns percentage mitigation, not flat
     subtraction).
   - Apply on-hit item/trait effects.
   - Grant **mana**: flat mana per basic attack (10 mana per attack under
     current patch conventions), see 3.2.
   - If the unit has a ranged attack, spawn a projectile entity with a
     travel time based on distance (for "full physics" fidelity); melee
     attacks resolve instantly on attack-timer completion.
6. Ability casting: when mana >= max mana, interrupt attack/move behavior
   this tick to cast; apply ability effect (damage/heal/shield/CC per the
   ability's data-defined effect); reset mana to `0` or to `overflow` (see
   3.2); some champions with "no mana, cast on cooldown" variants use a
   fixed-interval timer instead of a mana bar (model both modes in the
   ability schema).
7. Death check: any unit at <=0 HP is removed, triggers on-death effects
   (item/trait), and the loser's team combat-strength for HP-damage
   calculation is recorded.
8. Combat ends when one side has zero living units, or a max-duration
   safety cap is hit (real TFT rounds are ~30s+ before "sudden death"/
   damage-ramp mechanics kick in to prevent infinite stalls — implement an
   analogous escalating-damage or hard timeout fallback).

### 3.2 Mana mechanics (verified against current patch conventions)
- Mana per basic attack landed is **role-dependent** (not per attack
  attempt — must connect, though crits/on-hit don't change this base amount
  unless an item/trait explicitly grants bonus mana per attack, e.g. items
  granting "+N bonus mana on attack"), per the Set 15 role-revamp mechanic
  still in effect: **10 mana** for Assassins/Marksmen/Fighters, **7 mana**
  for Casters, **5 mana** for Tanks. Model as a per-champion `role` field
  (or a direct `mana_per_attack` value pulled from source data) rather than
  a single global constant.
- **Tanks only** also generate mana from **taking damage**: roughly 1% of
  pre-mitigation damage + 3% of post-mitigation (i.e. actual HP lost) damage,
  converted to mana, capped at ~42.5 mana from a single damage instance.
  This rewards being tanky/focused without infinite-mana abuse from massive
  single hits. Other roles do not generate mana from damage taken.
- Starting mana varies per champion (some start with 0/X mana pool, others
  start partially charged or with bonus starting mana from items like Spear
  of Shojin/Tear of the Goddess-line items).
- Overflow mana (mana above the cap when a cast triggers) carries over into
  the next mana bar rather than being discarded.
- Some units/traits disable mana generation entirely and instead cast on a
  fixed cooldown timer ("Cosmic Rhythm"-style mechanics) — support both
  modes via an `ability.cast_mode: "mana" | "cooldown"` field.

### 3.3 Damage/mitigation formulas (implement, verify exact constants
against current patch tooltips before finalizing — these shift slightly
patch to patch)
- **Physical damage** mitigated by target Armor using a diminishing-returns
  curve (percentage reduction that approaches but never reaches 100% as
  armor grows).
- **Magic damage** mitigated by target Magic Resist the same way.
- **True damage** ignores all mitigation.
- Damage amp / damage reduction modifiers (from items/traits, e.g. "+X%
  damage amp", "-X% damage taken") apply multiplicatively after the
  armor/MR mitigation step.
- Shields absorb damage before HP loss; some shields have "decay" (shrink
  over time) or are damage-type-specific (physical/magic-only shields exist
  in some items/traits).

## 4. Economy

Base income per round (from planning-phase start), current patch:
- Stage 1 has a soft ramp: 2 / 2 / 3 / 4 gold at rounds 1-2/1-3/1-4/2-1.
- From round 2-2 onward: **5 gold base income** every round (2-1 is still
  part of the ramp at 4 gold).
- **Interest**: +1 gold per 10 gold currently held, calculated at end of
  round before income is added, **capped at +5** (i.e. capped at gold >= 50).
- **Win streak bonus** (paid every round while streaking, including PvE
  rounds): +1 at 3-4 consecutive wins, +2 at 5, +3 at 6+.
- **Loss streak bonus**: same thresholds/amounts as win streak, for
  consecutive losses.
- **+1 gold flat bonus** after winning any PvP round (separate from streak).
- Selling champions refunds gold based on cost and star level, with a small
  "penalty" for anything above 1-star/1-cost (a 2-star 3-cost sells for 1
  less than its raw combine value, etc. — model as
  `sell_value = base_combine_cost - (0 if (star==1 and cost==1) else 1)`,
  clamped at >= cost).

### XP / Leveling
- Players passively gain a small amount of XP per round (2 XP/round is the
  common baseline) in addition to any XP bought with gold.
- Buying XP costs 4 gold for 4 XP (a fixed exchange rate).
- Each level requires a cumulative XP threshold; thresholds increase per
  level and must be pulled from current-patch data (they do change slightly
  set to set — treat the exact table as set-specific config in the data
  schema doc rather than hardcoding here, but the *mechanism* — spend gold
  1:1 for XP in increments of 4, passive trickle each round, discrete level
  thresholds 1 through 10 (sometimes higher via specific mechanics) — is
  stable across sets).
- Level determines: max board size (units you can field), and shop odds
  (Section 5).

### Shop odds and champion pool (Set 17 / patch 17.8 values — re-verify
if targeting a different patch; use as the numeric example)

| Level | 1-cost | 2-cost | 3-cost | 4-cost | 5-cost |
|-------|--------|--------|--------|--------|--------|
| 1     | 100%   | 0%     | 0%     | 0%     | 0%     |
| 2     | 100%   | 0%     | 0%     | 0%     | 0%     |
| 3     | 75%    | 25%    | 0%     | 0%     | 0%     |
| 4     | 55%    | 30%    | 15%    | 0%     | 0%     |
| 5     | 45%    | 33%    | 20%    | 2%     | 0%     |
| 6     | 30%    | 40%    | 25%    | 5%     | 0%     |
| 7     | 19%    | 30%    | 40%    | 10%    | 1%     |
| 8     | 15%    | 20%    | 32%    | 30%    | 3%     |
| 9     | 10%    | 17%    | 25%    | 33%    | 15%    |
| 10    | 5%     | 10%    | 20%    | 40%    | 25%    |

- Shop has **5 slots**; each slot rolls its cost tier independently using
  the row above, then picks uniformly among currently-available (in-pool)
  champions of that tier.
- Champion pool sizes (shared across all 8 players; copies deplete as
  bought, return to pool on sell/elimination):

| Cost | Copies in pool per unique champion |
|------|-------------------------------------|
| 1    | 30 |
| 2    | 25 |
| 3    | 18 |
| 4    | 10 |
| 5    | 9  |

- 3-star a champion = 9 copies of that champion (three 1-star -> 2-star
  needs 3 copies; three 2-star -> 3-star needs 3 more sets of 3, i.e. 9
  total 1-star-equivalents).
- Rerolling the shop (for gold, cost fixed, typically 2 gold) draws 5 new
  slots using the same odds table.

## 5. Items

- **Component items** (basic items): dropped from PvE rounds / carousels /
  augments. Current patch's basic components: B.F. Sword, Chain Vest,
  Frying Pan, Giant's Belt, Needlessly Large Rod, Negatron Cloak, Recurve
  Bow, Sparring Gloves, Spatula, Tear of the Goddess (10 total, one stat
  focus each: AD, Armor, AD variant, Health, AP, MR, Attack Speed, Crit,
  trait-emblem-generator, Mana).
- **Combining**: exactly 2 components combine into 1 completed item
  (deterministic combination table — component A + component B = specific
  completed item; there are 10 components -> 45 unique unordered pairs ->
  45 completed "advanced" items, though not all pairs are used/unique in
  every set; Spatula pairs produce **trait emblem** items instead of stat
  items).
  - The full current combination table must be pulled from source data
    (doc 02) since exact pairings can shift slightly, but the combinatorial
    *rule* (2 components -> 1 completed item, order doesn't matter) is
    stable.
- A champion can hold **up to 3 completed items** (some champions/traits
  modify this, e.g. "Dual Wielding"-style effects granting a 4th slot).
- **Radiant items**: current-patch upgrade mechanic where a normal completed
  item is enhanced (typically via an in-game "anvil"/portal event) into a
  stronger Radiant version with amplified effects — treat as
  `item.radiant_version_of` in the schema.
- **Artifact items**: a separate item category (current patch has ~20+,
  e.g. Gold Collector, Zhonya's Paradox) typically obtained via specific
  augments/encounters rather than normal combination, often with unique/
  build-around effects.
- **Emblems**: grant the wearer a specific trait regardless of their
  innate traits (craftable from Spatula + component, or standalone
  uncraftable versions from certain sources).

## 6. Traits (origins/classes)

- Each champion has 1+ traits (origin and/or class, terminology varies by
  set — current set uses "Origins" and "Class" categories per the wiki).
- A trait is "active" on your board once you have >= its lowest breakpoint
  count of champions with that trait fielded (bench doesn't count).
- Breakpoints are trait-specific tiers (e.g. 2/4/6/8 count thresholds) each
  granting a bonus; bonuses generally get stronger at higher breakpoints
  and are **not** typically cumulative across tiers (you get the highest
  tier's bonus, not the sum of all tiers you've passed) — verify per-trait
  in source data since a few traits use additive/stacking bonuses instead
  (e.g. "unique trait" style bonuses that scale per unit rather than having
  discrete breakpoints).
- Some traits have "unique" behavior where only specific counts matter
  (e.g. a trait active at exactly 1 champion, common for very strong
  single-unit traits) — model breakpoints as an explicit sorted list per
  trait rather than assuming a uniform pattern like 2/4/6/8.

## 7. Round damage / player HP loss

- On losing a PvP round, the losing player takes damage roughly equal to a
  **base round-damage value** (increases as the game progresses through
  stages) **plus a component per surviving enemy unit** (typically their
  cost, scaled up for higher star levels, e.g. 2-star counts double, 3-star
  counts triple, of the survivors on the winning board).
- On losing to PvE rounds, damage is typically smaller/fixed or based on
  which minions survived.
- A player is eliminated at 0 HP; their bench/board champions return to
  the shared pool immediately.

## 8. Augments (recommend stubbing for v1, documenting for later milestone)

- At specific rounds (commonly 2-1, 3-2, 4-2 in recent sets, verify current
  patch's exact reveal rounds), each player picks 1 of 3 offered augments
  from a tiered pool (Silver/Gold/Prismatic tiers, roughly increasing in
  power/rarity as the game progresses).
- Augments apply a persistent modifier to econ, combat, or provide
  free items/units — because effects are extremely varied (bespoke per
  augment), treat each as a small effect-hook (same pattern as item/ability
  effects) rather than trying to special-case them individually up front.
  Recommend implementing the augment *system* (offer 3, apply persistent
  hook) in an early milestone, but only wire up a handful of simple augments
  (e.g. flat stat boosts, econ tweaks) before expanding.

## 9. Open questions / things to verify against the live client or very
recent patch notes before finalizing constants (flagged rather than
guessed):
- Exact XP-per-level threshold table for the current patch.
- Exact armor/MR mitigation formula constant (the diminishing-returns
  curve's exact coefficient).
- Exact round-damage-by-stage table.
- Whether current patch's augment reveal rounds match the "2-1/3-2/4-2"
  pattern referenced above.
- Precise movement speed / pathing tile-per-second value for units (not
  well documented publicly; may require empirical tuning or accepting an
  approximation).
