# Judgement Calls — TEMPORARY REVIEW DOC

Every decision made while building milestones 1–7 that the three spec docs did
not fully determine. Written to be reviewed and adjusted; **delete or fold into
docs 01–03 once settled**.

## Review status (2026-08-01)

Four decisions were reviewed and settled. ✅ marks a resolved entry.

| Entry | Decision | Outcome |
|---|---|---|
| 1.1 | Shop draw weighting | ✅ **Keep `by_copies`.** No code change. **Doc 01 sec 5 should be amended** to describe copy-weighted draws. |
| 1.2 | Combat re-targeting | ✅ **Switched to sticky targeting.** Code changed. **Doc 01 sec 3.1 step 3 should be amended.** |
| 3.1 / 3.2 | Invented XP + round-damage tables | ✅ **Leave flagged in `config.unverified`;** try to source real values from CDragon at milestone 8, fall back to these. |
| 4.4 | Item effect magnitudes | ✅ **Added `params` to `ItemDef`.** **Doc 02 sec 2's item schema should be amended.** |

**All three doc amendments have been applied** (2026-08-01): doc 01 sec 3.1
step 3, doc 01 sec 5, and doc 02 sec 2. Both docs carry an `## Amendments`
section at the top recording what changed and why. The code and the specs now
agree on these points.

**Entry 2.1 is now closed** (2026-08-01). Direction given: "Riot is the source
for everything." Investigating the live payload showed that is achievable for
champions/traits/items but *not* for the economy tables — `shopOdds`,
`poolSize`, `xpTable` and `rerollCost` have zero occurrences in the full 26 MB
CDragon document, and `setData` carries only champions, traits, items and
augments. Follow-up direction: community documentation is good enough for
those. So `config.json` stays hand-curated, the fetch script is forbidden from
writing it, and it now carries a `provenance` block classifying every constant
as `riot_published` / `community_documented` / `engine_artifact`. Doc 02 gains
section 4b defining its schema.

Section 9 below records the calls made during milestone 8 itself.

Each entry says what was decided, why, and where it came from. Flags:

- 🔴 **Deviates** from an explicit statement in doc 01/02/03.
- 🟠 **Invented constant** — a number the docs flag as unverified or don't give.
- 🟡 **Gap-filled** — docs were silent; a choice was required.
- ⚪ **Deferred/stubbed** — deliberately not built yet.

Priority column: how much a wrong choice here would cost to change later.

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
| 2.1 | **`data/config.json`** holds every set/patch-specific table: shop odds, pool sizes, XP thresholds, economy constants, combat tunables, round structure, role→mana map. | Doc 02 defines only `champions/traits/items/VERSION.json`, but doc 03 sec 2.7/2.8 requires odds and XP tables be data, not code. A fifth file was the only way to satisfy both. **Doc 02's schema section should probably absorb this.** | **High** — it's a schema addition |
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
| 5.4 | **Tank damage-mana uses HP actually lost** (i.e. after shield absorption) for the 3% term. | Doc 01 sec 3.2 equates "post-mitigation" with "actual HP lost," which is ambiguous when a shield eats the hit. Current reading: a fully-shielded hit generates almost no mana. | Medium — plausibly wrong |
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
| 6b.1 | **Moves use two-step SELECT → PLACE**, not a `MOVE(from, to)` pair. | Doc 03 sec 3.2 lists `MOVE(from_slot, to_slot)`; the full product over 37 slots is ~1,400 actions. SELECT/PLACE keeps the space at 489 total and mirrors dragging a unit. Cost: a random policy almost never fields anything, since fielding needs two correlated actions. Harmless for a learned policy, but it makes the random baseline weaker than `rl.opponents.RandomPolicy`. | **High** — shapes the whole action space |
| 6b.2 | **Bench→bench moves are excluded from the mask.** | Bench order carries no meaning in TFT, so allowing them would waste an action on a no-op. | Low |
| 6b.3 | **Illegal actions are caught by the env, not propagated** — `info["illegal_action"]`, a configurable `invalid_action_penalty` (default 0), and `strict_actions=True` to re-raise. | Doc 03 sec 2.10 says the engine raises "so the RL wrapper can catch-and-mask illegal actions cleanly" — the engine still raises; the wrapper absorbs. Required for Gymnasium's API checker and for SB3, which both sample the raw action space. | Medium |
| 6b.4 | **`max_actions_per_round = 12`.** | Doc 03 sec 3.2 suggests "up to 8"; 8 proved tight once SELECT/PLACE costs two actions per placement. | Medium — interacts with 6b.1 |
| 6b.5 | **Champions encoded as a normalised index + cost + star + item count** (4 floats/slot), not one-hot. | One-hot over 52 champions × 42 slots would dominate the vector. Doc 03 sec 3.1 flags a set/attention encoder as the natural upgrade. Downside: index proximity implies a similarity that does not exist. | **High** — likely limits learning |
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
| 6c.3 | **Shaping rewards board strength, not just survival.** `0.03 × (board value / reference) + 0.01 × (1 − hp_lost/100)` per round. | The first shaping attempt rewarded survival only, and barely helped: random and do-nothing agents both die on round 13-14, giving stdev 0.0028 (~1%). Board strength is what the agent directly controls and causally drives winning. Measured effect: scripted play earns 1.136 vs random's 0.263, stdev 0.45. Doc 03 sec 3.3 lists trait/item progress as acceptable shaping in the same spirit — but also warns shaping is easy to get subtly wrong, so this needs review for reward-hacking (e.g. hoarding cheap units to inflate board count). | **High** — most likely place to distort the objective |
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
| 7.3 | **Augments.** | Doc 01 sec 8 recommends stubbing for v1. | Milestone 9 |
| 7.4 | **Consumables** (`consumables.json`). | Doc 02 sec 3.10: "safe to stub/skip for v1." | Milestone 9 |
| 7.5 | **Item effects**: Bramble Vest, Infinity Edge crit amp, Rabadon's amp, Dragon's Claw. Their *stats* all apply; only the special behaviour is missing. | Doc 02 sec 2 explicitly allows partial coverage. | Ongoing |
| 7.6 | **Abilities**: `gragas_body_slam`, `ornn_volcanic_rupture`, `spacegroove_regeneration`. Left unimplemented **on purpose** to keep the warn-once-and-no-op path exercised in tests. | doc 02 sec 2, doc 03 sec 2.4 | Ongoing |
| 7.7 | **Mana lock** after casting (real TFT briefly blocks mana gain post-cast). | Not mentioned in doc 01. | Unclear if needed |
| 7.8 | **Shield decay** and damage-type-specific shields — the data model supports both (`Shield.remaining`, `Shield.damage_type`); no current effect uses decay. | doc 01 sec 3.3 mentions both | Ongoing |

---

## 8. Highest-priority items to settle

~~1.1 shop draw weighting~~ ✅ settled — keep `by_copies`.
~~3.1 / 3.2 XP and round-damage tables~~ ✅ settled — revisit at milestone 8.
~~4.4 item effect magnitudes~~ ✅ settled — `params` added.
~~1.2 re-target-every-tick~~ ✅ settled — sticky targeting.
~~6c.10 observation missing selection state~~ ✅ fixed.

~~2.1 config.json schema~~ ✅ settled — stays curated, doc 02 sec 4b added.

Still open:

1. **5.4** whether shields should suppress a tank's damage-mana.
2. **6c.3** board-strength shaping — the most likely place to distort the objective, and needed because the sparse reward gives literally zero gradient (**6c.2**).
3. **6b.5** champion encoding as a scalar index — the likeliest ceiling on learning. **Now more urgent:** the real set has 63 champions, not 13, so the scalar-index encoding is compressing ~5× more distinct units into one float.
4. **6b.1** SELECT/PLACE moves — cheap action space, but two actions per placement.
5. **9.1 / 9.2** star scaling and role mapping (below) — both approximations that feed combat directly.

---

## 9. Milestone 8 — real Set 17 data (2026-08-01)

Calls made while normalising the live CDragon payload. All were authorised as
"your best call … unless further searches disprove those"; where a search
*was* run to check one, the outcome is noted.

| # | Call | Why | Priority |
|---|---|---|---|
| 9.1 | 🟠 **Star scaling derived, not sourced**: health ×1.8/star, attack damage ×1.5/star. | Riot ships one scalar per stat; the multiplier is applied by the game and is absent from the payload. **Checked against the LoL wiki's TFT:Champion page**, which gives AD 100/150/225% and health 100/180/324% — consistent, so the call stands. Still an approximation: real per-champion values can deviate. | **High** — every unit's HP and AD |
| 9.2 | 🟡 **Riot's 13 roles collapsed onto our 5.** `*Carry`→Marksman, `*Reaper`→Assassin, `*Fighter`+`HFighter`→Fighter, `*Caster`+`ADSpecialist`→Caster, `*Tank`→Tank. | Doc 01 sec 3.2 models 5 roles and derives `mana_per_attack` from them, so this feeds combat directly. `ADSpecialist`→Caster is the weakest link (2 units, and "specialist" is about range, not casting). | **High** |
| 9.3 | 🟡 **`role: null` falls back on attack range** (≤1 melee → Fighter, else Caster). | Set 17's Miss Fortune ships no role. Affects exactly one unit. | Low |
| 9.4 | 🟠 **Zero base stats backfilled with the cost-tier median.** | LeBlanc and Riven ship `damage: 0`, which would leave them unable to attack or generate mana. A median re-derives itself each patch instead of baking in a constant, but it is still an invented number. | Medium |
| 9.5 | 🟡 **`mana: 0` treated as "not mana-gated"**, replaced with 100. | Caitlyn ships `mana: 0`; the schema requires a positive pool. Practically inert while no abilities are implemented. | Low |
| 9.6 | 🟡 **Ability variables read from indices 1..3.** | Verified empirically: 151 of 168 varying variables rise monotonically over exactly those indices, and spot checks (Jinx 29/44/70, Briar 120/180/285) match plausible per-star progressions. Index 4 is an unused 4-star slot. | Medium — confident |
| 9.7 | 🟡 **Unmapped item variables never become stats.** Only 10 Riot keys map to modelled stats; the rest fall through to `params`. | Riot mixes units across keys (`AD` is a fraction, `AS`/`CritChance` are percentages), so guessing an unknown key's units would silently corrupt derived stats. Cost: real item effects are largely inert. | Medium |
| 9.8 | 🟡 **Every champion ability gets `effect_id: "ability_<id>"`, unimplemented.** | Preserves the per-star params in the data file and surfaces the gap as one warn-once per champion, while units still auto-attack with correct stats (doc 02 sec 2). Nothing casts yet. | **High** — 63 abilities are no-ops |
| 9.9 | 🟡 **Item pool limited to components + advanced + emblems (65).** Radiant, artifact, consumable and set-mechanic items excluded. | They need mechanics the engine does not model. The 10 components match doc 02 sec 3.4 exactly. | Medium |
| 9.10 | 🟡 **Origin-vs-class curated from doc 02 sec 3.1/3.2**, defaulting to `origin`. | Riot does not publish the split. The doc's 20+15 lists reconcile exactly with the 35 traits fetched. | Low |
| 9.11 | 🟡 **Starter dataset frozen as `tests/fixtures/starter_data/`**, and the existing suite repointed at it. | Its hand-calculated expectations are what make those ~488 tests meaningful; asserting them against patch-varying data would destroy that. Real data is covered separately by `tests/test_real_dataset.py`, which asserts invariants only. | Medium |
