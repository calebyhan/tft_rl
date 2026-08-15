# 04 — The real-game bridge

Scope for playing real TFT with the trained model. Written 2026-08-18, after
doc 99 entry 128 closed the fidelity arc and entry 130 closed PPO-shaped RL:
every simulator-internal avenue is now closed **by measurement**, and this is
the axis with no measurements at all.

## 0. The line this does not cross

**Injecting input into a live TFT client violates Riot's Terms of Service**,
results in permanent account bans, and affects the seven other people in every
lobby. This bridge is built read-only and advisory. Layer 3 below names the
boundary explicitly so it is a decision someone takes deliberately, not
something that arrives by increment.

Nothing in `bridge/` may synthesise mouse or keyboard input. If that changes it
is a product decision, not a refactor.

## 1. Why the seam is where it is

`ObservationEncoder.encode` takes `(player, round_id, opponents, board_hexes)`
— **not** a `Match`. The observation layer is already decoupled from the
simulator's game loop, so a real game does not need a simulated one behind it.
An adapter that can build a `PlayerState` can drive the existing policy
unchanged. `PlayerState` is a plain dataclass; `UnitInstance` takes
`(champion, star_level, items, position, registry)`.

That is the whole architectural claim, and it is why this is weeks rather than
months.

## 2. Layers

| layer | what it does | ToS | status |
|---|---|---|---|
| **L1 state** | observed game state → `PlayerState` + `RoundId` + opponents | none — pure data | **built** (99 §131) |
| **L2 decision** | state → recommended action, via the clone and/or `rl/search.py` | none — pure compute | **built** (99 §133) |
| **L3 output** | *advisory only*: print/overlay the recommendation for a human | none | **built** (99 §134) |
| ~~L3′ actuation~~ | ~~synthesise input into the client~~ | **prohibited** | not built |

`ObservedState` (L1's input) is deliberately **source-agnostic**: a JSON
document describing what an observer can see. Where it comes from — a fixture,
a human typing, an API, a vision pipeline — is a separate concern, and keeping
it separate is what makes L1 testable today with no client involved.

## 3. Input sources, and the one open question

- **Fixtures / engine snapshots** — available now, and the only thing needed to
  prove L1 correct.
- **Riot Live Client Data API** (`localhost:2999`) — official and read-only.
  **Its TFT coverage is unverified**; League exposes a rich payload and TFT may
  expose little or nothing. This is the single highest-value unknown in the
  whole bridge and it is cheap to resolve. Do not assume either way.
- **Match-V1 reference data** (`data/reference/`) — post-game only, so useless
  for live play, but usable to measure how much of the observation *real* board
  states can fill. Note its limits: units carry `character_id`, `tier`,
  `rarity` and **no items and no hex positions**, so it can reconstruct board
  *composition* but not geometry.
- **Screen capture + vision** — works, read-only, and by far the most work.
  Only worth starting once the API question above is answered.

## 4. Milestones

1. **`ObservedState` + adapter, proven by round-trip.** Engine `PlayerState` →
   `ObservedState` → JSON → `PlayerState` → encode. The two observation vectors
   must be **identical**. Uses the engine as ground truth, which is the only
   source that has items, positions, bench and shop all at once.
2. **Coverage measurement against real data.** Build `ObservedState` from
   `data/reference/` seats and report which observation features are
   unfillable. Answers "how much does a real observer actually need to see?"
   *before* any vision work is commissioned.
3. **Decision service.** `ObservedState` → ranked recommended actions, reusing
   `rl/action.py`'s mask so a recommendation is always legal.
4. **Advisory output.** Human-readable recommendation for a state.

Milestone 1 is the load-bearing one: an adapter that is not provably faithful
makes every later measurement meaningless, in the way doc 99 lesson 27's
aggregated measurements did.

**Milestones 1-4 are built** (doc 99 §131, §132, §133, §134). What remains is
the vision pipeline, whose minimum scope §132.2 measured: **bench, shop and
augments**, which post-game data cannot fill at all, plus the hero scalars.
`scripts/advise.py` works today on a hand-written or captured state file.
