# Judgement Calls & Learning Journal

Every decision this project made that the three spec docs
([01](01_game_mechanics_reference.md), [02](02_data_schema_and_sourcing.md),
[03](03_engine_and_rl_architecture.md)) did not determine, and every result
measured while building it.

This started as a temporary review file for milestones 1–7. It is not temporary
any more: entries 9 onward are the project's record of what was tried, what it
cost, and what it turned out to mean — including the parts that were wrong.
**Withdrawn and corrected entries are kept, not deleted.** Several of this
project's most useful conclusions come from re-checking a number that had
already been cited three times as fact.

## How to read this

The document is in two parts, and they are different kinds of thing:

- **Part I — Standing decisions** (§1–8). A catalogue of judgement calls made
  where the specs were silent or were deviated from. Reference material, kept
  current. Mostly tables.
- **Part II — Journal** (§9–32). Dated entries, newest last. Each one records a
  question, what was measured, and what changed as a result. Read in order they
  tell the story of the agent going from 8.000 to parity with its teacher.

**Citing an entry.** Use `doc 99 entry N.M` in code comments and commit
messages — for example `doc 99 entry 29.1`. Numbers are **stable**: an entry is
never renumbered, because ~77 comments across the codebase point at them. A
superseded entry keeps its number and gains a banner naming its successor.

**Status markers** on journal entries:

| | meaning |
|---|---|
| ✅ | stands as written |
| ⚠️ | partly corrected or narrowed by a later entry — read both |
| ❌ | withdrawn; the later entry supersedes it |

**Flags** on standing decisions:

| | meaning |
|---|---|
| 🔴 | deviates from an explicit statement in doc 01/02/03 |
| 🟠 | invented constant — a number the docs flag unverified or don't give |
| 🟡 | gap-filled — the docs were silent and a choice was required |
| ⚪ | deliberately deferred or stubbed |

---

## Lessons

The methodology findings, which generalise past this project. Each is stated
where it was learned; this is the index to them.

**1. Relational beats descriptive.** Nine milestones of observation work asked
*how much* information the vector carried. The answer that mattered was *what
kind*. Every widening that failed added description of entities (the `features`
encoding: ~1800 extra floats, rejected three times). Every one that worked
added a *comparison between* entities — identity match against the roster, dot
product with board trait counts, rank among owned units, threshold against a
cap. **Twelve floats, four comparisons, 1.266 placement.** (§29.1, §30.4)

**2. A rate is uninterpretable without its achievable maximum.** "BUY sits at
48%" means nothing until you know whether 48% is bad. Measuring the ceiling
took one minute and could have invalidated three entries. (§26.4, §28.1)

**3. Measure the label function, not a property of the features.** The 90.7%
ceiling was wrong because it counted how often the expert's argmax was
*unambiguous* rather than how often the expert *took* it. Those are different
questions. (§28.1)

**4. A number measured once, in one regime, becomes a default and then a
fact.** It happened twice: the 90.7% ceiling survived three entries before
being re-derived, and `--target-kl 0.02` shipped as a default on evidence from
a policy that no longer existed. Re-derive before citing. (§28.2, §31.1)

**5. A probe that cannot fit its own training set is a statement about the
feature set, not the model.** Two investigations turned on this: a 52% train
accuracy exposed a missing economy gate, a 42.5% exposed a missing rule regime.
(§28.3, §30.1)

**6. Replication tests precision; it does not test whether the measurement
answers the question.** The 60k screen's only significant arm was an artefact
that a 3-seed replication would have confirmed three times over. Duration was
the test that mattered. (§23.3, §23.5)

**7. Aggregate metrics hide composition.** Overall action match stayed flat at
51% while placement improved 0.770; a KL arm posted fewer last places *and*
fewer top-fours at an identical mean. Report the distribution. (§25.4, §29.2,
§30.3, §31.3)

**8. Favourable tail statistics are not evidence under an unstated
tail-sensitive objective.** Reading a win-rate rise as "a gain under ranked LP"
assumed the answer; scoring it properly showed the last-place rise cancelled
it. (§32.1)

**9. A policy pinned at last place has no outcome variance, so no A/B built on
it can resolve anything.** Four consecutive experiments were wasted before this
was noticed. `EvalResult` now warns. (§18.3, §18.5)

**10. Whole-game invariants catch what per-feature tests cannot.** A champion
pool leak survived 30 passing unit tests and was caught by `smoke_test.py`
asserting conservation across whole games. (§21.4)

**11. Mutation-test the tests that pin your central claim.** Four tests in this
project passed against deliberately broken implementations, and two more
silently skipped on a fixture that could not construct the case. A test that
asserts nothing is worse than no test, because it reads as coverage. (§29.1,
§30.2)

**12. Baselines have been invalidated eight times.** Engine changes shift every
number. Never compare a figure against one from an older commit; re-measure
both arms together. (§22, §30.5)

---

## Index

### Part I — Standing decisions

| § | Topic | Flag |
|---|---|---|
| 1 | Deviations from the specs | 🔴 |
| 2 | Files and structure the docs didn't specify | 🟡 |
| 3 | Invented constants, all flagged in `config.unverified` | 🟠 |
| 4 | Schema conventions that avoid changing doc 02's schema | 🟡 |
| 5 | Combat mechanics where doc 01 was silent | 🟡 |
| 6 | Player / match mechanics where the docs were silent | 🟡 |
| 6b | RL environment (milestone 6) | 🟡 |
| 6c | Training (milestone 7) | 🟡 🔴 |
| 7 | Deliberately deferred | ⚪ |
| 8 | Open items | — |

### Part II — Journal

| § | Date | Entry | Status |
|---|---|---|---|
| 9 | 08-01 | Milestone 8 — real Set 17 data | ✅ |
| 10 | 08-01 | Entry 6b.5 resolved — the scalar index encoding stays | ✅ |
| 11 | 08-01 | Milestone 8b — real abilities | ✅ |
| 12 | 08-01 | Base-stat verification against the wiki | ✅ |
| 13 | 08-01 | Entry 6c.3 resolved — the shaping was reward-hacking | ✅ |
| 14 | 08-01 | Entry 9.2 resolved — the role model was missing a role and two perks | ✅ |
| 15 | 08-01 | Entry 6b.1 resolved — the action space is not the bottleneck | ✅ |
| 16 | 08-01 | Ability coverage — widened magnitude lookup | ✅ |
| 17 | 08-01 | Milestone 9 — augments, self-play, board scouting | ✅ |
| 18 | 08-01 | The value head was never trained — and that was not the bottleneck | ✅ |
| 19 | 08-02 | Milestone 9 measured — scouting hurts, self-play is inert | ❌ 22.2, 22.3, 31.2 |
| 20 | 08-02 | Item acquisition and real PvE rounds | ✅ |
| 21 | 08-02 | The Realm of the Gods — an HP-ordered contested draft | ✅ |
| 22 | 08-02 | The milestone 12 re-measurement | ⚠️ 31 |
| 23 | 08-02 | Why PPO degrades its warm start — the screen | ⚠️ 31.1 |
| 24 | 08-02 | DAgger does not close the imitation gap | ⚠️ 27.3, 30.1 |
| 25 | 08-02 | The bottleneck is BUY, and the observation cannot express it | ⚠️ 27.2, 28.1 |
| 26 | 08-02 | BUY's ceiling, and 25.2 is untested rather than refuted | ⚠️ 28.1 |
| 27 | 08-02 | BUY is structural, not informational — the clean test | ⚠️ 28.3, 29 |
| 28 | 08-02 | Correcting 26.1: the BUY ceiling is 67.7%, not 90.7% | ✅ |
| 29 | 08-02 | Two relational features close 63% of the imitation gap | ✅ |
| 30 | 08-02 | Parity with the teacher, from twelve floats | ✅ |
| 31 | 08-03 | PPO from a parity clone: two verdicts reversed | ✅ |
| 32 | 08-03 | LP scoring, and a correction to 31.3 | ✅ |
| 33 | 08-03 | Closing the fidelity gap — item effects | ⚠️ 34.6 |
| 34 | 08-03 | Closing the fidelity gap — items, traits, four bugs | ✅ |
| 35 | 08-03 | 100% content coverage — abilities, traits, five systems | ✅ |
| 36 | 08-03 | External audit: nine real defects, four of them mine | ✅ |
| 37 | 08-03 | The econ sweep: the teacher could not sell | ✅ |
| 38 | 08-03 | The clone cannot follow the better teacher | ✅ |
| 39 | 08-04 | Ranking is an architecture problem, not a feature problem | ✅ |
| 40 | 08-04 | One float per slot closes 76% of the clone-teacher gap | ✅ |
| 41 | 08-04 | The slot head regresses: a scorer with no context | ✅ |
| 42 | 08-04 | Context restores the slot head to parity, and no further | ✅ |
| 43 | 08-04 | The flag sweep, re-run on a teacher that can sell | ✅ |
| 44 | 08-04 | The better teacher's gain does not reach the clone | ❌ |
| 45 | 08-04 | BUY: the slot head improves 4 of 5 kinds and not placement | ❌ |
| 46 | 08-04 | One-ply board search: small, not resolved at n=300 | ⚠️ n |
| 47 | 08-04 | Positioning matters; search of it is worth ~0.2, flat | ⚠️ scoped by 53.3 |
| 48 | 08-04 | PPO degrades a strong warm start (+1.077, t=+6.27); self-play was broken | ✅ |
| 49 | 08-04 | Imitation is NOT exhausted: clone is 0.507 behind its teacher | ✅ |
| 50 | 08-04 | The gap is context-dependent: PICK/MOVE/SELL, necessity ≠ sufficiency | ✅ |
| 51 | 08-04 | Augment choice is worth nothing (t=+0.06); PICK is a carousel term | ✅ |
| 52 | 08-04 | SELL worth 1.893 (clone captures 85%); the teacher never repositions | ✅ |
| 53 | 08-04 | Defaults flipped; search helps a weak teacher, harms a good one | ✅ |
| 54 | 08-04 | Two RNG defects in the search path; 53 survives at +0.307, t=+2.45 | ✅ |
| 55 | 08-05 | DAgger closes 54% of the imitation gap once the fit stops diverging | ⚠️ t |
| 56 | 08-05 | The teacher's 3.030 mostly measured weak opposition | ✅ |
| 57 | 08-05 | The DAgger divergence was unbounded logits; label smoothing fixes it | ✅ |
| 58 | 08-05 | Imitation is exhausted at t=+1.71; early-game outcomes are ~unpredictable | ✅ |
| 59 | 08-05 | The critic is data-limited and trained ~50x past its optimum | ✅ |
| 60 | 08-05 | The critic was never the constraint: PPO collapses onto REROLL | ✅ |
| 61 | 08-05 | The drift is not advantage-driven; REROLL is penalised and wins anyway | ✅ |
| 62 | 08-05 | Not a shared-head artefact: REROLL rises under *any* perturbation | ✅ |
| 63 | 08-05 | The drift goes to suppressed x always-legal actions; END_PLANNING leads | ✅ |
| 64 | 08-06 | The PPO collapse is fixable; PPO still contributes nothing | ✅ |
| 65 | 08-06 | Training-seed sd is 0.074; imitation is saturated at ~3.40 | ✅ |
| 66 | 08-06 | Every lever is closed; gold has no sink and 3-stars never happen | ✅ |
| 67 | 08-06 | Board size dominates; star scaling is correct; slow-roll test was crude | ⚠️ |

### The arc, in one table

Placement of the agent's own seat against seven scripted bots, n=300. Every row
is a different engine or observation, so **only adjacent rows are comparable**
(lesson 12).

| milestone | agent | teacher | what changed |
|---|---|---|---|
| 7 | 8.000 | 4.467 | PPO from scratch never leaves last place (§6c.9) |
| 7 | 6.250 | 4.467 | behaviour cloning + selection state (§6c.10) |
| 12 | 5.907 | 4.620 | frozen engine: items, PvE, Realm draft (§22) |
| 16 | 5.533 | 4.620 | 1500-episode label budget (§27.3) |
| 17 | 5.063 | 4.620 | shop `owned` + `synergy` (§29) |
| 18 | **4.567** | 4.620 | unit star/cost rank + `board_full` (§30) |
| 19 | 4.637 | 4.620 | PPO from parity — a null (§31.3, §32.1) |
| 20 | 4.813 | 3.437 | engine rules corrected + teacher can sell; agent unmoved (§38.1) |
| 21 | 3.760 | 3.437 | `copy_counts`: one float per unit slot (§40.1) |
| 22 | 3.793 | 3.437 | shared-weight slot head — a null (§42.1) |
| 23 | 3.747 | **3.030** | teacher flags: -0.407 in the teacher, nothing in the student (§43, §44) |
| 24 | 3.537 | 3.030 | slot+shop+row head: match 76.8% → 81.9%, placement t=-1.43 (§45.6) |
| 25 | 4.613 | 3.030 | PPO from the 3.537 clone: **+1.077 worse**, t=+6.27 (§48.2) |

Rows 20 onward are n=150 rather than n=300; the engine's *rules* changed at
row 20 (§36), so nothing above it is comparable to anything below.

---

# Part I — Standing decisions

Judgement calls made where the specs were silent, or where the code knowingly
departs from them. Reference material: kept current, not a historical record.
✅ marks an entry that has since been settled by review or by measurement, with
the resolving journal entry named.

### Settled by review (2026-08-01)

Four decisions were reviewed with the project owner and closed.

| Entry | Decision | Outcome |
|---|---|---|
| 1.1 | Shop draw weighting | ✅ **Keep `by_copies`.** No code change. Doc 01 sec 5 amended to describe copy-weighted draws. |
| 1.2 | Combat re-targeting | ✅ **Switched to sticky targeting.** Doc 01 sec 3.1 step 3 amended. |
| 3.1 / 3.2 | Invented XP + round-damage tables | ✅ **Left flagged in `config.unverified`;** real values sought from CDragon at milestone 8, these kept as fallback. |
| 4.4 | Item effect magnitudes | ✅ **Added `params` to `ItemDef`.** Doc 02 sec 2's item schema amended. |

All three doc amendments were applied. Docs 01 and 02 carry an `## Amendments`
section recording what changed and why; code and specs agree on these points.

**Entry 2.1 closed the same day.** Direction given: "Riot is the source for
everything." The live payload showed that is achievable for champions, traits
and items but *not* for the economy tables — `shopOdds`, `poolSize`, `xpTable`
and `rerollCost` have zero occurrences in the full 26 MB CDragon document, and
`setData` carries only champions, traits, items and augments. Follow-up
direction: community documentation is good enough for those. So `config.json`
stays hand-curated, the fetch script is forbidden from writing it, and it
carries a `provenance` block classifying every constant as `riot_published` /
`community_documented` / `engine_artifact`. Doc 02 gained section 4b.

---

## 1. Deviations from the specs (🔴) — review these first

| # | Decision | Why | Reference | Priority |
|---|---|---|---|---|
| 1.1 | ✅ **SETTLED: keep `by_copies`.** Shop draws are weighted by remaining copies, not uniform over available champions. Made configurable (`shop_draw_weighting: "by_copies" \| "uniform"`, default `by_copies`). | Doc 01 says a slot "picks uniformly among currently-available champions of that tier." Taken literally, partially-bought champions stay equally likely, which erases the contested-unit dynamic that pool sizes exist to create. Real TFT draws a random *copy*. Both readings are implemented and tested; only the default differs from the doc. | doc 01 sec 5 | **High** — changes rolling odds and therefore econ strategy |
| 1.2 | ✅ **SETTLED: switched to sticky targeting (2026-08-01).** A unit now keeps its target while the target lives, re-picking only on death or when no path exists (`_move_toward` clears an unreachable target). Previously it re-targeted every tick while out of range, per doc 01 sec 3.1's literal wording, which made chasers flip targets constantly. | doc 01 sec 3.1 — **needs amending** | Done |
| 1.3 | **`targeting_rule` lives on `UnitInstance`, not `ChampionDef`.** | Doc 01 sec 3.1 says "model as a per-unit `targeting_rule` field," but doc 02's champion schema has no such field and must stay byte-identical so real data drops in. Put it on the runtime unit, settable by items/effects. | doc 01 sec 3.1 vs doc 02 sec 2 | Low |
| 1.4 | **Purchases never auto-field.** A buy goes to the bench; a full bench blocks the buy unless the copy combines immediately. | An earlier version fell back to placing on the board. That is not TFT behaviour and made the "bench is full" check inconsistent with what `buy()` actually did. | doc 01 sec 4 (implied) | Low |

---

## 2. Files and structure the docs didn't specify (🟡)

| # | Decision | Why | Priority |
|---|---|---|---|
| 2.1 | ✅ **SETTLED: `data/config.json`** holds every set/patch-specific table: shop odds, pool sizes, XP thresholds, economy constants, combat tunables, round structure, role→mana map. **Doc 02 sec 4b now defines it**, it carries a `provenance` block, and the fetch script must not write it. | Doc 02 defined only `champions/traits/items/VERSION.json`, but doc 03 sec 2.7/2.8 requires odds and XP tables be data, not code. Riot publishes none of these values (verified against the live payload), so they stay curated. | Settled 2026-08-01 |
| 2.2 | **`engine/stats.py`**, not in doc 03's layout. Holds `StatBonuses` / `DerivedStats` / `derive_stats`. | `unit` → `items`/`traits` → back to `unit` is a cycle; a module below all three breaks it. | Low |
| 2.3 | Python **3.12** venv, not 3.14. | torch / stable-baselines3 compatibility at milestone 7. | Low |
| 2.4 | Board geometry (7 wide × 4 deep) is a **code constant**, not config. | It's a stable game-layout fact, not per-set balance data. Contrast with everything in 2.1. | Low |
| 2.5 | Loader treats **unknown JSON fields as errors**, and reports *all* problems at once. | Doc 03 sec 2.2 asks for loud failure. Strictness means a fetch-script field rename fails visibly rather than silently dropping a stat. Risk: real CDragon output may carry extra fields, and milestone 8 may need to relax this. | Medium — may bite at the data swap |
| 2.6 | `config.unverified` lists tables doc 01 sec 9 flags as unconfirmed; the loader logs them as a warning on every load. | Keeps invented constants visible instead of passing as verified. | Low |

---

## 3. Invented constants (🟠) — all flagged in `config.unverified`

| # | Constant | Value | Basis | Priority |
|---|---|---|---|---|
| 3.1 ✅ | `xp_to_next_level` | 2/2/6/10/20/36/48/76/84 | Doc 01 sec 9 lists the exact table as unverified. These are commonly-cited modern-TFT values. | **High** — drives all levelling pace |
| 3.2 ✅ | `stage_base_damage` | stage 2–7 → 2/5/8/12/15/20 | Doc 01 sec 9 flags the round-damage table as unverified. Shape (rising per stage) is right; magnitudes are guesses. | **High** — drives game length |
| 3.3 | `movement_hexes_per_second` | 2.0 | Doc 01 sec 9: "not well documented publicly; may require empirical tuning." | Medium |
| 3.4 | `projectile_hexes_per_second` | 12.0 | Doc 01 sec 3.1 asks for travel time but gives no speed. | Low |
| 3.5 | `armor_mitigation_constant` | 100 → `100/(100+resist)` | Doc 01 sec 3.3 gives this shape and sec 9 flags the exact coefficient as unverified. | Medium |
| 3.6 | Sudden death | ramp from 30s, 3%/sec of max HP, escalating, bypasses shields and mitigation | Doc 01 sec 3.1 asks for "an analogous escalating-damage or hard timeout fallback" without specifying. Bypassing mitigation guarantees termination. | Low |
| 3.7 | `tick_seconds` | 0.05 | Doc 01 sec 3 suggests 30–100 ms. Quantises attack intervals: 0.75 AS shows 1.35s gaps vs a true 1.333s. | Medium — affects fidelity vs speed |
| 3.8 | `max_duration_seconds` | 60 | Doc 01 sec 3.1 mentions ~30s before ramp mechanics. | Low |
| 3.9 | `round_structure` | 7 rounds/stage, stage 1 = 4 rounds, PvE at x-7, max 9 stages | Doc 01 sec 1 says "periodic PvE rounds" without pinning the schedule. | Medium |
| 3.10 | Attack-speed cap 5.0, crit-chance cap 1.0 | code constants in `stats.py` | Stable global TFT mechanics, not per-set data. | Low |
| 3.11 | Sample dataset stats | all 13 champions' costs, HP, AD, mana, and all trait/item magnitudes | Hand-authored per doc 02 sec 5. **Not real Set 17 data** — replaced wholesale at milestone 8. | None — disposable |

---

## 4. Schema conventions invented to avoid changing doc 02's schema (🟡)

| # | Decision | Why | Priority |
|---|---|---|---|
| 4.1 | **Emblems declare their trait via `effect_id: "emblem_<TraitId>"`.** Loader validates the trait exists. | Doc 02's `ItemDef` has no field for "which trait does this grant," and the schema must stay byte-identical. A naming convention keeps it data-driven; the fetch script normalises real emblems into it. | Medium — fetch script must honour it |
| 4.2 | **Trait/item params naming a known stat are auto-applied as flat bonuses**; other keys belong to the `effect_id` implementation. | Lets a purely statistical trait need zero Python, and means an *unimplemented* `effect_id` still delivers its stat half instead of doing nothing. | Medium — a nice property, but implicit |
| 4.3 | **Reserved params key `targets`**: `"team"` or `"trait_members"` (default). | TFT traits differ on whether the bonus hits the whole board or only trait members; doc 02's `TraitDef` has no field for it. | Medium |
| 4.4 | ✅ **SETTLED: added `params` to `ItemDef` (2026-08-01).** Effects now read `effect_values` = `stats` overlaid with `params`, so magnitudes that are not stats (Bramble Vest's reflect) are expressible. Bramble Vest is implemented as proof; the loader rejects `params` without an `effect_id`. Previously: item effects read their magnitude from the item's own `stats` block. | `ItemDef` has no `params`. So Spear of Shojin's bonus mana *is* its `mana: 15` stat, Guinsoo's stack size *is* its `attack_speed_pct: 0.10`. Keeps numbers in data. Awkward for effects whose magnitude isn't a stat the item grants (e.g. Bramble Vest's reflect) — those stay unimplemented. | **High** — blocks a class of item effects |
| 4.5 | Item stat keys use an explicit `_pct` suffix (`attack_speed_pct`, `attack_damage_pct`) for percentage bonuses; the key set is closed and validated. | Doc 02's example is ambiguous about flat vs percent. Percentages multiply the post-flat value. | Medium |
| 4.6 | Ability power baseline is **100** (= 1.0× scaling); items add flat AP. | TFT convention. | Low |
| 4.7 | `no_effect` is a registered no-op, so an item like Spatula can declare "no behaviour" without tripping the unimplemented-effect warning. | Otherwise every load logs a false warning. | Low |
| 4.8 | Radiant items are **excluded from the recipe table**. | Otherwise a radiant sharing its base's recipe makes `combine()` ambiguous. | Low |

---

## 5. Combat mechanics where doc 01 was silent (🟡)

| # | Decision | Why | Priority |
|---|---|---|---|
| 5.1 | **Casting is checked before moving/attacking** each tick. | Doc 01 sec 3.1 lists casting at step 6 but says a ready cast "interrupts attack/move behaviour this tick." Followed the prose, not the numbering. | Low |
| 5.2 | **Attack timer only accumulates while a target is in range**, and carry-over is capped at one attack period. | Prevents a unit that walked a long way from discharging a burst of stacked attacks on arrival. | Medium |
| 5.3 | **Projectiles roll crit at launch, apply mitigation on landing.** If the target dies in flight the shot fizzles: no damage, **no mana**. | Doc 01 sec 3.2 grants mana only for an attack that *lands*. | Low |
| 5.4 | ✅ **SETTLED: both readings implemented**, selected by `combat.damage_mana_post_mitigation_basis` (default `"hp_lost"`). `"after_resists"` makes the 3% term ignore shields. | Doc 01 sec 3.2 equates "post-mitigation" with "actual HP lost," which is ambiguous when a shield eats the hit. The LoL wiki confirms the 1%/3%/42.5 figures but is silent on shields, and no authoritative source settles it — so the ambiguity is represented in config rather than resolved by guess, the same pattern as entry 1.1. Note the 1% pre-mitigation term applies under either reading, so a fully-shielded tank is never cut off entirely. | Settled 2026-08-01 |
| 5.5 | **An unimplemented ability still consumes its mana/cooldown.** | Otherwise the unit sits at full mana retrying every tick, silently changing its behaviour more than a plain no-op would. | Low |
| 5.6 | **Cooldowns tick on wall-clock time**, continuing while stunned or out of range. | Was a bug (cooldowns only advanced when the unit reached the cast check, firing a tick late). | Low |
| 5.7 | **Excess crit chance above 100% is discarded**, not converted to crit damage. | Real TFT converts it via specific items. Not modelled. | Low |
| 5.8 | **Damage amp is the source's, durability the target's**; both apply multiplicatively after armour/MR. | Doc 01 sec 3.3 says amp/reduction apply after mitigation but doesn't say which side owns which. | Low |
| 5.9 | **Draw resolution**: more survivors wins, then higher total HP, then a true draw. | Doc 01 doesn't cover a timeout with both sides alive. | Low |
| 5.10 | Ordering tie-breaks use **unit `uid`**, from a process-global counter. Determinism holds for a fixed seed *and* a fixed unit-construction order; absolute uid numbers differ between processes. | Needed a stable total order. Worth revisiting if match state ever gets serialised. | Medium |

---

## 6. Player / match mechanics where docs were silent (🟡)

| # | Decision | Why | Priority |
|---|---|---|---|
| 6.1 | **Traits count distinct champions, not unit copies.** Two Jinxes = one Sniper. | Doc 01 sec 6 says "champions with that trait fielded"; matches TFT. | Low — confident |
| 6.2 | **Board is `dict[Hex, UnitInstance]` in the player's own (team-0) frame**; `deploy_for_combat(team)` mirrors it onto whichever side they occupy. | Doc 03 sec 2.10 specifies `dict[Hex, ...]`. A player has no fixed side, so a canonical frame plus a mirror was needed. | Medium |
| 6.3 | **A combine keeps the fielded copy on the board**, salvages all items to the survivor, and returns anything over the 3-slot cap to the bag. | Doc 01 doesn't describe combine mechanics beyond "9 copies = 3-star." Matches TFT and loses nothing. | Low |
| 6.4 | **Dropping a component on a unit already holding a component auto-combines them.** | TFT behaviour; doc 01 sec 5 gives only the combination rule. | Low |
| 6.5 | A buy that would combine immediately is **allowed with a full bench**, via a temporary overflow slot. | TFT behaviour. | Low |
| 6.6 | **Odd player count → ghost fight** against a clone of another living player's board. | Doc 01 sec 1 doesn't cover odd counts after eliminations. Cloned so the source board is never mutated. | Medium |
| 6.7 | **On a draw, both players take only the stage base damage.** | Doc 01 sec 7 covers a loser, not a draw. | Low |
| 6.8 | **Rematch avoidance = 2-round memory**, otherwise a random legal pairing. | Doc 01 sec 1 calls a "simplified round-robin-ish or random-avoid-repeats scheme" reasonable. | Low |
| 6.9 | **Simultaneous eliminations** share adjacent placements, tie-broken by seat id; surviving players rank by HP then seat. | Needed a deterministic total order. Real TFT breaks simultaneous KOs differently. | Low |
| 6.10 | **All illegal actions raise `IllegalAction`** rather than no-op. | Doc 03 sec 2.10 requires this so the RL wrapper can mask cleanly. | Low — confident |
| 6.11 | Match ends at 1 survivor **or** stage > `max_stages` (9). | Safety cap against a non-terminating game. Never hit in testing (games run 24–31 rounds). | Low |

---

## 6b. RL environment (milestone 6) (🟡)

| # | Decision | Why | Priority |
|---|---|---|---|
| 6b.1 | ✅ **SETTLED — keep two-step SELECT → PLACE.** The premise that splitting a move across two correlated actions is hard to learn did not survive measurement: a cloned policy follows a SELECT with a PLACE **100%** of the time, and the real errors are picking the wrong shop slot or hex. See section 15. | Settled 2026-08-01 |
| 6b.2 | **Bench→bench moves are excluded from the mask.** | Bench order carries no meaning in TFT, so allowing them would waste an action on a no-op. | Low |
| 6b.3 | **Illegal actions are caught by the env, not propagated** — `info["illegal_action"]`, a configurable `invalid_action_penalty` (default 0), and `strict_actions=True` to re-raise. | Doc 03 sec 2.10 says the engine raises "so the RL wrapper can catch-and-mask illegal actions cleanly" — the engine still raises; the wrapper absorbs. Required for Gymnasium's API checker and for SB3, which both sample the raw action space. | Medium |
| 6b.4 | **`max_actions_per_round = 12`.** | Doc 03 sec 3.2 suggests "up to 8"; 8 proved tight once SELECT/PLACE costs two actions per placement. | Medium — interacts with 6b.1 |
| 6b.5 | ✅ **Champions encoded as a normalised index + cost + star + item count** (4 floats/slot). **Tested against the alternative and kept.** | See the resolution below — the richer encoding measured *worse*. | Settled 2026-08-01 |
| 6b.6 | **Observation is a flat `Box(-1, 1, (206,))`**, every feature normalised. | Works with an off-the-shelf MLP policy. Size scales with the dataset — the full Set 17 data will widen it without a code change. | Low |
| 6b.7 | **`item_bag_slots = 10`** caps how many bagged items are addressable. | The bag is unbounded in principle; the action space needs a fixed width. | Low |
| 6b.8 | **Opponent features are HP / level / streak only.** | Doc 03 sec 3.1 explicitly defers full board scouting to v2. Enforced by a test asserting an opponent's board cannot change the observation. | Low — per spec |
| 6b.9 | **Reward is terminal-only by default**: `(9 - placement) / 8`. Shaping behind `reward_shaping=True`, capped at ±0.05/step. | Doc 03 sec 3.3 recommends starting sparse. | Low — per spec |
| 6b.10 | **A selection consumed by a combine is silently dropped** rather than erroring. | Buying a unit's third copy can combine away a SELECTed bench unit. Was a live bug. | Low |

---

## 6c. Training (milestone 7) (🟡 / 🔴)

| # | Decision | Why | Priority |
|---|---|---|---|
| 6c.1 | **MaskablePPO (`sb3-contrib`)**, not plain SB3 PPO. | Doc 03 sec 3.4 says "PPO (e.g. via stable-baselines3 or a custom implementation)". With 489 actions and only a handful legal at any moment, unmasked PPO would spend its budget learning the interface rather than strategy. Doc 03 sec 3.2 already assumes masking. | Low — strictly better |
| 6c.2 | 🔴 **Training needs reward shaping**, contrary to doc 03 sec 3.3's "start without shaping". | Measured, not assumed: with terminal-only reward, episode reward stdev is **exactly 0.0000** — an untrained policy places 8th in every game, so all returns are identical and PPO has no gradient at all. Doc 03 sec 3.3 anticipates this ("only adding shaping if training is too slow/unstable"); this is that case, reached immediately rather than eventually. | **High** — a documented deviation |
| 6c.3 | ✅ **SETTLED: replaced with potential-based shaping.** `shaping_mode="potential"` (default) uses `F = gamma * phi(s') - phi(s)`; `"bonus"` keeps the old standing payment for comparison. | The old form was measured reward-hacking exactly as this entry feared — see section 13. | Settled 2026-08-01 |
| 6c.4 | **Weights `board=0.03`, `survival=0.01` per round.** | Over ~27 rounds this totals ~1.0, comparable to the terminal reward's 0.125-1.0 range. Deliberately not tuned further. | Medium |
| 6c.5 | **`gamma=0.999`.** | A match is ~27 rounds x ~5 actions = ~135 steps; a lower discount would not reach the terminal reward. | Low |
| 6c.6 | **`rl/evaluate.py` is a new module** not in doc 03's layout, holding the metrics harness and the scripted/random baselines. | Doc 03 sec 4 names win rate and average placement as the success metric but gives no home for measuring them. | Low |
| 6c.7 | **`scripted_policy` mirrors `GreedyPolicy` through the action space.** | Serves as the ceiling check — it reaches 4.47 average placement, confirming the action space is expressive enough. Without it there is no way to tell "the agent hasn't learned" apart from "the agent cannot express good play". | Low — diagnostic only |
| 6c.8 | **Behaviour-cloning warm start (`--warm-start N`)** from the scripted policy, before PPO. | From-scratch PPO stayed flat at 8.000 across 100k steps even with board shaping (see 6c.9). Inspecting the trained policy showed it had collapsed to `END_PLANNING` every round — peak board size **0**. Discovering the BUY → SELECT → PLACE chain by chance is too rare to bootstrap from. Cloning starts PPO near competent play instead of at nothing. | **High** — currently the only route past the baseline |

### 6c.9 Measured training results (starter dataset, seat 0 vs 7 greedy bots)

| run | shaping | steps | avg placement |
|---|---|---|---|
| baseline: do nothing | — | — | 8.000 |
| baseline: random legal | — | — | 8.000 |
| baseline: scripted heuristic | — | — | **4.467** |
| PPO from scratch | survival only | 150k | 8.000 (flat throughout) |
| PPO from scratch | board strength | 100k | 8.000 (flat throughout) |
| behaviour cloning only (30 epochs) | board strength | — | 7.100 |
| BC warm start + PPO | board strength | 120k | 7.400 final, 6.700 best at 90k |
| *after fixing 6c.10:* cloning only | board strength | — | 6.450 |
| *after fixing 6c.10:* BC + PPO | board strength | 120k | **6.250 final**, 6.100 best at 90k |

Fixing the selection-state defect (6c.10) moved every figure: cloning 7.10 →
6.45, final 7.40 → **6.25**, top-4 0% → **25%**. Still short of the scripted
4.47, and the run still oscillates (6.65 → 7.25 → 6.10 → 7.20 → 6.25) rather
than converging — PPO keeps drifting off the cloned policy and partially
recovering. Stabilising that (lower learning rate, KL penalty toward the cloned
policy, or lower `ent_coef`) is the obvious next lever.

The warm start is what breaks the flat-8.000 barrier, but the result is
unstable: 7.900 → 7.200 → **6.700** → 7.600 → 7.400. PPO drifts away from the
cloned behaviour after ~90k steps. Cloning itself plateaus at **63% action
match**, which is the ceiling PPO starts from — see 6c.10 for the likely cause.

| # | Decision | Why | Priority |
|---|---|---|---|
| 6c.10 | ✅ **FIXED (2026-08-01).** The observation now carries a 7-feature selection block: holding-a-unit flag, which slot, board-vs-bench, and the held unit's champion / cost / star / attack range. Measured effect: BC action match 63.1% → 65.7%, after-cloning placement 7.10 → **6.45**, top-4 10% → **20%**. Previously: **the observation did not encode selection state** — neither *whether* a unit is held nor *which* one. | Verified directly: after a `SELECT`, the only observation feature that changes is `actions_left`. The action mask gates legality, so the agent cannot act illegally, but the policy network is blind to the state that determines whether `SELECT` or `PLACE` is correct and where a held unit should go (melee front / ranged back). This is the most likely reason behaviour cloning plateaus at 63%. **This is a defect, not a trade-off — it should be fixed.** Fixing it changes the observation shape and invalidates saved checkpoints, so it needs a retrain. | Done |

Reward variance measured under a random policy: **0.0000** with terminal-only
reward, 0.0028 with survival shaping, 0.0079 with board shaping (scripted
scores 1.136 ± 0.45 under the same shaping). The gap between random and
scripted is large; the problem is that random play never reaches the states
where that gap appears.

---

## 7. Deliberately deferred (⚪)

| # | Not built | Doc says | When |
|---|---|---|---|
| 7.1 | **PvE creep boards.** PvE rounds resolve as free wins: income paid, no streak, no damage. | Doc 01 sec 1: stage 1 "can be stubbed." | Drops into `Match._fight_creeps` alone |
| 7.2 | **Set 17 Realm of the Gods** — Minor Blessings at 2-4/3-4/4-4, God Boon shop at 4-7, low-HP catch-up. | Doc 01 sec 1 describes it as its own system. | Milestone 9 |
| 7.3 | ~~**Augments.**~~ ✅ | Doc 01 sec 8 recommends stubbing for v1. | Built at milestone 9 — system complete, catalog synthetic (section 17) |
| 7.4 | **Consumables** (`consumables.json`). | Doc 02 sec 3.10: "safe to stub/skip for v1." | Milestone 9 |
| 7.5 | **Item effects.** ⚠️ This entry was written against the 13-champion starter sample and is superseded by §33.1: after the milestone 8 data swap the real figure was **36 of 49** non-emblem items unimplemented, not the four named here. Their *stats* all apply. | Doc 02 sec 2 explicitly allows partial coverage. | §33 |
| 7.6 | **Abilities**: `gragas_body_slam`, `ornn_volcanic_rupture`, `spacegroove_regeneration`. Left unimplemented **on purpose** to keep the warn-once-and-no-op path exercised in tests. | doc 02 sec 2, doc 03 sec 2.4 | Ongoing |
| 7.7 | **Mana lock** after casting (real TFT briefly blocks mana gain post-cast). | Not mentioned in doc 01. | Unclear if needed |
| 7.8 | **Shield decay** and damage-type-specific shields — the data model supports both (`Shield.remaining`, `Shield.damage_type`); no current effect uses decay. | doc 01 sec 3.3 mentions both | Ongoing |

---

## 8. Open items

What is actually unresolved, as of entry 32. Everything previously listed here
has been settled and moved to the closed table below.

### Open

Deliberately **unnumbered**. This is a worklist that changes as items close,
and numbering it invites citations that survive the item they pointed at — a
stale `8.5` reference in `scripts/fetch_cdragon.py` (it meant 9.5) is what
prompted `scripts/check_doc_refs.py`. Cite the journal entry, not this list.

| Item | Where |
|---|---|
| **The agent is at its teacher and cannot pass it by imitation.** The clone places 4.567 against a 4.620 scripted heuristic. Imitation caps at the teacher by construction, and every PPO configuration tested from that clone is a null or worse. The remaining routes are a better expert or an RL setup unlike any tried. | §31.4, §32.4 |
| **The scripted expert is deliberately crude.** It ignores champion abilities when valuing units, itemises by a single-carry rule, and positions only by melee/ranged. Raising it raises the imitation ceiling directly — currently the clearest lever on the item above. | §6c.7, §31.4 |
| ~~29 of 63 abilities remain unimplemented~~ ✅ **Closed at §35.** All 63 abilities, 35 traits and 65 items are implemented. What remains is not content but *mechanisms*: the player-choice traits of §35.4 and the partial omissions of §35.5. | §9.8, §11.2, §16, §35 |
| **The augment catalog is not Riot data.** The Set 17 payload carries no usable generic pool and no tier field, so the shipped 14 are archetypes exercising the hooks. The augment *system* is complete. | §17.1 |
| **Set 17's God Boon / armoury at 4-7 and the two-gods alignment mechanic are not modelled.** Only the carousel-spirit contested draft is. | §21.1, §7.2 |
| **Single training seed throughout §29–32.** Sufficient for reverting a default to neutral, not for asserting a new claim. | §31.4 |
| **`nokl` at 120k was noisy** (4.777 / 5.157 / 4.853 / 4.600). A longer multi-seed run would separate drift from progress. | §31.4 |

### Closed

~~1.1 shop draw weighting~~ ✅ keep `by_copies`.
~~1.2 re-target-every-tick~~ ✅ sticky targeting.
~~2.1 config.json schema~~ ✅ stays curated; doc 02 sec 4b added.
~~3.1 / 3.2 XP and round-damage tables~~ ✅ flagged, sought at milestone 8.
~~4.4 item effect magnitudes~~ ✅ `params` added to `ItemDef`.
~~5.4 shields vs tank damage-mana~~ ✅ both readings in config.
~~6b.1 SELECT/PLACE two-step moves~~ ✅ structure is learned perfectly; not the bottleneck (§15).
~~6b.5 champion encoding as a scalar index~~ ✅ tested and kept; rejected three times over (§10, §26.2, §27.4).
~~6c.3 board-strength shaping~~ ✅ was reward-hacking; now potential-based (§13).
~~6c.10 observation missing selection state~~ ✅ fixed (§6c.10).
~~7.3 augments~~ ✅ system built at milestone 9 (§17).
~~9.1 star scaling~~ ✅ verified against Bel'Veth's in-game per-star values (§12).
~~9.2 role mapping~~ ✅ Specialist role added, two role perks implemented (§14).
~~11.3 multi-hit abilities~~ ✅ implemented.
~~17.5 / 17.6 scouting and self-play unmeasured~~ ✅ measured (§19), then both verdicts overturned (§22.2, §22.3, §31.2).
~~18.2 the untrained critic~~ ✅ fixed; was not the bottleneck (§18, §22.1).
~~19.3 PPO contributes nothing over BC~~ ✅ superseded — it *degrades* a weak clone (§22.1) and is a null from a good one (§31.3).
~~22 the imitation gap is compounding off-policy drift~~ ✅ refuted; it was BUY, and BUY was representational (§24.2, §29).
~~25.2 the observation cannot express the BUY rule~~ ✅ refuted as stated, then vindicated in a different form — raw traits did nothing, the *comparison* did everything (§27.2, §29.1).
~~26.1 the BUY ceiling is 90.7%~~ ✅ corrected to 67.7% (§28.1).
~~27.2 a set/attention encoder is needed~~ ✅ not needed for BUY, SELECT or PLACE; derived relational features sufficed (§30.5).
~~31.3 unleashed PPO is a gain under ranked LP~~ ✅ corrected — it is a null under LP too (§32.1).

---

# Part II — Journal

Dated entries, newest last. Each records a question, what was
measured, and what changed as a result. Entry numbers are stable and
cited from code; superseded entries keep their number and carry a
banner naming the entry that replaced them.

---

## 9. Milestone 8 — real Set 17 data (2026-08-01)

Calls made while normalising the live CDragon payload. All were authorised as
"your best call … unless further searches disprove those"; where a search
*was* run to check one, the outcome is noted.

| # | Call | Why | Priority |
|---|---|---|---|
| 9.1 | ✅ **VERIFIED — star scaling ×1.8 health / ×1.5 attack damage.** Riot ships one scalar per stat and the game applies the multiplier, which is absent from the payload. Confirmed twice: the LoL wiki's TFT:Champion page (AD 100/150/225%, health 100/180/324%), and directly against Bel'Veth's in-game per-star values — health 750/1350/2430 matches exactly, AD 47/70.5/105.75 matches the displayed 47/71/106 modulo integer rounding. | Settled 2026-08-01 |
| 9.2 | ✅ **SETTLED — and the model was wrong in three ways.** Riot documents **six** team roles, not five; `Specialist` was missing and its two Set 17 champions were being forced into Caster. Two role perks were also unmodelled: Caster **+2 mana/second** and Fighter **10% omnivamp**. All three are now implemented; see section 14. | Settled 2026-08-01 |
| 9.3 | 🟡 **`role: null` falls back on attack range** (≤1 melee → Fighter, else Caster). | Set 17's Miss Fortune ships no role. Affects exactly one unit. | Low |
| 9.4 | 🟠 **Zero base stats backfilled with the cost-tier median.** | LeBlanc and Riven ship `damage: 0`, which would leave them unable to attack or generate mana. A median re-derives itself each patch instead of baking in a constant, but it is still an invented number. | Medium |
| 9.5 | 🟡 **`mana: 0` treated as "not mana-gated"**, replaced with 100. | Caitlyn ships `mana: 0`; the schema requires a positive pool. Practically inert while no abilities are implemented. | Low |
| 9.6 | 🟡 **Ability variables read from indices 1..3.** | Verified empirically: 151 of 168 varying variables rise monotonically over exactly those indices, and spot checks (Jinx 29/44/70, Briar 120/180/285) match plausible per-star progressions. Index 4 is an unused 4-star slot. | Medium — confident |
| 9.7 | 🟡 **Unmapped item variables never become stats.** Only 10 Riot keys map to modelled stats; the rest fall through to `params`. | Riot mixes units across keys (`AD` is a fraction, `AS`/`CritChance` are percentages), so guessing an unknown key's units would silently corrupt derived stats. Cost: real item effects are largely inert. | Medium |
| 9.8 | 🟡 **Every champion ability gets `effect_id: "ability_<id>"`, unimplemented.** | Preserves the per-star params in the data file and surfaces the gap as one warn-once per champion, while units still auto-attack with correct stats (doc 02 sec 2). Nothing casts yet. | **High** — 63 abilities are no-ops |
| 9.9 | 🟡 **Item pool limited to components + advanced + emblems (65).** Radiant, artifact, consumable and set-mechanic items excluded. | They need mechanics the engine does not model. The 10 components match doc 02 sec 3.4 exactly. | Medium |
| 9.10 | 🟡 **Origin-vs-class curated from doc 02 sec 3.1/3.2**, defaulting to `origin`. | Riot does not publish the split. The doc's 20+15 lists reconcile exactly with the 35 traits fetched. | Low |
| 9.11 | 🟡 **Starter dataset frozen as `tests/fixtures/starter_data/`**, and the existing suite repointed at it. | Its hand-calculated expectations are what make those ~488 tests meaningful; asserting them against patch-varying data would destroy that. Real data is covered separately by `tests/test_real_dataset.py`, which asserts invariants only. | Medium |

---

## 10. Entry 6b.5 resolved — the scalar index encoding stays

Entry 6b.5 flagged the scalar champion index as "likely limits learning," and
milestone 8 made it look worse still: the real set has 63 champions, not 13, so
the encoding compresses ~5x more distinct units into one float. It was the top
recommendation after the data swap.

**Measurement did not support it.** A `features` encoding was implemented
(role one-hot + normalised base stats + trait multi-hot; 47 floats per slot
against 4, 2056 observation dims against 240) and compared against `index` by
behaviour-cloning the scripted policy and evaluating over 60 unseen seeds:

| budget | `index` match → placement | `features` match → placement |
|---|---|---|
| 150 ep, 25 epochs | 62.4% → 7.78 | 64.4% → 7.58 |
| 150 ep, 50 epochs | 71.6% → 6.78 | 90.3% → **7.42** |
| 400 ep, 50 epochs | 80.4% → **6.05** (top4 22%) | 91.8% → 6.95 (top4 8%) |

`features` imitates the expert far more accurately at every budget and plays
**worse** at every budget. The obvious explanation — overfitting that more data
would fix — predicts the gap closing as expert episodes grow; 2.7x more data
did not close it. The likelier cause is that most of the added width is sparse
trait bits spread across 28 mostly-empty board slots, so the encoding adds
dimensionality faster than signal.

**Decision:** `index` stays the default. `features` remains available behind
`champion_encoding="features"` (env, encoder, and `train_ppo.py
--champion-encoding`) so the comparison is reproducible and so a future
attempt — with a set/attention encoder over occupied slots only, per doc 03
sec 3.1 — has somewhere to start.

**Caveat on scope:** this was behaviour cloning only, with no PPO phase. It is
evidence about how well each representation supports imitation and generalises
off the expert's state distribution, not about the final achievable ceiling.

**What this redirects attention to.** The agent's real gap is not the
observation encoding. Against a scripted ceiling of ~4.5 average placement, BC
alone reaches 6.05 — and the same pipeline reached 6.45 on the 13-champion
starter set, so the swap to real data made the problem materially harder while
every one of the 63 abilities is still an unimplemented no-op (entry 9.8).
Implementing real abilities is now the better lever than encoding work.

---

## 11. Milestone 8b — real abilities (2026-08-01)

Direction: "heuristic then verify online … hands free yet highly accurate."

**Approach: classify from Riot's description markup, not variable names.**
Riot uses 240 distinct ability-variable keys across 63 champions (`Damage`,
`APDamage`, `ADDamage`, `DamageAP`, `DamageAD`, …), so key names are weak
evidence. The description carries semantic markup that is much stronger:

    "...dealing <physicalDamage>@TotalDamage@ (%i:scaleAD%)</physicalDamage>"

The damage-type tag classifies 60 of 63 abilities; the other 3 genuinely deal
no damage (Poppy shields, Zed clones, Miss Fortune picks a mode). Structure
comes from the markup; only magnitude lookup uses key names, narrowed by the
damage type so a physical ability can never pick up an AP variable.

**Magnitude semantics, confirmed from the payload:** magic abilities carry
flat `Damage` scaled by AP; physical abilities carry a *percentage* of AD
(Briar's 120/180/285 is 120%/180%/285% AD). Shields are flat.

**Online verification** (as requested), sampling the classified output:

| champion | ours | source | verdict |
|---|---|---|---|
| Veigar | `damage` 330/495/750, magic | "330/495/750 magic damage" | ✅ exact |
| Poppy | `shield` 400/475/575 | shield ability, no damage | ✅ correct |
| Kindred | `ad_ratio` 1.15/1.75/9.0 | "115/175/900% AD" | ⚠️ number real, **wrong ability** |

The Kindred check is why this section exists. 900% AD looked like a parsing
bug and is in fact Riot's real number — but it belongs to her *passive*, while
her *active* fires arrows at 3–5 targets for 75/115/600% AD. We were casting
the passive's magnitude as a single-target active.

**Consequence — refuse passive/active splits.** The `@Var@` references in the
description are computed display names (`ModifiedDamage`, `TotalDamage`) that
do not resolve back to raw variables, so nothing in the payload says which
number belongs to the active cast. Rather than approximate, `classify_ability`
declines whenever both `<spellPassive>` and `<spellActive>` are present. That
dropped coverage from 41/63 to **28/63** and is the right trade: a
mis-assigned ability looks healthy while silently corrupting combat, whereas
an unimplemented one warns once and no-ops (doc 02 sec 2).

| # | Call | Priority |
|---|---|---|
| 11.1 | 🟡 **Effect structure from description markup**, magnitude from damage-type-narrowed key names. | **High** — decides what 28 champions do |
| 11.2 | 🟡 **Decline rather than approximate**: no damage tag, no usable variable, or a passive/active split all yield an unimplemented placeholder. | **High** — this is the accuracy guarantee |
| 11.3 | ✅ **RESOLVED — multi-hit abilities implemented.** `multi_hit_magic_damage` / `multi_hit_physical_damage` apply `hits` damage instances spread over `targets` enemies, both defaulting to 1. Detection is double-gated: a count variable *and* an "each"-style cue must both be present, so a single-hit ability is never silently multiplied. Target-counts (`NumTargets`) and `...Per...` rates are excluded. Four champions qualify (Akali 5, Bel'Veth 12, Jinx 16, Kai'Sa 16); Jinx's cast went from 33.8 damage to ~540. | Settled 2026-08-01 |
| 11.4 | 🟡 **Raw variables retained alongside canonical keys**, so implementing a better effect later needs no re-fetch. | Low |

**Known remaining gap (11.3).** The single largest fidelity issue now. Riot
ships the counts (`NumAttacks`, `NumArrows`, `RocketsPerLaunchAttack`) and the
descriptions say "each", so a multi-hit effect is buildable — it needs a new
generic effect rather than better parsing, which is why it was not folded in
here. Until then, carries with multi-hit abilities are underpowered.

---

## 12. Base-stat verification against the wiki (2026-08-01)

While checking multi-hit magnitudes, a community site's per-hit numbers for
Bel'Veth (25/38/57) and Kai'Sa (33/50/79) came out ~2.4x higher than ours.
Dividing those by our AD ratios gives an implied attack damage that is
*constant across star levels* (113.6 / 115.2 / 114.0), which means that site
computes its display with one fixed AD rather than the star-scaled value — so
its figures are not directly comparable. Our model applies the ratio to the
unit's derived AD, which does scale with stars and items, as real TFT does.

To rule out the alternative — that our base stats were simply wrong — Bel'Veth
was checked against the LoL wiki directly:

| stat | ours | wiki |
|---|---|---|
| cost | 2 | 2 |
| health | 750 | 750 |
| attack damage | 47 | 47 |
| armor | 45 | 45 |
| magic resist | 45 | 45 |
| attack speed | 0.75 | 0.75 |

Exact on every field, which validates the whole champion-normalisation path
(entry 9.x), not just this one unit. Hit counts were separately confirmed from
Riot's text: Bel'Veth 12 slashes, Kai'Sa 16 missiles.

**Still unverified:** the derived per-star arrays (entry 9.1) — the wiki page
gives 1-star values, so the 1.8x/1.5x multipliers remain an approximation.

---

## 13. Entry 6c.3 resolved — the shaping was reward-hacking

The first PPO run on real data (`runs/real-data-150k`, 150k steps, BC warm
start) produced a flat result: behaviour cloning alone reached 5.90 average
placement, PPO finished at 5.77. With a 30-episode evaluation the 95% CI is
±0.73, so that difference is indistinguishable from zero, and the apparent
checkpoint "oscillation" (5.53–6.33) spans only 1.1x the CI half-width — it was
noise, not a trend.

**The diagnosis was not what the flat curve suggested.** PPO's own internals
were healthy throughout:

| metric | value | reading |
|---|---|---|
| `explained_variance` | 0.76 → 0.80 | the critic predicts ~78% of return variance, so advantages carry real signal |
| `approx_kl` | 0.014 | stable, no collapse |
| `clip_fraction` | 0.11 | normal |
| `entropy_loss` | flat −0.85 | still exploring |

And the agent *did* optimise: episode reward rose 22% (0.566 → 0.693). But the
terminal reward is `(9 - placement) / 8`, so the 0.23 placement improvement
accounts for only +0.029 of that. **The remaining +0.098 — 77% of the gain —
came from shaping.** The agent was maximising the reward it was given; the
reward simply did not track winning.

**Cause.** The old shaping paid a per-round bonus for holding a strong board.
Summed over an episode that totals about **+0.120**, against a terminal reward
of 0.125 — so roughly half the agent's grade was the proxy rather than the
objective.

**Fix.** Potential-based shaping, `F = gamma * phi(s') - phi(s)` (Ng, Harada &
Russell 1999), with `phi` combining normalised board strength and HP. The
per-round terms telescope, so the episode total collapses to a boundary term
and **cannot change which policy is optimal** — it only shifts credit earlier.
Measured over full episodes:

| mode | total shaping | grows with episode length? |
|---|---|---|
| `potential` | −0.0101 | no |
| `bonus` | +0.1200 | yes |

`"bonus"` is retained behind `shaping_mode` so the comparison stays
reproducible, and `tests/test_shaping.py` asserts both the invariance property
and the contrast, so neither can silently rot.

**Measurement also fixed.** `--eval-episodes` now defaults to 100 rather than
20. At 30 episodes the CI was wider than the effects worth detecting, which is
how the noise got read as a trend in the first place.

**Caveat.** Potential-based shaping is guaranteed not to *mislead* the agent;
it is not guaranteed to *help*. If the remaining gap is exploration or budget,
the next run will land near BC's 5.90 — which would still be informative, since
it rules out reward misalignment as the explanation.

### 13.1 Outcome of the potential-shaping run

`runs/potential-150k` — same budget, potential-based shaping, 100-episode
evaluations.

**The fix worked at its stated purpose.** Decomposing the reward gain:

| run | reward gain from placing better | from shaping |
|---|---|---|
| `real-data-150k` (bonus) | 23% | **77%** |
| `potential-150k` (potential) | **73%** | 27% |

The agent is now being graded on the objective rather than the proxy, and the
critic is healthier still (`explained_variance` 0.86).

**But absolute performance barely moved.** BC alone 6.16; the trained policy
read 6.11 / 6.08 / 6.18 / 6.18 / 6.04 / 6.05 across checkpoints and 5.68 at the
final update. With a 95% CI of ±0.38 (n=100), only that last point separates
from BC at all, and it sits ~1 CI half-width from its neighbours — weak
evidence of a real gain rather than a clean improvement.

**Conclusion: reward misalignment was a genuine defect, but not the
performance bottleneck.** It was worth fixing — the old shaping was provably
distorting the objective, and that is now ruled out as an explanation — but the
gap to the scripted policy (4.65 on the same 100 seeds) is ~1.0–1.5 placement
and remains unexplained.

**Cross-run comparisons are not clean.** Between the two runs the evaluation
size changed (30 → 100 episodes) *and* combat changed (multi-hit abilities, entry
11.3). BC alone reads 5.90 in the first and 6.16 in the second; the scripted
ceiling reads 4.30 and 4.65. Only within-run comparisons are trustworthy.

Remaining candidates for the gap, none yet tested: the SELECT/PLACE action
space (**6b.1**), exploration, or simply far more compute than 150k steps.

---

## 14. Entry 9.2 resolved — the role model was missing a role and two perks

Entry 9.2 flagged the Riot-role -> our-role mapping as approximate, with
`ADSpecialist` -> Caster as the weakest link. Checking it against Riot's own
role-revamp article turned up more than a bad mapping.

**Riot documents six team roles, each with mana-per-attack and some with an
extra perk:**

| role | mana/attack | perk |
|---|---|---|
| Tank | 5 | builds mana from damage taken; increased targeting priority |
| Fighter | 10 | **10% omnivamp** |
| Assassin | 10 | reduced targeting priority |
| Marksman | 10 | — |
| Caster | 7 | **+2 mana per second** |
| Specialist | unique | generates resources its own way (Riot's example: Kayle generates none) |

Doc 01 sec 3.2 lists only the first five and none of the perks. Three fixes:

**14.1 — `Specialist` added to `ROLES`.** Riot's payload pairs a damage type
(AD/AP/H) with a team role, so `ADSpecialist` is Attack-damage Specialist, not
a Caster variant. Set 17 ships two (Caitlyn, Gnar). They now carry
`mana_per_attack: 0`, modelling the documented "generates none" case. This is
flagged in `config.unverified`: Riot says Specialists are unique but publishes
no per-champion rule, so 0 is a defensible default rather than a known value.
It interacts with entry 9.5 — Caitlyn ships `mana: 0` in the payload, which now
reads as "Specialist, not mana-gated" rather than as missing data.

**14.2 — Caster mana regeneration.** `combat.role_mana_per_second` grants 2
mana/second to Casters, applied per tick in `step()` so it continues while the
unit is stunned, kiting or out of range. Affects 18 of 63 champions and makes
casters cast meaningfully more often.

**14.3 — Fighter omnivamp.** `combat.role_omnivamp` gives Fighters 10%
lifesteal on damage dealt. Note `DerivedStats.omnivamp` already existed and was
**never read anywhere in combat** -- item omnivamp was silently dead. Wiring the
role perk activates both. Healing is measured on damage that actually landed,
so a fully-absorbed hit sustains nobody.

**Still unmodelled:** Tank's increased and Assassin's reduced targeting
priority. Both are qualitative in the source, and our targeting is nearest-first
with a uid tie-break (entry 1.2), so adding a priority weight is a real design
change rather than a constant. Left for a later pass.

The mapping itself is now confirmed rather than guessed: every Riot role maps
to a team role whose attack ranges agree (Carry/Caster ranged 4-6, Reaper and
Fighter melee 1-2, Tank melee 1), and "Carry" and "Reaper" are simply the
payload's names for Marksman and Assassin.

---

## 15. Entry 6b.1 resolved — the action space is not the bottleneck

6b.1 supposed that splitting a move into two correlated actions
(`SELECT` then `PLACE`) makes it hard to learn, and that a flat
`MOVE(from, to)` space might do better despite being ~1,400 actions wide. That
was the last structural hypothesis for the agent's gap, so it was tested before
being built: clone the scripted policy, then break imitation accuracy down by
action kind.

**The two-step structure is learned perfectly.** Across 787 expert `SELECT`
actions, the cloned policy followed with a `PLACE` **787 times — 0% broken
pairs.** Whatever the agent is failing at, it is not stringing the pair
together.

Per-kind exact-match accuracy (75.6% overall):

| action kind | n | exact match | most common error |
|---|---|---|---|
| END_PLANNING | 1315 | 96.8% | — |
| BUY_XP | 894 | 89.4% | stops planning instead |
| PLACE | 787 | 75.3% | **a different hex** |
| SELECT | 787 | 66.3% | stops planning instead |
| BUY | 1426 | **52.7%** | **a different shop slot** |

The two worst categories fail *within* their own action kind: `BUY` picks the
wrong shop slot and `PLACE` picks the wrong hex. Those are content decisions —
which unit is worth buying, which hex suits this unit — not interface
mechanics. A flat `MOVE` space would not touch either, and would cost ~3x the
action-space width.

**Decision:** keep SELECT/PLACE. Building the alternative was avoided on the
evidence, as with entry 6b.5.

**Re-measured reference on current combat** (after entries 11.3, 5.4 and 9.2
changed the engine): behaviour cloning alone reaches **6.10**, the scripted
policy **4.36**, over 100 seeds. Earlier figures in sections 13 and 13.1 predate
those changes and are not comparable.

**What is left.** Three structural hypotheses have now been tested and rejected
— observation encoding (6b.5), reward shaping (6c.3), action space (6b.1). The
gap of ~1.7 placement is concentrated in decision quality on `BUY` and `PLACE`,
where the expert's choices depend on champion-specific judgement. Notably 6b.5
found that giving the network richer champion features *improved imitation
substantially* (80% -> 92% action match) while making play slightly *worse*,
which suggests imitating this particular scripted policy is close to exhausted
as a strategy. The remaining levers are more compute, a stronger expert, or
self-play — not another environment fix.

---

## 16. Ability coverage — widened magnitude lookup (2026-08-01)

Follow-up to sections 11 and 15. Of the 35 declined abilities, an initial
survey suggested 14 were "unambiguous, just an unrecognised variable name".
**That estimate was wrong** — inspecting them showed several carry *three*
damage variables with nothing to say which belongs to the cast (Pyke:
SpearDamage / AoEDamage / TargetDamage; Fizz and Sona likewise), and others
needed capabilities the engine lacked.

Three general rules were added rather than per-champion fixes:

| # | Rule | Why |
|---|---|---|
| 16.1 | **Flat physical damage** (`flat_physical_damage`). A plain `Damage` on a physical ability is an absolute value, not a share of AD. | Riot uses both forms and the engine only supported the ratio one. `ap_ratio` is pinned to 0 so it does not scale with AP. |
| 16.2 | **`*AD`-suffixed variables are ratios.** | Corki's `MissileAD` is [28, 42, 280] — a percentage of AD, matching Jinx's `ADDamage` 29/44/70. It contains no "damage" substring, so the generic fallback picked up `MeepDamage` (a set-mechanic bonus) instead — a verified mis-assignment, caught by auditing every newly classified ability. |
| 16.3 | **Per-second damage becomes a volley over its duration.** | Aurelion Sol channels for `Duration` seconds dealing `DamagePerSecond`; one hit understates it by the channel length. Reuses the entry 11.3 volley effect. Declines when no duration is published. |

All three are gated by **"unique candidate or decline"**: the fallback search
ignores names that *modify* a damage (`Amp`, `Mult`, `Reduction`, `Threshold`,
`Ratio`) and succeeds only when exactly one candidate remains. That is what
keeps Pyke, Fizz and Sona correctly declined.

**Result: 28 -> 34 of 63 abilities implemented.** Newly covered and audited
against their descriptions: Cho'Gath, Mordekaiser, Pantheon, Rhaast, Aurelion
Sol, Corki.

**Known approximations among the new six:** Mordekaiser is primarily a shield
champion whose damage component was classified (his shield is not modelled);
Pantheon's cone is treated as single-target. Both are under-modelled rather
than wrong in kind.

**Remaining 29 declined**, unchanged and deliberately so: 12 opaque
passive/active splits, ~15 with multiple indistinguishable damage variables,
and 2 with no damage at all (Zed's clone, Miss Fortune's mode select). Closing
these needs per-champion knowledge that the payload does not contain.

---

## 17. Milestone 9 — augments, self-play, board scouting (2026-08-01)

Doc 03 milestone 9 is one line ("(Stretch) Augments, self-play, full
board-scouting observations"), so nearly everything here is a judgement call.

### 17.1 Augments are **not** Riot-sourced, and could not be

This is the significant finding of the milestone, and it breaks the project's
standing rule that Riot is the source for everything.

The cached CDragon payload was surveyed directly. It contains **43 entries**
matching `TFT17_Augment_*`. That is far short of a real set's pool (200+), and
the ones present are almost entirely bespoke:

* *God Augments* and their quest chains — "Aurelion Sol's Boon", which offers
  a sub-choice of three quests, each with its own multi-round trigger.
* *Carry augments* — "Gain a Nasus. Your strongest Nasus becomes an Attack
  Fighter with a single target Ability that gets stronger…", i.e. an entire
  replacement ability per augment.
* *Trait-conditional effects* — "Conduit Abilities last 25% to 50% longer,
  depending on the Ability."

Two blockers, both checked rather than assumed:

1. **No tier field.** `AUGMENT_TIERS` (silver/gold/prismatic) has no
   counterpart in the payload. The closest signal is a roman-numeral suffix on
   the icon path (`Concentration_II.tex`), which resolves for only 30 of the 43
   — the rest are `Missing-T2.tex`, `ADMIN_Armorery_Icon.tex`, or plain names.
   Assigning tiers would be guessing, and tier drives which augments are
   offered when.
2. **No mechanically simple augments.** Doc 01 sec 8 says to wire up "a handful
   of simple augments (flat stat boosts, econ tweaks)" first. Essentially none
   of the 43 is that shape. Importing them faithfully would produce ~43
   augments that all warn-and-no-op, so every reveal round would be a choice
   between three things that do nothing — worse than useless for RL, since it
   is noise the agent is asked to respond to.

**Decision: ship 14 generic archetypes** (`data/augments.json`) that exercise
every hook the system supports — flat stats, instant gold/XP/items, per-round
income, an extra board slot. They are labelled `engine_artifact` in
`config.json`'s provenance block and listed under `unverified`, so nothing
reads them as Riot data. The *system* is complete and general; only the catalog
is synthetic. Importing a real pool is a data edit, not a code change.

### 17.2 A second effect registry rather than reusing `engine.effects`

Augment hooks take a `PlayerState` and fire on a round boundary; combat effects
take a combat context and fire on a tick. Sharing one table would put two
incompatible call signatures behind one lookup, so a data typo would surface as
a `TypeError` deep inside combat rather than as a missing effect. Both
registries keep the same discipline: unknown id warns **once**, no-ops, never
crashes.

Stat-granting augments need no hook at all — any `params` key naming a modelled
stat is applied board-wide, exactly as trait breakpoint params already work. So
a purely statistical augment is pure data, and the stat half of a
partly-implemented augment still applies.

### 17.3 A separate `set_owner_bonuses` slot on `UnitInstance`

Augments could not ride on `set_trait_bonuses`: combat **overwrites** that slot
at the start of every fight from the board's own trait state, which would
silently erase them. `test_combat_trait_bonuses_do_not_erase_augment_bonuses`
pins this. Ghost boards copy the slot too — omitting it would make ghost fights
systematically easier than the real board they stand in for.

### 17.4 Augment choice is an **action**, not a seat-policy callback

The first design let the match ask each policy to choose. That works for
scripted seats but not the RL seat: `Match._planning_phase` calls the agent's
no-op policy and then immediately resolves the pick, so the agent would never
see the offer. Rather than leave a modelled mechanic outside the agent's
control — noise it is asked to respond to but cannot act on — `PICK_AUGMENT`
joined the action space (+3 actions).

Consequences, each deliberate:

* `END_PLANNING` is **masked off** while an offer is pending. TFT has no way to
  decline an augment.
* A seat may declare `defers_augment_pick`; only the RL env seat does. Everyone
  else resolves within one planning phase.
* Exhausting the action budget with an offer live still takes the first offer,
  so a live offer can never reach combat.
* `scripted_policy` and `end_planning_policy` both had to learn to pick.
  **`scripted_policy` was violating the mask** before this — it returned
  `END_PLANNING` unconditionally, which happened not to raise. Now fixed.

The scripted baseline picks the **first offer, always**, deliberately: ranking
augments needs per-augment knowledge the heuristic does not have. Augment
choice is therefore headroom a learned policy can beat rather than a target it
must match.

### 17.5 Scouting is a summary, not a board copy

`scouting="full"` exposes, per opponent: board size, board value, best star
level, average unit cost, item density, at-unit-cap flag, and their active
trait tiers. It does **not** copy their 28 hexes — that would multiply the
observation by roughly eight, and position matters far less to the decision it
feeds ("is their board stronger than mine, and what are they contesting?").

Scouting is legal in TFT — you may visit any board between rounds — so this is
not hidden information. It is **off by default** anyway: it adds 287 floats
(296 -> 583 on Set 17 data), and entry 6b.5 measured that widening this
observation with sparse features made the agent play *worse*. Treat it as a
hypothesis to measure, not an upgrade.

### 17.6 Self-play samples a pool, and does not always use the latest policy

Training only against your current self is the standard route to a cycling,
non-transitive policy. `SnapshotPool` keeps the last N snapshots and samples
per seat per episode, which is the usual fix.

* Snapshots go through `save`/`load`, not `deepcopy` — an SB3 model holds an
  optimiser, a rollout buffer and a live reference to the env it is training
  in, and deep-copying that graph would hand opponent seats a handle on the
  learner's own environment.
* Opponents are **stochastic** (`deterministic=False`); a deterministic
  opponent is a fixed target the learner can memorise one counter to.
* An empty pool falls back to `GreedyPolicy`, so `--self-play` is safe from
  step 0 and training begins against the heuristics.
* `--self-play-mix` sets what fraction of seats are snapshots. It exists
  because cost is real: every opponent action is a forward pass, for up to 12
  actions x 7 seats x ~30 rounds.
* A snapshot that emits an illegal action **ends its turn with a warning**
  rather than retrying. Silently retrying would let a stale snapshot act as a
  much weaker opponent without saying so.

Sanity check that self-play is wired correctly: an *untrained* model placed
**3.67** against seven copies of itself and **8.00** against the scripted bots.
Self-play makes the opposition exactly as weak as the learner, which is both
the point and the hazard — placement against self-play opponents is not
comparable to placement against the fixed bots, and only the latter is a
progress metric.

### 17.7 First self-play run — **inconclusive, not negative**

A matched pair was run to check the pipeline, identical but for `--self-play`
(40k steps, 4 envs, BC warm start 150 ep / 25 epochs, shaping on, 40 eval
episodes against the *fixed* bots):

| arm | scripted | after BC | final |
|---|---|---|---|
| control | 4.675 | 7.550 | 7.700 |
| self-play (mix 0.5) | 4.675 | 7.550 | **7.975** |

It would be easy to read this as "self-play hurts". **It does not support that
claim.** Two reasons:

1. **Both arms got worse than their own BC start** (7.55 → 7.70 and 7.98). At
   40k steps PPO is degrading the cloned policy in the control too, so the run
   is underpowered — earlier runs used 120–150k steps. Nothing about self-play
   is isolated by a comparison where the control is also failing.
2. **The gap is inside the noise.** 40 episodes gives a 95% CI half-width of
   roughly ±0.71 placement; the difference is 0.275, about a third of that.

What the run *does* establish is that the pipeline works end to end: snapshots
are taken, loaded, and played as seats; no illegal actions; matches terminate;
metadata records it. That was its purpose. A real measurement needs the budget
where PPO improves on BC at all, and should compare at ≥100 eval episodes.

**Corrected cost estimate.** This module's docstring originally claimed
self-play was "roughly an order of magnitude" slower. Measured over 10 episodes
with a trained policy: 4.1s at `mix=0`, 5.0s at `mix=0.5`, 7.7s at `mix=1.0` —
**1.9x**, not 10x. A policy that ends its planning phase early takes far fewer
than `max_actions_per_round` forward passes, so the naive arithmetic
overestimates badly. The docstring has been corrected to the measured figures.

Still open:

1. **17.1** The augment catalog is synthetic. Importing a real pool needs a
   payload that carries a tier field and a set of mechanically simple augments;
   this one has neither.
2. ~~**17.5 / 17.6 / 17.7** Neither full scouting nor self-play has been
   *measured* to improve placement.~~ ✅ **Settled in section 19**, once entry
   18.5 had established an operating point where anything could be measured at
   all: full scouting is significantly **harmful** (-0.303, t=-2.34) and
   self-play is **inert** (-0.147, CI spans zero). The build-then-measure order
   was the right one — both were correct implementations of bad ideas, which is
   only distinguishable by measuring.
3. **Prerequisite for measuring either.** ~~At 40k steps PPO makes the cloned
   policy *worse* in both arms.~~ **Superseded by entry 18.3:** the apparent
   degradation is inside the error bars. The real blocker is a floor effect —
   every arm places 8th in ~90% of games, so no A/B built on this operating
   point can resolve anything.

---

## 18. The value head was never trained — and that was not the bottleneck (2026-08-01)

Entry 17.7 left a blocker: PPO appeared to make the behaviour-cloned policy
*worse*. This entry records the investigation, the real defect it found, the
prediction that **failed**, and the reframing that came out of it.

### 18.1 The defect (real, fixed, verified)

`behaviour_clone` optimised `loss = -log_prob.mean()` over
`model.policy.parameters()`. That expression backprops through the action head
and the shared feature extractor — but gives the **value head zero gradient**,
while rewriting the extractor beneath it. PPO therefore began from a critic
that was both untrained *and* mismatched to its own inputs.

Measured, not assumed. `explained_variance` at PPO's first update was **-0.43**
— worse than predicting the mean — and the critic's fit to the expert's own
returns was **-1.146**.

The fix adds a value-regression term: the expert rollouts already carry
observable rewards, so their discounted returns (at PPO's own `gamma`, under
PPO's own reward setting) are a free regression target. `--value-coef` weights
it; `0` reproduces the old behaviour for comparison.

| | critic EV on expert data | EV through PPO |
|---|---|---|
| `--value-coef 0` | **-1.146** | -0.43 → 0.62 |
| `--value-coef 0.5` | **+0.738** | 0.39 → 0.68 |

The critic was broken and now is not. That result is solid and the fix stays.

### 18.2 The prediction that failed

The stated hypothesis was that this broken critic was *why* PPO degraded its
warm start — garbage advantages walking the policy off the cloned solution. It
predicted the fix would stop the degradation. **It did not.**

| arm | after BC | final | delta |
|---|---|---|---|
| `--value-coef 0` | 7.550 | 7.700 | -0.150 |
| `--value-coef 0.5` (critic fixed) | 7.550 | 7.775 | -0.225 |

A tenfold improvement in the critic changed placement not at all. The defect
was real; the causal claim about it was wrong. This is the **fourth**
structural hypothesis about the agent's weakness to be rejected by measurement,
after observation encoding (6b.5), reward shape (6c.3) and action space (6b.1).

### 18.3 The correction that matters more

Re-examining the distributions rather than the means shows the framing itself
was wrong. "PPO degrades the cloned policy" does not survive its own error
bars:

| arm | mean | sd | 95% CI | placement distribution |
|---|---|---|---|---|
| BC | 7.550 | 1.11 | ±0.343 | 4:2 5:2 6:1 7:2 **8:33** |
| final (vc 0) | 7.700 | 0.97 | ±0.299 | 4:2 6:2 **8:36** |
| final (vc 0.5) | 7.775 | 0.86 | ±0.267 | 3:1 6:1 7:2 **8:36** |

The intervals overlap heavily. Every arm places **8th in 83-90% of games**, and
the entire difference between them is a handful of non-eighth finishes.

This is a **floor effect**, and it invalidates the diagnostic value of the
recent A/Bs — including entry 17.7's self-play pair, which has the same shape.
A policy pinned at last place has almost no outcome variance, so no comparison
built on it can resolve anything. The blocker was never "find the bug that
makes PPO destructive"; there may be no such bug. It is that **the measurement
apparatus has no signal to measure** at this operating point.

Note the warm start here (150 episodes / 25 epochs) is much smaller than the
one that produced the 6.10 BC figure quoted elsewhere (400 / 50). These runs
were sized for pipeline validation, and were then read as if they were
experiments. That was the error.

### 18.4 Standing rule taken from this

Before any A/B is treated as evidence, check that the **baseline arm is off the
floor** and that the effect being claimed exceeds `1.96 * sd / sqrt(n)`. Report
the placement *distribution*, not just the mean — the mean hid a 90%-eighth
distribution behind a plausible-looking 7.55.

### 18.5 Where the floor ends — measured

BC alone (no PPO), 100 evaluation episodes each:

| warm start | action match | critic EV | placement | 8th-place rate | top 4 | cost |
|---|---|---|---|---|---|---|
| 150 ep / 25 epochs | 64.7% | 0.74 | 7.650 ±0.183 | **84%** | 3% | 161s |
| 400 ep / 50 epochs | 81.0% | 0.79 | 6.250 ±0.356 | 33% | 18% | 381s |
| 800 ep / 50 epochs | 84.1% | 0.75 | 5.990 ±0.394 | 32% | 25% | 697s |

Placement distributions:

```
150 ep:  4:3  5:4  6:2  7:7                        8:84
400 ep:  1:2 2:1 3:8 4:7 5:12 6:14 7:23            8:33
800 ep:  1:1 2:5 3:12 4:7 5:11 6:11 7:21           8:32
```

**150 episodes is below the floor**: one outcome, 84% of the time, so there is
no variance for any comparison to resolve. That is where entry 17.7's self-play
pair and entry 18.2's value-coef pair were both run, which fully accounts for
four consecutive "inconclusive" results.

Note the standard deviation *doubles* from 150 to 400 episodes (1.11 -> 1.82).
Counterintuitive but expected: the low variance at 150 was the floor
suppressing outcomes, not the policy being consistent. **A suspiciously tight
CI on a bad mean is a floor-effect signature, not a precise measurement.**

**400 ep / 50 epochs is the minimum viable operating point** and is the
recommended default: it more than doubles the cost of 150 but is the difference
between an experiment and a coin flip. 800 buys +3.1% action match and lands
*inside* 400's error bar, so it is not worth 1.8x the time as a default.

Also worth noting: at 84% action match the clone still only reaches 5.99
against its teacher's 4.675, so imitation is converging toward but not reaching
the scripted policy, and the residual gap remains concentrated in the content
decisions (BUY, PLACE) identified in section 15 -- not in mechanics.

Still open:

1. **18.3** Whether PPO beats behaviour cloning has **never been tested off the
   floor**. The question is open, not answered negatively. Retesting it at
   400/50 is the immediate next step, and is a prerequisite for 17.5 and 17.6.

### 18.6 PPO vs BC, retested off the floor — improves, but not significantly

Step 1 of the post-18.5 plan: the question "does PPO beat behaviour cloning?"
re-asked at 400 ep / 50 epochs, 120k steps, 100 evaluation episodes.

| | placement | top 4 | last place |
|---|---|---|---|
| scripted (teacher) | 4.860 ±0.474 | 43% | 22% |
| after BC | 6.250 ±0.356 | 18% | 33% |
| PPO 40k | 6.150 | 21% | — |
| PPO 80k | **5.780** | 30% | — |
| PPO 120k (final) | 5.880 ±0.378 | 27% | 30% |

There is now a **real learning curve** — 6.25 → 6.15 → 5.78 → 5.88, plus top-4
rising 18% → 30% — where at 150 episodes there was only noise around the floor.
That alone vindicates 18.5's operating-point change.

But the improvement does **not** clear significance. Both arms were evaluated
on the same 100 seeds, so the correct test is paired:

```
paired mean improvement : +0.370 placement
paired sd               :  2.360
95% CI                  : [-0.093, +0.833]
t                       :  1.57      (|t| > 1.98 is p < 0.05 at n = 100)
seeds better/worse/tied :  41/33/26
```

p is roughly 0.12. **The honest statement is that PPO plausibly improves on its
warm start by ~0.37 placement, and one run at n=100 cannot establish it.** The
direction is consistent across three checkpoints and two metrics, which is
suggestive; it is not proof.

Also worth recording: pairing on seeds bought only a **1.12x** power gain
(unpaired t 1.40 vs paired 1.57). Much less than hoped — the seed fixes the
match setup but not which opponent policies land in which seats, so most
episode variance is not controlled by it. Do not count on pairing to rescue an
underpowered comparison.

**Power required, at the observed sd of 2.36:**

| effect to detect | episodes needed (80% power) |
|---|---|
| 1.00 placement | 44 |
| 0.75 | 78 |
| 0.50 | 175 |
| **0.37 (observed)** | **319** |
| 0.25 | 699 |

The 100-episode default resolves effects of ~0.66 and larger. Anything subtler
— which includes every milestone 9 feature — needs 300+ evaluation episodes.
This is the budget to plan for before running the 17.5 / 17.6 A/Bs, and it is
cheap relative to training (100 episodes ≈ 40s).

### 18.7 The floor detector is now enforced, not just documented

`EvalResult` gained `ci95`, `floor_rate` and `on_the_floor`. `summary()` prints
the CI inline and appends a loud warning when a result finishes last in ≥50% of
games. The threshold sits well above a competent policy (the scripted teacher
is at 22%) and well below the 84% that made four experiments uninterpretable.
`--warm-start` now defaults to 400 with `--warm-start-epochs` 50.

The point is that entry 18.4's rule was a note a reader had to remember. Now a
degenerate result announces itself in the output that gets pasted into these
write-ups.

Still open:

1. ~~**18.6** PPO's ~0.37 improvement over BC needs ~320 evaluation episodes to
   confirm or reject.~~ ✅ **Rejected in 19.3**: retested at n=300 it fell to
   +0.147 (t=1.12). The effect did not replicate, and the refusal to call it
   established here is why nothing downstream was built on it.
2. ~~**17.5 / 17.6** Self-play and full scouting remain unmeasured.~~ ✅ done in
   section 19, at exactly the 400/50 + 300-episode budget prescribed here.
3. The clone still trails its teacher (**5.853 against 4.683**, a gap of 1.17
   at t=8.42). PPO closes none of it to within measurement error; the gap
   remains in the BUY and PLACE content decisions from section 15.

---

## 19. Milestone 9 measured — scouting hurts, self-play is inert (2026-08-02)

Step 2 of the post-18.5 plan. Three arms, identical but for the feature under
test: warm start 400 ep / 50 epochs, PPO 120k steps, **300 evaluation
episodes** (sized from 18.6's power table to resolve ~0.38 placement), all
evaluated against the *fixed scripted bots* on the same seeds and compared
paired.

| arm | obs size | action match | critic EV | after BC | after PPO | top 4 | last place |
|---|---|---|---|---|---|---|---|
| scripted (teacher) | — | — | — | — | 4.683 ±0.266 | 43% | — |
| control | 296 | 81.0% | 0.79 | 6.000 | **5.853 ±0.222** | 26% | 29% |
| self-play (mix 0.5) | 296 | 81.0% | 0.79 | 6.000 | 6.000 ±0.222 | 23% | 30% |
| full scouting | 583 | 80.8% | 0.91 | 6.230 | 6.157 ±0.217 | 22% | 35% |

Paired contrasts (positive = second arm placed better):

```
control BC -> control PPO : +0.147  CI [-0.109, +0.403]  t=+1.12  not significant
control    -> self-play   : -0.147  CI [-0.396, +0.102]  t=-1.15  not significant
control    -> scouting    : -0.303  CI [-0.558, -0.049]  t=-2.34  SIGNIFICANT
control    -> scripted    : +1.170  CI [+0.898, +1.442]  t=+8.42  SIGNIFICANT
```

### 19.1 Full scouting is harmful, and the mechanism is the familiar one

> **WITHDRAWN by entry 22.2.** Re-measured against the frozen engine, the sign
> reversed. The claim below is superseded; it is kept because the reasoning it
> generalised from is still cited elsewhere.

`--scouting full` is the project's first **significant negative** result. The
signature is what makes it informative:

* It fits the expert *better* — critic explained variance **0.91 against 0.79**
  — at essentially identical imitation accuracy (80.8% vs 81.0%).
* It plays *worse* before PPO ever runs: BC alone is 6.230 against 6.000.
* Last-place rate rises 29% -> 35%.

That is precisely the pattern entry 6b.5 measured for the `features` champion
encoding: a wider observation fits the expert's state distribution more closely
and generalises off it worse. **Two independent tests, same signature**, on the
same environment. This should now be treated as a known property rather than a
coincidence: adding sparse, wide features to this observation degrades play,
and the burden of proof is on any future widening.

Doc 03 sec 3.1 lists full board scouting as the natural v2 observation upgrade.
On this evidence it is not one. The capability stays in the codebase — it is
correct, tested, and cheap to re-test if the encoder ever changes — but it is
now documented as measured-harmful, not as an open option.

### 19.2 Self-play is inert at this scale

> **WITHDRAWN by entry 22.3.** Against a control that visibly degrades,
> self-play is the only arm that holds level with its warm start.

-0.147 with a CI centred on zero. At 120k steps, a 5-snapshot pool and
`mix=0.5`, self-play neither helps nor hurts.

This is unsurprising rather than damning: the snapshots are copies of a policy
that places 6.0, so the opponent distribution they provide is *weaker* than the
scripted bots, not stronger. Self-play is a mechanism for escaping a ceiling
imposed by fixed opponents, and there is no evidence the agent is anywhere near
that ceiling — it is still 1.17 placement *behind* the scripted heuristic. The
honest reading is that self-play was applied before the conditions that make it
useful existed.

### 19.3 PPO over BC **failed to replicate**

> **SUPERSEDED by entry 22.1**, which is stronger: PPO is not merely no better
> than behaviour cloning, it is significantly *worse* (+0.620, t=3.97).

Entry 18.6 measured +0.370 (t=1.57, n=100) and explicitly declined to call it
established. At n=300 the same comparison gives **+0.147 (t=1.12)** — the
effect shrank by 60% when power was tripled, which is what a chance fluctuation
does under replication.

The current honest position: **PPO's benefit over behaviour cloning is
indistinguishable from zero.** Nearly all of the agent's competence comes from
imitating the scripted policy; the RL phase is, so far, contributing nothing
measurable.

That the caution in 18.6 was warranted is the useful part. A +0.37 at
p≈0.12 reported as a win would have become a false premise for everything
after it.

### 19.4 What is actually established

The one large, stable, repeatedly-significant fact is the gap to the teacher:
**+1.170, t=8.42**. It has survived every engine change, every observation
variant, and every training configuration tried. Section 15 localised it to the
BUY (52.7% match) and PLACE (75.3%) decisions — the agent has learned the rules
of the interface essentially perfectly and has not learned what a good board is.

Five structural hypotheses have now been rejected by measurement rather than
argument: observation encoding (6b.5), reward shape (6c.3), action space
(6b.1), the untrained critic (18.2), and full scouting (19.1) — the last being
rejected as an *improvement* while being confirmed as a real effect in the
opposite direction. Self-play (19.2) is a sixth, measured null.

Still open:

1. **19.3** With PPO contributing nothing measurable, the productive direction
   is unlikely to be another PPO knob. Either the expert must get better (the
   agent is chasing a 4.68 teacher, so imitation caps there), or the content
   decisions need representation the current encoder cannot express — and 19.1
   is direct evidence that *widening* the flat vector is not that. Doc 03 sec
   3.1's set/attention encoder remains the untested structural idea.
2. **19.2** Self-play is worth revisiting only once the agent is at or past the
   scripted baseline, which is the condition under which fixed opponents become
   the binding constraint.

---

## 20. Item acquisition and real PvE rounds (2026-08-02)

### 20.1 The gap: the item system was unreachable

Measured before any change, over 10 games x 8 players:

```
items sitting unused in bags :  28   (only from the augment added in section 17)
items equipped on units      :   0
```

**Zero.** Two independent causes, both confirmed by reading the code rather
than inferred:

1. **Nothing granted items.** `PlayerState.add_item` had exactly one caller in
   the entire engine — the augment hook from section 17. `_fight_creeps`
   returned an unconditional free win with no drops, and there was no carousel.
2. **No policy equipped.** Neither `scripted_policy` nor `GreedyPolicy`
   referenced `equip_offset` or `equip_from_bag`.

So 65 items, the 45-pair combine table, 13 implemented item effects (Bramble
Vest, Spear of Shojin, Guinsoo's...), `max_items_per_unit`, the emblem→trait
path and **370 of 492 action-space actions (75%)** were reachable only from
unit tests. Every item test constructed its items directly, which is exactly
why nothing caught it.

Doc 01 sec 1 permitted stage 1 to be "stubbed". The stub was taken as licence
to make *all* PvE rounds free wins, and that decision quietly removed one of
TFT's three power axes from the simulation.

### 20.2 Monsters are Riot-sourced; wave composition is not

A pleasant surprise: the CDragon payload **does** carry Set 17's PvE monsters.
They were being filtered out by the `teamplanner` playable-unit filter (the
same filter that correctly excludes `TFT17_Enemy_Aatrox`). Real published
stats, now in `data/creeps.json`:

| id | name | HP | AD | AS | armor | MR | range |
|---|---|---|---|---|---|---|---|
| `TFT17_PVE_Minion` | Cosmic Squid | 250 | 20 | 0.80 | 10 | 10 | 1 |
| `TFT17_PVE_Krug` | Cosmic Bruiser | 1200 | 95 | 0.80 | 50 | 25 | 1 |
| `TFT17_PVE_Raptor` | Cosmic Scrapper | 1200 | 100 | 1.20 | 25 | 25 | 1 |
| `TFT17_PVE_Gromp` | Cosmic Gromp | 3000 | 350 | 0.70 | 30 | 30 | 2 |
| `TFT17_PVE_ElderDragon` | Cosmic Elder Dragon | 10000 | 900 | 0.80 | 50 | 50 | 2 |

All ship `mana: 0/0` and a placeholder "Nothing To See Here!" ability, so
creeps never cast. `_parse_champion` gained an `is_creep` mode relaxing exactly
two rules — empty traits, and `max_mana` 0 — rather than weakening them for
champions. A creep is additionally *required* to have no traits, since one with
a trait would join trait counts during its own fight.

**Not** Riot-sourced, and flagged: how many monsters per wave, which wave lands
on which round, and the drop rates. Research pinned the schedule shape (X-7
creep rounds; Krugs at 2-7, wolves/raptors at 3-7) and Riot Mort's own
statement that creep rounds always drop "1 or more items, or 5 gold", which is
what the weighted `loot` options encode. Exact rates are not published.

Creeps are deliberately kept **out of `GameData.champions`**: `SharedPool` and
the shop are both built from that mapping, so a creep listed there would become
purchasable. `test_creeps_load_and_stay_out_of_the_champion_pool` asserts the
pool does not merely lack them but raises on them.

### 20.3 PvE rounds are now losable, and damage is flat

`_fight_creeps` runs a real `CombatSimulator`. A weak board loses, takes
damage, and forfeits the loot — measured at roughly 1 in 4 creep rounds lost
across scripted games, which is the intended shape: beatable by a normal board,
punishing for a bad one.

Loss damage uses `stage_base_damage` directly rather than
`economy.round_damage`. Doc 01 sec 7 says PvE damage is "smaller/fixed", and
the survivor-scaled PvP formula would be actively wrong here: it multiplies by
champion cost, and creeps carry a nominal cost that means nothing.

**Low-HP catch-up.** Set 17 gives players lower in the HP standings component
*anvils* instead of random components on PvE rounds. Modelled as: the bottom
half of living players by HP get to *choose* their component via an optional
`choose_component` policy hook, everyone else draws at random. `GreedyPolicy`
uses it to complete an item on its carry when it can.

A dataset with no `creeps.json` keeps the old free-win path, so the frozen
starter fixture still runs unchanged.

### 20.4 Policies now equip, and it moved the expert

Equipping concentrates items on the strongest *fielded* unit — three items on
one carry beats one item on three, and it needs no per-champion knowledge.
`GreedyPolicy` equips after `_fill_board`, so items land on units that are
actually staying fielded. `scripted_policy` equips **through the action space**
(`EQUIP`), so the behaviour is something a cloned policy can copy.

Measured over 5 games x 8 players after the change: bags empty, 17 items
equipped, 5 of them combined into completed items.

**Baselines, re-measured (100 episodes) — the fourth invalidation:**

| policy | before items | after items |
|---|---|---|
| do nothing | 8.000 | 8.000 |
| random legal | 8.000 | 8.000 |
| scripted heuristic | 4.683 ±0.266 | **4.260 ±0.474**, top4 57%, win 15% |

The teacher got better, which is the point: the expert now plays a game with
items in it, so the imitation ceiling rises. Note the CI *widens* (0.27 → 0.47)
— items add real variance to outcomes, where before every game was decided by
board strength alone.

Still open:

1. **The Realm of the Gods is not implemented.** Set 17's carousel replacement
   at 1-1 / 2-4 / 3-4 / 4-4, where **the two lowest-HP players pick first, then
   the next two**, and every offering carries a component. This is the largest
   remaining fidelity gap and the only place where an inter-player *contested*
   decision exists — nothing else in the engine makes seats compete for a
   shared resource in a fixed order.
2. **All agent baselines are invalid again** (fourth time). The section 19
   verdicts on self-play and scouting were measured against an itemless game
   and would need re-running before they can be quoted.
3. Wave composition and drop rates are judgement calls (20.2); the monster
   stats are not.

---

## 21. The Realm of the Gods — an HP-ordered contested draft (2026-08-02)

Completes the carousel half of milestone 10. This is the **only** mechanic in
the engine where seats compete for a shared resource in a fixed order; every
other planning action is independent per seat, which is why it needed its own
phase rather than another per-player callback.

### 21.1 Modelled as a contested draft, not Set 17's literal blessing menu

A deliberate divergence, stated plainly. Set 17's actual Realm of the Gods
offers each player a *private* menu of Minor Blessings from two gods — it is
not contested. The classic carousel was contested.

Doc 01 sec 1 resolves this explicitly: *"the lowest-HP-picks-first spirit of
the old carousel is preserved even though the underlying pick mechanic
changed; model this as its own system rather than a champion-carousel stub."*
So the implementation keeps the **carousel's contested ordering** — one shared
line-up, lowest HP picks first, an early picker genuinely denies a later one —
which is the strategically load-bearing part, rather than reproducing a private
menu where pick order would be decorative.

Sourced from research, not assumed:

* Carousel pick order is by ascending HP, **in pairs** (two lowest first, then
  the next two).
* The line-up is **9 champions for 8 players**, so the last picker still has a
  choice rather than a leftover. Modelled as `extra_offerings`.
* Every carousel champion carries an item, with a component guaranteed on the
  first one. Modelled as every offering carrying a component.

Also confirmed by research and now *un*-flagged: the augment schedule guessed
back at entry 17 — **2-1 / 3-2 / 4-2, silver/gold/prismatic** — is correct for
Set 17.

### 21.2 Realm rounds have no combat

1-1 / 2-4 / 3-4 / 4-4 sit *between* fights in real TFT. `play_round` therefore
runs the draft and the planning phase, pays income, and returns **no reports**:
no damage, no streak movement, no pairing. This changes the shape of a game —
four fewer fights than before — and is the more faithful reading.

### 21.3 The RL seat drafts through its own action space

Same reasoning as `PICK_AUGMENT` at entry 17.4: a modelled mechanic the agent
cannot act on is noise it is asked to respond to. `PICK_OFFERING` joins the
action space (+9 actions, sized from config so the layout is stable even when
the realm is disabled).

The ordering makes this harder than augments were. Augment offers are private
and simultaneous; the draft is sequential, so the env must sit **mid-draft**:
seats with less HP than the agent pick first, the queue pauses on the agent's
turn, and `resume_realm()` finishes the seats above it once the agent has
acted. `Match` exposes the queue explicitly rather than hiding it in a
generator, so the paused state is inspectable and testable.

`END_PLANNING` is masked off while an offering is pending, and exhausting the
action budget takes the first offering — TFT gives no way to decline.

### 21.4 The bug the smoke test caught that the unit tests did not

`_generate_offerings` draws `seats + extra_offerings` champions **out of the
shared pool**, but only one per seat is ever taken. The spares were never
returned, leaking exactly `extra_offerings` copies per realm round — 4 per
game:

```
game 17 (seed 17): champion pool leaked: 1163 free + 28 held + 5 in shops = 1196, expected 1200
```

Thirty unit tests covering the draft passed while this was broken, because
none of them checked the pool across a whole draft. The smoke test's
pool-conservation invariant found it immediately. Two regression tests were
added at the unit level so it is caught in both places.

Worth generalising: **the invariant checks in `smoke_test.py` are load-bearing
and not redundant with the unit suite.** They test conservation properties
across whole games, which per-feature tests structurally cannot.

### 21.5 Full-bench picks convert to gold

Real TFT always hands you the carousel unit. With a full bench the engine sells
it immediately for its value instead — losing the pick entirely would be both
worse for the player and less faithful. The component still lands in the bag.

Still open:

1. Set 17's actual God Boon / armoury at 4-7 and the two-gods alignment
   mechanic are not modelled; only the carousel-spirit draft is (21.1).
2. **All agent baselines are invalid again** — fifth time. Realm rounds remove
   four fights from every game, which changes damage, economy and pacing.

---

## 22. The milestone 12 re-measurement (2026-08-02)

The first measurement pass run against a **frozen** engine. Every prior agent
number was taken before items, real PvE combat or the Realm draft existed, so
the entire section-19 verdict set was stale rather than wrong. All four arms
share one 400/50 behaviour clone, differ by a single flag, and evaluate over
n=300. Fresh scripted baseline: **4.620 +/-0.251** (win 10.3%, top4 46.3%).

```
arm          place   ci95   top4    8th     vs BC control (positive = PPO hurt)
bc           5.907  0.226  25.3%  27.7%
ppo          6.527  0.206  13.7%  43.3%     +0.620  t=+3.97  SIGNIFICANT
scout        6.257  0.213  17.0%  36.3%     +0.350  t=+2.21  significant
selfplay     5.947  0.220  20.0%  28.7%     +0.040  t=+0.25  null
```

### 22.1 PPO degrades its own warm start — now established

Entry 19.3 could only say PPO's benefit was indistinguishable from zero. At
n=300 on the finished game it is **negative and significant: +0.620 placement
worse, t=3.97.** Top-4 halves (25.3% -> 13.7%) and the last-place rate rises
27.7% -> 43.3%. The curve is monotone downhill across twelve checkpoints and
never beat its starting point once.

What makes this quotable where the earlier readings were not: the three
confounds that could previously explain it are all gone. The floor effect is
gone (BC places 8th in 27.7% of games, not 84%). The critic is healthy
(`explained_variance` **0.830** on expert data, against -1.146 before the
entry-18 value-regression fix). And the game now contains items and real PvE,
so the action space is actually reachable. **All three were removed and the
effect got larger.** That retires the last live hypothesis from entry 18: the
untrained critic was the leading explanation for the degradation, the critic
was fixed, and the degradation is worse.

### 22.2 Entry 19.1 is withdrawn: full scouting reversed sign

```
19.1 (old engine):  scouting 0.303 placement WORSE than control, t=-2.34
22   (frozen):      scouting 0.270 placement BETTER than control, t=-1.79
```

The new number does not reach significance (|t| < 1.96), so this is **not** a
finding that scouting helps — scouting is still +0.350 worse than the BC
control. What it does is remove the support for 19.1's claim.

The generalisation is the real casualty. 19.1 argued that scouting and the
`features` champion encoding shared a signature (better expert fit, worse play)
and concluded that *widening the flat observation vector is a known-harmful
operation, with the burden of proof on any future widening.* That inference now
rests on one surviving data point. There is also a plausible reason the
scouting half moved: it was measured on a game where opponents' boards carried
**no items**, so the added features encoded far less than they do now.

Downgraded from "known property" to a single observation that failed to
replicate once the environment gained content.

### 22.3 Entry 19.2 is withdrawn: self-play is not inert, it is protective

Self-play was filed as a measured null against a control that did not visibly
degrade. Against a control that now does, the same null is the result:

* vs the PPO control: **-0.580, t=-3.78** — the largest effect in the pass.
* vs the BC control: **+0.040, t=+0.25** — statistically indistinguishable from
  not running PPO at all.

Every other arm degrades significantly. Self-play is the only one that comes
back level with its warm start. That is a different claim from "self-play
helps" — it does not help, it **prevents the loss**.

**The mechanism is not known and is deliberately not guessed at here.** The
obvious story — snapshot opponents are weaker, so the agent wins more — does
not obviously produce a protective effect, because evaluation is always against
the fixed scripted bots. 19.2's reasoning (self-play is for escaping a ceiling
imposed by fixed opponents, and the agent is nowhere near that ceiling) is
still sound and still fails to predict this. It needs a targeted experiment.

### 22.4 Single training seed — the limit on 22.2 and 22.3

n=300 gives tight *evaluation* intervals, but every arm is **one training
run**. Nothing here captures seed variance, and PPO is notoriously seed
sensitive.

22.1 is safe from this: the effect is large, monotone across checkpoints, and
consistent with four prior measurements. **22.2 and 22.3 are not.** Both are
single-seed reversals of previously published verdicts and should be replicated
at 3 seeds (~4h) before being treated as established. They are recorded here as
withdrawals of the old claims, which they support on their own, rather than as
new claims, which they do not yet.

### 22.5 The EQUIP mask and the executor disagreed

`illegal_actions` was non-zero at two checkpoints of the PPO run. Under action
masking that is impossible, so it was a mask bug. Reproduced directly:

```
unit items: ['TFT17_Item_ASTraitEmblemItem']  bag: ['TFT17_Item_ASTraitEmblemItem']
MASK SAYS SAME EQUIP LEGAL AGAIN: True
RESULT: RAISED IllegalAction -> Challenger Emblem is unique and cannot be stacked
```

The mask checked only the slot cap; `validate_loadout` also forbids stacking a
`unique` item, and 16 of the 65 shipped items are unique. Fixed by adding
`PlayerState.can_equip_from_bag`, so the mask **asks the engine** instead of
reimplementing its rules — the class of bug recurs whenever a rule lives in two
places. The predicate mirrors `equip_from_bag`'s commit-to-the-first-combinable
behaviour exactly, since promising a combine the executor never attempts would
be the same bug again.

The fix was deliberately **held until the pass finished** so the committed code
matches the runs that produced the numbers above. It does not invalidate them:
the penalty applied identically to all four arms and the comparisons are paired.

Still open:

1. **22.3** The self-play mechanism. It is the only lever measured to stop the
   degradation and nobody knows why, which makes it the highest-value
   experiment available.
2. **22.1** With PPO established as *harmful* rather than merely useless, the
   suspects are the training setup, not the environment: no KL leash against
   the warm start, and dense board-strength shaping that was added to escape a
   zero-variance reward (6c.2) — a condition that no longer holds.
3. The imitation gap: BC matches the scripted policy's action **81.7%** of the
   time yet places **1.29 worse** than it (5.907 against 4.620). An 18%
   disagreement rate costs a fifth of the placement range, which is the
   signature of compounding off-policy drift.

---

## 23. Why PPO degrades its warm start — the screen (2026-08-02)

Entry 22.1 established the effect. This locates the cause. Five arms, 60k
steps, one seed, n=200, all sharing one 400/50 clone and differing by a single
knob. Deliberately a **screen, not a measurement**: the degradation is plain by
30k, so half the horizon buys the same signal at half the cost.

```
arm        place   ci95   top4    8th   vs control    lost from BC
bc         5.680  0.304  31.5%  29.0%
control    6.420  0.256  16.5%  41.5%                       +0.740
noshape    6.570  0.254  12.0%  46.0%  +0.150 t=+0.82       +0.890
kl         6.135  0.266  20.0%  35.5%  -0.285 t=-1.51       +0.455
noent      6.150  0.276  20.0%  34.0%  -0.270 t=-1.40       +0.470
lowlr      5.805  0.275  24.5%  25.0%  -0.615 t=-3.21       +0.125
```

### 23.1 The step size is too large for the warm start

`lowlr` (3e-4 -> 5e-5) recovers **83%** of the degradation, is the only
significant arm, and posts the lowest last-place rate measured anywhere in this
project -- 25.0%, under the clone's own 29.0%.

The single number is not what makes this credible. **Three of the arms restrain
how far the policy moves per update** -- `kl`, `noent`, `lowlr` -- and all
three recover ground, ordered by how hard they restrain it. The one arm that is
not about drift (`noshape`) is the only one that got worse. A coherent
mechanism rather than one lucky cell: PPO at 3e-4 takes steps too large for a
policy that took 400 episodes to build, and walks off it.

Curves say it too:

```
control  6.07  -> 6.52  -> 6.42     climbing away
lowlr    5.605 -> 5.76  -> 5.805    flat
```

### 23.2 Reward shaping is not the cause

`noshape` was the arm with the best a-priori story: shaping was added in 6c.2
purely to escape a zero-variance terminal reward, and that condition expired
once the clone came off the floor (27.7% last, not 84%). It came back **worse**
than control, +0.890 from the clone.

This is the "not enough reward signal" outcome flagged before the run, not a
vindication of the shaping design. Either way the hypothesis is rejected, and
6c.2's shaping stays.

### 23.3 The objection the screen cannot answer

**`lowlr` may simply be "less PPO."** At 1/6 the step size over 60k steps the
policy barely moves, and a policy that barely moves trivially keeps its warm
start. Its flat curve fits "correctly leashed" and "nearly frozen" equally well.

Duration separates them, so the follow-up is **not** a 3-seed replication of a
60k screen -- it is 250k at 5e-5. If the effect is slowness, it degrades like
the control, only later. `--target-kl` runs alongside because it restrains
drift *without* throttling learning, making it the only arm that could yield a
gain rather than an avoided loss.

That follow-up uses a **different seed from the screen**. The screen selected
these arms; scoring them on the seed that selected them would be selection bias.

### 23.4 Nothing here shows PPO helping

The best arm is still **+0.125 behind not running PPO at all**, and the project
baseline it is chasing (scripted 4.620) is 1.2 placement ahead of the clone.
Recovering most of a loss is not a gain. If the ceiling of this line of work
turns out to be "PPO does less damage," the honest conclusion is that the RL
phase is not earning its compute at this scale, and the productive direction is
the expert or the encoder (19.4, 22.1) rather than another PPO knob.

### 23.5 The 250k follow-up: the screen's winner was wrong, the runner-up holds

250k steps, n=300, **seed 21** — deliberately not the screen's seed 13.

```
shared BC clone (seed 21): 5.833   top4 27.3%   8th 29.3%

arm        place   ci95   top4    8th        vs BC            vs control
control    6.353  0.195  14.3%  32.7%   +0.520 t=+3.31
lowlr      6.093  0.222  21.7%  33.7%   +0.260 t=+1.56    -0.260 t=-1.72
kl         5.853  0.215  24.3%  25.3%   +0.020 t=+0.12    -0.500 t=-3.37
```

**`lowlr` was slowness, exactly as 23.3 feared.** It tracked the clone to 150k
and then broke: 5.963 -> 6.220 -> 6.093 final, last-place climbing 29.3% ->
36.0%. The screen's only significant arm (t=-3.21) does not survive the
duration test. Had the follow-up been the "obvious" 3-seed replication of the
60k screen, it would have confirmed an artefact three times over. **Replication
tests precision; it does not test whether the measurement answers the
question.**

**`--target-kl 0.02` fully prevents the degradation.** +0.020 against the clone
(t=0.12) — statistically indistinguishable from not running PPO — and -0.500
against the control (t=-3.37). Its curve improves where every other arm
worsens: 6.060 -> 5.947 -> 5.927 -> 5.853.

### 23.6 The degradation replicates across seeds

```
seed 12 (entry 22):  BC 5.907 -> PPO 6.527   +0.620  t=3.97
seed 21 (entry 23):  BC 5.833 -> PPO 6.353   +0.520  t=3.31
```

22.4 flagged single-seed as 22.1's main weakness. It is now measured twice, on
independent seeds, at similar magnitude. **PPO degrading its own warm start is
the best-established agent-side result in this project.**

### 23.7 Two unrelated fixes land on precisely the same number

This is the finding worth sitting with:

```
self-play (22.3):     +0.040 vs BC   t=0.25
--target-kl (23.5):   +0.020 vs BC   t=0.12
```

A snapshot opponent pool and a KL trust region share no mechanism. Both remove
the degradation completely. **Neither produces any gain whatsoever.** Every
intervention that helps converges on exactly "level with the warm start," and
nothing has ever measured past it.

The parsimonious reading is that PPO's step size was never the binding
constraint -- it was only the thing that *broke* something already at its
ceiling. Leash it and the damage stops; nothing appears in its place, because
there is nothing at this scale for PPO to find. `kl` is the more useful of the
two: it costs nothing in wall time and its distribution is genuinely different.

One nuance the means hide. `kl` posts the **lowest last-place rate measured
anywhere in the project (25.3%, against the clone's 29.3%) while also posting
fewer top-4s (24.3% vs 27.3%)**. Identical mean, compressed distribution --
measurably more risk-averse play. In TFT that is a real strategic stance, not a
rounding artefact, and it is invisible to the summary statistic this project
has been optimising. Worth remembering that average placement is a lossy
scoreboard.

### 23.8 Recommendation: stop tuning PPO

Three knobs, two horizons, two seeds, and the ceiling has not moved. The agent
sits 1.2 placement behind a scripted heuristic it already imitates 81.7% of the
time. Nothing in the RL phase has ever added a measurable point.

`--target-kl 0.02` should become the default -- it strictly dominates the
current default (-0.500, t=-3.37, no wall-time cost) -- and then the work
belongs upstream, where 19.4 and 22.1 already pointed:

1. **The expert caps the student.** BC chases a 4.620 teacher and lands at
   5.833. Closing that 1.2 gap is worth more than any PPO knob, and 22's
   imitation-gap note (81.7% action match, 1.29 placement worse) says the loss
   is compounding off-policy drift -- a DAgger-style iterative clone addresses
   exactly that, and has never been tried here.
2. **The encoder.** Doc 03 sec 3.1's set/attention encoder remains the one
   untested structural idea, and 22.2 has now removed the evidence that was
   being used to argue against widening the observation.

---

## 24. DAgger does not close the imitation gap (2026-08-02)

Entry 22's open item 3 read: the clone matches the scripted expert 81.7% of the
time yet places 1.29 worse, "the signature of compounding off-policy drift."
DAgger is the textbook fix for exactly that. It was implemented, verified, and
**the hypothesis is refuted.**

Budget-matched by design. DAgger adds labelled data, so `bc700` holds the total
label budget fixed and isolates the only variable that matters: whose state
distribution the labels come from. Seed 21, n=300, no PPO phase.

```
arm       place   ci95   top4    8th   match          vs bc400
bc400     5.833  0.238  27.3%  29.3%  81.8%
bc700     5.867  0.214  24.7%  25.7%  84.6%   +0.033 t=+0.20
dagger    5.803  0.228  23.3%  24.7%  88.7%   -0.030 t=-0.18

dagger vs bc700 (budget-matched): -0.063  t=-0.40
scripted teacher: 4.620
```

### 24.1 Imitation improved substantially; play did not move at all

```
match     81.8%  ->  84.6%  ->  88.7%      disagreement 18.2% -> 11.3%
place     5.833  ->  5.867  ->  5.803      flat, every t below 0.5
```

DAgger did precisely what it is supposed to do mechanically: three rounds of
student-distribution labelling cut the disagreement rate by **38%**. Placement
did not respond. Neither did adding 75% more expert data, which bought 2.8
points of match and nothing else.

This is the same signature recorded for the `features` champion encoding
(6b.5), for full scouting as originally measured (19.1), and now twice more in
one experiment. **Fitting the expert more closely does not make this agent play
better.** Four independent observations; it should now be treated as a property
of the setup rather than a recurring coincidence.

### 24.2 What that rules out, and what is left

Off-policy drift is dead as an explanation. The student can be trained directly
on the states its own mistakes produce, reach 88.7% agreement there, and still
sit 1.2 placement behind its teacher. The gap is not about *where* the training
states come from, and not about *how many* there are.

Two possibilities survive:

1. **The residual 11% is concentrated on the decisions that decide games.**
   Section 15 localised the original mismatch to BUY (52.7% match) and PLACE
   (75.3%) -- precisely the "what is a good board" judgements. If aggregate
   match rose to 88.7% while BUY stayed poor, the average is hiding the only
   number that matters. **This is cheap to check and is the immediate next
   diagnostic**: break match down per `ActionKind` rather than in aggregate.
2. **The policy class cannot represent the expert's decision function** on the
   states that matter, no matter how the data is drawn. That points at the
   observation encoder -- doc 03 sec 3.1's set/attention design, still the one
   untested structural idea, and 22.2 has since removed the evidence that was
   being used to argue against widening the observation.

### 24.3 The tally

Rejected by measurement, not argument: observation encoding (6b.5), reward
shape (6c.3), action space (6b.1), untrained critic (18.2), full scouting as an
improvement (19.1, later withdrawn as a *harm* too), self-play as an
improvement (19.2/22.3), PPO step size as the ceiling (23.7), expert data
volume (24.1), and off-policy drift (24.2).

Every intervention that has ever helped -- self-play, `--target-kl` -- converges
on "level with the warm start" and never past it. Nothing in this project has
yet produced a measured *gain* over behaviour cloning. The consistent shape of
that result across nine rejected hypotheses is itself the finding: the
bottleneck is upstream of training, in what the agent can see or in the
teacher it is copying.

### 24.4 The code stays

`--dagger-rounds` is correct, tested (including a mutation check that the
expert labels rather than the actor) and cheap. It is off by default because it
buys nothing measurable here, not because it is broken -- and if the encoder
ever changes, the drift hypothesis deserves a re-test on the new policy class.

---

## 25. The bottleneck is BUY, and the observation cannot express it (2026-08-02)

Entry 24.2 left two survivors and named the cheap test: break action match down
per `ActionKind` instead of in aggregate. `scripts/action_match.py` does that,
on both state distributions -- the expert's (what cloning trained on) and the
student's (what it actually faces).

Possibility 1 is **confirmed**. The average was improving *around* the decision
that decides games.

```
                   BUY    SELECT  PLACE  BUY_XP  END   EQUIP  AUGMENT  overall
bc400   expert    50.7%   67.1%   75.6%  83.3%  91.8%  71.8%   100%     74.7%
bc700   expert    52.1%   82.9%   85.7%  91.1%  91.8%  76.9%   100%     80.2%
dagger  expert    53.0%   81.6%   83.5%  91.8%  88.8%  77.5%   100%     79.7%

bc400   student   45.9%   29.1%   56.9%  84.8%  90.0%  77.8%   100%     51.2%
bc700   student   47.7%   60.7%   65.0%  89.6%  87.8%  81.6%   100%     70.3%
dagger  student   46.7%   69.5%   71.7%  81.7%  87.3%  88.4%   100%     73.0%
```

### 25.1 DAgger worked exactly where it should, and BUY ignored it

On the student distribution -- the one DAgger exists to fix -- it beat the
budget-matched control on precisely the decisions that suffer from drift:

```
SELECT   60.7% -> 69.5%      PLACE  65.0% -> 71.7%      EQUIP  81.6% -> 88.4%
```

Positioning is a *recoverable* error: reach a bad board state and the expert
labels tell you how to fix it. DAgger is not broken, and 24 was not a null
result about DAgger -- it fixed what it targets.

**BUY did not move: 47.7% -> 46.7%.** Three models, two distributions, six
measurements, all between 45.9% and 53.0%. Every other action kind spans
29%-100% and responds to data; BUY is pinned at coin-flip regardless of how
much data it gets or where the data comes from. That is not a learning-rate or
distribution problem. It is an information problem.

### 25.2 The default observation cannot represent the expert's BUY rule

`GreedyPolicy._buy_phase` sorts candidates by `(owned, synergy, cost, slot)`,
where `synergy` is the sum of the *current board's* trait counts over the shop
champion's traits. Deterministic and fully specified -- not noise, so not
inherently unlearnable.

But under the default `champion_encoding="index"` a shop slot is **2 floats**:
a normalised champion ordinal and cost. `rl/observation.py` has said so in
writing since milestone 6:

> ``index`` ... cannot express what a shop or bench unit would contribute to a
> trait.

To reproduce the expert's rule the network must invert a 63-way ordinal into a
trait set from memory, then cross-reference it against board trait counts held
elsewhere in the vector. **The information needed for a correct BUY is not in
the observation in usable form**, which is why no amount of data, and no change
of state distribution, moves it.

The other kinds do not need this. SELECT/PLACE/EQUIP operate on units already
owned, whose traits *are* encoded; BUY_XP and END_PLANNING are near-scalar
decisions. The one action requiring champion-to-trait knowledge is the one
action stuck at chance.

### 25.3 This reopens 6b.5, with a mechanism and a sharper test

`champion_encoding="features"` -- role, base stats and a **multi-hot of traits**
per slot -- is exactly the missing information, and 6b.5 measured it *worse* on
placement and filed it closed. Three reasons to re-open it:

1. **The engine has changed beyond recognition** since 6b.5: items, real PvE,
   the Realm draft. 22.2 already withdrew the structurally identical scouting
   verdict for precisely this reason.
2. **There is now a mechanism**, which 6b.5 lacked. It predicts a specific,
   falsifiable thing rather than a hoped-for improvement.
3. **There is now a better dependent variable.** 6b.5 judged on placement,
   which is noisy and distal. The prediction here is narrow: *BUY match should
   rise above ~50% under an encoding that exposes traits.* That is measurable
   at n=40 episodes in minutes and does not depend on placement moving at all.

If BUY match rises and placement still does not follow, that is a different and
also valuable finding -- it would mean the scripted expert's own BUY rule is
not worth imitating, and the ceiling is the teacher (19.4's first branch).

### 25.4 Read this before trusting any aggregate match number

`bc400` scores 81.8% on the training set and **51.2%** on the states it
actually reaches. The headline number in entries 18-24 was in-sample against
the expert's own distribution -- generous by 30 points about the situation the
agent is really in. Aggregate match also hides a 2:1 spread across kinds and
weights by frequency, so a model can improve its average by getting better at
`BUY_XP` (619 samples) while the decision that builds the board stays at chance.

Per-kind, on-student-distribution, or it is not a diagnosis.

---

## 26. BUY's ceiling, and 25.2 is untested rather than refuted (2026-08-02)

> Heading corrected: the ceiling stated in this entry is wrong. See 28.1.

Two follow-ups to entry 25, one of which corrects it.

### 26.1 The ceiling: BUY at ~48% is a real defect, not ambiguity

> **CORRECTED by entry 28.1.** The 90.7% below counts how often the argmax is
> unambiguous, which is not the same as how often the expert takes it. The
> validated ceiling is **67.7%**. The conclusion (BUY is a real defect) stands;
> its magnitude is ~20 points, not ~42.

Before concluding anything from a low match rate, the question that should have
been asked first: **how high could it possibly be?** The expert sorts by
`(owned, synergy, cost, slot)`. If the leading candidates routinely tie on the
first three and only the arbitrary `slot` separates them, then ~50% would be
near-optimal and entry 25 would be built on nothing.

Measured directly over 771 BUY decisions from 30 scripted games:

```
mean affordable candidates:                     3.42
top choice tied on (owned, synergy, cost):   135/771 = 17.5%
   tie of 2: 112     tie of 3: 15     tie of 4: 7     tie of 5: 1

CEILING for a model that cannot see slot index: 90.7%
```

Only 17.5% of BUY decisions are ambiguous, and most of those are 2-way. **The
achievable ceiling is 90.7% and the models sit at 45.9%-53.0%.** Entry 25.1
survives with a concrete target attached: BUY is ~42 points below what the
information supports, while SELECT/PLACE/EQUIP all respond to training.

### 26.2 The `features` arm is confounded -- 25.2 is untested, not refuted

25.3 predicted BUY match would rise above ~50% under an encoding exposing
traits. It did not (48.1% expert states, 44.7% student). Taken alone that
refutes the mechanism. It cannot be taken alone:

```
                     BUY     overall (expert states)   in-sample   placement
bc400  index        50.7%           74.7%                81.8%       5.833
features            48.1%           61.2%                90.2%       6.683
```

**The features model overfit uniformly**: highest in-sample match ever recorded
here, worst out-of-sample, degraded on *every* action kind. BUY's 2.6-point
drop sits inside a 13.5-point across-the-board collapse. This measures 2056
observation dims against a 400-episode label budget, not the value of trait
information.

The confound is mine: holding the budget fixed at 400 is the wrong control for
a 10x wider observation. The matched comparison would scale labels with
dimensionality. **25.2's mechanism is untested.**

It does independently re-confirm 6b.5's original verdict -- `features` is worse
on placement -- on an engine 6b.5 never saw. That much is now measured twice.

### 26.3 What the clean test is

Features encoding at a substantially larger label budget, with the same narrow
dependent variable: **does BUY match move toward its ceiling?** (stated here
as 90.7%, corrected to 67.7% by 28.1). Placement is
secondary and can stay flat without invalidating the answer.

If BUY stays near 50% with overfitting controlled, the mechanism is genuinely
dead and the remaining explanation is structural rather than informational:
BUY is a *relational argmax over a candidate set* -- score each shop slot
against the board's trait counts, then take the best -- which a flat MLP over a
concatenated vector approximates poorly no matter which features are present.
That is an argument for doc 03 sec 3.1's set/attention encoder specifically,
rather than for a wider flat vector, and it would be the first time the
evidence pointed at that design for a stated reason.

### 26.4 Method note: measure the ceiling before diagnosing the gap

26.1 took under a minute and could have invalidated an entire entry. The
general form: **a rate is uninterpretable without its achievable maximum.** The
same omission would have made "81.7% action match" look impressive in entries
18-24 when the honest in-distribution figure was 51.2% (25.4).

---

## 27. BUY is structural, not informational — the clean test (2026-08-02)

26.3 named the test: scale the label budget with the observation width and ask
whether BUY match moves toward its ceiling (stated as 90.7% at the time;
corrected to 67.7% by 28.1). 1500 episodes (3.75x the
previous budget), both encodings, seed 21.

```
student-state match      BUY   SELECT  PLACE  EQUIP  BUY_XP   END   overall  placement
bc400      index  400   45.9%  29.1%   56.9%  77.8%   84.8%  90.0%   51.2%     5.833
index      index 1500   48.2%  55.9%   89.7%  93.5%   99.4%  95.6%   78.0%     5.533
features feat.   1500   48.1%  28.5%   55.8%  75.8%   96.2%  85.2%   51.7%     5.887
```

### 27.1 Everything improved except BUY

At 1500 episodes the index clone improves on **every** action kind -- PLACE
+32.8, EQUIP +15.7, BUY_XP +14.6, SELECT +26.8, overall +26.8 points -- and its
student-state match (78.0%) closes to within 5 points of its expert-state match
(83.1%), meaning distribution drift is now largely a solved problem for this
policy class.

**BUY moved 2.3 points, from 45.9% to 48.2%** -- against a ceiling stated
here as 90.7% and since corrected to 67.7% (28.1). The observation stands; the
gap is ~20 points rather than ~42.

Trait information changes nothing: the features arm at the same budget scores
**48.1%** against index's **48.2%**. Overfitting is no longer the explanation --
index@1500 generalises well by every other measure.

### 27.2 25.2's mechanism is dead

> **PARTLY WITHDRAWN by 28.3.** The refutation of 25.2 stands. The positive
> claim -- that this is the first mechanism-backed argument for a set/attention
> encoder -- does not: the probe built to test it could not discriminate, and
> 28.1 shows part of the gap is the expert's economy gate rather than
> representation.

Entry 25.2 argued the observation could not express the expert's BUY rule,
since `index` encodes a shop slot as 2 floats and cannot say what the champion
contributes to a trait. That was a good hypothesis with a stated mechanism, and
it is now **refuted cleanly**: an encoding carrying an explicit trait multi-hot
per slot, trained on a budget that does not overfit it, buys **0.1 points** of
BUY match.

What survives is structural. BUY is a *relational argmax over a candidate set*:
score each of ~3.4 affordable shop slots against the board's trait counts, then
take the maximum. Every other action kind is a classification over a fixed
layout and all of them respond to data. A flat MLP over a concatenated vector
approximates a set-argmax poorly regardless of which features are in the
vector, which is exactly the pattern observed.

This is the first evidence in the project pointing at doc 03 sec 3.1's
**set/attention encoder for a specific, stated reason** rather than as the
last untried idea. The prediction it makes is narrow and pre-registered here:
*an architecture that scores shop candidates independently and compares them
should move BUY off ~48% toward 67.7%, with or without any placement change.*
(Ceiling corrected by 28.1; the probe in 28.3 did not resolve this.)

### 27.3 Correction to 24.1: expert data does help, above 700 episodes

24.1 concluded from `bc400` vs `bc700` that "more expert data buys nothing --
2.8 points of match and nothing else." That was true over the range tested and
**wrong as a general claim.**

```
400 ep   5.833      student-state overall match 51.2%
700 ep   5.867      (no gain -- the basis for 24.1)
1500 ep  5.533      student-state overall match 78.0%
```

At 1500 the clone gains 0.300 placement over `bc400` and 26.8 points of
student-state match. **5.533 is the best clone measured in this project** and
the first genuine placement improvement any intervention has produced -- as
against self-play and `--target-kl`, which only ever avoided a loss.

The methodological error is worth naming: 24.1 drew a monotone conclusion from
two points 300 episodes apart and generalised it. The 700-episode arm was
simply below the threshold where data starts paying.

### 27.4 The features encoding is now rejected three times

Placement 5.887 against index's 5.533 at an identical budget, and worse on
every action kind but BUY_XP. With 6b.5 and 26.2 that is three independent
rejections across two different engines and two budgets. `champion_encoding`
stays `index`; the case is closed unless the architecture changes.

Still open:

1. **27.2** The set/attention encoder, with BUY match as its dependent variable.
2. The clone is still 0.913 behind its teacher (5.533 vs 4.620), and BUY is now
   the only localised defect large enough to account for a gap that size.

---

## 28. Correcting 26.1: the BUY ceiling is 67.7%, not 90.7% (2026-08-02)

The architecture probe (`scripts/buy_probe.py`) was built to test 27.2. It
instead found an error in the entry it was built on.

### 28.1 The ceiling measured the wrong quantity

26.1 asked how often the expert's top-ranked candidate is **unambiguous** --
17.5% of BUY decisions have a tie on `(owned, synergy, cost)` -- and reported
the complement, 90.7%, as the achievable match ceiling. That silently assumes
the expert always takes its own argmax.

It does not. `GreedyPolicy._buy_phase` walks the sorted candidates and buys the
first that clears `cost <= self._spendable(player)`, an economy gate stricter
than the mask's `can_buy`. It can therefore skip its top pick to preserve gold.
Measured over 660 BUY decisions with >=2 candidates:

```
expert picked one of its top-ranked candidates:  67.7%
  ... exactly argmax with lowest-slot tiebreak:  67.7%
  ... exactly argmax with highest-slot tiebreak: 51.2%
```

**32.3% of the time the expert declines its own argmax.** A model with perfect
`(owned, synergy, cost)` knowledge and the right tiebreak caps at 67.7% unless
it also learns the economy gate.

The correct reading of the BUY gap:

```
models                        45.9% - 53.0%
argmax rule (no economy gate)         67.7%
26.1's claimed ceiling                90.7%   <- wrong
```

The defect is ~20 points, not ~42. Real, and worth pursuing -- but a third of
the "gap" 25-27 were chasing never existed. Entries 25.1, 26.1, 27.1 and the
README all quoted 90.7%; they are corrected in place.

### 28.2 Why the error survived three entries

The number was never re-derived. It was computed once, in the entry that
introduced it, and then cited by 27 and by the README as an established
constant. Its own 26.4 note -- *"a rate is uninterpretable without its
achievable maximum"* -- was right, and the maximum it supplied was itself
unvalidated.

The check that would have caught it takes one line: compare the expert's actual
choice against the argmax, rather than counting ties. **Measure the label
function, not a property of the features.**

### 28.3 The architecture probe is inconclusive

Five heads on 8590 BUY decisions, 80/20 split:

```
head       test    train
flat       43.5%   100.0%     memorises
shared     46.0%   100.0%     memorises
pointer    49.1%   100.0%     memorises
lean       42.0%    52.7%     cannot fit
bilinear   41.7%    52.0%     cannot fit
oracle     43.4%    52.4%     cannot fit, even given `owned`
always-pick-first-candidate: 48.5%
```

Nothing beats picking the lowest-index affordable slot. The fat heads reach
100% train accuracy -- capacity to memorise 6872 samples, not evidence about
architecture. The lean heads cannot fit the training set at all, including
`oracle`, which is handed the `owned` flag straight from the engine.

That last row is the informative one: `owned` is the expert's *primary* sort
key and supplying it changes nothing, so the lean input is missing something
else -- almost certainly the economy gate, which 28.1 shows drives a third of
the decisions.

**27.2's structural claim is neither confirmed nor refuted.** The probe cannot
discriminate while one family memorises and the other underfits. A fair test
needs the label function characterised first (28.1 is the start), heads matched
on capacity, and a train/test split large enough that 100% train accuracy is
not attainable.

### 28.4 Status

- BUY is still the outlier: every other action kind responds to data, it does not.
- The gap is ~20 points against a validated 67.7%, not ~42 against a fictional 90.7%.
- The set/attention encoder is **not** justified by evidence yet. 27.2 said this
  would be the first mechanism-backed argument for it; that argument does not
  survive 28.1 and 28.3.
- Part of what looked like a representation failure is the expert being harder
  to imitate than assumed -- a *cascade with an economy gate*, not an argmax.

---

## 29. Two relational features close 63% of the imitation gap (2026-08-02)

The BUY investigation (25-28) ends here. `owned` and `synergy`, appended per
shop slot to both champion encodings -- **10 extra floats** -- produce the
largest improvement measured in this project.

```
                      placement      top4    win     BUY (student states)
m14_bc400   400 ep    5.833 +/-0.238  27.3%  3.7%          45.9%
m16_index  1500 ep    5.533 +/-0.231  28.0%  4.7%          48.2%
m17_derived 400 ep    5.063 +/-0.263  43.0%  6.3%          82.3%
scripted teacher      4.620
```

-0.770 against its matched 400-episode control, and 0.470 better than the
1500-episode clone on **3.75x less data**. The gap to the teacher falls from
1.213 to 0.443 -- a **63% reduction**.

### 29.1 The mechanism is confirmed, not merely the outcome

```
BUY match     expert states   student states
m14_bc400         50.7%           45.9%
m17_derived       87.8%           82.3%
```

+36 points on the distribution the agent actually faces, against the ~91%
a small model reaches given these quantities (28.1 ablation). This is the
prediction registered in 27.2/28.4, measured on the number it named.

What failed before makes the point sharper. `features` supplies every
champion's full trait multi-hot -- strictly more raw information than
`synergy` -- and moved BUY 0.1 points across three separate tests. **Raw
description is not the same as the comparison.** `owned` requires an identity
match against every board and bench slot; `synergy` a dot product between the
champion's traits and the board's trait counts. Both are *relational*, and a
flat MLP over a concatenated vector does not find them.

The unit tests encode exactly this: a mutation replacing board-relative synergy
with the champion's own trait count -- a plausible number in the right slot --
fails `test_synergy_tracks_the_board_not_the_champion`. That mutation would
have made the fix inert while looking correct.

### 29.2 Aggregate action match is worse than useless here

```
                overall student-state match     placement
m14_bc400              51.2%                      5.833
m17_derived            51.5%                      5.063
```

**The headline match number is unchanged while placement improves 0.770.**
Composition moved underneath it: BUY +36.4, SELECT 29.1% -> 21.9%, PLACE
56.9% -> 52.1%. Tracked on aggregate match alone, the single most effective
change in this project reads as noise.

25.4 warned that aggregate match hides a 2:1 spread across kinds and weights by
frequency. This is that warning realised, in the favourable direction.

**The SELECT/PLACE decline is not a clean regression** and must not be quoted
as one. SELECT sample count rose 258 -> 1180: the agent now buys far more
units and therefore makes far more positioning decisions, in richer board
states. The two arms' positioning rates are measured on different
distributions and are not comparable. Whether positioning genuinely degraded
needs its own controlled test.

### 29.3 Why this was missed for four milestones

The observation was reviewed repeatedly -- 6b.5, 19.1, 22.2, 26.2, 27.4 -- and
every review asked *how much* information it carried. `features` won that
question every time (2056 dims against 240) and lost on play every time.

The right question was *what kind*. Every prior widening added more description
of individual entities. None added a comparison between entities. The clue was
in `rl/observation.py` from milestone 6 -- "cannot express what a shop or bench
unit would contribute to a trait" -- and was read as an argument for a wider
champion encoding rather than for a derived feature.

Method note: what finally located it was not a better model but a **feature
ablation on a 1281-parameter probe** (28.3, 29.1). Establishing that the label
was trivially predictable *in the right coordinates* converted an open
architecture question into a specific, cheap observation change.

### 29.4 Consequences

- **All agent baselines are invalidated again** (seventh time). Every number
  in 22-27 predates this observation.
- **The set/attention encoder is not needed for BUY.** 27.2 proposed it because
  a flat MLP cannot compute a relational argmax; supplying the relation
  directly was sufficient and roughly free. It may still matter for SELECT and
  PLACE, which are now the largest remaining defects.
- `champion_encoding` stays `index`. The derived features are cheaper and work
  on both encodings; `features` remains rejected on placement (27.4).
- PPO has not been re-tested against this clone. Every prior PPO result was
  measured against a policy whose worst decision was a coin flip.

---

## 30. Parity with the teacher, from twelve floats (2026-08-02)

Entry 29 fixed BUY with two relational shop features. The same procedure --
read the expert's rule, hand-compute what it reads, probe whether a tiny model
predicts the choice, expose the survivors -- applied to SELECT and PLACE closes
the rest of the gap.

```
                     placement       top4    win     data
m14_bc400            5.833 +/-0.238  27.3%   3.7%    400 ep
m17_derived          5.063 +/-0.263  43.0%   6.3%    400 ep
m18_ranks            4.567 +/-0.247  47.0%   8.3%    400 ep
scripted teacher     4.620 +/-0.251  46.3%  10.3%
```

**The clone is now statistically indistinguishable from the policy it is
imitating** (-0.053 against intervals of +/-0.25). Not "better than": a 0.053
difference on a +/-0.247 interval is parity, and it should be quoted that way.

Two observation changes totalling **12 floats** moved the clone 5.833 -> 4.567
on an unchanged 400-episode budget. The `features` encoding added ~1800 floats
across three attempts and lost every time (6b.5, 26.2, 27.4).

### 30.1 The probes, and the two rules they recovered

```
probe (1281-param slot scorer)   train    test     agent before
SELECT                           100.0%  100.0%       21.9%
PLACE                             75.3%   81.4%       52.1%
```

SELECT is `max(bench, key=(star, cost))` -- **entirely determined by quantities
the observation already encoded.** Unlike BUY, nothing was missing. What was
missing was the *comparison*: an argmax over ~37 slots restricted to bench
units, which a flat MLP does not compute.

PLACE needed a genuine correction. The first probe fit **42.5% of its own
training set** because it modelled only "field into an empty hex" and missed
that a full board switches the expert to evicting its weakest unit. Adding
occupant strength and a board-full flag took it to 81.4%. A probe that cannot
fit its training data is a statement about the feature set, not the model --
the same signal that exposed the missing economy gate in 28.3.

### 30.2 What was added, and the line drawn

* **Two ranks per owned unit slot** -- normalised star rank and cost rank, over
  board and bench together.
* **`board_full`** in the self block.

Deliberately **two independent ranks, never a composite "strength"**. The
expert's strength is lexicographic `(star, cost)`; encoding that would hand
over its policy rather than a fact about the board. Ranks are an ordering any
player can see, and the agent must still learn how to combine them.

`board_full` is derivable from board count and level -- but it is a
*comparison* between two encoded values, and it selects between two rule
regimes. Same "derivable but never derived" pattern as `synergy`.

### 30.3 Mechanism confirmed, composition shifted again

```
student states     SELECT   PLACE    BUY    overall
m17_derived         21.9%   52.1%   82.3%    51.5%
m18_ranks           50.4%   67.1%   74.7%    73.3%
```

SELECT +28.5, PLACE +15.0 -- the two the change targeted. **BUY fell 7.6
points** while placement improved 0.496. Aggregate match is again a poor
guide, and again the arms are not measured on identical distributions (SELECT
sample count 1180 -> 621: the agent now reaches its board faster and needs
fewer selections). Whether the BUY decline is real or distributional needs its
own test before anyone acts on it.

### 30.4 The lesson, stated once

Nine milestones of observation work asked *how much* information the vector
carried. The answer that mattered was *what kind*:

**Every widening that failed added description of entities. Every one that
worked added a comparison between entities.**

`owned` (identity match against the roster), `synergy` (dot product with board
trait counts), star/cost rank (ordering among owned units), `board_full`
(threshold comparison). Twelve floats, four comparisons, 1.266 placement.

What located them was not a better architecture but **feature ablation on
~1k-parameter probes**. Establishing that a label is trivially predictable in
the right coordinates converts "we need a better encoder" into a specific,
cheap, testable feature.

### 30.5 Consequences

- **Baselines invalidated an eighth time.** Every agent number before m18.
- **The set/attention encoder is not needed for SELECT or PLACE either.** 27.2
  proposed it because a flat MLP cannot compute a relational argmax. Supplying
  the relations directly was sufficient, three times running.
- **19.2's condition is finally met.** Self-play was filed as "worth revisiting
  once the agent reaches the scripted baseline, which is the condition under
  which fixed opponents become the binding constraint." That is now true, and
  it makes the PPO/self-play re-test genuinely interesting rather than a
  re-measurement chore.
- Every PPO result in 22-23 was measured against a policy 1.2 placement worse
  than this one. None of them transfer.
- Win rate is **8.3% against the teacher's 10.3%** -- a real remaining gap that
  average placement hides.

---

## 31. PPO from a parity clone: two verdicts reversed (2026-08-03)

Re-run of the PPO and self-play arms from the m18 clone (4.567, at parity with
its 4.620 teacher). Every result in 22-23 was measured against a warm start
1.2 placement worse, so none of them transferred. 120k steps, n=300, seed 21.

```
arm             place   ci95    win   top4    8th          vs clone
clone (m18)     4.567  0.247   8.3%  47.0%  11.7%
ppo (kl 0.02)   5.360  0.257   6.0%  34.7%  26.3%   +0.793 t=+4.36
nokl            4.637  0.264  12.3%  51.0%  16.0%   +0.070 t=+0.38
selfplay        5.107  0.261   8.7%  40.3%  20.0%   +0.540 t=+2.95

scripted teacher 4.620          10.3%  46.3%
```

### 31.1 `--target-kl 0.02` is reverted -- it is now the worst arm

23.5 measured the leash removing the degradation entirely (-0.500, t=-3.37) and
that made it the **default**. From a parity clone it is the largest degradation
in the table: **+0.793, t=+4.36**, last place more than doubling (11.7% ->
26.3%). No leash is flat (+0.070, t=+0.38).

Default reverted to `None`. A setting justified by evidence from a policy that
no longer exists is not justified.

The mechanism is plausible in hindsight and was not anticipated: sb3's
`target_kl` early-stops the whole update, **including the value-function
term**. Against a weak clone the policy had far to move and the leash mostly
prevented harm; against a good clone the KL threshold trips early and often,
leaving a critic that never catches up to a policy that is still shifting.
That was never tested, and 23.5 did not think to.

**This is the second time a constant became a default and then a fact.** 26.1's
90.7% ceiling survived three entries before 28.1 rechecked it. The pattern is
the same: a number measured once, in one regime, cited thereafter without
re-derivation.

### 31.2 Self-play degrades at parity -- 19.2's precondition was wrong

19.2 and 22.3 filed self-play as worth revisiting "once the agent is at or past
the scripted baseline, which is the condition under which fixed opponents
become the binding constraint." That condition was met exactly, and self-play
**degrades significantly**: +0.540, t=+2.95.

The stated precondition was not the operative one. The snapshot pool is still
built from a policy that loses to the scripted bots more often than not, so it
supplies a *weaker and narrower* opponent distribution regardless of how the
learner compares to the baseline. 22.3's "protective" reading -- which was
already flagged single-seed -- does not survive either.

### 31.3 PPO does not degrade *unleashed*, and it reshapes the distribution

> **Interpretation CORRECTED by 32.1.** The observations below are right; the
> conclusion that this is "a clear gain" under a ranked-LP objective is not.
> Scored under LP the arm is a null (+0.63 against the clone's +0.75), because
> the rise in last-place finishes cancels the rise in firsts.

`nokl` is the interesting arm. Mean placement is flat, but the shape moves:

```
            1st    top4    8th
clone      8.3%   47.0%  11.7%
nokl      12.3%   51.0%  16.0%
teacher   10.3%   46.3%    --
```

More firsts, more top-fours, **and** more last places. PPO is producing a
higher-variance, higher-upside policy at an unchanged mean -- and its win and
top-4 rates now exceed the scripted teacher's.

Whether that is an improvement depends on the objective. This project has
optimised **average placement**, by which it is a null. Ranked TFT rewards 1st
far more than 5th-vs-6th, by which it is a clear gain. The metric was chosen in
doc 03 sec 4 before there was any policy whose tails differed, and it is now
the binding constraint on what counts as progress.

This is the third time mean placement has hidden the finding: 23.7 (KL arm,
fewer 8ths *and* fewer top-4s at an equal mean), 29.2 (aggregate match flat
while placement moved 0.770), and now this.

### 31.4 What survives

- **22.1/23.6 do not generalise.** "PPO degrades its own warm start" was
  measured twice, on two seeds -- but always with the leash absent *and* a weak
  clone, or the leash present. Unleashed PPO from a good clone is flat, not
  degrading.
- **Imitation is done as a source of gains.** The clone is at its teacher and
  cannot pass it by construction.
- The only measured route to a better *mean* is now a better expert, or an
  objective that is not the mean.

Still open:

1. Re-run `nokl` for longer. Its curve was noisy (4.777 / 5.157 / 4.853 /
   4.600) and 120k may simply be too short to distinguish drift from progress.
2. Decide whether average placement is still the right objective. If top-4 rate
   or a ranked-LP-weighted score were the target, `nokl` is already an
   improvement over both the clone and the teacher.
3. Single seed throughout. 31.1 reverses a shipped default on one seed, which
   is defensible for a revert-to-neutral but not for a new claim.

---

## 32. LP scoring, and a correction to 31.3 (2026-08-03)

31.3 observed that unleashed PPO left average placement flat while moving
firsts 8.3% -> 12.3% and top-four 47.0% -> 51.0%, and concluded: *"By average
placement this is a null. By ranked TFT value, where 1st is worth far more than
5th-vs-6th, it's a clear gain."*

`EvalResult` now reports LP alongside placement (`LP_BY_PLACEMENT`, community
documented mid-tier values; the convex-toward-1st *shape* is what matters and
is not in doubt). Every run stored its full placement distribution, so the back
catalogue re-scores for free.

### 32.1 The claim was wrong

```
                  place     LP
m18 clone         4.567   +0.75 +/-2.61
m19_nokl          4.637   +0.63 +/-2.76
scripted teacher  4.620   +0.28 +/-2.64
```

**LP agrees with placement: `nokl` is a null.** +0.63 against +0.75, a
difference of 0.12 on intervals of +/-2.7.

The error was arithmetic, not conceptual. 31.3 reasoned from the win and
top-four rates and never priced the *other* half of the same reshaping -- last
place rose 11.7% -> 16.0%. LP weights both, and they cancel almost exactly.
Reading two favourable tail statistics as "a gain under a tail-sensitive
metric" was assuming the answer the metric was built to supply.

31.3's factual observations stand; its interpretive conclusion is withdrawn.

### 32.2 The back catalogue is safe

Across 23 recorded runs, placement and LP produce **one** ranking flip:
`m14_dagger` (#7 by placement, #9 by LP) against `m14_bc400` (#9, #7) -- two
arms already statistically indistinguishable (5.803 vs 5.833, LP -11.89 vs
-11.80).

No past verdict changes under LP. That is a stronger result than it looks: it
means average placement has not been quietly misleading this project, and the
suspicion in 31.3 that "the metric is now the binding constraint on what counts
as progress" was unfounded. It was one arm, mis-read.

### 32.3 Both metrics stay, and why

LP is kept and reported alongside placement, not because it changed any verdict
but because **it is the check that stopped one being invented.** The failure
mode it guards against -- quoting favourable tail statistics as evidence under
an unstated tail-sensitive objective -- had already happened once, in the entry
immediately before it.

Placement remains primary: every number in this project's history is measured
against it, and 32.2 shows the two agree.

### 32.4 Where this leaves the agent

```
scripted teacher  4.620   LP +0.28
m18 clone         4.567   LP +0.75
```

The clone is at parity with its teacher on both metrics, and **nothing
measured has passed it.** PPO from the parity clone is a null unleashed
(31.3/32.1) and significantly worse with the KL leash or self-play (31.1/31.2).

Imitation is exhausted by construction. The remaining routes are a better
expert, or an RL setup that does something none of the tested configurations
has. Neither is a knob; both are work.

---

## 33. Closing the fidelity gap — item effects (2026-08-03)

Entries 29-32 took the agent to parity with its teacher and then found nothing
could pass it. §31.4 named two routes out: a better expert, or an RL setup
unlike any tried. A third had been sitting in the backlog misfiled as polish.

### 33.1 The engine was far shallower than the docs recorded

Measured against the loaded dataset, not from memory:

```
champion abilities   34 / 63 implemented     (29 missing, 46%)
item effects         13 / 49 implemented     (36 missing, 73%)  [emblems excluded]
trait breakpoints     0 / 86 implemented     (78 carry non-stat params)
augments             14 synthetic archetypes, not the Riot pool
```

**§7.5 was badly stale**: it lists four missing item effects (Bramble Vest,
Infinity Edge, Rabadon's, Dragon's Claw). The real figure was 36. That entry
was written against the 13-champion starter sample and never revisited after
milestone 8 swapped in real data. Corrected there.

A first pass also mis-measured traits as having no `effect_id` at all -- they
carry one *per breakpoint*, and the top-level field does not exist. The
conclusion (zero implemented) held; the shape did not.

With 73% of item effects, 46% of abilities and 100% of trait behaviours inert,
two boards of equal cost fight almost identically. Units differentiate by raw
stats alone.

### 33.2 This explains the null results, not just the missing content

Two independent measurements land on the same reading.

The expert A/B (§34) found three deliberate strategy improvements -- synergy-
aware shopping, role-matched items, corner positioning -- **all null**, while a
single economy scalar moved a full placement. And levelling is monotone: spend
every spare gold on XP and placement improves 4.620 -> 3.663 (t=-7.42).

That is a game whose dominant strategy is *maximise unit count*, which is what
a game with inert items, abilities and traits should look like. **The
strategy-flatness and the fidelity gap are one finding seen twice.**

It also retro-explains the observation work: every feature that helped
(`owned`, `synergy`, star/cost rank, `board_full`) was about buying and
fielding. None was about combat. There was nothing in combat to see.

### 33.3 No sourcing work was needed

The payload check was the useful surprise. All 36 unimplemented items already
carry their params in `data/items.json`; all 86 trait breakpoints carry theirs.
The CDragon payload also carries trait `desc` prose and `effects[].variables`,
so nothing is blocked on data. **This is entirely an implementation gap.**

### 33.4 Two triggers were registered but never dispatched

`ON_HIT` and `PERIODIC` existed in `EffectTrigger` and were wired for
*abilities* but never fired for **items**: `_fire_item_triggers` was called
only for `ON_COMBAT_START`, `ON_ATTACK`, `ON_DAMAGED` and `ON_DEATH`.

An item effect registered on either would load cleanly, warn about nothing,
and silently never run -- indistinguishable from working. Both are now
dispatched (`ON_HIT` from the attacker's side of `deal_damage`, `PERIODIC`
once per tick with the implementation owning its own interval).

### 33.5 Riot's internal ids do not always match display names

**Void Staff ships under `item_TFT_Item_StatikkShiv`.** Registering by display
name produced an effect that matched no item at all.

`test_every_registered_item_effect_matches_a_real_item` now asserts every
registered `item_*` id exists in the dataset, because a registered-but-absent
id is dead code that reads as coverage -- the same class of failure as the
silent doc citations in §29's tooling.

### 33.6 First batch: ten items

Warmog's Armor, Sterak's Gage, Bloodthirster, Titan's Resolve, Rapid Fire
Cannon, Archangel's Staff, Last Whisper, Void Staff, Crownguard, Quicksilver.

Each is verified to *observably change a fight*, not merely to load: a status
appears, a stat rises, a shred lands on the enemy. Threshold items are asserted
to fire at most once per combat.

Params keep Riot's own variable names verbatim. Renaming on the way in is a
silent place for a transcription error to hide and the loader cannot catch one.

> **CORRECTED by entry 34.5/34.6.** Both halves of this paragraph were wrong.
> Riot *does* publish the cadence ("every second", in the item description I
> had not read), so the proc is now implemented. And the CC immunity was **not**
> modelled: it was a status named `cc_immune` that nothing in the engine read,
> and its test asserted the status existed rather than that a stun was blocked.
> The item did nothing at all.

One deliberate omission: Quicksilver's periodic attack-speed proc. Riot does
not publish its cadence, and inventing one would be a guess dressed as data --
the CC immunity is modelled, the proc is not.

Still open:

1. 26 further item effects, 29 abilities, 86 trait breakpoints.
2. The strategy-flatness baseline (random-buy diagnostic) has **not** been
   measured yet. It should be, before and after the remaining work, so
   "the engine got deeper" is a number rather than an impression.
3. Every agent baseline is invalid again -- ninth time, and this time by
   intent.

---

## 34. Closing the fidelity gap — items, traits, and four bugs (2026-08-03)

Entry 33 did ten items. This entry finishes the items (65 of 65), builds the
trait registry that never existed, and — more importantly — turns up four bugs
that were making already-"implemented" content silently inert.

The shape of the session repeats a lesson this project keeps relearning: **most
of the work was not writing behaviours, it was discovering that existing
behaviours never ran.**

### 34.1 Two non-stat modifiers were promoted to first-class state

`cc_immune` and `healing_reduction` now live on `StatusEffect` and are read by
`apply_status` and `heal` respectively. Both are needed by more than one
effect, and the alternative — string-matching `source` at each site — is how
the Quicksilver bug below happened.

`mana_gain_bonus` joined them for Adaptive Helm and Conduit.

### 34.2 Burn and Grievous Wounds are engine primitives

`apply_burn` and `apply_grievous_wounds` are simulator methods, not per-item
code. Burn is a share of the *target's* max health per second dealt as true
damage on its own cadence, and burns do not stack — a weaker application does
not overwrite a stronger one. Grievous Wounds does not stack additively
either: two 33% sources are 33%, not 66%.

### 34.3 `ManaRegen` was a stat all along

Eight items carried a `ManaRegen` param with no implementation. Riot's own
description for Tear of the Goddess renders it as a stat line —
`%i:TFTManaRegen% +@ManaRegen@ Mana Regen` — so it is a stat, not an effect.
Added to `ITEM_STAT_KEYS`, `DerivedStats`, and the tick loop.

Eight items each needing their own identical hook was the signal that the
model, not the items, was wrong.

### 34.4 🔴 Deathblade and Rabadon's were delivering none of their damage amp

Riot ships some variables under a hashed name. Deathblade and Rabadon's
Deathcap publish their **entire** effect as Damage Amp under `{1543aa48}` and
nothing else, so both were granting only their raw AD/AP.

The hashed key was identified by finding an item that carries both it *and* its
readable twin at an identical value: Giant Slayer publishes `DamageAmp` and
`{1543aa48}` as 0.15 apiece. That duplication is also why the alias is skipped
when the canonical key is present — summing them would hand Giant Slayer 30%.

Two of the most-used carry items in the game were roughly half strength.

### 34.5 Quicksilver's data contradicts the wiki, and the data wins

The project owner supplied wiki text: 14 seconds of CC immunity, 4% attack
speed every 2 seconds. The live Set 17 payload says 18 seconds, 3%, every
1 second. The wiki text is from an earlier patch; the payload is authoritative
and is what shipped.

One judgement call: the wiki ties the attack-speed stacking to the immunity
window ("during this time"). Riot's description puts it in a **separate
paragraph** with no such clause, which in TFT item descriptions means two
independent effects. Implemented as independent, and flagged here because a
reasonable person could read it the other way.

### 34.6 ❌ Quicksilver was a decorative label on a no-op

Entry 33 shipped Quicksilver as `StatusEffect("cc_immune", ...)` — a status
whose *name* was `cc_immune` and which **nothing in the engine read**.
`apply_stun` never consulted it. The item did nothing whatsoever.

Its test asserted `"cc_immune" in sources`, which passed against the no-op.
This is the fourth test in this project to pass against broken code, and the
mechanism is always the same: asserting that a thing was *recorded* rather than
that it *changed an outcome*.

The rule that catches it: **assert the consequence, never the bookkeeping.**

### 34.7 🔴 One effect_id could only ever have one trigger

`EFFECTS` was `dict[str, Callable]`, so a registry lookup returned exactly one
hook per effect_id. But real items routinely combine triggers — Sunfire Cape
grants max health at combat start *and* burns on an interval — and an item
carries exactly one effect_id to express both.

Ten of the items in this batch are multi-part. Under the old registry, one half
of each would have been silently dropped, with no warning, because the id
*was* registered.

`EFFECT_HOOKS: dict[str, list[tuple[trigger, fn]]]` replaces it. Registering
the same id twice on the same trigger still raises — that is a copy-paste, not
a multi-part item.

I nearly shipped the old failure mode in new clothes: my first draft registered
the second halves under invented ids like `item_TFT_Item_RedBuff_burn`, which
no item carries and which therefore would never have fired.

### 34.8 🔴 Every once-per-combat and interval item was dead after round 1

`_once` records fired keys on `unit._effect_once`. `reset_for_combat` cleared
statuses and shields but not that set. Units persist across rounds, so:

* Sterak's, Bloodthirster, Edge of Night, Protector's Vow fired in the first
  fight of a game and never again.
* Worse, the interval items key their guard on `sim.t`, which restarts at 0
  each combat — so every bucket collided with round 1's and Archangel's,
  Quicksilver, Sunfire, Spirit Visage and Dragon's Claw were dead too.

Measured directly: Sterak's fired `[1, 0, 0]` across three successive combats.
Now `[1, 1, 1]`.

This is the single largest defect of the batch, and no unit test would have
found it — every test constructed a fresh unit and ran one fight. It took
asking "does this still work on the *second* round?"

### 34.9 Traits: the registry that never existed

`engine/trait_effects.py` is the third registry, deliberately separate from
`effects.py` (tick-scoped, one wearer) and `augments.py` (round-scoped):

* An item effect fires for one wearer. A trait fires for a **team**, and
  routinely treats members and non-members differently ("Your team gains 5%
  Health. Brawlers gain more"). Merging the contexts means every item hook
  carrying team fields it never reads.
* Traits key on trait id + tier, not one effect_id. The data ships
  `trait_TFT17_HPTank_2/_4/_6` differing only in magnitude; registering by
  trait id and reading the tier's params keeps that one implementation instead
  of three.

**21 of 35 traits implemented**, covering every class trait — the composition
backbone: Challenger, Brawler, Bastion, Marauder, Conduit, Timebreaker,
Voyager, Fateweaver, Sniper, Vanguard, Rogue, plus Mecha, Meeple, Dark Star,
Space Groove and six unique traits.

Sniper needed the `DAMAGE_MODIFIER` trigger introduced for Giant Slayer: its
amp grows with the distance to the victim, which cannot be a stat because it
depends on where the target is standing at the moment of the hit.

### 34.10 The 14 traits not implemented, and why

These are **not** "not done yet" — each needs an engine system that does not
exist, and faking one would be worse than the omission:

| Trait | Missing system |
|---|---|
| Shepherd | Summoned units (Bia, Bayin) |
| Stargazer | Empowered hexes + a per-game constellation |
| Anima, Oracle, Factory New, Timebreaker's econ half | Between-round loot/economy hooks |
| Arbiter, Commander, Gun Goddess, Psionic | Player-facing mid-game choices |
| N.O.V.A. | Per-champion surge selector |
| Primordian | Swarmling spawning |
| Replicator | Ability re-cast at reduced effectiveness |
| Divine Duelist | Player-level (Tactician) omnivamp |
| Galaxy Hunter | Zed clones |

Several partial omissions are flagged in code where they occur: Marauder's
overheal-into-shield (the `heal` primitive clamps and discards the excess, so
there is no overheal quantity to convert), Rogue's stealth-redirect and Edge of
Night's untargetability (both need a targeting exclusion the simulator lacks),
and Fateweaver's "Lucky" (would change the meaning of every rng draw).

### 34.11 Mutation testing found two vacuous tests in the new batch

Ten mutations were run against the new tests. Five were caught immediately.
Two were not, and both tests were rewritten:

* **Giant Slayer**: the test asserted `amped > plain`, but the item's stat
  block carries a *flat* 15% amp that applies to every victim — so it passed
  with the conditional multiplier entirely removed. Now asserts strictly more
  than the flat-only prediction.
* **Multi-part items**: asserted only the first-registered trigger's half,
  which still fires under a registry that ignores every hook after the first.
  Now asserts both halves.
* **Trait PERIODIC / members-vs-allies**: both tests called
  `_fire_trait_triggers` directly, proving the hook but not the wiring. Two new
  tests step the simulator and check a non-member does not receive a
  member-only bonus.

A third vacuous test was found in *entry 33's* batch:
`test_threshold_shields_fire_at_most_once_per_combat` read
`getattr(event, "via")`, but log kwargs land in `event.detail` — the list was
always empty and `len([]) <= 1` passed against anything. Now asserts exactly 1.

**Running tally: seven tests in this project have passed against broken code.**
Every one asserted that something was recorded rather than that an outcome
changed.

### 34.12 Coverage now

| | Before entry 33 | Now |
|---|---|---|
| Item effects | 13 / 49 | **65 / 65** |
| Traits with behaviour | 0 / 35 | **21 / 35** |
| Abilities | 34 / 63 | 34 / 63 |

Still open:

1. **29 abilities.** Historically blocked on opaque passive/active splits
   (§11, §16). The params are all present; each needs a per-champion hook,
   which the `ability_TFT17_<Name>` id convention already anticipates.
2. **14 traits** needing the systems in 34.10.
3. Every agent baseline is invalid again — tenth time, by intent.

### 34.13 Did the engine get deeper? Partly — and levelling still wins

The econ sweep, re-run with control and both arms measured **together** in one
run (n=300, paired):

| arm | place | ci95 | LP | 1st | top4 | vs control |
|---|---|---|---|---|---|---|
| control | 4.813 | 0.240 | −1.65 | 7.0% | 45.7% | — |
| buy_synergy | 4.720 | 0.250 | −0.65 | 9.0% | 46.0% | −0.093, t=−0.75 |
| match_items | 4.807 | 0.240 | −1.61 | 7.0% | 45.3% | −0.007, t=−0.39 |
| corner_carry | 4.837 | 0.250 | −1.98 | 8.0% | 42.0% | +0.023, t=+0.23 |
| all_three | 4.753 | 0.244 | −1.13 | 8.0% | 44.3% | −0.060, t=−0.47 |
| **level@0g** | **4.023** | 0.229 | **+6.43** | 11.3% | **59.3%** | **−0.790, t=−6.62** |

**The levelling gap is −0.790 (t=−6.62).** Before this batch, entry 33 measured
it at −0.957 (t=−7.42). So the gap narrowed by about 17%.

⚠️ **That comparison is cross-commit and is suggestive, not established.** The
−0.790 is internally valid — both arms ran together on the same engine, same
seeds. The *change* from −0.957 is not a paired test: every arm moved (control
4.620 → 4.813, level@0g 3.663 → 4.023), which is exactly what lesson 12 says
happens whenever the engine changes. A clean measurement of "did depth reduce
the levelling advantage" needs both engines run against the same seeds, which
is not something this repo can do without keeping the old engine alive.

What is *not* in doubt: **maximising unit count still dominates by a mile.**
t=−6.62, top-4 45.7% → 59.3%, LP −1.65 → +6.43. Implementing 65 item effects
and 21 traits did not dethrone "spend every spare gold on XP".

**The more interesting null: `buy_synergy` is still a null (−0.093, t=−0.75).**
This arm buys for trait synergy, and traits now actually work. The prediction
going in was that it would start paying. It did not. Two readings, which this
run cannot separate:

1. The scripted expert's synergy heuristic is too crude to exploit the traits.
2. Traits still contribute too little relative to raw stats and unit count.

Reading 2 has a plausible mechanism worth stating: many of the strongest traits
implemented here are **team-wide** (Challenger, Brawler, Bastion, Marauder all
grant to the whole board). A team-wide bonus scales with how many units you
field, so implementing them may have *reinforced* the levelling strategy rather
than counterbalanced it. Distinguishing 1 from 2 needs an oracle-buy probe, not
more seeds — the axis that discriminates is expert quality, not noise.

**Prediction scorecard.** Three outcomes were named before the run: gap shrinks,
gap holds, gap grows. The gap shrank, but far less than the size of the content
change would suggest, and the strategic conclusion is unchanged. Recording this
as a weak confirmation, not a vindication.

Still open, and now the sharpest question in the project: **is the engine's
flatness a content problem at all?** Two batches of content have now failed to
move it. That is evidence against the entry 33 diagnosis, which attributed the
monotone econ result to missing items/traits/abilities.

---

## 35. 100% content coverage — abilities, traits, and five new systems (2026-08-03)

Direction: "I want 100% clone of TFT." Entry 34 closed items and two thirds of
the traits; this entry closes the rest. Every champion ability, every trait and
every item now has an implementation.

| | Before 33 | After 34 | Now |
|---|---|---|---|
| Item effects | 13 / 49 | 65 / 65 | **65 / 65** |
| Traits | 0 / 35 | 21 / 35 | **35 / 35** |
| Abilities | 34 / 63 | 34 / 63 | **63 / 63** |

### 35.1 The ability blocker was automation, not information

`fetch_cdragon.py` refuses to canonicalise an ability tagged both
`spellPassive` and `spellActive`, because nothing in the payload says which
variable belongs to which half — the `@Var@` references in the display text are
computed names that do not resolve back to raw variables. That refusal is
**correct** and stays: it is why Kindred's `ADDamage` (her passive) was never
cast as her active (§11.2, §16).

But the *description prose* does name each variable's role, and reading 29
descriptions resolves all 29 splits. The blocker was that the split cannot be
automated, not that the information was missing. `engine/abilities.py` supplies
the per-champion logic; every magnitude still comes from `params`, so the house
rule ("no per-champion *constants* in code") holds — what is per-champion is the
logic, which the `ability_TFT17_<Name>` id convention already anticipated.

Champion **passives** needed a dispatch that did not exist: abilities were only
ever fired on ON_CAST. `_fire_ability_triggers` now runs them on ON_ATTACK,
ON_HIT, ON_DAMAGED, ON_DEATH and PERIODIC, reusing entry 34.7's multi-hook
registry so one effect_id carries both halves.

### 35.2 Summons are a separate dataset, deliberately

Shepherd, Zed and LeBlanc create units mid-combat. `data/summons.json` holds
them, **not** `champions.json`, because that mapping builds both the shop and
the shared champion pool — a summon there would be purchasable and would leak
pool copies, which is exactly the class of bug the smoke test exists to catch.
Summons carry no traits, so Shepherd cannot summon its way to a higher tier.

Dark Star's "Mini Black Hole" is deliberately *not* a summon. Riot ships it as a
pseudo-unit with `attack_range: 0` and `crit_damage: 0`, which is a marker for
an execute rather than a unit that fights; it is implemented as the execute it
is.

### 35.3 Five new engine systems

| System | Needed by |
|---|---|
| Cone geometry (`hexgrid.cone`) | Graves, Gwen, Ornn, Riven, Urgot |
| Untargetability | Edge of Night, Rogue, Party Animal |
| Summons (`sim.summon`) | Shepherd, Zed, LeBlanc |
| Reposition / dash | Pyke, Talon, Fizz, Gwen, Kindred, Riven |
| Per-combat counters and marks | Kindred, Caitlyn, Vex, Sona, Riven, Master Yi, Fiora, Shen |
| Lucky rolls (`lucky_roll`) | Fateweaver, Caitlyn, Twisted Fate |
| Between-rounds trait hooks | Anima, Oracle, Factory New, Timebreaker, Divine Duelist, Commander |

An untargetable unit is skipped by target selection but still occupies its hex
and still takes area damage, which is TFT's behaviour. Counters and marks are
per-combat and cleared by `reset_for_combat` — the same discipline entry 34.8
had to retrofit onto `_effect_once`, applied correctly the first time here.

Marks are keyed by the unit that placed them, so two Kindreds do not share a
stack count on one victim.

`PLAYER_TRAIT_HOOKS` is a fourth registry, for traits that pay out *between*
rounds rather than during a fight. It takes a `PlayerState`, so it cannot share
the combat registry. Payouts are counted off the **fielded** board, so benching
a trait between rounds stops it paying.

### 35.4 Where a player choice was required, the choice is not modelled

Several traits and abilities are built around a decision the engine has no way
to offer a player. Each is implemented up to that boundary and the boundary is
stated, rather than a choice being invented:

* **Arbiter** — the player authors a law (a cause and an effect). Registered as
  an explicit no-op so the coverage count distinguishes "needs a choice
  mechanism" from "nobody wrote it".
* **Gun Goddess** — Miss Fortune's mode. Her damage amp applies; the mode does
  not. Her ability resolves at her strongest published tier.
* **Anima** — the choice is *take weapons now or save for stronger ones*. The
  greedy branch is taken.
* **Commander** — Command Mods are per-unit behavioural overrides with no
  representation. The cadence is tracked; nothing is granted.
* **Psionic**, **Stargazer**, **Factory New** — the item grant / constellation /
  armoury purchase is replaced by the stat outcome it would produce.

### 35.5 Partial omissions, stated where they occur

Named here so they are not mistaken for coverage:

* **Primordian's swarmlings** — Riot ships no swarmling unit in the Set 17
  payload. There is nothing to summon and inventing stats would be fabrication.
  The damage-taken-to-damage-dealt conversion *is* modelled.
* **Marauder's overheal-into-shield** — `heal` clamps at max health and discards
  the excess, so there is no overheal quantity to convert.
* **Rogue's stealth-redirect**, **Edge of Night's untargetability window**,
  **Galio's projectile attraction** — the first two now have the untargetable
  primitive but need a *redirect*, which the projectile model cannot express.
* **Fateweaver's "Lucky"** — implemented for the checks that route through
  `lucky_roll`; it does not retroactively change every rng draw in the sim.
* **Bard's saucer** collapses its per-second ticks into the cast. Total damage
  is the same; a persistent board hazard is not modelled.

### 35.6 Mutation testing: one system was untested, again

Ten mutations against the new tests. Nine were caught. The one that was not:
**every ability test called its hook directly**, so deleting the entire
`_fire_ability_triggers` dispatch left all of them green — the same failure
shape as entry 34.11's trait tests, repeated one batch later.

Two tests now run a full fight and assert a passive fired from the tick loop.

The lesson has now cost four separate batches, so stating it as a rule:
**a test that constructs the call it is testing has verified the callee, not
the system.** At least one test per subsystem must enter through the same door
production does.

Running tally: **eight tests in this project have passed against broken code.**

### 35.7 What "100%" does and does not mean

Every effect_id in the dataset resolves to an implementation, and the coverage
tests assert it. That is a real and checkable claim.

It is **not** a claim that the simulator is behaviourally identical to Riot's.
The omissions in 35.4 and 35.5 are real, the combat model is a tick loop rather
than Riot's engine, and none of this has been validated against actual game
outcomes — there is no ground truth in this repo to validate against.

Still open:

1. The strategy measurement has **not** been re-run since abilities and the
   remaining traits landed. Entry 34.13's finding — that content depth barely
   moved the levelling advantage — was measured with 29 abilities still inert.
   It should be re-run before anything is concluded from it.
2. Every agent baseline is invalid again. Eleventh time, by intent.

---

## 36. External audit: nine real defects, four of them mine (2026-08-03)

A subagent with web access audited the engine against Set 17 documentation,
scoped to *systems and rules* rather than content coverage. Its findings were
re-verified here before being acted on — and two of its claims were wrong, so
that verification mattered.

### 36.1 🔴 Three item effects were reading keys their items do not have

`ctx.number(key)` returns `0.0` for a key the item does not carry. That is
silent, and it hid three defects shipped in entries 33–34:

| Item | Read | Actual effect |
|---|---|---|
| Spear of Shojin | `"mana"` — a **starter-fixture** key | granted 0 mana, always |
| Rapid Fire Cannon | `"ADOnAttack"` — absent | fell through to the item's flat **45% attack speed, per attack** |
| Guinsoo's Rageblade | `"attack_speed_pct"` — its *total* bonus | ~43% over-strength per stack |

Measured: an RFC carrier went **0.87 → 2.49 attack speed in six autos**.

Two further errors surfaced with them. `TFT_Item_RapidFireCannon` is Set 17's
**Red Buff** (attacks burn and wound) — the second display-name/id mismatch
after Void Staff (§33.5), and I had implemented an attack-speed stacker that
the item is not. And Guinsoo's stacks **every second**, not per attack.

`tests/test_item_effects.py` now extracts every literal `ctx.number("X")` key
from each registered effect and asserts the item declares at least one of them.
It is cheap, it is general, and it catches this whole class.

### 36.2 🔴 Abilities could never critically strike

Crit was rolled only in `_auto_attack`. No ability damage path consulted
`crit_chance` or `crit_damage`, so both were **dead stats on every AP carry**,
and Infinity Edge and Jeweled Gauntlet — whose entire text is "Gain Precision"
— shipped as pure stat sticks with `effect_id: no_effect`.

They were classified as no-ops because the fetch script's test is "does it have
leftover params?", and a keyword item has none. `KEYWORD_ITEM_EFFECTS` now
forces an effect_id for exactly these. Precision is a `StatusEffect` flag read
inside `deal_damage`, which rolls crit for non-attack damage.

This was not a content gap; it was a missing damage-pipeline capability, and it
removed an entire itemisation axis.

### 36.3 Thief's Gloves, and a bug the fix introduced

Thief's Gloves was `no_effect`. It now re-rolls two random completed items onto
its wearer each round, resolved in `PlayerState` *before* combat so item and
trait combat-start hooks see them.

The first version let it roll a **Tactician item**, which grants a board slot:
the board widened for one round, then the slot vanished on the next re-roll,
leaving a unit fielded above the cap. `scripts/smoke_test.py` caught it — the
second time this session that whole-game invariants caught something no unit
test would have.

### 36.4 🔴 Player damage was roughly fourfold too high, truncating every game

The engine charged `Σ(cost × star)` per surviving enemy. The LoL wiki:

> base damage for the stage plus **1 damage per surviving enemy champion**

Star level and cost do not matter — a 3-star 5-cost costs the loser exactly
what a 1-star 1-cost does. Doc 01 sec 7 is itself wrong here; the code
faithfully implemented a wrong spec.

The XP table was wrong in the same direction: `7→8` cost **48** against a real
**60**, while `8→9` and `9→10` were *over*-priced at 76/84 against 68/68 —
cheap mid-levels, expensive top levels, precisely the deformation that makes
"level, don't roll" dominant. `stage_base_damage` was 20–25% high at stages 5–7.

Measured effect of the damage rule alone: games ran ~27 rounds and ended at
stage 5; they now run ~30 and reach stage 6. **The entire phase in which
composition pays off — level 9, 5-costs, 3-stars, completed carries — was being
cut off before it arrived.** A game that ends at 5-3 *should* reward having the
most bodies now.

⚠️ **Two sources disagree** on stage 4–6 base damage: the LoL wiki gives 7/9/11,
community trackers give 8/10/12. The wiki is used and the disagreement is
recorded in `config.provenance`.

### 36.5 A placement test had been asserting the wrong direction

`test_earlier_elimination_means_a_worse_placement` sorted players by
elimination round ascending and asserted their placements were **ascending**.
Earlier elimination means a *worse* (higher) placement, so the sequence must be
descending. It only ever passed because its own escape hatch fired on ties —
and correcting the damage rule lengthened games enough to break the ties and
expose it.

**Ninth test in this project to pass while asserting something untrue.**

### 36.6 The strongest finding: no policy in this project has ever rerolled

`scripted_policy` contained **no reroll branch at all**, and `GreedyPolicy`
rolls at most once per planning phase above 45 gold. Measured: 0 rerolls across
10 full games, and gold piling up unspent — mean 164 by 5-4, far past the
interest cap.

Rolling is the primary gold sink in real TFT and the *only* mechanism that
converts gold into specific units, and therefore into 2-star 4-costs and into a
composition. With it absent, **XP is the only unbounded gold sink, so "spend
every spare gold on XP" wins by construction rather than by mechanics.**

That reframes §34.13 entirely. Every arm of that econ sweep — control,
`buy_synergy`, `match_items`, `corner_carry`, `level@0g` — played a game with
no rolling. It is the most plausible single explanation for why two batches of
content (65 items, 35 traits, 63 abilities) failed to move the result: the arm
that would exploit them was never available. **It is not a fidelity problem.**

`scripted_policy` now takes `roll_at_level`, defaulting to **0 (off)** so every
historical measurement stays reproducible. A 20-seed smoke check put `roll@7`
*behind* no-roll (5.550 vs 5.100) — far too few seeds to mean anything, and
recorded only so the eventual result cannot be fitted to a remembered hint.

### 36.7 No mana lock

Real TFT locks every champion out of mana gain for 1s after casting. Without
it, tanks convert damage taken during the cast straight into the next one and
Casters keep regenerating — a uniform over-generation favouring exactly the
units that already cast most. Doc 99 entry 7.7 listed this as "unclear if
needed"; the wiki documents it precisely.

### 36.8 Overtime bypassed the entire defensive game

`_apply_sudden_death` subtracted a share of max health straight from
`current_hp`, "bypass[ing] shields and mitigation so termination is
unconditional". Real overtime is an **acceleration** — 300% attack speed, 200%
ability damage, 66% healing reduction, damage still going through resists.

The audit measured ~25% of fights still live at 30s. For the deciding seconds
of a quarter of all fights, armour, MR, `durability`, shields and healing were
worth **nothing** — a direct anti-composition bias in an invented constant.
Overtime is now the acceleration; the burn is retained only as a floor so two
boards that cannot hurt each other still terminate.

⚠️ The audit's *impact* estimate for this (96% of fights won by whoever led on
bodies at 30s) is *confounded* — leading on bodies at 30s is already evidence
of winning. The mechanism is real; that number is not evidence of its size.

### 36.9 Where the audit was wrong

Verified against the LoL wiki before acting:

* It claimed players **start at level 2**. They start at level 1, which the
  engine already did.
* It gave stage 4–6 base damage as 8/10/12; the wiki says 7/9/11 (see 36.4).

Both would have been silent corruptions of a table classed
`community_documented`. Re-deriving before citing is the rule that caught them.

### 36.10 What the audit checked and found correct

Worth recording, so the audit reads as coverage rather than a complaint list:
shop odds by level and pool sizes 30/25/18/10/9 both match Set 17 exactly;
copy-weighted draws; interest computed before income; streak thresholds; sell
values; the 55 component recipes; trait counting by distinct champion; the
armour curve; base crit 25%/140%; tank damage-mana 1%+3% capped at 42.5;
projectile fizzle granting no mana; sticky targeting; BFS pathing around
blockers; ghost armies cloning a living player without mutating them.

Still open, and deliberately not done in this batch:

1. **Radiant, Artifact and Support item classes** are absent from the dataset
   entirely — `radiant_version_of` is `null` on all 65 items, though
   `ItemRegistry` already has the plumbing. Support items are a distinct
   *system* (value depends on the ally you park them beside).
2. **No item carousel after stage 4.** Currently invisible because games ended
   at 5-3; with 36.4 corrected they now reach stage 6, so this is a live
   item-supply gap.
3. **No shop lock** — a real planning-phase decision the action space lacks.
4. **Multi-target abilities pick victims by list order, not position**
   (3 abilities), which is precisely the class of mechanic through which
   positioning is supposed to matter.
5. **Every baseline is invalid again** — twelfth time, and this time the
   engine's *rules* changed, not just its content.

## 37. The econ sweep, re-run with a reroll arm (2026-08-03)

### 37.1 Why this run exists

Two things make every econ number in [§34.13](#3413-economy-the-one-arm-that-moved)
unusable. The engine's *rules* changed in §36 — player damage, the XP table and
stage base damage were all wrong, and all three independently subsidised
levelling. And [§36.6](#366-the-strongest-finding-no-policy-in-this-project-has-ever-rerolled)
established that no policy here has ever rerolled, so "level" was winning a
contest it ran in unopposed.

This is the first fair test of the project's central economic question.

**Design.** Seven arms over the same 300 seeds, paired. `control` is the
existing default (`level_at_gold=30`). The `level@Ng` arms sweep the levelling
threshold; the `roll@N` arms spend spare gold on rerolls from level N upward.
Run as one process so both sides of every comparison come from the same
engine — lesson 12.

```
.venv/bin/python scripts/expert_ab.py --episodes 300 --only-sweeps \
    --level-at-gold 0 20 50 --roll-at-level 6 7 8
```

`--only-sweeps` is new, and skips the four flag arms (`buy_synergy`,
`match_items`, `corner_carry`, `all_three`) — they are not what this run is
asking about, and each costs ~15 minutes.

### 37.2 Outcomes named before the run finished

Written while the process was still running, so that whatever appears cannot
be narrated as the thing that was expected (lesson 15).

| # | Outcome | What it would mean |
|---|---|---|
| A | A `roll@N` arm beats `control` and every `level@Ng` arm | The flatness of §34 was **the expert**, not the engine. Rolling is the missing gold sink; content had no arm through which to pay off. The next step is a reroll-capable teacher and a fresh clone. |
| B | Roll arms null, but the `level@Ng` spread narrows vs §34.13 | Both contribute. The §36 rule corrections removed part of levelling's artificial edge; rolling adds a real alternative but the scripted buy logic is too crude to use it. Next step is the *buy* policy, not the sink. |
| C | Roll arms null and the level spread holds | Economy is not where the signal is. Diagnosis moves to combat resolution — most likely §36's still-open item 4, positional targeting. |
| D | Roll arms clearly *worse* | Real, and not the same as null. Either rolling at a fixed level is genuinely bad play in this engine (plausible — it is bad play in real TFT without a reason to roll), or the reroll branch spends gold without converting it, which is a bug in the branch rather than a fact about economies. Distinguish by checking units bought per game, not by re-running. |

Prior: **B**, weakly. The 20-seed smoke check in §36.6 pointed at D, but 20
seeds discriminate nothing and it is recorded only so it cannot be quietly
promoted to a hint.

A result is reportable at n=300 paired only with its t-statistic and its
histogram, not its mean alone (lesson 4). Note that the seven opponents still
run `GreedyPolicy`, so 4.500 remains the no-difference line.

### 37.3 Result of the first run

> **VOID — the roll arms measured nothing. Superseded by 37.4 and 37.6.**

Stopped after ~25 minutes, two arms in, once 37.4 showed the reroll branch
could not function. The arms are kept named here so the abandoned run is
visible as abandoned rather than quietly disappearing.

### 37.4 🔴 The teacher never sold a unit — and rolling depended on it

The sink probe (`scripts/sink_probe.py`, new) counts actions by kind rather
than placement, because action counts are far less noisy than placement and
answer a different question. On 12 seeds it showed the reroll arm rolling
45 times a game while purchases barely moved — 28.6 → 29.7:

| arm | place | reroll | buy_xp | buy | sell |
|---|---|---|---|---|---|
| control | 5.417 | 0.0 | 36.5 | 28.6 | 0.0 |
| roll@7 | 4.917 | 45.3 | 17.5 | 29.7 | 0.0 |

That is outcome D's signature from 37.2, and 37.2 said to distinguish it by
checking units bought rather than by re-running. Instrumenting the reroll
branch gave the mechanism immediately:

> **100% of rerolls happened with a full bench**, mean gold 25.1, with an
> affordable shop slot present **every single time**.

A full bench masks every `BUY` action. The policy therefore fell through to
the reroll branch, rerolled a shop it could not buy from, and repeated until
its gold hit the interest floor. Rolling was structurally incapable of working.

The root cause is one branch further back, and is the same *kind* of gap as
36.6: **`scripted_policy` has no sell branch.** The board fills with the
strongest units, the `SELECT` branch then refuses to field anything weaker,
and every subsequent purchase is stranded on the bench permanently.

**The bots are not affected, and this was first written here claiming they
were.** `GreedyPolicy._sell_surplus` (`rl/opponents.py`) already frees bench
space by selling the weakest surplus 1-stars, and has since milestone 5-6. The
error came from trusting a grep that returned nothing; the correction matters
because it inverts the reading of the sell arm. The teacher was the *only*
seat that could not sell, so its improvement is a genuine gain rather than the
exploitation of a shared handicap — and no change to the opponents is needed.

One real asymmetry survives: `_sell_surplus` stops at the first non-1-star, so
a bot bench that fills with 2-stars clogs too. Narrower than the teacher's bug,
and left alone rather than fixed mid-measurement.

Adding `sell_bench` — sell the weakest bench unit when the bench is full,
never one that is combine progress — changes the game far more than rolling
does:

| arm | place | reroll | buy_xp | buy | sell |
|---|---|---|---|---|---|
| control | 5.417 | 0.0 | 36.5 | 28.6 | 0.0 |
| sell | 2.917 | 0.0 | 36.8 | **136.8** | 103.1 |
| roll@7 | 4.917 | 45.3 | 17.5 | 29.7 | 0.0 |
| roll@7+sell | 3.167 | 5.7 | 34.2 | **137.1** | 102.7 |

Purchases per game rise **4.8×**. Note also that with selling enabled the
reroll branch almost stops firing (45.3 → 5.7): gold now has somewhere better
to go. n=12, so the *placements* are indicative only — the action counts are
what this table is for.

Two lessons, both already on the list and both re-earned. A rate is
uninterpretable without its achievable maximum (lesson 6): "the expert buys
28.6 units a game" was never checked against what it *could* buy. And an arm
must be verified to do the thing it is named for before its result means
anything — 36.6 named the missing sink correctly and still measured a branch
that could not reach it.

Both flags default off, so every number before today reproduces.

### 37.5 The run that replaces it

```
.venv/bin/python scripts/expert_ab.py --episodes 300 --only-sweeps --sell \
    --level-at-gold 0 50 --roll-at-level 6 7 8
```

Seven arms, same 300 seeds, paired: `control`, `level@0g`, `level@50g`,
`sell`, and `roll@{6,7,8}+sell`. The roll arms now all include selling,
because 37.4 shows rolling without it measures nothing.

**Outcomes named before it finished**, superseding 37.2's table — the question
has changed, since `sell` is now the arm most likely to move:

| # | Outcome | What it would mean |
|---|---|---|
| A | `sell` is a large improvement and the roll arms add little on top | The teacher's ceiling was a *bench-management* bug, not economy. The clone is at parity with a teacher that was throwing away four-fifths of its purchases; imitation was never the binding constraint 36.6 and §8 claimed. Re-clone before anything else. |
| B | `sell` and a `roll@N+sell` arm both improve, roll adding on top | Economy is real and rolling is a genuine second lever. Teacher becomes `sell + roll@N`, then re-clone. |
| C | `sell` improves and the roll arms are *worse* than `sell` alone | Rolling at a fixed level is bad play in this engine, as it is in real TFT without a reason to roll. Drop it; the finding is 37.4 alone. |
| D | `sell` does not reproduce its n=12 improvement at n=300 | The 12-seed table was noise in placement even though the action counts were not. Would mean 4.8× more purchases does not translate into placement — itself a strong statement about combat, and the diagnosis moves there. |

Prior: **A or B**, and this time with a mechanism rather than a hunch behind
it — the 4.8× purchase gap is a structural fact measured on action counts, not
a placement difference that might be noise.

### 37.6 Result: outcome A, decisively

n=300, paired on shared seeds. 4.500 is parity with the seven bots.

| arm | place | ci95 | LP | 1st | top4 | vs control (paired) |
|---|---|---|---|---|---|---|
| control | 5.017 | 0.263 | -3.54 | 9.7% | 40.7% | — |
| level@0g | 4.757 | 0.256 | -1.11 | 11.0% | 42.7% | -0.260, t=-1.64 |
| level@50g | 5.177 | 0.276 | -4.93 | 11.0% | 38.3% | +0.160, t=+1.24 |
| **sell** | **3.437** | 0.266 | +13.11 | 33.0% | 65.7% | **-1.580, t=-10.05** |
| roll@6+sell | 3.487 | 0.267 | +12.76 | 31.7% | 67.3% | -1.530, t=-9.54 |
| roll@7+sell | 3.380 | 0.257 | +13.81 | 30.3% | 69.7% | -1.637, t=-10.40 |
| roll@8+sell | 3.493 | 0.259 | +12.41 | 28.0% | 65.3% | -1.523, t=-9.82 |

**Outcome A, exactly as 37.5 defined it.** Selling is worth 1.580 placement at
t=-10.05. Rolling adds nothing on top of it: `roll@7+sell` against `sell`
paired is **-0.057, t=-0.58, n=300** — a null. All three roll arms land inside
0.11 of the sell arm, and their ordering in the level they roll at is noise.

The econ sweep that motivated all of this is *also* a null once selling is
absent from the question: `level@0g` is -0.260 at t=-1.64, `level@50g` +0.160
at t=+1.24. Levelling policy was never the lever. **The teacher's ceiling was a
bench-management bug**, and both §34.13's flatness and 36.6's reroll diagnosis
were looking one branch past it.

The distribution moves more than the mean does, which is why this project
quotes it (lesson 4):

| | 1st | 8th | floor rate |
|---|---|---|---|
| control | 29 | 61 | 20.3% |
| sell | 99 | 21 | 7.0% |
| roll@7+sell | 91 | 18 | 6.0% |

Firsts more than triple and last places drop by two thirds. Note also that
`sell` and `roll@7+sell` reach nearly the same mean by different routes — the
roll arm trades firsts (99 → 91) for top-fours (65.7% → 69.7%). That is the
same pattern as the KL arm in §31: an identical mean covering two different
distributions. Neither is preferred here on the strength of a null.

**What this changes.** §8's binding constraint — "the clone is at parity with
its teacher, so imitation is exhausted by construction" — was describing a
teacher crippled by a one-branch bug, not a real ceiling. The teacher is now
1.58 placement better. `sell_bench=True` becomes the teacher for the re-clone;
`roll_at_level` stays at 0, since nothing justifies carrying an extra flag on a
t=-0.58 null.

Still open: whether the *student* can actually reach the new teacher. That is
the next measurement, not an inference from this one. And whether the defaults
of `scripted_policy` and `GreedyPolicy` should change is deliberately deferred
until after the re-clone, so the comparison is not made against a moving
baseline (lesson 12).

### 37.9 The parallel path, validated at full scale

The 7-arm serial run took **2h 05m**. Re-running three of its arms with
`--workers 10` reproduced `control` 5.017, `sell` 3.437 and `roll@7+sell` 3.380
**exactly** — every placement identical — in **7 minutes**, at 956% CPU. That
is the strongest available check on 37.8's equivalence claim: not a unit test on
4 seeds but 900 full games agreeing digit for digit with a run made in a
different process topology.

`--json` now persists per-arm placements. Without it only the printed table
survived, and the `roll@7+sell` vs `sell` pairing above — arm against arm
rather than arm against control — could not have been computed after the fact
without re-running for two hours.

### 37.7 The cloning pipeline could not be told which teacher to clone

Prep for the re-clone, done while 37.5 ran. `collect_expert_data` called
`scripted_policy(env)` with no arguments, so **the teacher was hardcoded** and
none of the flags added since §34 — `buy_synergy`, `match_items`,
`corner_carry`, and now `sell_bench` and `roll_at_level` — could ever reach the
dataset. Every clone this project has trained imitated the bare default.

That is not a missing convenience. Imitation caps at its teacher by
construction (§8), so the teacher's configuration is part of the experiment.
`expert_kwargs` now threads from the CLI (`--expert-sell`,
`--expert-roll-at-level`) through `behaviour_clone` and `dagger` into the
labelling policy, built once so the clone and every DAgger round label with the
*same* teacher — two different teachers across rounds would aggregate
contradictory labels for identical states.

Defaults are off, so every clone measured before today reproduces.

**A pre-existing defect found on the way: `--help` has been crashing.** An
unescaped `%` in `--target-kl`'s help text raised `ValueError: unsupported
format character '>'`, because argparse only interpolates help strings lazily
at format time. It reproduces on `HEAD` and predates this session. Nothing
exercised it: no test ran the CLI. There is one now, and it is the cheap kind
that covers a whole class — any future unescaped `%` in any help string fails
it.

Three regression tests, all mutation-checked: reverting the threading fails the
`expert_kwargs` test, and re-breaking the escape fails the `--help` test.

### 37.8 Where the time actually goes, and the one speedup worth taking

Asked whether any of this is GPU-accelerable. Profiled rather than guessed —
3 games under `cProfile`, 31.4s total:

| | share of runtime |
|---|---|
| `Simulation.step` — the combat tick loop | **97%** |
| policy, observation encoding, shop, economy, everything else | ~3% |

167,697 interpreted ticks driving 1.47M `_act` calls. Branchy, sequential,
tiny-state game logic — the shape GPUs are worst at, with no batched tensor
math anywhere to move onto one.

**GPU is the wrong axis, in all three places it could apply.** The simulator
would need rewriting as batched tensor ops across parallel fights, which is a
rewrite of the engine's core and fights the determinism guarantee everything
here depends on. The policy net is 381 inputs → 501 actions through a small
MLP, where kernel-launch overhead exceeds the compute — `--device cpu` is
already the default and its help text already says so, which was a correct
call. And the machine is an M3 Pro: MPS only, no CUDA. The single place a GPU
might pay is the BC fit over a large aggregated DAgger dataset, which is
minutes off a 75-minute run.

**Parallelism across seeds was the real answer, and it was sitting unused.**
12 cores, 6 of them performance cores, and every measurement this project has
ever run used exactly one. `evaluate` loops seeds serially and training uses
`DummyVecEnv`, which steps its envs sequentially in a single process. Games
are independent and deterministic per seed — embarrassingly parallel.

`evaluate_scripted_parallel` runs seeds across processes. Workers rebuild the
env and policy themselves: `scripted_policy` closes over its env and is not
picklable, and shipping a live env would share mutable state across processes
even if it were. That limits this path to policies describable by keyword
arguments — every arm of every sweep, but *not* an sb3 model, so `evaluate`
remains the general entry point.

Measured, 12 seeds × 2 arms, with the main sweep still holding a core:

| | wall clock |
|---|---|
| `--workers 1` | 74.7s |
| `--workers 10` | **16.1s** |

4.6×, and the results are **identical**, not merely close. At 12 seeds over 10
workers the load balancing is poor; 300 seeds should do better, though the six
efficiency cores are slower than the performance cores so the realistic
ceiling is nearer 6× than 12×.

**A vacuous test, caught by mutation — the tenth in this project.** The first
version used `pool.map`, which already returns results in input order, so the
seed-keyed reassembly was dead code and `test_parallel_evaluation_preserves_
seed_order` passed with the reassembly deleted. Switching to `imap_unordered`
fixed both problems at once: better load balancing, since games vary from ~3
to ~10 seconds and a chunk no longer blocks on its slowest seed, and results
genuinely arriving in completion order, which makes the reassembly load-bearing
and the test real. Both parallel tests now fail when it is removed.

The equivalence test asserts *identity* rather than similarity deliberately: if
it ever diverges, either the engine has acquired hidden global state or results
are being reassembled by position, and the second would silently corrupt every
paired comparison in the project.

Not done: `SubprocVecEnv` for training, and the tick hot path itself. The
profile hands the latter over for free — `builtins.any` is 14.8M calls and 20%
of runtime, `is_untargetable` 8.6M calls and 14%, both re-evaluated per unit
per target-selection per tick over status-effect lists that change rarely. A
per-unit counter maintained on status add/remove should take most of that, and
determinism makes it verifiable: results must be bit-identical before and
after. Left alone for now — it touches the engine's hottest code, and there is
a measurement in flight.

## 38. The clone cannot follow the better teacher (2026-08-03)

### 38.1 The re-clone: a null, and a failed prediction

Two behaviour-cloning arms, same seed, same budget (`--warm-start 400
--timesteps 0`), run side by side so neither is measured against a moving
baseline. Only the teacher differs. n=150.

| clone of | clone place | its teacher | gap |
|---|---|---|---|
| old teacher | 4.847 | 5.017 | -0.17 |
| sell teacher | 4.813 | 3.437 | **+1.38** |

**The teacher's 1.58-placement improvement did not transfer.** The two clones
are 0.034 apart — a null — while their teachers are 1.58 apart.

I predicted the opposite. [Entry 37.6](#376-result-outcome-a-decisively) called
for re-cloning as the immediate next step on the reasoning that imitation caps
at the teacher, so a better teacher lifts the student. It does not.

What this does to §8 is worth stating plainly. "The clone is at parity with its
teacher, so imitation is exhausted by construction" was never evidence about
imitation. It was evidence that *that* teacher was easy to copy. Raise the
teacher and the student stays put, now **1.38 behind** what it is imitating.
Parity was a property of the teacher, not a ceiling on the method.

Some signal did get through — firsts 20 → 27, LP -1.63 → -1.05 — but top-4 is
flat (44.0% vs 43.3%) and last places are unchanged (29 vs 30). A small
redistribution at the top, not the teacher's policy.

### 38.2 Localising it: the clone knows *when* to sell, not *which*

Action match against the sell teacher, 25 episodes, expert states — `SELL` is
the worst-matched kind by a wide margin and is 28% of all expert actions:

| kind | match | n |
|---|---|---|
| PICK_AUGMENT | 100.0% | 75 |
| BUY | 85.3% | 3228 |
| BUY_XP | 81.3% | 1013 |
| END_PLANNING | 73.8% | 381 |
| PLACE | 69.8% | 556 |
| PICK_OFFERING | 67.7% | 99 |
| SELECT | 65.4% | 557 |
| EQUIP | 64.2% | 285 |
| **SELL** | **24.3%** | **2379** |

`scripts/action_match.py` had to be taught which teacher to label with, or it
would have compared the sell clone against the policy it was *not* cloned from
— the same hardcoded-teacher gap as 37.7, in a second script.

Splitting the rate (`scripts/sell_ceiling.py`, new) separates three readings
the aggregate cannot:

```
expert SELL decisions: 2379
  clone chose SELL at all  : 93.1%
  clone chose the same unit: 24.3%
  ...of the times it sold  : 26.2% were the right unit
```

**The clone learned *when* to sell almost perfectly and cannot work out *which*
unit to sell.** That is a much narrower defect than "cloning failed".

### 38.3 The ceiling, measured before drawing the conclusion

The teacher sells the weakest bench unit by `(star, cost)` and breaks ties by
bench index, so where several units tie its specific choice is arbitrary and
learnable only as "lowest index wins". If ties were common, 26.2% might be
near the achievable maximum. Measured over 2525 SELL decisions:

| units tied for weakest | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| count | 1772 | 364 | 226 | 87 | 55 | 13 | 8 |

70% of decisions have a **unique** correct answer, mean 1.56 candidates, and a
model that learned the rule perfectly but guessed uniformly among ties would
score **81.8%**. The clone scores 26.2%.

Ties are not the explanation. The clone genuinely cannot identify the weakest
bench unit. (The tie sample is 2525 decisions from seeds 0-24 against the
match sample's 2379 from seeds 90000+; different draws of the same
distribution, which is fine for a ceiling but they are not the same games.)

### 38.4 What it points at, and the line this runs into

This is the project's own observation rule, arriving from the other direction:

> Relational beats descriptive. If a quantity requires an identity match, a dot
> product, a **ranking** or a threshold across slots, a flat MLP will not
> derive it. Supply it.

Choosing which bench unit to sell is a ranking across slots. Nothing in the
observation lets the network compare bench units *against each other*; each
slot is described independently, and "which of these is smallest" is precisely
the operation the rule says will not be derived. That predicts a low SELL rate
and a high BUY rate (85.3%, a per-slot judgement), which is what is measured.

**And it runs straight into the other rule.** CLAUDE.md forbids encoding the
expert's policy, and names the exact trap: "a composite *strength* score using
the expert's lexicographic `(star, cost)` preference would be copying, not
learning." A `is_weakest_sellable` flag per bench slot would be that score
wearing a different hat — it hands over the teacher's decision rule directly.

The line, stated explicitly as required: **star rank and cost rank across bench
slots are facts a player reads off the screen** and are on the allowed side.
The *composite* that combines them in the teacher's lexicographic order is not.
Supplying two independent rankings and letting the network learn how to combine
them is a real experiment; supplying their combination is copying. This has not
been measured yet, and is deliberately not being called a fix.

### 38.5 Still open

1. Whether adding bench star-rank and cost-rank moves SELL match toward 81.8%,
   and whether that moves placement. Two separate questions — 24.2 raised
   aggregate match 81.8% → 88.7% with no placement movement at all, so match
   is not a proxy for the thing being optimised.
2. Whether the same defect explains `SELECT` on student states (22.1%), which
   is also a cross-slot comparison and is the largest single bucket there.
3. Whether the teacher's defaults should change. Still deferred, and now for a
   better reason: the teacher and the student disagree about what is
   achievable, so changing the default changes what every future clone
   inherits.
4. DAgger against the sell teacher, untested. The clone's problem is not
   state-distribution drift, so there is no reason to expect it to help, but
   that is a prediction rather than a measurement.

### 38.6 The probe: the label is trivial in the right coordinates, and absent from the observation

`scripts/sell_probe.py` (new). Identical labels, two feature sets, 5660 SELL
and 1288 SELECT decisions from the sell-capable teacher, 60 episodes.

| | SELL train | SELL test | SELECT train | SELECT test |
|---|---|---|---|---|
| hand-computed per-slot | 100.0% | **100.0%** | 100.0% | 99.6% |
| the real 381-float observation | 100.0% | **20.7%** | 100.0% | 76.4% |
| *rule-but-random-tiebreak ceiling* | | *82.0%* | | *82.3%* |
| *the clone itself* | | *26.2%* | | *22.1%* |

Five per-slot floats — `(star, cost, slot, on_bench, copies)` — predict the
teacher's sell choice **perfectly, on held-out data**. The observation the
agent actually reads predicts it at 20.7%, which is no better than the clone's
own 26.2%. The clone is not underperforming what its input supports; it is
already at it.

Note the hand-computed probe *exceeds* the 82.0% tie ceiling, which is the
ceiling behaving correctly rather than a contradiction: 82.0% is the score of a
model that learns the rule but guesses among ties, and this one also learns the
positional tiebreak from the `slot` feature.

**A correction to how this project states its own lesson.** The rule is "a
probe that cannot fit its own training set is a statement about the feature
set, not the model", and it is true — but the converse is not, and this run is
where that mattered. The observation head fitted **100% of its training set**
while generalising at 20.7%: with 381-dimensional inputs that are unique per
sample, a 512-wide network memorises, and the training fit carries no
information about whether the feature is present. **The generalisation gap is
the signal, not the training fit.** Reading the training fit alone here would
have concluded the opposite of the truth.

### 38.7 What the missing ingredient turned out to be

The first version of the hand-computed probe fitted **34.7% of its own training
set** — it could not represent the rule either. The missing feature was
`copies`: the teacher refuses to sell combine progress, so without a count of
how many copies of a champion the player holds, the label is not a function of
the features at all.

That is worth more than the fix, because of what the feature *is*. Counting
copies means matching champion identity between units in different slots. The
project's observation rule names exactly this:

> If a quantity requires an **identity match**, a dot product, a ranking or a
> threshold across slots, a flat MLP will not derive it. Supply it.

So the sell decision needs both operations the rule warns about — an identity
match (copies) and a ranking (weakest). SELECT needs only the ranking, and
scores 76.4% from the observation against SELL's 20.7%. **Two symptoms, one
mechanism, and their severity ordered by how many cross-slot operations each
requires.** That ordering was not predicted in advance and is the strongest
evidence here that the mechanism is real rather than fitted.

### 38.8 Next hypothesis, stated before it is tested

If the analysis is right, supplying the cross-slot comparisons should raise
SELL match toward the probe's 100% and — separately, and not to be assumed —
may move placement toward the teacher's 3.437.

The features to add are per bench slot: **star rank, cost rank, and copies
held**. The line drawn in 38.4 holds. Rank and copy count are facts a player
reads off the screen. Their lexicographic *combination* in the teacher's order
is the expert's policy and stays out.

Two failure modes named in advance, so neither can be narrated as success:

* Match rises, placement does not. Precedent exists — 24.2 raised aggregate
  match 81.8% → 88.7% with no placement movement. This would mean SELL match
  is not on the path to placement, and the 1.38 gap lives elsewhere.
* Neither moves. The observation was not the binding constraint and the
  descriptive-vs-relational framing does not explain this gap, despite the
  probe. The `features` encoding was rejected three times on stories that
  survived less scrutiny than this one, so this outcome is live.

### 38.9 The ranks were already there; the identity match was not

Checking the observation before adding anything to it: **star rank and cost
rank per unit slot already exist** — they are entry 30's twelve floats, added
for exactly this class of problem. So 38.8's proposal was half-shipped, and
that explains the asymmetry in 38.6 rather than leaving it a coincidence:
SELECT needs only the ranking, has it, and reads at 76.4%. SELL needs the
ranking *and* an identity match, has only the first, and reads at 20.7%.

What was missing is `copies` — how many copies of a champion the player holds
at that unit's star level. `owned` exists for *shop* slots (`SHOP_DERIVED_
FEATURES`) and has no counterpart on owned units.

Added behind `copy_counts`, default off. One float per owned unit slot,
381 → 418. Re-probing with it, everything else identical:

| | without | with |
|---|---|---|
| SELL, from the observation | 20.7% | **49.1%** |
| SELECT, from the observation | 76.4% | 77.5% |

**+28.4 points on SELL from one float per slot, and SELECT does not move.**
The specificity control was named in advance by the mechanism — SELECT's rule
has no copy term, so it should not move, and it does not. That is much better
evidence than the SELL jump alone.

Star level is load-bearing in the count: three 1-stars combine, a 1-star and a
2-star do not, so a count ignoring it would mark a unit as combine progress
when it is nothing of the kind — the exact judgement the sell rule makes.

Still 49.1% against the hand-computed probe's 100%, so **the observation is not
the whole story**, and the remaining gap now has a different candidate: the
hand-computed probe scores each slot through *shared weights* and takes an
argmax, while the observation head is a monolithic MLP with no
permutation-equivariance across slots. That is an architecture gap, not a
feature gap, and it is the next hypothesis after this one resolves.

**A near-miss worth recording, since it was in the method rather than the
code.** The first mutation run reported the star-level test passing against an
implementation with star level deliberately removed. The test was fine; `-k
copy` had never selected it, because "copies" does not contain the substring
"copy". Six tests ran where eight were expected and the discrepancy was not
checked. Mutation testing only proves anything if the mutated code and the
selected test actually meet — **count the tests that ran**.

## 39. Ranking is an architecture problem, not a feature problem (2026-08-04)

### 39.1 The same numbers, read two ways

[Entry 38.9](#389-the-ranks-were-already-there-the-identity-match-was-not) left
the observation at 49.1% on SELL against hand-computed features' 100%, and
named the next hypothesis: the hand-computed probe scores each slot through
*shared weights* and takes an argmax, while the observation head is a
monolithic MLP with no permutation-equivariance across slots.

Tested directly. A third probe reads **the same observation**, merely sliced
per unit slot, into a shared-weight scorer — no new information, only a
different arrangement of identical floats. Alignment was verified first: across
4,120 slots, block *i* of the board+bench sections is action slot *i*, zero
mismatches.

Two positional floats have to be appended per slot (`on_bench`, normalised
index). A shared-weight scorer sees each slot in isolation and structurally
cannot tell a board slot from a bench one, nor break ties by index — both of
which the monolithic head gets for free from *where* the numbers sit in its
input. Without them the probe measures the loss of position rather than the
gain from sharing, and it showed: SELECT fell to 41.1% against the monolithic
head's 79.1%, because its rule reads the strongest *bench* unit while the
strongest unit overall is usually fielded.

With them, held-out accuracy:

| | SELL | SELECT |
|---|---|---|
| hand-computed features | 100.0% | 100.0% |
| the real observation, monolithic MLP | 49.1% | 80.6% |
| **the real observation, per-slot + shared weights** | **99.9%** | **100.0%** |
| *tie ceiling* | *82.0%* | *82.3%* |
| *the clone itself* | *26.2%* | *22.1%* |

**The information was in the observation the whole time.** A permutation-
equivariant reader extracts it perfectly. The monolithic MLP cannot, and that
is the entire remaining gap.

### 39.2 Which of the two changes did what

Running the shared-weight probe *without* `copy_counts` separates them:

| | SELL | SELECT |
|---|---|---|
| shared weights, no copies | 36.9% train / 27.1% test | 99.6% |
| shared weights, with copies | 100.0% train / 99.9% test | 100.0% |

- **SELECT needs only the architecture.** 99.6% with no new feature at all.
- **SELL needs both.** Without `copies` the shared-weight scorer cannot fit
  even its own training set (36.9%), because a scorer that sees one slot at a
  time cannot count copies of a champion held in *other* slots any more than
  the monolithic head could.

That refines this project's central observation rule, which lists four
operations a flat MLP will not derive — identity match, dot product, ranking,
threshold across slots — and prescribes one remedy for all of them: supply the
quantity. The two probes separate the list into two kinds:

> **A ranking across slots is an architecture problem**, and weight sharing
> solves it completely without adding anything to the observation.
> **An identity match across slots is a feature problem**, and must still be
> supplied, because a per-slot scorer cannot compute it either.

Entry 30's twelve floats — star and cost ranks — were therefore a *workaround
for an architectural limitation*, and a successful one, closing a 1.266
placement gap. They are also, on this evidence, unnecessary given a
permutation-equivariant head. That is a claim about the probe so far, not about
placement, and it is not yet a reason to remove them.

### 39.3 What this predicts, before it is built

If the analysis holds, replacing the policy's flat head over slot actions with
a **shared-weight per-slot scorer** — one network scoring each slot from its
own block plus its position, then a masked softmax over slots — should let the
clone reach match rates near the probe's rather than near 26%. Every slot-typed
action is in scope: SELL, SELECT, PLACE and EQUIP together are 4,077 of 8,573
expert decisions, 48%.

This is a change to the network, not to the environment, so the observation and
the action space stay fixed and every prior measurement remains comparable.

Named in advance, so the outcome cannot be narrated afterwards:

* **Match rises to probe levels and placement follows.** The 1.38 clone-teacher
  gap was architectural. This is the breakthrough case.
* **Match rises, placement does not.** Precedent exists (24.2: aggregate match
  81.8% → 88.7%, placement unmoved). Would mean slot decisions are not on the
  path to placement, and the gap lives in BUY/BUY_XP or in combat.
* **Match does not rise.** The probe fits offline on a fixed dataset; a policy
  trained end-to-end through an SB3 feature extractor may not realise it. Would
  indict the training setup rather than the analysis.

## 40. One float per slot closes 76% of the clone-teacher gap (2026-08-04)

### 40.1 The result

Behaviour cloning, `--warm-start 400 --timesteps 0`, seed 0, n=150, identical
budget across all three. Only the marked thing differs. The teacher throughout
the last two rows is the sell-capable expert at **3.437**.

| clone | place | ci95 | LP | 1st | top4 | gap to its teacher |
|---|---|---|---|---|---|---|
| old teacher | 4.847 | 0.390 | -1.63 | 13.3% | 44.0% | -0.17 |
| sell teacher | 4.813 | 0.415 | -1.05 | 18.0% | 43.3% | +1.38 |
| **sell teacher + `copy_counts`** | **3.760** | 0.396 | **+10.07** | **28.7%** | **64.7%** | **+0.32** |

Paired on shared seeds, `copy_counts` against its own control:
**-1.053, t=-4.55, n=150**. The replay also reproduced both means exactly
(4.813 and 3.760), which doubles as a determinism check on model evaluation.

**One float per unit slot moved the clone 1.053 placement**, and closed 76% of
the 1.376 gap that [entry 38.1](#381-the-re-clone-a-null-and-a-failed-prediction)
opened. The distribution moves with the mean rather than around it: firsts
20 → 43, last places 30 → 16, top-four 43.3% → 64.7%, LP -1.05 → +10.07.

For scale, this is the largest single-feature effect measured in this project.
Entry 30's twelve rank floats closed a 1.266 gap; this is one float per slot,
37 in total, for 1.053.

### 40.2 What it confirms, and what it does not

Confirms the mechanism from 38.7 end to end. `copies` is an **identity match
across slots** — counting copies of a champion held in *other* slots — and
39.2 established that this is the one operation on doc 99's list that weight
sharing does *not* fix, because a per-slot scorer cannot compute it either. It
had to be supplied, and supplying it worked.

It does **not** confirm the architecture hypothesis, which is a separate
prediction and is still running. Note the two are not additive by assumption:
this clone reads its observation through the same monolithic MLP that the probe
in 39.1 could only push to 49.1% on SELL, yet its *placement* is within 0.32 of
its teacher. So a policy can be near teacher-level on placement while
disagreeing with the teacher on nearly half of a common decision type.

That is the third time in this project that match and placement have come
apart, and it is worth stating as the general form: **match measures agreement
with a particular teacher's choices, including its arbitrary ones; placement
measures whether the game was played well.** Where the teacher's choice among
several good options is arbitrary — which is most of what ties are — the two
must diverge.

### 40.3 A note on how close this now is

The clone is 0.32 behind its teacher and the teacher is 3.437 against bots at
4.500. Before today the best clone in this project sat at 4.567 against a
teacher at 4.620 and the arc had been flat for eleven entries. The chain that
produced this was: the teacher could not sell (37.4) → the better teacher did
not transfer (38.1) → the disagreement was one action kind (38.2) → it was not
ties (38.3) → the missing quantity was an identity match (38.7) → adding it
moved the probe (38.9) → and it moves the agent (40.1).

None of the individual steps was a large piece of work. Every one of them
depended on measuring the ceiling before interpreting the rate.

### 40.4 Still open

1. The architecture arm (`--slot-head`), running now. 39.3 named its outcomes.
2. Whether `copy_counts` should become the default. It changes the observation
   width, so every prior model becomes unloadable against it -- deferred until
   the architecture result lands, so both defaults change once rather than
   twice.
3. PPO from this warm start, untested. Every previous attempt started from a
   clone at 4.5-4.8; none has started from 3.76.
4. Whether the remaining 0.32 is ties. The clone need not break them the
   teacher's way, so part of this gap may not be a defect at all.

### 40.5 Operational: torch threads, and why two runs are slower than one

Three concurrent jobs on a 12-core M3 Pro ran far slower than their serial cost
predicted. Cause: torch defaults to **6 intra-op threads per process**, so two
training runs plus an evaluation oversubscribe every performance core, and the
nets here are small enough that the threading buys nothing to begin with —
39.1's whole point is that the model is tiny and the work is elsewhere.

Two consequences worth carrying:

* Run the *simulator* in parallel (37.8's `evaluate_scripted_parallel`, near
  linear because each worker is one busy core running pure-Python ticks) and
  the *torch* work serially, or pin `OMP_NUM_THREADS=1` when overlapping runs.
  These are opposite prescriptions for the same machine and it matters which
  workload is which.
* Process-elapsed times were misread twice while diagnosing this, because
  `pgrep -f <script>` matches the waiting shell's own command line as well as
  the process it is waiting for. Wait on the artifact — a line in the log, a
  file on disk — not on a process pattern.

Neither is a result, but both cost real time today.

## 41. The slot head regresses: a scorer with no context (2026-08-04)

### 41.1 The result: outcome 3, and a large regression

[Entry 39.3](#393-what-this-predicts-before-it-is-built) predicted that a
shared-weight slot head would lift the clone toward the probe's match rates.
Same teacher, same budget, same seed, `copy_counts` on in both:

| clone | place | ci95 | LP | 1st | top4 | 8th |
|---|---|---|---|---|---|---|
| monolithic head | **3.760** | 0.396 | +10.07 | 28.7% | 64.7% | 16 |
| `--slot-head` | **5.147** | 0.398 | -4.55 | 16.0% | 38.7% | **41** |

**+1.387 placement worse.** Last places rose from 16 to 41 of 150. This is
39.3's third outcome — the offline probe result did not transfer — and it is
not a null but a clear regression.

Training match barely moved (85.0% → 82.5% at epoch 50), which is itself
informative: the head was learning the dataset about as well while playing far
worse.

### 41.2 Why: the scorer cannot see anything but its own slot

Match by kind against the sell teacher, expert states, locates it exactly:

| kind | monolithic | slot head |
|---|---|---|
| BUY | 83.9% | 83.0% |
| SELL | 83.0% | 75.5% |
| **SELECT** | **66.7%** | **37.0%** |
| **PLACE** | **68.8%** | **44.0%** |
| EQUIP | 58.7% | **83.4%** |

EQUIP *improved* by 24.7 points — it is the one slot-typed decision that
depends only on which unit is the best carry, which is exactly what a per-slot
scorer computes. SELECT and PLACE collapsed.

The cause is a design error in the head, not in the hypothesis. My scorer feeds
each slot **only its own unit block plus `on_bench`**. But:

* `PLACE`'s rule is melee-to-the-front, ranged-to-the-back — a function of the
  **held** unit's attack range and the **target hex's row**. The held unit lives
  in the observation's `selection` section and the row is positional. The
  scorer sees neither. It cannot express the placement rule *at all*.
* `SELECT` similarly switches regime on whether the board is full, a fact in the
  `self` block that the scorer also never receives.

The monolithic head reads the whole observation and has both for free. In
removing its ability to confuse slots, I removed its ability to see the context
that makes slot decisions meaningful.

The probe did not catch this because it only ever asked about SELL and SELECT
in isolation, on states where the teacher had already decided to take that
action. **A probe on a decision studied alone cannot detect that the decision
needs context the probe itself supplied by construction.**

### 41.3 What this does and does not refute

It does **not** refute 39.2's decomposition. Weight sharing still reads SELL
and SELECT off the observation at 99.9%/100% offline, and EQUIP's +24.7 points
is that effect surviving into a trained agent. What is refuted is the specific
claim in 39.3 that *this head* would lift the clone: a per-slot scorer with no
global context is strictly weaker than a monolithic MLP for any decision whose
rule reads something outside the slot.

The correct form is the standard pointer-network one, and it is the next
iteration rather than a conclusion: **score each slot from its own block *and*
a learned embedding of the whole observation**, so the head keeps the weight
sharing and regains the context. That is one concatenation.

Prediction, before it runs: PLACE and SELECT recover toward the monolithic
head's rates while EQUIP keeps its gain, and placement lands between 3.760 and
the teacher's 3.437. If instead it merely returns to ~3.760, the sharing buys
nothing once context is available, and the architecture line closes.

### 41.4 The third script with a hardcoded env config

`action_match.py` collected expert data at 381 floats while the models needed
418, and failed with a torch shape error. That is the same defect as 37.7
(`train_ppo`'s hardcoded teacher) and 38.2 (`action_match`'s hardcoded teacher)
— a script that reconstructs an env or a teacher from defaults rather than from
what the artifact was built with.

The general fix, not yet done: runs already write a metadata sidecar recording
every argument, and `compare_models.py` reads env options back out of it. Every
script that loads a model should do the same instead of taking flags that can
silently disagree with the checkpoint.

### 41.5 Editing a custom policy orphans every checkpoint that used it

Adding the context term to `SlotScoringHead` made
`runs/reclone-slothead/model.zip` **unloadable**. SB3 stores the custom policy
class by reference and rebuilds it from *current* source, so the saved weights
no longer match the class they are loaded into:

```
Missing key(s): action_net.context_net.0.weight ...
size mismatch for action_net.slot_net.0.weight:
  checkpoint torch.Size([128, 8]) vs current torch.Size([128, 72])
```

Nothing analytical was lost -- 41.1's placement and 41.2's match table were
already recorded -- but the artifact is dead and cannot be re-measured without
retraining. This is a sharper version of the reproducibility rule the flags
follow: a *flag* default can be left off so old runs reproduce, but there is no
equivalent for the shape of a network. Any edit to a custom head is a one-way
door for its checkpoints.

It also took out a comparison that was two-thirds finished, because
`compare_models.py` loaded all models up front and died on the third. It now
skips an unloadable run and reports why, so one dead artifact cannot cost the
arms that still load.

Worth doing before the next head edit: version the head, or write its
constructor arguments into the run's metadata sidecar so a mismatch reports
itself as a version difference rather than as a tensor shape.

## 42. Context restores the slot head to parity, and no further (2026-08-04)

### 42.1 The result

The corrected head — each slot scored from its own block, its position, **and**
a learned embedding of the whole observation. Same teacher, budget and seed;
`copy_counts` on throughout. n=150.

| clone | place | ci95 | LP | 1st | top4 | 8th | bc match |
|---|---|---|---|---|---|---|---|
| monolithic head | 3.760 | 0.396 | +10.07 | 28.7% | 64.7% | 16 | 85.0% |
| slot head, no context | 5.147 | 0.398 | -4.55 | 16.0% | 38.7% | 41 | 82.5% |
| **slot head + context** | **3.793** | 0.384 | +9.48 | 28.7% | 62.0% | **11** | **89.1%** |

Adding context recovered the whole 1.387 regression — and stopped exactly at
the monolithic head's number. **+0.033 against it: a null.**

[Entry 41.3](#413-what-this-does-and-does-not-refute) named this branch in
advance: "if it merely returns to ~3.760, the sharing buys nothing once context
is available, and the architecture line closes." It returns to 3.793. **The
line closes.**

### 42.2 The fourth divergence between match and placement

The context head fits the teacher **better than either alternative** — 89.1%
against 85.0% and 82.5% — and plays no better than the monolithic one. That is
now the fourth time in this project that match and placement have come apart,
and the clearest instance: a 4.1-point match improvement bought 0.033 placement,
which is noise.

The distributions differ slightly at equal means — last places 16 → 11, top-four
64.7% → 62.0%, firsts identical at 43 — which is the same "same mean, different
shape" pattern as §31's KL arm and §37.6's roll arm. Nothing here justifies
preferring either head.

**The practical conclusion is to keep the simpler one.** The slot head is ~130
lines, a custom SB3 policy class, and a one-way door for its checkpoints
(41.5). It buys nothing measurable. `--slot-head` stays available and stays off
by default.

### 42.3 What the architecture arc actually produced

Worth stating plainly, because the arc looks like a failure and is not:

* 39.1's finding stands as a fact about *offline probing*: a shared-weight
  reader extracts SELL and SELECT from the observation at 99.9%/100% where a
  monolithic MLP manages 49.1%/80.6%.
* That fact did **not** convert into placement. The monolithic head reaches
  within 0.32 of its teacher while disagreeing with it on half of SELL.
* So the probe measured a real property of the representation that turned out
  not to be the binding constraint on play.

The generalisable lesson, and it is uncomfortable: **an offline probe
establishes what a representation *can* express, not what the agent needs.**
Entry 38.6's probe correctly identified a missing feature that was worth 1.053
placement. Entry 39.1's probe, run the same way with the same rigour,
identified an architectural limitation worth 0.033. The probes were equally
sound; only one of the gaps mattered. A probe result is a hypothesis about
placement, never a substitute for measuring it.

### 42.4 Where the ceiling now sits

The clone is at 3.760 and its teacher at 3.437 — a 0.32 gap, against 1.38
before `copy_counts`. Two directions remain, and they are different in kind:

1. **Close the last 0.32.** Diminishing, and part of it may not be a defect at
   all: where the teacher's choice among tied options is arbitrary, the clone
   need not match it to play as well.
2. **Raise the teacher.** It is 3.437 and it is the ceiling for imitation. And
   the flag sweep that measured `buy_synergy`, `match_items` and `corner_carry`
   (§34.13) ran on a teacher that **could not sell** — the same invalidation
   that 36.6 applied to the econ arms. Those flags have never been measured on
   a teacher that plays a normal game.

(2) is the cheaper and larger lever, and `evaluate_scripted_parallel` now makes
that sweep about seven minutes rather than two hours.

## 43. The flag sweep, re-run on a teacher that can sell (2026-08-04)

### 43.1 Why it needed re-running

`buy_synergy`, `match_items` and `corner_carry` were measured in §34.13 against
a teacher whose bench filled after a few rounds and which then made 28.6
purchases a game against an achievable 136.8 (37.4). Every one of them is a
judgement about *which units and items to acquire*, on a policy that had
largely stopped acquiring. That is the same invalidation 36.6 applied to the
econ arms, and it was noticed only after 42.4 went looking for the next lever.

300 seeds, paired, all arms sell-capable, one process, ~10 minutes with
`--workers 8`.

### 43.2 Result: no flag is significant alone, the combination is

| arm | place | ci95 | LP | 1st | top4 | 8th | floor | vs control (paired) |
|---|---|---|---|---|---|---|---|---|
| control | 3.437 | 0.266 | 13.11 | 33.0% | 65.7% | 21 | 7.0% | — |
| buy_synergy | 3.197 | 0.256 | 15.71 | 35.7% | 70.3% | 16 | 5.3% | -0.240, t=-1.60 |
| match_items | 3.450 | 0.265 | 12.93 | 33.0% | 65.0% | 20 | 6.7% | +0.013, t=+0.67 |
| corner_carry | 3.300 | 0.262 | 14.75 | 35.0% | 70.3% | 19 | 6.3% | -0.137, t=-1.05 |
| **all_three** | **3.030** | 0.241 | **17.34** | **37.0%** | **72.3%** | **12** | **4.0%** | **-0.407, t=-2.82** |

`match_items` remains a clean null even now — 0.013 at t=+0.67, and its
distribution is nearly identical to control's. The other two are each
sub-threshold on their own, and together with the null they clear it.

The combination is very close to additive: the individual deltas sum to -0.363
against a measured -0.407. So this is not an interaction effect, it is three
small independent gains, two of which are simply too small to resolve at n=300
on their own. Worth stating because "the whole is more than the parts" would
have been the tempting reading and the numbers do not support it.

The distribution moves in the right direction throughout: last places 21 → 12,
firsts 99 → 111, floor rate 7.0% → 4.0%.

### 43.3 The teacher is now 3.030

Against 4.500 for the bots it plays. The arc of the teacher across today:

| teacher | place |
|---|---|
| as it stood this morning | 5.017 |
| + sell branch (37.4) | 3.437 |
| + buy_synergy, match_items, corner_carry | **3.030** |

Cloning from it is running. Whether the student follows is a separate question
and has already gone the wrong way once today (38.1), so it is being measured
rather than assumed.

One caution carried forward: `--expert-flags` sets all three together because
that is the arm that was significant. Nothing here says `match_items` earns its
place, and it is included only because removing a null from a measured
combination would be re-deriving the result from arms that were not run.

## 44. The better teacher's gain does not resolve in the clone (2026-08-04)

### 44.1 The number, and its t

Cloning from the 3.030 teacher (sell + all three flags), against cloning from
the 3.437 teacher (sell only). Same seed, budget and observation; n=150.

| clone of | place | ci95 | LP | 1st | top4 | 8th | vs the other (paired) |
|---|---|---|---|---|---|---|---|
| sell teacher (3.437) | 3.760 | 0.396 | +10.07 | 28.7% | 64.7% | 16 | — |
| flags teacher (3.030) | 3.533 | 0.367 | +12.36 | 30.0% | 70.0% | 12 | **-0.227, t=-0.99** |

**t=-0.99 is not significant.** The mean moved in the predicted direction and
by roughly the amount the teacher gained (-0.407 in the teacher, -0.227 in the
student), and the distribution moved consistently — top-four 64.7% → 70.0%,
last places 16 → 12 — but none of that survives the standard this project
holds itself to. At n=150 a 0.227 difference is inside the noise.

This is recorded as **⚠️ n**, not as a result. A re-measurement at n=300 is
running. Naming the outcomes first:

* **It resolves.** Teacher gains transfer at roughly half strength, and raising
  the teacher stays the cheapest lever.
* **It does not resolve.** Then 3.533 is not distinguishable from 3.760, the
  -0.407 teacher gain did not reach the student, and the *transfer* question
  from 38.1 reopens: `copy_counts` let the student follow one teacher
  improvement, and it does not follow that it will follow every one.

The second outcome is entirely live. Today already contains one teacher
improvement of 1.58 that produced 0.03 in the student.

### 44.2 What is safe to say without the re-measurement

The teacher is 3.030 and that is measured at n=300 with t=-2.82 (§43.2). The
best clone is somewhere in the 3.5-3.8 range. The clone-teacher gap is
0.32-0.50 depending on which pairing is used, against 1.38 this morning.

The honest summary of the day's arc is that **the agent improved from 4.813 to
somewhere near 3.6, and exactly one step of that is individually significant**
— `copy_counts`, at t=-4.55. The rest is directionally consistent and
individually under-powered, which is what a sequence of 0.2-placement
improvements measured at n=150 looks like.

### 44.3 Resolved at n=300: it does not transfer

> **Outcome 2 of the two named in 44.1.**

| clone of | place | ci95 | LP | 1st | top4 | vs the other (paired) |
|---|---|---|---|---|---|---|
| sell teacher (3.437) | 3.820 | 0.271 | +9.22 | 26.3% | 62.7% | — |
| flags teacher (3.030) | 3.747 | 0.263 | +9.93 | 26.0% | 64.3% | **-0.073, t=-0.48** |

The n=150 estimate of -0.227 shrank to **-0.073 at n=300**, t=-0.48. A
0.407-placement improvement in the teacher produced nothing measurable in the
student. Row 23 of the arc table is corrected accordingly: the teacher moved,
the agent did not.

Note also that the *same model* read 3.760 at n=150 and 3.820 at n=300. That
0.06 is a reminder of what n=150 buys, and why 44.1 was filed as ⚠️ rather than
as a new best.

**The day's only individually significant agent improvement is `copy_counts`,
at t=-4.55.** Everything else moved the teacher, or moved the student by less
than the noise.

### 44.4 The transfer question, restated

Two teacher improvements today, two different fates:

| teacher change | teacher | student |
|---|---|---|
| + sell branch | -1.580 | **0.00** (4.847 → 4.813) |
| + sell branch, *with* `copy_counts` | -1.580 | -1.053 (t=-4.55) |
| + buy_synergy/match_items/corner_carry | -0.407 | -0.073 (t=-0.48) |

The pattern is consistent and it is the same one 38.7 identified: **a student
follows a teacher only where its observation supports the decision the teacher
changed.** Selling was unfollowable until `copies` was added; then it followed
almost fully. The flag improvements are apparently unfollowable now.

That is a testable claim rather than a story, and it names the next step
exactly. `buy_synergy` shops on trait synergy; `corner_carry` is a positional
rule. Match by kind against the *flags* teacher will say which decision the
student is failing, as it did in 38.2 and 41.2. If the answer is BUY, note that
`synergy` is already encoded — but only for **shop** slots
(`SHOP_DERIVED_FEATURES`), which is exactly the sort of asymmetry that produced
the `copies` finding.

Not assumed: that the answer will be a missing feature. 42.3 is the standing
caution — a representation gap found by probing is a hypothesis about
placement, and one of the two found today was worth 1.053 while the other was
worth 0.033.

## 45. BUY: the one argmax the slot head never covered (2026-08-04)

### 45.1 Following 44.4's prediction to the decision it named

Match by kind for the clone of the flags teacher, against the clone of the
sell-only teacher, both on expert states:

| kind | clone of sell teacher | clone of flags teacher |
|---|---|---|
| **BUY** | **83.9%** | **77.4%** |
| SELL | 83.0% | 75.4% |
| BUY_XP | 67.1% | 88.7% |
| PLACE | 68.8% | 74.2% |
| SELECT | 66.7% | 67.1% |
| EQUIP | 58.7% | 58.6% |

BUY got *worse* when the teacher started shopping on synergy — the one
decision `buy_synergy` changes. EQUIP is unchanged at 58.6%, consistent with
`match_items` being a measured null (43.2).

### 45.2 A hypothesis killed in two minutes

The shop `synergy` feature is written as
`min(sum(trait_counts) / max_level, 1.0)` — **clipped**. If real synergy sums
exceeded the scale, the ranking would saturate exactly on developed boards and
the teacher's rule would be unreadable there.

Measured over 4,636 shop slots at BUY decisions: **0% saturated.** The largest
synergy seen is 9 against a scale of 10, and clipping never merges two distinct
values. The feature is fine.

Recorded because the cost of checking was two minutes and the cost of believing
it would have been a day.

### 45.3 The probe: BUY has headroom that the unit slots did not

| | test |
|---|---|
| hand-computed (owned, synergy, cost) | 92.3% |
| the real observation, monolithic MLP | 68.1% |
| **the real observation, per-slot + shared weights** | **84.4%** |
| *rule-but-random-tiebreak ceiling* | *91.8%* |
| *the clone itself* | *77.4%* |

Three hand-computed floats read the rule essentially at its ceiling, so nothing
is missing from the observation — this is not another `copies`. But a shared
weight reader gets 84.4% where a monolithic one gets 68.1%, and **the first
slot head never touched the shop section at all**: it covered SELL, SELECT,
PLACE and EQUIP only.

BUY is 2,532 of 6,860 expert decisions — 37%, the largest single kind — and it
is the decision that determines what the board is made of.

### 45.4 Why this is not simply 42 again

§42 found that shared weights over *unit* slots bought 0.033 placement, and
42.3's standing caution is that a probe gap is a hypothesis about placement,
not a result. That caution applies here in full.

The reasons to run it anyway, stated before the result:

* The unit-slot head reached parity because the monolithic head was *already*
  near its own ceiling there. On BUY the clone sits at 77.4% against a 91.8%
  ceiling — 14 points of headroom, where SELL had ~1.
* BUY is 37% of decisions rather than EQUIP's 3%.
* 44.3 established that the *teacher* is 0.407 better and the student captures
  none of it. If that gap is BUY-shaped, this is the mechanism.

Outcomes named in advance:

* **BUY match rises and placement follows.** The 0.407 was BUY-shaped and the
  student can now follow teacher improvements to shopping.
* **BUY match rises, placement does not.** The fifth match/placement
  divergence, and strong evidence that shopping *choice* is not what separates
  3.75 from 3.03 — which would point at what the teacher does with what it
  buys, i.e. positioning and itemisation.
* **Neither moves.** The offline probe does not transfer for shop slots either,
  and the architecture line closes for good.

Running at n=300 rather than 150, because 44.1 showed n=150 cannot resolve a
0.2 difference and the honest sample size is the one that can.

### 45.5 Result: every argmax improved, and PLACE collapsed

Clone from the flags teacher with the shop-extended slot head, n=300:

| clone | place | ci95 | LP | 1st | top4 | bc match |
|---|---|---|---|---|---|---|
| monolithic head | 3.747 | 0.263 | +9.93 | 26.0% | 64.3% | 84.6% |
| slot + shop head | 3.840 | 0.272 | +8.86 | 27.7% | 59.7% | 87.1% |

No gain. Match by kind says why, and it is not subtle:

| kind | monolithic | slot + shop head |
|---|---|---|
| **BUY** | 77.4% | **84.4%** |
| **EQUIP** | 58.6% | **89.6%** |
| **SELECT** | 67.1% | **75.4%** |
| SELL | 75.4% | 78.5% |
| **PLACE** | **74.2%** | **37.9%** |
| BUY_XP | 88.7% | 80.2% |

BUY landed on **84.4%** — the probe in 45.3 predicted 84.4%, to the decimal.
EQUIP rose 31 points, SELECT 8.3. Four of the five slot-typed decisions
improved, several substantially, and placement did not move because PLACE fell
36.3 points and cancelled them.

**The cause is my own earlier decision, applied too broadly.** When I dropped
the raw slot index from the head (§41-42) the reasoning was sound: the index
encodes the teacher's arbitrary "lowest bench index wins" tiebreak, and copying
that is imitating an implementation detail. But the index was carrying a second
thing — **which row of the board a hex is in** — and PLACE's entire rule is
melee to the front rows, ranged to the back. A shared scorer that cannot tell
the front row from the back cannot express the placement rule at all.

Two facts were riding on one feature and I removed both while reasoning about
one. The row is now supplied explicitly, read from the board geometry rather
than from slot ordering, with the arbitrary index still absent.

This also explains a loose end from 41.2: the context-free head scored PLACE at
44.0% and I attributed all of it to the missing global context. Context was
genuinely missing — it is worth ~6 points here — but most of that gap was the
row, and 42's context fix restored PLACE only because the *monolithic* trunk
was still producing those logits at the time.

Re-running with the row restored, n=300. Named in advance: if PLACE returns to
~74% while BUY/EQUIP/SELECT keep their gains, aggregate match should reach the
high 80s and this becomes the first architecture arm with a real chance at
placement. If placement still does not move with four of five decision kinds
improved and none regressed, that is decisive evidence that **imitation match
is not the path to placement here**, and the next lever is elsewhere entirely.

### 45.6 Resolved: match rose 5 points, placement did not move

With the board row restored, n=300, paired against the monolithic head:

| clone | place | ci95 | LP | 1st | top4 | bc match | agreement |
|---|---|---|---|---|---|---|---|
| monolithic head | 3.747 | 0.263 | +9.93 | 26.0% | 64.3% | 84.6% | 76.8% |
| slot + shop + row | 3.537 | 0.270 | +12.12 | 32.0% | 64.7% | 89.6% | **81.9%** |
| | | | | | | | **-0.210, t=-1.43** |

Match by kind, all against the flags teacher on expert states:

| kind | monolithic | slot+shop | slot+shop+row |
|---|---|---|---|
| BUY | 77.4% | 84.4% | **85.1%** |
| SELL | 75.4% | 78.5% | **79.0%** |
| SELECT | 67.1% | 75.4% | **76.7%** |
| PLACE | 74.2% | 37.9% | **75.3%** |
| EQUIP | 58.6% | 89.6% | **87.8%** |

**Every slot-typed decision improved, none regressed, aggregate agreement rose
5.1 points — and placement is t=-1.43.** This is the second outcome named in
45.4, and it is the decisive form of a pattern that recurred five times today.

The row diagnosis was correct: PLACE returned from 37.9% to 75.3%, above the
monolithic head's own rate, confirming that removing the slot index had taken
the board row with it and that context was only a small part of 41.2's gap.
BUY landed at 85.1% against the probe's predicted 84.4%. The mechanism worked
exactly as analysed. It simply does not produce placement.

**The conclusion for the architecture line, stated at full strength: imitation
agreement is not the binding constraint on play in this environment.** Five
times today a change moved match without moving placement (§40.2, §42.2, §44.3,
§45.5, and this), and once a change moved placement 1.053 while *lowering* SELL
agreement's ceiling relevance (§40). Agreement measures whether the student
reproduces a particular teacher's choices, including its arbitrary ones.
Placement measures whether the game was played well. Optimising the first has
now been shown, repeatedly and at n=300, not to deliver the second.

`--slot-head` stays off by default. The head is ~130 lines, a custom SB3 policy
class, and a one-way door for its checkpoints (41.5); it buys 0.210 placement
at t=-1.43. It is kept rather than deleted only because the *diagnostic* value
was high — it produced the row finding and the BUY probe confirmation.

### 45.7 What this says about the approach

Nineteen entries of PPO have produced no improvement (§18, §23, §31, §32, and
today's arms). Every gain this project has ever measured came from one of two
places: **making the teacher better**, or **supplying a quantity the
observation lacked**. Both are capped — imitation cannot exceed its teacher,
and 45.6 shows agreement is no longer the lever.

The teacher is 3.030 and the clone 3.5-3.7. That is the ceiling of the current
paradigm, and it is close.

The untried direction is **search**. The engine is a fast deterministic
simulator, which is exactly the object a rollout or expert-iteration method
needs and which most RL projects do not have. A teacher built from search
optimises placement directly rather than a hand-written lexicographic guess,
and the cloning half of the pipeline — the half that demonstrably works — stays
unchanged. Recorded here as the recommendation, not yet as a measurement.

## 46. One-ply board search (2026-08-04)

### 46.1 Why search, and what was built

45.7's argument: every gain this project has measured came from raising the
teacher or from supplying a missing quantity, both are capped, and PPO has
produced nothing in nineteen entries. The untried direction is **search**, for
which this project has the one asset most RL projects lack -- a fast
deterministic simulator that can be queried as a model.

`rl/search.py`. At the end of each planning phase, each benched unit is
considered as a swap onto the board, the resulting board is simulated against a
panel of the strongest living opponents, and the swap is kept only if it beats
the current board by a margin.

Two constraints on the design, both from today's findings rather than from
taste:

* **It does not use the actual next opponent.** The pairing is unknown during
  planning, and a teacher optimising against information the student's
  observation lacks is a teacher the student cannot follow -- 38.7 and 44.4
  measured that twice.
* **Its decisions execute through the action space**, as SELECT then PLACE. A
  teacher whose choices cannot be expressed as actions cannot be cloned however
  good its boards are.

### 46.2 Result: null, and the reason is a noise floor

300 seeds, paired, both arms sell-capable:

| arm | place | ci95 | LP | 1st | top4 | vs control (paired) |
|---|---|---|---|---|---|---|
| control | 3.437 | 0.266 | 13.11 | 33.0% | 65.7% | — |
| + 1-ply search | 3.367 | 0.252 | 13.77 | 31.3% | 67.7% | **-0.070, t=-0.57** |

A null. Before reading anything into that, two diagnostics -- because a null
from a search that never fires, or that is measuring noise, is a statement
about the configuration rather than about search:

* **The search fires on 43.2% of planning phases.** It is not a no-op.
* **The noise floor exceeds the decision margin.** Re-simulating the *same*
  two boards with different combat seeds gives fight values with a standard
  deviation of **0.64**, against a margin of 0.5.

So at one trial per opponent the search was choosing between candidates largely
on noise. That is the same class of error as measuring a rate without its
ceiling: the *signal* was never established to exceed the *variance* of the
measurement it was built on.

`trials` now averages each candidate over several combat seeds, drawn once and
reused across candidates so that candidates are compared on the same fights.
Three trials cuts the spread to ~0.37, below the margin. Re-running.

Named before the result: if the null holds with the noise floor below the
margin, one-ply board choice is genuinely not worth anything here and the
search hypothesis needs a different decision -- positioning or itemisation --
rather than a bigger budget on this one.

### 46.3 With the noise floor below the margin: still not resolved

Same 300 seeds, `trials=3` so each candidate is averaged over three combat
seeds and the spread falls from 0.64 to ~0.37, below the 0.5 margin.

| arm | place | ci95 | LP | 1st | top4 | vs control (paired) |
|---|---|---|---|---|---|---|
| control | 3.437 | 0.266 | 13.11 | 33.0% | 65.7% | — |
| search, 1 trial | 3.367 | 0.252 | 13.77 | 31.3% | 67.7% | -0.070, t=-0.57 |
| search, 3 trials | 3.283 | 0.254 | 14.74 | 34.7% | 69.3% | **-0.153, t=-1.32** |

**The effect estimate doubled when the noise was halved** (-0.070 → -0.153),
which is the signature of a small real effect emerging from variance rather
than of nothing at all. It is still not significant at n=300.

46.2 pre-registered the reading for this case: "if the null holds with the
noise floor below the margin, one-ply board choice is genuinely not worth
anything here." The honest verdict is narrower than that, because t=-1.32 is
under-powered rather than flat: **one-ply board *selection* is worth something
on the order of 0.15 placement, and resolving that at this n would take
roughly four times the seeds.**

That is a poor trade. 0.15 does not change the picture -- the teacher is 3.030,
the clone 3.5-3.7, and imitation caps at the teacher regardless. Spending two
more hours to put a confidence interval around 0.15 buys a number, not a
direction.

**What the run does establish, and it is the useful part:** search *works
mechanically*. It fires on 43.2% of phases, its decisions execute through the
action space, it does not perturb the game it runs inside, and reducing its
measurement noise moves its effect in the predicted direction. The machinery is
sound; this particular decision is simply not where the value is.

### 46.4 The next decision to search, and why

`best_swap` searches *which unit to field*. The teacher was already competent
at that -- it fields by `(star, cost)`, which is a decent proxy, so there was
little to win.

The decision the teacher does *crudely* is **positioning**: `_preferred_hex`
puts melee in the front rows and ranged in the back, and nothing else. Doc 99's
still-open list has carried "multi-target abilities pick victims by list order,
not position" since §36 precisely because positioning has never been exercised.
A search over *where* to place a unit has a much larger space of outcomes than
a search over which unit to place, and no heuristic competitor to beat.

Not yet measured, and named as a hypothesis rather than a plan: if positioning
search also returns ~0.15, then search yields small broad gains here and the
paradigm does not change; if it returns substantially more, positioning is the
untapped axis and the engine's own §36 gap becomes the thing to fix first.

### 46.5 A ledger of what runs cost

Every measurement here is a wall-clock commitment and the only record of that
cost was whatever was remembered, which was wrong twice today: a 7-arm sweep
launched as "about an hour" took 2h 05m, and the search arm was described as
~1.7x a plain arm when with `trials=3` it is ~6x.

`rl/timing.py` appends one JSON line per run; every script prints an estimate
before it starts and its actual on completion. `scripts/timings.py` reports the
accumulation. Today's observed durations were backfilled so the first estimates
are real rather than empty.

| kind | runs | median | typical shape |
|---|---|---|---|
| `bc_clone` | 3 | 39m | warm-start 400, eval 150 |
| `compare_models` | 2 | 68m | 300 episodes, 2 models |
| `expert_ab` | 4 | 8m | up to 7 arms, parallel |
| `pytest` | 1 | 9m | full suite |
| `smoke` | 1 | 60s | whole-game invariants |

Two design points. Estimates use the **median per-unit rate**, not the mean, so
one run that shared a machine with two others does not drag every later
estimate. And rates are per `episodes x arms / workers`, so an estimate
transfers across sweep sizes rather than only matching identical runs.

Search arms record under a separate kind: one full combat simulation per
candidate per panel member per trial is a different cost class, and mixing them
would make both estimates useless.

## 47. Positioning is worth 5.8 units and nobody optimises it (2026-08-04)

### 47.1 The question, asked before building anything

46.4 proposed searching *where* to place units rather than *which* to field.
Before building that -- or fixing the positional-targeting gap §36 has carried
open -- establish that position affects outcomes in this engine at all.
Searching a dimension the simulator does not express finds nothing, and no
budget fixes that.

`scripts/position_probe.py`. Hold both boards fixed, re-fight under many random
arrangements of one side, and compare the spread against the engine's own
noise: the **same arrangement re-fought under different combat seeds**. That
control is what makes the number interpretable, and it is the same discipline
as measuring a ceiling before reading a rate.

### 47.2 Result: positioning dominates engine noise

40 sampled states, 16 arrangements and 16 combat seeds each:

| | value |
|---|---|
| sd from **rearranging** (combat seed fixed) | **1.661** |
| sd from **reseeding** (arrangement fixed) | 0.593 |
| best-minus-worst arrangement, mean per state | **5.78 units** |
| signal / noise | **2.80** |

Moving the same units around is worth **2.8x the engine's own variance**, and
the gap between the best and worst arrangement of an identical board averages
**5.78 surviving units** -- on boards of 4 to 9. That is an enormous
unexploited axis.

For scale: the entire flag sweep in §43, three heuristic improvements together,
moved the teacher 0.407 placement. The teacher currently chooses its
arrangement with `_preferred_hex` -- melee to the front rows, ranged to the
back, and nothing else. **No policy in this project has ever optimised
positioning**, exactly as no policy had ever sold a unit this morning (37.4).

### 47.3 The probe found the opposite answer first, because of a bug in the probe

The first run reported sd 0.000 from rearranging and concluded positioning does
not matter. The cause was ordering in my own probe:

```python
player.board.clear()
player.board.update(rearranged(player, rng))   # reads player.board -- now empty
```

`rearranged` reads the board it is rearranging, and clearing first meant every
"layout" was an **empty board**, every fight a -99, and every spread exactly
zero. A ratio of exactly 0.00 was the tell; a bug that produces a suspiciously
clean number is easier to catch than one that produces a plausible one, and
this one produced the cleanest possible.

There is now an assertion: if every candidate layout scores as an empty board,
the probe raises rather than reporting a confident zero.

**The lesson is not "check for bugs" but something narrower.** This probe was
built to answer a go/no-go question, and its failure mode returned the
*no-go* answer. A measurement whose bugs all point one way needs a positive
control -- the reseeding arm was already there and read 1.053 against
rearranging's 0.000, which is an impossible combination and should have been
read as such immediately rather than after a separate check.

### 47.4 What follows

Two things, and they are the same thing:

1. **The teacher should search its arrangement.** The machinery from §46 works
   -- it fires, executes through the action space, and does not perturb the
   game. Pointed at unit choice it found ~0.15 because `(star, cost)` was
   already a decent incumbent. Pointed at positioning it has a 5.78-unit spread
   to work in and an incumbent that is two rules long.
2. **§36's open item 4 is now the highest-value engine gap**, not a footnote.
   Multi-target abilities picking victims by list order rather than by position
   means part of this axis is still unmodelled -- and 47.2 says the modelled
   part alone is worth 2.8x noise. Fixing it makes positioning matter *more*,
   not less.

Prediction, before either is done: positional search returns substantially more
than the 0.15 that unit-choice search returned. If it does not, the 5.78-unit
spread is dominated by arrangements a sensible policy would never pick, and the
reachable part of the space is small -- which would be worth knowing and is the
reason to measure rather than assume.

### 47.5 Positional search: 0.203, and a failed prediction

300 seeds, paired, both arms sell-capable and flag-equipped, `trials=3`,
6 candidate moves per phase.

| arm | place | ci95 | LP | 1st | top4 | vs control (paired) |
|---|---|---|---|---|---|---|
| control | 3.437 | 0.266 | 13.11 | 33.0% | 65.7% | — |
| unit-choice search (46.3) | 3.283 | 0.254 | 14.74 | 34.7% | 69.3% | -0.153, t=-1.32 |
| **positional search** | **3.233** | 0.267 | **15.53** | **38.3%** | **70.7%** | **-0.203, t=-1.52** |

**47.4 predicted positional search would return "substantially more" than
unit-choice search's 0.15. It returned 0.20.** That is the same ballpark and
equally unresolved at n=300. The prediction failed and is recorded as failed.

The distribution moves more than the mean: firsts 33.0% → 38.3%, top-four
65.7% → 70.7%, LP +2.4. Both are consistent with a small real effect that
n=300 cannot separate from zero.

### 47.6 Why the number may be a budget rather than a ceiling

Diagnostics on the positional arm:

* it proposes a move on **73% of planning phases** -- it is not idle;
* a typical board has **~168 legal moves** (9 units x free hexes, plus swaps),
  and the arm samples **6**. That is **3.6% of the space**.

So -0.203 is what 3.6% coverage buys against a 5.78-unit best-to-worst spread
(47.2). Whether search is worth pursuing here is therefore not yet answered:
the honest question is whether the gain **scales with budget**. Running the
same arm at 24 candidates (~14% of the space).

Named before it finishes:

* **Gain scales roughly with coverage** (~0.4 at 4x candidates) → search is the
  path, and the next question is how deep it is worth going.
* **Gain saturates near 0.2** → the reachable part of the positioning space is
  small, most of the 5.78-unit spread is arrangements no sensible policy would
  pick from, and search yields a small fixed gain here regardless of budget.
* **Gain shrinks** → 6 candidates was overfitting the panel, and more search
  finds moves that beat one opponent while losing to the field.

The third outcome is live and the reason the panel is only one opponent: a move
tuned against a single board is exactly the sort of thing that looks better in
search than in play.

### 47.7 The gain saturates: 4x the budget buys nothing

Same arm at 24 candidates (~14% of the move space) against 6 (~3.6%):

| arm | place | LP | 1st | top4 | vs control (paired) |
|---|---|---|---|---|---|
| control | 3.437 | 13.11 | 33.0% | 65.7% | — |
| position@6 | 3.233 | 15.53 | 38.3% | 70.7% | -0.203, t=-1.52 |
| position@24 | 3.270 | 14.98 | 33.0% | 70.3% | -0.167, t=-1.26 |

Paired directly against each other on shared seeds: **+0.037, t=+0.29.**
Four times the search budget is worth nothing, and if anything is fractionally
worse. That is the second of the three outcomes named in 47.6.

Costs, from the timing ledger: the arm went from 8m to 21m for no gain.

**This is the important negative result of the search line.** 47.2 measured a
5.78-unit spread between the best and worst arrangement of a board, which is
large. 47.7 shows that sampling four times as much of that space does not
capture more of it. Two readings remain, and they differ in what to do next:

* the *reachable* part of the space is shallow -- a handful of samples already
  finds most of the available value, and the rest of the 5.78 spread consists
  of arrangements that are bad rather than good; or
* the search **overfits its panel** -- with one opponent, a move that wins the
  simulated fight need not win against the field, and more candidates simply
  finds more moves that are specific to that one board.

The second is testable directly by widening the panel rather than the candidate
set, and is running now at `panel=3, candidates=6`. If the panel is the binding
constraint, three opponents at six candidates should beat one opponent at
twenty-four, despite costing similar. If it also lands near 0.2, both readings
collapse into the same practical answer: **search is worth about 0.2 placement
here and no configuration of it is worth more.**

### 47.8 It was the panel, not the depth

> **WITHDRAWN by 47.9.** The panel comparison this section draws its
> conclusion from is not resolvable at n=300: `panel=3` against `panel=1` is
> -0.053 at t=-0.40. The reasoning below was built on a single arm.

| arm | place | LP | 1st | top4 | vs control (paired) | cost |
|---|---|---|---|---|---|---|
| control | 3.437 | 13.11 | 33.0% | 65.7% | — | 3m |
| position@6, panel 1 | 3.233 | 15.53 | 38.3% | 70.7% | -0.203, t=-1.52 | 8m |
| position@24, panel 1 | 3.270 | 14.98 | 33.0% | 70.3% | -0.167, t=-1.26 | 21m |
| **position@6, panel 3** | **3.180** | **16.07** | 37.0% | **71.7%** | **-0.257, t=-1.88** | 16m |

**Widening the panel helps where widening the candidate set did not**, at
similar cost. That settles 47.7's two readings in favour of the second: the
search was **overfitting its panel**, not exhausting a shallow space. A move
that wins one simulated fight need not win against the field, and searching
harder against a single opponent finds more moves that are specific to it.

This is the same shape as a lesson this project already has in a different
domain -- replication tests precision, not validity. Four times the candidates
is a more precise search of the *wrong objective*; three opponents is a less
precise search of a better one.

t=-1.88 is still short of significance at n=300, but it is the first search
configuration to approach it, and the trend across panel sizes is what the next
run tests. Running `panel=6` -- nearly the whole lobby.

Named before it lands:

* **The gain keeps rising with panel size** → the objective, not the search, was
  the constraint all along, and the right form of this is "beat the field"
  rather than "beat an opponent". That also has a cheap approximation worth
  trying next: score against the *average* of opponent boards rather than
  simulating each.
* **It flattens near 0.26** → three opponents already approximate the field, and
  search is worth ~0.25 placement here, full stop.

### 47.9 Correction: no configuration differs from any other

`panel=6` landed at -0.167 (t=-1.15), *worse* than `panel=3`'s -0.257, which
breaks the monotone story 47.8 told. Comparing every configuration against
every other, paired on shared seeds, n=300:

| | -0.053 | +0.037 | +0.037 |
|---|---|---|---|
| **p3 vs p1** | t=-0.40 | | |
| **p6 vs p1** | | t=+0.28 | |
| **c24 vs p1** | | | t=+0.29 |
| **p6 vs p3** | +0.090, t=+0.66 | | |
| **c24 vs p3** | +0.090, t=+0.72 | | |
| **c24 vs p6** | +0.000, t=+0.00 | | |

**Nothing distinguishes any configuration from any other.** Maximum |t| across
all six comparisons is 0.72.

47.8 claimed "widening the panel helps where widening the candidate set did
not" on the strength of one arm reading -0.257 against -0.203 and -0.167. That
difference was never resolvable, and the section is withdrawn. It is the exact
error this project has a lesson for -- *state t-statistics and n*, and *single
results are fine for reverting a default to neutral, not for asserting a new
claim* -- committed while writing about a different instance of the same
mistake.

> **SCOPED by [53.3](#533-why-search-helps-a-weak-teacher-and-harms-a-good-one).** This holds against a teacher with no
> positional heuristic (`expert_ab`'s control is `{}`). Against the current
> default teacher, which has `corner_carry`, the same search is **+0.303
> worse, t=+2.57**. The sign inverts.

### 47.10 What search is actually worth here

Pooling the four positional configurations per seed reduces policy noise
without touching seed noise, and gives the best available estimate of "search,
in general":

| | delta | t | n |
|---|---|---|---|
| pooled positional search (4 configs) | **-0.198** | -1.78 | 300 |
| unit-choice search | -0.153 | -1.32 | 300 |
| pooled across all five search variants | **-0.189** | -1.82 | 300 |

Five independent configurations -- two different decisions, candidate budgets
of 6 and 24, panels of 1, 3 and 6 -- all land between -0.15 and -0.26, and the
pooled estimate is **-0.19 at t=-1.82**. Consistency across configurations is
the real evidence here; no single arm resolves, but five arms agreeing on a
0.2-placement gain is not what nothing looks like.

**The conclusion for the search line: it works, it is worth about 0.2
placement, and no configuration tried is worth more.** Depth does not help,
panel size does not help, and the decision searched barely matters. That is a
complete answer to 45.7's proposal, and a negative one relative to the hope
that search would break the imitation ceiling open.

Set against the day: `copy_counts` alone was worth 1.053 at t=-4.55. Search
across five configurations is worth 0.19 at t=-1.82. The engine's 5.78-unit
positional spread (47.2) is real but mostly unreachable -- a policy that plays
sensibly is already near the top of the reachable part.

---

## 48. PPO degrades a strong warm start; self-play was silently broken (08-04)

**Question.** Every PPO attempt in this project has started from a weak clone
(~4.6) on an engine with three wrong rules, so "PPO degrades its warm start"
was always confounded with "the warm start was weak". The clone is now at
3.537. Does PPO improve it, hold it, or degrade it?

Outcomes were named before the runs finished, per the standing rule:
degradation (the historical result), flat within noise (a local optimum PPO
cannot leave at this budget), or improvement (the first time anything here has
exceeded imitation).

### 48.1 `--init-from`: pay for the clone once

Cloning costs ~39 minutes and is deterministic, yet every PPO arm re-derived
its own. That is not merely wasteful: two arms meant to be compared were each
starting from a *separately produced* warm start, so any drift between those
clones confounded the comparison they existed for.

`--init-from` loads weights into the model already bound to this run's env and
hyperparameters, via `set_parameters` rather than `MaskablePPO.load` -- `load`
would carry the saved run's hyperparameters across and silently override the
ones the arm is testing.

It is guarded. `check_init_flags` compares the four architecture-affecting
flags against the checkpoint's sidecar and exits naming the mismatch, because
the alternative is a tensor-shape error deep inside torch. Three scripts in
this project have reconstructed an env from module defaults rather than from
the checkpoint they were loading (45.2), so this is a known failure mode, not a
hypothetical one. The guard is parametrised per flag and mutation-tested:
truncated to check only the first flag, 3 of 4 cases fail.

### 48.2 PPO degrades it, from both opponent regimes

Two arms, 60k steps, branched off the same frozen checkpoint. 300 shared seeds,
paired:

| run | placement | 1st | top4 | vs warm start | t |
|---|---|---|---|---|---|
| `reclone-rowhead` (warm start) | **3.537** | 32.0% | 64.7% | -- | -- |
| `ppo-from-clone` (control) | 4.613 | 19.3% | 46.7% | **+1.077** | **+6.27** |
| `ppo-from-clone-sp` (self-play) | 4.297 | 20.7% | 53.7% | **+0.760** | **+4.69** |

Every column moves together -- this is not a mean concealing a mixed
distribution. First-place rate falls by a third.

**The outcome is degradation, and it is now unconfounded.** PPO does not merely
fail to exceed the teacher from a strong start; it actively walks away from a
policy already at teacher parity. For scale: `copy_counts`, the most productive
change in this project, was worth 1.053 (40.1). One PPO run gives back 1.077.

### 48.3 Self-play delays degradation but does not prevent it

| steps | control | self-play |
|---|---|---|
| start | 3.517 | 3.517 |
| 30k | 4.633 | **3.667** |
| 60k | 4.317 | 4.517 |

At 30k self-play has held essentially all of the warm start while the control
has already lost a full placement. By 60k both have converged.

Paired at n=300, **self-play vs control is -0.317 at t=-1.76** -- it degrades
less, consistently, but does not separate. This is weaker than 22.3's
"self-play is the only arm that holds level", and the 30k reading is a single
60-episode point that should not be quoted as a result on its own.

### 48.4 Self-play had been unrunnable since `copy_counts` landed

The first self-play arm died five minutes in:

    ValueError: Unexpected observation shape (381,) ... please use (418,)

`snapshot_factory` built opponent seats by hand-listing encoder options --
`champion_encoding` and `scouting`. `copy_counts` was added to the encoder
(38.9) and never added here, so snapshot seats encoded 381 floats for a policy
expecting 418. Its docstring claimed *"Every setting the snapshot needs is read
off `env`, so a snapshot seat always shares the learner's observation and action
layout"* -- a promise a hand-enumeration structurally cannot keep.

**Every self-play run has been impossible since `copy_counts` landed, and
nothing said so.** 22.3's finding predates `copy_counts` and is not invalidated;
what it means is that the claim has never been re-tested on a strong warm start,
because any attempt would have crashed. 48.3 is the first such test.

Fixed structurally rather than by adding one more name to the list:
`ObservationEncoder.layout_settings()` returns the whole layout, the factory
splats it, and a size mismatch now raises at construction instead of surfacing
inside torch. The guard is a test that **introspects
`ObservationEncoder.__init__`** and asserts `LAYOUT_OPTIONS` covers every
defaulted keyword, so a future option cannot be silently omitted.
Mutation-tested: reverting the factory to hand-enumeration fails.

*Lesson.* A comment or docstring asserting "this stays in sync" is not a
mechanism. Where one object must mirror another's configuration, copy the
configuration wholesale and assert the result matches; an enumeration at the
call site is a list that will be out of date the next time someone extends the
thing being enumerated.

### 48.5 Where the measurement time actually goes

Profiled, since the timing ledger (46.4) had made the costs visible and none of
them had ever been attributed:

- `env.step` is **99.7%** of wall clock; `CombatSimulator.run` is **97.8%** of
  that. Everything is combat ticks.
- **Observation encoding is not a target**: encoder, action mask and policy
  together are **0.3%**.
- **Torch is not a target for evaluation**: the forward pass is **1.2%**, and
  identical at 1 vs 6 threads. The oversubscription hazard does not touch eval.
- **The BC epoch loop is not a target**: `fit_clone` extrapolates to **~1
  minute** of `bc_clone`'s 39. Nearly all of it is *serial episode collection*.

Three of those four are suspects this project would plausibly have optimised on
intuition. All three measured as noise.

Landed, each verified rather than assumed:

| change | effect | verification |
|---|---|---|
| `_select_target` checks the sticky target before building the candidate list | -19% | bit-identical over **30 full games** -- placements, exact float reward `repr`, step counts, round ids, HP, gold |
| parallel expert collection (`rl/collect.py`) | **4.78x** | byte-identical on all four arrays |
| parallel model evaluation (`evaluate_model_parallel`) | ~17x on `compare_models` | equivalence test against serial, per seed |

The reorder cannot change the answer: a `current` that is alive and targetable
is necessarily a member of `targetable_enemies_of(unit)`, so the `not enemies`
early return is unreachable in exactly the case it skips ahead of.

`compare_models` fell from a 68-minute median for two arms to **6 minutes for
three** -- 6.8s to 0.4s per episode, consistent with 10 workers times the
1.577x engine gain compounding.

*A null worth keeping.* Memoising `effects.hooks_for` looked significant by
call count (2.52M calls) and measured **zero**. The list it replaces is over
0-2 elements, so the dict lookup costs the same. Profiler call counts are not
costs.

*A mutation-testing note.* The parallel-collection equivalence test **passed**
under a completion-order mutation -- with 4 episodes on 3 workers they happened
to finish in order. Only the separate seed-reversal test caught it
deterministically. Order correctness needed its own test; the equivalence test
was not sufficient, and would have read as though it were.

### 48.6 A test that had never asserted anything

`test_potential_falls_when_the_board_is_emptied` drove the env by taking the
lowest legal action, which never fielded a unit -- so it skipped on every run
since it was written, and the one claim it exists to pin (losing board strength
is penalised) was unchecked. Now driven by the scripted policy, and an empty
board is a failure rather than a skip. Mutation-tested against a `_potential`
that ignores the board.

This is the third instance of the pattern in this project (the two silent
fixture skips noted under *Testing*). **A skip is not a pass.** The suite now
reports 0 skipped, which is the only state in which that number carries
information.

### 48.7 What this changes, and what is still open

The imitation ceiling is now a *measured* ceiling rather than a suspected one.
Imitation cannot exceed its teacher by construction; search is worth 0.19
(47.10); and PPO from the best clone this project has produced is worth
**-1.077**. Three routes past the teacher, all measured, none positive.

Still open:

- **PPO hyperparameters from a strong start are one sample.** Both arms used
  the same learning rate, entropy coefficient and 60k budget. The result is
  robust to the opponent regime, which is one axis; it is not robust to
  anything else, because nothing else was varied.
- Whether the degradation is the critic. `explained_variance` was 0.968 on
  expert data at the end of cloning; it was not measured after PPO.
- Self-play's 30k reading. If PPO degrades monotonically and self-play delays
  it, a shorter budget might keep more of the warm start -- but "stop before it
  gets worse" is not learning, and should not be dressed as a result.
- The engine gaps from 36 and 47.4, unchanged: multi-target abilities pick
  victims by list order rather than position; no Radiant/Artifact/Support item
  classes; no carousel after stage 4; no shop lock.

---

## 49. Imitation is not exhausted: the clone is 0.507 behind its teacher (08-04)

**Question.** 48.7 concluded that three routes past the teacher are all
measured and none is positive. That framing assumes the clone has *reached* its
teacher. It had never been checked on shared seeds in the current regime -- and
two different teacher numbers were in circulation: 3.030 in this document, and
3.437 hardcoded in `compare_models`' output footer. They cannot both be right,
and the whole "imitation is exhausted" conclusion depends on which is.

This is precisely the failure the *re-derive numbers before citing them* lesson
exists for, and it is the third instance (after the 90.7% ceiling and the
`--target-kl` default).

### 49.1 The teacher is 3.030, and imitation has 0.507 left

`scripts/teacher_gap.py` evaluates the teacher and the models on the **same
seeds in the same run**, with the teacher's flags read from the checkpoint's
sidecar rather than assumed. n=300:

| arm | placement | 1st | top4 | vs teacher | t |
|---|---|---|---|---|---|
| **TEACHER (scripted)** | **3.030** | 37.0% | 72.3% | -- | -- |
| `reclone-rowhead` (best clone) | 3.537 | 32.0% | 64.7% | **+0.507** | **+3.31** |
| `ppo-from-clone` | 4.613 | 19.3% | 46.7% | +1.583 | +9.53 |
| `ppo-from-clone-sp` | 4.297 | 20.7% | 53.7% | +1.267 | +7.60 |

Doc 99's 3.030 was right; the footer's 3.437 was wrong. The constant has been
**deleted rather than corrected** -- a hardcoded reference printed beside a
fresh measurement reads as though it were measured with it, which is how it
survived. `compare_models` now points at `teacher_gap.py` instead.

**The clone is 0.507 behind its own teacher at t=+3.31, n=300.** That is
significant, and it is 2.6x everything the entire search line was worth (0.19,
t=-1.82, 47.10).

**This revises 48.7.** Imitation is *not* exhausted. The best clone has never
reached the policy it is copying, and closing that gap is worth more than
either alternative route measured so far. 48.7's "three routes, none positive"
stands for the three it names; what it missed is that the first route was never
run to completion.

### 49.2 The critic did not collapse -- so that is not the mechanism

48.7 listed the critic as the open question behind PPO's degradation. Measured
on 13,728 held-out expert transitions:

| model | explained variance | predicted mean | actual mean |
|---|---|---|---|
| `reclone-rowhead` | 0.262 | 0.647 | 0.654 |
| `ppo-from-clone` | 0.249 | 0.541 | 0.654 |
| `ppo-from-clone-sp` | **0.401** | 0.458 | 0.654 |

PPO leaves explained variance essentially where it found it (0.262 -> 0.249),
and self-play's critic is *better* than the clone's. **Critic collapse is
refuted as the mechanism for the 1.077 degradation**; the damage is in the
policy objective. Predicted values do drift low (0.541 and 0.458 against an
actual 0.654), so the critic becomes biased without becoming less informative.

### 49.3 The critic was never as good as reported

The number this project has cited -- **0.968** explained variance after cloning
-- is computed on `obs_t` and `return_t`, the very tensors the fit just
minimised against. It is an in-sample figure. On held-out states from the same
teacher the same critic scores **0.262**.

That figure appears in doc 99 entry 18, in `--value-coef`'s help text, and in
`behaviour_clone`'s docstring, in every case as evidence that the
value-regression warm start worked. What it actually shows is that the
optimiser converged. PPO consumes the critic on states it has never seen, which
is the regime the 0.262 describes.

Nothing about 18's conclusion is overturned -- the fix was measured against
`explained_variance` of **-0.43**, and moving off that was real. What is
overturned is the *size*: the critic is adequate, not excellent.

`fit_clone` now reports both figures, and says so explicitly when no holdout is
supplied. The holdout is collected from the same teacher on seeds disjoint from
the training range (510,000+ against 10,000+), which is affordable only because
collection is now parallel (48.5). Mutation-tested: scoring the holdout on the
training tensors fails the test.

*Lesson.* **A diagnostic computed on training data is a statement about the
optimiser, not about the model.** This project already had the converse lesson
-- *a probe that cannot fit its own training set is a statement about the
feature set* (30) -- and never wrote down the other half. Any fit quality
quoted as evidence of a model's usefulness needs a holdout, or an explicit
label saying it has none.

### 49.4 What this changes

The next move is no longer a pivot. **Close the 0.507.** It is the largest
measured, unclaimed gap available, it is a supervised problem rather than an RL
one, and every tool for attacking it already exists.

Still open:

- Why the gap persists. 45.6 raised action match from 76.8% to 81.9% and moved
  placement only t=-1.43, so agreement and placement have decoupled before (a
  finding recorded five times). The gap may be concentrated in a few decisive
  action kinds rather than spread evenly -- unmeasured.
- Whether DAgger closes it. It targets exactly this failure (compounding
  off-policy drift) and has never been run against the current teacher, the
  slot head, or `copy_counts`. Its parallel path is not implemented (48.5).
- The value-scale drift in 49.2 is unexplained.
- `copy_counts` and the teacher flags are still not defaults, so every fresh
  run reproduces an older, weaker configuration unless flagged. Deferred to the
  user since 40.

---

## 50. The gap is context-dependent, not diffuse: necessity and sufficiency disagree (08-04)

**Question.** 49.1 put the best clone 0.507 behind its teacher. 49.4 said to
close it. This asks *which decisions* it lives in -- and deliberately measures
that by **placement, not agreement**, because raising action match has failed to
move placement five separate times (45.6 most recently: 76.8% -> 81.9% for
t=-1.43).

`scripts/gap_attribution.py` hands the teacher authority over one kind of
decision at a time and measures what comes back. Two controls bound it:
delegating nothing must reproduce the clone, delegating everything must
reproduce the teacher. Both landed **exactly** -- 3.537 and 3.030, gap +0.507
at t=-3.31, independently reproducing 49.1 -- so the middle rows are readable.

SELECT and PLACE are delegated together: a PLACE names a destination for the
unit a SELECT picked up, and splitting them would have the teacher placing a
unit the clone chose, which is neither policy.

### 50.1 Sufficiency: no single kind recovers anything

Teacher takes kind X, clone keeps the rest. n=300:

| delegated | placement | recovered | t |
|---|---|---|---|
| none (= clone) | 3.537 | -- | -- |
| BUY | 3.630 | **-0.093** | +0.63 |
| SELL | 3.437 | +0.100 | -0.73 |
| MOVE | 3.493 | +0.043 | -0.30 |
| EQUIP | 3.560 | -0.023 | +0.27 |
| ECON | 3.513 | +0.023 | -0.27 |
| PICK | 3.383 | +0.153 | -1.21 |
| all (= teacher) | 3.030 | +0.507 | -3.31 |

Max |t| across the six is **1.21**. Individual recoveries sum to 0.203 -- 40% of
a gap that full delegation recovers entirely. On this table alone the honest
reading is "no single kind carries the gap".

*A prediction recorded and refuted.* Before the run I expected BUY and MOVE to
recover most, on the grounds that BUY is the kind the agent reads worst from
the observation (48% against a 91.8% ceiling, 29). BUY came back **negative**
and MOVE recovered 9%.

*A story fitted and withdrawn.* On seeing BUY negative mid-run I proposed that
the teacher buys units the clone will not follow through on -- interference
rather than incompetence. At t=+0.63 that is noise, and constructing a
mechanism for it was exactly the error *name the possible outcomes before the
run finishes* exists to prevent. Withdrawn, and recorded rather than deleted.

### 50.2 Necessity: three kinds are significant

The inverse. Teacher takes everything **except** X; the clone keeps X. Measured
against the teacher, so the quantity is the cost of withholding one kind:

| kind withheld | placement | cost vs teacher | t |
|---|---|---|---|
| **PICK (augment+offering)** | 3.400 | **+0.370** | **+3.21** |
| **MOVE (SELECT+PLACE)** | 3.360 | **+0.330** | **+2.46** |
| **SELL** | 3.307 | **+0.277** | **+2.41** |
| ECON | 3.150 | +0.120 | +1.41 |
| BUY | 3.193 | +0.163 | +1.23 |
| EQUIP | 2.957 | -0.073 | -0.99 |

*Predicted before the run:* if the gap were diffuse, every arm lands near 3.030
and none stands out. **Refuted.** Three stand out where the forward direction
resolved nothing.

### 50.3 The finding: a decision's value depends on the policy around it

The two directions disagree, and the disagreement is the result.

SELL delegated *into* a clone buys 0.100 (t=-0.73, nothing). SELL withheld
*from* a teacher costs 0.277 (t=+2.41, real). Same decision, same two policies.
The only difference is what surrounds it.

**A better decision only pays off if the rest of the policy can exploit it.**
The teacher's sell is worth having when the surrounding play sells into a
coherent economy and re-buys; dropped into a policy that will not follow
through, it buys nothing measurable. Symmetrically, the clone's weakness in a
kind is only visible when everything else is competent enough for it to matter.

This is the mechanism behind the decoupling recorded five times (22, 34.13,
38.7, 44.3, 45.6): **per-kind imitation improvements have always been measured
in the regime where they cannot pay off** -- inside an otherwise-unchanged
clone. That is not evidence they are worthless. It is evidence the measurement
was taken in the wrong place.

The 0.507 is therefore **not diffuse** (the 50.1-only reading, which was stated
here mid-run and is superseded) and **not localised** to one kind either. It is
concentrated in PICK, MOVE and SELL, but only expressible against a competent
surrounding policy.

*Note on the sums.* Necessity costs total 1.187 against a 0.507 gap; sufficiency
recoveries total 0.203. Neither should sum to the gap -- overlapping authority
double-counts, and that overlap is precisely the interaction being measured.

### 50.4 EQUIP: the clone is already at parity

Withholding EQUIP from the teacher costs **-0.073 (t=-0.99)** -- the clone's
equipping is, if anything, slightly better, and certainly not worse.

This matches 41.2 from the other side: EQUIP was the one slot-typed decision
that got *better* when the slot head lost its global context (58.7% -> 83.4%),
because it is the one decision that genuinely depends on nothing outside the
slot. Two unrelated experiments now agree that EQUIP is solved. **Stop spending
observation width or architecture on it.**

### 50.5 What this changes

49.4 said "close the 0.507" and treated DAgger as the obvious instrument. That
is now more specific and partly redirected:

- **Target PICK, MOVE and SELL.** Together they carry the resolvable part.
  PICK is the largest single term and has never been examined in this project
  at all -- augment and offering choice has no dedicated features, no probe, and
  no entry.
- **Stop measuring per-kind changes inside an otherwise-unchanged clone.** That
  regime is now known to understate them. Any future per-kind imitation work
  should be evaluated with the *rest* of the policy held competent, which the
  complement harness now supports directly.
- **EQUIP is done** (50.4).
- BUY is the surprise: worst-imitated (29), and neither sufficient (-0.093) nor
  significantly necessary (+0.163, t=+1.23). The 48%-against-91.8% agreement
  deficit that motivated three separate observation changes may simply not be
  worth much placement. Not resolved -- t=+1.23 is not a null -- but the burden
  has shifted.

Still open:

- Whether targeting PICK/MOVE/SELL actually closes the gap, or whether the
  interaction means only the full combination does. 50.3 predicts partial
  recovery at best from any single-kind fix.
- Why PICK matters so much. Augments are the least-verified part of the dataset
  (17.1: `augments.json` is generic archetypes, not the real Set 17 pool), so
  this may be measuring a defect in the data rather than a real skill.
- DAgger remains unrun against the current teacher, slot head and
  `copy_counts`, with no parallel collection path (48.5).

---

## 51. Augment choice is worth nothing; the PICK gap is a carousel gap (08-04)

**Question.** 50.2 made PICK the largest single term in the clone's 0.507 gap
(+0.370 withheld from the teacher, t=+3.21). Inspecting the teacher then showed
it has **no augment policy at all** -- 9 of 9 augments taken at option index 0,
its action space's first legal choice. So the 0.370 might be a real decision the
clone fails, or the clone failing to copy an arbitrary constant.

`scripts/pick_probe.py` runs everything except PICK as the teacher -- the
sensitive regime per 50.3 -- and varies only how PICK is made.

### 51.1 A measurement that was not reproducible

The first run said index 0 beat random picking by **0.463, t=+2.85**, refuting
the "arbitrary default" reading. It also contradicted the code: augment offers
come from `rng.sample` and `PICK_AUGMENT` indexes the *offer position*, so
"always index 0" and "uniform among the offered" are the same distribution and
the difference should have been zero.

The code was right. A second run of the **identical** arm returned 3.257 against
the first run's 3.493 -- a 0.236 swing, larger than most effects this project
measures. The probe seeded one `random.Random` **per worker process**, and
`imap_unordered` hands episodes to whichever worker is free, so which episode
drew which option changed between runs. The arm was not reproducible and its
paired t was invalid: the arms differed by an uncontrolled draw as well as by
policy.

Fixed by reseeding from the **episode seed** inside `_episode`, so any
`(mode, seed)` reproduces regardless of scheduling. Regression test pins both
the contract and the reseed; mutation-tested by deleting the reseed line.

*Lesson.* **A randomised arm must be seeded per episode, not per worker.** Any
pool that dispatches by availability makes per-process state a function of
scheduling, and scheduling is not an experimental variable. More generally: this
was caught only because a *second* configuration happened to re-measure the same
arm. A single run would have shipped it with a t-statistic attached. Where an
arm is stochastic, re-run it before believing it -- the project rule about
replication testing precision rather than validity does not apply when the
question is whether the arm is stable at all.

### 51.2 Augment choice is worth nothing

Re-measured with deterministic arms, n=300:

| PICK made by | placement | vs teacher | t |
|---|---|---|---|
| teacher (index 0) | 3.030 | -- | -- |
| **random augment only** | **3.037** | **+0.007** | **+0.06** |
| random offering only | 3.203 | +0.173 | +1.22 |
| random both | 3.223 | +0.193 | +1.31 |
| clone | 3.400 | +0.370 | +3.21 |
| last option | 3.443 | +0.413 | +2.54 |

**Choosing augments at random costs +0.007 placement (t=+0.06).** The augments
in this dataset are interchangeable. That is consistent with 17.1: `augments.json`
is a set of generic archetypes rather than the real Set 17 pool, and generic
archetypes are exactly what an indifference result looks like.

So the PICK term is **an offering term** -- the carousel draft -- and augment
choice contributes nothing to it.

### 51.3 The decomposition does not resolve

The total is significant; its halves are not. Offering-order value is +0.173
(t=+1.22) and the clone being worse than random picking is +0.177 (t=+1.11).
Two roughly equal parts summing to a real 0.370, neither individually resolved
at n=300.

What can be said: the 0.370 is real, augments are not in it, and the clone is
*at best* level with random picking on the part that remains. What cannot yet be
said is whether the clone's deficit is mostly failing to draft well or mostly
failing to draft at all.

`last` is worse than `random` (+0.220, t=+1.39) and clearly worse than the
teacher (+0.413, t=+2.54), which is weak evidence that earlier offerings are
better -- unexplained, since `_generate_offerings` draws sequentially from the
shared pool with no strength ordering.

### 51.4 10% of the observation encodes a decision worth nothing

The observation spends **56 of 418 floats (13.4%) on augments**: a 14-wide
multi-hot of held augments plus 3 x 14 one-hots for the offered choices. The 42
floats encoding the *choice* describe a decision measured at t=+0.06.

Held augments still have real effects, so the 14-wide held block may carry
value. The 42 offered-choice floats are a live removal candidate -- 10% of the
observation, on a null. This project's standing finding is that width without a
relational payload does not help (29, and the `features` encoding rejected three
times), and this is width with a *measured* payload of zero.

Not done here: removing it orphans every existing checkpoint, and it should be
measured as its own arm rather than bundled.

### 51.5 What this changes

- **Stop treating PICK as an augment problem.** It is a carousel problem.
- **Do not build augment features.** The decision they would serve is worth
  0.007 placement in this engine. If augments are to matter, the fix is the
  *dataset* (17.1), not the observation or the policy.
- The carousel is the live question, and it is nearly unexamined: no probe, no
  features beyond the offering block, and `_generate_offerings`' ordering effect
  in 51.3 is not understood.
- 50.5's "target PICK, MOVE and SELL" narrows to **MOVE, SELL and the
  carousel**.

Still open:

- Why earlier offerings appear better (51.3).
- Whether the clone's PICK deficit is drafting badly or ignoring drafting;
  n=300 does not separate them.
- The 42 dead observation floats (51.4).
- MOVE (+0.330, t=+2.46) and SELL (+0.277, t=+2.41) from 50.2 are untouched and
  are now the two best-attested targets.

---

## 52. What SELL and MOVE are worth, and the teacher's blind spot (08-04)

**Question.** 50.2 made MOVE (+0.330, t=+2.46) and SELL (+0.277, t=+2.41) the
two best-attested terms in the clone's gap. A gap is uninterpretable without
what the decision is worth, so this measures the denominator for each --
`scripts/pick_probe.py --kind`, generalised from 51's PICK probe.

### 52.1 `random` is not a floor for these decisions

First attempt used the same arms as 51: random and last-option.

| kind | random | last |
|---|---|---|
| SELL | 5.760 (t=+16.86) | 3.687 |
| MOVE | **7.977** (ci95 0.017) | **8.000** (ci95 0.000) |

*Predicted:* random MOVE would be **less** destructive than random SELL, since
a random legal layout still fields the same units. **Refuted, badly** -- MOVE
bottoms out at last place in all 300 games.

The design does not transfer. For PICK, random is a genuine alternative policy:
something must be picked, so picking randomly is a real strategy. For SELL and
MOVE, random is not unskilled but *destructive* -- it sells the carry and
unfields the board. Dividing the clone's gap by that spread would give a
tidy-looking "6.7% of achievable" whose denominator measures self-sabotage.
That is a floor effect, and 18.5 already says a floor leaves no variance to
compare against.

Replaced with **`forbidden`**: the teacher plays on with the decision masked
out entirely. The decision *not taken*, rather than taken badly.

### 52.2 Selling is worth 1.893; the clone captures 85%

| SELL made by | placement | vs teacher | t |
|---|---|---|---|
| teacher | 3.030 | -- | -- |
| clone | 3.307 | +0.277 | +2.41 |
| **forbidden** | **4.923** | +1.893 | +12.85 |
| random | 5.760 | +2.730 | +16.86 |

**The `forbidden` arm is independently corroborated.** 37.4 measured a teacher
that could not sell at **5.017**, by an unrelated route on a different
configuration. This arm gets **4.923**. Two independent measurements of "a
teacher that cannot sell" agreeing to 0.09 is the strongest validation any
probe in this project has had.

So selling is worth 1.893 placement, and the clone's deficit of 0.277 means it
**already captures 85.4%** of it. The remaining headroom is real but small.

### 52.3 MOVE is not positioning: SELECT+PLACE is the only way to field a unit

`forbidden` for MOVE returns **8.000 with ci95 0.000** -- last place in all 300
games. Not a tuning problem: `SELECT`+`PLACE` is the sole route from bench to
board, so denying it leaves an empty board for the whole game.

50's "MOVE" group therefore conflates two different things -- **fielding**
(which units reach the board at all) and **positioning** (where they stand).
The denominator is structurally degenerate, and no share of it is meaningful.

### 52.4 The teacher never repositions

Isolating positioning: forbid `SELECT` of a *board* slot, keeping bench->board
fielding. A fielded unit can then never move again.

The result was **identical to the teacher, +0.000, t=0.00** -- the mask never
binds. Verified directly rather than inferred from a null: over 8 games the
teacher issued **173 bench selections and 0 board selections**.

**The teacher has no repositioning behaviour at all.** It chooses a hex once,
via `_preferred_hex`, when a unit is fielded, and never revisits it.

Two consequences:

- **The clone's +0.330 MOVE gap is a *fielding* gap**, not a positioning one.
  It is about which units reach the board and where they first land.
- **Repositioning is worth something and the teacher takes none of it.** 47.2
  measured a 5.78-unit spread between the best and worst arrangement of a fixed
  board, and 47.10 found one-ply positional search worth ~0.19 (t=-1.82) -- a
  gain available *precisely because* the incumbent never repositions. That now
  reads less like a weak search result and more like a floor on an entirely
  unexploited axis.

### 52.5 What this changes

Per-decision accounting for the 0.507, with valid denominators where they exist:

| decision | worth | clone's deficit | captured |
|---|---|---|---|
| SELL | 1.893 | 0.277 | 85.4% |
| PICK (augment) | ~0.007 | -- | n/a, worth nothing (51.2) |
| PICK (offering) | unresolved | ~0.177 | unresolved |
| MOVE | degenerate (52.3) | 0.330 | fielding, not positioning |
| EQUIP | -- | -0.073 | at parity (50.4) |

**The clone is not badly wrong anywhere.** On the one decision with a clean
denominator it captures 85%. The 0.507 is spread across decisions the clone
mostly performs, which is consistent with 50.3's finding that the gap is
interactional rather than localised.

That shifts the recommendation. Chasing the last 15% of selling, or the
fielding residual, is grinding against a policy already close on each part.
**The larger prize is the teacher's own blind spot:** it never repositions,
which forfeits an axis worth at least 0.19 by direct measurement and plausibly
more, since 47's search was one-ply with a 6-24 candidate budget against a
5.78-unit spread. Raising the teacher raises the ceiling for everything cloned
from it -- and unlike the imitation residual, nobody has taken it.

Still open:

- Whether a repositioning teacher clones. 44.3 is the warning: the better
  teacher's gain did not reach the clone. A positional gain may be worse in
  this respect, since 45.5 showed PLACE is the kind most sensitive to what the
  head can express.
- PICK's offering half (51.3), still unresolved at n=300.
- The fielding-vs-positioning split inside MOVE has no clean probe yet; 52.4
  isolates repositioning only because the teacher does none.

---

## 53. Defaults flipped; search helps a weak teacher and harms a good one (08-04)

### 53.1 The measured-better configuration is now the default

Until today a run with no flags reproduced a configuration measured roughly 1.5
placement worse than the best known one: no `copy_counts` (t=-4.55, 40.1), a
teacher that could not sell (worth 1.893, 52.2), and no teacher flags (-0.407,
t=-2.82, 43). Each is a *measured* improvement, and leaving them opt-in meant
the honest default was the weak one.

`--copy-counts`, `--expert-sell` and `--expert-flags` now default on, with
`--no-...` forms for any comparison that needs the old behaviour. `--slot-head`
is deliberately **not** flipped: it is 45.6's t=-1.43, which does not resolve.

### 53.2 A repositioning teacher is worse, not better

52.4 found the teacher issues zero board-slot SELECTs -- it never moves a
fielded unit -- and 52.5 recommended raising the teacher on that axis, calling
it the one prize nobody had taken. `--expert-reposition` wraps the teacher in
47's one-ply positional search and threads it through parallel collection
(verified: 16 board-slot SELECTs per 4 games against the plain teacher's 0).

*Predicted:* ~2.85, from 47.10's pooled -0.189. **Refuted, and significantly:**

| | placement | 1st | top4 |
|---|---|---|---|
| teacher | **3.030** | 37.0% | 72.3% |
| teacher + repositioning search | 3.333 | 35.3% | 69.0% |

**+0.303, t=+2.57, n=300.** The opposite sign to 47.10, and significant where
47.10 was not.

### 53.3 Why: search helps a weak teacher and harms a good one

`scripts/expert_ab.py`'s control arm is `{}` -- **no teacher flags at all**. So
47 measured search against a teacher without `buy_synergy`, `match_items` or
`corner_carry`, the last of which is itself a positioning heuristic. Its arms
were internally consistent, so its comparison was valid; what was invalid was
carrying the conclusion forward to a teacher that had since gained a positional
rule.

Measured directly, n=300, same search configuration throughout:

| teacher | no search | + search | delta | t |
|---|---|---|---|---|
| sell-only | 3.437 | 3.170 | **-0.267** | **-2.13** |
| full minus `corner_carry` | 3.237 | 3.173 | -0.063 | -0.48 |
| full (all flags) | **3.030** | 3.333 | **+0.303** | **+2.57** |

Monotone: the better the teacher, the less search is worth, until it is
actively harmful. Note also that the three *searched* arms land within 0.16 of
each other (3.170 / 3.173 / 3.333) -- **search overwrites whatever positioning
the teacher had**, washing out the flags' contribution rather than adding to it.

The mechanism is the same one 48 found for PPO: a noisy improvement operator
applied to a policy that is already good moves it off its solution. Search
accepts a move when one ply of simulation beats the incumbent by `margin=0.5`,
estimated from `trials=3` fights against `panel_size=1`. Against a poor
arrangement that is a real signal; against `corner_carry`'s arrangement most
accepted moves are noise.

*Incidental confirmation.* `sell-only` measures **3.437** -- precisely the stale
constant 49.1 deleted from `compare_models`' footer. That number was the
sell-only teacher, exactly as diagnosed.

### 53.4 What this changes

**52.5's recommendation is withdrawn.** Raising the teacher by repositioning
does not work with the instrument available; the teacher's blind spot is real
(52.4) but one-ply search is not the way to fill it.

47's conclusion is **scoped, not withdrawn**: "one-ply positional search is
worth ~0.19" holds against a teacher with no positional heuristic, and is false
against the current default teacher.

*Lesson.* **An improvement measured against one baseline does not transfer to a
better one, and can invert.** This is the eighth-plus baseline invalidation
here, but the first where the *sign* flipped rather than the magnitude. The
standing rule -- re-measure both arms together -- is necessary but not
sufficient: 47 did re-measure both arms together, and was still wrong to
generalise, because the arms shared a baseline that later stopped being the
default. Record what a result was measured *against*, not just what it measured.

Still open:

- **`trials` is the untested axis.** 47 swept panel size and candidate budget
  and found nothing distinguishing; neither sweep touched the number of
  simulations per candidate, which is precisely the term controlling the noise
  this diagnosis blames. If search harms a good teacher because its value
  estimate is noisy, more trials should reduce the harm -- and that is a direct
  test of the mechanism rather than another configuration.
- The teacher's positional blind spot itself (52.4) is unaddressed. A cheap
  deterministic heuristic in the shape of `corner_carry` may be the right
  instrument, given a noisy search is not.

---

## 54. Two RNG defects in the search path; 53's finding survives (08-04)

### 54.1 The search stream was seeded per worker, not per episode

`search_policy` builds one `random.Random(rng_seed)` per policy, and
`evaluate_scripted_parallel` builds one policy per **worker**. With
`imap_unordered` the episodes a worker receives -- and their order -- vary run
to run, so the search's draws did too. Two runs of an identical configuration
returned **3.333 and 3.257**.

This is the **same defect as 51.1**, in a different file. When 51.1 was fixed it
was treated as a local mistake in `pick_probe` rather than a pattern worth
grepping for; it was already present in the older and far more heavily cited
path, so **every search number in 46, 47 and 53 carried it**.

Fixed by exposing the stream as `act.rng` and reseeding it per episode in
`_parallel_episode`. Tests pin both sides of the contract.

*Lesson.* **A defect found in one place is a hypothesis about every place.** The
first instance was caught, fixed, tested and written up without ever asking
whether the pattern recurred. One `grep` for `random.Random(` beside a worker
pool would have found the second instance an hour earlier.

### 54.2 Seeding from the episode seed leaked the future

The obvious fix -- `rng.seed(seed)` -- made the measurement reproducible and
flipped the result from +0.303 to **-0.087**, i.e. search suddenly *helped*.

A sign flip caused by a reseed is not a benign event, and the cause was
immediate on inspection: `TFTEnv.reset(seed=s)` constructs `Match(seed=s)`,
whose `self.rng = random.Random(s)` draws every combat seed in the game. Seeding
the search with the same `s` hands it **the identical sequence** -- it was
scoring candidate boards using the very combat seeds the real fight was about
to use. Clairvoyant, not better.

Fixed with a large prime offset (`SEARCH_SEED_OFFSET = 1_000_003`), giving a
stream that is independent of the match's but still reproducible per episode.

*Lesson.* **An evaluator seeded from the same value as the thing it evaluates is
not independent of it.** Determinism and independence are separate properties,
and the natural fix for the first silently destroyed the second. Any harness
that reseeds from an episode seed must offset away from whatever else that seed
drives.

### 54.3 The trials axis is a null; the mechanism is unknown

53.3 blamed search's harm on a noisy value estimate -- `trials=3` fights per
candidate. Quadrupling it:

| arm | placement | vs no search | t |
|---|---|---|---|
| no search | 3.030 | -- | -- |
| search, trials=3 | 3.257 | +0.227 | +1.92 |
| search, trials=12 | 3.250 | +0.220 | +1.65 |

**trials=12 vs trials=3: -0.007, t=-0.05.** Four times the simulation budget
changes nothing. **The noise diagnosis is refuted.**

The replacement I reached for -- that search overfits the single sampled
opponent rather than the field -- is *also* unsupported: it predicts panel size
should matter, and 47 swept panels of 1, 3 and 6 and found them
indistinguishable. So the honest position is that **search harms a good teacher
for reasons not identified**, with two candidate mechanisms and evidence against
both. Recorded as open rather than swapped for a third story.

### 54.4 53.2 restated, on a stable footing

Re-measured with an independent, per-episode-reproducible stream, running the
search arm twice to demonstrate determinism rather than assert it:

| arm | placement |
|---|---|
| teacher, no search | 3.030 |
| teacher + repositioning search, run 1 | 3.337 |
| teacher + repositioning search, run 2 | **3.337** (identical) |

**+0.307, t=+2.45, n=300.** Within 0.004 of 53.2's original +0.303.

So the per-worker RNG added *variance* (a 0.076 swing between runs) but **not
bias**, and 53's conclusion stands: one-ply positional search harms the full
teacher. What changed is that the number is now reproducible and the harness no
longer leaks.

Still open:

- Why search harms a good teacher (54.3). Both proposed mechanisms have
  evidence against them.
- The teacher's positional blind spot (52.4) remains unfilled, and one-ply
  search is now ruled out as the instrument.
- 46 and 47's per-configuration numbers were all measured on the unstable
  stream. Their *conclusions* are unaffected -- 47.9 found nothing
  distinguishing any configuration, and added noise can only have made that
  more likely, not less -- but any future citation of a specific figure from
  them should be re-measured first.

---

## 55. DAgger closes half the imitation gap, once the fit stops diverging (08-05)

### 55.1 Two runs destroyed by an unstable fit

DAgger was run for the first time against the current teacher, slot head and
`copy_counts`. Both attempts collapsed to ~8.000 -- last place in every game:

| run | BC | round 1 | round 3 | final |
|---|---|---|---|---|
| first | 3.517 | 92.2% match, loss 0.23 | loss 2.2e5 | 8.000 |
| + gradient clipping | 4.100 | loss 3.2e5 | loss 1.0e5 | 7.933 |

Rounds 1 and 2 of the first run were *healthy and better than the clone* (92.2%
and 93.3% action match against BC's 89.6%), then the loss exploded.

**Two mechanisms were proposed and the first was wrong.** Gradient clipping was
missing -- `fit_clone` ran `zero_grad(); backward(); step()` with no clip, where
SB3's own PPO clips at `max_grad_norm`. That is a real defect and is now fixed.
It was **not** the cause: with clipping the divergence moved *earlier*, from
round 3 to round 1.

The cause was the learning rate. `fit_clone` builds a fresh `Adam(lr=1e-3)` per
call -- 3.3x PPO's rate, with moment estimates reset every refit and no
schedule. Stable on 137k expert rows; divergent on 170k+ aggregated ones. The
DAgger path now defaults to **3e-4**, exposed as `--dagger-lr`.

Data was ruled out first rather than assumed: both expert-driven and
student-driven datasets were checked for illegal labels, empty masks,
non-finite observations and unbounded returns. All clean.

*Lesson.* **A loss curve consistent with a mechanism is not evidence for it.**
Both explosions looked exactly like gradient explosion, and one hour of compute
went into the wrong fix. When two hypotheses both fit the same summary
statistic, instrument rather than guess -- per-batch loss and gradient norms
would have separated them immediately.

### 55.2 One round closes 54% of the gap

At lr=3e-4 the fit is clean -- loss 0.452 -> 0.178, action match 87.2% ->
94.3%, no instability. n=300, shared seeds:

| arm | placement | vs teacher | t |
|---|---|---|---|
| TEACHER | 3.030 | -- | -- |
| **dagger (1 round)** | **3.263** | **+0.233** | +1.70 |
| clone (BC only) | 3.537 | +0.507 | +3.31 |

**dagger vs clone: -0.273, t=-1.85.** The gap to the teacher falls from 0.507
to 0.233 -- **54% closed** by point estimate, and the best imitation result
since `copy_counts` (40.1).

It is **not resolved**: |t|=1.85 is under this project's bar. Recorded as
suggestive. Three things argue it is real -- the mechanism matches 50.3's
finding that the gap is interactional, the fit was clean, and this was **one**
round where three were planned.

*A retracted claim.* The 60-episode in-run evaluation read **2.883**, better
than the teacher, and was reported as such with an explicit note that it needed
300 seeds. It did not survive them. The discipline held only because the
verification was already queued when the number was reported.

### 55.3 Still open

- Three rounds at 3e-4, the run originally intended. If it passes |t|=2 the
  result stands on its own.
- Whether the fresh-optimiser-per-refit is itself worth fixing; a persistent
  optimiser with a schedule is the standard form.

---

## 56. The teacher's 3.030 mostly measured weak opposition (08-05)

**Question.** Every number in this project is measured with the agent in one
seat and seven `GreedyPolicy` bots in the others. Eight seats makes **4.500
parity by construction**, so 3.030 means "beats those seven bots" and nothing
more. Whether that is skill has never been tested.

`scripts/teacher_check.py` swaps the opponents for a trained policy
(`reclone-rowhead`) in all seven seats. n=300:

| arm | placement | 1st | top4 |
|---|---|---|---|
| teacher vs bots | **3.030** | 37.0% | 72.3% |
| **teacher vs clones** | **4.387** | 14.0% | 53.7% |
| clone vs clones (control) | 4.707 | 12.0% | 45.3% |
| unflagged scripted vs clones | 5.900 | 3.7% | 25.0% |

**The teacher loses +1.357 placement (t=+7.52) when the opposition is
competent.**

### 56.1 The control does not land on 4.500, and that matters

`clone vs clones` reads **4.707**, not the 4.500 arithmetic predicts. The cause
is a real asymmetry rather than a bug: the agent seat acts one action at a time
through `evaluate` and deterministically, while opponent seats run
`SnapshotPolicy` stochastically with a 12-action-per-round cap. "The same
policy in every seat" is therefore not quite true.

So **4.707 is this harness's parity line**, not 4.500, and every arm must be
read against it. Quoting 4.387 as "0.11 better than parity" would understate
the teacher by using the wrong reference.

### 56.2 What the teacher actually is

Against the harness's own parity line:

| field | teacher's edge over parity |
|---|---|
| GreedyPolicy bots | **1.36** |
| trained clones | **0.32** |

The teacher is genuinely better than the policies around it, and its edge
**shrinks fourfold** when the opposition is competent. It is a modestly good
policy that beats weak bots decisively -- not a strong one.

Ordering survives: teacher 4.387 < clone 4.707 < unflagged scripted 5.900. The
teacher's edge over the clone compresses from 0.507 in the bot field to 0.320
in the clone field, which is the same compression seen everywhere else.

### 56.3 What this does and does not invalidate

**Does not:** every result in this log is a *comparison* between policies
measured against the same fixed field. Those comparisons stand.

**Does:** the absolute scale. "Teacher at 3.030" reads as a strong player and
is not one. The 0.507 imitation gap and 55.2's closing of half of it are real,
but they happen in a compressed and forgiving environment.

**A limit of this test, stated before it was run.** The opponents are clones
*of the teacher* and inherit its blind spots -- neither repositions (52.4), and
both ignore augments the data makes inert anyway (51.2). Beating them by 0.32
is a narrow claim. This test can show the teacher is not good; it cannot show
that it is.

The genuinely external checks remain undone:

- Compare engine statistics against public TFT data -- game length, 3-star
  frequency, damage curves. A data question, not an ML one.
- Fix the known simulator gaps: positional multi-target targeting (47.4) and
  the placeholder augment pool (17.1) are the two largest.

---

## 57. The DAgger divergence was unbounded logits, not gradients (08-05)

Entry 55.1 named the learning rate as the cause of the DAgger explosions and
fixed it. A third run diverged anyway, in round 2. Three runs had now blown up
at three different rounds under three configurations, which is the signature of
something that accumulates rather than something that fires.

### 57.1 What the instrumentation showed

Per-epoch pre-clip gradient norm and largest legal-action logit were added to
`fit_clone`. One run answered it:

| stage | loss | action match | grad | max logit |
|---|---|---|---|---|
| bc epoch 1 | 1.2589 | 63.5% | 9.34 | 87 |
| bc epoch 50 | 0.2941 | 89.4% | 9.44 | 1,224 |
| dagger1 epoch 50 | 0.1777 | 94.3% | 8.93 | 6,805 |
| dagger2 epoch 8 | 0.2434 | 92.1% | 10.87 | 8,985 |
| dagger2 epoch 50 | 546,979 | 41.9% | 745,943 | 121,164,840 |

The gradient norm is **flat at ~9-14 until after the collapse**. It is a
consequence, not a cause. The logits climb monotonically from the first epoch,
carry across rounds, and eventually one misclassified example with a huge
margin contributes ~1e5 loss.

This is textbook softmax cross-entropy on near-separable data: once the argmax
is correct, the only remaining gradient pushes the correct logit further out,
and the optimum is at infinity. BC was on the same trajectory the whole time
(87 -> 1,224), merely subcritical -- which is why cloning always survived and
only aggregation died.

**An instrumentation bug found on the way.** The first logit readings were a
flat 1e8 -- sb3-contrib's mask fill value. An unfiltered max reports the
constant, never the network. Only legal-action logits are read now.

### 57.2 Three fixes that could not have worked

| attempt | effect |
|---|---|
| gradient clipping | moved divergence round 3 -> round 1 |
| lr 1e-3 -> 3e-4 | moved divergence round 1 -> round 2 |
| AdamW decay 1e-2 | 1,224 -> 684 over 50 BC epochs, still climbing |

All three bound the **rate of travel** against an objective whose optimum is at
infinity. None creates a destination. Decay was measured alone rather than
assumed: it halved the endpoint without flattening the curve, whose last eight
epochs were steeper than its middle thirty. It is kept -- it cost 0.6 points of
action match -- but it is not the fix.

### 57.3 Label smoothing, and what it did

Smoothing spreads `eps` uniformly over the *legal* actions, so the loss has a
finite minimiser and the drift has somewhere to stop. Same data, same seed,
same 50 epochs, `eps=0.02`:

| arm | max logit at epoch 50 | action match |
|---|---|---|
| plain | 1,224 | 89.4% |
| + AdamW decay | 684 | 88.8% |
| + label smoothing | **31** | **89.8%** |

Flat in the low 30s across the last fourteen epochs, and the *best* action
match of the three. Bounding the logits cost nothing.

**A prediction that was directionally right and numerically wrong.** The
plateau was predicted at ~10, from `log((1-eps)(K-1)/eps)`. That formula
describes the target's logit *gap*; the instrument reports the largest absolute
log-probability over legal actions, which is the least-likely legal action -- a
different and larger quantity. The claim that mattered (bounded, two orders of
magnitude down) held; the specific figure was mismatched to what was measured.

**Warm-start placement, flagged not claimed.** 3.600 here against 3.150 for the
decay-only run, both n=60 with +/-0.6 intervals. 3.600 sits closer to the
n=300 `reclone-rowhead` figure of 3.537, so the reading is that 3.150 was the
lucky draw -- but n=60 cannot settle it. Re-measure at n=300 if the DAgger arms
come back ambiguous.

*Lesson.* **Bound the destination, not the speed.** Three fixes in a row
treated a divergence as a stability problem when it was an objective problem.
Each made the symptom later and was read as partial progress. The question that
separated them is not "what stops this growing so fast" but "what does this
converge to, and is that finite".

*Lesson (restated from 55.1, because it was not followed).* The lesson "a loss
curve consistent with a mechanism is not evidence for it -- instrument rather
than guess" was written the same morning this entry's first two wrong fixes
were attempted. Roughly three hours of compute went into hypotheses that the
instrumentation settled within 30 epochs of its first run. Writing a lesson down
is not the same as applying it.

### 57.4 The three-round run, and a side effect

Three rounds completed with no divergence -- logits 41.7, 45.7, 45.0 across the
rounds where the previous run reached 6,805 then 1.2e8. The blocker is gone.

Label smoothing also **improved behaviour cloning on its own**, which is not
what it was added for: BC 3.537 -> 3.390 at n=300 (see 58). Suggestive rather
than established -- two training runs at one seed each, and the arm carries
AdamW decay as well.

### 57.5 Still open

- Whether `eps=0.02` is near-optimal or merely sufficient. It was picked as a
  standard value, not measured.
- The fresh-optimiser-per-refit from 55.3, still unaddressed.

---

## 58. Imitation is exhausted; early-game outcomes are near-unpredictable (08-05)

### 58.1 Three rounds of DAgger buy nothing over one

n=300, shared seeds, all arms measured in the same run:

| arm | placement | vs teacher | t |
|---|---|---|---|
| TEACHER | 3.030 | -- | -- |
| dagger_smooth (3 rounds) | 3.280 | +0.250 | +1.71 |
| dagger_lr (1 round) | 3.263 | +0.233 | +1.70 |
| bc_smooth (BC only) | 3.390 | +0.360 | +2.60 |
| reclone-rowhead (older BC) | 3.537 | +0.507 | +3.31 |

Rounds 2 and 3 are worth **nothing**: 3.280 against 3.263. Action match
saturated at 93.7% after round 1 and never moved, which was the tell. 55.3's
open item is answered.

**The two paths converge.** DAgger over the old BC gained 0.274; over the
smoothed BC it gained only 0.110, because BC had already travelled most of the
distance. Different routes, same endpoint ~3.27 -- the shape of a ceiling.

**The remaining gap is no longer significant.** +0.250 at t=+1.71 is under this
project's bar. The clone is not distinguishable from the policy it copies. The
imitation gap that opened at 0.507 (entry 49) is closed as a *findable*
quantity, and further imitation work has nothing left to target.

*A trap avoided rather than survived.* The in-run 60-episode evaluation read
3.600 -> 3.617, i.e. **no gain at all**, and the 300-seed measurement shows
-0.110. Reporting the n=60 figure would have produced a retraction in the same
shape as 55.2's 2.883. It was not reported because the verification was already
queued -- the discipline, not the judgement, is what held.

### 58.2 How much of placement is knowable at all

The critic prints `0.965 in-sample, 0.228 held-out` in every warm start, and
0.228 has been cited repeatedly without ever measuring its achievable maximum.

The engine is deterministic given a seed, so a state can be replayed exactly and
then forked: play to round `k`, replace the match RNG and every seat policy's
RNG with independent streams, play to the end, `R` times. Spread across those
rollouts is variance the state at `k` cannot explain, by construction. By the
law of total variance the best explained variance *any* critic could reach is
`Var_s(E[P|s]) / Var(P)`.

40 seeds x 8 rollouts x 4 fork points, `GreedyPolicy` in all eight seats:

| fork round | irreducible | explainable | EV ceiling |
|---|---|---|---|
| 6 | 4.200 | 0.566 | **0.119** |
| 12 | 3.290 | 1.873 | 0.363 |
| 18 | 2.660 | 2.669 | 0.501 |
| 24 | 0.775 | 4.177 | 0.844 |

**Neither prior hypothesis was right; the answer is a function of round.** At
round 6 almost nothing about final placement is knowable -- a ceiling of 0.119
regardless of model. By round 24 the game is nearly decided at 0.844.

The between-seed term is corrected for estimation error (`between_raw - w/R`);
each seed's mean comes from 8 rollouts, and the uncorrected figures run 0.087
higher at the early fork points. Uncorrected, this would have measured the
ceiling plus its own sampling noise.

### 58.3 What that implies, and the limit on it

**The critic is underfit, not maxed out.** 0.228 against a mid-game ceiling near
0.5, with 0.965 in-sample, is memorisation. So "advantages are irreducibly
noise" is too pessimistic: PPO's degradation (entry 48, +1.077) is at least
partly a fixable baseline problem.

**Early-game credit assignment is structurally near-hopeless.** A ceiling of
0.119 at round 6 is not a modelling failure. Economy, rolling and levelling
decisions live exactly where outcomes carry almost no signal.

**A limit, stated before acting on it.** This measures the ceiling given the
*full match state*. The critic sees a 418-float encoding, so there are two
stacked ceilings and this cannot separate "underfit" from "the observation
cannot express the difference". Refitting with substantially more expert data
discriminates: climbing toward 0.5 means data-limited, plateauing near 0.25-0.3
means observation-limited.

**A proxy, also stated up front.** Placement under `GreedyPolicy` in all eight
seats; the critic fits discounted shaped returns for the teacher's seat. The
dominant noise terms are policy-independent to first order.

### 58.4 Where this leaves the project

Imitation is done. The endpoint is ~3.27 against a teacher at 3.030, and entry
56 established that 3.030 is roughly *average* against competent opposition
(4.387 against a 4.500 parity line). Both remaining paths are now explicit:

- **Make RL work.** Blocked on a critic at less than half its achievable
  explained variance. This is the first evidence that the blockage is fixable.
- **Raise the teacher.** Imitation tracks its teacher closely now, so a better
  teacher would convert directly -- but it relocates the ceiling rather than
  removing it.

*Lesson.* **Measure the ceiling before optimising the rate.** 0.228 was quoted
across three entries as evidence the critic had collapsed. It is roughly half
of what is achievable mid-game and *four times* what is achievable at round 6 --
the same number is a failure or a near-optimum depending on when it is read.

---

## 59. The critic is data-limited, and overtrained by a factor of ~50 (08-05)

Entry 58.3 could not separate "the critic is underfit" from "the observation
cannot express the difference". This measures the discriminating curve:
held-out explained variance against **episodes**, at fixed capacity, with the
real value-branch shape (`obs -> 256 -> 256 -> 1`).

**The hypothesis, stated before the run.** 137k rows from 400 episodes looks
like abundant data and is not: the return is dominated by one terminal
placement per game, so the effective number of independent targets is closer to
the *episode* count than the row count. That predicts a curve still climbing at
1200 episodes.

| episodes | rows | EV train | EV holdout | best epoch |
|---|---|---|---|---|
| 75 | 25,424 | 0.844 | 0.263 | 11 |
| 150 | 51,000 | 0.701 | 0.276 | 3 |
| 300 | 103,117 | 0.638 | 0.364 | 3 |
| 600 | 206,334 | 0.601 | 0.416 | 2 |
| 1200 | 409,697 | 0.552 | **0.452** | **1** |

| capacity | EV train | EV holdout |
|---|---|---|
| (64, 64) | 0.556 | 0.454 |
| (256, 256) | 0.552 | 0.452 |
| (512, 512) | 0.553 | 0.461 |

### 59.1 Data-limited, not capacity-limited, not observation-limited

Held-out EV climbs 0.263 -> 0.452 and is still rising (+0.036 on the last
doubling), against entry 58.2's ~0.5 mid-game ceiling. **Capacity is
irrelevant**: 64x64 matches 512x512 to within 0.007, so the value head was never
the constraint. The observation is not the binding constraint either -- it
supports 0.452, close to what an oracle with full match state could reach.

### 59.2 The unpredicted finding: 50 epochs where 1 is optimal

The `best epoch` column was not what this probe was built to measure. Best
held-out EV arrives at **epoch 1** at 1200 episodes and epochs 2-3 at 300-600.
`behaviour_clone` trains for **50**. The critic is optimised one to two orders
of magnitude past its optimum, and everything after is memorisation -- which is
precisely the 0.965 in-sample / 0.228 held-out signature that has been quoted
since entry 49.

At 300 episodes this fitter reaches 0.364 where the 400-episode warm start
reports 0.228, so early stopping alone looks worth ~+0.15 EV **at zero
collection cost**.

*Not a like-for-like comparison.* This probe fits the value head alone with
Adam at 1e-3; the warm start fits policy and value jointly for 50 epochs at
`value_coef=0.5`. The direction is unambiguous; the magnitude is not a
substitution.

### 59.3 Why the controls mattered

A low EV is only evidence about the data if the fitter works. It reaches
**0.986** on a linear synthetic signal and finds **nothing** in pure noise --
the second control guards a risk introduced by reporting best-over-epochs,
which deliberately selects the most favourable epoch and could manufacture
apparent signal. Both are asserted in `tests/test_critic_scaling.py`.

### 59.4 What this predicts, and the test that would refute it

PPO degrades a strong warm start by +1.077 (entry 48). The mechanism proposed
in 58.3 was that advantages are computed against a critic that is noise on
unseen states. That critic is now explicable: undertrained on independent
targets and overtrained on epochs.

**The prediction: fixing the critic should reduce or remove PPO's
degradation.** If PPO still degrades a warm start with a critic at ~0.45
held-out EV, the advantage-quality story is wrong and the cause is elsewhere.
That is the discriminating run, and it has not been done.

*Lesson.* **Count independent targets, not rows.** "137k transitions" framed the
dataset as large for four months. The terminal reward makes an episode one
target, and every conclusion about the critic being underfit or the observation
being weak was drawn against a sample of ~400.

---

## 60. The critic was never PPO's constraint (08-05)

Entry 59.4 predicted that fixing the critic would reduce PPO's +1.077
degradation, and named the refuting outcome in advance. **It refuted.**

### 60.1 The prediction failed

A warm start at 1200 episodes with the value rewind reached **0.385 held-out
EV** (from 0.228), with the in-sample gap collapsing from 0.965/0.228 to
0.679/0.385. PPO from that frozen checkpoint, 60k steps, entry 48's
configuration:

| steps | ent_coef=0.01 | ent_coef=0 |
|---|---|---|
| 0 (warm start) | 3.700 | 3.700 |
| 10k | 3.717 | 4.033 |
| 20k | 4.067 | 3.883 |
| 30k | **7.567** | 4.983 |
| 60k | 6.683 | 7.950 |
| 61k | 7.283 | **8.000** |

On-policy explained variance held at **0.5-0.85 throughout**. The critic was
healthy while the policy was destroyed.

**A confound I introduced.** Three things changed at once (critic rewind, 400
-> 1200 episodes, label smoothing) and the comparison was against entry 48's
*stored* number. "A good critic does not prevent degradation" survives that;
"the fix made it worse" does not, and is not claimed.

**Removing the entropy bonus delayed the collapse and did not prevent it** --
the fourth intervention today to change *when* a failure happens rather than
*whether*, after the three in entry 57.2.

### 60.2 What the collapsed policy actually does

Rolled out over three seeds, actions by kind:

| policy | steps | top actions | placements |
|---|---|---|---|
| `ws1200` | 881 | BUY 285, SELL 200, BUY_XP 109, PLACE 99 | 3, 8, 5 |
| `ppo-noent` | 330 | **REROLL 83**, SELECT 62, END 51, BUY 42, PLACE 22 | 8, 8, 8 |

The teacher has `roll_at_level=0` and never rerolls, so the clone does not
either. PPO converges onto REROLL as its most common action, stops buying
(285 -> 42) and stops placing (99 -> 22). No board, every fight lost, 8.000 --
exactly the `do_nothing` baseline.

REROLL is almost always legal, costs gold, and carries no immediate reward or
penalty. It is where a policy lands when nothing distinguishes actions.

### 60.3 The actual constraint

With terminal-only reward (`reward_shaping=False`) discounted at gamma=0.999
over 300-900 steps, the per-step advantage is dominated by *which game* the
episode is, not *which action* was taken. Entry 58.2 already measured this: the
EV ceiling at round 6 is **0.119**. Early-game advantages are near-noise for any
critic, so improving the critic could not have helped -- 59.4 optimised a term
that was never binding.

**Still open, and now the obvious test:** `--reward-shaping` exists and was off
in every arm here. Per-step signal is the intervention that addresses the
measured cause rather than a symptom. Untested.

### 60.4 Reward shaping, and a transient that was not real

`--reward-shaping` was the test 60.3 named. It **also only delayed the
collapse**: 8.000 unshaped against 6.283 shaped at 61k steps, from the same
3.700 warm start. Reward sparsity is not the root cause either.

One reading looked like the first RL improvement this project has ever
produced -- **3.283 at 10k steps**, against a 3.700 warm start, with top-4 at
71.7% vs 60.0%. It did not survive:

| arm | placement (n=300) | vs teacher | t |
|---|---|---|---|
| TEACHER | 3.030 | -- | -- |
| `ppo-shaped-10k` | 3.427 | +0.397 | +2.76 |
| `ws1200` | 3.603 | +0.573 | +3.90 |

**Paired: -0.177, t=-1.12.** Under the bar. Better in 124 games, worse in 101,
tied in 75 -- a coin flip with a lean.

The run's own log had already said so: consecutive evaluations at 10,000 and
10,240 steps read **3.283 and 3.583**. A 0.3 swing from 240 steps of training is
the n=60 noise floor, and it was visible before the verification was queued.

**A selection effect worth naming.** The 10k point was chosen *after* looking at
seven evaluations across three runs. Fresh evaluation seeds control for
evaluation noise but not for having picked the best of seven draws. The clean
version needs a second *training* seed, which is the axis that discriminates.

*Lesson.* **An intervention that only moves the failure later is evidence
against its own mechanism.** Five times today -- clipping, learning rate and
decay on the DAgger divergence, then the entropy bonus and reward shaping here.
Each looked like partial progress and each was a sign the diagnosis was wrong.
Delay is not mitigation.

---

## 61. The drift is not advantage-driven (08-05)

Entry 60 left one hypothesis standing: REROLL wins because the advantages
reward it. `scripts/advantage_probe.py` reads PPO's **own** `RolloutBuffer`
after `compute_returns_and_advantage`, so this is the signal the optimiser
consumed, not a reimplementation of GAE.

### 61.1 REROLL is penalised, and wins anyway

`ws1200` (the warm start, where the drift begins), 81,920 transitions:

| kind | n | mean adv | % positive |
|---|---|---|---|
| SELL | 19,638 | +0.0083 | 56.6% |
| SELECT | 8,757 | +0.0070 | 55.4% |
| END_PLANNING | 3,164 | +0.0043 | 51.8% |
| BUY_XP | 9,474 | +0.0040 | 54.6% |
| BUY | 27,755 | +0.0006 | 51.0% |
| EQUIP | 3,226 | -0.0062 | 45.2% |
| PLACE | 8,058 | -0.0103 | 43.5% |
| **REROLL** | **139** | **-0.0107** | 40.3% |
| PICK_AUGMENT | 735 | -0.0178 | 41.1% |

`ppo-noent` (the collapsed policy, 12,288 transitions) agrees: REROLL -0.0042
against -0.0039 overall, at n=1071. Measured from both ends, **REROLL is not
preferentially rewarded**. The hypothesis is refuted -- the sixth today.

**The advantages are also barely differentiated.** In the collapsed policy every
kind falls between +0.0022 and -0.0063, a spread of 0.008 across categories
spanning "build your board" and "burn gold for nothing".

### 61.2 What this leaves: a shared-parameter coupling

The slot head has per-kind heads (`sell_head`, `select_head`, `place_head`,
`equip_head`, `buy_head`) and **one `global_net` producing END_PLANNING, BUY_XP
and REROLL together**. Both of REROLL's siblings carry positive advantage
(+0.0043, +0.0040). Pushing `global_net` toward them plausibly raises REROLL's
logit as a side effect, against its own negative advantage.

This is the first hypothesis today that is not about the reward. It predicts the
collapse changes shape or disappears under `--no-slot-head`. **Untested.**

### 61.3 Two process failures, same root

`env_kwargs_from()` was written *for* this script to avoid rebuilding an env
from module defaults (45.2) -- and then not called. A 381-vs-418 shape error
caught it. An unused guard is worse than an absent one: it reads as solved.

The probe printed a confident verdict from **three** REROLL samples, reading
+0.0380 -- the opposite of the n=1071 and n=139 answers. Had only the warm start
been run at low volume, it would have confirmed the prevailing hypothesis on
noise. A `MIN_SAMPLES` guard now blocks the verdict below 60.

*Lesson.* **Read the signal before theorising about it.** Six hypotheses were
proposed and refuted across entries 57, 60 and 61 -- five about reward or
optimisation, one about the advantages. The probe that settled it took under an
hour and could have been written before any of them.

---

## 62. REROLL rises under any perturbation (08-05)

Entry 61 left one hypothesis: REROLL shares `global_net` with END_PLANNING and
BUY_XP, both of which carry positive advantage, so pushing them lifts it.
Tested directly -- ascend one action kind's log-prob from fixed weights, measure
REROLL's before and after, with separate-head kinds as controls.

| arm | shares `global_net` | REROLL delta |
|---|---|---|
| `buy_xp` | yes | +2.58 |
| `end` | yes | +1.46 |
| `buy` | no | +0.61 |
| `place` | no | +0.10 |

Shared +2.02 against separate +0.35, and the probe declared the coupling
confirmed. **It was wrong.**

### 62.1 The control that refuted it

Freezing `global_net` and repeating the `end` arm should suppress the rise if
the coupling runs through those weights. It **amplified** it: +5.03 against
+1.46. The mechanism is not `global_net`.

That control is itself confounded -- freezing the head makes the objective
harder to reach, forcing larger changes upstream, which perturbs everything
more. It is enough to refute the specific claim, not to quantify a replacement.

The arms were unequal in another way, noticed before the control ran: `buy` and
`place` span many slot-scored indices, so a `logsumexp` push spreads thinner per
index than for single-index `end`/`buy_xp`. The original contrast was never as
clean as its verdict line implied.

### 62.2 What survives

REROLL's log-prob rose under **every** intervention -- +1.46, +2.58, +0.61,
+0.10, +5.03 -- and never fell, despite these being *normalised* log-probs where
raising one action should lower the rest.

The likely mechanism is unglamorous. Cloning drives rarely-taken actions to very
low logits: REROLL sits at **-9.48** and is 0.2% of expert actions. Any
perturbation of the shared representation regresses it upward. It is legal in
**93.7%** of states, so as its probability recovers it gets sampled, and the loop
closes. Nothing about reward, advantage or head structure is required.

If that is right, the collapse is a property of *fine-tuning a heavily peaked
cloned policy with a near-flat learning signal* -- not of PPO's configuration.
Untested; it predicts the drift targets whichever legal action the clone
suppressed hardest, not REROLL specifically.

### 62.3 Seven hypotheses

Across entries 57, 60, 61 and 62, in one day: gradient clipping, learning rate,
AdamW decay, critic quality, entropy bonus, reward sparsity, a 10k transient,
REROLL-is-rewarded, and the shared head. Every one was consistent with the
evidence available when proposed, and every one was refuted by a measurement
that took under an hour.

*Lesson.* **Write the control before believing the arm.** This probe printed
"COUPLING CONFIRMED" from a comparison whose asymmetry was already known, and
the refuting control was one command away. A verdict line that can only say
"confirmed" or "unexplained" will say "confirmed" too often.

---

## 63. The drift targets suppressed *and* always-legal actions (08-05)

Entry 62 predicted the collapse was regression-to-the-mean in logit space: the
mass PPO gains should concentrate on whatever cloning suppressed hardest. Both
policies scored on the **same 3000 states**, paired per action index.

### 63.1 The prediction as stated is false

`correlation(baseline log-prob, gain) = +0.091` -- near zero and the *wrong
sign*. Worse for the hypothesis:

| baseline quintile | mean gain |
|---|---|
| lowest (most suppressed) | **-0.771** |
| highest | -0.423 |

The most suppressed actions *lost* more than the least. Suppression alone does
not cause the runaway.

### 63.2 What does: suppression x legality

| among suppressed actions | n | mean gain |
|---|---|---|
| legal in >50% of states | 16 | **+0.178** |
| legal in <=50% | 35 | -0.398 |

A **+0.576** contrast. This was built as the falsifiable half precisely because
no ceiling effect explains it -- the ceiling argument applies equally to both
groups, which are matched on baseline.

| top gainers | kind | legal | base | gain |
|---|---|---|---|---|
| 500 | **END_PLANNING** | 97.8% | -8.50 | **+3.61** |
| 498 | REROLL | 93.8% | -9.43 | +1.58 |

**The largest gainer is END_PLANNING, not REROLL** -- which independently
explains the step count falling 881 -> 330 (60.2). The policy learns to stop
playing, and REROLL is the runner-up rather than the story.

### 63.3 The mechanism, and what it now predicts

Only actions legal in nearly every state can absorb drifting probability mass;
once they do they are sampled, and sampling reinforces them. Suppressed *and*
always-legal is the conjunction. Neither reward, advantage (61), nor head
structure (62) is required.

This is the first hypothesis today to survive its own discriminating test, and
one half of it was refuted in the same run -- which is the reason to believe the
other half at all.

**It predicts** that constraining the always-legal actions -- masking
END_PLANNING until some minimum action count, or removing REROLL from a teacher
that never uses it -- should change the collapse's shape, not merely delay it.
Untested, and "delays it" is the outcome that would refute it, per 60.4's
lesson.

*Lesson.* **Build the half that can fail.** The correlation was always going to
look supportive -- log-probs are bounded above, so some negative slope is
mechanical. The legality split was matched on baseline and could have come back
flat. It is the only part of this entry worth citing.

---

## 64. The collapse is fixable, and PPO still contributes nothing (08-06)

Entry 63 located the drift: mass flows to actions cloning suppressed **and**
that are legal nearly everywhere. The standard answer is an anchor to the
cloned behaviour -- what RLHF does when fine-tuning an imitation model. Note it
is *not* `--target-kl`, which bounds movement from the **rollout** policy and
was reverted as the worst arm from a parity clone (23.5).

Implemented as an auxiliary BC loss on frozen expert data rather than a KL term
in PPO's objective, to avoid copying sb3-contrib's 118-line `train()` (silent
drift on upgrade, and it would corrupt the `entropy_loss` logging that
diagnosed 60-62).

### 64.1 A configuration error that looked like a result

The first anchored run degraded to 5.517 and lost expert agreement 82.6% ->
65.1%. Read as "anchoring is too weak", it was arithmetic: the anchor fired
**once** per 2048 environment steps while PPO ran `n_epochs=10` over 8
minibatches -- **80** gradient steps in the same window. It measured one step
against eighty.

`--bc-anchor-steps` now matches the counts, and the run prints the ratio so the
comparison cannot silently be unfair again.

### 64.2 Matched, the collapse disappears

| steps | anchor 1:80 | anchor 80:80 |
|---|---|---|
| 10k | 3.883 | 3.517 |
| 30k | 4.417 | 3.667 |
| 40k | 5.017 | 3.167 |
| 61k | 5.517 | 3.683 |

**No degradation across 60k steps** -- the first stable PPO run in this project,
after six interventions failed (57.2, 60.1, 60.4).

### 64.3 The control: it is not PPO

Expert agreement *rose*, 82.6% -> 86.1%, and behaviour moved **toward** the
teacher (BUY 285->335, SELL 200->248, steps 881->968). That is what continued
cloning looks like, not what RL improvement looks like. The anchored arm also
saw 200 expert episodes `ws1200` never did.

`--learning-rate 0` zeroes PPO's updates while the anchor runs on its own Adam.
300 shared seeds:

| arm | placement | vs teacher | t |
|---|---|---|---|
| TEACHER | 3.030 | -- | -- |
| **anchor-only (PPO disabled)** | **3.400** | +0.370 | +2.59 |
| ppo-anchored2 | 3.513 | +0.483 | +3.02 |
| ws1200 | 3.603 | +0.573 | +3.90 |

Paired: **anchored2 - anchor-only = +0.113, t=+0.73** -- PPO makes it slightly
*worse*. `anchor-only` is the best arm. All stability and all gain come from
behaviour cloning; PPO is inert to mildly harmful.

**The stable RL run is behaviour cloning in a PPO-shaped wrapper.**

### 64.4 What does pay

`anchor-only - ws1200 = -0.203, t=-1.35`: 200 extra expert episodes, suggestive
and in the direction 59 predicted from imitation still being data-limited at
1200 episodes. Imitation keeps paying; RL does not.

*Lesson.* **Check the ratio before reading the arm.** An intervention given 1/80
the gradient steps of what it opposes has not been tested. And a mid-run
reversal was called here on a single n=60 checkpoint (anchor-only 4.083 vs
3.517) that the 300-seed control flatly contradicted -- the fourth n=60 reading
today to point the wrong way.

---

## 65. The training-seed noise floor, and what it invalidates (08-06)

Four clones, identical configuration (400 episodes, smoothing, slot head),
differing **only in training seed**, all on 300 shared evaluation seeds:

| clone | placement |
|---|---|
| seedvar-1 | 3.387 |
| bc_smooth (seed 0) | 3.390 |
| seedvar-3 | 3.467 |
| seedvar-2 | 3.543 |

**spread 0.157, sd 0.074.** Largest pairwise |t| between *identically
configured* clones: **1.00**.

### 65.1 What it invalidates

`ws1200` (1200 episodes) scored **3.603** -- outside the range of all four
400-episode clones. Every arm built on it was then measured against it:

| arm | vs `ws1200` | vs a typical clone |
|---|---|---|
| `ws1200-dagger` (3.410) | -0.193, t=-1.23 | **+0.02** |
| `anchor-only` (3.400) | -0.203, t=-1.35 | **+0.01** |

Both "gains" were `ws1200` being a poor draw. `ws1200-dagger` 3.410,
`anchor-only` 3.400, `bc_smooth` 3.390 and `seedvar-1` 3.387 are **the same
number**.

**Imitation is saturated at ~3.40** -- 400 episodes or 1500, DAgger or not.
Entry 64.4's "imitation keeps paying" is withdrawn: it was one unlucky baseline
read as a trend.

### 65.2 What survives

Effects far larger than 0.157 stand: the PPO collapse (3.7 -> 8.0) and its fix,
imitation's gap to the teacher (+0.36 to +0.51, t=+2.4 to +3.5), and the critic
defects of 59. Effects near 0.2 measured on one training seed per arm do not.

### 65.3 The statistical error

A paired *evaluation* t answers "is this policy better on these seeds". A claim
about a **method** needs the training seed varied too, and evaluation pairing
cannot substitute -- no number of evaluation seeds averages out one training
run's luck. With sd=0.074, detecting a 0.2 effect at |t|=2 needs roughly **2-3
training seeds per arm**; one gives t~1.9 at best, which is where tonight's
readings kept landing.

*Lesson.* **A difference is uninterpretable without its noise floor** -- the
same shape as *a rate is uninterpretable without its achievable maximum*, and
unmeasured here for 65 entries. Evaluation noise was detected four times
tonight and each time "fixed" by adding evaluation seeds (60 -> 300). That
treats the symptom. The variance was upstream, and the 50 minutes this
measurement cost could have been spent at any point in the preceding ten hours.

---

## 66. Every lever closed, and the reason is upstream (08-06)

### 66.1 The teacher is at a local optimum on every parameter

300 shared seeds, scripted policy, **no training seed** so these need no
replication caveat. `roll_at_level=0` reproduces 3.030 as its control.

| arm | placement | vs control | t |
|---|---|---|---|
| control | 3.030 | -- | -- |
| roll_at_level=8 | 3.043 | +0.013 | +0.25 |
| roll_at_level=7 | 3.187 | +0.157 | +1.73 |
| roll_at_level=6 | 3.257 | +0.227 | +1.96 |
| level_at_gold=40 | 3.190 | +0.160 | +1.43 |
| level_at_gold=20 | 3.207 | +0.177 | +1.45 |
| keep_interest=False | 3.257 | +0.227 | +1.81 |
| level_at_gold=50 | 3.310 | +0.280 | +2.31 |

Every change is worse, and `level_at_gold` degrades in **both** directions.
Rerolling never helps -- 61's observation that REROLL is 0.2% of expert actions
was the teacher being *correct*.

### 66.2 The imitation gap is diffuse

Gap attribution on `seedvar-1` (a typical clone, not the unlucky `ws1200`).
Both controls pass: delegating nothing gives 3.387, everything gives 3.030.

| delegated | recovered | % of gap | t |
|---|---|---|---|
| BUY | +0.113 | 32% | -0.78 |
| MOVE | +0.097 | 27% | -0.65 |
| PICK | +0.090 | 25% | -0.75 |
| EQUIP | +0.023 | 7% | -0.23 |
| ECON | +0.020 | 6% | -0.20 |
| SELL | -0.053 | -15% | +0.35 |
| **all** | **+0.357** | 100% | **-2.38** |

Full delegation recovers the gap; **no single kind does**. Three kinds carry a
quarter each, none individually significant. There is no targeted fix.

### 66.3 Why everything is closed: gold has no sink

Living players, mid-game, 30 games:

| round | gold | board | level | stars |
|---|---|---|---|---|
| 12 | 42.6 | 5.25 | 5.33 | 82% 1-star, 18% 2-star |
| 20 | 72.0 | 6.95 | 6.97 | 65% / 35% |
| 28 | **107.8** | 7.66 | 7.42 | 48% / 52%, **~0% 3-star** |

Gold accumulates without bound, and **3-stars essentially never occur** (0.3%
across whole games). In real TFT gold sits near the 50 interest cap because
anything above it is spent, and 3-star low-cost units are routine by stage 4-5.

These are one finding: **gold has no effective sink**. That also explains 66.1 --
rolling is harmful and `level_at_gold` is already optimal not because the
teacher is well-tuned but because there is nothing worth converting gold into.
A ceiling of 3.030 follows from the economy, not from the decision rules.

*Lesson.* **When every lever is at a local optimum, suspect the terrain.** Seven
parameters, two policy classes and an entire RL programme all bottomed out
around the same value. The common cause was upstream of all of them, and one
descriptive measurement of the game state found it. Nothing in this project had
ever printed the average gold.

### 66.4 Next

Diagnose the missing sink before any further optimisation. Candidates: shop
odds or pool sizes making upgrades unreachable, the teacher selling the
duplicates 3-stars need (`sell_bench`, worth +1.893 in 52), or a level cap
interacting with `xpTable`. All are data/engine questions, not ML ones.

---

## 67. Board size dominates, and the slow-roll test was too crude (08-06)

66.4 named the missing gold sink as the thing to diagnose. The 3-star path
needs the real TFT pattern -- hold at low level where 1-cost odds are high, roll
for copies -- which 66.1's **one-at-a-time** sweeps could not have found, since
it requires two changes together.

| arm | placement | vs control | t |
|---|---|---|---|
| control (lvl30, no roll) | 3.030 | -- | -- |
| greedy-lvl (lvl20, roll@8) | 3.263 | +0.233 | +1.87 |
| slow-roll (lvl80, roll@7) | 4.283 | +1.253 | +9.10 |
| slow-roll (lvl80, roll@6) | 4.407 | +1.377 | **+9.70** |

Catastrophic -- among the largest effects in this log. **Board size dominates**:
delaying levels costs slots, and slots decide fights.

### 67.1 Star scaling is not the cause

If 3-stars were underpowered the reroll path would be correctly unattractive.
They are not. Across all 63 champions the 3-star/1-star ratios are **3.24x
health and 2.25x attack damage** -- exactly real TFT's 1.8^2 and 1.5^2, with
zero variance. The unit-quality math is right.

### 67.2 Why this entry is flagged, not concluded

`level_at_gold=80` starves levelling from stage 1. Real slow-rolling holds at
level **6-7 with a nearly full board** and rolls surplus gold. This tested
"never level" and labelled it "slow roll"; the t=+9.70 largely measures the cost
of a small board, which was already known. **It does not establish that reroll
strategies are non-viable here** -- that claim needs an arm that reaches level
6-7 normally and then rolls, which has not been run.

*Lesson.* **A one-at-a-time sweep cannot find a strategy that needs two changes
at once.** 66.1 concluded "local optimum on every parameter" from seven
independent sweeps and stated it more confidently than that design supports. The
conjunction was invisible by construction -- and the first conjunction tried was
then mis-specified, so the question is still open.
