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

~~5.4 shields vs tank damage-mana~~ ✅ settled — both readings in config.
~~6b.5 champion encoding as a scalar index~~ ✅ tested and kept — the "likeliest ceiling on learning" claim did not survive measurement.
~~9.1 star scaling~~ ✅ verified against Bel'Veth's in-game per-star values.
~~11.3 multi-hit abilities~~ ✅ implemented.
~~6c.3 board-strength shaping~~ ✅ settled — was reward-hacking; now potential-based.
~~9.2 role mapping~~ ✅ settled — Specialist role added, two role perks implemented.
~~6b.1 SELECT/PLACE moves~~ ✅ settled — structure is learned perfectly; not the bottleneck.
~~7.3 augments~~ ✅ settled — system built at milestone 9; catalog is synthetic, see section 17.

Still open:

1. **9.8 / 11.2** 29 of 63 abilities remain unimplemented (down from 35) — opaque passive/active splits and champions with several indistinguishable damage variables. See section 16.
2. **17.1** The augment catalog is not Riot data — the Set 17 payload carries no usable generic pool and no tier field. See section 17.
3. ~~**17.5 / 17.6** Full scouting and self-play are unmeasured.~~ ✅ measured in section 19 — scouting is significantly **harmful** (-0.303, t=-2.34), self-play is **inert** (-0.147, CI spans zero).
4. **19.3** PPO contributes nothing measurable over behaviour cloning (+0.147, t=1.12 at n=300; the earlier +0.370 failed to replicate). The 1.17-placement gap to the scripted teacher is the one large, stable, repeatedly-significant fact. See section 19.

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
