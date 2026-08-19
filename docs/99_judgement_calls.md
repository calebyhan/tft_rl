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
- **Part II — Journal** (§9–on). Dated entries, newest last. Each one records a
  question, what was measured, and what changed as a result. Read in order they
  tell the story of the agent going from 8.000 to parity with its teacher.

**Citing an entry.** Use `doc 99 entry N.M` in code comments — for example `doc 99 entry 29.1`. Numbers are **stable**: an entry is
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

**13. A parallel evaluation reads its code from disk, not from memory.** Every
long measurement here is a `spawn` pool, so the working tree is shared mutable
state for its whole duration. A mutation test run against a live evaluation
spliced two different policies into one table, and the contaminated arms
printed plausible numbers supporting a tidy and entirely false story. Freeze
the tree, or fingerprint it between arms. (§68.4)

**14. Validate the model before optimising against it.** Seventy entries, four
experiment batches and an entire RL programme were tuned against an economy
whose field could not spend its gold — a defect one profile script and two web
searches exposed, which reframed three of the last five entries. "The data
checks out" is a different claim from "the simulation behaves like the game",
and only the second one licenses treating a measured ceiling as real. (§70)

**15. A `spawn` pool re-imports the module it was launched from.** A helper
script without an `if __name__ == "__main__"` guard fork-bombed for 90 minutes
and wrote a 745 MB log of `RuntimeError` while reporting nothing. Silence reads
identically to slowness — check the log's *size*, not just its tail. (§72.4)

**16. When imitation is saturated, the ceiling is the teacher, not the method.**
"Imitation is exhausted" was true and was read as *this line of work is
finished*; it meant *this teacher is finished*. Nine entries of optimisation
followed. Improving the teacher moved the agent 0.543 in one training run —
larger than anything the RL programme ever produced. (§75.2)

**17. A stochastic teacher caps imitation at its own self-agreement.**
`best_move` sampled its candidates from a free-running RNG, so one board mapped
to many labels: five streams gave five different answers on 55% of states, and
the search agreed with itself 38.7% of the time. Cloning a one-to-many map
learns the marginal — a blur over many good moves, which is not a good move.
The teacher gained 0.330 and the clone gained nothing. Before reading an
agreement rate as a failure to fit, check what the teacher's agreement with
*itself* is. (§79.3)

**18. Agreement and placement can decouple completely.** DAgger raised
student-state agreement 25-29 points on the two decision kinds that were
collapsing, and placement moved -0.083 (t=-0.57). An imitation metric improving
is not evidence the policy improved, even when the metric was correctly
diagnosing the problem. Measure the objective. (§81.2)

**19. The clone noise floor is ~0.14 placement, so one seed resolves
nothing below ~0.4.** Two arms differing only in one observation feature read
-0.227, +0.110, +0.067 across three seeds -- mean -0.017. The favourable seed
alone would have been written up as promising. This applies to anything
requiring *retraining*; measurements that re-evaluate one fixed policy on
shared episode seeds are unaffected. (§83.1, §83.4)

**20. A per-action learning signal needs a *better* comparator, not just
a counterfactual.** Substituting the teacher's action moved placement -0.194
(t=-2.28); substituting an alternative from the clone's own peaked distribution
moved nothing across 1098 samples. The same measurement answers "is this action
good" only when the alternative is meaningfully different. (§91.2)

**21. A defect being real is not evidence it is the binding constraint.**
Shaping really did concentrate 64.6x of its credit on one action kind, and the
per-action fix really did cut that to 12.0x. The policy collapsed exactly as
before. Validating that a fix does what it claims is necessary and says nothing
about whether it matters — the objective still has to be measured. (§93.3)

**22. A reliability statistic is meaningless without the direction it
points.** Perturbations at sigma 0.4 ranked with r=0.99 across disjoint seed
blocks -- a near-perfect, entirely reproducible ranking of how badly each one
*broke* the policy. The probe's verdict column read `followable`. Reproducible
and useful are different properties, and only one of them is what a search
climbs. (§94.3)

**23. A rate measured over minutes need not hold over hours.** A 55k-step
probe measured 184 env steps/sec; the 5M-step run it was used to project came
in at 123 -- 33% short over 11 hours. Project long runs from long measurements.
(§96.4)

**24. An external reference has its own spread, and it must be measured
before any gap against it is quoted.** The engine appeared to under-price a
3-star by 0.125 placement. Splitting the *same* reference sample by patch moved
that statistic 0.098 -- so the finding was the size of drift inside the
comparator, and not assertable. This is lesson 2 one level up: there, a rate
needed its achievable maximum; here, a discrepancy needs the reference's own
variance. Both cost one command. The sequel matters as much: disaggregating by
cost tier, the *same* reference was stable to 0.002 across two rank bands and
four patches, and the engine's error there was larger and opposite in sign per
tier. A reference too noisy to support a claim in aggregate can be precise
enough in its parts. (§97.6, §97.7)

**25. ~~An intervention that moves behaviour toward the reference and makes
performance worse is evidence about the simulator.~~ WITHDRAWN by §103.1**,
one hour after it was written. It generalised from §102.4, and §103 showed the
0.343 loss was the *implementation* -- protecting every progressing copy
congested the bench -- not the 3-star. A selective version costs nothing and
still 3-stars. The lesson as written would have licensed skipping the very
check that refuted it. The sound residue: an intervention is only evidence
about the model once it is a *good* implementation of the behaviour, which is
lesson 21 restated. Kept as a record of a generalisation made too fast.

**26. Relational features close a gap when the teacher's rule is a *function
of the relation*. A teacher whose rule is a *simulation* has no such
features.** Every relational widening that worked supplied a quantity the rule
takes as an argument: `owned` and `synergy` for BUY, `copies` for SELL, the
star and cost ranks for SELECT. Supply the argument and the label becomes
nearly trivial — 91.2%, 100%, 100% on probes. `best_swap` is different in kind:
its answer is the output of three combat trials against two boards, so no set
of scoutable quantities determines it, and the one feature that would — the
simulated margin — is the teacher's computation rather than a fact about the
board. 41 hand-built relational floats moved the probe 2.5 points of a 32-point
deficit. **Before widening an observation, check that the teacher's rule is a
function of something, and not a procedure.** If it is a procedure, the student
cannot be given its answer without being given its policy. (§110.3, §109.2)

**27. When a total is off, read the rows before theorising about the total.**
Four entries (115–117) chased a uniform 3-star shortfall that the per-cost
table had already localised to one archetype. Then three more (120–122)
theorised about why a seat rolls 29 times instead of 91 — the floor, the
competing buys — and both answers were wrong. The per-*round* table settled it
in one run: the seat holds 26g at 5-1 and 9g every round after, because rolling
to zero forfeits the interest that was most of its income. A total is a sum
over a mechanism that may not be uniform, and averaging is exactly the
operation that hides which row is doing the work. **The corollary for tests:
when a mutation survives, suspect the measurement aggregates two mechanisms
before adding another case** — `test_roll_buys` passed against a mutation
that broke board-building until the buy counts were split by phase. (§123.2,
§118.3, §122.4)

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
| 67 | 08-06 | Board size dominates; star scaling is correct; slow-roll test was crude | ⚠️ resolved by 68 |
| 68 | 08-06 | Slow-rolling fails when specified correctly; 3-stars need targeting | ⚠️ 98.5 |
| 69 | 08-06 | 3-stars are unreachable at the default action budget by any policy | ⚠️ refined by 70 |
| 70 | 08-06 | External validation: data is correct, but no policy can spend its gold | ✅ |
| 71 | 08-06 | Real economy archetypes; field and action budget changed; **all prior numbers void** | ✅ |
| 72 | 08-06 | The teacher's edge was 74% opponent weakness; a real economy recovers half | ⚠️ table withdrawn by 73 |
| 73 | 08-06 | The field was not a fair lobby; targeting is what makes reroll work | ✅ |
| 74 | 08-06 | **The teacher is below parity (4.823 vs 4.500); its 3.030 had the sign wrong** | ✅ |
| 75 | 08-06 | **A better teacher transmits: 89% of it reaches the clone (-0.543, t=-3.64)** | ✅ |
| 76 | 08-06 | Combat prices stars correctly; reroll's shortfall is a gold budget | ✅ |
| 77 | 08-06 | Unsourceable combat constants: 3 of 4 shown not to matter | ✅ |
| 78 | 08-06 | Repositioning is worth -0.33; teacher now 0.617 above parity | ✅ |
| 79 | 08-07 | **Search doesn't transmit: labels were fixable, the observation is the wall** | ✅ |
| 80 | 08-07 | The incumbent placement rule beats both alternatives; spacing is under-priced | ✅ |
| 81 | 08-07 | **DAgger closes the distribution gap and buys nothing; imitation is exhausted** | ✅ |
| 82 | 08-07 | **The disagreement that costs placement is positional; SELL is 38% and inert** | ✅ |
| 83 | 08-07 | **Attack range does nothing; the clone noise floor is 0.14, not 0.074** | ✅ |
| 84 | 08-07 | PICK_OFFERING's -0.405 was a thin cell; -0.133 at n=631 | ✅ |
| 85 | 08-07 | Reroll gets 30 of the 58 rolls it needs; not the action budget | ⚠️ cause found in 86 |
| 86 | 08-07 | **The teacher never implemented reroll targeting: slowroll6 -1.210** | ✅ |
| 87 | 08-07 | Roll floor is not a lever; behavioural guard for EconStrategy fields | ✅ |
| 88 | 08-07 | **Level curve is a local optimum; every economy lever now measured** | ✅ |
| 89 | 08-08 | **PPO still collapses to 8.000 unanchored; anchored it cannot move** | ✅ |
| 90 | 08-08 | **The drift is END_PLANNING up / BUY down; REROLL is at the mean** | ✅ |
| 91 | 08-08 | **Single actions do not measurably move placement; PPO fits noise** | ✅ |
| 92 | 08-08 | **Shaping gives END_PLANNING ~100x the credit of board-building actions** | ✅ |
| 93 | 08-08 | **Fixing the credit concentration does not stop the collapse** | ✅ |
| 94 | 08-08 | **Flat fitness landscape then a cliff; ES viable only at 3-6 days of compute** | ✅ |
| 95 | 08-08 | **Every RL run saw ~378 games; DummyVecEnv was serial; ~2.5x reachable** | ⚠️ |
| 96 | 08-09 | **33x the data changes nothing; 95.1 refuted; every learning method now exhausted** | ✅ |

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

> **Every row above is void as of [§98](#98-the-carousel-fix-elimination-timing-closes-a-late-game-stalemate-appears-08-09).** The carousel schedule now covers
> stages 5-9, which removes two combat rounds per game. No figure measured
> before 08-09 is comparable to one measured after it. **Re-derived so far:**
> the econ archetype table, unmoved ([§100](#100-the-reroll-mispricing-survives-both-fixes-and-86s-table-reproduces-exactly-08-09)), and the agent baseline
> ([§104](#104-the-agent-baseline-re-derived-post-98-08-09)): clone **4.900**, teacher **4.750** on the same 60 seeds.

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

> **Re-diagnosed by entry 70.** The observation is right and the cause is
> wrong. The sink exists and is correctly priced against real TFT; what is
> missing is any policy able to *reach* it -- `GreedyPolicy` buys XP once per
> round, so 60 XP of levelling takes 10 rounds however much gold is banked.

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

> **RESOLVED by entry 68.** The correctly-specified arm was run with a new
> `level_cap` knob: it fails too (cap7+roll@6 = 4.823 against control 3.030).
> This entry's *arm* was mis-specified and its *conclusion* was right. 67.2's
> "does not establish that reroll strategies are non-viable here" is now
> established -- they are non-viable, and entry 68.3 gives the reason.

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

---

## 68. Slow-rolling, specified correctly, fails; the reason is targeting (08-06)

Entry 67 is flagged ⚠️ because the arm it called "slow roll" was
`level_at_gold=80`, which starves levelling from stage 1 and tests *never
level*. Real slow-rolling levels normally to 6-7, **stops there**, and rolls the
surplus. Separating those needs a knob that caps the destination without
delaying the journey, and `scripted_policy` had none -- so `level_cap` was
added (stops *buying* XP; passive XP still accrues at 2/round, as in real TFT,
where a slow-roller stops paying for levels rather than stops receiving them).

`scripts/slowroll_ab.py`, 300 shared seeds, teacher configuration
(`sell_bench` plus the three expert flags). No training seed, so no replication
caveat (entry 65). Both anchors reproduce doc 99's stored values exactly, which
is what licenses reading the rest.

| arm | placement | vs control | t |
|---|---|---|---|
| control | **3.030** | -- | -- |
| roll@6 (entry 66.1's arm) | **3.257** | +0.227 | +1.96 |
| cap8 | 3.583 | +0.553 | +10.08 |
| cap8+roll@7 | 3.583 | +0.553 | +6.03 |
| cap7 | 4.760 | +1.730 | +19.40 |
| cap7+roll@6 | 4.823 | +1.793 | +15.31 |

### 68.1 The conjunction fails, and entry 67's conclusion survives its bad arm

**Rolling on top of a cap buys nothing.** cap8 3.583 -> cap8+roll@7 3.583 is
+0.000; cap7 4.760 -> cap7+roll@6 4.823 is +0.063, the wrong way. The cap costs
+0.553 at level 8 and +1.730 at level 7, monotone in slots, and rolling
recovers none of it.

Entry 67's ⚠️ resolves: its arm was mis-specified and its **conclusion was
right anyway**. Board size dominates. The question it left open -- whether
reroll strategies are viable here -- is now answered no, on the arm it said was
needed.

### 68.2 The action budget was a real confound, and not the cause

`DEFAULT_MAX_ACTIONS_PER_ROUND = 12` caps the agent seat's actions per round
across buying, selling, placing *and* rolling, with reroll last in priority --
while the seven `GreedyPolicy` bots plan a whole phase at once and are **not
capped at all**. Real slow-rolling spends 40-60 rolls in a single round. At 12
the roll arms managed 5-10 rolls per *game*, so entry 66.3's "gold has no sink"
was partly a fact about the wrapper.

Raising it to 60 (`/a60`) is the discriminating test. Three outcomes were named
before the run: the budget is the cause; conversion is blocked elsewhere; or
rolling is genuinely bad here. **The third fired.**

| arm | placement | vs control | t | rolls/game | r28 gold | 2-star |
|---|---|---|---|---|---|---|
| control | 3.030 | -- | -- | 0.0 | 35.9 | 46.4% |
| control/a60 | 2.890 | -0.140 | -1.45 | 0.0 | 37.0 | 46.6% |
| roll@6 | 3.257 | +0.227 | +1.96 | 5.2 | 35.7 | 50.3% |
| **roll@6/a60** | **4.687** | +1.657 | +11.89 | **40.1** | 29.7 | **71.8%** |
| cap7+roll@6/a60 | 4.820 | +1.790 | +12.79 | 44.8 | 53.3 | 71.0% |

The budget is not handicapping the teacher: control/a60 gains only 0.140 at
t=-1.45, under the bar. But given a real budget, **rolling gets much worse** --
3.257 -> 4.687 as rolls go 5.2 -> 40.1. The gold does drain and the units do
improve: 2-star runs 46.4% -> 71.8%. Rolling converts. It simply loses more in
board slots (8.8 -> 7.4) and levels (8.1 -> 7.0) than it gains in stars, because
gold spent rolling is gold not spent on XP.

### 68.3 Why 3-stars never appear: the teacher does not target

> **Half refined by entry 69.** Targeting is necessary and **not sufficient**.
> At the default action budget the shop never offers a committed champion more
> than ~6.4 copies of the 9 needed, so no shopping policy reaches a 3-star.
> This section's "the missing mechanism is a *policy* one" is wrong as stated:
> the binding constraint is `max_actions_per_round`.

**3-star rate is 0.0% in every arm, including at 44.8 rolls per game.** The
arithmetic says it cannot be otherwise. At level 7 the 1-cost tier is 19% over
14 one-cost champions, so a *specific* 1-cost arrives 0.068 times per roll:

    45 rolls x 5 slots x (0.19 / 14) = 3.1 copies

against the **9** a 3-star needs. At level 6 (30% 1-cost) it is 4.8 -- still
short. Real slow-rolling clears the bar by rolling 150-200 times across several
rounds at low level, which no budget tested here approaches.

More basic than the volume: the teacher shops on `(owned, synergy, cost)` and
so **spreads purchases across champions**. A reroll comp commits to two or
three specific units. Without targeting, copies never concentrate on anything,
and the 3.1 above is an overestimate of what actually happens. The missing
mechanism is a *policy* one, not an engine or data one -- entry 67.1 already
established star scaling is exactly right, and 66's shop odds, pool sizes and
xp table all check out.

### 68.4 A contaminated measurement, and how it printed a plausible number

The first run of this table was **invalid and is not reported above**. Mutation
tests that rewrite `rl/evaluate.py` on disk were run *while* the evaluation was
live. `evaluate_scripted_parallel` uses `spawn`, so each arm's workers
re-import from disk: two arms were measured against deliberately broken code.

It did not look wrong. It read cap7+roll@6 = 3.693 and cap8 = 3.030, against
clean values of **4.823** and **3.583** -- and 3.693 supported a tidy story
("rolling recovers 62% of the cap's cost") that is entirely an artefact. The
contamination was caught only because a single arm was re-run by hand and
disagreed.

`slowroll_ab.py` now hashes every `engine/` and `rl/` source file between arms
and aborts if the tree moves. The clean runs print their fingerprint
(`9c12674de54a`).

*Lesson.* **A parallel evaluation reads its code from disk, not from memory.**
Every long-running measurement in this project is a `spawn` pool, and the
working tree is shared mutable state for the whole duration of it. Editing
source during a run is not a style problem; it silently splices two different
policies into one table, under one set of column headings.

*Lesson (restated from 60.4, and it held).* **Name the possible outcomes before
the run finishes.** Three were named for the budget test and the least
convenient one fired. Had they not been written down, "rolling converts gold
into 2-stars" (true, and visible in the table) was available as a success story
for an arm that placed 1.4 worse.

### 68.5 Still open

- Whether a *targeting* teacher -- commit to 2-3 champions, roll for those --
  reaches 3-stars and whether that beats 3.030. This is the arm 68.3 implies
  and it has not been run.
- Whether `max_actions_per_round=12` should stay. It costs the teacher only
  0.140 (t=-1.45), but it is an asymmetry the opponents do not face, and it
  bounds any policy that would want to roll.
- External validation against real TFT statistics, still never done.

---

## 69. The 3-star ceiling is the action budget, not the shop (08-06)

68.5 named a targeting teacher as the next arm. Before building it, measure
what it would be working against -- lesson 2, *a rate is uninterpretable
without its achievable maximum*.

**Copies offered is a hard upper bound on copies obtainable.** A policy can at
best buy every copy the shop shows it, so if the most-offered champion arrives
fewer than the **9** a 3-star needs, targeting is closed before it is written.
`scripts/copy_ceiling.py` counts arrivals (a slot going X -> Y is one arrival of
Y; buying empties a slot and never counts), in live games where seven bots draw
from the same `SharedPool`.

### 69.1 The first metric measured hindsight, not policy

The obvious statistic -- copies of the best champion over a whole game -- read
**8.03** for the teacher, near the 9 needed, and looked like a green light. It
is a max over ~63 champions **chosen after seeing the outcome**. A reroll comp
must commit before it knows which champion the shop will favour.

`commit@K` is the honest version: take the champion leading at round `K`, then
bank its arrivals for the whole game. n=40:

| arm | rolls/game | hindsight | **c@6** | c@10 | c@14 |
|---|---|---|---|---|---|
| a12 (the default) | 0.0 | 8.03 | **6.30** | 6.90 | 7.35 |
| a12+roll@6 | 5.4 | 8.65 | **6.45** | 6.70 | 7.20 |
| a12+cap7 | 0.0 | 8.03 | **6.35** | 6.88 | 7.30 |
| a12+cap7+roll@6 | 10.7 | 8.88 | **6.78** | 7.50 | 7.60 |
| a60 | 0.0 | 7.92 | **6.50** | 6.70 | 7.17 |
| a60+roll@6 | 39.4 | 14.55 | **9.90** | 10.20 | 10.95 |
| a60+cap7+roll@6 | 43.1 | 15.75 | **10.53** | 11.03 | 11.90 |

Hindsight overstates the honest ceiling by **1.7 to 5.2 copies**, and it is the
difference between "9 is reachable" and "9 is not". Reporting it would have
justified building the targeting teacher on a number that measures the
measurement.

### 69.2 The binding constraint is `max_actions_per_round`

> **Refined by entry 70.** True of the *agent*, incomplete as stated. The seven
> opponents are throttled harder by a different mechanism -- `GreedyPolicy`
> buys XP and rerolls once per round, hard-coded -- so this section's ceilings
> were measured in a configuration where no seat can spend its gold. They
> describe this setup, not the engine.

At the default budget of 12, **every** arm sits at c@6 = 6.3-6.8, against 9.
Capping levels does not move it (6.30 -> 6.78) and neither does rolling
(6.30 -> 6.45), because at 12 actions per round -- shared across buying,
selling, placing and rolling, with reroll last in priority -- the policy
manages 5-10 rolls per *game*.

At 60 it manages 39-43 rolls and c@6 clears 9 (**9.90**, **10.53**).

**The budget alone does nothing**, which is the control that makes this a
conjunction rather than a single cause: `a60` without rolling sits at c@6 =
6.50, indistinguishable from `a12`'s 6.30. Extra actions only matter to a
policy that spends them on the shop. So:

> **3-stars are unreachable at the default action budget by any shopping
> policy whatsoever, and become marginally reachable at 5x the budget.**

This reframes entries 66-68. "Gold has no sink" (66.3), "rolling converts
nothing" (68.1) and "the teacher does not target" (68.3) are all downstream of
one wrapper constant. 68.3 proposed targeting as *the* missing mechanism; that
was half right -- targeting is necessary and **not sufficient**, and at a12 it
is not even sufficient in principle.

`DEFAULT_MAX_ACTIONS_PER_ROUND = 12` is also an asymmetry the opposition does
not face: `GreedyPolicy` plans a whole phase at once and is uncapped. It costs
the teacher little directly (control at 60 actions gains only 0.140, t=-1.45,
entry 68.2) precisely because the teacher does not roll -- it is invisible until
a policy wants the sink.

### 69.3 What this does and does not license

Marginal means marginal: c@6 = 9.90 against 9 needed is a *mean*, so roughly
half of games fall short, and it assumes **perfect conversion** -- buying every
single copy offered, which no policy achieves under gold and bench limits.

What the current teacher converts, as peak copies held of one champion while
alive (n=40; measured at a checkpoint, **not** at episode end, where a dead seat
holds nothing and reads a vacuous zero):

| arm | ceiling c@6 | teacher peak | share |
|---|---|---|---|
| a12 | 6.30 | 4.65 | 74% |
| a12+roll@6 | 6.45 | 4.70 | 73% |
| a60 | 6.50 | 4.65 | 72% |
| a60+roll@6 | 9.90 | 5.70 | 58% |

The non-targeting teacher already captures ~73% of the ceiling; at a60 the
shop outruns it and the share falls to 58%. For a 3-star at a60, a targeting
policy must reach **9 of 9.90 = 91%** of the ceiling. Concentrating purchases
on one champion is exactly what raises that share, so the arm is not hopeless
-- but it has to more than close a 58% -> 91% gap, on a mean that only just
clears the threshold.

So the targeting arm of 68.5 is **not closed, but it is conditional**: it can
only pay at a raised action budget, and raising the budget is an engine
decision, not a tuning one.

*Lesson.* **A ceiling computed with hindsight is not a ceiling.** The selection
step -- max over 63 champions -- was inside the statistic rather than inside the
policy. The fix was to make the commitment explicit and early, which is what the
strategy being measured actually requires. Same shape as 28.1's 90.7%: both
measured how good the *best* option looked rather than how good the *chosen*
one was.

### 69.4 Still open

- Whether to raise `max_actions_per_round`. It gates the entire economy and is
  an asymmetry the bots do not face, but changing it invalidates every baseline
  in this log (lesson 12).
- The targeting teacher, now conditional on the above.
- External validation against real TFT statistics, still never done.

---

## 70. External validation: the data is right, the policies cannot spend (08-06)

69.4's open item, and the one thing never done in 70 entries: **every ceiling in
this log was measured against the engine's own economy.** Entries 66-69 concluded
gold has no sink, 3-stars never occur, and the action budget gates everything --
all judged against the simulator itself.

`scripts/engine_profile.py` emits the engine's side keyed by stage-round label,
the form real TFT benchmarks are published in. Eight `GreedyPolicy` seats
driving `Match` **directly, not through the RL wrapper**, so
`max_actions_per_round` does not apply -- profiling through the wrapper would
measure the wrapper and call it the engine.

### 70.1 The economy tables are externally correct

The LoL Wiki's XP table against `config.json`:

| level -> next | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|
| wiki | 2 | 6 | 10 | 20 | 36 | 60 | 68 | 68 |
| engine | 2 | 6 | 10 | 20 | 36 | 60 | 68 | 68 |

Exact. So are 4 gold -> 4 XP, 2 passive XP per round, and the 50-gold interest
cap. Entry 66 checked these internally and called the data fine; that now has
an external source behind it. 67.1's star scaling (3.24x health, 2.25x AD) was
already verified. **The data is not the problem, and this closes that
hypothesis properly rather than by assertion.**

### 70.2 The divergence, quantified

n=60, living players only:

| stage-round | engine level | real TFT | engine gold |
|---|---|---|---|
| 3-2 | 5.67 | 6 | 46.9 |
| 3-5 | 6.01 | 7 | 57.9 |
| 4-1 | 6.67 | 7-8 | 68.1 |
| 4-2 | 6.97 | 8 | 71.5 |
| 5-1 | 7.01 | 8-9 | 99.4 |
| 5-7 | 8.00 | 9 | 122.0 |

The field runs **~1 level behind from stage 3 and 1.5-2 behind by stage 5, on
roughly twice the gold**. Level 8 arrives at 5-7 against real TFT's 4-1/4-2 --
about ten rounds late. Gold never stops climbing: 145 by 6-4, against real TFT
where it sits near the 50 interest cap because everything above it is spent.

**3-stars: 1 game in 60 (1.7%)**, first appearing at 6-2. In real TFT a 3-star
1-cost is routine by stage 4-5.

### 70.3 The cause: one purchase per round

`GreedyPolicy.plan` calls `player.buy_xp()` **once** and `player.reroll()`
**once** per planning phase. No loops. So a bot gains at most 4 purchased + 2
passive = **6 XP per round** no matter how much gold it holds.

Level 7 -> 8 costs 60 XP, so it takes **10 rounds** -- a prediction the profile
confirms directly: level sits at 6.99 at 4-3 and reaches 8.00 at 5-7, which is
11 rounds, while gold climbs 75.1 -> 122.0. A real player holding 100 gold makes
15 purchases and levels in **one** round. That is a ~10x throttle, and it
applies to all eight seats.

### 70.4 What this overturns

**"Gold has no sink" (66.3) is wrong as diagnosed.** The sink exists and is
correctly priced; no policy in this project can *reach* it. There are two
independent throttles, and entry 69 found only one:

| | mechanism | applies to |
|---|---|---|
| opponents | 1 XP + 1 reroll per round, hard-coded | all 7 bot seats |
| agent | `max_actions_per_round = 12` | the RL seat |

69's "the action budget gates the entire economy" was right about the agent and
**missed that the opposition field is throttled harder, by a different
mechanism**. So 69's c@6 ceiling of ~6.3 copies was measured in a world where
nobody can spend -- which is neither real TFT nor what the data describes. That
ceiling stands as a fact about this configuration and **not** as a fact about
the engine.

**A consequence worth stating before it is measured.** `scripted_policy` acts
through the action space and *can* buy XP repeatedly within its 12 actions, so
the teacher levels faster than the field it plays against. Part of the teacher's
3.030 may therefore be "it can spend and they cannot" rather than better play --
which would sit consistently with entry 56, where the teacher fell to 4.387
against a stronger field. Untested, and it is the discriminating question for
every teacher-relative number in this log.

*Lesson.* **Validate the model before optimising against it.** Seventy entries,
four batches of experiments and an entire RL programme were tuned against an
economy whose field could not spend its gold. The check cost one profile script
and two web searches, and it reframed three of the last five entries. "The data
checks out" (66) was true and not the same claim as "the simulation behaves like
the game".

### 70.5 Still open

- Whether to let `GreedyPolicy` loop its purchases. It is a small change that
  invalidates **every baseline in this log** (lesson 12), so it is a deliberate
  call, not a fix to slip in.
- Same question for `max_actions_per_round = 12`.
- How much of the teacher's edge is the opponents' throttle (70.4).
- Combat fidelity is still unvalidated; this entry covers the economy only.

Sources: [LoL Wiki XP table](https://wiki.leagueoflegends.com/en-us/TFT:Experience),
[Mobalytics standard leveling](https://mobalytics.gg/blog/tft/guide-standard-leveling-strategy/),
[Mobalytics leveling guide](https://mobalytics.gg/blog/tft/leveling-guide/).

---

## 71. Real economies, and the field the agent had been training against (08-06)

Entry 70 found the opposition ~1 level behind real TFT on twice the gold,
because `GreedyPolicy.plan` bought XP **once** per round. Direction given: the
goal is an RL model that can play *real* TFT, so fidelity is the objective --
take whatever gives the highest accuracy going forward.

### 71.1 The policy's economics were right; its execution was not

`_spendable` already computed the interest floor correctly: interest is +1 per
10 gold **capped at 50**, so gold above 50 earns nothing and holding it is
waste. At 145 gold the old policy was *willing* to spend 95. It could spend 6 --
one XP purchase (4) and one reroll (2) per round.

So 66.3's "gold has no sink" was never an economy-design problem and 70.3's
"one purchase per round" is the whole of it. The fix is loops, not new
reasoning.

### 71.2 Four archetypes, and what each produces

`EconStrategy` carries `level_targets` (round label -> level, the form real
benchmarks are published in) and `roll_floors` (round -> gold to spend down
to). n=20 per arm, eight identical seats, real dataset:

| archetype | 3-2 | 4-1 | 4-5 | gold shape | 3-star games |
|---|---|---|---|---|---|
| real TFT | 6 | 7-8 | 8 | ~50, dips on roll-down | routine by stage 4-5 |
| **standard** | 6.00 | 7.00 | 7.98 | 47 -> **19** at 4-5 -> rebuilds | 10% |
| **fast8** | 6.00 | 7.41 | 7.93 | 47 -> **10.8** at 4-1 -> rebuilds | **0%** |
| **slowroll6** | 6.00 | 6.00 | 6.00 | holds ~50, rolls surplus | **30%** |
| **hyperroll** | 5.00 | 5.99 | 6.00 | **12.4** by 3-2 | 15% |
| legacy | 5.67 | 6.67 | ~7 | 47 -> 145 by 6-4 | 1.7% |

`standard` reproduces the published curve almost exactly. The ordering on
3-stars is the one real TFT has: reroll comps produce them (30%, 15%), fast 8
does not (0%), and the first ones appear in stage 4 rather than 6-2.

**A design error caught by the numbers.** The first archetype set had `fast8`
levelling *slower* than `standard` at 4-1, which is backwards for a strategy
whose whole point is being level 8 there. `roll_floors` applied from a round
*onward*, so `fast8` rolled to 10 gold every round forever and never earned
interest again. Real roll-down is once, then rebuild. `standard`/`fast8` now
restore the save floor the round after their breakpoint; `slowroll6`/
`hyperroll` keep a standing floor because continuous surplus-rolling is what
those archetypes actually do.

### 71.3 Two defaults changed

**The field is now a mixed lobby** -- 3 standard, 2 fast8, 2 slowroll6, 1
hyperroll. Eight identical bots is not a lobby, and a single-archetype field
lets a learned policy overfit to one opponent model, which this project has
never controlled for.

**`DEFAULT_MAX_ACTIONS_PER_ROUND` 12 -> 50.** Entry 69 established 12
forecloses every reroll strategy; with the opponents now genuinely rolling, it
also made the agent the only throttled seat. It is a **cap, not a cost** --
`END_PLANNING` advances the round whatever the budget, so a policy that
finishes early pays nothing. An earlier claim in this session that raising it
costs ~5x training time was wrong.

### 71.4 What this invalidates

**Every number in this log.** The teacher's 3.030, imitation's ~3.40 plateau,
66-70's ceilings, the arc table -- all measured against a field that could not
spend its gold and an agent that could not roll. Lesson 12 says re-measure both
arms together; here there is no "both arms", because the world changed. The
measurement history restarts at this entry.

That is the correct trade for the stated goal and it is not a small one: it
discards roughly 70 entries of calibration.

### 71.5 Still open

- Re-measure the teacher and the arc against the new field. Nothing downstream
  means anything until this is done.
- Whether `slowroll6` at 30% and the first 3-star in stage 4 is *close enough*
  to real TFT, or still low. No external rate was sourced for this.
- `hyperroll` produces fewer 3-stars (15%) than `slowroll6` (30%) despite being
  the dedicated 1-cost reroll strategy -- its roll floor is restored at 3-2,
  which likely stops it too early. Archetype tuning, not a mechanism problem.
- **Combat fidelity is entirely unvalidated** and is now the largest gap.
  `config.unverified` already flags `armor_mitigation_constant`,
  `sudden_death_*` and the movement/projectile speeds as approximations.

---

## 72. What the teacher's 3.030 was actually measuring (08-06)

Entry 71 gave the field real economies and declared every prior number void.
This is the re-measure. All arms 300 shared seeds against the new mixed field,
no training seed, so no replication caveat (entry 65).

### 72.1 Most of the teacher's edge was opponent weakness

Parity is 4.500 by construction. The teacher's distance below it:

| world | teacher | edge over parity |
|---|---|---|
| old field (one purchase/round) | 3.030 | **1.470** |
| real economies, archetypes capped at level 8 | 3.883 | 0.617 |
| real economies, archetypes levelling to 9-10 | **4.120** | **0.380** |

**The edge fell by 74%.** 70.4 predicted this before it was measured -- "part of
the teacher's 3.030 may be *it can spend and they cannot*" -- and named entry
56's 4.387-against-a-stronger-field as the corroborating evidence. It was right.

Every imitation result in this log was cloning a policy that is barely better
than average against opponents who play the economy properly.

### 72.2 A real economy recovers about half of it

> **WITHDRAWN by entry 73.** These arms were measured against a field whose
> `slowroll6`/`hyperroll` seats placed 5.293 and 6.107 -- three of eight seats
> were free wins. The direction ("a real economy beats no economy") is
> re-measured in 73.6's follow-up; the numbers below are not usable.

The teacher had no economic plan at all -- "buy XP whenever gold >= 30" -- while
the field ran published strategies:

| teacher econ | placement | vs incumbent | t |
|---|---|---|---|
| fast8 | **3.723** | -0.397 | -3.29 |
| standard | 3.807 | -0.313 | -2.46 |
| no-econ (incumbent) | 4.120 | -- | -- |
| slowroll6 | 5.293 | +1.173 | +8.47 |
| hyperroll | 5.843 | +1.723 | +11.58 |

**`fast8` and `standard` are indistinguishable from each other**: -0.083 at
t=-0.71, better in 118 games and worse in 110. The finding is "a real economy
beats no economy" (t=-2.46 to -3.29), *not* that fast 8 is the best plan. Either
is a defensible teacher; `standard` tracks the published curve most closely.

### 72.3 The reroll archetypes are good opponents and bad agents

`slowroll6` and `hyperroll` are catastrophic in the agent seat (+1.173,
+1.723) while being perfectly reasonable in opponent seats -- 71.2 measured
them producing 30% and 15% 3-star games. The mechanism is entry 67's, holding
across three worlds now: rolling costs levels, levels cost board slots, and
slots decide fights. Entry 68's conclusion survives the world change intact,
which is stronger evidence than the original measurement was.

**Still open:** whether the `slowroll6`/`hyperroll` *seats* also place badly
inside a game. Per-seat placement by archetype has not been measured, and if
they do place badly the mixed field is a lobby of two weak archetypes, which
would flatter the agent.

### 72.4 A level cap that was mine, not the game's

The first archetype set stopped at level 8. Real TFT reaches 9 from ~5-5 and
`max_level` is 10, and in this engine board size dominates -- so a plan capping
at 8 forfeits slots to a policy that simply keeps levelling. An n=8 spot check
showed every econ arm losing, which was measuring that gap rather than the
economies. All four now carry a late 9 and a 10 where the economy supports it.
That change moved the incumbent 3.883 -> 4.120, because it strengthened the
opponents.

*Lesson.* **A `spawn` pool re-imports the module it was launched from.** The
first version of 72.2 was a scratchpad script with no `if __name__ ==
"__main__"` guard: every worker re-ran the module and spawned more workers. It
burned 90 minutes and wrote a **745 MB** log of `RuntimeError` while reporting
nothing. Silence was diagnosed as slowness for over an hour because the log's
*size* was never checked -- and lesson 13, about `spawn` reading from disk, had
been written the same day.

---

## 73. The field was not a lobby, and three fixes to get there (08-06)

Entry 72.3 left one open item: whether `slowroll6` and `hyperroll`, catastrophic
in the agent seat, also place badly *inside* a game. If so the default field is
a lobby with weak seats -- which inflates every agent number measured against
it, the exact defect 72.1 had just found in the *old* field.

`scripts/field_check.py` measures placement per archetype with eight bot seats
and no agent, so 4.500 is parity by arithmetic and the spread is the fairness
metric.

### 73.1 It was not a lobby

| archetype | seats | placement |
|---|---|---|
| fast8 | 2 | 3.823 |
| standard | 3 | 3.887 |
| slowroll6 | 2 | **5.293** |
| hyperroll | 1 | **6.107** |

**Spread 2.283.** Three of eight seats were free wins, so entry 72's teacher
figures (3.723 / 4.120) were measured against a weak field and are withdrawn.

### 73.2 Fix 1: the policy could not buy what it rolled for

`_buy_phase` gated every purchase at `_spendable` = gold - 50. A slow-roller
rolls down to 50, hits the copy it was rolling for, and **cannot afford it** --
it pays to search and then refuses the result. The interest floor governs
*rolling*, not *buying*.

Real bug, fixed in `GreedyPolicy` and `scripted_policy`. Effect on placement:
**none** (spread 2.283 -> 2.309). Rather than accept the convenient conclusion
that reroll is non-viable, the fix was checked for effect: `slowroll6` went from
its prior behaviour to **46.5 rolls and 94.7 buys per game** against
`standard`'s 14.5 and 65.2. The fix worked and did not matter -- which is what
made the next step necessary rather than optional.

### 73.3 Fix 2: targeting, which was the mechanism all along

Rolling 46 times while spreading purchases across ~14 champions of a tier never
concentrates copies. `EconStrategy` gained `target_cost`/`target_count`: commit
to N champions of a tier, rank them by copies already held so the commitment
emerges from what the shop offered, prefer them above synergy and cost, and
never sell them.

| | before | after |
|---|---|---|
| games with a 3-star | 40% | **100%** |
| 3-star share of units at 5-1 | 0.3% | **8.4%** |
| first 3-star | scattered to 5-3 | **4-1 to 4-3** |

Stage-4 3-stars is the real TFT pattern. `slowroll6` went **5.430 -> 4.853**.
This is entry 69.3's hypothesis confirmed, and it is a *policy* mechanism, not
an engine one.

### 73.4 Fix 3: an archetype that never transitioned

`hyperroll` did not move (6.073 -> 6.067). Its curve held **level 5 from 2-3 to
4-5** -- a five-unit board through all of stages 3 and 4. That is not
hyper-roll, it is never transitioning. Real hyper-roll rolls in stage 2, hits,
and rejoins a normal curve. Corrected to 4@2-1, 5@2-3, 6@3-2, 7@4-1, 8@4-5,
9@5-5. **6.067 -> 5.093.**

### 73.5 Where the field landed

| archetype | seats | placement |
|---|---|---|
| fast8 | 2 | 4.107 |
| standard | 3 | 4.229 |
| slowroll6 | 2 | 5.003 |
| hyperroll | 1 | 5.093 |

**Spread 2.283 -> 0.987.** The econ archetypes cluster near parity; the reroll
archetypes remain ~0.8-0.9 worse.

**Tuning stops here, deliberately.** The remaining spread could be closed by
further hand-fitting, but a field balanced by fitting is a field whose fairness
is an artefact of the fitter. The residual is a *hypothesis worth testing
rather than tuning away*: reroll trades board slots for star levels, and if
stars do not pay for slots here, board size is overweighted relative to real
TFT -- where a six-unit 3-star board genuinely beats an eight-unit 2-star one.
That is a **combat**-fidelity question, and 67.1 only verified star *stats*, not
whether they win fights.

*Lesson.* **Three "the engine is broken" candidates in a row were the policy
definitions.** The buy gate was a real code bug; the reroll weakness was a
missing policy mechanism; the residual was a badly written level curve.
Concluding "reroll comps are non-viable in this engine" at any of the three
earlier points would have been wrong, and each time the tempting conclusion
pointed at the simulator rather than at what had just been written.

### 73.6 Still open

- Re-measure the teacher against the fair field; 72.2's table is withdrawn.
- The 0.987 residual: does a 3-star board beat a bigger 2-star board here?
- Whether `standard`/`fast8` being ~0.4 better than the reroll pair is
  *correct* -- real TFT strategy win rates differ, but no external rate was
  sourced.
- Combat fidelity, still entirely unvalidated.

---

## 74. The teacher was below average all along (08-06)

73.6's follow-up, replacing 72.2's withdrawn table. Same five arms, 300 shared
seeds, against the **fair** field of 73.5 (spread 0.987).

| arm | placement | vs parity | vs incumbent | t |
|---|---|---|---|---|
| **standard** | **4.213** | **-0.287** | -0.610 | -4.04 |
| fast8 | 4.337 | -0.163 | -0.487 | -3.44 |
| hyperroll | 4.877 | +0.377 | +0.053 | +0.33 |
| **no-econ (incumbent)** | **4.823** | **+0.323** | -- | -- |
| slowroll6 | 6.077 | +1.577 | +1.253 | +8.34 |

### 74.1 The number this project was built on

**The teacher is worse than parity.** 4.823 against 4.500, on a field where
every opponent runs a published economy plan. The policy that ~70 entries of
imitation work cloned, and whose 3.030 anchored every comparison in this log, is
*below average* against competent opposition.

The arc of that number as the world got more honest:

| field | teacher | edge over parity |
|---|---|---|
| one purchase per round | 3.030 | +1.470 |
| real economies, capped at level 8 | 3.883 | +0.617 |
| real economies to level 9-10 | 4.120 | +0.380 |
| **fair field (73.5)** | **4.823** | **-0.323** |

The original figure overstated the teacher's edge by more than a full placement
and had the **sign wrong**. Entry 56 saw the shadow of this (4.387 against a
stronger field) and 70.4 predicted it before measuring; neither went far
enough, because both still assumed the teacher was good and the opposition
merely weak.

### 74.2 An economy is worth 0.610, and which one does not matter

`standard` -0.610 (t=-4.04) and `fast8` -0.487 (t=-3.44) both clear the bar.
Against each other: **+0.123, t=+1.05** -- indistinguishable, as they were in
72.2 on the unfair field. The finding replicates across two fields and remains
"a real economy beats no economy", *not* that either plan is the right one.

`standard` is the recommended teacher: it is the only arm measurably better
than parity, and it tracks the published level curve most closely.

### 74.3 What this means for everything downstream

Imitation cloned a below-parity policy to within ~0.36 (entry 66.2) and called
the remainder a gap worth closing. The gap that mattered was never
clone-to-teacher; it was **teacher-to-competent**, and it was never measured
because the opposition could not spend gold.

An agent trained to match this teacher is being trained to place 4.823. Nothing
in the RL programme was wrong about optimisation; the target was wrong.

### 74.4 Still open

- ~~Plumb `--expert-econ` through `train_ppo.py`.~~ **Done.** The flag reaches
  the single `expert_kwargs` dict (so the clone and every DAgger round share
  one teacher), lands in the sidecar, and is read back by `teacher_gap` and
  `teacher_check`. That read-back is the part that mattered: dropping it would
  score a clone trained on the 4.213 teacher against the 4.823 one and produce
  a plausible, meaningless gap. `tests/test_doc_refs.py` asserts the round trip
  in both directions.

  The first clone aimed at a better-than-parity target has **not** been
  trained; nothing in this log yet describes one.
- Whether `standard` at -0.287 is a *good* teacher or merely a less bad one.
  Parity is not skill; it is the average of eight.
- The 0.987 field residual and combat fidelity, both from 73.6.

---

## 75. Improving the teacher improves the agent, one-for-one (08-06)

Entry 74 found the teacher below parity and 74.4 plumbed `--expert-econ`. This
trains the first clone aimed at a better-than-parity target, with a matched
control: **both clones trained in the same world, identical configuration,
differing only in the teacher's economy.** 400 episodes, 50 epochs, label
smoothing 0.02, slot head, seed 0. All placements 300 shared seeds.

| teacher | teacher place | clone | clone place | gap | t |
|---|---|---|---|---|---|
| `standard` econ | **4.213** | `bc-econ-s0` | **4.740** | +0.527 | +3.53 |
| no econ | 4.823 | `bc-noecon-s0` | 5.283 | +0.460 | +3.30 |

### 75.1 The economy survives cloning

**Econ clone - control clone = -0.543, t=-3.64**, better in 157 games and worse
in 92. The teachers differ by 0.610, so imitation transmitted **89%** of the
improvement. The two clone-to-teacher gaps are near-identical (+0.527, +0.460):
imitation behaves the same whatever teacher it is given.

This was not the expected outcome. Economy decisions are a handful of `BUY_XP`
and `REROLL` actions among dozens of buys and placements per round, so a clone
could plausibly hold high action match while missing exactly the decisions that
set the economy. It does not: the plan transmits.

### 75.2 What this says about the last twenty entries

Entries 48-65 spent four experiment batches and an entire RL programme trying to
beat a teacher by optimisation, and **every** attempt failed -- PPO at +0.113
(t=+0.73), DAgger at nothing over plain BC, imitation saturated at ~3.40 across
400 and 1500 episodes.

The lever that moved the agent was making the teacher better. It cost one flag
and a 13-minute training run, and it moved placement 0.543 -- larger than any
effect the RL programme ever produced, in the right direction, at t=-3.64.

*Lesson.* **When imitation is saturated, the ceiling is the teacher, not the
method.** "Imitation is exhausted" (58.4) was true and was read as *this line of
work is finished*. It meant *this teacher is finished*. Nine entries of
optimisation followed a conclusion that pointed at the target rather than the
optimiser.

### 75.3 The agent is still below average

4.740 against a 4.500 parity line. The teacher is *above* parity at 4.213 and
the clone gives back more than that margin in the imitation gap. The honest
statement is: the first clone trained toward a better-than-average target, and
measurably better than the alternative -- **not** yet better than average.

### 75.4 A number not to cite yet

The econ clone reports **0.622 held-out critic EV**, against the 0.228-0.452
this project has always seen, and the control reports 0.237 on the same code.
An econ teacher following a deterministic level curve plausibly makes outcomes
more predictable.

But 58.2 measured the *ceiling* on knowable placement variance at ~0.5 mid-game,
and 0.622 sits above it. Either that ceiling moved when the world changed, or
the two quantities are not comparable. **Unresolved**, and 0.622 should not be
quoted as a win until it is -- this is exactly the shape of the 90.7% ceiling
that survived three entries before being re-derived (lesson 4).

### 75.5 Still open

- Whether the imitation gap (~0.5) can be closed now that the target is worth
  hitting. Single training seed per arm here; 0.543 clears entry 65's 0.074
  noise floor comfortably, smaller differences would not.
- A better teacher still. `standard` at -0.287 is barely above parity, and
  parity is not skill.
- Reconcile 0.622 against 58.2's ceiling (75.4).
- Combat fidelity and the 0.987 field residual, both from 73.6.

---

## 76. Combat prices stars correctly; the reroll shortfall is a gold budget (08-06)

73.6 left a hypothesis: reroll trades slots for stars, so if stars do not pay
for slots then board size is **overweighted** relative to real TFT -- a combat
defect. Lesson 14 says validate the model before optimising against it, and
combat was the only unvalidated half, so this was measured before any further
teacher work.

`scripts/star_vs_slots.py` fights the two boards directly. Whole-game
measurements cannot isolate this: there, economy, items, augments and HP all
vary at once. Both sides draw from the same cost tier and roster, and both use
`place_team`'s default layout, so only star level and unit count differ.

### 76.1 The hypothesis is refuted

| small board | vs | small wins |
|---|---|---|
| 6x 3-star | 8x 2-star | **100.0%** |
| 6x 3-star | 9x 2-star | 92.0% |
| 7x 3-star | 9x 2-star | 100.0% |
| *control:* 6x 2-star | 8x 2-star | **0.0%** |
| *control:* 8x 3-star | 8x 2-star | **100.0%** |

Both controls land exactly where they must -- the bigger board wins at equal
stars, the 3-star board wins at equal slots -- so the harness is sound and the
rows above are readable.

**A six-unit 3-star board crushes an eight-unit 2-star board**, which is real
TFT's behaviour and the entire reason reroll comps exist. Combat is not
overweighting board size. The prediction was wrong and the axis is clean.

### 76.2 What the shortfall actually is

Reroll seats never *field* a 3-star board. Entry 73 measured 3-stars at 8.4% of
units at 5-1 -- **under one per seat** -- against the six the matchup above
assumes. The arithmetic at level 6, where 2-costs are 40% of a 5-slot shop
across 13 champions:

    P(specific 2-cost per roll) = 5 x 0.40/13 = 0.154
    9 copies  ->  58 rolls      (one 3-star)
    27 copies -> 176 rolls      (three)

`slowroll6` manages **46 rolls per game**, so ~0.8 three-stars -- which is
exactly the 8.4% observed. It is not being cheated by combat; it cannot afford
what it is trying to buy. A game yields roughly 420 gold and it spends most of
it on the units it hits (94.7 buys/game), so one 3-star costs ~200 gold all-in
and three would cost more than the game pays out.

Income matches real TFT (base 5, interest to 5, streak to 3, +1 on a win), and
real 2-cost reroll comps typically land **one** carry rather than three. So the
0.987 field residual is plausibly correct rather than a defect: reroll is a
weaker line here, not a broken one.

### 76.3 What this does and does not validate

Validated: the **star-vs-slot exchange rate**, on its own axis, against a real
TFT qualitative fact. Combined with 67.1 (star scaling exactly 3.24x health /
2.25x AD) the unit-quality half of combat now has two independent checks.

### 76.4 Three more constants, checked against published values

Same method as 70.1's xp table -- compare the engine against a source rather
than against itself:

| quantity | published | engine |
|---|---|---|
| armor/MR mitigation | `100 / (100 + resist)` | `k/(k+resist)`, `k=100.0` |
| mana per attack | 10 Assassin/Marksman/Fighter, 7 Caster, 5 Tank | identical |
| tank mana from damage | 1% pre-mitigation, 3% post-mitigation | identical |
| ...capped per instance | 42.5 | 42.5 |

The mitigation *implementation* was checked, not just the constant: 100 damage
into 50 armor yields 66.7, matching the published worked example.

**`armor_mitigation_constant` can come off `config.unverified`** -- doc 01 sec 9
flagged the "exact curve coefficient" as unconfirmed and it is now confirmed.
The mana figures were already implemented from the same sources (entry 5.4) but
had never been re-derived; they hold.

**Still not validated:** targeting, positioning, attack speed and crit,
projectile behaviour, and combat duration against real fight lengths.
`sudden_death_*` and the movement/projectile speeds remain approximations that
no source has been found for.

*Lesson.* **Name the falsifiable version and build its controls.** The
hypothesis was stated as a specific matchup with two controls that had to read
0% and 100%, so the refutation was unambiguous rather than a judgement call.
Three entries had circled "board size dominates" without ever fighting the two
boards; the measurement took one script and refuted a hypothesis three entries
had been leaning on.

---

## 77. Sensitivity analysis for the constants that cannot be validated (08-06)

76.3 left `movement_hexes_per_second`, `projectile_hexes_per_second` and the
`sudden_death_*` pair unvalidated. Unlike the xp table (70.1) or the mitigation
curve (76.4), **these cannot be validated**: Riot does not publish them,
`config.unverified` says so, and a search found nothing.

Validation being impossible does not make the risk unmeasurable. The question
that matters is not "is 2.0 hexes/second correct" but **"would any conclusion
change if it were 1.0 or 4.0"**. `scripts/combat_sensitivity.py` answers that,
overriding config in memory via `dataclasses.replace` -- `data/config.json` is
hand-curated and nothing writes to it.

### 77.1 Two metric traps, both caught before reading a result

**The obvious metric was saturated.** 6x3-star vs 8x2-star reads 100% (76.1),
and a rate pinned at its ceiling cannot register sensitivity *even where
sensitivity exists* -- the floor-effect trap of 18.5 and 52.1. The script now
calibrates across eight matchups and sweeps whichever sits nearest a coin flip;
that is 5x3-star vs 9x2-star at 38.3%.

**The first run was uninterpretable.** At n=40 the largest swing was 7.5pp
against a sampling standard error of **7.7pp**. Reporting "these constants
barely matter" from that would have been reading noise as a result. n=300 drops
the standard error to 2.8pp.

Placement was deliberately *not* the metric: it is zero-sum across eight seats
and a global constant moves every seat at once, so an agent's placement can sit
still while combat changes underneath it. That would look like insensitivity
and be an artefact of the measure.

### 77.2 Three of four are harmless

n=300, baseline 38.3%, standard error 2.8pp:

| variant | 5x3* beats 9x2* | delta | mean duration |
|---|---|---|---|
| baseline | 38.3% | -- | 28.9s |
| movement 1.0 (half) | 41.0% | +2.7 | 29.9s |
| movement 4.0 (double) | 36.3% | -2.0 | 28.3s |
| projectile 6.0 | 39.0% | +0.7 | 29.2s |
| projectile 24.0 | 38.3% | +0.0 | 28.8s |
| sd damage 1%/s | 38.7% | +0.4 | 29.0s |
| sd damage 6%/s | 38.0% | -0.3 | 28.9s |
| **sudden death start 15s** | **33.0%** | **-5.3** | **17.8s** |
| sudden death start 45s | 40.7% | +2.4 | 33.2s |

`movement_hexes_per_second`, `projectile_hexes_per_second` and
`sudden_death_damage_pct_per_second` move the strategic exchange rate by **less
than one standard error across a 2x range in each direction**. Whatever their
true values, nothing this project concludes rests on them.

**`sudden_death_start_seconds` is the exception.** -5.3pp at 15s is ~1.9
standard errors -- suggestive, not established -- and it halves mean fight
duration. It is the one unsourced constant that plausibly decides which
strategies work, and it should stay flagged.

### 77.3 A duration check that came free

Fights average **28.9s and time out 0% of the time** at baseline. Real TFT
fights typically run ~20-35s and rarely hit the timer, so the duration model is
in the right regime. This is a weak check -- no source was found for a real
distribution -- and is recorded as a sanity reading, not a validation.

### 77.4 Where combat fidelity now stands

| axis | status |
|---|---|
| star scaling | verified (67.1) |
| star-vs-slot exchange rate | verified (76.1) |
| armor/MR mitigation | verified against published (76.4) |
| mana per attack, damage-mana, cap | verified against published (76.4) |
| crit chance / damage | verified: 25% / 1.4x, real TFT baseline |
| targeting | verified: nearest, held until death; ties by uid is a deliberate determinism deviation |
| movement, projectile, sd damage | unsourceable, **shown not to matter** (77.2) |
| sudden death start | unsourceable, **may matter** (77.2) |
| attack speed, base stats | from Riot's payload via the fetch script |

*Lesson.* **When ground truth does not exist, measure sensitivity instead.** An
unverifiable constant is not automatically a risk; it is a risk only if
conclusions move when it moves. Three of these had been carrying an
`unverified` flag since milestone 1 and could have been cleared at any point by
a sweep that took one script.

---

## 78. Repositioning is worth 0.33, and the old default was the reason it looked worthless (08-06)

Entry 52.4 established the teacher never repositions -- 173 bench selections
and 0 board selections over 8 games. Entry 47.10 measured positional search at
**-0.198 (t=-1.78)**, under this project's bar, and it was shelved. That figure
came from the world entry 71.4 voided: throttled opponents, a 12-action budget,
a teacher with no economy.

Re-derived because three things changed that bear on it directly: targeting is
now verified faithful (77.4), the star-vs-slot exchange rate is verified
(76.1), and the teacher has an economy against a fair field (73.5, 74.2).

**Augment choice was the other candidate and was dropped.** The augment pool is
14 generic archetypes rather than the real Set 17 set (`config.unverified`,
entry 17.1), so tuning it optimises invented data -- lesson 14's trap. Position
uses the real hex board and verified targeting.

### 78.1 What the budget buys

300 shared seeds, teacher with `standard` econ, against the fair field:

| arm | placement | vs control | t |
|---|---|---|---|
| control (no search) | 4.213 | -- | -- |
| move c6 p1 | 4.100 | -0.113 | -0.87 |
| **move c12 p1** | **3.883** | **-0.330** | **-2.53** |
| move c6 p3 | 3.903 | -0.310 | -2.20 |

Pairwise, so the ranking is not read off the column:

| comparison | delta | t |
|---|---|---|
| c12 vs c6 | -0.217 | -1.85 |
| c6p3 vs c6 | -0.197 | -1.48 |
| c12 vs c6p3 | -0.020 | -0.14 |

**Established:** a search at the larger budget beats no search (-0.31 to -0.33,
t=-2.2 to -2.5). **Not established:** that more candidates beat more panel, or
that c12 specifically beats c6 -- t=-1.85 is under the bar and the two larger
arms are interchangeable at t=-0.14.

### 78.2 Why 47.10 read a null

47's default was `max_candidates=6, panel_size=1` -- the one arm here that
*still* cannot be distinguished from control (t=-0.87). The old conclusion was
not wrong about its own arm; it generalised from the cheapest configuration to
the technique. 47.7's "more budget on candidates bought nothing" is the claim
that misled, and it is **not** cleanly overturned here either (t=-1.85) -- what
changed is that *some* larger budget now clears the bar where none did.

### 78.3 The teacher's arc

| teacher | placement | vs parity |
|---|---|---|
| no econ (the policy ~70 entries cloned) | 4.823 | **+0.323** |
| + `standard` econ (74.2) | 4.213 | -0.287 |
| + positional search c12 (78.1) | **3.883** | **-0.617** |

Two changes, both cheap, moved the teacher from *below* average to 0.617 above
it. Entry 75 measured teacher gains transmitting to the clone at 89%, so this
is worth ~0.29 on the agent if it carries.

### 78.4 Cost, and what it means for cloning

The four arms took **84 minutes** -- each candidate move is a full combat
simulation, so a search teacher is ~4x the cost per game. Collecting 400
expert episodes with `c12 p1` is roughly 28 minutes rather than 7. Affordable,
but it makes every future DAgger round and every re-clone materially slower,
and that cost should be stated before it is spent.

### 78.5 Still open

- Train a clone on the search teacher and check the 89% transmission holds for
  a *positional* improvement; 75 measured it for an economic one.
- Whether the teacher's `_preferred_hex` rule can be improved directly, which
  would be free at inference where search is not.
- The `c12`-vs-`c6` question, still under the bar at t=-1.85 after 84 minutes.

---

## 79. The search teacher was not a function of the board, so it could not be cloned (08-07)

Entry 78.3 recorded the plan: the teacher gains **0.330** from positional
search, entry 75 measured teacher gains transmitting to the clone at **89%**,
so the agent should gain ~0.29. It gained nothing. The reason turned out to be
a property of the search itself, and it invalidates how 78 framed the result
rather than the result.

### 79.1 The clone measurement

`bc-search-s0`: same pure-BC configuration as `bc-econ-s0` (400 expert
episodes, 50 epochs, no DAgger, no PPO, seed 0), differing only in the
teacher's `c12 p1` search. Both clones and the search teacher on shared seeds
0-299, teacher reconstructed from the sidecar:

| arm | placement | gap to own teacher | t |
|---|---|---|---|
| teacher, econ only (78.1) | 4.213 | -- | -- |
| teacher, econ + c12 search | **3.883** | -- | -- |
| `bc-econ-s0` | 4.740 | +0.857 | +5.78 |
| `bc-search-s0` | **4.930** | **+1.047** | +6.90 |

Clone to clone: **+0.190, t=+1.31, n=300** — under the bar, so the honest
statement is that the search clone is *not better*, not that it is worse.
Either way 0.330 of teacher strength produced nothing, and the gap to teacher
**widened** from 0.857 to 1.047.

The teacher arm reproduced 78.1's 3.883 exactly on the same seeds, which is
also the first confirmation that the sidecar search reconstruction works.

**The prediction in 78.3 failed.** 89% transmission was measured for an
*economic* improvement and does not generalise to a positional one.

### 79.2 Where the disagreement is

Per-action-kind agreement with the teacher that actually labelled each run, on
**expert states** with deterministic prediction:

| action kind | econ teacher | search teacher |
|---|---|---|
| BUY | 96.7% | 96.2% |
| BUY_XP | 94.7% | 95.0% |
| PICK_AUGMENT | 99.2% | 99.2% |
| REROLL | 95.0% | 86.9% |
| **SELECT** | **84.0%** | **47.4%** |
| **PLACE** | **78.8%** | **44.5%** |
| *overall* | *90.8%* | *83.0%* |

Every non-positional decision is untouched. The whole 7.8-point drop is the two
positional kinds, and `SELECT` volume nearly doubled (910 -> 1644 labels): the
teacher's improvement lives exactly where the clone fits worst.

### 79.3 The cause, and the correction to 79.2

47.4% on a clone's *own training set* reads as a failure to fit, which is a
statement about the feature set (CLAUDE.md). Two setups could be at fault, with
opposite remedies: the observation cannot express which hex is better, or the
teacher is not a function of the observation at all.

`best_move` builds the full ~200-move list, calls `rng.shuffle`, and evaluates
the first `max_candidates`. With a free-running stream, two calls on a
byte-identical board consider **different candidate moves entirely**. Measured
over 60 states x 5 RNG streams:

| | |
|---|---|
| modal-move agreement | **38.7%** |
| states where all five streams agreed | 10.0% |
| mean distinct answers per state | 4.03 of 5 |
| states giving five different answers | 55% |
| "no move" rate | 24.7% |

**38.7% is a ceiling on SELECT/PLACE action match** — no student can agree with
the teacher more often than the teacher agrees with itself. The clone's 47.4%
is *above* it, the excess coming from the 24.7% of states where the search
declines to move and the deterministic base policy answers.

So 79.2's reading was wrong, in the way lesson 6 names: a rate quoted against
an unstated maximum. The clone is not failing to fit the positional labels; it
is fitting them about as well as they can be fitted. And the predicted
explanation — the observation lacking the relation — is **not** the operative
one. It remains untested, because the label noise masks it.

This also explains 78.1's budget ranking without contradicting it. More random
samples cover the move space better, so the teacher genuinely plays better while
becoming *less* learnable. Better teacher, worse labels, pulling opposite ways —
which is the observed pattern exactly.

### 79.4 The fix

Seed the candidate sample from a digest of the board layout, the occupied and
free hexes, and the panel. The sampling *distribution* is unchanged — moves are
still drawn uniformly from the same ~200 — so search quality should be
untouched (measured in 79.7: +0.053, t=+0.39), while the draw becomes
reproducible for a given state.
`state_seeded=False` restores the free-running stream so every pre-79 number
stays reproducible.

**A trap inside the fix.** The first version keyed on `hash()`. Python
randomises string hashing per process, so the key would have been deterministic
in a single-process test and silently state-dependent across the `spawn` pools
that `evaluate_scripted_parallel` and `collect_expert_data` both use — the exact
defect, wearing the fix's clothes. It uses SHA-256, and
`test_state_seeding_does_not_depend_on_pythonhashseed` runs the search in
subprocesses under three `PYTHONHASHSEED` values and requires one answer.

### 79.5 Tooling repaired

`scripts/action_match.py` rebuilt its teacher from hand-passed CLI flags, with
no `econ` and no search available at all. Run against these clones as written it
would have measured disagreement with a policy neither model ever saw, and
printed a plausible table. It now takes run directories and reconstructs from
the sidecar, like `teacher_gap`. That is the third script in this project with
this defect (37.4, 38.9, 45.2 are the earlier ones).

`--expert-reposition` hardcoded `max_candidates=6, panel_size=1` — precisely the
arm 78.1 measured at t=-0.87, the one budget indistinguishable from no search.
Cloning it would have reproduced 47.10's null and read as a replication. The
budget is now a flag, recorded in the sidecar, and reconstructed by
`teacher_gap` and `teacher_check`.

### 79.7 Determinism is free

Three arms, 300 shared seeds, one run, with a source fingerprint checked
between arms (lesson 13):

| arm | placement | vs control | t |
|---|---|---|---|
| control (no search) | 4.213 | -- | -- |
| c12 stream (pre-fix) | 3.883 | -0.330 | -2.53 |
| **c12 state-seeded** | **3.937** | **-0.277** | **-2.13** |

state-seed vs stream: **+0.053, t=+0.39, n=300**. Indistinguishable, which is
what the mechanism predicts — the distribution is unchanged, only the draw's
provenance. Control reproduced 78.1's 4.213 and the stream arm reproduced its
3.883, both exactly.

The three possible outcomes were named before the run finished (lesson: a story
cannot be fitted afterwards). The third — state-seeding measurably *better* —
would have been treated as an artefact to explain rather than a win, since no
mechanism makes a reproducible draw beat an equivalent random one.

### 79.8 Clean labels changed nothing, which is the real finding

`bc-search-det-s0`: identical to the other two clones, teacher state-seeded.

Determinism control first, because the whole reading rests on it -- 60 states x
5 streams, same probe as 79.3:

| | stream | state-seeded |
|---|---|---|
| modal-move agreement | 38.7% | **100.0%** |
| states where all five agreed | 10.0% | **100.0%** |
| distinct answers per state | 4.03 of 5 | **1.00** |

The ceiling is fully lifted. Then, on shared seeds 0-299:

| clone | placement | gap to own teacher |
|---|---|---|
| `bc-econ-s0` (no search) | **4.740** | +0.803 |
| `bc-search-s0` (stream labels) | 4.930 | +0.993 |
| `bc-search-det-s0` (clean labels) | **4.977** | +1.040 |

det vs stream: +0.047, t=+0.32. det vs econ: +0.237, t=+1.54. All three clones
are the same policy within noise; **no search teacher produces a better clone at
any label quality**, while its teacher is 0.803 ahead.

Per-action, against a teacher whose ceiling is now 100%:

| | stream teacher | state-seeded teacher |
|---|---|---|
| SELECT | 47.4% (1644 labels) | **46.8% (1636 labels)** |
| PLACE | 44.5% | **45.5%** |

**Not one point of movement.** Under the stream, 47.4% sat *above* its 38.7%
ceiling and was uninterpretable. With the ceiling at 100% the clone still reads
46.8%. That is a real failure to fit, and it is now unconfounded.

**A predicted mechanism failed and is recorded as failed.** State-seeding was
expected to yield *fewer* positional labels, because repeated visits to an
unchanged board would stop accumulating coverage. Counts are 1644 vs 1636.
Dead -- and it was the explanation that would have excused a weak result.

### 79.9 What this establishes

The observation cannot express **which hex is better**. 79.3 dissolved the
first attempt at this claim by showing the evidence for it was a ceiling
artefact; this is the same claim with the artefact removed. The teacher is now
a provable function of the board, and the clone still cannot follow it, so the
gap is in what the observation carries -- CLAUDE.md's rule that a probe which
cannot fit its own training set is a statement about the feature set.

It is also the project's central finding restated. Which hex is better is a
*relation* between our units' positions and the enemy's threats; the
observation supplies a *description* of where units stand. Relational beats
descriptive (§44, §57), and this is the relation not being supplied.

Note what this does **not** say. The search teacher is genuinely stronger
(3.937, -0.277 vs control, t=-2.13) and remains the best teacher measured. What
fails is transmitting it by imitation through the current observation.

### 79.6 Still open

- Whether a positional *relation* in the observation -- threat range, distance
  to the nearest enemy carry, front/back occupancy against the opposing shape --
  closes it. This is the first concrete widening candidate since 57, and unlike
  the rejected `features` encoding it is a comparison, not a description.
- Whether `_preferred_hex` can be improved directly, which is free at inference
  and needs no imitation at all. 78.5 raised this; 79.8 makes it the cheaper
  path of the two.
- Entry 75's 89% transmission stands for economic improvements and is now known
  **not** to be a general rate.
- Whether the observation can express *which hex is better*. Still untested —
  79.2's evidence for it dissolved with the ceiling.
- `best_swap` shuffles nothing, but selects candidates by `(star, cost)` order,
  so it is already a function of the board. Untouched here.

---

## 80. The placement rule is already the best of three, and spacing barely matters here (08-07)

79.6 left two paths. This is the cheap one: improve the teacher's *placement
rule* rather than widen the observation. A rule is a deterministic function of
the board, so it is free at inference and a clone can follow it -- PLACE match
against the plain econ teacher is 78.8%, against 45.5% for the search teacher's
moves (79.2). Search costs ~4x per game and transmits nothing (79.9), so the
bar a free rule is measured against is **3.937**, not 4.500.

### 80.1 Both alternatives are worse

The incumbent sorts empty slots by depth and takes an end. That sort is
**stable**, so within the chosen row ties break by slot index and every unit
lands on the same flank -- the board clumps into a corner. Two alternatives,
varying only the column chosen within the target row, 300 shared seeds:

| rule | placement | vs rows | t |
|---|---|---|---|
| `rows` (incumbent) | **4.213** | -- | -- |
| `centre` | 4.500 | +0.287 | **+2.21** |
| `spread` | 4.440 | +0.227 | +1.71 |

`rows` reproduced 78.1's 4.213 exactly. `centre` is significantly **worse**;
`spread` is worse and under the bar. The hypothesis that flank-clumping is a
defect was wrong -- of the three, clumping is the best.

### 80.2 Why, and a correction made before publishing it

Clumping is punished in real TFT mainly by **area abilities**, so the null
invited a fidelity explanation. A first pass at `engine/effects.py` found one
radius-based champion ability in 63 and was about to be written up as "AoE is
essentially unmodelled".

That count was wrong. Per-champion behaviour lives in `engine/abilities.py` --
the *second* registry, which this file's own conventions name explicitly -- and
searching one of two registries produced a number 9x too low. Corrected:

| ability shape | champions | spacing matters? |
|---|---|---|
| radius / line / adjacency | 9 (14%) | yes |
| multi-target, count-based | 21 (33%) | **no** |
| single target or self | 33 (52%) | n/a |

`_spread_targets` returns "the primary target plus the *nearest other
enemies*, up to `count`" -- there is no radius cutoff, so a third of champions
hit the same number of units however the board is spaced. Spreading mitigates
9 champions' abilities, not 30.

So the null is **partly** explained by the engine: the specific skill `spread`
was built to exploit is under-priced. It is not fully explained -- 14% of
champions are genuinely position-sensitive, and 47.2's 5.78-unit best-worst
spread from rearranging a fixed board shows position pays through melee/ranged
geometry and targeting regardless of AoE. This is not a clean fidelity defect
and should not be cited as one.

### 80.3 What it changes

Nothing in the teacher: `rows` stays. `place_rule` is kept as a parameter with
`rows` the default, because the two alternatives are now measured rather than
untried, and a future entry that wants to revisit spacing should start from
these numbers rather than re-deriving them.

The cheap half of 79.6 is now closed, and it did not pay. The remaining path is
the expensive one: supply the positional *relation* the observation lacks.

### 80.4 Still open

- Whether a positional relation in the observation closes 79.9's gap. Now the
  only live lead on position.
- Whether `_spread_targets` should take a radius, which is a **fidelity**
  question rather than an agent one, and would change what any spacing
  experiment measures. Flagged, not assumed: no source was checked for how Set
  17 abilities actually select secondary targets.
- 78.5's `c12`-vs-`c6` question, still unresolved and now lower value given
  search does not transmit.

---

## 81. DAgger closes the distribution gap and buys nothing (08-07)

79.9 left the clone 0.803 behind its teacher and read the cause as the
observation. Before spending on observation width, the competing explanation
was worth eliminating: **distribution shift**. 79.2 showed the signature
plainly -- the clone held 90.8% agreement on the teacher's states and fell to
69.5% on its own, with BUY_XP collapsing 94.7% -> 38.0%. DAgger is the standard
fix and was off in every clone measured that day (`dagger_rounds: 0`).

Not untried: 24.2 measured DAgger raising match 81.8% -> 88.7% with no placement
movement. That was against a teacher placing 4.823, *below* parity, in the world
71.4 voided. "Following a bad teacher more faithfully doesn't help" is a
different claim from "following a good teacher more faithfully doesn't help".

A **dose-response** (0 / 2 / 5 rounds) rather than one arm, so a flat line is a
strong replication rather than a single null. Rounds 1-2 of the 5-round arm
reproduced the 2-round arm's transition counts and match exactly -- same seed,
nested comparison, not two independent draws.

### 81.1 The result

300 shared seeds, paired against the 0-round control:

| arm | placement | vs 0 rounds | t | gap to teacher |
|---|---|---|---|---|
| TEACHER | 4.213 | -- | -- | -- |
| `bc-econ-s0` (0 rounds) | 4.740 | -- | -- | +0.527 |
| `dagger-r2` | 4.657 | -0.083 | -0.57 | +0.443 |
| `dagger-r5` | 4.730 | -0.010 | -0.07 | +0.517 |

r5 vs r2: +0.073, t=+0.52. Flat at every dose.

### 81.2 DAgger did its job -- that is what makes this decisive

The null is **not** DAgger failing to work. On student states:

| action kind | 0 rounds | 2 rounds |
|---|---|---|
| overall | 69.5% | **75.8%** |
| BUY_XP | 38.0% | **67.0%** |
| SELECT | 37.5% | **62.7%** |
| PLACE | 46.3% | **56.9%** |

Expert-state match rose 89.6% -> 96.5%, closing two thirds of the residual
disagreement. Student-state agreement rose 25-29 points on the two decision
types 79.2 identified as the collapse. Placement moved -0.083 (t=-0.57).

**Agreement with this teacher does not determine placement.** That is a
stronger statement than 24.2's, which could be dismissed as a fact about a
below-parity teacher; here the teacher is 0.617 above parity and the result is
identical.

### 81.3 More rounds are actively worse

| round | match | loss |
|---|---|---|
| 1 | 96.5% | 0.318 |
| 2 | 96.5% | 0.327 |
| 3 | 96.5% | 0.331 |
| 4 | 96.3% | 0.339 |
| 5 | 96.1% | 0.344 |

Each round adds ~55k student transitions to what becomes a 459k aggregate, so
the expert's own distribution is progressively diluted. All the agreement
arrives in round 1; rounds 2-5 are cost with a small negative drift. This was
named as a risk before the run and is why the dose-response was included.

### 81.4 What is now eliminated

The clone-teacher gap has three candidate causes. Two are now closed:

| cause | test | result |
|---|---|---|
| label noise | 79.8, state-seeded search | no movement |
| distribution shift | 81.1, DAgger 0/2/5 | no movement |
| observation cannot represent the policy | -- | untested |

Imitation is exhausted in a stronger sense than the founding claim meant. It is
not that the teacher is the ceiling (16); it is that **at ~96% agreement the
remaining disagreement does not carry placement**, so no imitation method can
close 0.527.

### 81.5 Still open

- The observation, now the only surviving explanation and no longer a guess.
  Both alternatives were tested and eliminated rather than argued away.
- Why 0.527 survives 96% agreement at all. A 4% disagreement rate costing a
  fifth of the placement range implies the residual is concentrated on
  decisions of very high leverage; which ones is unmeasured, and identifying
  them is cheaper than widening the observation blind.
- `dagger()` accepts `expert_kwargs` but **not** `search_kwargs`, so DAgger with
  a search teacher would silently label with a non-search one. Latent; the fifth
  instance of the family 79.5 catalogues. Not hit here because this teacher has
  no search.

---

## 82. The residual disagreement that costs placement is positional (08-07)

81.4 left the observation as the only surviving explanation for the clone's
0.527 gap. Widening it blind costs a training run per guess -- and the same
champion encoding has been rejected three times for want of a target. A 4%
disagreement rate costing a fifth of the placement range implies the residual
is concentrated on a few high-leverage decisions; this finds which.

**The counterfactual.** At a state where clone and teacher disagree: play the
rest under the clone, versus substitute the teacher's action *once* and then
continue under the clone. The placement difference is that decision's leverage.
`deepcopy` cannot fork the env (`mappingproxy`), so branches replay from the
seed -- verified deterministic first, so both branches share every RNG draw and
differ only in the substituted action.

One detail that would have silently invalidated it: `scripted_policy` closes
over the env it was built with and reads live player state from it, not from
the observation it is handed. The teacher needs its own env stepped in lockstep
with the **executed** action, or the games diverge and every later
"disagreement" is between different boards.

### 82.1 Leverage by action kind

900 counterfactuals over 300 episodes, clone = `dagger-r2`. Negative means the
teacher's action was better.

| action kind | n | share | mean delta | t |
|---|---|---|---|---|
| PICK_OFFERING | 42 | 4.7% | -0.405 | -1.55 | *(**REFINED by 84**: -0.133 at n=631)* |
| SELECT | 148 | 16.4% | -0.230 | -1.76 |
| PLACE | 161 | 17.9% | -0.161 | -1.46 |
| BUY | 89 | 9.9% | -0.101 | -0.84 |
| BUY_XP | 52 | 5.8% | +0.019 | +0.08 |
| **SELL** | **346** | **38.4%** | **+0.020** | **+0.32** |
| EQUIP | 32 | 3.6% | +0.031 | +0.10 |
| END_PLANNING | 25 | 2.8% | +0.200 | +0.96 |
| REROLL | 5 | 0.6% | +0.800 | +1.09 |

Overall: -0.076, t=-1.65 -- **under the bar**, so "correcting one action helps"
is not established in aggregate.

Pooled, grouping the two positional kinds:

| group | n | mean delta | t |
|---|---|---|---|
| **positional (SELECT + PLACE)** | 309 | **-0.194** | **-2.28** |
| everything else | 591 | -0.014 | -0.25 |
| economic (BUY / BUY_XP / SELL / REROLL) | 492 | +0.006 | +0.11 |

The grouping is post-hoc in the sense that per-kind numbers were seen first, but
it is confirmatory of the standing hypothesis from 78-80 rather than fished.
t=-2.28 at n=309 is solid, not overwhelming.

### 82.2 Why DAgger bought nothing

`SELL` is **38.4% of all disagreements and carries +0.020 (t=+0.32)**. Nearly
two fifths of the mismatch DAgger was closing costs nothing. Economic
disagreement as a whole is +0.006 -- indistinguishable from zero across 492
samples.

81 raised student-state BUY_XP agreement 38.0% -> 67.0% and SELECT 37.5% ->
62.7%, and moved placement -0.083. This says why: the economic half of that was
worthless by construction, and the positional half is where the value is but is
also where the observation cannot support the choice (79.9).

### 82.3 Stage profile

| stage | n | mean delta | t |
|---|---|---|---|
| 2 | 202 | -0.163 | -1.26 |
| 3 | 214 | -0.159 | -1.36 |
| 4 | 269 | -0.033 | -0.59 |
| 5 | 165 | +0.067 | +1.21 |

Leverage is early and decays to nothing by stage 5, consistent with compounding
-- a bad board on 2-3 is carried, a bad board on 5-5 has little game left to
matter. No stage clears the bar alone.

### 82.4 What it specifies

Three independent lines now converge on the same target:

| entry | finding |
|---|---|
| 79.9 | the clone cannot imitate positional choices even with clean labels |
| 80.1 | hand-written placement rules do not help; the incumbent is best of three |
| 82.1 | positional disagreement is the only kind whose correction pays |

The observation should gain a positional **relation**, not a description --
distance from each fielded unit to the nearest scouted enemy, how many enemies
can reach it, our board's shape against the opposing shape. Descriptions have
failed three times (§44); comparisons have worked every time.

### 82.5 Still open

- The feature set itself, and whether it closes any of the 0.527.
- The aggregate one-step effect is under the bar (t=-1.65); only the positional
  subset clears it. A multi-step counterfactual would test whether the teacher's
  advantage is in sustained sequences rather than single choices.
- ~~PICK_OFFERING has the largest magnitude (-0.405) on the smallest n (42).~~
  **Re-measured in 84: -0.133 at n=631.** The row was a thin-cell artefact.

---

## 83. Supplying attack range does nothing, and the clone noise floor is 0.14 (08-07)

82.4 specified the observation as the remaining target. Reading it first
sharpened the target considerably:

| information | encoded? |
|---|---|
| own board positions | **yes** -- units are written per hex, so slot index *is* the hex |
| the **selected** unit's attack range | **yes** (`SELECTION_FEATURES` index 6) |
| board/bench units' attack range | **no**, under the `index` encoding |
| opponent geometry | **none** -- scouting is a composition summary |

The teacher's placement rule is `ranged = attack_range > 1` -> deepest row
(corner-most under `corner_carry`), else front. It is **purely
self-referential**: it never reads enemy positions. So imitating it needs no
enemy geometry, only one missing quantity -- per-unit attack range, behind an
identity match the policy cannot invert (CLAUDE.md). One float per slot: 418 ->
455, against ~1800 for the `features` encoding rejected three times (44).

### 83.1 It does nothing

Three paired seeds, 300 shared episodes each:

| seed | `econ` | `range` | diff |
|---|---|---|---|
| 0 | 4.740 | 4.513 | -0.227 |
| 1 | 4.470 | 4.580 | +0.110 |
| 2 | 4.703 | 4.770 | +0.067 |
| **mean** | **4.638** | **4.621** | **-0.017, t=-0.16** |

Seed 0 was a favourable draw. Had it been run alone -- as every clone
comparison in 79 and 81 was -- it would have read -0.227 and been written up as
promising.

### 83.2 The predicted mechanism failed too

The prediction was that PLACE and SELECT agreement would rise, since that is
the rule the feature feeds. On fresh expert states:

| | `bc-econ-s0` | `bc-range-s0` |
|---|---|---|
| PLACE | 79.0% | 78.5% |
| SELECT | 84.0% | 83.1% |
| overall | 90.8% | 90.2% |

Slightly **lower** on all three, while training-set match rose ~0.85pp. The
feature buys fitting capacity, not generalisation.

### 83.3 A number this entry got wrong before catching it

The training-match gain was first reported as **89.6% -> 95.9%**. The 89.6% was
`bc-search-s0`'s -- a clone of the *search* teacher, which 79.3 established is
much harder to fit because its labels were near-random. `bc-econ-s0` predates
this session and has no log. Measured properly at seeds 1 and 2, `econ` trains
to 95.1%/95.0% and `range` to 95.9%/95.9%: **+0.85pp, not +6.3**.

Lesson 12 says engine changes invalidate cross-run comparisons. It applies to
cross-*teacher* comparisons identically, and was not applied.

### 83.4 The noise floor is twice what was assumed

Within-arm seed-to-seed spread, n=3 each, 300 episodes per point:

| arm | placements | sd |
|---|---|---|
| `econ` | 4.740 / 4.470 / 4.703 | **0.146** |
| `range` | 4.513 / 4.580 / 4.770 | **0.133** |

~0.14, against the **0.074** training-seed figure this project has been quoting.
At one seed only effects above ~0.4 are detectable. That calibrates several
single-seed clone comparisons made today -- 79.1's +0.190 and 79.8's +0.047 were
both reported as under the bar, and are now quantifiably inside noise rather
than merely unproven.

It does **not** touch measurements where both arms share one policy and differ
only in evaluation seeds -- 78.1, 79.7, 80.1 and 82 are paired on shared
episode seeds with no retraining, and carry no training-seed variance at all.

### 83.5 What is left

`unit_range` stays in the code as an off-by-default flag: it is measured, and a
future entry revisiting the observation should start from these numbers.

Three targeted interventions have now failed: clean positional labels (79.8),
better placement rules (80.1), and supplying attack range (83.1). 82's leverage
finding stands independently -- positional disagreement is the only kind whose
correction pays -- so the remaining candidate is the information that is
genuinely absent rather than merely encoded awkwardly: **enemy geometry**. Every
positional relation worth computing needs opponent positions, and the
observation contains none.

### 83.6 Still open

- Enemy geometry in the observation, and whether it closes any of the 0.527.
  Note the teacher itself does not use it, so a clone with it would be
  *exceeding* the teacher's information -- which imitation cannot reward. This
  is an argument for RL from a clone, not for more cloning.
- Every future clone comparison needs >=3 seeds. Single-seed clone results
  should be treated as direction, not evidence.

---

## 84. PICK_OFFERING's leverage was a thin cell (08-07)

82.5 flagged it: largest magnitude of any action kind (-0.405) on the smallest
n (42, t=-1.55), and explicitly "worth a targeted re-measure before anything is
built for it". 82.1 sampled disagreements uniformly, so a kind holding 4.7% of
them got 42 samples -- and the table was *sorted by mean*, so the extreme cell
was also the least precise one.

`disagreement_cost.py` gained a `--kind` filter. Stratifying spends the same
episode budget on the question being asked; the per-kind mean is unbiased
either way, only its precision changes. It yields ~2.3 samples per episode
instead of 0.14.

| | n | mean delta | t |
|---|---|---|---|
| 82.1, uniform sampling | 42 | -0.405 | -1.55 |
| **84, stratified** | **631** | **-0.133** | **-1.72** |

Direction holds; magnitude falls to a third and stays under the bar. Weighted
by its 4.7% share the contribution is about **-0.006** against a 0.527 gap.

**Not worth building for.** The intended follow-up was an `owned`-for-offerings
feature -- the teacher's rule is `(champion_id in owned, cost)` and the clone
matches it at 54-58%, its worst of any kind. `owned` is explicitly sanctioned
by CLAUDE.md as a fact a player reads off the screen, so it would have been a
legitimate feature built on an illegitimate number.

Sorting a table by mean and reading the top cell selects for noise as much as
for effect, and the smallest cells move most. 13 minutes of re-measurement
against a training run and an observation change.

### 84.1 Still open

- Nothing new. 82's pooled positional finding (-0.194, t=-2.28, n=309) is
  unaffected: it rests on the two *largest* cells, not the smallest.

---

## 85. Reroll is unplayable in the agent seat, and it is not the budget (08-07)

84's econ table, re-derived against the fair field on 300 shared seeds:

| econ | placement | vs standard | t |
|---|---|---|---|
| **standard** | **4.213** | -- | -- |
| fast8 | 4.337 | +0.123 | +1.05 |
| hyperroll | 4.877 | +0.663 | +4.42 |
| **slowroll6** | **6.077** | **+1.863** | **+14.89** | *(**SUPERSEDED by 86**: 4.867)* |

74's 4.823 (no econ) and 4.213 (standard) reproduced exactly. Archetype
*selection* is settled -- `standard` is already the best of the four and
`fast8` is indistinguishable from it -- so that lever yields nothing.

`slowroll6` at 6.077 is the finding. Slow-rolling at 6 is a mainstream real-TFT
line; here it is worse than having no economy at all. An agent trained here
would learn reroll is a trap, which is false of the game being modelled.

### 85.1 The profile

Teacher in the agent seat, per round, sampled only while alive (a dead seat
holds no units, and averaging those in reads as "no 3-stars" when it means
"dead" -- entry 73's vacuous-zero trap):

| | standard | slowroll6 |
|---|---|---|
| HP at 4-3 | 51.1 | 43.8 |
| gold at 4-3 | 36.8 | **59.2** |
| level at 5-2 | 7.8 | 7.0 |
| **3-star units, any round** | 0.00 | **0.00** |

**Zero 3-stars, ever.** Entry 73 recorded reroll archetypes reaching a 3-star
in 100% of games -- but that profiled `GreedyPolicy` seats in the *field*,
which plan a whole phase at once and are not action-budgeted. Same archetype,
two execution paths, never controlled for. In the agent seat it is zero.

Gold *climbs* to ~59 against a roll floor of 50, so 76's "the shortfall is a
gold budget" does not describe the agent seat either: it is not gold-starved.

### 85.2 Two hypotheses, both refuted

**Action budget.** Per-round action counts showed rounds hitting the 50-action
cap with SELL 23 / BUY 23 / REROLL 4 -- each reroll costs ~12 actions because
the shop refreshes, several units are bought, and the surplus is sold. Raising
the cap:

| econ | budget 50 | budget 150 | budget 400 |
|---|---|---|---|
| standard | 4.213 | 4.370 | 4.370 |
| slowroll6 | 6.077 | 5.940 | 5.940 |

-0.137 (t=-1.70) from 50 to 150 and **exactly nothing** from 150 to 400 --
identical placements. At budget 400 a round uses only 55 actions: the cap was
never the binding constraint. Refuted. (`standard` got *worse* with more
actions, +0.157 t=+2.44, unexplained.)

**Buy/sell churn burning gold.** `sell_value` refunds the full combine cost for
1-star units at every tier -- spread 0. The churn is gold-neutral. Refuted.

### 85.3 What the arithmetic says

Pool sizes (30/25/18/10/9), L6 shop odds (30/40/25/5/0) and 13 two-cost
champions are all faithful to real TFT. So:

* P(a given shop slot is a specific 2-cost at L6) = 0.40/13 = **0.031**
* expected copies per roll (5 slots) = **0.154**
* rolls to expect the 9 copies a 3-star needs = **58**, or ~117 gold

Measured over a whole game, `slowroll6` performs **30-33 rerolls** and holds a
maximum of **0** copies of any champion. It needs 58 and gets 30.

The reason is timing, not gold rate: it reaches its 50-gold floor only at
**4-1**, and is dead or nearly so by **5-2**, leaving ~8 rounds of rolling at
~4 rolls each. A real slow-roll is rolling from ~3-2, which is roughly double
the window.

### 85.4 Status

**Partial.** The mechanism is identified as a timing/window problem and two
plausible causes are eliminated, but the fix is not established. `SLOWROLL6`'s
`roll_floors={"3-2": 50}` is a plan that cannot start until gold reaches 50,
which its own `level_targets` delay by spending on XP to level 6 at 3-2.

This is the fourth time this session a defect read as the engine and was the
harness or a plan definition (79.3 search sampling, 80.2 registry search,
83.3 cross-teacher comparison, and this). Whether the residual is *also* a
fidelity defect is untested.

### 85.5 Still open

- Whether an earlier roll floor (or a lower one) makes `slowroll6` viable.
  Cheap: it is a config change and a teacher-side A/B, no retraining.
- Why `standard` degrades with a larger action budget (+0.157, t=+2.44).
- Whether reroll is *also* mispriced beyond the timing, which cannot be judged
  until a plan that actually rolls 58 times exists.
- 84's archetype table is sound for the agent seat but should not be read as a
  statement about the strategies themselves.

---

## 86. The teacher never implemented reroll targeting (08-07)

85 left the reroll question partial: `slowroll6` performs 30-33 rolls against
the 58 needed, holds **0 copies of anything**, and reaches **0 three-stars** in
the agent seat -- while entry 73 recorded the same archetype hitting a 3-star
in 100% of games. 85.2 refuted the action budget and the buy/sell spread.
86 finds the cause, and it is neither the engine nor the plan.

### 86.1 The defect

`EconStrategy` declares `target_cost` and `target_count`: which champions a
reroll comp concentrates its copies into. Counting references:

| module | `target_cost` | `target_count` | `_targets` |
|---|---|---|---|
| `rl/opponents.py` (`GreedyPolicy`, the seven opponent seats) | 6 | 4 | 10 |
| **`rl/evaluate.py` (`scripted_policy`, the teacher)** | **0** | **0** | **0** |

The teacher silently ignored both. In the agent seat `slowroll6` rolled the
shop and then bought by generic `(owned, synergy, cost)` strength, scattering
purchases across the roster. It was a reroll economy with the reroll removed.

This also resolves 73's contradiction: 73 profiled `GreedyPolicy` seats in the
*field*, which honour targeting. Same dataclass, same archetype, two code
paths, opposite behaviour, no warning. 76's "the shortfall is a gold budget"
described the field, not the agent seat, where gold *climbs* past its floor.

### 86.2 The fix

`_targets` lifted out of `GreedyPolicy` into a module-level `reroll_targets`
that both callers share -- a second copy is what caused this. In the teacher:

* a target outranks synergy and cost in `buy_key`: a fourth copy of the carry
  beats a stronger unit the plan will never star up;
* targets are never sold off the bench, since nine copies must be *held* long
  enough to combine and the existing `_copies_owned < 2` guard would sell
  singles of the carry;
* with nothing yet held `reroll_targets` is empty, so any unit at the target
  cost counts as a candidate carry -- otherwise the plan can never start. The
  commitment then emerges from what the shop offered, as in `GreedyPolicy`.

Per-game peak copies of one champion, and 3-stars reached:

| | peak copies | 3-stars |
|---|---|---|
| before | 0, 0, 0, 0, 0, 0 | 0 every game |
| **after** | **8, 9, 9, 9, 9, 8** | **0, 1, 1, 1, 1, 0** |

### 86.3 What it is worth

300 shared seeds, paired against 84's identical run:

| econ | before | after | change |
|---|---|---|---|
| no-econ | 4.823 | 4.823 | **identical** |
| standard | 4.213 | 4.213 | **identical** |
| fast8 | 4.337 | 4.337 | **identical** |
| **slowroll6** | **6.077** | **4.867** | **-1.210, t=-8.72** |
| hyperroll | 4.877 | 5.203 | +0.327, t=+2.41 |

The three archetypes without `target_cost` are **bit-identical placement for
placement across 300 seeds** -- the blast radius is exactly the two reroll
plans, which is what a correct fix predicts.

`slowroll6` gains 1.210 and moves from worse-than-no-economy to near parity.
It remains 0.653 behind `standard` (t=+4.23), with a boom-or-bust profile --
11.7% firsts against standard's 13.0%, but 21.7% eighths against 8.3% -- which
is what reroll looks like in real TFT.

`hyperroll` got **worse**. Committing to three 1-costs is apparently worse than
buying generically here. Unexplained; recorded as measured.

### 86.4 What this voids

- **84's reroll rows.** `slowroll6` 6.077 and `hyperroll` 4.877 measured
  archetypes with the reroll removed. The `standard` / `fast8` / no-econ rows
  are unaffected and reproduce exactly, so 84's conclusion that `standard` is
  the best archetype still holds -- by a smaller margin.
- **85's floor A/B.** The `2-5@20` result (-0.433, t=-3.53) was measured
  pre-fix and should be re-derived before it is used.
- **85.3's timing diagnosis** was partly right -- the window is genuinely short
  -- but targeting, not timing, was the binding constraint.

Every clone and teacher figure using `standard` is untouched, which is every
imitation number in 74-83.

### 86.5 Still open

- Whether 0.653 behind `standard` is the right price for reroll, which is now
  a *fidelity* question that can finally be asked, since the plan executes.
- Why `hyperroll` degrades under targeting.
- Re-derive 85's floor sweep on the fixed teacher.
- Five defects this session were one code path honouring a setting another
  ignored (79.5, 83.3, 86.1). No mechanism warns when a declared field is read
  by one consumer and not another.

---

## 87. The roll floor is not a lever, and a guard for declared fields (08-07)

86.5 left two items. Both are closed here.

### 87.1 85's floor sweep, re-derived on the fixed teacher

86.4 voided it: the sweep was measured against a teacher that ignored
targeting. Re-run identically, 300 shared seeds, both controls holding
(`standard` 4.213, incumbent now 4.867):

| arm | pre-fix | post-fix | vs incumbent | t |
|---|---|---|---|---|
| 3-2@50 (incumbent) | 6.077 | 4.867 | -- | -- |
| 3-2@30 | 5.967 | 4.913 | +0.047 | +0.33 |
| **2-5@20** | **5.643 (-0.433, t=-3.53)** | **4.753** | **-0.113** | **-0.81** |
| 3-2@0 | 6.053 | 5.157 | +0.290 | **+2.11** |

**85's finding evaporated.** "Starting earlier is worth 0.433 (t=-3.53)" reads
-0.113 (t=-0.81) once targeting works. It was compensating for the defect: an
earlier start gave more shops to stumble into copies by accident. With the plan
buying deliberately, it buys nothing.

Rolling everything is now *significantly worse* (+0.290, t=+2.11) rather than
neutral -- gold spent destroying interest is gold not spent on target copies.

**The roll floor is not a lever.** The incumbent is fine and needs no change.

### 87.2 A guard for declared fields

Six defects this session were one code path honouring a declared setting while
another ignored it (79.5, 83.3, 86.1). The encoder has a guard for exactly this
-- `test_layout_options_covers_every_encoder_option` -- and it caught a real one
during 86's gate: `unit_range` was added to `ObservationEncoder` and not to
`LAYOUT_OPTIONS`, which would have made self-play seats mis-encode, the same
381-vs-418 failure `copy_counts` once caused. `EconStrategy` had no equivalent.

`tests/test_econ_fields.py` adds one. It must be **behavioural**, not textual: a
grep reports **zero** references to `level_targets` and `roll_floors` in the
teacher, which uses both through `econ.target_level()` / `econ.roll_floor()`
accessors. A text audit would be confidently wrong in both directions.

For each field, a variant that must change behaviour; assert the action
sequence differs. Plus a coverage test so a new field cannot slip past
unexercised.

**Two ways it was vacuous before mutation testing caught them:**

* `roll_floors={}` asserted nothing. The teacher falls back to `save_floor`
  when no override applies, and `SLOWROLL6`'s only entry (3-2 -> 50) *equals*
  its `save_floor` of 50. Now `{"2-1": 0}`.
* A 900-step budget truncated before stage 4, where `slowroll6` first rolls, so
  two identical openings were compared.

**And a limitation, established rather than assumed.** Reverting 86's buy-side
targeting *alone* leaves the cases passing: `target_cost` still reaches the
bench-sell guard. Only reverting **both** use sites -- the actual pre-86 state
-- fails `target_cost` and `target_count`. The test detects a field reaching the
teacher at all, not that every consumer honours it. A field gaining a second
consumer that ignores it would still slip through.

### 87.3 Still open

- Whether 0.653 behind `standard` is the right price for reroll -- the fidelity
  question, now askable because the plan executes.
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).
- The imitation ceiling is unchanged: 81 showed agreement and placement
  decoupled, and nothing since bears on it.

---

## 88. The level curve is at a local optimum; the economy is exhausted (08-07)

The last untested economy lever. 84 settled archetype selection, 87.1 settled
roll floors, 86 fixed reroll targeting (which `standard` does not use). The
curve inside `standard` was hand-written in 74 and adopted on the strength of
the +0.610 that having *any* economy bought -- never tuned.

Economy is the one improvement class measured to transmit to the clone (89%,
entry 75), so a gain here would reach the agent. 300 shared seeds, teacher-side:

| arm | placement | vs incumbent | t |
|---|---|---|---|
| **incumbent** | **4.213** | -- | -- |
| late-push (8 and 9 a stage earlier) | 4.227 | +0.013 | +0.15 |
| early-6 (level 6 a round sooner) | 4.373 | +0.160 | +1.27 |
| cap-8 (never level past 8) | 4.393 | +0.180 | **+4.49** |
| late-hold (hold 7, bank, jump) | 4.627 | +0.413 | **+4.69** |

No arm beats it; the nearest is indistinguishable and three are worse. The
incumbent reproduced 4.213 exactly.

**`cap-8` is significantly worse (+0.180, t=+4.49)**, which answers a real open
question rather than being a null: levels 9 and 10 pay for themselves despite
the gold they cost.

### 88.1 What this closes

| economy lever | status |
|---|---|
| archetype selection | settled -- `standard` best, `fast8` indistinguishable (84) |
| reroll targeting | fixed, worth -1.210 on `slowroll6`, but `standard` unaffected (86) |
| roll floors | not a lever (87.1) |
| PICK_OFFERING | -0.006 contribution, negligible (84) |
| **level curve** | **local optimum (88)** |

The teacher is about as good as hand-written heuristics get here: **4.213**,
0.287 above parity, and every economic knob measured.

**86's -1.210 does not move the agent.** It is on `slowroll6`, which the
teacher does not run; `standard` was bit-identical before and after. The
largest fix of the session corrected the map, not the territory.

So the binding constraint is what 81 established and nothing since has touched:
at ~96% agreement the residual disagreement does not carry placement, so no
imitation method closes the clone's ~0.5 gap. Improving the teacher is now
exhausted as well.

### 88.2 Still open

- RL from a clone, which is the only remaining path that can *exceed* a
  teacher. Nine prior entries of RL never beat imitation, but all predate the
  validated engine (71.4) and a teacher above parity (74).
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting.

---

## 89. PPO still destroys a competent policy; only the anchor prevents it (08-08)

88 exhausted the teacher and 81 exhausted imitation, leaving RL from a clone as
the only path that can *exceed* a teacher. Nine prior entries of RL never beat
imitation, but all predate the validated engine (71.4) and an above-parity
teacher (74) -- so entry 60's collapse deserved a re-derivation rather than a
citation.

Three arms, all `--init-from runs/bc-econ-s0` (4.740), 150k steps, self-play,
differing only in `--bc-anchor-coef`:

| steps | coef 0.0 | coef 0.1 | coef 0.5 |
|---|---|---|---|
| 0 | 5.033 | 5.033 | 5.033 |
| 25k | 6.733 | 4.983 | 4.767 |
| 50k | 7.500 | 4.883 | 4.700 |
| 75k | **7.967** | 4.783 | 4.383 |
| 125k | **8.000** | 4.783 | 5.633 |
| 150k | **8.000** | 4.717 | 4.783 |

(n=60 in-run; the anchored columns wander inside a +/-0.6 CI and have no trend.)

### 89.1 The collapse reproduces exactly

Without an anchor, PPO walks a competent policy monotonically to **8.000** --
the `do_nothing` baseline, to three decimals. Entry 60's failure was **not** an
artefact of the voided world or a weak starting policy: validated engine,
teacher 0.287 above parity, clone at 4.740, same result.

Same mechanism, too. Action mix over three games:

| run | top actions | actions/game |
|---|---|---|
| **coef 0.0 (collapsed)** | **REROLL 35%, END_PLANNING 21%** | **89** |
| coef 0.5 | BUY 29%, SELL 20% | 396 |
| `bc-econ-s0` | BUY 34%, SELL 25% | 389 |

Mass flowed to the two always-legal, no-immediate-consequence actions entry 63
measured as the drift targets (END_PLANNING +3.61, REROLL +1.58). The policy
ends planning immediately and takes a quarter the actions of a healthy one.

### 89.2 Anchored, it holds and never moves

Paired against the clone it started from, 300 shared seeds:

| arm | placement | vs its own clone | t |
|---|---|---|---|
| `bc-econ-s0` (init) | 4.740 | -- | -- |
| coef 0.5 | 4.847 | +0.107 | +0.67 |
| coef 0.1 | 4.873 | +0.133 | +0.89 |

Both flat, both trending very slightly worse. A 5x change in anchor weight
moves nothing, so this is not a tuning question.

**The anchor is load-bearing, not a refinement.** It was introduced as a
countermeasure against drift; it is the only thing holding the policy up.
Remove it and the policy is destroyed; keep it and the policy cannot move,
because the auxiliary loss pulls it back toward its initialisation. The flat
pilot was the honest result, not an artefact of the hyperparameter -- which was
the confound this sweep existed to rule out.

### 89.3 What it means

RL is not currently a path here, and not because PPO is under-tuned. Entry 61
measured the advantages directly and found the optimiser doing exactly what it
should: the signal favours `REROLL`. That diagnosis now survives into the
validated world.

So the constraint is the **reward**, which this project has never seriously
changed. Placement arrives once, at the end of a ~450-action episode, so nearly
every action receives credit it did not earn.

### 89.4 Still open

- Whether the reward signal can distinguish a good action from a null one at
  all. **Measure that before building shaping** -- the ceiling-first discipline
  that saved a training run in 84 and would have saved four hours in 85.
  `--reward-shaping` and `--shaping-mode potential` exist and are untested
  against this failure.
- All three arms are single-seed. A collapse to 8.000 is an order of magnitude
  outside 83's 0.14 noise floor and readable at n=1; the two flat results are
  not, though a 5x anchor change producing nothing is itself evidence.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting.

---

## 90. The drift is END_PLANNING and BUY, not REROLL (08-08)

89 established that PPO destroys a competent policy without an anchor and
cannot move with one, and located the constraint in the reward. 89.4 said to
measure whether the signal distinguishes a good action from a null one
**before** building shaping -- the ceiling-first discipline that saved a
training run in 84 and would have saved four hours in 85.

`advantage_probe.py` reads PPO's own `RolloutBuffer` after
`compute_returns_and_advantage`, so what is measured is what the optimiser
consumed. 24576 transitions at the `bc-econ-s0` clone, shaping off:

| action kind | n | share | mean adv | % positive | vs pooled 45.5% |
|---|---|---|---|---|---|
| PICK_OFFERING | 197 | 0.8% | +0.0052 | 55.3% | +9.8pp |
| **END_PLANNING** | 1388 | 5.6% | **+0.0004** | **50.1%** | **+4.6pp (t~+3.4)** |
| PLACE | 2698 | 11.0% | -0.0014 | 48.4% | +2.9pp |
| SELL | 6490 | 26.4% | -0.0018 | 49.0% | +3.5pp |
| SELECT | 2762 | 11.2% | -0.0050 | 46.1% | +0.6pp |
| REROLL | 471 | 1.9% | -0.0051 | 46.3% | **+0.8pp (t~+0.35)** |
| BUY_XP | 1431 | 5.8% | -0.0054 | 45.1% | -0.4pp |
| **BUY** | **8195** | **33.3%** | **-0.0109** | **41.1%** | **-4.4pp (t~-8.0)** |
| EQUIP | 795 | 3.2% | -0.0123 | 41.9% | -3.6pp |
| PICK_AUGMENT | 149 | 0.6% | -0.0282 | 32.9% | -12.6pp |

### 90.1 REROLL is at the mean

**REROLL is not preferentially rewarded** (+0.8pp, t~+0.35). Entry 61's
conclusion survives into the validated world.

But 60 and 61 both framed the collapse as *converging onto REROLL*, and named
it in advance. `END_PLANNING` is the most-rewarded common action and `BUY` --
**a third of all transitions** -- is the least, both significant. PPO moving
mass from BUY toward END_PLANNING is a complete and sufficient account of a
policy that ends planning immediately and takes 89 actions per game instead of
389 (89.1). REROLL rising to 35% in the collapsed policy is a *consequence* of
mass leaving BUY, not a preference for rolling.

Naming the suspect in advance is what hid this for thirty entries. The probe
now reports the extremes rather than a named kind.

### 90.2 What it does not establish

That buying is bad. Advantage is `return - V(s)`, and the critic's held-out EV
is ~0.58 (58.2 puts the knowability ceiling near 0.5). BUY happens in
systematically identifiable states -- holding gold, board not yet full -- so a
critic that misestimates those states hands every BUY in them the same bias.
This is as consistent with **credit misassignment** as with buying being
genuinely bad, and the advantages alone cannot separate them.

That distinction decides the fix: a better critic, or a reward that does not
lean on it.

### 90.3 Still open

- Separate the two readings of 90.2. The entry-82 counterfactual machinery
  measures an action's *true* effect on placement; comparing that against the
  advantage the same action receives would show directly whether the signal
  tracks the truth. This is the ceiling measurement 89.4 asked for and it is
  not yet done.
- Only then, shaping. `--reward-shaping` and `--shaping-mode potential` exist
  and remain untested against this failure.
- Single seed, one clone. The BUY and END_PLANNING gaps are many SE wide, but
  they describe *this* policy's state distribution.

---

## 91. Single actions do not measurably move placement (08-08)

89.4 asked for this before any shaping work: can the reward distinguish a good
action from a null one? 90 measured PPO's advantages; 90.3 said to compare them
against an action's *true* effect, since advantages alone cannot separate
"buying is bad" from "the critic misestimates states where buying happens".

The counterfactual: replay to a state, substitute an alternative drawn from
**the policy's own distribution**, let the policy play on, difference the final
placements. Positive means losing that action hurt. Per kind, this is directly
comparable to 90's per-kind advantages.

1098 deviations at `bc-econ-s0`:

| kind | n | true cost | t | PPO adv | adv rank | cost rank |
|---|---|---|---|---|---|---|
| BUY_XP | 79 | +0.114 | 0.84 | -0.0054 | 7 | 1 |
| SELL | 331 | +0.033 | 0.39 | -0.0018 | 4 | 2 |
| BUY | 328 | -0.088 | -1.11 | -0.0109 | 8 | 3 |
| SELECT | 97 | -0.206 | -1.32 | -0.0050 | 5 | 6 |
| PLACE | 132 | -0.280 | -1.82 | -0.0014 | 3 | 7 |
| END_PLANNING | 68 | -0.294 | -1.12 | +0.0004 | 2 | 8 |

### 91.1 Nothing is significant, and that is the finding

Largest |t| is **1.82**. Overall mean across all 1098 samples is -0.101
(t~-1.4). The correlation between advantage and true cost is **r = -0.38 over
6 kinds** -- with n=6, |r| > 0.81 is needed for significance, so **the signal
is not shown to be inverted**. 90.2's two readings remain unseparated, and the
reason is that the ground truth itself is unmeasurable here.

**Within the policy's own action distribution, a single action does not
measurably change placement.** There is essentially nothing for the advantage
signal to track.

### 91.2 Why 82 found an effect and this did not

82 substituted the **teacher's** action and measured -0.194 (t=-2.28) pooled
across positional kinds. This substitutes an alternative from **the clone's own
peaked distribution** (training logits ~28) and measures nothing.

The difference is the quality of the alternative, not the method. The clone's
top-two actions are near-equivalent, so choosing between them does not matter;
the teacher's action is meaningfully better, so substituting it does. Both
results are consistent, and together they say the per-action signal exists only
against a *better* policy, not within one.

### 91.3 What it means for RL

Per-action credit assignment from terminal placement is not achievable here at
practical sample sizes. About 400 actions per episode each carry no
individually measurable effect, while collectively determining an outcome
spanning 7 placements.

PPO's advantages are not so much wrong as **fitting noise**. That is a complete
account of 89: unanchored, the policy follows noise to the `do_nothing`
attractor; anchored, it cannot move because the anchor is the only real signal
present. It also explains why 60's four proposed mechanisms were each refuted
-- critic quality, entropy, reward sparsity, transient improvement. None was
the cause because the cause is that the per-action signal-to-noise is near
zero.

### 91.4 What would follow

- **Shaping is now the indicated direction rather than a guess**: a dense
  potential-based signal exists precisely to supply per-action information that
  terminal reward cannot. `--reward-shaping` / `--shaping-mode potential` are
  untested against this failure.
- But shaping must be *validated the same way* before it is trained against:
  re-run this probe with shaping on, and check whether shaped per-action credit
  correlates with true cost. A shaped signal that also fails to track truth
  would be a denser source of the same noise.
- A method that does not need per-action credit -- evolutionary search over
  policy parameters, or search at inference -- sidesteps the problem entirely.
  Search was measured at -0.277 for the teacher (79.7) and does not transmit by
  cloning, but it does not require credit assignment.

### 91.5 Still open

- Single clone, single seed. The nulls are wide, and "not significant" at
  n~100-300 per kind is weaker than "zero".
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting.

---

## 92. Shaping concentrates all credit on END_PLANNING (08-08)

91.4 named shaping the indicated direction and said to **validate it the same
way before training against it** -- a shaped signal that also fails to track
truth would be a denser source of the same noise. This is that check, and it
fails much harder than expected.

Mean shaped reward per action kind, `bc-econ-s0`, 40 episodes,
`shaping_mode="potential"`, against 91's measured true costs:

| kind | n | mean shaped r | true cost (91) |
|---|---|---|---|
| **END_PLANNING** | 1126 | **0.01492** | -0.294 |
| SELL | 5125 | 0.00023 | +0.033 |
| PLACE | 1537 | 0.00015 | -0.280 |
| BUY | 6482 | 0.00011 | -0.088 |
| BUY_XP | 1121 | 0.00000 | +0.114 |
| SELECT | 1548 | -0.00000 | -0.206 |

`END_PLANNING` receives **~100x more shaped credit than any action that builds
the board**. Correlation with true cost is r = -0.51 across 6 kinds -- not
significant at n=6, and beside the point next to the concentration.

### 92.1 Why

`_shaping_reward` is called **only at round transitions**, and its docstring
says so: "Dense per-round shaping". Phi = 0.03 * board_strength + 0.01 *
hp_fraction, and a round's entire Phi change -- every purchase, every
placement, and the combat HP swing -- is attributed to whichever action
advanced the round. That action is always `END_PLANNING`.

So shaping is dense *per round* (~17 actions), not per action. It cannot supply
the per-action credit 91 showed is missing, **by construction**.

### 92.2 It would make 89's collapse worse

90 measured `END_PLANNING` as already the most-rewarded common action
(+4.6pp positive rate) with shaping **off**, and 89.1 showed the unanchored
policy collapsing to 89 actions per game -- ending planning immediately.
Turning shaping on multiplies the credit on exactly that action by ~100.

Every RL run in 89 had shaping off (`--reward-shaping` not passed). Had it been
on, the collapse would very likely have been faster. This is the second time a
plausible next step would have made things worse: 80's `centre` placement rule
was the first.

### 92.3 The implementable fix

Evaluate the potential **after every action**, not every round. Phi is already
a pure function of board strength and HP, so a `PLACE` that improves the board
would be credited at the moment it happens rather than pooled into the round's
terminal action.

The telescoping guarantee is unaffected in kind -- `F = gamma*Phi(s') - Phi(s)`
applied on every transition still sums to a boundary term, so it cannot change
which policy is optimal (Ng, Harada & Russell). What changes is *where the
credit lands*, which is the entire problem 91 identified.

**Not yet measured.** The same validation applies: re-run the credit probe with
per-action potential and check the correlation against 91's true costs before
any training run is spent on it.

### 92.4 Still open

- Implement and validate per-action potential.
- 91's caveat stands: the true costs it compares against are themselves not
  significant, so a correlation against them is weak evidence either way. The
  *concentration* finding does not depend on them.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting.

---

## 93. Fixing the credit concentration does not stop the collapse (08-08)

### 93.1 Why

92.3 proposed evaluating the potential after **every action** rather than every
round, so a `PLACE` that improves the board is credited when it happens instead
of being pooled into the round's terminal `END_PLANNING`. Implemented as a third
`SHAPING_MODES` entry (`per_action`), leaving `potential` and `bonus` untouched
so every prior number still reproduces — including 89's collapse, which is the
control this is measured against.

The validation 92.3 required, run before spending a training run:

| | `potential` | `per_action` |
|---|---|---|
| concentration on `END_PLANNING` | 64.6x | **12.0x** |
| `PLACE` credit | 0.00015 | **0.00115** |
| r vs 91's true costs | -0.51 | -0.56 |

The fix works as designed: concentration down 5.4x, `PLACE` credit up 7.7x. The
residual 12x is legitimate — the combat HP swing lands on the round-advance step
and is not attributable to any single planning action. The correlation did not
improve, but 91 showed the true per-action costs are not individually
significant, so there may be nothing there to correlate with.

### 93.2 The test, and the outcomes named in advance

Not "does it improve a good policy" but **can the signal hold a policy up on its
own** — 89 established the BC anchor is the only thing preventing collapse. Two
unanchored (`--bc-anchor-coef 0.0`) 150k runs from `runs/bc-econ-s0` (5.033),
one per shaping mode. Outcomes named before the runs finished:

* `per_action` holds, `potential` collapses — fix confirmed. 92.2 predicted
  `potential` would collapse *faster* than no shaping.
* both collapse — credit distribution was not the binding constraint.
* both hold — shaping in general is the fix; would need checking for reward
  hacking (shaped term dominating the terminal signal).

### 93.3 Both collapse

| steps | `potential` | `per_action` |
|---|---|---|
| 0 | 5.033 | 5.033 |
| 25k | 5.867 (floor 30%) | 6.467 (floor 43%) |
| 50k | 6.983 (floor 60%) | 7.733 (floor 90%) |
| 75k | — | 7.967 (floor 97%) |
| 150k | — | **7.733 (floor 88%)** |

The second outcome. `per_action` gave back the entire 5.033 start by 75k and
finished *worse than the scripted baseline* (6.467) — the log's "+0.267 over
random" is framing, not a result. Same trajectory as 89's unshaped unanchored
run.

Redistributing the credit did not help, because 91 had already shown there is no
per-action signal to redistribute: 1098 counterfactual deviations, max |t| =
1.82. **Concentration was real and was fixed; it was not the binding
constraint.** 91 is the deeper finding and this is its consequence, not a
separate failure.

### 93.4 A prediction that failed, and a stopped run

92.2 predicted `potential` shaping would make the collapse *faster*. It is
consistently **slower** — better at both shared checkpoints (5.867 vs 6.467,
6.983 vs 7.733) with half the floor rate. The mechanism proposed there is wrong
in sign. Both still collapse, so this changes no conclusion, but it is recorded
as failed rather than quietly dropped.

The `potential` arm was **stopped at 50k**, not run to 150k. Its per-step cost
decayed 15x (~1400 -> ~90 steps/min) while `ep_len_mean` stayed flat at ~390, so
steps were getting more expensive, not longer: the self-play pool grows every
25k and every opponent seat runs policy inference. `per_action` masked this by
collapsing — dead seats are cheap. Its trajectory was already unambiguous at 50k
and it is a control arm, so the remaining runtime bought precision on a
prediction already seen to fail.

Single seed. Adequate here: 7.7 vs 5.0 is an order of magnitude outside 83's
0.14 noise floor. It would not license a claim of *improvement*, and none is
made.

### 93.5 What this closes

Shaping is now eliminated the same way label noise (79), distribution shift (81)
and the observation (83) were. Every mechanism proposed for the RL failure that
operates by **improving the per-action signal** has been measured and none
moved placement. That is consistent with 91's finding that the per-action signal
does not exist to be improved.

### 93.6 Still open

- 91.4's direction is now the surviving one: methods needing no per-action
  credit — evolutionary/population search over policy parameters, or search at
  inference. Neither has been tried.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).
- The self-play pool's per-step cost growth is a measurement hazard for any
  future long run where the policy *does not* collapse. Not a bug; worth knowing
  before budgeting.

---

## 94. The fitness landscape around the clone is flat, then a cliff (08-08)

### 94.1 Why

93 closed the last of the per-action fixes. Label noise (79), distribution
shift (81), observation width (83) and shaping (93) all work by improving the
*per-action* learning signal, and none moved placement, because 91 had already
shown no single action measurably changes the outcome.

91.4's surviving direction is methods needing no per-action credit.
Population/evolutionary search is the cheapest: perturb the policy
*parameters*, play whole episodes, keep what places better. It never asks which
action was responsible.

It has its own precondition, and this measures it before a search is spent. ES
climbs a ranking of perturbations by episode-level fitness, so that ranking must
be **reproducible**. Each perturbation is evaluated on two *disjoint* seed
blocks and the two are correlated across members. `r` is the reliability of the
ranking, and it decides the direction.

### 94.2 The sigma grid had to be measured, not guessed

The first grid (0.002-0.05) was mostly dead on arrival: at sigma 0.002 a
perturbation changed **0 of 120 actions**. The clone's logits are ~28, so small
weight changes leave the argmax intact. Measured across 600 fixed states:

| sigma | 0.002 | 0.005 | 0.01 | 0.02 | 0.05 | 0.1 | 0.2 | 0.4 |
|---|---|---|---|---|---|---|---|---|
| decisions changed | 0.5% | 0.6% | 0.8% | 1.3% | 2.9% | 4.8% | 11.2% | 28.2% |

Two of the three original arms would have measured an unchanged policy against
itself and reported "no signal" for entirely the wrong reason.

The first attempt at this curve was also wrong, and non-monotonically so (11.8%
at sigma 0.002 against 5.7% at 0.005). It measured action changes *along the
perturbed rollout*: once one action differs the trajectory diverges and every
later step compares two different games. Measuring on a fixed set of base states
gives the clean curve above. Same divergence hazard `disagreement_cost.py`
handles by replaying from seed -- it recurs whenever two policies are compared
by playing them rather than by querying them.

### 94.3 Flat, then a cliff

12 members per sigma, two disjoint 40-game blocks, base = 5.037.

| sigma | mean | best | sd(A) | noise | sd_true | r(A,B) |
|---|---|---|---|---|---|---|
| 0.05 | 4.811 | 4.475 | 0.287 | 0.358 | **~0** | -0.37 |
| 0.15 | 5.079 | 4.688 | 0.282 | 0.310 | **~0** | 0.24 |
| 0.40 | 7.263 | 5.537 | 0.885 | 0.121 | 0.877 | 0.99 |

`sd_true^2 = sd(A)^2 - noise^2` is **negative** at both usable sigmas: the
spread between perturbations is smaller than the noise on measuring it, so the
members are statistically indistinguishable. There is no ranking to climb.

At sigma 0.4 there is a real, highly reliable ranking (r=0.99) -- of **damage**.
Every member is ~2.2 placement worse than base. The script's own verdict column
printed `followable` there, which is why it now checks direction before
reliability: a reproducible ranking that is entirely downhill is not a gradient.
**A reliability statistic is meaningless without the direction it points**, the
same shape of error as lesson 6.

Winner's curse, checked rather than assumed: best-of-12 at sigma 0.05 was 4.475;
expected best-of-12 under *pure noise* is 4.625. The apparent winner is what
noise alone produces. Selecting it is selecting noise -- 91's failure exactly.

### 94.4 A lead not claimed

At sigma 0.05 the whole population averaged 0.226 better than base (t=-4.57),
which would suggest the BC policy sits on a sharp point that smoothing helps.
Not claimed, for two reasons. The t treats 12 member means as independent when
they share seed blocks, so a seed-driven bias shifts all members together and
never enters the error term -- anti-conservative. And sigma 0.15 gives +0.042,
so the effect is not monotone in sigma the way real smoothing would be. Testing
it needs per-seed pairing, which the first run did not save; the probe now
stores per-seed placements so it can be tested.

### 94.5 What it does and does not kill

It does **not** strictly kill ES. The ES update averages fitness noise across
the population, so per-member reliability near zero is survivable given enough
members. What decides it is `sd_true`, which this run only **bounds** (below
~0.15). At that upper bound a population of 50 gives a usable gradient at ~2000
episodes per generation -- 20+ hours for a full search, with the payoff scaling
on a number never measured. If `sd_true` is really 0.05, the same run is worth
nothing.

So the bound has to become a number before the budget is spent: sigma 0.05, 10
members, 200-game blocks. Running.

### 94.6 Still open

- `sd_true` at sigma 0.05 (running).
- Whether the sigma-0.05 population improvement in 94.4 survives paired testing.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).
- Search at inference, the other 91.4 direction, still untried.

### 94.7 Resolved: sd_true is real, tiny, and too expensive to climb

sigma 0.05, 10 members, two disjoint **200**-game blocks. Base 4.795 on both
blocks (coincidence -- both sum to 959; the blocks were checked disjoint and
their per-seed placements differ).

| | sd(A) | noise | sd_true | r(A,B) |
|---|---|---|---|---|
| 40-game blocks (94.3) | 0.287 | 0.358 | ~0 (negative) | -0.37 |
| **200-game blocks** | 0.178 | 0.135 | **0.117** | 0.10 |

At the larger block size `sd_true^2` is finally positive: perturbations really
do differ. But the second estimator disagrees -- computing it from the
two-block averaged fitness gives **0.040**, not 0.117. Both estimate the same
quantity, so the gap is small-sample instability (a variance estimate on 10
members carries ~45% relative error). The defensible statement is
**sd_true ~ 0.04-0.12**, which confirms 94.5's upper bound rather than
improving on it. The observed r=0.10 and the r=0.43 implied by the variance
decomposition also agree, given the ~0.38 standard error on a correlation at 10
members.

**94.4's lead is refuted.** Paired properly -- each member against base on the
same 400 seeds -- the population is 0.063 better, t=-1.92. The unpaired version
read 0.226 at t=-4.57. The caution in 94.4 was right and the effect is about a
third the size and not significant. There is no evidence the BC policy is
improved by parameter smoothing.

**The cost.** ES does not need per-member reliability; the population averages
the noise out. At sd_true ~ 0.1, and measured throughput of 4400 episodes per
38 minutes:

| episodes/member | noise | members for SNR 3-5 | episodes/gen | wall/gen |
|---|---|---|---|---|
| 200 | 0.135 | 50 | 10,000 | ~86 min |
| 40 | 0.358 | 115 | 4,600 | ~40 min |

A 100-generation search is **3-6 days of compute**, with an unknown per-
generation step size, against a target gap of a few tenths of a placement. The
precondition passes and the economics do not.

**Not spent.** The other 91.4 direction -- search at inference -- is far cheaper
to test and already has a positive precedent here in the teacher's positional
search (79). It also needs no learning signal, which is the thing 91, 93 and 94
have now each shown is absent.

Scope: this tests sigma 0.05 only. A signal at some sigma between 0.05 and 0.4
is not excluded, though 94.3 measured 0.15 as flat and 0.4 as uniformly
destructive, so there is little room left for one.

### 94.8 Still open (revised)

- Search at inference for the planning decisions, not just positioning.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).
- ES remains technically viable at ~3-6 days of compute if the cheaper
  directions are exhausted.

---

## 95. Throughput: the reframe, and how little of it is reachable (08-08)

> **95.1's reframe is REFUTED by entry 96.** The throughput engineering in
> 95.2-95.4 stands; the inference that 89-94 were measuring sample size does
> not. A 5M-step run (33x the data) collapsed to 8.000 by 600k and stayed.

### 95.1 The number that reframes entries 89-94

**Every RL run in this project has seen ~378 games of TFT.** 150k timesteps
divided by an `ep_len_mean` of 397. PPO on a game with this branching factor is
normally given 1e7-1e8 steps; this is 1.5e5.

Entries 89-94 each measured "the learning signal is absent" and read it as a
statement about *method*. At 1e-3 of the usual data budget it is at least
partly a statement about *sample size*. The probes were sound; the frame around
them was too confident.

Not fully self-cancelling: 91's finding that single actions do not measurably
move placement is partly about the environment's outcome variance, which no
training budget changes -- eight near-equal seats make placement noisy however
long you train. But high variance and tiny samples compound, and both point at
the same fix, so it strengthens the case rather than weakening it.

### 95.2 Micro-optimisation bought 5%

Predicted 3-10x from hoisting dispatch out of the combat hot path. Measured
**1.05x**. Four changes, all verified fingerprint-identical by
`scripts/engine_bench.py`:

* `effects.hooks_for` and `trait_effects.trait_hooks_for` memoised -- they
  rebuilt a filtered list on each of ~3.6M calls per benchmark game, nearly
  always to return nothing. Registration clears the caches.
* the twice-per-tick `sorted(self.units, key=uid)` cached, invalidated when a
  summon appends.
* empty-list guards on the six `status_effects` predicates, which built a
  generator frame per call to iterate an empty list ~10.9M times per game.

Why it could not have worked: **178M Python function calls per 4 games.** The
cost is interpreter overhead spread across millions of tiny operations, not a
hotspot that can be deleted. There is no 10x here without compiling combat.

The first profile was also taken against a *random* policy, which places 8th
every game and dies in stage 2, so it never simulates a late-game board.
Optimising against it would have tuned the cheapest rounds in the game. The
benchmark now plays the scripted teacher. **A profile is only as representative
as the workload driving it.**

### 95.3 `DummyVecEnv` was stepping every env serially

Training built its vector env with `DummyVecEnv`, which steps envs **in one
process, one after another**. `--envs 4` bought nothing on a 12-core machine,
which is the whole explanation for 66 steps/sec against 264 for a single env.

Fixing it to `SubprocVecEnv` gives **1.39x**, not the 8-10x the core count
suggests:

| vec | envs | steps/sec |
|---|---|---|
| dummy | 4 | 264 |
| dummy | 12 | 278 |
| subproc | 12 | **367** |

A straggler effect: the vector env waits for every worker at every step, and
per-step cost here is wildly unbalanced -- a combat round is ~100x a planning
action -- so throughput is gated by whichever env is mid-combat. This is
exactly why `evaluate_scripted_parallel` scales and this does not: the eval
harness parallelises at **episode** granularity with no per-step sync.
Step-lockstep parallelism does not suit an env with variable step cost.

`--vec subproc` refuses to combine with self-play rather than silently training
against a stale snapshot pool, and the env options are passed explicitly into
each child: `build_env` reads a module global that `spawn` leaves empty in the
child, so children would otherwise have built the *default* observation layout
while the parent's policy expected the configured one. Caught before running,
not after.

### 95.4 What the budget actually becomes

Training carries ~4x overhead on top of env stepping, most of it evaluation
(360 episodes run serially per run, against a parallel harness that already
exists).

Parallel evaluation was verified equivalent before being used, not assumed:
24 episodes, serial 65.3s vs parallel 13.6s (**4.82x**), with **every placement
identical**, not merely the mean. A silently different eval would have shifted
every metric in the run with nothing to flag it.

Measured end to end at the real eval cadence (50k steps, `--envs 12 --vec
subproc --eval-workers 10`), rather than by multiplying the parts:

| scope | before | after | |
|---|---|---|---|
| marginal rate (scales with steps) | 72 | **184** steps/s | **2.55x** |
| end-to-end on a 50k run | 66 | 101 steps/s | 1.53x |

The two differ because ~190s of fixed cost (baselines, final evaluation, setup)
dominates a short run and is negligible in a long one. For a 5M run the fixed
cost is 3 minutes of 7.6 hours, so the marginal rate is the one to project
from.

**2.55x, not 100x.** 1e7 steps stays out of reach without compiling combat. But
**5M steps is a 7.6h overnight run, and that is ~13,000 episodes against the
378** every conclusion in 89-94 rests on -- enough to test whether more data
changes the answer, which is not the same as a full-scale RL run.

Where the 2.55x came from, against what was predicted:

| change | measured | predicted |
|---|---|---|
| engine micro-optimisation | 1.05x | 3-10x, wrong |
| `DummyVecEnv` -> `SubprocVecEnv` | 1.39x | 8-10x, wrong |
| serial -> parallel evaluation | 4.82x on eval | 1.8x, understated |

The two changes predicted to matter did not; the one treated as secondary
cleanup carried the result. **The engine was never the bottleneck -- evaluation
was**, running 360 episodes serially while 11 cores idled.

### 95.5 Still open

- The 5M-step run itself, and what it says about 89-94. It trains against the
  **scripted field**, not self-play: `--vec subproc` cannot hold the mutable
  snapshot pool. That makes it a different experiment from 89-93, to be
  labelled rather than compared across.
- Compiling combat (Cython/numba/rewrite) is the only route past ~165 steps/sec.
  Not attempted; large, and it would need the fingerprint as its safety rail.
- Whether 0.653 behind `standard` is the right price for reroll (fidelity).
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).

---

## 96. 33x the data changes nothing: unanchored PPO collapses and stays (08-09)

### 96.1 The test 95 was written to enable

95.1 reframed 89-94: every RL run in this project had seen ~378 games, so "no
learning signal" might have been a statement about sample size rather than
method. 95's throughput work existed to test that. First run at the new budget:
**5M steps, unanchored (`--bc-anchor-coef 0.0`), 12 subproc envs, against the
scripted field**, initialised from `bc-econ-s0` (5.033).

| steps | placement | floor rate |
|---|---|---|
| 0 | 5.033 | -- |
| 300k | 7.867 | 92% |
| 600k | **8.000** | **100%** |
| 600k -> 5M | 8.000 | 100% |

~12,594 episodes against the 378 of every prior run. It reaches the floor by
600k and sits there for the remaining 4.4M steps.

### 96.2 95.1's reframe is refuted

**Recorded as a failed prediction.** More data did not change the answer: the
collapse reproduces at 33x the budget and against a *different* opponent field
(scripted, not self-play -- `--vec subproc` cannot hold the mutable snapshot
pool). 89's result was not an artefact of a small sample.

What survives from 95 is only the engineering: the throughput work is real and
the 378-game figure was worth knowing. What does not survive is the inference
drawn from it. **A constraint being real is not evidence it is the binding
one** -- lesson 21, learned in 93 about shaping, and repeated here about data
volume within a day.

### 96.3 The floor is absorbing, so most of the run is uninformative

At 100% last place there is no outcome variance, so there is no gradient to
recover on -- the codebase's own baseline check has flagged this since 18.5
("too little outcome variance to compare against"). Everything after 600k is a
policy sitting in an absorbing state, not evidence about learning. The finding
is entirely in the first 600k; the remaining 4.4M steps only establish that it
does not climb back out, which is worth knowing once and never again.

This is consistent with 91: no per-action signal to learn from, plus a
degenerate terminal signal once the floor is reached.

### 96.4 Throughput came in below projection

5,000,000 steps in 40,610s = **123 steps/sec**, against the 184 projected in
95.4 from a 55k probe. 33% short. Not investigated -- candidates are thermal
throttling over 11 hours, and the subproc straggler effect (95.3) behaving
differently over a long run than a short one. Recorded so the next projection
starts from 123, measured over 11 hours, rather than 184, measured over 5
minutes. **A rate measured over minutes does not necessarily hold over hours.**

### 96.5 What this closes, and what it leaves

Closed: unanchored PPO in this environment, at any data budget reachable
without compiling combat. Combined with 89 (anchored PPO cannot move), 93
(shaping does not help), and 94 (ES has no gradient at usable sigma), every
learning method tried here has now been measured and none beats the scripted
teacher.

Left, and the reason 95's engineering still matters: the agent is being trained
to place well in a simulator with a **known mispricing** -- `slowroll6`, a
mainstream real-TFT line, places 1.8 worse than standard (85, 86) and has sat
under "still open" for ten entries while the RL directions were exhausted one
by one.

A shop-odds check run against this (level 6, 2-cost): 0.0308 per slot, 0.1538
copies per roll, **58.5 rolls** for a 3-star, derived from `shop_odds` and
`pool_sizes` -- both community-documented, and matching real TFT's arithmetic.
So the roll odds are **not** the mispricing, despite `shop_draw_weighting`
being an invented constant. That leaves two candidates:

* **the window** -- 85.3 already located it: gold reaches 50 only at 4-1 and
  the seat is dead by 5-2, ~8 rounds of rolling where real TFT gets roughly
  double. A survival question.
* **the payoff** -- what the 3-star is worth once acquired, governed by the
  invented combat constants (`max_duration_seconds`, `sudden_death_*`,
  `tick_seconds`, movement/projectile speeds). 76 validated the star-vs-slot
  exchange rate against the engine's *own* combat, which cannot detect an error
  in those constants.

Both are testable against real-TFT elimination-stage and game-length
distributions. `scripts/engine_profile.py` already emits the engine's side; the
reference side has never been collected.

### 96.6 Still open

- Fidelity: collect real-TFT reference distributions and compare (the gate).
- Which of window / payoff explains the reroll mispricing.
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41).
- The eval-cadence aliasing found in this run: `_on_step` fires on
  `num_timesteps % every == 0` and `num_timesteps` advances by `n_envs`, so
  `--envs 12 --eval-every 100000` evaluated every **300,000** (LCM). Harmless
  here, silent, and wrong for any `n_envs` that does not divide `eval_every`.

---

## 97. Real-TFT reference distributions: the window is fine, the field dies rich (08-09)

96.5 named the fidelity comparison as the gate on everything downstream and
narrowed the `slowroll6` mispricing to two candidates, **the window** and **the
payoff**. The reference side had never been collected. It has now.

### 97.1 What was collected

1,000 ranked-standard Set 17 matches from NA challenger (8,000 participants)
via Riot's `match-v1`, by `scripts/fetch_riot_matches.py`. Reduced by
`scripts/reference_profile.py`; the engine's side comes from
`scripts/engine_profile.py --fidelity-json --econ mixed` (300 games, 2,400
seats, `rl.opponents.DEFAULT_FIELD`); `scripts/fidelity_compare.py` pairs them.
Both sides import the same aggregation helpers, so the arms cannot drift apart
in how they average.

**Riot gives only end-of-game state per participant, not trajectories.** There
is no reference counterpart to the living-player table `engine_profile` has
emitted since entry 70. What there is is a cross-section: a participant with
`last_round = R` shows their level, gold and board *at R*, because that is when
they died. The engine side is conditioned identically -- each player is
snapshotted going into the round they were eliminated in. The two views are not
interchangeable and the old table is left untouched.

**Four outcomes were named before the run finished** (they are in
`fidelity_compare`'s docstring): window; accumulation; payoff; or all four
axes match and `slowroll6`'s 0.653 is simply correct.

### 97.2 The window hypothesis is refuted. Recorded as a failed prediction

85.3 and 96.5 said the seat gets ~8 rounds of rolling where real TFT gets
"roughly double". It does not.

| | engine | reference | delta | t |
|---|---|---|---|---|
| mean elimination round | 29.78 | 30.36 | **-0.58** | -5.67 |
| mean game length | 37.15 | 36.28 | **+0.87** | +6.33 |

Significant at this n and negligible in size: 0.58 of a round against a
36-round game, and the engine's games are *longer*, not shorter. Max
cumulative gap (KS) 0.143, peaking at 5-4. Whatever prices reroll wrongly, it
is not that the seat dies too early.

### 97.3 The engine fights two rounds real TFT does not

The KS peak has a cause. `data/config.json`'s `realm.rounds` is
`[[1,1],[2,4],[3,4],[4,4]]` -- the Set 17 contested draft of entry 21 replaces
the carousel, and it stops after stage 4. Real TFT has a no-combat round at
**every** `x-4`.

| eliminations on 5-4 and 6-4 | count | share |
|---|---|---|
| engine | 306 / 2,100 | **14.6%** |
| reference | 10 / 7,000 | **0.14%** |

A hundredfold gap, in the stages where 60% of all eliminations happen. The
engine plays two extra PvP rounds per game and grants two fewer draft
acquisitions. This is a concrete, externally-sourced defect, and it is the
first thing in 97 that is unambiguously the *engine* rather than a policy.

The mapping this rests on is validated by the data rather than by its own
arithmetic: real eliminations show a hard trough at every `x-4` (carousel) and
a near-trough at every `x-7` (PvE). An off-by-one would scatter those
structural zeros onto ordinary combat rounds. `tests/test_reference_profile.py`
asserts the trough and was mutation-tested against exactly that off-by-one.

### 97.4 The field dies rich -- the largest number in the comparison

Gold held at the moment of elimination, by round:

| round | engine | reference | t |
|---|---|---|---|
| 4-3 | 50.2 | 8.4 | +9.7 |
| 4-6 | 41.3 | 8.0 | +15.3 |
| 5-1 | 42.4 | 8.0 | +21.0 |
| 5-2 | 44.6 | 8.1 | +24.6 |
| 5-3 | 47.9 | 7.5 | +28.6 |
| 5-5 | 38.5 | 7.9 | +18.0 |
| 6-3 | 23.2 | 6.4 | +9.2 |

Real players die with about 8 gold. The engine's seats die with 40-55 through
the whole mid-game, and are simultaneously **0.5 to 1.3 levels lower** at the
same elimination round (t to -14.4). Hoarding, not poverty.

This is 66.2's "gold has no sink" and 70's "no policy can spend its gold",
confirmed for the first time against something outside the engine. Entry 70
established it by profiling the engine against itself; this is the external
check that was missing.

**It indicts the scripted field, not necessarily the simulator.** The engine
arm is eight `GreedyPolicy` seats; the reference arm is humans. A rules defect
and a policy defect are indistinguishable in this measurement. That is the same
shape as 85.4 and 86.1, where a defect that read as the engine was the teacher
-- now six times.

### 97.5 3-star incidence is 13 points short

| | engine | reference |
|---|---|---|
| participants holding a 3-star at the end | **21.5%** (515) | **34.5%** (2,763) |

z = -12.10. This is outcome 2: the pacing is right and the accumulation is not,
which 97.4 explains directly -- gold that is never spent does not become
copies. Note the engine reaches 21.5% only with the mixed field; eight
`standard` seats give ~3%.

The engine also never 3-stars a 4- or 5-cost (0 of 2,400 seats). Real
challenger does, 67 and 13 times, placing 1.179 and 1.000 -- figures too
confounded to price anything, since reaching a 3-star 5-cost mostly means the
game was already won.

### 97.6 The payoff hypothesis does not survive its control

The comparable quantity is the *edge* a 3-star confers, since both sides
average 4.5 over all seats by construction.

| | engine | reference |
|---|---|---|
| placement of holders | 4.315 | 4.190 |
| edge over the field | -0.185 | **-0.310** |

The engine appears to under-price a 3-star by 0.125 placement. **It is not
assertable.** Splitting the reference by patch -- 16.14 (n=396) against 16.15
(n=604), both inside the same sample -- moves the same statistic by 0.098:

| | 16.14 | 16.15 | drift | engine gap | survives? |
|---|---|---|---|---|---|
| 3-star rate | 33.2% | 35.4% | 2.2pp | 13.0pp | yes, 6x |
| 3-star edge | -0.249 | -0.347 | **0.098** | **0.125** | **no** |
| game length | 36.10 | 36.41 | 0.31 | 0.87 | yes, 3x |

The *aggregate* payoff discrepancy is the size of drift within the reference
itself between two patches three weeks apart. Lesson 2's shape, one level up: a
discrepancy is uninterpretable without the reference's own spread, and
measuring that spread cost one command.

This kills the aggregate statistic, not the payoff question -- 97.7 takes it
apart by cost tier, where the reference turns out to be stable to 0.002 and the
engine's error is both larger and signed differently per tier.

### 97.7 The aggregate hid it: per cost tier the payoff *is* mispriced

A second reference band, 1,000 NA diamond matches (8,000 participants), was
collected as the rank control. It also lands on older patches -- 16.10-16.12
against challenger's 16.14-16.15, because diamond players play fewer games, so
their last ten reach back months. The band control is therefore partly a second
patch control, which makes what follows stronger rather than weaker.

Placement conditional on holding a 3-star, **by cost**:

| cost | engine (n) | challenger | diamond | reference drift | engine gap | t (lower bound) |
|---|---|---|---|---|---|---|
| 1 | **3.479** (48) | 4.425 | 4.426 | **0.002** | **-0.947** | **-2.82** |
| 2 | **4.418** (462) | 4.165 | 4.177 | **0.013** | **+0.241** | **+2.01** |
| 3 | 2.800 (5) | 4.012 | 3.989 | 0.023 | -1.189 | -1.16 |

Across two rank bands and four patches the reference moves by **0.002** on the
1-cost row. Against that, the engine's gaps are assertable, and they have
**opposite signs**: the engine badly *over*-prices a 3-star 1-cost and mildly
*under*-prices a 3-star 2-cost.

The aggregate in 97.6 washed both out because the two populations have
different composition -- **90% of the engine's holders are 2-cost**, against a
reference spread of 47% / 54% / 32% across costs 1/2/3. A single "edge over the
field" number averages a +0.24 and a -0.95 over incompatible mixtures. Lesson 7
("aggregate metrics hide composition"), which has now cost this project four
findings.

> **Confounded by archetype -- see [entry 101](#101-every-3-star-in-this-engine-is-produced-by-an-explicit-target-08-09).** 101 found that untargeted seats
> reach a 3-star in 0.33% of games against a real 34.5%, so every engine holder
> in the table above comes from the one archetype that targets that cost: the
> 1-cost row is `hyperroll` seats, the 2-cost row is `slowroll6` seats. "The
> engine over-prices a 3-star 1-cost" is not separable from "hyperroll seats
> that hit their carry place well". The *reference* stability across bands
> (0.002) stands; the engine side does not support a per-tier pricing claim.

t is computed with sd = 2.29, the standard deviation of a uniform placement on
1-8 and therefore an upper bound on the true conditional spread, so both t are
lower bounds. Both sides remain correlational: a player who 3-stars a 1-cost is
often one who was forced into it, and the engine's selection process differs
from a human's. What the comparison licenses is "the engine prices these two
tiers differently from real TFT, in opposite directions", not a causal value
for a 3-star.

### 97.8 What this changes

- **96.5's window candidate is refuted** (97.2), and its payoff candidate
  survives only per cost tier, with opposite signs by tier (97.7) -- not as the
  single under-pricing it was posed as.
- **Two defects neither candidate named**, and both are larger than the payoff
  effect: the field cannot convert gold into board (97.4) and the engine fights
  two rounds real TFT does not (97.3).
- **`slowroll6`'s 0.653 behind `standard` is no longer evidence of a simple
  mispricing.** It has not been shown correct either; the measurement that
  would settle it is a `slowroll6` agent-seat profile against this reference,
  which 97 did not run.
- The reference samples are kept at `data/reference/` with provenance blocks.
  Nothing in them is loaded by the engine.

### 97.9 Still open

- **Fix `realm.rounds` to cover stages 5+ and re-measure.** Every placement
  number in the log shifts (lesson 12); this is an engine rules change, so it
  invalidates baselines by construction.
- Whether 97.4 is a rules defect or a `GreedyPolicy` defect. The discriminator
  is a human-comparable spending profile, not another engine-vs-engine run.
- **Why the engine over-prices a 3-star 1-cost by 0.947** (97.7). The engine
  side is n=48, and the combat constants tagged `engine_artifact` are the
  obvious suspects, but 77 already showed 3 of 4 do not matter.
- `slowroll6` in the agent seat against this reference (97.8).
- Why `hyperroll` degrades under targeting (+0.327, t=+2.41) -- still open from 86.
- The eval-cadence aliasing from 96.6 is unfixed.

---

## 98. The carousel fix: elimination timing closes, a late-game stalemate appears (08-09)

97.3 found `realm.rounds` stopping at `[4,4]` while real TFT has a no-combat
round at every `x-4`. Fixed: the schedule now runs `[1,1]` and `[s,4]` for
stages 2-9, with `cost_tiers` continuing the documented 1/2/3/4 pattern capped
at 5. **The tier offered at 5-4 and later is not sourced** and is flagged in
`config.unverified`; the *schedule* is, by the reference data.

**This is an engine rules change, so every placement number measured before it
is void** (lesson 12). The arc table's rows are not comparable across it.

### 98.1 Four predictions, named before the run

Recorded as stated, then scored:

| | prediction | outcome |
|---|---|---|
| P1 | 5-4 / 6-4 eliminations collapse to ~0 | ✅ exactly 0 |
| P2 | mean elimination round rises toward the reference | ✅ closed |
| P3 | game length rises, *widening* its gap | ✅ and worse than expected |
| P4 | 3-star rate rises toward 34.5% | ❌ **refuted** |

### 98.2 What closed

300 games, mixed field, against the same 1,000-match challenger reference:

| | before | after | reference |
|---|---|---|---|
| eliminations on 5-4 + 6-4 | 306 (14.6%) | **0** | 10 (0.14%) |
| mean elimination round | 29.78 (t=-5.67) | **30.57 (t=+1.79)** | 30.36 |
| share eliminated in stage 6+ | 29.9% | **37.5%** | 37.2% |
| max cumulative gap (KS) | 0.143 | **0.063** | -- |

The elimination *distribution* is now a good match: the mean is within 0.21 of
the reference and no longer significant, and the stage-6+ share lands within
0.3 points. 97.2 already said the window was not the problem; it is now not the
problem by a wider margin.

### 98.3 What the fix exposed

Game length went the wrong way, as P3 said it would, and by three times as much:

| | before | after | reference |
|---|---|---|---|
| mean game length | 37.15 (t=+6.33) | **38.99 (t=+18.14)** | 36.28 |
| eliminations at 7-1 or later | -- | **5.3%** | 1.7% |

Mean elimination round matches while mean game length is 2.71 rounds too long,
which is only possible if the discrepancy sits in the tail -- game length is a
max-statistic over the seven eliminations. It does: the engine matches the
reference through ~94% of the field and then its **last one or two seats
survive far too long**, at three times the reference's rate of very-late
eliminations.

The obvious reading is a top-of-lobby resolution problem -- two strong boards
failing to finish each other, implicating `combat.max_duration_seconds` and
`combat.sudden_death_*`. **That reading is probably backwards and is not
asserted here.** `combat.py:1337` decides a timed-out fight by remaining
health, so a timeout still produces a winner, and a winner with *many*
survivors: round damage is `stage_base_damage + damage_per_surviving_unit x
survivors`, so stalled fights deal **more** damage and should kill players
*faster*.

The competing and simpler reading is that total damage per game is now too low
-- removing two combat rounds removed two damage events, and the phantom rounds
had been compensating. `stage_base_damage` and `damage_per_surviving_unit` are
both `community_documented` and were corrected against the wiki at 36.4, so if
they are right the deficit is in how often damage is dealt, not how much.

Which of the two it is has not been measured. It is 98.6's first item, and the
probe must distinguish them rather than assume either.

Removing the phantom combat rounds did not create this. It removed the
confound that was masking it: two extra damage-dealing rounds per game were
compensating for a late game that cannot close itself.

### 98.4 P4 refuted: two more carousels and a longer game buy no 3-stars

| | before | after | reference |
|---|---|---|---|
| 3-star holder rate | 21.5% | **21.7%** | 34.5% (z=-11.90) |
| gold at elimination, 5-3 | 47.9 | 47.9 | 7.5 |
| 1-cost 3-star placement | 3.479 | 3.612 | 4.425 |

**Recorded as a failed prediction.** Two extra draft acquisitions and 1.8 more
rounds of life moved 3-star incidence by 0.2 points, and gold at elimination
did not move at all. This strengthens 97.4 rather than weakening it: the field
is not short of *time* or *opportunities*, it is unable to convert gold into
board. Giving a hoarder a longer game produces a longer hoard.

### 98.5 A casualty: the level cap no longer frees gold into rerolls

`tests/test_evaluate.py` failed on the fixed config, and it was not brittleness.
The claim it pinned -- 68's mechanism, that capping levels stops XP consuming
the gold so rolling becomes reachable -- is now false. Both arms re-measured
together at n=24 (lesson 12), across the config change and nothing else:

| REROLL actions | uncapped | capped (cap 7) | delta |
|---|---|---|---|
| before the carousel fix | 780 | 821 | **+41** |
| after | 822 | 818 | **-4** |

The *uncapped* arm gained 42 rerolls from the fix and the capped arm gained
nothing. Longer games hand the uncapped policy the rolls it previously had to
free up by capping, so the cap's advantage was an artefact of the truncated
carousel schedule.

Where the freed gold goes instead, n=24, by action kind:

| kind | uncapped | capped | delta |
|---|---|---|---|
| BUY_XP | 250 | 179 | **-71** |
| REROLL | 822 | 818 | -4 |
| BUY | 5041 | 5143 | **+102** |
| SELL | 4282 | 4387 | **+105** |

Roughly 284 gold stops being spent on XP and reappears as **102 more buys and
105 more sells** -- the buy/sell churn 85.2 established is gold-neutral. This is
97.4's "the field cannot convert gold into board" with a mechanism attached:
given more gold, the policy does not roll more, it churns more.

Only the XP half of the claim survives, and only that half is now asserted in
the test. The churn direction is not stable at the n=4 the suite can afford
(-10 at n=4, +9 at n=8, +102 at n=24), so it is recorded here rather than
pinned there.

### 98.6 Still open

- **The late-game stalemate (98.3)**, now the largest unexplained gap in the
  comparison and the first finding that points squarely at the `engine_artifact`
  combat constants.
- Everything still open from 97.9, unchanged: the gold conversion defect
  (97.4), whether it is rules or `GreedyPolicy`, the 1-cost over-pricing
  (97.7), `slowroll6` in the agent seat.
- **Every pre-98 placement baseline is void.** Nothing in the arc table is
  comparable across this entry.

---

## 99. The gold gap is the interest floor, and closing it buys nothing (08-09)

97.4 found the field dying on 40-55 gold against a real challenger's ~8, the
largest single discrepancy in the fidelity comparison. 98.5 added a mechanism
from the other direction: gold freed from XP became buy/sell churn rather than
rerolls. This entry finds the cause, fixes it, and measures the fix.

### 99.1 The cause is a missing endgame clause

`EconStrategy.save_floor` is 50 and every archetype's `roll_floors` restores 50
by 4-6, so a seat spends only the income above 50. The reasoning in the
docstring is sound as far as it goes -- 50 is the interest cap, below it you
lose interest and above it you gain nothing -- and it **has no endgame
clause**. A real player one hit from elimination rolls their whole bank; no
plan here ever does. The economy is preserved up to the moment it dies.

`scripts/gold_sink_probe.py`, 420 eliminations over 60 games, mixed field:

| stage | n | gold at death | floor in force | at or above floor |
|---|---|---|---|---|
| 4 | 45 | 41.4 | 47.3 | 44% |
| 5 | 215 | 41.1 | 50.0 | 47% |
| 6 | 143 | 20.7 | 50.0 | 10% |

Mean 33.6 gold unspent at death -- **16.8 rerolls or 8.4 XP purchases** -- and
**24% of eliminated seats die holding 60+**. Predicted outcome O3 (binding
mid-game, not late) was the one that landed. By archetype, `slowroll6` dies
richest at 44.1 with 58% at or above its floor, which is the plan whose entire
purpose is spending its gold.

One column of the probe is vacuous and is called out here rather than quietly
dropped: "gold when HP <= 20" reproduces the gold column exactly, because a
seat being eliminated is at low HP by construction.

### 99.2 The fix works mechanically

`EconStrategy.desperation_hp` drops the roll floor to 0 once a seat is at or
below that HP. **Default 0, i.e. off** -- enabling it changes every field
number, so it is a measured A/B, not a silent default. `desperation_ab.py`,
60 games, shared seeds, one field differing:

| | off | hp=10 | hp=20 | hp=30 | reference |
|---|---|---|---|---|---|
| gold at elimination | 33.65 | 23.68 (t=-6.48) | 13.78 (t=-15.22) | **9.70 (t=-20.92)** | **~8** |
| gap to reference closed | -- | 39% | 77% | **93%** | -- |
| died holding 60+ | 24% | 16% | 5% | **0%** | -- |
| elimination round | 30.64 | +0.18 (t=+0.55) | +0.14 (t=+0.43) | +0.10 (t=+0.32) | -- |

Monotone in the threshold, and at hp=30 the engine essentially **reproduces the
reference**: 9.70 against ~8, with nobody dying on a full bank. The diagnosis
in 99.1 is therefore correct -- the floor was the binding constraint on
spending, not the shop, the bench or the buy rule.

Note the direction of the survival column: the closer the arm gets to real
spending behaviour, the *smaller* its already-null effect on survival. Nothing
here is a performance lever at any threshold.

### 99.3 And it buys nothing

Survival does not move at any threshold: +0.18 (t=+0.55), +0.14 (t=+0.43),
+0.10 (t=+0.32) at hp=10/20/30. Seats dump their whole bank into rerolls in the
rounds before they die -- 24 gold apiece at hp=30, enough for twelve rolls --
and last no longer for it.

**Lesson 21 for the third time** -- shaping's credit concentration (93), the
carousel schedule (98.3's tail), and now this. A defect can be real, correctly
diagnosed, and cleanly fixable while not being the binding constraint on
anything that matters. Validating that a fix does what it claims is a different
measurement from validating that it matters, and only the second one licenses
adopting it for effect.

The fidelity argument for adopting it anyway is separate and is genuine: the
project's goal is an agent that plays real TFT, and a field that hoards a bank
it never spends is not a real lobby. That is a reason to turn it on, but it is
not evidence of a placement gain, and it should never be cited as one.

### 99.4 What is not yet measured

The A/B changes **all eight seats** and reports a field-internal statistic.
What matters for the project is the *agent seat* against a changed field, which
is a different measurement and was not run. Entries 72 and 73 both moved every
downstream number by changing the field; this would too.

`desperation_hp` is an invented constant, on the same footing as the roll
floors of 71. Real TFT has no published threshold. **hp=30 is the value the
reference picks**, not one chosen for effect: it is where gold at elimination
matches real players, and it was the last of three tried rather than the first.
Nothing in 99.3's conclusion depends on the value, since the survival null
holds at all three.

### 99.5 Still open

- Whether to adopt `desperation_hp` as a field default -- a fidelity call, not
  a performance one (99.3), and it voids the field baselines again.
- The agent seat against a spend-down field (99.4).
- The residual 5.8 gold between hp=20's 13.78 and the reference's ~8.
- Everything still open from 98.6, unchanged: the late-game tail (98.3), the
  1-cost 3-star over-pricing (97.7), `slowroll6` in the agent seat.

---

## 100. The reroll mispricing survives both fixes, and 86's table reproduces exactly (08-09)

> **The measurement stands; the word "mispricing" is questioned by entry 111.**
> `slowroll6` really does place +0.553 (t=+3.54) behind `standard`. But 111.4
> decomposes that into a 23.6% miss branch placing 6.799 and a hit branch at
> 4.516, and 111.5 argues the cause is that `slowroll6` cannot pivot off a
> failed roll — a scripted-policy defect rather than a simulator one. The
> engine's actual mispricing against real data is **+0.379 (t=+4.82)** and is
> measured on 3-star holders across the whole field (111.2).

98 declared every prior placement baseline void, correctly: removing two combat
rounds per game is a rules change. This re-derives the one table that the whole
of 97-99 exists to explain -- the econ archetypes -- and asks whether
`slowroll6`'s deficit, the original motivation, survived.

### 100.1 Both arms measured now, not against a stored number

The obvious shortcut was to compare the fixed engine against 86's recorded
figures. That is the error lesson 12 exists to prevent, and here it had a
specific hazard: 86 predates 87 and 88, both of which touched the econ plans,
so any difference would confound the carousel fix with those. So the pre-98
config was restored and **both arms were run now**, 300 shared seeds each,
`scripts/econ_teacher_ab.py`, teacher configuration, mixed field.

| arm | pre-98 | post-98 | delta | t |
|---|---|---|---|---|
| no-econ | 4.823 | 4.880 | +0.057 | +1.24 |
| **standard** | **4.213** | **4.300** | +0.087 | +1.64 |
| fast8 | 4.337 | 4.323 | -0.013 | -0.34 |
| **slowroll6** | **4.867** | **4.853** | -0.013 | -0.26 |
| hyperroll | 5.203 | 5.163 | -0.040 | -0.98 |

**All five pre-98 values reproduce 86's stored table exactly** -- 4.823 /
4.213 / 4.337 / 4.867 / 5.203, to three decimals, three days and two entries
later. The confound worried about above does not exist, and the measurement
chain is reproducible end to end. That is worth more than the entry's main
result.

### 100.2 The carousel fix changes nothing here

No arm moves: every |t| <= 1.64 on 300 paired seeds. Gap to `standard`:

| | pre-98 | post-98 | post-98 t |
|---|---|---|---|
| fast8 | +0.123 | +0.023 | +0.20 |
| **slowroll6** | **+0.653** | **+0.553** | **+3.54** |
| hyperroll | +0.990 | +0.863 | +5.16 |

**Outcome 2 of the three named before the run.** `slowroll6` remains
significantly behind `standard`, and the 0.10 narrowing is below the 0.2 that
was declared in advance as the threshold for reading movement -- and is driven
by `standard` getting *worse* (+0.087) rather than `slowroll6` improving
(-0.013). Two extra carousels and ~1.8 more rounds of game, which should favour
the plan that needs roll volume above all others, did nothing for it.

### 100.3 What this means for 98's "all baselines void"

98's banner was correct procedure and turned out not to matter for this table.
Both statements hold at once, and the second does not license skipping the
first next time: the reason to re-measure is that you cannot know in advance
which way it will go, and the only way to learn that a rules change was
harmless is to measure it. Nine invalidations taught the rule; this is the
first case where re-measuring found nothing, and it cost 18 minutes.

The banner stands for every *other* table. Only the econ archetypes have been
re-derived.

### 100.4 Where the mispricing can still live

Four candidates existed at 96.5 and after. Three are now closed:

* the **window** -- refuted (97.2), and unchanged by the carousel fix.
* the **shop odds** -- exonerated by arithmetic (96.5).
* the **gold budget** -- real, diagnosed and fixed to a null (99).

What remains:

* the **per-tier payoff error** (97.7): the engine over-prices a 3-star 1-cost
  by 0.947 against a reference stable to 0.002, and under-prices a 2-cost by
  0.241. A reroll plan's whole return is concentrated in exactly those tiers,
  which makes this the best-fitting surviving explanation.
* the **late-game tail** (98.3): games 2.71 rounds too long, concentrated in
  the last one or two seats.

### 100.5 Still open

- Test the per-tier payoff error as the cause of the reroll gap (100.4).
- The late-game tail (98.3) and its two competing readings.
- Whether to adopt `desperation_hp=30` as a field default (99.5) -- a fidelity
  call, worth nothing in placement.
- `slowroll6` measured in the *agent seat* against the reference distributions,
  still not run (97.9, 98.6).
- The eval-cadence aliasing from 96.6, still unfixed.

---

## 101. Every 3-star in this engine is produced by an explicit target (08-09)

100.4 nominated the per-tier payoff error as the best surviving explanation for
the reroll gap. Before testing it, the per-tier *incidence* was split out, and
it changed the question.

### 101.1 The tier profile is inverted

3-star holders as a share of seats, engine (300 games, mixed field) against the
two reference bands:

| cost | engine | challenger | diamond | ratio real/engine |
|---|---|---|---|---|
| 1 | **2.04%** | 16.39% | 19.02% | **8x** |
| 2 | **19.29%** | 18.15% | 21.66% | **0.9x -- matches** |
| 3 | **0.33%** | 10.12% | 12.79% | **30x** |
| 4 | 0% | 0.84% | 1.29% | never |
| 5 | 0% | 0.16% | 0.27% | never |

The 2-cost rate is right and every other tier is missing. That is not a
shortfall, it is the wrong shape: in real TFT a 1-cost is the *easiest* thing
to 3-star -- 30 copies in the pool against a 3-cost's 18, and the best shop
odds at low level -- so 2-costs being the common case and 1-costs being 8x rarer
is inverted. 96.5 already exonerated the shop odds by arithmetic, so the
distortion is downstream of them.

### 101.2 Outcome A: targeting is not a multiplier, it is the gate

`scripts/three_star_source.py`, 60 games, seats grouped by archetype. Peak
copies is in copy-equivalents (a 2-star counts 4, a 3-star 9), so 9 is the
threshold a 3-star must cross:

| archetype | `target_cost` | seats | any 3-star | at c1 | at c2 | peak copy-equiv |
|---|---|---|---|---|---|---|
| standard | -- | 180 | **0.6%** | 0% | 0.6% | 6.59 |
| fast8 | -- | 120 | **0.0%** | 0% | 0% | 5.94 |
| slowroll6 | 2 | 120 | 81.7% | 0% | 81.7% | 11.24 |
| hyperroll | 1 | 60 | 13.3% | 13.3% | 0% | 8.30 |

**Untargeted seats reached a 3-star once in 300 games -- 0.33%, against a real
34.5%.** Every 3-star this engine produces comes from an explicit
`target_cost`, and only ever at that exact cost. Nothing anywhere reaches cost
3 or above.

Outcome A of the three named in advance. Targeting is a gate, not a multiplier.
The untargeted seats are not close and unlucky either: they peak at 5.9-6.6
copy-equivalents, which is a 2-star plus a spare, and never approach 9. A real
player accumulates 3-stars *incidentally* -- holding early units, hitting pairs
while playing for something else -- and no policy here does.

### 101.3 What this costs entry 97.7

97.7 read the per-tier placement gaps as a pricing error: the engine
over-prices a 3-star 1-cost by 0.947 and under-prices a 2-cost by 0.241, against
a reference stable to 0.002 across two bands and four patches.

**The engine side of that comparison is archetype-pure.** Its 1-cost holders
are `hyperroll` seats and its 2-cost holders are `slowroll6` seats, because
nothing else ever produces one. "The engine over-prices a 3-star 1-cost" is
therefore not separable from "hyperroll seats that hit their carry place
well" -- a selection effect inside a single archetype, on n=48. 97.7 now
carries a banner saying so.

The reference-side stability is unaffected and remains the entry's durable
part. What is withdrawn is the inference from it to a *pricing* claim about
this engine.

### 101.4 The reroll gap is not an execution failure

`slowroll6` reaches its 3-star in **81.7%** of games and still places 0.553
behind `standard` (t=+3.54, entry 100.2). Whatever is wrong, it is not that the
plan fails to execute -- 86 fixed that, and this confirms the fix holds. The
plan does what it is supposed to do, four games in five, and loses anyway.

That leaves two readings, and 101 does not separate them:

* the 3-star it gets is genuinely worth less here than in real TFT -- which is
  97.7's claim, now unsupported on the engine side and needing a measurement
  that is not archetype-confounded;
* or the *cost* of getting there is too high -- the board it gives up while
  concentrating, which no entry has priced.

### 101.5 Still open

- Price the reroll gap without the archetype confound: the comparison needs
  seats that differ *only* in whether they hold a 3-star, which the current
  field cannot supply (101.3).
- **Why untargeted seats never 3-star anything** (101.2). The suspect is the
  buy/sell rule spreading purchases and breaking pairs; it is a policy defect
  in the same class as 99, not an engine-rules one.
- Whether a field that never 3-stars incidentally is a fair opponent model at
  all, given the agent trains against it.
- Everything from 100.5 except the per-tier payoff item, which 101.3 narrowed.

---

## 102. The teacher can be made to 3-star, and it makes it worse (08-09)

101 found untargeted seats reaching a 3-star in 0.33% of games against a real
34.5%. This traces the mechanism, fixes it, and measures the fix. Lesson 16 is
why it was worth doing: the teacher is the imitation ceiling, and improving it
is the only lever that has ever moved the clone (75.2: 89% transmits).

### 102.1 The mechanism is the sell rule breaking pairs

A 1-star of a champion already held at 2-star is the start of the second pair a
3-star needs. It is also the weakest unit on the bench, so "sell the weakest
surplus" reaches for it first. Neither consumer protected it -- entry 86's
recurring defect, and they disagreed on what they *did* protect:

* `GreedyPolicy._sell_surplus`: reroll targets only.
* the teacher: additionally `_copies_owned < 2`, keeping two copies *at the
  same star level* -- which does not cover a single copy pairing with a 2-star.

`scripts/teacher_copies_probe.py`, teacher, `standard` econ, 30 episodes:

| | before |
|---|---|
| episodes reaching any 3-star | **0/30** |
| peak copy-equivalents (9 = a 3-star) | 4.87, max 7 |
| distribution of peaks | 4:18, 5:4, 6:2, 7:6 |
| progress-breaking sells | **13.4%** (568/4238) |

Eighteen of thirty games peak at exactly 4 -- one 2-star of one champion, and
never anything more.

*A correction inside this entry.* The first version of the probe counted a sell
as progress-breaking if the seat held *any* 1-star matching *any* 2-star, not
whether the unit actually sold was one. That read 29.4%. Reading the sold unit
gives 13.4% -- the proxy over-counted by 2.2x. The corrected figure is the one
above.

### 102.2 The fix does what it claims

`keep_pairs` prefers to sell something that is not progressing an upgrade,
falling back when every candidate is (a full bench that cannot sell stalls
every later purchase -- 37.4).

| | before | after | real |
|---|---|---|---|
| episodes with a 3-star | 0/30 | **6/30 = 20.0%** | 34.5% |
| by cost | -- | **{1: 3, 2: 2, 3: 2}** | spread across tiers |
| peak copy-equivalents | 4.87 | **7.27, max 10** | -- |
| progress-breaking sells | 13.4% | **3.7%** | -- |

3-stars now appear at costs 1, 2 *and* 3 -- the tiers 101 measured as 8x and
30x too rare.

### 102.3 And it is worse. Outcome 3 of three named in advance

300 shared seeds, `standard` econ, default field, one flag differing:

| arm | placement | 1st | top4 | 8th |
|---|---|---|---|---|
| keep_pairs=off | **4.300** | 12.7% | 54.7% | 8.3% |
| keep_pairs=on | 4.643 | 10.7% | 48.7% | 12.0% |

**+0.343, t=+2.65.** The hoped-for outcome did not happen; "worse" was named as
a possibility before the run and is what landed.

`keep_pairs=off` reproduces 100's `standard` arm at 4.300 exactly, which is what
licenses reading the difference.

An earlier version of this A/B ran both arms against a field that also had the
fix, giving +0.327 (t=+2.52). The field change was reverted and the A/B re-run
so both arms face the project's actual default field; the numbers above are the
re-run. Same conclusion, and the first version is recorded because it was run.

### 102.4 Three lines now converge on the engine under-valuing a 3-star

| | |
|---|---|
| `slowroll6` executes in 81.7% of games | and places +0.553 behind `standard` (100.2, 101.4) |
| the teacher forced to 3-star, 0% -> 20% | places +0.343 worse (102.3) |
| real challenger holds a 3-star 34.5% | and holders place **0.31 better** than the field (97.6) |

In this engine, pursuing a 3-star is a losing strategy. In real TFT it is a
mainstream line. The sign is flipped and the magnitude is roughly 0.6
placement.

This is 96.5's **payoff** candidate, supported for the first time by a *causal
intervention* rather than by the conditional comparison 101.3 had to withdraw
as archetype-confounded. An intervention that moves behaviour toward the
reference and makes performance worse is evidence about the *simulator*, not
about the behaviour.

It may also unify with 98.3's unexplained late-game tail: a 3-star's advantage
compounds over a long fight, so combat that fails to resolve truncates
concentrated power specifically while also leaving late fights undecided. Both
would follow from the duration constants -- `max_duration_seconds`,
`sudden_death_*` -- which are `engine_artifact` and which 76 structurally could
not test.

### 102.5 The competing explanation, not yet excluded

`keep_pairs` is blunt: it protects **every** progressing copy unconditionally,
including copies of champions the seat will never play. A real player holds two
or three pairs and abandons the rest. So the loss may be bench congestion
rather than 3-stars being underpriced, and the two are not separated here.

The evidence does not settle it either way. Against congestion: the arm does
reach 20% 3-stars, so it is not merely hoarding dead copies. For congestion:
the loss shows up as fewer top-fours (54.7% -> 48.7%) *and* more last places
(8.3% -> 12.0%), which is what a weaker board looks like, not what a
concentrated one does.

### 102.6 Nothing is adopted

`keep_pairs` defaults **off** and the `GreedyPolicy` change is reverted, so the
tree behaves exactly as it did before this entry. A change that costs 0.343 is
not adopted for fidelity's sake, and 99.3's warning applies again: the fidelity
argument is real and is not evidence of a gain.

### 102.7 Still open

- **Separate underpricing from bench congestion** (102.5). A selective
  `keep_pairs` -- cap the protected champions at two or three -- is the cheap
  discriminator, and it must be run before 102.4 is treated as established.
- **Test the duration constants directly.** `scripts/combat_sensitivity.py`
  already runs both relevant probes: the star-vs-slots exchange rate and the
  fraction of fights hitting the timeout. It has never been run against the
  post-98 engine.
- Everything from 101.5.

---

## 103. It was bench congestion: a selective keep_pairs is free (08-09)

102.5 named bench congestion as the unexcluded alternative to 102.4's
"the engine under-values a 3-star", and 102.7 named the discriminator: cap the
number of protected champions instead of protecting every one. Run at n=300,
shared seeds, `standard` econ, default field:

| `keep_pairs` | placement | vs off | t | 3-star rate | 1st | top4 | 8th |
|---|---|---|---|---|---|---|---|
| 0 (off) | **4.300** | -- | -- | 0% | 12.7% | 54.7% | 8.3% |
| **2** | **4.283** | **-0.017** | **-0.14** | **15%** | 14.7% | 55.3% | 10.3% |
| 3 | 4.483 | +0.183 | +1.52 | 15% | 12.3% | 50.7% | 10.0% |
| 99 (102.3's arm) | 4.720 | +0.420 | +3.33 | 20% | 9.0% | 47.3% | 12.0% |

**Congestion, not underpricing.** The loss is monotone in how many champions
are protected -- 0, +0.18, +0.42 -- and is *absent* at a cap of two, which
still reaches a 3-star in 15% of games. If the engine were under-pricing the
3-star itself, the arm that produces them at 15% would pay for it. It does not.

### 103.1 What this withdraws

**102.4's three-line convergence is broken, and the teacher line was the one
carrying it.** Restated honestly:

| line | status |
|---|---|
| `slowroll6` executes 81.7% and places +0.553 behind `standard` | **stands** (100.2, 101.4) |
| real challenger holds a 3-star 34.5%, holders place 0.31 better | **stands** (97.6) |
| ~~the teacher forced to 3-star loses 0.343~~ | **withdrawn** -- that was the implementation, not the 3-star |

What survives is far weaker than 102.4 claimed. At the margin a 3-star in this
engine is worth **approximately nothing** (-0.017, t=-0.14) where real TFT pays
about 0.31. That is still a gap, and it is a *null against a positive* rather
than the sign flip of 0.6 placement 102.4 asserted. It is not enough on its own
to indict the combat constants.

**Lesson 25 is withdrawn.** It generalised from 102.4 within the hour and the
generalisation did not survive its own discriminator. The specific claim -- "an
intervention that moves behaviour toward the reference and makes performance
worse is evidence about the simulator" -- is only sound once the intervention
has been shown to be a *good* implementation of the behaviour. Mine was not,
and the lesson as written would have licensed skipping exactly the check that
refuted it. What remains true is much smaller and already covered by lesson 21.

### 103.2 A note on how this nearly went wrong

102.4 was written from three measurements that agreed, and agreement is
persuasive. The discriminator that broke it cost eight minutes and was named in
the same entry (102.7) -- but only because 102.5 had been forced to write down
the alternative explanation rather than leaving it implicit. Naming the
competing reading in the entry is what made the check obligatory a step later.

This is the fourth time in this project a tidy story assembled from agreeing
measurements failed its first real test (23.3, 68.4, 95.1, and this).

### 103.3 `keep_pairs=2` is worth adopting, on fidelity

It costs nothing on the mean (-0.017, t=-0.14) and moves the teacher from 0% to
15% 3-star incidence against a real 34.5% -- less unrealistic, not yet
realistic. The distribution is boom-or-bust in the way real reroll play is:
firsts 12.7% -> 14.7% and eighths 8.3% -> 10.3%, with top-four flat. LP is
marginally up (3.81 -> 4.07) and well inside noise.

That is a fidelity gain at no measured cost, which is a better case than either
`desperation_hp` (99, free but inert) or the unconditional arm (102, costly).
**Still not adopted here:** it changes every teacher number and so voids the
clone baselines, and 99.3's rule applies -- a fidelity argument is not evidence
of a gain. It is a decision, and it is recorded as one.

### 103.4 Still open

- The `slowroll6` deficit is **unexplained again**. 103.1 removed the
  explanation 102.4 offered, and 100.4's other candidate (the per-tier payoff)
  was withdrawn as confounded at 101.3.
- Whether to adopt `keep_pairs=2` (103.3).
- Why cap 3 is worse than cap 2 -- 0.18 for one more protected champion,
  t=+1.52, not significant but monotone with the cap-99 arm.
- The late-game tail (98.3), untouched by any of this and still the largest
  raw fidelity gap.
- Everything from 101.5.

---

## 104. The agent baseline, re-derived post-98 (08-09)

98 voided every placement figure in this log, and nothing since had re-measured
the *agent*. The arc table's last row predates two rules changes, so no claim
about the model was checkable. This fixes that and nothing else.

Two behaviour-cloning seeds, identical configuration to `bc-econ-s1`
(`--warm-start 400 --warm-start-epochs 50 --expert-flags --expert-sell
--expert-econ standard --slot-head`, 60 eval episodes). Two seeds because the
clone training-noise floor is 0.14 and one seed resolves nothing below ~0.4
(lesson 19).

| | placement | ci95 | top4 | floor rate |
|---|---|---|---|---|
| clone, seed 0 | 4.867 | 0.612 | 50.0% | 21.7% |
| clone, seed 1 | 4.933 | 0.475 | 33.3% | 10.0% |
| **clone, mean** | **4.900** | -- | -- | -- |
| **teacher, same 60 seeds** | **4.750** | -- | -- | -- |
| teacher, seeds 0-299 | 4.300 | -- | -- | -- |

**Gap to teacher: +0.150**, which is at the clone noise floor. The clone is at
parity with its teacher, exactly as 81 established pre-98. Neither of today's
engine changes moved that relationship.

### 104.1 The seed set matters more than the sample size here

The teacher scores **4.750 on seeds 0-59 and 4.300 on seeds 0-299**. Quoting
the clone's 4.900 against the 300-seed figure gives a gap of 0.600 -- four
times the real one -- purely because the first sixty seeds are harder than
average.

Both numbers are correct and comparing them is not. This is lesson 12's rule
in a form it had not taken before: not "re-measure across commits" but
**"compare on the same seeds"**, which matters just as much when the arms are
n=60 and n=300 from the same run. `evaluate` takes `seeds=range(n)`, so a
60-episode eval and a 300-episode eval are nested, not independent -- easy to
forget precisely because they share code.

### 104.2 What is now measurable again

The arc table has a current row. Any future claim about the agent can be
compared against 4.900 (2 seeds, n=60, seeds 0-59) or against the teacher's
4.750 on the same seeds. Nothing else in the arc table has been re-derived and
the banner still stands for all of it.

### 104.3 Still open

- Unchanged from 103.4. This entry adds no finding, only a measurable baseline.
- The standing recommendation for what to do next is 79's diagnosis: search
  produces better-than-policy decisions and **the observation is what stops
  them transmitting**. Combined with lesson 1 -- relational features have
  worked every time, descriptive ones never -- that is the one direction with a
  live diagnosis and no negative result against it. Everything else named in
  §8 is now measured: economy (88), imitation (81), RL (89-96), and fidelity
  (97-103).

---

## 105. External review: the combat surrogate, and why this engine's search is capped by 91 (08-09)

104 recorded that every internal lever is measured and none moves the agent.
Two web searches -- the technique that produced lesson 14 -- did more to
redirect the programme than any measurement since 97.

### 105.1 What the field does

**Riot's own TFT RL work** (GDC 2023, Ran Cao, *Simulating Teamfight Tactics
Using Deep Learning for Fast Reinforcement Learning AI Training*). Their
binding constraint was throughput, stated in the deck as "a full game takes
minutes; we want one game to end in seconds". They could not use the game
server, so they built a **custom Python game** -- and replaced combat
simulation with a **learned combat model**: board states in, **damage
distribution** out, via a CNN plus transformer encoder over champion
embeddings with hex-position encodings (the deck frames a board as "a
generalised image" and "a generalised sentence"). RL runs on top of that.

**Auto-battler agents that beat strong humans are search-based, not
model-free.** The Hearthstone Battlegrounds MCTS assistant reports losing 9.56%
of turns against 26.26% for experienced human players.

Neither line of work reports success from model-free per-action RL on a game of
this shape, which is consistent with 89-96 rather than a rebuke of them.

### 105.2 Where this project sits

The throughput number matches: `rl/opponents.py` records a game as ~3-10s of
pure-Python combat ticks and 97% of measurement time, and 96.4 measured 123 env
steps/sec over 11 hours. Riot hit the same wall and solved it with a surrogate.

This project is better placed than Riot was on exactly one axis: 97-104
validated the combat engine against 2,000 real matches, so it is a *trustworthy
generator of unlimited training data* for a surrogate. Riot had to work around
a game server; we have a checked simulator.

But a surrogate would **not** help the RL that has already failed. 96 measured
33x the data changing nothing, so episode throughput is not the binding
constraint on PPO here. A surrogate is worth building only to make **search**
affordable, and only if search is worth having.

### 105.3 Search in this engine is capped by 91, and the cap is structural

`rl/search.py`'s `best_swap` is a one-ply search that moves **one bench unit
onto the board**. That is a single action. 91 measured 1,098 single-action
counterfactuals and found **max |t| = 1.82**: single actions do not measurably
move placement.

So 54's **+0.307** is roughly what 91 predicts, and widening that search buys a
more precise estimate of a decision that does not matter. Measured cost of
widening, 10 episodes, 10 workers:

| arm | wall clock |
|---|---|
| no search | 5.2s |
| default (4 candidates x 2 panel x 3 trials) | 60.7s (12x) |
| wide (16 x 4 x 4) | 248.2s (48x) |

A budget sweep at usable n is ~80 minutes for a result 91 already predicts. It
was **not run**, and that is the finding: the existing search is the wrong
shape, not the wrong size.

### 105.4 What 91 does not cover

91 tested *single-action* counterfactuals only. It says nothing about changing
several actions at once, which is what a whole-board search does -- and a
multi-swap candidate costs the same one combat to evaluate as a single-swap
one. The untested hypothesis is that placement responds to **board-level**
changes while being insensitive to unit-level ones, which is also what 67, 68
and 72 ("board size dominates") would predict.

That is the one search question this project has never asked, and it is cheap
to ask before any surrogate is built.

### 105.5 Recommended order

1. **Multi-action board search, measured against the one-swap incumbent.** If
   whole-board candidates do not beat +0.307 materially, search is dead here
   and no surrogate is justified.
2. Only then, the **combat surrogate**, to make deeper search affordable.
3. Only then, deeper search or MCTS.

Each step is gated on the previous one paying, which is lesson 2 applied to an
engineering programme rather than to a statistic.

### 105.6 Still open

- Everything from 104.3, reframed by the above.
- The macro-action reformulation (a plan-level action space) remains untried
  and is the non-search alternative to the same diagnosis.

---

## 106. Multi-action search buys nothing over one swap; the surrogate is unjustified (08-09)

> **106.2 WITHDRAWN by entries 107.1 and 108.2.** The three-arm table and the
> surrogate conclusion stand. 106.2 does not, on two counts. 107.1: it
> attributes the `best_swap` gain measured here to the `best_move`
> non-transmission measured in 79, which are different searches — there was no
> `move` arm in this table. 108.2: the **-0.527** itself does not replicate,
> reading **-0.243 (t=-2.00)** at n=300 on the same budget. Do not quote it.

105.5 set a gated programme: multi-action search first, and a combat surrogate
only if depth paid. It does not.

`best_board` changes up to three units at once for the same one combat per
candidate. 150 shared seeds, teacher configuration, `standard` econ, all three
arms measured together:

| arm | placement | ci95 | LP | 1st | top4 | vs none | vs swap |
|---|---|---|---|---|---|---|---|
| no search | 4.553 | 0.353 | +1.04 | 10.0% | 48.7% | -- | -- |
| **swap (1 action)** | **4.027** | 0.364 | +6.88 | 18.0% | 60.7% | **-0.527, t=-3.03** | -- |
| board (3 actions) | 4.120 | 0.354 | +5.71 | 15.3% | 58.0% | -0.433, t=-2.46 | **+0.093, t=+0.59** |

**Outcome 2 of the three named before the run.** Multi-action search is a null
against single-action search, and marginally the wrong way.

### 106.1 The hypothesis was wrong, and it was mine

105.4 argued that 91 only tested *single-action* counterfactuals, so
board-level changes might move placement where unit-level ones do not, as
"board size dominates" (67, 68, 72) would predict. Changing three units at once
buys nothing over changing one. Recorded as a failed prediction.

**This closes 105.5 steps 2 and 3.** A combat surrogate exists to make deeper
search affordable; depth is worth nothing here, so the surrogate is not
justified. A multi-week build avoided by a 40-minute run, which is the entire
point of gating it.

### 106.2 What the same table says instead, and it is larger

Search is worth **-0.527 (t=-3.03)** to the teacher on the current engine, with
firsts 10.0% -> 18.0% and top-four 48.7% -> 60.7%. That is a bigger teacher gain
than 54's +0.307, though the two are not comparable -- 54 was n=300 on the
pre-98 engine, and only the three arms above were measured together (lesson 12).

Lesson 16 and 75.2 say a teacher gain of that size should reach the clone at
~89%. **79 says this particular one does not**: "search doesn't transmit --
labels were fixable, the observation is the wall."

So the live question is no longer *deeper search*. It is:

> The teacher has a 0.527 gain that the student cannot absorb. 79 diagnosed the
> observation as the reason, and lesson 1 says relational features close
> exactly this kind of gap. Can the observation be widened to carry what the
> search is deciding on?

That is worth more than anything else currently open: 0.527 on the teacher, at
89% transmission, is roughly 0.47 on the agent -- larger than every measured
intervention in this log since 75.

79's non-transmission result predates the post-98 engine and should be
re-derived before being relied on.

### 106.3 Still open

- Re-derive 79's non-transmission on the current engine (106.2).
- If it reproduces: what comparison does `best_swap` make that the observation
  cannot express? It scores a candidate board by *simulated fight margin against
  a panel of opponents* -- a relation between our board and theirs, which is
  precisely the descriptive/relational distinction of lesson 1, and the
  observation currently carries scouting only as a summary.
- The macro-action reformulation (105.6), untouched.
- Everything from 104.3.

---

## 107. Search still doesn't transmit — and 79's own fix has now been ruled out as the reason (08-10)

106.3 asked for 79's non-transmission result to be re-derived before being
relied on. It reproduces, to within about a point in every cell. What is new is
what the re-derivation *eliminates*.

### 107.1 106.2 joined two different searches

`--expert-reposition` builds `search_kwargs` with `mode="move"`
(`scripts/train_ppo.py:1288`), dispatching to `best_move`. The **-0.527
(t=-3.03)** in 106.2 came from `scripts/board_search_ab.py:72`, whose arms are
`none` / `swap` / `board` — there was **no `move` arm in that table at all**.
The two search a different decision:

| | `best_move` | `best_swap` |
|---|---|---|
| decides | which fielded unit moves, and where | which bench unit is fielded |
| candidates | ~200 legal moves, sampled | top-4 bench by (star, cost), fixed |
| target hex | searched | first free, else weakest |

Both halves of 106.2 are real measurements; the sentence joining them is not.
"0.527 at 89% transmission is roughly 0.47 on the agent" attaches a
`best_swap` gain to a `best_move` non-transmission. **Entry 106 flagged ⚠️.**

### 107.2 79.1 was never re-run after 79's own fix

`bc-search-s0` (79.1) trained on free-running-stream labels. 79.3 measured
those at 38.7% self-agreement, 79.4 seeded the sample from the board to fix it,
79.7 confirmed the fix costs no search quality (+0.053, t=+0.39). **No clone
was ever trained afterwards.** `state_seeded=True` has been the default since;
this is the first test of the remedy 79 prescribed for itself.

Ceiling re-measured, `scripts/search_determinism.py --states 60 --repeats 5`,
c12/p1:

| | pre-79.4 (79.3) | now |
|---|---|---|
| modal-move agreement | 38.7% | **100.0%** |
| states where all 5 streams agreed | 10.0% | **100.0%** |
| mean distinct answers per state | 4.03 of 5 | **1.00 of 5** |
| "no move" rate | 24.7% | 16.7% |

The labels are single-valued. Lesson 6's achievable maximum is 100%.

### 107.3 The measurement

Two BC clones, seed 0, 400 expert episodes, 50 epochs, `--slot-head`,
`--expert-econ standard`, identical but for `--expert-reposition` (c12/p1,
state-seeded). Each scored against its **own** teacher reconstructed from its
sidecar, n=300 shared seeds, paired:

| arm | place | 1st | top4 | 8th | vs own teacher |
|---|---|---|---|---|---|
| teacher, econ only | 4.300 | 12.7% | 54.7% | 8.3% | — |
| teacher, econ + move search | **3.903** | 18.7% | 62.7% | 8.3% | — |
| `xmit-nosearch-s0` | 4.537 | 11.0% | 51.0% | 14.0% | +0.237, t=+1.60 |
| `xmit-search-s0` | **4.770** | 7.0% | 45.3% | 11.0% | +0.867, t=+5.25 |

- teacher, econ → econ+move: **-0.397, t=-3.11, n=300**
- clone, nosearch → search: **+0.233, t=+1.52, n=300**

Under the bar, so the honest statement is that the search clone is **not
better**, not that it is worse. The gap to its own teacher widens 0.237 →
0.867. 79.1 reproduces in structure and roughly in magnitude (there: teacher
-0.330, clone +0.190 at t=+1.31, gap 0.857 → 1.047).

**A failed read of mine.** The in-run n=60 evaluations said the opposite —
nosearch 4.867 against search 4.467 — and I reported that as the transmitting
direction before the paired n=300 reversed it. Same 60-episode trap as 104.1,
one step after describing it.

### 107.4 Per-action, against 79.2 — nothing moved

Expert states, deterministic prediction, `scripts/action_match.py`:

| action kind | 79.2 econ | **107 nosearch** | 79.2 search | **107 search** |
|---|---|---|---|---|
| BUY | 96.7% | 96.6% | 96.2% | 96.5% |
| BUY_XP | 94.7% | 96.6% | 95.0% | 94.8% |
| PICK_AUGMENT | 99.2% | 99.2% | 99.2% | 99.2% |
| REROLL | 95.0% | 94.5% | 86.9% | 83.7% |
| **SELECT** | 84.0% | **86.3%** | 47.4% | **47.7%** |
| **PLACE** | 78.8% | **79.6%** | 44.5% | **45.5%** |
| *overall* | *90.8%* | *90.8%* | *83.0%* | *83.5%* |

SELECT volume 910 → 1644 in 79.2; 931 → 1677 here. A different engine, and the
label ceiling raised from 38.7% to 100.0%, and every cell lands within about a
point.

### 107.5 What this eliminates, which is the point

79.3 named two causes with opposite remedies and could only test one:

> "the predicted explanation — the observation lacking the relation — is
> **not** the operative one. It remains untested, because the label noise masks
> it."

The mask is now off. Labels are single-valued (107.2), and overall BC fit rose
with them (79.2's search arm 83.0% → 83.5% here, and 89.9% at epoch 50 on the
training objective against the econ arm's 95.0%). SELECT and PLACE did **not**
rise, and placement did not transmit.

So the fit was never limited by label noise. The clone fits 47.7% of positional
labels that are now fittable at 100%. By CLAUDE.md's rule — a probe that cannot
fit its own training set is a statement about the feature set, not the model —
**the observation is the binding constraint, and this is the first time this
project has isolated it rather than inferred it.** 79.3's suspicion was right
for a reason 79.3 could not check.

What `best_move` is comparing: it scores a *layout* by simulated fight margin
against a panel of opponents. That is a relation between where our units stand
and where theirs do. The observation carries opponents as six summary scalars
(`SCOUT_FEATURES = 6`) and only under `scouting="full"`, which is off by
default — and carries no opposing *positions* at all under any setting. Lesson
1 says relational features are the only widening that has ever worked here.

### 107.6 Still open

- **The swap-search clone, which is now the cheapest live test.** 106.2's
  0.527 belongs to `best_swap`, and no clone has ever been trained on it —
  `--expert-reposition` cannot express `mode="swap"`. `best_swap`'s candidate
  set is deterministic by construction, so it never had a label-noise problem;
  and its decision is *which unit*, not *which hex*, which the observation may
  already support. Needs a `--expert-reposition-mode` flag.
- The relational scouting widening implied by 107.5, which should be
  hypothesis-first: name the comparison `best_move` makes before encoding
  anything.
- The macro-action reformulation (105.6), untouched.
- Everything from 106.3 and 104.3.

---

## 108. The swap search doesn't transmit either, and the residual is one decision kind (08-10)

107.6 named the swap clone the cheapest live test: `best_swap` never had a
label-noise problem, and it decides *which bench unit is fielded* rather than
*which hex a unit stands on* — the axis 107.4 blamed. `--expert-reposition-mode`
added so the teacher is expressible at all; flag, sidecar and
`teacher_gap.search_config` all carry it, with
`test_reconstructed_search_configs_are_callable` pinning the round-trip against
79.5's three-time defect.

### 108.1 Neither search transmits

Same recipe as 107.3 at `best_swap`'s c4/p2 — entry 106's budget. All arms on
shared seeds 0–299, paired:

| arm | place | 1st | top4 | 8th | vs own teacher |
|---|---|---|---|---|---|
| teacher none | 4.300 | 12.7% | 54.7% | 8.3% | — |
| teacher swap | 4.057 | 14.7% | 61.3% | 8.7% | — |
| teacher move | 3.903 | 18.7% | 62.7% | 8.3% | — |
| `xmit-nosearch-s0` | 4.537 | 11.0% | 51.0% | 14.0% | +0.237, t=+1.60 |
| `xmit-swap-s0` | 4.703 | 8.7% | 45.3% | 10.0% | +0.647, t=+4.17 |
| `xmit-search-s0` | 4.770 | 7.0% | 45.3% | 11.0% | +0.867, t=+5.25 |

| comparison | Δ | t |
|---|---|---|
| teacher, none → swap | **-0.243** | -2.00 |
| teacher, none → move | **-0.397** | -3.11 |
| clone, none → swap | **+0.167** | +1.11 |
| clone, none → move | **+0.233** | +1.52 |

**Outcome 2 of the four named before the run.** Both teachers gain, neither
clone does, both gaps widen. **My prediction of outcome 1 failed** — removing
hex choice from the search does not make it transmissible.

### 108.2 106.2's magnitude does not replicate either

106 measured the swap teacher's gain at **-0.527 (t=-3.03), n=150**. Same
budget, same econ, seeds from zero, **n=300: -0.243 (t=-2.00)** — less than
half, and the two intervals barely meet. 107.1 already withdrew the *inference*
106.2 drew; the number it drew it from is itself soft. It was the figure that
made 105's surrogate programme look worth gating.

Lesson 12 applies in the narrow sense — 106's arms were measured together and
this one was not — but the no-search baselines differ too (4.553 there, 4.300
here), so the honest reading is that neither figure is a constant and the
n=150 one should not be quoted. **Entry 106 index status already ⚠️.**

### 108.3 The residual is SELECT alone, which is the useful part

> **Quoted against the wrong maximum; see entry 109.3.** The localisation
> stands. "54.7% against 86.3%" does not read as a fit failure: the
> observation's achievable maximum for these labels is **61.2%**, and the clone
> is at 89% of it — the same fraction it reaches in the plain arm.

Expert states, deterministic prediction, all three clones:

| action kind | nosearch | **swap** | move |
|---|---|---|---|
| BUY | 96.6% | 96.3% | 96.5% |
| BUY_XP | 96.6% | 95.0% | 94.8% |
| REROLL | 94.5% | 97.6% | 83.7% |
| PICK_AUGMENT | 99.2% | 100.0% | 99.2% |
| **PLACE** | 79.6% | **76.0%** | 45.5% |
| **SELECT** | 86.3% | **54.7%** | 47.7% |
| *overall* | *90.8%* | *86.5%* | *83.5%* |

PLACE comes back — 45.5% → 76.0%, against 79.6% with no search at all —
exactly as removing hex choice predicts, since `best_swap` drops its unit on
the first free hex or the weakest occupied one. SELECT does not: 54.7% against
86.3%.

So the imitation failure is **not** positional in general. It is one decision:
*is this benched unit worth fielding?* And that is precisely what `best_swap`
answers by simulating the fight — a comparison between a candidate unit and the
opposing boards it would have to beat.

This is a much sharper target than 107.5's. The observation encodes each unit
descriptively (cost, star, items, role, stats, traits) and each opponent as at
most six summary scalars, off by default. Nowhere does it carry *how a unit of
ours fares against a board of theirs*. Lesson 1: description has failed every
time, comparison has worked every time.

### 108.4 Still open

- The relational feature implied by 108.3, hypothesis-first: name the
  comparison `best_swap` makes, encode that, and check whether SELECT fit
  moves before checking whether placement does. SELECT fit is the discriminator
  and it is cheap; placement is the expensive confirmation.
- Whether a teacher gain of ~0.25–0.40 is even worth transmitting. Both are
  smaller than 106.2's withdrawn 0.527, and lesson 16's 89% would put the
  ceiling near 0.2–0.35 on the agent.
- The macro-action reformulation (105.6), untouched.
- Everything from 107.6, 106.3 and 104.3.

---

## 109. The observation caps SELECT at 61% for the search rule and 93% for the plain one (08-10)

108.4 asked for SELECT fit to be made the discriminator before any placement
run. `scripts/select_probe.py` does it: train a probe on **nothing but the
observation the clone already sees**, on **only** the SELECT decisions, and
compare against the clone. No feature is invented, so nothing here depends on a
judgement about what to encode.

### 109.1 Read held-out, not training fit

The obvious reading — CLAUDE.md's "a probe that cannot fit its own training set
is a statement about the feature set" — does not apply directly. The
observation is 381 continuous floats, so every row is unique
(`duplicate_label_ceiling`: 100.0%, zero collisions across 6836 rows) and the
probe reaches 100% train fit in every arm by memorising. Training fit
discriminates only when memorisation is unavailable. The clone's own rate is
measured on fresh episodes, so held-out is both the informative and the
comparable quantity. Stated because the first version of this script asserted
the opposite in its docstring.

### 109.2 The measurement, with its control

150 episodes each, identical teacher flags and econ, differing **only** in the
search wrapper. 512 hidden, 4000 epochs, masked to legal slots, contested
decisions only (>1 legal SELECT), 20% held out:

| SELECT labels | contested n | majority | **probe held-out** | clone (108.3) | clone / probe |
|---|---|---|---|---|---|
| plain, `max(star, cost)` | — | — | **93.4%** | 86.3% | 92.4% |
| swap, `best_swap` | 6836 | 28.2% | **61.2%** | 54.7% | 89.4% |

**A 32-point split on the same observation with the same probe.** The plain
rule reads quantities already carried per unit slot and the probe recovers it
almost perfectly. The search rule is not recoverable.

### 109.3 This reframes 108.3, and mostly in a good way

The clone sits at **~90% of a dedicated probe in both arms** (92.4% and 89.4%).
It is not differentially failing on the search labels; it tracks whatever the
observation supports, and pays a uniform ~7-point multi-task cost for learning
ten other action kinds at the same time.

So 108.3's "SELECT 54.7% against 86.3%" is real but was quoted against the
wrong maximum — lesson 6 again, and the third time in this project the same
error has been caught (79.3, 101, here). Against its achievable 61.2% the clone
is at 89%, which is *normal* transmission. **There is nothing to recover by
training harder.** Better cloning, DAgger, more epochs and more capacity are
all bounded above by 61.2%, and 81 already measured DAgger at -0.083 (t=-0.57).

The remedy has to raise the 61.2%. That is the observation, and it is now a
number that can be moved and re-measured in ~12 minutes per candidate feature
instead of ~35 minutes per training run.

### 109.4 Still open

- Candidate features, hypothesis-first, each scored by this probe before any
  clone is trained. The line CLAUDE.md draws matters here and should be stated
  per candidate: `best_swap` decides by *simulated fight margin against a
  panel*, so encoding that margin directly is copying the teacher's computation,
  not learning. Legitimate candidates are the comparisons a player reads by
  scouting — ours-versus-theirs on board value, star levels, trait tiers,
  frontline counts — and the bench-versus-board comparison the argmax needs,
  which requires a ranking across slots that a flat MLP will not derive.
  61.2% is the number to beat.
- Whether ~0.25-0.40 of teacher gain is worth the work at all (108.4).
- The macro-action reformulation (105.6); everything from 108.4, 107.6, 104.3.

---

## 110. Relational features fail for the first time, and the reason is instructive (08-10)

109.4 set 61.2% as the number to beat and named the line: encode the *inputs* to
`best_swap`'s judgement, never the simulated margin itself, which is the
teacher's computation rather than a fact about the board.

### 110.1 The candidates, and why these

Every relational feature the observation carries is **self-referential** —
`owned` / `synergy` compare a shop slot to the player's own roster,
`star_rank` / `cost_rank` / `copies` compare the player's units to each other.
Nothing compares the player's board to an opponent's, and `best_swap` decides
by fighting one. `star_rank` and `cost_rank` already span bench *and* board
slots, which is exactly why the plain rule probes at 93.4%: the ordering its
argmax needs is present.

Two families added, 41 floats, both visible in the real client:

- **trait delta, per unit slot** (37) — breakpoints the board gains by fielding
  a benched unit, or loses by removing a fielded one. Hovering a unit shows
  this. It is a dot product plus a threshold across slots, the operation 29 and
  38.6 both measured a flat MLP failing to derive.
- **board versus panel** (4) — unit count, value, best star, active trait tiers,
  each as ours minus theirs, against the same panel `best_swap` uses.

### 110.2 It does not work

150 episodes, same seeds, same probe, 20% held out:

| arm | width | probe held-out |
|---|---|---|
| observation only | 381 | **61.2%** |
| + 41 relational floats | 422 | **63.7%** |
| *(plain rule, for scale)* | 381 | *93.4%* |

**+2.5 points against a 32-point deficit.** Held-out drifts 1-2 points across
epochs in both arms (66.2% → 63.7% with features, 64.5% → 61.2% without), so
the honest statement is that the effect is small and this single split does not
establish it is real. Either way it is not a recovery. **Outcome 2 of the three
named before the run.**

### 110.3 The first failure of the relational rule, and what it refines

CLAUDE.md states the project's most productive finding as: adding *description*
has failed every time, adding a *comparison between* entities has worked every
time. This is the first measured exception, and it does not overturn the rule so
much as bound it.

The comparisons that worked — `owned`, `synergy`, `copies`, the ranks — each
supplied a quantity the teacher's rule **is a function of**. `max(bench,
key=(star, cost))` is a function of ranks; the sell rule is a function of copy
counts; BUY is a function of ownership and synergy. Supply the argument and the
label becomes trivial.

`best_swap`'s rule is not a function of any scoutable quantity. It is a function
of a *combat simulation* — positions, ability timings, item procs, damage rolls
over three trials against two boards. There is no small set of features whose
value determines it, because the thing determining it is the simulator. The
refinement:

> Relational features close a gap when the teacher's rule is a **function of the
> relation**. When the teacher's rule is a *simulation*, its output is not a
> function of any feature short of running the simulation, and supplying the
> output is copying rather than learning.

That also retro-explains 79 and 108 better than "the observation is too narrow"
did. Both searches were unclonable for the same reason, and no width of flat
observation was ever going to fix it.

### 110.4 What this closes

The search-transmission programme, in full. Every branch is now measured:

- deeper search — worth nothing (106)
- removing hex choice — does not transmit (108)
- fixing label noise — does not transmit (107)
- training harder — bounded above by 61.2% (109)
- widening the observation — +2.5 points (here)

The prize was ~0.25-0.40 of teacher gain, of which none reaches the agent. This
thread should stop. Recorded as a **negative result on a well-specified
question**, which is the honest description: five entries and one day to close
a direction that had been open and quoted since entry 47.

### 110.5 Still open

- **Fidelity, which matters more for the stated goal.** `slowroll6` still
  places +0.553 (t=+3.54) worse than `standard` (100), and reroll lines are
  viable in real TFT. An agent trained here learns something false about the
  real game. That is a bigger obstacle to playing real TFT than the 0.3
  placement this thread was chasing.
- The macro-action reformulation (105.6) — the one remaining representation
  change, and the only untried item that 110.3 does not argue against, since it
  changes what a decision *is* rather than what describes it.
- Everything from 109.4, 108.4, 104.3.

---

## 111. The reroll premise, measured at last: real lines are better, the engine's are neutral (08-10)

Ten entries treated `slowroll6`'s **+0.553 (t=+3.54)** deficit (100) as a defect
because reroll lines are mainstream, viable play in real TFT. The viability half
came from general knowledge of the game and was never measured, while 2,000
ranked Set 17 matches have sat in `data/reference/` since 97. Lesson 24 one step
earlier: check the reference exhibits the phenomenon before quoting a gap
against it.

`scripts/reroll_reference.py` classifies a seat as **reroll** if its board at
elimination holds a **cost-2 3-star** — the payoff `slowroll6` targets
(`target_cost=2`), and the only trace the line leaves in end-of-game state,
since Riot reports no roll counts and no level history.

### 111.1 A methodology error of mine, recorded because it was tempting

A seat that survives longer rolls more shops, so it both 3-stars more often and
places better; the naive split is confounded. My first repair was to stratify on
`last_round`, and it is **worse than the disease**. Elimination order essentially
*is* placement in TFT — measured here, round 27 → 6.88, round 37 → 1.68 — so
conditioning on it conditions on the outcome. Every within-stratum delta duly
collapsed to ±0.18 and the survival-controlled mean read +0.069, which I briefly
took for "reroll is neutral in reality". It is a collider control and shows
nothing. The table is still printed, with a warning, and is not evidence.

The design that works is the one the reference programme was built for: run the
**engine** through the identical classifier and statistic, so a bias present in
both arms cancels in the difference between them.

### 111.2 The measurement

| | reroll − other | t | n |
|---|---|---|---|
| real TFT (challenger + diamond) | **-0.410** | -9.58 | 16 000 |
| engine, `DEFAULT_FIELD`, 1000 games | **-0.031** | -0.47 | 8 000 |
| **engine − real** | **+0.379** | **+4.82** | |

Reroll seats place **4.171** against **4.582** in real TFT: the premise is
correct, the lines are genuinely good. In the engine the same seats place 4.475
against 4.506 — neutral. The engine under-rewards the line by **0.379 ± 0.079**
relative to reality, which is the reroll mispricing stated as a number for the
first time in this project.

At 250 games the engine arm read -0.121; at 1000 it reads -0.031. The 250-game
figure was noise, and quoting it would have overstated the engine's fidelity.

**An unlooked-for fidelity success.** Cost-2 3-star holders are **18.9%** of
engine seats against **19.9%** of real ones. The engine 3-stars at very nearly
the real rate.

### 111.3 The payoff hypothesis dies a third time, and differently

97.7 and 102.4 both proposed that the engine under-values a 3-star, and both
were withdrawn. 111.2 kills the idea in a cleaner way than either: *holding* a
cost-2 3-star in the engine is **neutral** (-0.031), not punished. Whatever
costs `slowroll6` its 0.553, it is not that the payoff is weak once obtained.

### 111.4 Where the deficit actually is

`scripts/reroll_cost_probe.py`, 400 games, mixed field, splitting each archetype
by whether it ever held the payoff (sticky, so a seat that hit and was later
dismantled still counts as a hit):

| archetype | hit rate | place \| hit | place \| miss | cost of miss | t | overall |
|---|---|---|---|---|---|---|
| standard | 0.2% | 4.000 | 4.252 | +0.252 | +0.25 | 4.252 |
| fast8 | 0.0% | — | 3.962 | — | — | 3.962 |
| hyperroll | 0.0% | — | 5.210 | — | — | 5.210 |
| **slowroll6** | **76.4%** | **4.516** | **6.799** | **+2.283** | **+16.22** | **5.055** |

Two separable effects, and neither is the 3-star's strength:

- **The miss branch is catastrophic.** 23.6% of `slowroll6` seats never hit, and
  they place 6.799. That is ~0.54 of the deficit on its own.
- **Hitting is not enough.** A `slowroll6` seat that *does* 3-star still places
  4.516, worse than `standard`'s 4.252 average. ~0.26 more.

### 111.5 The new hypothesis, after two withdrawn ones

> **REFUTED by entry 112.3.** Implemented at the round the hit distribution
> actually supports (5-2), the pivot improves the miss branch by 0.584 and
> moves the archetype **+0.006 (t=+0.05)**. The miss branch is real and is not
> where the deficit lives. 112.4 has what replaces this.

`slowroll6` **cannot pivot**. Its `roll_floors={'3-2': 50}` and level targets
hold it at level 6 until 5-1 whether or not it is hitting, so a seat that bricks
keeps rolling a shop that has already failed it, on a six-unit board, into stage
5. A real player who has not hit by 4-2 abandons and levels.

If that is the cause, then `slowroll6`'s deficit is a **scripted-policy defect,
not an engine mispricing** — and entries 96–103 were investigating an artefact
of the field rather than the simulator. That would not void 111.2's +0.379,
which is measured on 3-star *holders* across the whole field and is independent
of any one archetype's plan.

This is the same shape as 99 (interest floor with no endgame clause) and the
`desperation_hp` work, both of which fixed cleanly and bought nothing in
placement. The honest prior is therefore that the pivot closes the *miss branch*
and does not move the agent. It is still worth doing, because the claim under
test here is **fidelity**, not agent strength, and a field that plays a line no
real player would play is a bad comparator regardless of what it costs.

### 111.6 Still open

- Implement the pivot and re-measure both the archetype table and 111.2's
  difference of differences. Named outcomes first, and note that a pivot changes
  `slowroll6` into something that is no longer a slow roll if set too eagerly —
  lesson 25's residue, an intervention is only evidence once it is a *good*
  implementation.
- The residual +0.264 on the hit branch, which the pivot cannot touch: a
  six-unit board of 3-stars losing to an eight-unit board of 2-stars is the
  "board size dominates" finding (67, 68, 72) meeting the reroll line head-on.
  That, not 3-star strength in isolation, is where a real payoff mispricing
  would live.
- Whether real *missed* reroll attempts can be identified at all. They are
  invisible in end-of-game state, which bounds what this reference can settle.
- Everything from 110.5.

---

## 112. The pivot works, and is worth nothing; 111.5 refuted (08-10)

111.5 proposed that `slowroll6`'s deficit is a scripted-policy defect — the plan
has no clause for not hitting, so a bricked seat keeps rolling a failed shop
into stage 5. `pivot_at` implements the clause: once the round arrives and the
seat holds **zero** 3-stars at its target cost, targeting is dropped, the roll
floor becomes `pivot_floor`, and the level curve falls back to `STANDARD`'s.
Inert by default (`pivot_at=""`), so every pre-112 number reproduces.

Wired into **all three** consumers on **both** sides — `reroll_targets`, the
roll floor and the level curve, in `GreedyPolicy` and the teacher — per entry
86's rule.

### 112.1 The first arm deleted the archetype, and that is my error

Pivot at 4-2, the round a real player abandons:

| arm | slowroll6 | hit rate | place \| hit | place \| miss | standard | deficit |
|---|---|---|---|---|---|---|
| no pivot | 5.055 | **76.4%** | 4.516 | 6.799 | 4.252 | +0.803 |
| pivot 4-2 | 4.470 | **6.1%** | 4.143 | 4.491 | 4.446 | **+0.024** |

The deficit all but vanished, and it means nothing: the archetype stopped being
a reroll line. **Outcome 3 of the four named before the run** — lesson 25's
residue, an intervention is only evidence once it is a good implementation.

I took the real-player heuristic "no hit by 4-2, abandon" and assumed the timing
transfers, without measuring when this engine's `slowroll6` actually hits.

### 112.2 When it actually hits

600 `slowroll6` seats, 300 games, round of **first** cost-2 3-star:

| round | 4-2 | 4-3 | 4-4 | 4-5 | 4-6 | 4-7 | 5-1 | 5-2 | 5-3 | 5-4 | 5-5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| first hits | 18 | 39 | 51 | **95** | 83 | 72 | 49 | 7 | 12 | 15 | 14 |
| cumulative | 4.0% | 10.5% | 19.0% | 34.8% | 48.7% | 60.7% | 68.8% | 70.0% | 72.0% | 74.5% | 76.8% |

**4.0% have hit by 4-2**, which is the 6.1% above. The marginal rate collapses
after 5-1 (49 → 7), so 5-2 is where abandoning costs almost nothing — a rule
read off the distribution rather than a round chosen and then justified.

### 112.3 At the right round it is a clean null

| arm | slowroll6 | hit rate | place \| hit | place \| miss | standard | deficit |
|---|---|---|---|---|---|---|
| no pivot | 5.055 | 76.4% | 4.516 | 6.799 | 4.252 | +0.803 |
| pivot 5-2 | 5.061 | 71.5% | 4.601 | **6.215** | 4.252 | +0.810 |

**+0.006, t=+0.05, n=800 seats.** The pivot does what it was built to do — the
miss branch improves by 0.584 — and the gain is spent exactly: hit rate falls
4.9 points and the hitters lose 0.085. Net zero.

`standard` read **+0.000 (t=+0.00)** here against **+0.194 (t=+2.10)** in the
4-2 arm, which is the sanity arm working. That movement is not a confound to be
removed but arithmetic: placements in a lobby sum to a constant, so an archetype
cannot gain without the other seats losing. It is why the deficit against
`standard`, not raw archetype placement, is the statistic.

### 112.4 What this settles

**111.5 is refuted, and it was mine.** The miss branch is real, is worth 0.584
to the seats in it, and is *not* where the deficit lives — closing it changes
nothing. The third time in this log a policy defect has been found, fixed
cleanly, and bought nothing (99, 103, here), which is now less a run of bad luck
than a property of this field.

Read together with 112.1, something stronger follows. Abandoning at 4-2 gives a
deficit of +0.024 and abandoning at 5-2 gives +0.810: **the earlier the line is
abandoned the better it does, and the best available version of `slowroll6` is
to not slow roll at all.** In this engine the reroll line is dominated at every
pivot point tested.

That returns the mispricing to the simulator, where 111.2 measured it at
**+0.379 (t=+4.82)** against real data — and no policy patch to the field
touches it. 111.3 already killed "a 3-star is worth too little" in isolation.
The surviving candidate is 111.6's: a six-unit board of 3-stars losing to an
eight-unit board of 2-stars, which is "board size dominates" (67, 68, 72)
meeting the reroll line head on.

### 112.5 Still open

- The board-size interaction, now the only surviving explanation for the +0.379.
  It is a *combat* question and testable without any policy: field a fixed
  six-unit 3-star board against an eight-unit 2-star board and measure, rather
  than inferring from placements.
- `pivot_at` stays in the tree, inert, tested and measured. It is the right
  behaviour for a field meant to resemble real play even though it costs
  nothing, but it should not be switched on silently — that would move every
  field number for no gain.
- Everything from 111.6 and 110.5.

---

## 113. It is the board slot, not the 3-star: real boards lose at 36.2% carrying more value (08-10)

112.4 left one candidate for the +0.379 mispricing: a six-unit board of 3-stars
losing to an eight-unit board of 2-stars. Every number in that chain came from
placements. This asks it in combat, where there is no economy, no shop and no
elimination order.

### 113.1 Two harness errors, both caught by controls

**The positioning was mirrored twice.** `place_team`'s contract is "row 0 is the
front line" for *both* teams -- `Board.to_combat` mirrors team 1 onto the far
half. The first version passed rows 3/2 for team 0 and 0/1 for team 1, putting
team 0's melee in its **back** row. A same-archetype control, which must be 50%
by symmetry, read **35.6% with a -2.38 survivor margin**: nearly the whole
cross-archetype effect was the handicap. Fixed, the controls read 52.6% (+0.44)
and 50.2% (-0.05).

Without the control this would have been reported as a decisive finding. It cost
one line to include.

**The idealised probe was not value-matched.** Six cost-2 3-stars is 108 board
value; eight cost-3 2-stars is 72. The 100% win rate in that row measures a 50%
value advantage, not a slot trade, and it does not refute anything. Kept below
for what it does show, labelled.

### 113.2 What the isolated fights do show

40 trials per row, champions redrawn per trial and identical across the row:

| left | right | win | margin |
|---|---|---|---|
| 1x cost-1 3-star | 1x cost-3 2-star | 90.0% | +0.80 |
| 1x cost-2 3-star | 1x cost-4 2-star | 62.5% | +0.25 |
| 1x cost-3 3-star | 1x cost-5 2-star | 61.3% | +0.23 |

**The design heuristic holds.** A 3-star of cost N beats a 2-star of cost N+2,
mildly, which is what "roughly equivalent" should look like. Star stats come
from per-champion arrays in the Riot payload rather than a computed multiplier,
so there was no scaling constant to be wrong -- and this confirms none is.

### 113.3 The real boards, with no idealisation at all

Final boards captured from 400 games of `DEFAULT_FIELD`, then replayed head to
head, 1200 fights per row, **items included**:

| matchup | win | margin | value L | value R | units L | units R |
|---|---|---|---|---|---|---|
| **slowroll6 vs standard** | **36.4%** | **-2.42** | **66.3** | 65.2 | **7.61** | 9.05 |
| fast8 vs standard | 55.0% | +0.80 | 64.2 | 65.5 | 9.16 | 8.97 |
| *standard vs standard* | *50.2%* | *-0.06* | | | | |
| *slowroll6 vs slowroll6* | *52.6%* | *+0.28* | | | | |

**Precision, because it bit.** The headline is stable across captures --
36.2%/-2.23 at 150 games, 36.4%/-2.42 at 400 -- but at **40** games it read
**52.0%/-0.27**, drawn from only 80 `slowroll6` boards whose mean value happened
to be 70.2 rather than 66. The varying quantity is *which boards are captured*,
not the fights, so fight count does not buy precision and the capture size must
be reported. `fast8 vs standard` has **not** settled (48.2%, 49.0%, 55.0% across
three captures) and should not be quoted beyond its sign.

And the compositions those archetypes actually reach, 200 games:

| archetype | place | level | units | 3-stars | 2-stars | value |
|---|---|---|---|---|---|---|
| standard | 4.25 | 8.63 | 8.97 | 0.01 | 8.40 | 65.50 |
| fast8 | 4.03 | 8.70 | 9.12 | 0.00 | 7.63 | 61.80 |
| **slowroll6** | 4.97 | **7.29** | **7.67** | **1.34** | 6.13 | **66.50** |
| hyperroll | 5.24 | 8.03 | 8.46 | 0.15 | 7.24 | 44.47 |

`slowroll6` reaches **1.34** 3-stars, not six -- which is why 113.1's idealised
matchup was the wrong question as well as the wrong measurement.

### 113.4 The finding

Read the two tables together:

- `slowroll6` carries **more** board value than `standard` (66.3 against 65.2 in
  the matched fights, and the highest end-of-game value of any archetype at
  66.50) on **1.44 fewer units**, and loses by 2.42 survivors at a 36.4% win
  rate.
- `fast8` carries slightly **less** value on slightly **more** units and is at
  worst even and at best ahead (48.2-55.0% across captures).

> **A board slot is worth more than the value in it.** Concentrating the same
> gold into fewer, higher-star units is a losing trade in this engine, and
> spreading less gold over more units is free.

That is the mispricing, and it is neither the 3-star's stats (113.2, and 111.3)
nor any policy (112). It is the marginal value of a slot -- which is "board size
dominates" (67, 68, 72) restated as a fidelity defect rather than an
observation about the agent, and it explains why every archetype that trades
slots for quality has underperformed since entry 73.

### 113.5 Still open

- **The mechanism.** The most likely candidate is trait breakpoints: more units
  activate more traits, and the probe's own trait columns move with unit count
  (2.3 for the six-unit side against 3.0 for the nine-unit side). If a slot's
  worth is mostly its trait contribution, then the engine's trait tiers are
  doing work Riot's do not. Directly testable by re-running 113.3 with traits
  disabled on both sides.
- Whether real TFT shows the same slot dominance. `data/reference/` carries unit
  counts per participant and can be conditioned the same way, which would put a
  number on the marginal slot in reality for comparison.
- `scripts/star_value_probe.py` keeps its idealised row. It should be made
  value-matched before it is quoted for anything.
- Everything from 112.5 and 110.5.

---

## 114. A board slot is worth 2.9 star-ups, and that closes the arithmetic (08-11)

113.4 claimed a slot is worth more than the value in it, inferred from two
archetypes differing in several ways at once. `scripts/slot_value_probe.py`
prices both sides directly: take one captured `standard` board, perturb exactly
one thing, and fight it against an unperturbed board from the same pool.

### 114.1 Traits are not the mechanism

113.5's first candidate, tested by stripping every champion's trait tuple so no
breakpoint can activate, with boards still *captured* from normal games:

| | slowroll6 vs standard | control (std v std) |
|---|---|---|
| traits on | 36.4%, **-2.42** | 50.2%, -0.06 |
| traits off | 39.7%, **-1.81** | 50.7%, -0.01 |

Breakpoints account for **0.61 of 2.42** — about a quarter. Three quarters
survives with every trait in the game disabled. **Outcome 2 of the three named
before the run**: it is bodies, not tiers.

### 114.2 The two prices

300 games -> 900 `standard` boards, 900 fights per row. Units are dropped or
upgraded **weakest first** (by star, then cost), which is the order a real plan
sheds or stars them:

| perturbation | margin | win | per unit |
|---|---|---|---|
| none (control) | +0.37 | 52.8% | — |
| drop 1 weakest | -1.86 | 38.0% | **-2.23** |
| drop 2 weakest | -4.08 | 24.8% | **-2.23** |
| drop 3 weakest | -5.60 | 15.6% | -1.99 |
| upgrade 1 to 3-star | +1.14 | 56.9% | **+0.77** |
| upgrade 2 to 3-star | +1.91 | 62.7% | **+0.77** |
| upgrade 3 to 3-star | +2.84 | 69.6% | +0.82 |

> **A board slot is worth ~2.2 survivors. A star-up is worth ~0.78. The slot is
> worth 2.9x the star-up.**

Both prices are linear in k, which is itself worth noting: there is no
diminishing return on slots over the range that separates these archetypes, and
none on star-ups either.

### 114.3 It closes 113's arithmetic

`slowroll6` trades **1.44 slots for 1.33 star-ups** (113.3):

| | |
|---|---|
| cost of the slots | 1.44 x 2.23 = **-3.21** |
| gain from the star-ups | 1.33 x 0.78 = **+1.04** |
| predicted margin | **-2.17** |
| measured margin (113.3) | **-2.42** |

Two independently measured prices predict ~90% of a deficit measured a
different way. That is the strongest quantitative account this project has of
why any archetype under-performs, and it is a statement about the **simulator**,
not about a policy or an observation.

It also explains the shape of everything since 73 without needing 3-stars to be
weak: `hyperroll` (8.46 units) and `slowroll6` (7.67) are the two archetypes
that end with the fewest slots and the two that place worst; `fast8` ends with
the most (9.12) on the *least* value and places best.

### 114.4 What this does and does not establish

> **Answered by entry 115.2, and the answer is no.** Measured in placement in
> both arms, real TFT prices a slot at **2.62** star-ups against the engine's
> **1.97** — the engine values a 3-star *more* relative to a slot than reality
> does, which is the wrong direction to explain the reroll deficit. The prices
> below stand as facts about the engine; the defect is not in their ratio.

It does **not** yet establish that 2.9x is wrong. It is the engine's exchange
rate; whether real TFT's differs is a separate measurement, and the +0.379 of
111.2 says only that *something* differs.

Two cautions on the numbers themselves:

- The k=0 control reads **+0.37**, not 0.00. Every `per unit` figure is a
  difference from that control rather than from zero, which is why the row
  exists — but a residual that size means the two-decimal precision above is
  not real, and the honest claim is "about 2.2 against about 0.8".
- The drop rows remove the **weakest** units, so -2.23 is the price of a
  *marginal* slot. A slot holding a carry is worth more, and this says nothing
  about that.

### 114.5 Still open

- **The reference comparison, which is now the decisive one.** Real matches
  carry unit counts and star levels per participant, so the marginal placement
  per unit and per 3-star can be measured in `data/reference/` and in the engine
  by the same method. Neither figure is clean alone — the survival confound of
  111.1 applies to both — but the *ratio* compared across arms is the same
  difference-of-differences design that worked in 111.2. If real TFT prices a
  slot at well under 2.9 star-ups, the engine's exchange rate is the defect and
  it is a single, findable thing.
- Why a slot is worth 2.2 survivors when traits are off. Candidates are the
  focus-fire and target-selection rules (more bodies absorb more attacks) and
  the survivor-margin measure itself rewarding bodies mechanically — the latter
  would make the *metric* partly responsible and is worth checking before the
  exchange rate is called a defect.
- Everything from 113.5, 112.5 and 110.5.

---

## 115. The exchange rate is not the defect; the field's archetype coverage is (08-11)

114.5 set the decisive test: price a slot against a star-up in *both* arms, in
the same units, and compare the ratios. Survivor margin does not exist in Riot's
data, so the common currency is placement — fit
`placement ~ b0 + b_units * units + b_stars * three_stars` per arm and read
`b_units / b_stars`. Neither coefficient is causal, but the confound sits in
both arms, so comparing ratios is 111.2's design.

### 115.1 The metric was not inflating the slot

114.5 worried that survivor margin rewards bodies mechanically. It does not
inflate the result — read off 114.2's own win-rate column, which has no
body-count term:

| measure | slot | star-up | ratio |
|---|---|---|---|
| survivor margin | -2.23 | +0.77 | 2.9x |
| win rate | -14.8pp | +4.1pp | **3.6x** |

The body-independent measure gives a *larger* ratio, so if anything margin
understates the slot.

### 115.2 Real TFT prices the slot higher, not lower

| arm | b_units | b_stars | **slots per star-up** | n |
|---|---|---|---|---|
| real | -1.062 | -0.406 | **2.62** | 15 995 |
| engine | -1.452 | -0.739 | **1.97** | 3 200 |

Every coefficient is negative in both arms, so the fits are interpretable
(the failure mode named before the run was a positive coefficient, meaning the
survival confound had swamped the quantity).

**Outcome 2 of the three named, and opposite in direction to 114's hypothesis.**
The engine values a 3-star *more* relative to a board slot than reality does. If
the exchange rate were the reroll defect, `slowroll6` would be over-performing
here. 114.4 declined to claim 2.9x was wrong; that caution was right.

### 115.3 The gap that is real: the engine only 3-stars what a policy targets

> **The attribution is WITHDRAWN by entry 116.2.** The measured shortfall (0.46x
> overall, cost-2 matching at 1.03) stands. Blaming it on field coverage does
> not: adding a `target_cost=3` seat reaches 0.048 of the 0.179 target and makes
> the overall profile *worse*. 116.5 lists what coverage, odds, pools and gold
> have each been eliminated as.

3-stars per seat, by champion cost, both arms conditioned identically:

| cost | real | engine | ratio |
|---|---|---|---|
| 1 | 0.271 | 0.025 | **0.09** |
| 2 | 0.326 | 0.335 | **1.03** |
| 3 | 0.179 | 0.003 | **0.01** |
| 4 | 0.011 | 0.000 | 0.00 |
| 5 | 0.003 | 0.000 | 0.00 |
| **total** | **0.790** | **0.363** | **0.46** |

Cost-2 matches reality to within 3%. Costs 1 and 3 are at **9%** and **1%** of
it. The cause needs no measurement: `DEFAULT_FIELD` is 3 standard, 2 fast8, 2
`slowroll6` (`target_cost=2`) and 1 `hyperroll` (`target_cost=1`). **No seat
targets cost 3**, and one of eight targets cost 1. The engine 3-stars precisely
what some plan aims at and essentially nothing else, because `reroll_targets`
returns empty without `target_cost` and an untargeted seat spreads its buys
(entry 73, entry 86).

This is a **field coverage** gap, not a simulator one, and it is the largest
single fidelity discrepancy now measured. It also retro-justifies 111.2: that
difference-of-differences was computed on cost-2 3-star holders, the one cost
where the two arms agree.

### 115.4 Two measurements now disagree, and that is the honest state

- 111.2, on pooled placement of cost-2 3-star holders: the engine
  **under**-rewards the line by +0.379 (t=+4.82).
- 115.2, on the slot/star-up ratio: the engine **over**-values a 3-star relative
  to a slot, 1.97 against 2.62.

Both are confounded, differently — 111.2 by survival, 115.2 by whatever units
and 3-star counts jointly proxy — and they point opposite ways. So neither is a
clean causal estimate of what a 3-star is worth, and **the reroll question is
not settled**. What is settled is narrower and firmer: 114's prices are real
within the engine and predict 90% of the combat deficit; 113.2 shows the star
stats themselves are right; 115.3 shows the field does not attempt most of the
reroll lines real players run.

Recorded as an open disagreement rather than resolved in favour of whichever
number is more convenient.

### 115.5 Still open

- **Add a cost-3 reroll archetype to `DEFAULT_FIELD`** and re-measure 115.3.
  Real players 3-star cost-3 units at 0.179 per seat; this field does it at
  0.003. That is a concrete, bounded change with a stated target, and it is the
  first fidelity item in this whole arc that is not a hypothesis about the
  simulator.
- Whether the field's *composition* (3/2/2/1) matches real archetype shares at
  all. It was chosen in entry 70 without reference data; `data/reference/` can
  now estimate the real mix from 3-star costs and final levels.
- Reconciling 115.4's two measurements, which probably needs an estimator that
  is not cross-sectional.
- Everything from 114.5, 113.5 and 110.5.

---

## 116. The 3-star shortfall is not coverage, odds, pools or gold (08-11)

115.3 attributed the engine's 0.46x 3-star rate to **field coverage** — no seat
sets `target_cost=3`, and the engine 3-stars only what a plan aims at. 115.5
made adding that archetype the next step, with a pre-registered target: real
seats hold 0.179 cost-3 3-stars each.

### 116.1 The real mix, which 115.5 asked for

Classifying each real seat by its cheapest 3-star. **A lower bound on every
reroll share**, since a bricked attempt is indistinguishable from never trying:

| archetype | seats/lobby | share | avg level | avg place |
|---|---|---|---|---|
| no 3-star | 5.01 | 62.7% | 8.76 | 4.67 |
| reroll1 | **1.42** | 17.7% | 8.26 | **4.43** |
| reroll2 | **0.98** | 12.3% | 8.12 | **4.15** |
| reroll3 | **0.50** | 6.2% | 7.99 | **4.21** |
| reroll4 | 0.07 | 0.9% | 9.15 | 1.32 |

Every reroll line beats the no-3-star majority, which is 111's premise
confirmed a second way. And `DEFAULT_FIELD` is **overweight** at cost 2 — two
`slowroll6` seats produce 1.51 holders per lobby against reality's 0.98 — while
running 0.2 against 1.42 at cost 1 and 0.02 against 0.50 at cost 3.

### 116.2 `SLOWROLL7` added, and it made fidelity worse

A 3-cost reroll line at level 7 (real reroll3 seats average level 7.99), rolling
from 4-1. 300 games per field, scored by total absolute deviation from the real
per-cost profile:

| field | c1 | c2 | c3 | total | \|err\| |
|---|---|---|---|---|---|
| REAL | 0.271 | 0.326 | 0.179 | 0.790 | — |
| current (3/2/2/1) | 0.024 | 0.342 | 0.003 | 0.370 | **0.453** |
| with slowroll7 | 0.024 | 0.173 | 0.048 | 0.246 | **0.544** |
| mix-matched | 0.052 | 0.167 | 0.044 | 0.263 | 0.527 |

Swapping a `slowroll6` seat for `slowroll7` halves cost-2 and lifts cost-3 only
to 0.048 of a 0.179 target. **115.3's attribution was wrong**, and it was mine:
a seat dedicated to the line reaches 27% of the real rate, so coverage was at
most part of it. Per seat, `slowroll6` ends with 1.38 cost-2 3-stars and
`slowroll7` with 0.38 cost-3, against real holders averaging ~2.9.

### 116.3 Not the odds, and not the pools

Straight from `config.json`, no simulation. Rolls needed for 9 copies of one
**named** champion, at 5 slots per roll:

| level | c1 | c2 | c3 | c4 |
|---|---|---|---|---|
| 5 | 56.0 | 70.9 | 117.0 | 1260 |
| 6 | 84.0 | **58.5** | 93.6 | 504 |
| 7 | 132.6 | 78.0 | **58.5** | 252 |
| 8 | 168.0 | 117.0 | 73.1 | 84.0 |

Cost-2 at level 6 and cost-3 at level 7 are **identical at 58.5**, so the odds
do not distinguish the two lines. Pool sizes (30/25/18/10/9) and champions per
cost (14/13/13/14/9) both match real Set 17.

### 116.4 Not gold either

Roll volume, 200 games, counted by wrapping `PlayerState.reroll`:

| archetype | rolls/game | gold at end | 3-stars |
|---|---|---|---|
| fast8 | 6.9 | 27.3 | 0.000 |
| hyperroll | 17.9 | 33.6 | 0.165 |
| slowroll6 | 46.8 | 46.2 | 1.270 |
| slowroll7 | 37.3 | 46.7 | 0.385 |
| standard | 19.1 | 32.5 | 0.012 |

Both reroll lines die holding ~46 gold — 23 unspent rolls — because their
`roll_floors` sit at 50 and they never dip into the bank, where a real
slow-roller commits down to 20-30. Real seats hold ~8 at elimination (97.4).

That looked decisive and is not. Sweeping the floor across every rolling
archetype, 250 games per arm:

| roll floor | c1 | c2 | c3 | total | \|err\| | gold at end |
|---|---|---|---|---|---|---|
| REAL | 0.271 | 0.326 | 0.179 | **0.790** | — | 8.0 |
| 50 (current) | 0.023 | 0.172 | 0.050 | 0.245 | 0.545 | 34.5 |
| 30 | 0.053 | 0.172 | 0.046 | 0.271 | 0.519 | 29.5 |
| 20 | 0.051 | 0.161 | 0.050 | 0.262 | 0.528 | 26.9 |
| 10 | 0.061 | 0.166 | 0.048 | 0.276 | 0.515 | 24.8 |
| 0 | 0.053 | 0.116 | 0.029 | 0.198 | 0.593 | 22.6 |

Gold at elimination falls 34.5 -> 24.8 and the 3-star total moves 0.245 ->
0.276 against a 0.790 target. At floor 0 it gets **worse**: the seat rolls away
the gold it needs to buy what the rolls turn up.

*(The `rolls` column of that sweep averaged over all eight seats, most of which
barely roll, so it was uninformative and is omitted here. 116.4's per-archetype
table is the one to read.)*

### 116.5 Where that leaves it

Four candidates eliminated for the 0.46x 3-star rate: **archetype coverage**
(116.2), **shop odds** (116.3), **pool sizes** (116.3) and **gold committed to
rolling** (116.4). The rate is 0.245-0.370 per seat against a real 0.790 and
nothing tried moves it.

What has not been tested, in order of my confidence:

- **Pool contention.** Eight seats share one pool, and two of them target the
  same cost tier by the same rule. Real lobbies contest too, but not with two
  bots running an identical `reroll_targets` heuristic. Measurable by running a
  field with exactly one reroll seat and comparing its per-seat hit rate.
- **The targeting rule itself.** `reroll_targets` picks by copies already held,
  re-derived every call, so an unlucky early shop can move the commitment
  around; a real player fixes on a carry and stays. Measurable by pinning the
  targets once and comparing.
- **Conditioning.** Real "holders" are conditioned on success. `slowroll6` hits
  76.4% and averages 1.66 3-stars *per hitter* against real holders' ~2.65, so
  the conditional gap (1.6x) is smaller than the marginal one (2.2x) and part
  of what 115.3 called a shortfall is a selection effect.

`SLOWROLL7` stays in `STRATEGIES` and **out of `DEFAULT_FIELD`**: it is the
instrument that produced 116.2 and every existing field number reproduces
without it. Adding it would void baselines for a measured fidelity *loss*.

---

## 117. The shop supplies enough copies; the targeting rule strands 46% of them (08-11)

116.5 listed three untested causes for the 0.46x 3-star rate, in confidence
order: pool contention, the targeting rule, and conditioning. Measured in that
order.

### 117.1 Contention: eliminated

Cost-2 3-stars per `slowroll6` seat as reroll seats are added to the lobby,
reported **per reroll seat** so composition does not confound it, 250 games per
arm:

| reroll seats | c2 3-stars/seat | hit rate | 3-stars/hitter | placement |
|---|---|---|---|---|
| 1 | 1.372 | 74.4% | **1.844** | 5.296 |
| 2 | 1.324 | 74.4% | 1.780 | 5.316 |
| 3 | 1.364 | 76.9% | 1.773 | 5.331 |
| 4 | 1.402 | 78.9% | 1.777 | 5.117 |

Flat, and if anything rising. Two bots running the same `reroll_targets`
heuristic against one pool do not starve each other. **A lone reroll seat with
the whole pool to itself still reaches 1.844 per hitter against reality's
~2.65**, so contention is not the constraint and conditioning (116.5's third
candidate) accounts for part of the marginal gap but not the conditional one.

### 117.2 The rule: confirmed, and the numbers are stark

> **The mechanism is WITHDRAWN by entry 118.2.** The measurements stand — 26.47
> copies, 3.69 champions, 12.31 stranded. The reading does not. Copies *scale
> with* `target_count` rather than being divided by it, the extra champions are
> bought by the generic rule rather than by target drift, and hysteresis against
> the drift measured a clean null (118.1). 118.3 then found cost-2 was never
> short in the first place.

What a `slowroll6` seat holds at the end, 400 seats:

| | |
|---|---|
| cost-2 copy-equivalents held | **26.47** |
| distinct cost-2 champions held | **3.69** |
| copies on champions below 9 | **12.31** |
| 3-stars if perfectly concentrated | **2.94** |
| 3-stars actually reached | **1.32** |

> **The shop is not the problem. The seat acquires 26.5 cost-2 copies — enough
> for 2.94 three-stars, against real holders' ~2.65 — and converts 45% of them.
> 12.31 copies, 46% of everything bought, sit on champions that never reach
> nine.**

That closes 116.5. Coverage, odds, pools, gold and contention are all
eliminated; the acquisition rate is *already correct*; the loss is entirely in
conversion.

The mechanism is visible in `reroll_targets` and was a deliberate design choice
(the docstring: "chosen by copies already held, so the commitment emerges from
what the shop has offered rather than being fixed in advance -- which is how a
player actually picks a reroll carry"). It is re-derived on **every call**, so
the top-3-by-copies set drifts as the shop offers things: the seat buys toward
whichever champions it currently leads on, that lead changes, and copies strand
behind it. 3.69 distinct champions held for a `target_count` of 3 is the
signature.

The reasoning behind the design is right — a player does discover their carry
rather than fixing it in advance — but a real player discovers it *once* and
then commits. This rule re-discovers it every planning phase.

### 117.3 Why this matters beyond the reroll line

The 3-star rate is the largest measured fidelity gap (115.3: 0.46x overall),
and it now has a single cause that is neither a constant nor a spec question.
It also reframes entries 111-116: the reroll archetype in this engine is not
being punished by combat or economy, it is **failing to build the board it is
trying to build**, and every placement comparison involving `slowroll6` since
entry 73 has been measuring a policy that converts under half the copies it
buys.

Whether fixing it moves *placement* is a separate question, and the honest
prior from 99, 103 and 112 is that it will not. It should still be fixed: the
claim under test in this arc is fidelity.

### 117.4 The fix, specified but not implemented

Give the commitment hysteresis: once a champion has been chosen as a target and
the seat holds enough copies to be committed, keep it until it completes or the
plan pivots. `reroll_targets` is currently a pure function of `(player, econ,
now)` and is shared by `GreedyPolicy` and the teacher (entry 86's rule), so
making it stateful touches both consumers and needs the same both-sides guard
`test_econ_fields` provides.

Named before implementing, so the result cannot be fitted afterwards:

1. Conversion rises toward 2.94 and the 3-star rate approaches real. Fidelity
   fixed, placement probably unmoved (99, 103, 112).
2. Conversion rises and placement *worsens* — committing to a bad carry is
   worse than drifting. This is the interesting outcome and it would say the
   drift is doing useful work.
3. Conversion does not rise, meaning the drift is not what strands the copies
   and 117.2's mechanism is wrong.

### 117.5 Still open

- Implement 117.4 and measure against the real per-cost profile (`|err|` from
  116.2, currently 0.453 for the shipped field).
- Cost-1 remains unexplained at 0.023 against a real 0.271, and `hyperroll`
  rolls only 17.9 times a game. Its level curve reaches 6 by 3-2, where a
  1-cost needs 84 rolls per named champion against 56 at level 5 (116.3). That
  is a *different* defect from this one and has not been measured.
- Everything from 115.5 and 110.5.

---

## 118. Cost-2 already matches reality; the shortfall is hyperroll's rolling window (08-11)

117.4 named three outcomes for commitment hysteresis. The answer was the third
— the mechanism was wrong — and chasing it properly moved the whole diagnosis.

### 118.1 Hysteresis: a clean null, and reverted

Preferring champions already past `COMMIT_COPIES=4` over ones merely leading on
raw copies produced **byte-identical** numbers: 26.47 copies, 3.69 champions,
12.31 stranded; `|err|` 0.453 -> 0.458.

The reason is visible in 117.2's own figures. At ~7 copies per champion held,
every candidate is past any sane threshold, so the "committed" ordering is the
old ordering. The drift 117.2 identified happens at **1-3 copies**, and
end-state hysteresis cannot see it. **Outcome 3 as named.** Reverted rather
than shipped — 25 lines that change nothing are worse than none — with the
finding left as a comment where the next person will look.

### 118.2 `target_count` is not a budget split, and 3 is already optimal

117.2 read 26.5 copies over 3 targets as 8.8 each, just under the 9 a 3-star
needs. That reading was wrong. 250 games per arm:

| target_count | c2 3-stars/seat | hit% | 3-stars/hitter | copies | champs | placement |
|---|---|---|---|---|---|---|
| 1 | 0.644 | 64.4% | 1.000 | 16.88 | 3.49 | 5.060 |
| 2 | 1.096 | 74.4% | 1.473 | 21.83 | 3.47 | 4.926 |
| **3 (current)** | **1.376** | 78.0% | 1.764 | 26.58 | 3.68 | **4.898** |
| 4 | 1.478 | 77.8% | 1.900 | 31.23 | 4.30 | 5.066 |

Copies **scale with** `target_count` (16.9 -> 31.2) rather than being divided by
it: targeting is what makes the seat buy aggressively at all, so fewer targets
means fewer copies, not more per champion. Concentrating is strictly worse, and
the shipped value of 3 is the placement optimum.

`champs` stays ~3.5 even at `target_count=1`, so the extra champions are bought
by the *generic* rule (owned / synergy / cost), not by targeting. 117.2's
"targeting drift" mechanism is therefore wrong on both counts.

### 118.3 Cost-2 was never the problem

Two `slowroll6` seats at 1.376 each over 8 seats is **0.344** cost-2 3-stars per
seat, against a real **0.326** (115.3). **The engine matches reality at cost 2
to within 6%.** Every per-cost table since 115.3 said so — 0.342 against 0.326 —
and I read the *total* (0.46x) as a uniform shortfall instead of reading the
row.

So the 3-star gap is entirely costs **1** (0.023 against 0.271) and **3** (0.003
against 0.179), and the reroll archetype that has driven entries 111-117 is,
on its own axis, correct.

### 118.4 The anomaly, stated precisely

| archetype | targets | 3-stars/seat | rolls/game |
|---|---|---|---|
| slowroll6 | cost 2 | **1.376** | 46.8 |
| hyperroll | cost 1 | **0.165** | 17.9 |

Two archetypes of identical shape — hold a level, roll the surplus, commit to
`target_count` champions — and an **8x** difference in yield. 116.3's odds table
explains it: a 1-cost needs **56** rolls per named champion at level 5 and
**84** at level 6, while a 2-cost needs 58.5 at level 6. `HYPERROLL` reaches
level 6 at 3-2 and its standing roll floor of 50 applies from 3-2 onward, so
almost all of its rolling happens at the level where 1-costs are *worst*, and
only 17.9 rolls happen at all.

Real hyperroll is played the other way round: stay low, roll in stage 2, and
level after hitting. Real seats end with 0.271 cost-1 3-stars and place 4.43
(116.1) — the largest reroll group in the data and a good one.

### 118.5 Still open

- Re-time `HYPERROLL`: hold level 5 through the stage-2/3 roll window instead
  of reaching 6 at 3-2, and re-measure the per-cost profile against 0.271. This
  is the same shape of fix as 111.5's pivot and 112 says to expect no placement
  gain — the claim under test is fidelity.
- Cost-3 at 0.003 against 0.179 remains unexplained; 116.2 showed a dedicated
  seat reaches only 0.048, and 118.4's timing argument does not obviously apply
  since level 7 is exactly where 3-costs are cheapest to hit (58.5 rolls).
- The lesson candidate from 118.3, not yet promoted: **when a total is off,
  read the rows before theorising about the total.** Four entries (115-117)
  pursued a uniform shortfall that the per-cost table had already localised.

---

## 119. Hyperroll can hit or it can level, never both; real TFT does both (08-11)

118.4 localised the last of the 3-star gap to `HYPERROLL`: 0.176 1-cost 3-stars
per seat where a 1-cost needs **56** rolls per named champion at level 5 and
**84** at level 6 (116.3), and the plan reaches level 6 at 3-2 with its roll
floor applying from 3-2 onward. 118.5 predicted the fix would need a
*conditional* transition rather than a longer hold, because entry 73 already
measured a fixed hold at 6.07.

### 119.1 The timing story is right

250 games per arm, `DEFAULT_FIELD` with only the hyperroll seat changed:

| variant | c1 3-stars/hyper seat | c1/seat | rolls | end level | placement |
|---|---|---|---|---|---|
| **real TFT** | — | **0.271** | — | **8.26** | **4.43** |
| current | 0.176 | 0.022 | 17.5 | 8.00 | 5.228 |
| hold 5 to 4-1 | 1.248 | 0.156 | 42.1 | 7.20 | 5.516 |
| hold 5, floor 30 | 1.232 | 0.154 | 43.3 | 7.31 | 5.568 |
| hold 5 to 4-5 (entry 73) | 1.576 | 0.197 | 50.4 | 6.78 | 5.648 |
| commit 5 + pivot 4-2 | 1.040 | 0.130 | 37.7 | 7.13 | 5.652 |
| commit 5, no pivot | **1.776** | **0.222** | 54.8 | **6.44** | 5.752 |

Holding the level lifts the hit rate **7-10x**, from 0.176 to as much as 1.776
per seat. The odds argument is confirmed.

### 119.2 `commit_level`, the mirror of `pivot_at`

A level *cap* that applies until the line lands, then releases to the plan's own
curve — `pivot_at` asks "have I given up?", this asks "have I got there yet?".
Ordered so a pivot outranks a commit: a bricked seat abandons rather than
sitting at the cap forever. Inert at 0, so every pre-119 number reproduces.
Four semantics tests plus an ordering test, all three mutations caught
(cap ignoring the hit condition, cap replacing rather than capping the curve,
and commit outranking pivot).

### 119.3 Releasing on the first hit was wrong, and the numbers said so

The first version released the cap on **any** 3-star. That yielded **1.100**
per seat — *worse than never releasing at all* (1.248) — because the seat levels
out of its own shop odds with two of its three carries still at 2-star.
`target_count` is the right threshold, and `line_complete` is deliberately a
different predicate from `has_hit`: the pivot asks whether *anything* landed,
the commit asks whether *everything* did. With that corrected the arm reaches
1.776, the best of any variant.

### 119.4 The structural finding, which is the point

> **WITHDRAWN by entry 120.2.** The budget was priced and it *does* permit both:
> a seat that levels up the standard curve and then rolls its surplus from 5-1
> reaches level 8 with P(1-cost 3-star) = 0.577, clearing the real corner. The
> monotone frontier below is real but is an artefact of the only lever this
> entry tried — capping the level — not a property of the economy.

Read the table by columns rather than by row:

> **Across all six arms, 1-cost 3-stars and end level trade off monotonically,
> and placement tracks level. The engine can hit *or* it can level. Real seats
> do both: 0.271 three-stars at level 8.26, placing 4.43.**

Every variant lands on the same frontier — 0.022 at level 8.00, 0.222 at level
6.44 — and no point on it reaches the real corner. That is not a parameter this
project has failed to tune; it is the shape of the whole trade-off, and it says
the *budget* (income, XP cost, roll cost, rounds available) does not permit what
real players routinely do.

Which is an engine-economy question, not a policy one, and it is the first time
this arc has produced one. Every constant involved is `community_documented`
rather than Riot-published: `xp_purchase_gold`, `xp_to_next_level`,
`reroll_cost`, `base_income`, `income_ramp`, `interest_per_gold` (doc 02 sec
4b's provenance block).

Stopping the sweep here deliberately. Continuing to tune `commit_level`,
`target_count` and floors against a target of 0.271 would eventually find a
combination that hits it, and it would be fitted rather than measured.

### 119.5 Still open

- **Price the budget.** Real seats reach level 8.26 *and* roll enough for 0.271
  1-cost 3-stars. Compute what that costs in gold against what a seat earns in
  this engine's economy. If it does not fit, one of the community-documented
  economy constants is wrong, and the arithmetic will say which. This is cheap
  and needs no simulation.
- `commit_level` stays **out of every shipped strategy**: it is the instrument
  for 119.1, and switching it on trades 0.2 placement across a field seat for
  fidelity on one metric, which is not a call to make silently.
- Cost-3 at 0.003 against 0.179 is still unexplained (116.2, 118.5).
- The lesson candidate from 118.3 remains unpromoted.

---

## 120. The budget was never the constraint; the teacher just does not spend it (08-11)

119.5's first item was to price the budget: real seats reach level 8.26 *and*
0.271 1-cost 3-stars, so compute what that costs against what a seat earns.
`scripts/economy_budget.py` does it in arithmetic, and `--measure` reads the
engine's own ledger back as a check on the arithmetic.

Outcomes named before running, per the discipline: either (a) the budget is
short, and one of the community-documented constants is wrong; (b) the budget
fits and the engine's income matches it, making 119.4's frontier a policy
artefact; or (c) the engine's income disagrees with the arithmetic, in which
case the model is wrong and nothing downstream of it means anything.

It was (b), decisively.

### 120.1 The naive inflow counter reads 558g against a ceiling of 434g

The first measurement watched `player.gold` and credited every increase. It
reported 558g earned per game where the analytic ceiling — every round at
maximum interest, maximum streak *and* a win — is 434g. An engine paying 29%
above its own theoretical maximum would be a serious economy bug.

It is not a bug. `player.gold` also rises on unit sales, carousel gold and
per-round augment payouts, and `award_income` explicitly excludes augment
payouts so "the economy tables stay a faithful record of doc 01 sec 4's rules"
(`engine/player.py`). Instrumenting `PlayerState.award_income` instead — which
is also the only hook that distinguishes the agent's seat from the seven
opponents' — the hyperroll seat earns **193.9g** over 31.5 rounds against an
analytic base of 146g for 32 rounds. The income model is validated, so outcome
(c) is ruled out and the arithmetic below can be trusted.

### 120.2 The budget fits, with room

> **CORRECTED by entry 123.3.** The table below is arithmetic for a seat that
> buys **no units at all**. That seat holds 135g entering stage 5; a real one
> holds 19.5g, because it has been buying a board all game. The gold totals are
> right and the roll counts are not: 91 rolls was never available to a seat that
> also fields units. `P = 0.577` is an upper bound on a strategy nobody can
> play, not a reachable target.

`ledger()` walks the rounds rather than summing endpoint totals, because a
total lets the same gold be spent twice: interest is only earned on gold that
has *not* been rolled, so banking and rolling compete for the same coin. The
seat buys XP up the STANDARD curve without breaking a 50g bank, then from the
roll-down round stops levelling and rolls to zero.

P(3-star) is the Poisson tail on copies of one *named* champion, not
`copies / 9`. This matters by an order of magnitude and the first version of
the table got it wrong: 4.87 expected copies is 0.54 three-stars read linearly
and 0.03 read as a tail. Nine copies of one champion is the event.

| roll down at | end level | rolls | c1 copies | P(1-cost 3-star) |
|---|---|---|---|---|
| 2-1 | 6 | 89 | 18.32 | 0.994 |
| 3-1 | 6 | 102 | 19.70 | 0.997 |
| 3-5 | 7 | 104 | 15.73 | 0.975 |
| 4-1 | 7 | 111 | 16.48 | 0.983 |
| 4-3 | 7 | 104 | 11.56 | 0.814 |
| 4-5 | 7 | 109 | 11.90 | 0.839 |
| **5-1** | **8** | **91** | **9.25** | **0.577** |
| 5-5 | 8 | 101 | 9.79 | 0.643 |
| never | 9 | 0 | 4.34 | 0.033 |
| *real TFT* | *8.26* | — | — | *0.271* |

**A seat that levels the full standard curve and then rolls its surplus from
5-1 reaches level 8 at P = 0.577 — twice the real rate, at the real level.**
The real corner is not merely reachable, it is interior. 119.4 is withdrawn:
the monotone frontier it found is a property of capping the level, which was
the only lever it tried, not a property of the economy. No economy constant is
implicated and none should be touched.

### 120.3 Where the gold actually goes

The engine ledger, 40 games, agent seat, instrumented at the grant and at
`buy_xp`:

| | standard | hyperroll |
|---|---|---|
| income | 217.9 | 193.9 |
| — base / interest / streak / win | 140.6 / 51.0 / 17.0 / 9.2 | 138.6 / 29.9 / 16.0 / 9.4 |
| spent on rerolls | 19.1 (9.5 rolls) | 34.6 (17.3 rolls) |
| spent on XP | 127.0 | 114.6 |
| unspent at death | 22.4 | 39.2 |
| residual (units, net of sales) | 49.5 | 5.5 |
| end level | 8.40 | 8.35 |

Read the hyperroll column. It spends **3.3× more gold on XP than on rolling**,
dies with 39.2g in hand, and ends at level 8.35 — statistically the same level
as `standard`'s 8.40. It also collects 29.9g of interest against a ceiling of
about 157g, so it is not banking either.

**`HYPERROLL` is a hyperroll seat in name only.** Its `roll_floors` are
`{"2-3": 0, "3-2": 50}`, so the entire roll-down happens inside stage 2, where
income is 5-7g per round; from 3-2 the floor is 50 forever and the plan never
rolls again. 17 rolls where 91 are affordable at the same end level.

### 120.4 What this changes

The 3-star shortfall is an **allocation** failure, not an economy failure. That
relocates the whole of 115-119: those entries eliminated coverage, odds, pools,
gold, contention and targeting as causes, and the cause was that the plan
declines to spend gold it has.

It also explains why 119's `commit_level` arms bought 3-stars at the price of
placement. Capping the level frees gold to roll, but pays for it in board
slots, which 114 priced. The 5-1 row above needs no cap: it rolls the *surplus
that already exists* after the curve is paid for.

### 120.5 Still open

- **Test the 5-1 surplus roll-down in the engine.** The arithmetic says level 8
  and P = 0.577 together. Nothing has run it. This wants a roll floor that
  decays late rather than a level cap — the shape `roll_floors` already
  expresses, e.g. `{"2-3": 0, "3-2": 50, "5-1": 0}`. Predict before measuring:
  fidelity should improve; placement is genuinely unknown, because 114 priced
  slots and this arm does not give any up.
- The arithmetic assumes an uncontested pool. `copies_per_roll` takes a
  `contested` fraction that is not exercised above; uniform depletion cancels
  exactly, so only *targeted* contention moves the number.
- Cost-3 at 0.003 against 0.179 is still unexplained (116.2, 118.5), and 120.3
  now supplies a candidate that fits: check the spend ledger of a 3-cost seat
  before theorising further.
- The lesson candidate from 118.3 remains unpromoted.

---

## 121. Rolling the surplus is the right lever, but the floor is not the gate (08-12)

120.5's first item, run. `scripts/surplus_rolldown_ab.py`, 250 games per arm,
paired seeds, only the hyperroll seat's `roll_floors` changed. Baseline is
today's `{"2-3": 0, "3-2": 50}`.

| arm | c1 3★/hyper | c1/seat | rolls | end lvl | placement | t vs base |
|---|---|---|---|---|---|---|
| baseline | 0.176 | 0.022 | 17.5 | 8.16 | 5.228 | — |
| surplus 4-5 | 0.276 | 0.035 | 29.9 | 7.85 | 5.268 | +0.81 |
| **surplus 5-1** | **0.292** | 0.036 | 29.0 | 7.94 | **5.180** | −1.19 |
| surplus 5-5 | 0.212 | 0.026 | 21.6 | 8.14 | 5.212 | −0.82 |
| surplus 5-1 @20 | 0.236 | 0.029 | 21.7 | 8.07 | 5.156 | −2.00 |
| *real TFT* | — | *0.271* | — | *8.26* | *4.43* | — |

### 121.1 The direction transferred; the magnitude did not

`surplus 5-1` raises 1-cost 3-stars per hyper seat by **66%** (0.176 → 0.292)
while holding end level at 7.94 against 8.16, and placement does not degrade.

Set against entry 119, that is the whole point of the lever. 119's best-fidelity
arm reached 1.776 three-stars but at level 6.44 and placement 5.752 — it paid
0.524 placement. This arm gives up no board slots and pays nothing measurable.
**Rolling the surplus dominates capping the level**, which is what 120.2
predicted and 120.4 argued.

But 120.2's *numbers* did not transfer, and that was outcome A's actual claim:
29.0 rolls against a predicted 91, and 0.292 against a predicted P = 0.577. The
prediction failed on magnitude. Recording it as failed.

### 121.2 Why, measured rather than argued

Two assumptions in `ledger()`, both wrong in the same direction:

- **The bank is not there.** The model starts the roll-down holding the 50g
  floor. The seat actually holds **26.1g** at 5-1 (n=120, 101/120 hyper seats
  alive to reach it). A floor of 50 is a level the plan rarely attains, not a
  balance it sits on.
- **Rolling is not what the gold buys.** From 5-1 onward the seat spends, per
  game: **52.8g on units, 36.7g on rolls, 12.4g on XP.** The total (101.9g)
  matches what the income model says is available, so no gold is missing — but
  more than half of it goes to buying, not rolling.

The mechanism is in `_econ_plan`: the roll loop calls
`self._buy_phase(player, context, budget="all")` after *every single roll*, so
rolling competes with its own buying for the same gold. `MAX_ROLLS_PER_ROUND`
is 80 and never binds; the floor from 5-1 is 0 and still only ~1.7 rolls a
round happen.

**So the roll floor is not the binding gate, and 120.3's diagnosis was right
about the totals but incomplete about the mechanism.** Raising the tap does
help — 66% more 3-stars — but the buy phase drinks most of what comes out.

### 121.3 Not shipping this

Five arms, best t = −2.00, and that arm (`5-1 @20`) has *fewer* 3-stars than
`5-1` while placing better — which is what multiple comparisons look like under
the null. No arm's placement effect survives being one of five. The fidelity
gain is real and the placement claim is "not worse", not "better".

`HYPERROLL` keeps `{"2-3": 0, "3-2": 50}`. Changing a shipped default on a
t = −1.19 would repeat exactly the mistake the measurement discipline exists to
prevent.

### 121.4 Still open

- **The buy/roll competition is the next lever, and it is untested.** The
  question is whether `_buy_phase` inside the roll loop should run on a
  targets-only budget while a plan is rolling, rather than `budget="all"`.
  Predict first: this should raise rolls sharply; whether 3-stars follow depends
  on whether those 52.8g of buys are target copies (in which case they are the
  3-stars and nothing improves) or generic units (in which case they are the
  leak). **Measure which, before changing anything** — 118.3's unpromoted lesson
  applies exactly.
- Field average is 0.036 against a real 0.271. That is field composition — one
  hyperroll seat in eight — and 116.2 already showed a dedicated seat does not
  close it.
- Cost-3 at 0.003 against 0.179 is still unexplained (116.2, 118.5, 120.5).
- The lesson candidate from 118.3 remains unpromoted.

---

## 122. The non-target buys are board strength, not a leak (08-12)

121.4 named the next lever and the order to test it in: measure whether the
52.8g a rolling seat spends on units is target copies or generic units, *then*
decide. Both done.

### 122.1 The split, measured first

Hyperroll seats rolling from 5-1, 120 games, gold spent on units from 5-1
onward, split by whether the champion bought is in `reroll_targets` at that
moment:

| | gold | units |
|---|---|---|
| target copies | 2.8 | 2.8 |
| everything else | 50.0 | 18.0 |

and the non-targets by champion cost: c1 2.9g, c2 8.6g, **c3 15.4g, c4 20.4g**,
c5 2.6g. So 94.7% of the gold goes to champions the plan is not collecting, and
the bulk of it to the expensive ones.

That is the leak reading, and it is what I expected to confirm.

### 122.2 It is not a leak. Prediction failed

`GreedyPolicy(roll_buys="targets")` narrows the buy phase *inside the roll loop*
to the reroll line. 250 games per arm, paired seeds:

| arm | c1 3★/hyper | rolls | end lvl | placement | t vs base |
|---|---|---|---|---|---|
| baseline | 0.176 | 17.5 | 8.16 | 5.228 | — |
| surplus 5-1 | 0.292 | 29.0 | 7.94 | 5.180 | −1.19 |
| targets-only buys | 0.228 | 18.8 | 8.10 | 5.388 | +1.49 |
| **surplus 5-1 + targets** | **0.316** | 29.6 | 7.90 | **5.484** | **+2.45** |

Outcome **E**, not the predicted D. Blocking those buys produces the best
fidelity in the whole arc — 0.316 1-cost 3-stars per hyper seat, 1.8× baseline —
and costs **0.256 placement at t = +2.45**. The 18 units a game were board
strength, which is entry 114's slot price arriving by a new route.

A second prediction failed with it, and it is the more informative one.
121.2 argued the roll loop "outbids itself", so removing the competing buys
should raise rolls sharply. **Rolls went 29.0 → 29.6.** Freed gold did not
become rolls. The competition story explains where the gold goes but not what
limits rolling, and the 3-star gain here comes from copies concentrating on the
line rather than from more searching.

### 122.3 What is now closed

Every lever tried against the 1-cost 3-star shortfall — 119's level cap, 121's
surplus floor, 122's targets-only buys — lands on the same trade: material
fidelity gains cost placement, and the arms that leave placement alone move
fidelity little. `surplus 5-1` remains the exception at −1.19, which is not a
result. **119.4's frontier was wrong about the cause (120.2) and right about the
shape.**

Nothing ships. `HYPERROLL` keeps `{"2-3": 0, "3-2": 50}` and `roll_buys`
defaults to `"all"`, so every pre-121 number reproduces.

### 122.4 A mutation that survived, and what it was telling me

`tests/test_roll_buys.py` passed all four cases against a mutation that flips
`_buy_phase`'s `targets_only` default to True — which silently filters the
*board-building* buy phases, leaving a seat unable to build a board. It survived
because the roll loop passes the argument explicitly and so is unaffected, and
the test counted every buy in one bucket, where the roll loop's volume drowned
the regression.

The fix was not another case. It was **splitting the measurement**: `_econ_plan`
runs buy, level, buy, then the roll loop, so a buy before that round's first
reroll is board-building and one after it is the roll loop. Counting the two
separately kills both mutations, on the two different assertions they should
hit.

Lesson candidate, unpromoted: **when a mutation survives, suspect the
measurement aggregates two mechanisms before adding another case.** Adding
cases to a metric that cannot see the defect is how a test file grows while its
coverage does not.

### 122.5 Still open

- The rolling constraint is *not* the floor (121.2) and *not* the competing buys
  (122.2). Both were measured and both were wrong. What limits a seat to ~29
  rolls when the arithmetic says ~91 is unexplained, and the next thing worth
  measuring is the per-round roll count against per-round gold — the totals have
  now been misleading twice.
- Cost-3 at 0.003 against 0.179 is still unexplained (116.2, 118.5, 120.5).
- Two unpromoted lesson candidates: 118.3's and 122.4's.

---

## 123. The rows: income collapses the moment the seat rolls to zero (08-12)

122.5 asked for the per-round view, on the grounds that the totals had misled
twice. They had. One run settles what three entries theorised about.

### 123.1 The table

120 games, hyperroll seats on the `surplus 5-1` floors, means over seat-rounds.
"gold in" is gold entering the planning phase; "gold at 1st roll" is gold when
that round's first reroll happens; "never rolled" is the share of seat-rounds
with no reroll at all.

| round | n | gold in | gold at 1st roll | rolls | gold out | never rolled |
|---|---|---|---|---|---|---|
| 4-1 | 120 | 43.8 | — | 0.00 | 16.0 | 100% |
| 4-4 | 119 | 40.9 | 61.9 | 1.80 | 35.9 | 68% |
| 4-5 | 119 | 49.1 | — | 0.00 | 4.6 | 100% |
| 4-7 | 101 | 19.5 | — | 0.00 | 13.5 | 100% |
| **5-1** | 101 | **26.1** | 26.0 | **8.83** | 0.5 | 20% |
| 5-2 | 88 | **9.3** | 6.0 | 2.93 | 0.4 | 22% |
| 5-3 | 74 | 9.1 | 6.4 | 2.96 | 0.4 | 23% |
| 5-5 | 61 | 8.6 | 2.5 | 1.21 | 0.5 | 49% |
| 6-1 | 41 | 9.4 | 2.8 | 1.37 | 0.5 | 49% |
| 6-5 | 20 | 8.7 | 4.4 | 1.80 | 0.5 | 40% |

### 123.2 What it says

**The seat rolls to zero at 5-1 and never has money again.** It enters 5-1 with
26.1g, rolls it away, and enters every subsequent round with **~9 gold** — 5
base plus streak and win bonus, and *no interest*, because interest is computed
on gold held and it holds none. Gold out is 0.5 in every row from 5-1 on: the
seat is not saving, it is broke.

Nine gold a round is 4.5 rolls a round at `reroll_cost` 2, against a further ~7
rounds of life. That is the ~29 rolls observed, and it is a **hard ceiling** set
by the interest rule, not by the roll floor (121.2) and not by the competing buy
phase (122.2). Both earlier answers were wrong; this one is arithmetic on the
rows.

Note also 4-1 through 4-7: **zero rolls in seven consecutive rounds**, holding
20–49 gold, because the floor there is 50 and gold never reaches it. And 4-5
turns 49.1g into 4.6g with no rolls at all — that is the level-8 XP purchase on
the standard curve. The stage-4 window is not a rolling window in any arm.

### 123.3 The 91 was never available

120.2 predicted 91 rolls from 5-1 and the engine delivers 29. The model is
wrong, and specifically: **`ledger()` buys no units.** It banks, buys XP, and
rolls; nothing else. Such a seat holds **135g** entering stage 5. The engine's
seat holds **19.5g**, because it has been buying a board all game.

So `P = 0.577` describes a strategy that fields no units and loses every fight.
The gold totals in 120.1–120.2 are right — the engine's income matches the
model — and the roll counts derived from them are an upper bound on a game
nobody can play. 120.2 is corrected rather than withdrawn: the budget does
permit level 8 alongside rolling; it does not permit level 8, rolling, *and* a
board, which is the actual constraint and the one entry 114 priced.

**Three entries theorised about a total; the rows answered it in one run.** That
is lesson 27, now promoted from the 118.3 candidate, with 122.4's mutation
corollary attached.

### 123.4 What this closes, and what it opens

The 1-cost 3-star shortfall is now explained end to end. A seat cannot roll more
than ~29 times in this economy while also fielding a board, because rolling to
zero destroys the interest that is most of its income. Every lever tried moves
the seat along that constraint rather than off it: 119's level cap, 121's floor,
122's targets-only buys. **The frontier 119.4 drew is real; 120.2's claim that
it was an artefact was itself the artefact.**

What this does *not* explain is real TFT, where seats reach 0.271 1-cost
3-stars at level 8.26. Under this engine's interest rule that combination
requires roughly triple the rolls the income permits. The open question is
therefore back on the constants after all, and it is a specific one:
`interest_per_gold` = 10 with `interest_cap` = 5 means a rolling seat forfeits
5g/round, a third of its income. That table is `community_documented` and has
never been checked against a real match ledger.

### 123.5 Still open

- **Check `interest_per_gold` and `interest_cap` against real match gold.**
  `data/reference/` has the match sample; a per-round gold trace from real seats
  would settle whether real players also drop to ~9g/round after a roll-down. If
  they do not, the interest table is where this arc ends.
- Cost-3 at 0.003 against 0.179 is still unexplained (116.2, 118.5, 120.5).
- Nothing shipped in 119–123. `HYPERROLL` keeps `{"2-3": 0, "3-2": 50}`,
  `commit_level` and `roll_buys` stay at their inert defaults.

---

## 124. The real corner is real: hitters sit at level 8.34 and place 4.42 (08-12)

123.5 asked for a real per-round gold trace to check `interest_per_gold`.
**That check cannot be run:** Riot's match payload carries `gold_left` — gold at
elimination — and nothing else per seat. There is no per-round series in
`data/reference/`, and no other field stands in for one. Recording that as
closed-by-impossibility rather than leaving it on the worklist.

So this asks the question the data *can* answer, and it is one that should have
been asked at the top of the arc. Entries 119-123 chased "0.271 1-cost 3-stars
at level 8.26, placing 4.43". **Both numbers are field averages over every
seat**, and I treated them throughout as a joint property of one seat. Lesson 27
applies to the reference side exactly as it does to the engine side: if the
3-stars come from level-7 seats and the 8.26 from seats with none, there is no
corner and the engine's frontier was never anomalous.

### 124.1 The split

`scripts/reroll_seat_profile.py`, grouping every seat by what it actually holds.
8000 seats per band.

**Challenger:**

| group | seats | share | level | placement | gold left | last round |
|---|---|---|---|---|---|---|
| all | 8000 | 100% | 8.60 | 4.50 | 8.5 | 31.1 |
| **holds a 1-cost 3★** | 1311 | **16.4%** | **8.34** | **4.42** | 8.6 | 31.5 |
| no 1-cost 3★ | 6689 | 83.6% | 8.65 | 4.51 | 8.4 | 31.0 |
| holds a 3-cost 3★ | 810 | 10.1% | 7.99 | **4.01** | 8.8 | 32.2 |
| no 3★ at all | 5237 | 65.5% | 8.76 | 4.66 | 8.4 | 30.7 |

Diamond is the same shape: hitters at level 8.19, placing 4.43; 3-cost hitters
at 7.91, placing 3.99.

Level distribution of challenger seats holding a 1-cost 3★: **82.7% are level 8
or above** (8: 37.1%, 9: 36.8%, 10: 8.8%). Only 17.3% sit below.

### 124.2 Outcome B. The hypothesis I was testing is refuted

There is no averaging artefact. A real seat that 3-stars a 1-cost is **0.31
levels** below one that does not, and places slightly *better*. The corner is a
property of individual seats, not of a mean over dissimilar ones.

For contrast, the engine's arms that hit at any rate sat 1-2 levels below their
field: 119's best-fidelity arm at 6.44, 121-122's at 7.90. **Real players give
up a third of a level; this engine gives up one to two.** 123.4's conclusion
stands and is now measured on the reference side rather than inferred.

### 124.3 The finding I was not looking for

**3-cost reroll is the best-placing group in real TFT** — 4.01 challenger, 3.99
diamond, against a field mean of 4.50 — and 10.1% of challenger seats play it.
The engine produces **0.003** (116.2, 118.5). That is the largest single
fidelity gap left, it sits on the archetype real players place best with, and
every previous attempt to explain it assumed it was a smaller version of the
1-cost problem. 124.1 says it is not: 3-cost hitters end *lower* than 1-cost
hitters (7.99 vs 8.34) and place *better*, which is a different shape entirely.

Also worth recording against 97.4: real seats hold **8.5 gold** at elimination,
and hitters hold 8.6 — no different. The engine's rolling seat ends every round
from 5-1 on with 0.5 (123.1). Real players hit *without* being broke, which is
the same structural statement from a third direction.

### 124.4 Still open

- The economy constants remain unverified and now unverifiable from this
  sample. If the arc continues on economy, it needs a data source with a
  per-round ledger; none is known.
- **Cost-3 reroll is the highest-value open question in the project**, on these
  numbers: best real placement, 10.1% incidence, ~0 engine production, and a
  profile that 124.1 shows is *not* the 1-cost story rescaled.
- Nothing shipped in 119-124.

---

## 125. The real 3-cost archetype is nothing like `SLOWROLL7` (08-12)

124.3 made 3-cost reroll the highest-value open question. Before guessing
another parameter at it -- 116.2 already guessed once and made the profile worse
-- describe it from the sample. Lesson 27 applied *before* the fact.
`scripts/cost3_archetype.py`, 810 challenger seats holding a 3-cost 3-star.

### 125.1 How many, and at what level

| 3-cost 3★ held | seats | share | level | placement |
|---|---|---|---|---|
| **1** | 480 | **59.3%** | 7.98 | 4.38 |
| 2 | 250 | 30.9% | 8.07 | **3.47** |
| 3 | 62 | 7.7% | 7.79 | 3.52 |
| 4 | 13 | 1.6% | 7.92 | 3.85 |
| 5 | 5 | 0.6% | 7.60 | 2.20 |

Level distribution of hitters: 6 → 0.9%, **7 → 35.2%, 8 → 36.4%**, 9 → 19.1%,
10 → 8.4%.

Two assumptions in `SLOWROLL7` are contradicted outright:

- **`target_count=3` is wrong.** The modal hitting seat holds **one**. Three or
  more is 9.9% of them. More is better where it happens — placement improves
  from 4.38 at one to 3.47 at two — but a plan that only counts itself finished
  at three is describing the top decile, not the archetype.
- **Holding level 7 is wrong.** 64% of hitters are at level 8 or above. This is
  not a seat that parks at 7; it is a seat that hits *and* levels, which is the
  same shape 124.2 found for 1-costs.

### 125.2 The board is not a 3-cost board

Mean units per hitting seat, by cost and star:

| cost | 1★ | 2★ | 3★ |
|---|---|---|---|
| 1 | 0.14 | 0.79 | 0.23 |
| 2 | 0.10 | 0.94 | **0.73** |
| 3 | 0.14 | 1.13 | **1.53** |
| 4 | **0.54** | **0.83** | 0.01 |
| 5 | 0.52 | 0.37 | 0.00 |

Board size 7.99 units. So a real 3-cost reroll seat fields ~2.7 cost-3 units,
**~1.4 cost-4 and ~0.9 cost-5 units**, and carries 0.73 cost-2 3-stars besides.
It is a rerolled *core* with expensive additions on top, and it 3-stars across
tiers rather than within one.

`SLOWROLL7` encodes the opposite: three cost-3 carries, level held at 7, and
`reroll_targets` steering every purchase to one tier. That is a caricature of
the archetype, and it explains 116.2's result — the dedicated seat reached 27%
of the real rate and made the *profile* worse — without needing the field-
coverage story that 115.3 offered and 116.2 withdrew.

Note also 122.2 in this light: blocking non-target buys cost 0.256 placement.
Real reroll seats buy off-plan constantly — a third of their board is 4- and
5-cost. The two findings agree.

### 125.3 Thirteen champions, not one

13 distinct cost-3s were 3-starred; the most common (`TFT17_Ornn`) appears in
28.3% of hitting seats, then Viktor/Lulu 17.4%, Miss Fortune 16.9%, Samira and
Illaoi 15.8%. The line is not one champion the field converges on, which is
consistent with the pool arithmetic: 18 copies per 3-cost against 30 per 1-cost
means a contested 3-cost line cannot support many seats at once.

### 125.4 What to test, and what not to conclude

The obvious move is to set `target_count=1` and let the level curve run to 8.
That is a *hypothesis*, not a finding, and it is exactly the shape of change
119.3 got wrong by reasoning ahead of the numbers. Outcomes named before the
run:

* **A** — incidence rises toward 10.1% and placement holds or improves. The
  archetype was mis-specified and 116.2's failure was the specification.
* **B** — incidence rises and placement worsens, as 122.2's arm did. Then this
  is the same fidelity/placement trade under a third name.
* **C** — incidence stays near 0.003. Then the specification was never the
  binding problem and 118.5's observation stands: level 7 is where 3-costs are
  cheapest (58.5 rolls) and the seat still cannot afford them, which points back
  at 123.2's income ceiling.

**C is the outcome the rest of this arc predicts**, and it should be said before
the run rather than after: 123.2 established that a seat rolling to zero earns
~9g/round, and a 3-cost 3-star needs 58.5 rolls of a *named* champion at level
7. Nothing in 125.1-125.3 changes that arithmetic. What the rows change is the
*target*: one 3-star, not three.

### 125.5 Still open

- The A/B above, unrun.
- Economy constants unverified and unverifiable from this sample (124.4).
- Nothing shipped in 119-125.

---

## 126. Levelling to 8 is worth 0.96 placement, and costs two thirds of the hits (08-12)

125.4's A/B, 250 games, seat 0 running the 3-cost line against `DEFAULT_FIELD`.

| arm | c3 3★/seat | hit rate | rolls | end lvl | placement | t vs base |
|---|---|---|---|---|---|---|
| `slowroll7` (shipped) | 0.396 | **30.8%** | 37.7 | 7.64 | 5.368 | — |
| count=1 | 0.300 | 30.0% | 39.8 | 7.73 | 5.180 | −2.21 |
| count=2 | 0.408 | 35.2% | 38.7 | 7.68 | 5.272 | −1.47 |
| count=1, level to 8 | 0.052 | 5.2% | 20.8 | 8.58 | **4.408** | **−9.52** |
| **count=2, level to 8** | 0.112 | 10.0% | 21.7 | 8.59 | **4.408** | **−9.70** |
| *real TFT* | — | *10.1%* | — | *7.99* | *4.01* | — |

**Outcome A on placement, and its opposite on fidelity.** None of the three
named outcomes covers this.

### 126.1 The level curve dominates; `target_count` barely registers

Levelling to 8 instead of parking at 7 is worth **0.96 placement** (5.368 →
4.408, t = −9.70) — the largest effect in this entire arc, and in the direction
124 and 125 pointed. `target_count` moves placement by 0.1-0.2 at |t| ≤ 2.21
across five arms, which is not a result. The parameter I expected to matter is
the one that does not.

That also closes 125.4's prediction: **C was wrong.** I argued from 123.2's
income ceiling that nothing would move, and something moved a great deal. The
ceiling is real but it constrains *hits*, not placement, and I conflated them.

### 126.2 The 10.0% is not a match, and nearly became one

`count=2, level to 8` hits 10.0% against real TFT's 10.1%, and that number is a
**coincidence of denominators**, not agreement. Real 10.1% is the share of *all*
seats holding a 3-cost 3-star. The engine 10.0% is the hit rate of **one
dedicated seat** out of eight. Converted to the same basis the engine field
produces 10.0% ÷ 8 = **1.25%** against 10.1% — still 8× short.

Turned around, the arithmetic is unflattering: if the real archetype is played
by roughly one seat per lobby, a real dedicated 3-cost seat must hit **~80%** of
the time to produce 10.1% across all seats. At two seats per lobby it is ~40%.
The best-placing engine arm hits 10%.

Writing that down because the row was one sentence away from entering the log as
"engine matches real incidence", which is exactly how a 90.7% ceiling became a
fact twice before.

### 126.3 The tension worth keeping

The specification that plays *well* (level to 8, placing 4.408) produces **a
third** of the 3-stars of the one that plays badly (parked at 7, placing 5.368).
Fidelity and placement point opposite ways again, and for the fourth time in
this arc — 119's cap, 121's floor, 122's targets-only buys, and now the level
curve.

But the sign has flipped relative to all three. Previously more fidelity cost
placement; here more placement costs fidelity, and the *real* seats sit at the
high-placement end (4.01) **while also hitting**. Real TFT is at a corner this
engine still has no arm anywhere near, which is 124.2's conclusion arriving from
the 3-cost side.

### 126.4 What this does and does not license

`SLOWROLL7` remains out of `DEFAULT_FIELD` and unchanged. Adding it would shift
every baseline in the project — the ninth such invalidation — and the case for
it is a fidelity case, while the arm that would justify it on placement is the
one that produces fewest 3-stars.

What is now well-supported is narrower and worth stating on its own: **for a
3-cost reroll plan in this engine, parking at level 7 is simply bad, worth
almost a full placement.** If `SLOWROLL7` is ever fielded, it should level to 8.
That is a conditional decision recorded now so it is not re-litigated.

### 126.5 Still open

- The dedicated-seat hit rate a real 3-cost player achieves is **unmeasurable
  from this sample** — hits are observable, attempts are not. Without it, engine
  hit rates cannot be compared to reality on the right denominator at all, and
  126.2's ~80% is an inference from an assumed archetype frequency, not a
  measurement.
- Economy constants unverified and unverifiable from this sample (124.4).
- Nothing shipped in 119-126.

---

## 127. The one fidelity match this project has is produced by bad play (08-12)

126.1 found a 3-cost reroll plan parked at level 7 places 0.96 worse than one
that levels to 8, on an archetype that is not shipped. `SLOWROLL6` **is**
shipped, holds two of eight seats in `DEFAULT_FIELD`, and parks harder: level 6
at 3-2, and no level 7 until **5-1**. `HYPERROLL` already runs the standard
curve and is not a candidate, so `slowroll6` is the only shipped plan 126 could
apply to.

`scripts/slowroll6_level_ab.py`, 250 games, only the `slowroll6` seats change.

| arm | c2 3★/seat | hit rate | rolls | end lvl | placement | t |
|---|---|---|---|---|---|---|
| `slowroll6` (shipped) | 1.376 | 78.0% | 47.3 | 7.51 | 4.898 | — |
| 7 at 4-1 only | 0.908 | 55.8% | 43.0 | 7.84 | 4.604 | −4.43 |
| **standard curve** | 0.312 | 23.6% | 22.8 | 8.58 | **4.124** | **−10.80** |

**Outcome A.** Parking generalises as a defect: **0.774 placement** for the
shipped archetype at t = −10.80, and monotone in how much the plan levels. The
intermediate arm separates the two effects — getting off level 6 is worth 0.294,
reaching 8 early is worth the other 0.480.

### 127.1 And it destroys the fidelity match, measured on the right basis

118.4's cost-2 figures are field-wide per seat, not per `slowroll6` seat, so the
two are not comparable as they stand. Re-derived on 118.4's basis, 150 games:

| | c2 3★/seat, field-wide | seats holding one |
|---|---|---|
| shipped | **0.339** | 19.7% |
| standard curve | **0.069** | 5.5% |
| real TFT | *0.326* | — |

The shipped arm reproduces 118.4's 0.344 within noise, which validates the
comparison. Levelling drops field-wide cost-2 production to **0.069 against a
real 0.326** — a 4.7× shortfall where there was a match.

Two things worth recording about getting here. The per-seat figure (1.376) times
the seat share looked irreconcilable with 0.339 until I checked the seat count:
I had written "three of eight seats" from memory and `DEFAULT_FIELD` has
**two**. 1.376 × 2/8 = 0.344. The discrepancy was my arithmetic, not the
engine's — and it was only visible because the two measurements were put on one
basis rather than compared as quoted.

### 127.2 The finding, which is larger than the archetype

**This project's only tier-level fidelity match is a product of bad play.**
`slowroll6` matches real cost-2 3-star rates because it parks at level 6 and
rerolls 47 times a game, and that costs it 0.774 placement.

Stated across all three tiers now measured:

| tier | fidelity comes from | placement cost |
|---|---|---|
| 1-cost (119, 121, 122) | capping level / blocking buys | 0.26-0.52 |
| 2-cost (127) | parking at level 6 | 0.774 |
| 3-cost (126) | parking at level 7 | 0.96 |

Every arm that produces 3-stars at a real rate plays worse than one that does
not, on every tier, and the effect grows with cost tier. Real seats sit at the
*good* end while hitting (124.1: 1-cost hitters at level 8.34 placing 4.42;
3-cost hitters placing 4.01). **124.2's conclusion is now confirmed on all three
tiers independently: the engine has no arm near the real corner, and this is not
a strategy-parameter problem.**

### 127.3 Not changing it

`SLOWROLL6` keeps its curve. Changing it would invalidate every baseline in the
project — the ninth such invalidation — *and* trade the only fidelity match for
placement on two of eight opponent seats. Neither half of that is worth doing on
its own and together they are clearly not.

Recorded as a standing fact instead: **the scripted field is ~0.77 placement
weaker on its `slowroll6` seats than a levelling variant would be.** That is a
handicap on two opponents, not on the teacher (which runs `standard`), so it
does not bias the clone's training signal in the way it would if the teacher
itself parked.

### 127.4 Still open

- The engine cannot hit and play well simultaneously on any tier. Every
  remaining explanation is structural: 123.2's income ceiling, or a mechanic the
  engine lacks. No strategy parameter has closed it in nine entries.
- Real dedicated-seat hit rates unmeasurable from the sample (126.5); economy
  constants unverifiable from it (124.4).
- Nothing shipped in 119-127.

---

## 128. Closing the fidelity arc (08-12)

Entries **111-127: seventeen entries, zero behaviour changes shipped.** Closing
it deliberately rather than drifting out of it, and recording why, so the next
person does not reopen it by reflex.

### 128.1 What it was for and what it returned

The arc asked whether this engine reproduces real TFT's 3-star economy, on the
premise that a simulator that does not cannot train an agent that transfers. It
answered that question, negatively and thoroughly:

- Real 1-cost hitters sit at level 8.34 placing 4.42; 3-cost hitters place 4.01
  (124.1). Real seats hit **and** play well.
- This engine cannot do both on **any** tier. Fidelity costs 0.26-0.52
  placement at cost 1, 0.774 at cost 2, 0.96 at cost 3 (127.2).
- The cause is not the roll floor (121.2), not the competing buy phase (122.2),
  not targeting, coverage, odds, pools or contention (116-118), and not the
  strategy specification (126.1). It is that a seat rolling to zero earns ~9
  gold a round, because interest is computed on gold it no longer holds
  (123.2).
- The economy constants that would explain it are `community_documented` and
  **unverifiable from the match sample**, which carries `gold_left` and no
  per-round ledger (124.4). Real dedicated-seat hit rates are likewise
  unmeasurable — hits are observable, attempts are not (126.5).

So the arc ends on a structural negative with no remaining measurable
hypothesis. That is a legitimate result and it is also a stopping condition.

### 128.2 Why nothing shipped, restated in one place

Each candidate was declined for a stated reason, not left undecided:

| change | measured | why not shipped |
|---|---|---|
| `desperation_hp`, `keep_pairs` | 99, 104 | inert defaults, opt-in |
| `commit_level` | 119 | −0.524 placement for fidelity on one metric |
| surplus roll floors | 121 | best arm t = −1.19, one of five |
| `roll_buys="targets"` | 122 | +0.256 placement cost, t = +2.45 |
| `SLOWROLL7` re-spec | 126 | archetype not fielded; fidelity and placement pick different arms |
| `SLOWROLL6` levelling | 127 | +0.774 placement but destroys the only fidelity match, and invalidates every baseline |

The one unambiguous finding — **parking at a low level costs 0.774-0.96
placement** — applies only to reroll archetypes, and the teacher runs
`standard`, which does not park. It therefore does not reach the agent.

### 128.3 The state of the actual goal

All nine milestones in doc 03 sec 4 are built. The agent is at **parity with its
scripted teacher** (4.567 vs 4.620, n=300) and no RL configuration has passed
it. That is the project's real open problem and the fidelity arc was never going
to move it: imitation is bounded by the teacher, and seventeen entries of
simulator validation do not raise a teacher.

**Two directions remain, and they are genuinely different work:**

1. **Beat the teacher.** The core unsolved problem. Economy improvements
   transmit to the clone at 89% (entry 75); positional and search improvements
   do not (79, 106-110), and the search-transmission programme is closed
   (lesson 26). Scripted-economy tuning is now also exhausted (88, 126, 127).
   What has never been tried is a teacher that is not a scripted policy.
2. **Build the bridge to real TFT.** The stated end goal, and entirely unbuilt:
   nothing in the repo reads a real game or emits real inputs. It would surface
   a different class of problem — observation extraction, latency, action
   legality against a live client — none of which any simulator work addresses.

Recording both rather than picking one, because the choice is a project
direction rather than a measurement, and this log is not the place to make it
silently.

### 128.4 Do not reopen without

- a data source with a **per-round gold ledger**, which would make 123.2's
  income ceiling testable against reality; or
- evidence that a specific **mechanic is missing** from the engine, rather than
  a constant being wrong — the constants have been eliminated as far as this
  sample allows.

Absent either, more strategy-parameter A/Bs will keep landing on the same
frontier, which nine entries have now traced from three independent directions.

---

## 129. Shortening the causal chain changes nothing: the reward is not the problem (08-12)

First entry of the RL-directed work that follows 128.3. Entry 91 found that a
single action does not measurably move **final placement** (1098 deviations,
largest |t| = 1.82) and concluded that PPO's advantages fit noise. The obvious
reading -- and the one most RL debugging instinct reaches for -- is that the
reward is too sparse: ~400 actions credited against one terminal number twenty
rounds away.

`scripts/round_credit.py` tests that directly. Same counterfactual as 91, same
replay-from-seed, same "draw an alternative from the policy's own support"; only
the **outcome variable** moves, from final placement to the HP lost in the *very
next fight*. Causal chain: twenty rounds → one.

1072 deviations at `bc-econ-s0`:

| kind | n | hp cost | t |
|---|---|---|---|
| END_PLANNING | 68 | +0.250 | 0.58 |
| SELL | 323 | +0.245 | **1.82** |
| BUY_XP | 74 | +0.122 | 0.44 |
| SELECT | 99 | +0.071 | 0.36 |
| BUY | 311 | +0.029 | 0.19 |
| PLACE | 133 | −0.113 | −0.84 |
| REROLL | 21 | −0.429 | −0.40 |
| EQUIP | 26 | −0.731 | −1.19 |
| **ALL** | **1072** | **+0.073** | **0.95** |

### 129.1 Outcome B, and C did not appear

Largest per-kind |t| is **1.82** — the same figure entry 91 got against final
placement, from a chain twenty times longer. Overall mean 0.073 HP at t = 0.95,
against fights that typically cost 2-11 HP.

The predicted outcome was **C**: board actions (BUY, SELECT, PLACE) should move
the next fight because they change the board that fights it, while economy
actions pay off rounds later. **It did not appear.** BUY sits at t = 0.19,
SELECT 0.36, PLACE −0.84 — indistinguishable from `BUY_XP` and `END_PLANNING`.
Naming C in advance is what makes that readable as a result rather than as a
disappointing table.

### 129.2 What this eliminates

**Reward sparsity is not the cause, and no denser reward fixes this.** Per-round
combat outcome is the densest well-founded signal this domain offers — it is
observable, immediate, and directly caused by the board that fights — and a
single action does not move it either. Anything less immediate is strictly
worse.

That retires the whole reward-engineering class: per-round rewards, potential
shaping (92-93 already refuted its credit distribution), reward scaling,
discount tuning. None of them address what is actually wrong.

### 129.3 What is actually wrong, restated

91.2 had it and its importance was under-read: substituting the **teacher's**
action cost −0.194 at t = −2.28 (entry 82), while substituting an action from
**the clone's own distribution** measures nothing. The problem is not the signal
that follows the action; it is that the actions being compared are
near-equivalent. The clone's top-two choices are interchangeable, so no outcome
variable — however immediate — can separate them.

**RL from a reward signal requires that the policy's own alternatives differ in
value. Here they do not, at this action granularity.** That is a property of the
action space, not of the reward, the critic, the entropy schedule, or the data
volume (96 already refuted 33× the data).

### 129.4 The one lever this leaves, and why it is plausible

If actions are individually null but collectively decisive, the fix is to make
each decision bigger: **one decision per round rather than ~400 per episode.**
The action space is currently micro (`BUY slot`, `SELECT`, `PLACE hex`), and
`rl/search.py` already operates at the coarser granularity — `best_board`
chooses a whole board for a round.

There is direct evidence that granularity carries signal where the micro one
does not: entry 106 measured search worth **0.527 placement** to the teacher.
Round-level board choices move outcomes measurably; the micro-actions composing
them do not.

The caution against it is equally direct, and has to be stated before any work
starts: entries 106-110 measured that search-derived improvements **do not
transmit to the clone**, and lesson 26 explains why — a teacher whose rule is a
*simulation* cannot be cloned from scoutable features. Temporal abstraction for
*RL* is a different claim from cloning a search teacher, but it inherits the
risk that the coarse action's value is only computable by simulating it.

### 129.5 Still open

- Whether a coarse (per-round) action space makes the counterfactual signal
  measurable. **That is the same probe run against a coarse policy**, and it is
  the cheapest possible test of the idea before any training run — measure the
  signal first, exactly as 129 did, rather than training and reading the curve.
- Nothing shipped.

---

## 130. Not granularity either: the value of a decision is genuinely diffuse (08-18)

129.5 asked for the cheapest test of 129.4's one remaining lever -- coarsen the
action space -- before building anything. `scripts/round_decision_credit.py`
runs 129's counterfactual with the **decision** coarsened instead of the
outcome: suppress one round's whole-board decision from
`search_policy(mode="board")`, fall back to the base policy's board (a
legitimate policy output, not a random one), and measure the HP lost in that
round's fight. Both branches replay from one seed; placement actions draw
nothing from the match RNG, so the combat seed is identical and the pairing is
exact.

80 episodes, **1151 round-level deviations**; the search changed the board in
44.9% of rounds.

| quantity | n | hp cost | t |
|---|---|---|---|
| one round's board decision | 1151 | +0.050 | **0.74** |
| rounds 0-11 | 388 | +0.082 | 1.37 |
| rounds 12+ | 763 | +0.033 | 0.34 |

**Outcome B.** Coarsening the decision by roughly thirty times changes nothing:
t = 0.74, against t = 0.95 for a single micro-action (129) and max |t| = 1.82
for a micro-action against final placement (91). Three probes, three
granularities, three nulls.

### 130.1 The tension that resolves it

> **CORRECTED, same day.** This section first quoted entry 106's **0.527**
> placement for the search. 108.2 says in terms that the n=150 figure "should
> not be quoted": it replicated at **−0.243 (t = −2.00) at n=300**, less than
> half, with the no-search baselines differing too. I cited the withdrawn
> number from the index line rather than re-deriving it — the exact failure
> lesson "re-derive before citing" names, on an entry already carrying a ⚠️.
> Figures below use 0.243. The correction **strengthens** the conclusion, which
> is why it was worth catching rather than quietly keeping.

The search is worth **0.243 placement (t = −2.00, n=300)** over a whole game
(108.2). That is modest and barely significant, but it is not zero. So the
search has some real value and no single application of it is detectable.

The arithmetic reconciles them. The search fires 14.4 times a game, so 0.243
placement is **0.017 placement per application** -- a genuinely tiny
per-decision effect. On the HP measure, the per-decision standard deviation is
**2.29 HP** against a mean effect of 0.050, so the effect is **~46× smaller
than its own standard deviation**, the 95% CI is [−0.082, +0.182], and detecting
the mean at t = 2 would need **~8,400 deviations** — 584 episodes of this probe,
about seven hours.

(A second correction: this section first characterised the effect as swamped by
variance "roughly 2,000× its size". That conflated the required *sample count*
with a variance ratio. The ratio of standard deviation to effect is **46×**;
the ~8,400 figure is what that ratio implies for n, being roughly
`(2 · sd / mean)²`.)

**The value of a decision here is real, tiny, and 46× smaller than the noise on
a single measurement of it.** That is the whole account, and it is not a defect
of the reward, the critic, the horizon, the entropy schedule, the data volume
(96), or the action granularity (130).

### 130.2 What this closes

PPO's advantage estimate is `Q(s,a) − V(s)` from sampled returns. If separating
one decision from its alternative needs ~8,400 samples of *that decision in that
kind of state*, and a training run sees a few hundred thousand transitions
spread across an enormous state space, the estimator cannot resolve the signal.
**It fits noise because the signal is below its resolution, and no
reward-side or action-side reshaping raises it.** 89-96 each refuted a proposed
mechanism; this is why every one of them was refuted.

It also explains cleanly why imitation works here and RL does not: **cloning
never needs per-decision credit.** It copies a policy whose *aggregate* is good,
which is exactly the quantity that is measurable in this domain.

### 130.3 The one method whose requirements match

Optimising aggregate return without per-decision credit is what
evolutionary/population methods do, and entry 94 already priced it here: a flat
fitness landscape then a cliff, **viable only at 3-6 days of compute**. That
figure was measured before this entry existed and should be re-derived before
acting on it (lesson: re-derive before citing), but the *shape* now has an
explanation it lacked in 94 -- ES is insensitive to exactly the quantity this
domain hides.

So the honest position on 128.3's direction 1: **PPO-shaped RL is closed by
measurement, not by lack of effort.** What remains is either ES at a known and
large compute price, or raising the teacher by non-learned means, which is
direction 2's territory.

### 130.4 Still open

- Whether ES's 3-6 day estimate survives re-derivation post-98 (every baseline
  before 98 is void).
- Nothing shipped. Three probes added: `round_credit.py`,
  `round_decision_credit.py`, and 129's reference table.

---

## 131. The bridge: milestone 1, and two bugs the round-trip caught (08-18)

128.3 left two directions. The choice was made for direction 2 — build the
bridge to real TFT — on the grounds that every simulator-internal avenue is now
closed *by measurement* (128, 129, 130) while the stated goal has no code and
therefore no measurements. Scope is `docs/04_real_game_bridge.md`.

### 131.1 The boundary, stated once

**Injecting input into a live TFT client violates Riot's ToS, permanently bans
accounts, and affects seven real people per lobby.** `bridge/` is read-only and
advisory by construction; doc 04 sec 0 records that actuation is a product
decision and not a refactor. Nothing here synthesises input.

### 131.2 Why this is weeks and not months

`ObservationEncoder.encode` takes `(player, round_id, opponents, board_hexes)`
— **not** a `Match`. The observation layer was already decoupled from the
simulator's game loop, so a real game does not need a simulated one behind it.
`PlayerState` is a plain dataclass and `UnitInstance` takes
`(champion, star, items, position, registry)`. An adapter is therefore the only
missing piece, not a rewrite.

### 131.3 Milestone 1, and its test design

`bridge/state.py` defines `ObservedState` — a source-agnostic JSON description
of what an observer can see, carrying champion ids rather than engine objects so
a fixture, a human, an API or a vision pipeline can produce one without
importing the engine. `bridge/adapter.py` converts both ways.

The test is a **round-trip through the observation vector**, not field-by-field:
engine state → `ObservedState` → JSON → engine state → encode, asserting the two
vectors are identical. A field-by-field comparison passes while silently
dropping whatever the encoder reads and the comparison forgot to check — which
is exactly what would have happened here, twice.

### 131.4 The two bugs, both found on the first run

- **Bench gaps.** `seat_from_player` collapsed empty bench slots. The encoder
  reads the bench **positionally** (`player.bench[index]`) while reading the
  board order-independently (`sorted(board_hexes)`), so collapsing gaps shifted
  every later slot. My own docstring claimed "bench gaps are preserved
  positionally" while the code did not preserve them — the comment was written
  from intent, not from the code. `ObservedSeat.bench` is now positional with
  `None` holes.
- **Augments.** The schema had no augments field at all. Augments occupy their
  own observation section (indices 297-352 of 381), so every reconstructed seat
  silently lost them. Found by locating the mismatched index through
  `spec.describe()` rather than by guessing at offsets — a first attempt at the
  arithmetic put the index in the opponents block and was wrong.

Both are the class of defect that would have made every later bridge
measurement meaningless while looking like it worked, which is what milestone 1
exists to prevent.

### 131.5 Mutation-tested

Four mutations, all caught, each by the assertion that should catch it:
collapsing bench holes, dropping augments, dropping items, and serialising an
unobserved `None` position as `[0, 0]`. The last matters for milestone 2: real
match data carries **no hex positions and no items** (doc 04 sec 3), so the
adapter fabricates geometry, and a caller measuring positional features must be
able to tell invented coordinates from observed ones.

### 131.6 Next, and the one open question

Milestone 2 is coverage: build `ObservedState` from `data/reference/` seats and
report which observation features real data cannot fill. That sizes the vision
problem **before** any vision work is commissioned.

The single highest-value unknown remains untested and is cheap: **does Riot's
Live Client Data API (`localhost:2999`) expose TFT state at all?** League's
payload is rich; TFT's coverage is unverified. Do not assume either way — the
answer decides whether input is an API read or a vision pipeline, which is the
difference between days and months.

---

## 132. Riot exposes no live TFT state; sizing the vision problem instead (08-18)

131.6 named the highest-value unknown: does Riot's Live Client Data API expose
TFT state? Answered, and it decides the shape of the whole bridge.

### 132.1 It does not, and has not for six years

The Live Client Data API (`https://127.0.0.1:2999/liveclientdata/...`) responds
during a TFT match but returns **"basically the same recycled JSON as for
LoL"** — no shop, bench, board, synergies or carousel. The request for exactly
those fields is
[RiotGames/developer-relations#373](https://github.com/RiotGames/developer-relations/issues/373),
**filed 2020-09-24 and still open**, unassigned, with no linked work. Riot's
supported TFT surface is `summoner-v1`, `league-v1` and `match-v1` — all
post-game.

No local probe was possible here (no client running), so this rests on the
issue tracker and the developer portal rather than on a measurement. Recorded
as sourced-not-measured.

**Consequence: live input is a vision pipeline, not an API read.** That is the
months-not-days branch, and it is now decided by evidence rather than by
assumption.

### 132.2 So: what would vision actually have to extract?

`scripts/bridge_coverage.py`, 400 real challenger seats against a 670-state
engine control. "engine fills" = observation indices ever non-zero under full
observation; "real fills" = the same from Riot's match payload.

| section | width | engine fills | real fills | coverage |
|---|---|---|---|---|
| self | 13 | 12 | 6 | 50% |
| selection | 7 | 0 | 0 | n/a |
| board | 168 | 88 | 55 | 62% |
| **bench** | 54 | 54 | 0 | **0%** |
| **shop** | 20 | 20 | 0 | **0%** |
| traits | 35 | 34 | 35 | control! |
| **augments** | 56 | 32 | 0 | **0%** |
| opponents | 28 | 28 | 7 | 25% |
| **TOTAL** | **381** | **268** | **103** | **38%** |

Post-game data fills **38%** of what the policy reads. The three all-zero
sections — bench, shop, augments — are precisely the live-only state, which is
the expected shape and is now quantified: a vision pipeline's minimum viable
scope is **bench + shop + augments + hero scalars**, and board composition is
the part that post-game data already covers.

### 132.3 Two measurement traps, both caught by an impossible number

- **An undersaturated control inflates everything.** The first run used 15
  engine states from one game and reported traits at **250%** — impossible, and
  the tell. 15 states touch 14 of 35 traits; 400 real seats touch all 35. The
  control is the *denominator*: an index it never touches is scored unfillable,
  so undersampling it inflates every coverage figure. Now 60 games / 670
  states, and ratios above 100% print `control!` instead of a number, because a
  ratio that cannot exceed 1 and does is not a coverage figure.
- The totals moved a long way while fixing it: board 98% → 62%, TOTAL 60% →
  38%. **The first table's numbers were all wrong in the flattering
  direction**, which is lesson 27 arriving in a new form — this time the
  aggregate was fine and the *denominator* was the unread row.

### 132.4 Real TFT has 4-star units and this engine cannot represent them

`UnitInstance` caps at `STAR_LEVELS = 3` and the real payload contains
`tier: 4`. Incidence: **0.46% of challenger seats** (37/8000) and 0.51% of
diamond (41/8000), spread across many champions — Veigar, Leona, Ezreal, Poppy,
Gnar, Cho'Gath, Briar — so it is a general mechanic, not one champion's ability.

The adapter clamps to 3 **and counts it**, reporting the count on every run, so
a fidelity gap cannot become a silent fact. Not implementing it: 0.5% incidence
does not justify touching the star system, and the clamp is now visible.

This is the bridge doing what 128.3 predicted — surfacing a class of problem no
simulator-internal work reaches.

### 132.5 Still open

- Milestone 3 (decision service) and 4 (advisory output) are unstarted.
- A vision pipeline is the only live-input path. Its minimum scope is 132.2's
  three zero sections.
- 4-star units unmodelled, deliberately, with the clamp counted.

---

## 133. Bridge milestone 3: the decision service works (08-18)

`bridge/decide.py`. An `ObservedState` in, ranked legal advice out, with no
simulation behind it. Read-only and advisory (doc 04 sec 0).

Working output on a state captured from a real engine game, using the
`bc-econ-s0` clone:

```
round 3-1  level 5  gold 18  hp 83  board 5
kind          detail                                p
BUY           TFT17_Gragas from shop slot 4     80.7%
BUY           TFT17_Veigar from shop slot 1     19.2%
SELECT        TFT17_Milio** @ board -1,4         0.0%
```

### 133.1 Two seams, both load-bearing

131.2 named one; this needed a second, and both held:

* `ObservationEncoder.encode(player, round_id, opponents, board_hexes)` — no
  `Match`.
* `ActionExecutor.legal_mask(player)` — no `Match`.

So **advice is legal by construction**: it comes from the engine's own mask
rather than a re-implementation of the rules, which is doc 03 sec 2.10's
discipline applied to a new consumer. The first draft borrowed a `Match` purely
for board geometry; that was replaced with `Board()` directly, because
borrowing a simulation for its coordinates would have quietly falsified the
module's whole claim.

### 133.2 The encoder must match the weights, and now cannot silently not

`load_advisor` reads the run's sidecar through `teacher_config` for
`champion_encoding` / `scouting` / `copy_counts` / `unit_range`, then asserts
`encoder.size == model.observation_space.shape[0]`. Defaulting those options
would build a differently-shaped or differently-*meaning* observation and the
model's output would be nonsense that still looked like advice — the same
failure `teacher_config` exists to prevent for the teacher (entry 74).

Without a model the advisor returns a **uniform** distribution over legal
actions, and a test pins that it is uniform. A silent fallback that resembled a
policy would be worse than no advice at all.

### 133.3 Three defects the tests found

- **Executor statefulness.** `ActionExecutor` remembers the selected unit, and
  that leaked across `recommend` calls, so PLACE was advised when nothing was
  selected. `recommend` now resets first. The consequence is deliberate and
  documented: advice is for a *clean* interaction state, so SELECT-then-PLACE
  is recommended one step at a time. `ObservedState` has no selection field
  because a live observer cannot reliably see one, and inventing it would put
  the mask out of step with reality.
- **An observed state has no pool history.** Executing a recommended SELL
  against a fresh `SharedPool` raises `ShopError`: the pool never issued the
  copy being returned. Added `bridge.adapter.pool_for`, which deducts every
  *visible* unit — `3 ** (star - 1)` copies — clamped at what remains.
  **Pool state is an inference, not an observation**, and the clamp is
  necessary because real data is partial and 4-star units (132.4) imply more
  copies than the engine models.
- Legality alone is not enough, so the test also **executes** every
  recommendation through `ActionExecutor.apply`. A mask that says yes while the
  executor raises is exactly the divergence doc 03 sec 2.10 forbids, and only
  running it catches that.

### 133.4 Mutation-tested

Four mutations, all caught, each by the assertion meant to catch it: dropping
the executor reset, ignoring the mask when scoring, describing actions by slot
number instead of champion name, and letting `pool_for` return a fresh pool.

### 133.5 Still open

- Milestone 4 (advisory output for a human) is a thin presentation layer on
  this and is unstarted.
- A vision pipeline remains the only live-input path (132.1), scoped by 132.2.
- The advice is only as good as the policy: the clone is at **teacher parity**
  (4.567 vs 4.620) and 130 closed the RL routes to improving it. This ships a
  working pipeline around a mediocre player, which is the honest description.

---

## 134. Bridge milestone 4: usable end to end, and one weak test (08-18)

`scripts/advise.py`. Milestones 1-4 of doc 04 are now built; the bridge does
something a person can use today.

```
round 3-1   level 5   gold 18   hp 83
board: TFT17_RekSai**, TFT17_Aatrox**, TFT17_Milio**, TFT17_Poppy**, TFT17_Ornn*
shop:  TFT17_Nasus, TFT17_Veigar, TFT17_Viktor, TFT17_Rhaast, TFT17_Gragas

#  action        detail                                 confidence
1  BUY           TFT17_Gragas from shop slot 4              80.7%
2  BUY           TFT17_Veigar from shop slot 1              19.2%
```

`--template` writes a skeleton with two real champion ids in it (an empty
template teaches nothing about what an id looks like), `--capture` produces one
from an engine game, and a plain file argument advises on a hand-written state.
Without `--run` the output states that it is uniform and *not advice*.

### 134.1 Actionable errors, because a person types these files

Riot exposes no live TFT state (132.1), so until vision exists an
`ObservedState` is hand-written, and the likeliest failure is a misspelled
`champion_id` — which previously surfaced as a bare `KeyError` from inside the
adapter. `bridge.adapter.validate` now returns messages naming the offending
value and the nearest real ids:

```
this state file cannot be read:
  - hero bench[0]: unknown champion 'TFT17_Akalii'. Did you mean TFT17_Akali, ...
  - shop[1]: unknown champion 'TFT17_Akalii'. Did you mean TFT17_Akali, ...
```

A 4-star is rejected with a pointer to 132.4 rather than a range error, because
"star_level 4 is outside 1-3" is true and unhelpful: real TFT has them and this
engine does not.

### 134.2 A mutation survived, and the test was the problem

Three mutations were run against the validator. Two were caught. **Dropping the
"Did you mean" suggestions entirely survived**, and the cause was the test, not
the code:

The misspelling under test was `real + "x"` — so the real id was a **substring
of its own typo**, and `assert real in problems[0]` was satisfied by the quoted
bad value alone. The assertion looked like it checked the suggestion and checked
nothing. Fixed by transposing the final character instead, asserting the typo
does not contain the real id, and asserting `"Did you mean"` explicitly. The
mutation is now caught.

This is 122.4's lesson in a second form: a surviving mutation is a statement
about the *measurement*. There it was an aggregate hiding a mechanism; here it
was an assertion satisfied by the wrong half of the string.

### 134.3 What the bridge is, honestly

A working, tested, read-only advisory pipeline around a policy at **teacher
parity** (4.567 vs 4.620). It does not make the agent stronger — 130 closed
those routes — it makes the existing agent *usable*, and it surfaced two engine
gaps no simulator work reached (4-star units, 132.4; pool state as an
inference, 133.3).

### 134.4 Still open

- ~~**The vision pipeline is the only remaining path to live play**~~, and
  132.2 scoped it: bench, shop and augments (0% fillable from post-game data)
  plus hero scalars. Everything before it is done.
  **CORRECTED by 136.4: this is false as stated.** A human typing an
  `ObservedState` is *also* live play, and works today with no new code. Vision
  removes the typing; it does not enable the capability.
- Actuation stays unbuilt and out of scope (131.1).
- The advice is only as good as the policy, which is the project's standing
  open problem.

---

## 135. The engine as a combat surrogate at inference (08-18)

The vision pipeline is the next milestone by doc 04's plan, and it is **not
buildable here**: there is no TFT client on this machine and no screenshots, so
anything written would be unverifiable by construction. Recording that as the
reason for taking a different step rather than skipping it silently.

So instead: `bridge/decide.py` gains `board_advice`, which answers the question
a person actually has — *"should I field this unit or that one?"* — by
**simulating the fight**, not by asking the clone.

### 135.1 Why this is available and cloning was not

Entries 106-110 closed search *transmission*: a teacher whose rule is a
simulation cannot be cloned from scoutable features (lesson 26). None of that
applies here, because the search is **run at inference rather than learned**.
The engine is used as a combat surrogate, which is what 105 noted Riot itself
does, and it needs no training run to deliver.

`clone_board` needs a `Match`, but only as a holder: `Match._clone_board` reads
the match's `registry` and board geometry and takes the player explicitly, and
`opponent_panel` reads `match.players`. So `battle_shim` builds a `Match` whose
players are the observed seats and whose eight policies raise if anything ever
tries to step them.

Working, on a hand-built state with two 1-cost 1-stars fielded and two 5-cost
3-stars benched:

```
advice: [('TFT17_Bard***', 'board -2,4'), ('TFT17_Blitzcrank***', 'board -2,5')]
```

`scripts/advise.py --search` prints it alongside the policy ranking, labelled
as a different method answering a different question.

### 135.2 A shipped template that produces a broken state

The first empty-result run looked like a legitimate "your board is fine". It
was not tested against a case where the answer *had* to be non-empty, and when
one was built it raised:

```
ValueError: slot (row=-4, col=0) is outside the 7x4 half-board
```

`position: (0, 0)` is an axial coordinate that **is not one of the 28 own-half
hexes** — and milestone 4's `--template` shipped exactly that. It encodes
without complaint (the encoder never checks) and crashes deep inside combat
geometry the first time the search runs. So the example a person was told to
copy was the one that breaks.

Two fixes: `validate` now checks positions against the real own-hex set and
names three valid examples, and the template emits a real hex. A test asserts
the **shipped template itself** validates, rather than a reconstruction of it.

**An empty result and a broken one are indistinguishable without a case that
must return something.** That is the same discipline as measuring an achievable
maximum before quoting a rate, applied to a feature instead of a metric.

### 135.3 A test whose premise was wrong

The companion test — that the search *declines* when the board is good — failed:
it fielded a 1-cost alongside two 5-cost 3-stars. The search was right and the
test was wrong. `max_board_units` follows level, so a two-unit board at level 8
has **six free slots**, and adding any body is a real improvement. "No change"
is only reachable on a *full* board; the test now uses level 2.

Worth keeping because the asymmetry is real and easy to forget: the board search
almost never declines while slots are open, so its advice early in a game is
"field more units" and only later becomes "swap these two".

### 135.4 Still open

- ~~The vision pipeline, unchanged and unbuildable here (132.1, 132.2).~~
  **Closed by 136.4**, for two independent reasons: it was never the *only*
  path to live play (the typed path already works), and screen capture under
  Vanguard is anti-cheat territory this project does not enter (131.1).
- `board_advice` uses `best_board`'s defaults. Its budget was tuned for a
  teacher inside training loops (106), not for a person waiting on a
  recommendation, and has not been re-derived for this use.
- The search's own value is **0.243 placement at t = −2.00** (108.2, corrected
  in 130.1). Modest, and it should not be oversold as advice.

---

## 136. The advisor's search budget, and a table that measured one state (08-19)

135.4 left `board_advice` running on `best_board`'s shipped defaults —
`trials=3, panel_size=2, max_candidates=6, max_swaps=3` — chosen in 106 for a
teacher inside a training loop, where the search fires tens of thousands of
times and every extra combat is multiplied by that. **An advisor has the
opposite budget:** it fires once, for a person already waiting, and a second of
compute is free. That default had never been re-derived for the regime it is
now used in, which is exactly the "measured once in one regime, became a
default, then a fact" pattern.

`scripts/search_budget.py` runs every arm on the **same** state and grades the
proposals with an independent **referee** — 7 opponents × 12 fights on seeds no
arm ever draws. A search graded on its own fights grades its own noise.

### 136.1 The first table was void: collected states were live references

The first run said every arm was net *negative* and the largest arm never fired
at all — a tidy story about a noise-triggered threshold, and completely wrong.

`collect_states` stored `SimpleNamespace(player=player, match=match)`, which
holds **live references**. The engine keeps mutating those objects as the game
plays on, so every state sampled from one game silently aliased that game's
*final* state. "80 states" were ~12 distinct ones, measured after the fact and
paired against duplicates of themselves — and final states have full boards and
nothing to do, which is precisely why nothing ever fired.

The tell was the control reporting **n=19 of 80**: most aliased players were
dead or boardless by the end. The fix is structural — `sweep` streams, calling
a visitor at the moment each state exists, which is both correct and cheaper
than deep-copying a `Match`.

Corroboration after the fix: the control's t fell from **−264.94 to −17.52** on
the same measurement. The old figure's precision was re-measuring duplicates.

**A snapshot of a mutable object is not a snapshot.** Nothing in the run
errored, the table was fully populated, and every number in it described a
single moment of each game.

### 136.2 The corrected curve, and what the advisor should use

80 states, referee 7 × 12 on unseen seeds. `dv` is survivors per fight against
the seat's current board; `% of ref` is against the large-budget arm.

| arm | fires | referee dv | % of ref | t vs shipped | agrees | sec/call |
|---|---|---|---|---|---|---|
| shipped (t3 p2 c6 s3) | 62% | +0.619 | 81% | — | 50% | 1.06 |
| trials 6 | 56% | +0.713 | 93% | +1.28 | 61% | 2.14 |
| **panel 4** | 51% | **+0.745** | **97%** | **+1.72** | 68% | **2.03** |
| candidates 10 | 68% | +0.572 | 75% | −0.99 | 50% | 1.07 |
| swaps 5 | 64% | +0.660 | 86% | +1.37 | 52% | 1.59 |
| t6 p4 | 49% | +0.741 | 97% | +1.77 | 68% | 3.99 |
| t6 p4 c10 s5 | 49% | +0.800 | 105% | +2.32 | 80% | 6.04 |
| large-budget ref | 46% | +0.765 | 100% | +1.95 | 100% | 20.83 |

Outcome **B** of the three named before the run: there is headroom and it is
cheap. `ADVISOR_SEARCH = {"panel_size": 4, "margin": 1.0}` — 81% → 97% of the
reference for about one extra second. The largest arm's 105% is not
distinguishable from it and costs three times as much.

Two honest limits:

- **t = +1.72 at n=80 is not a significant result.** This is evidence good
  enough to set a default in a regime that had no measurement at all, not a
  claim that panel 4 beats panel 2.
- **An arm scoring 105% proves the reference is not a ceiling.** It searches
  the same candidate generator with more compute, so it can be exceeded. The
  column was renamed from "% of ceiling" to "% of ref" rather than the number
  being explained away — a real achievable maximum is still unmeasured.

Widening the panel *narrows* firing (62% → 51%) while raising value. The extra
opponents mostly reveal that a proposal which beat the two strongest seats does
not beat the field.

### 136.3 `margin` is not panel-invariant, in all three search functions

`score()` divides by `trials` but **not** by `panel_size`
(`rl/search.py:168`, `:254`, `:521` — `best_swap`, `best_board`, `best_move`).
So `margin` is a threshold on the margin *summed over the panel*. Raising the
panel silently loosens the firing rule, and a wider-panel arm would have looked
better partly by firing more rather than searching better.

The probe holds the per-fight threshold fixed so budget is the only variable,
and `ADVISOR_SEARCH` carries `margin` explicitly alongside `panel_size`. A test
pins the coupling and was mutation-tested (panel 5 with margin 1.0 fails).

Not fixed in `rl/search.py` itself: normalising there would change teacher
behaviour and invalidate every search baseline. 106's `margin=0.5` should be
read as "0.25 per fight at a panel of 2".

### 136.4 Correcting "the only remaining path to live play"

134.4 and 135.4 both assert the vision pipeline is **the only remaining path to
live play**. That is false, and it was written three times without examination.
A human typing an `ObservedState` is also live play, and `scripts/advise.py`
does it today with no new code. Vision removes typing; it does not enable the
capability. Both entries now carry banners.

The distinction matters because vision is separately closed. 132.1 established
there is no live API. Screen capture under Vanguard then raises the question of
whether a tool would be *flagged* — and designing for non-detection is not
something this project does, on the same footing as 131.1's line against input
injection. A camera pointed at the monitor does not change that; it changes
only observability.

The question that actually decides the branch is whether Riot permits this
class of advisory tool at all — TFT has a tolerated overlay ecosystem, so the
answer is not obviously no. That is a policy question, answerable from Riot's
third-party tool terms rather than by experiment, and it is **not answered
here**.

### 136.5 Still open

- Riot's third-party tool policy for TFT, which decides whether any automated
  reader is permissible. Unread; no work should start on one before it is.
- A real achievable maximum for the board search. The large-budget arm is a
  reference, not a ceiling (136.2).
- The search's placement value remains **0.243 at t = −2.00** (108.2, corrected
  in 130.1). This entry improved the *board* it proposes; it did not re-measure
  what that is worth in placement, and the two must not be conflated.
- The advisor's per-round data entry cost is unmeasured. Whether the typed path
  is pleasant enough to use is now the question that gates everything, and it
  needs a human trying it, not a probe.

---

## 137. Does board advice need to know the opponents? (08-19)

This gates the typed path, which 136.4 established is the only live-play route
this project will take. `board_advice` picks a board by simulating fights
against a panel of opponents, so as written a person must enter **eight boards
a round** — which nobody will do. If advice survives a panel built from no
opponent information, they enter **one**: their own.

136.2 made this a live question rather than a formality: widening the panel
from 2 to 4 moved both firing rate and value, so *who* is simulated against
demonstrably matters.

Arms differ only in the panel the **search** sees. Every proposal is graded by
the same referee against the **true** field, because that is what the player
actually fights; grading a surrogate against itself would let a consistently
wrong panel score well.

### 137.1 Breadth is what pays, and identity is not

80 states. `dv` is survivors per fight; `agrees` is proposing the same units as
the true-field arm.

| search panel | fires | referee dv | % of true | t vs true | agrees | sec/call |
|---|---|---|---|---|---|---|
| true field (shipped) | 51% | +0.745 | 100% | — | 100% | 2.06 |
| **mirror (no opp info)** | 65% | **+0.525** | **70%** | −3.11 | 55% | 0.56 |
| one opponent | 61% | +0.505 | 68% | −2.95 | 49% | 0.61 |
| mirror, fights matched | 65% | +0.461 | 62% | −3.09 | 57% | 2.24 |
| one opp, fights matched | 59% | +0.575 | 77% | −2.04 | 56% | 2.42 |

**Fight count was a confound and is controlled.** `best_board` runs
`panel_size × trials` combats, so a one-member panel at the default `trials=3`
simulates 3 fights against the true field's 12. The first run of this probe did
exactly that. Matching the fight count does **not** close the gap — mirror goes
*down* (70% → 62%), one opponent up only to 77%. So the missing value is
opponent **diversity**, not simulation volume.

Two findings, neither of which was among the outcomes named before the run
(A "mirror is enough", B "one opponent is enough, mirror is not", C "the field
is required"):

- **Partial opponent knowledge is worth nothing.** Scouting one real board
  (68%) is not better than fighting your own shadow (70%). Whatever the true
  field contributes, it is a property of *averaging over several* opponents and
  not of knowing any particular one. B is refuted specifically.
  > **The "averaging over several" reading is CORRECTED by 138.1.** Averaging
  > over several *synthetic* boards recovers nothing, so breadth per se was not
  > the mechanism. The observation stands; the explanation was wrong.
- **More compute against the wrong objective made it worse.** The mirror arm
  lost value when given 4× the fights, because the extra precision sharpens an
  answer to the wrong question. Budget is only worth buying once the objective
  is right — which qualifies 136.2's curve.

Agreement is the other half of the story: the surrogates propose the same units
only ~55% of the time. This is not a small perturbation of the same advice, it
is different advice that happens to be worth somewhat less.

### 137.2 Shipping the mirror fallback

`best_board` gains an optional `panel_fn`, defaulting to `opponent_panel` so
the teacher is unchanged. `board_advice` uses it when a state carries no
opponent boards, fighting a mirror of the player's own board instead of
returning nothing — which is what it did before, since an empty panel makes
`best_board` bail immediately.

So the typed path now costs **one board per round** and delivers 70% of the
board-search value. Mutation-tested by removing the branch.

The honest framing: 70% of a search whose own placement value is 0.243 at
t = −2.00 (108.2, corrected in 130.1). This makes the typed path *possible*, and
it should not be sold as making it *strong*.

### 137.3 Still open

- Whether a **synthetic panel of several diverse boards** recovers the missing
  30%. 137.1 says breadth is the active ingredient and breadth does not require
  real opponents — a library of stage-typical boards is the obvious test and
  was not run.
- Riot's third-party tool policy (136.5), still unread, still gating any
  automated reader.
- The per-round data entry cost of the typed path, still unmeasured and still
  needing a person rather than a probe.
- A real achievable maximum for the board search (136.5).

---

## 138. A prior cannot stand in for the real field (08-19)

137.3 left the obvious follow-up: if breadth is what the true field supplies,
breadth is *prior knowledge* and needs no scouting. A library of stage-typical
boards, harvested offline from games seeded far from the evaluation games,
should then recover the missing 30%.

It does not.

### 138.1 Four opponent-free panels, one number

80 states, every arm graded by the referee against the **true** field.

| search panel | fires | referee dv | % of true | t vs true | agrees |
|---|---|---|---|---|---|
| true field (shipped) | 51% | +0.745 | 100% | — | 100% |
| mirror (no opp info) | 65% | +0.525 | 70% | −3.11 | 55% |
| library, stage-matched | 39% | +0.501 | 67% | −2.91 | 66% |
| library, size-matched | 41% | +0.531 | 71% | −2.63 | 65% |
| library, any stage | 28% | +0.330 | 44% | −3.24 | 55% |

Outcome **C** of the three named before the run. **The flatness is the result:**
a self-mirror, a stage-matched library and a size-matched library are four
quite different objects and all land in 67–71%. Only the stage-agnostic library
is worse (44%), which says a panel must be roughly the right *power level* —
and that once it is, nothing further about it helps.

So **137.1's explanation was wrong and is corrected there.** Averaging over
several synthetic boards buys nothing over fighting one copy of yourself.
Breadth was not the mechanism. The observation that one real opponent ≈ mirror
still stands; the inference drawn from it did not.

A first library run was worse still (39% firing against the true field's 51%),
which I read as a calibration defect rather than a fact about priors: `harvest`
freezes a seat the moment its game ticks into the target stage, so the library
held *early*-stage boards. Matching on the player's own board size instead —
which also costs the player nothing to know — moved it to 71% and 41% firing.
That is a real improvement over the stage index and still not a recovery. The
axis was changed to the one that discriminates, and the answer did not move.

### 138.2 The 100% baseline is in-sample, and that flatters it

The true-field arm searches against the same opponents the referee grades it
against — different fight seeds, but the same seats. Every surrogate is
out-of-sample by construction. So the true field is being scored partly on
information it was handed.

That makes **70% a lower bound** on what opponent-free advice is worth
relative to a fair baseline, not a point estimate. A player in a real lobby
fights *one* opponent per round, not a panel average, so the true-field arm's
advantage here is larger than the one available in play.

Recorded rather than corrected: fixing it means grading against a held-out
opponent the search never saw, which is a different probe. It does not change
the decision below, because it can only move the surrogates *up*.

> **The "can only move the surrogates up" prediction FAILED — see 139.1.** The
> probe was run. Fair held-out grading leaves the ratio at 68% against 70%,
> i.e. unchanged and marginally *down*. The in-sample advantage is real but
> small (+18%, not significant) and does not explain the deficit.

### 138.3 What this settles

**Do not build the library.** The mirror fallback already shipped in 137.2 is
as good as any prior tested, costs nothing to maintain, and needs no harvest
step. `scripts/synthetic_panel.py` is kept as the evidence that the more
elaborate thing was tried and did not pay.

The typed path's value is therefore what 137.2 shipped: one board a round, ~70%
of true-field board-search value, on a search worth 0.243 placement at
t = −2.00 (108.2, corrected in 130.1).

### 138.4 Still open

- Why real contemporary opponents beat every substitute is **unexplained**.
  Power level is necessary (the 44% arm) and not sufficient (the 71% arm).
  Something about the actual field is carrying the remaining 30% and this
  entry does not identify it.
- A fair baseline for the true field, graded against held-out opponents
  (138.2).
- Riot's third-party tool policy (136.5), unread, still gating any automated
  reader.
- The per-round data entry cost of the typed path (137.3), still needing a
  person rather than a probe.

---

## 139. The in-sample caveat was right and did not matter (08-19)

138.2 flagged that the true-field arm searched against the same seats the
referee graded it on, and predicted this made 70% a floor — that fair grading
"can only move the surrogates up". This grades every arm against a **held-out
half of the lobby**: living opponents split alternately by strength, the search
sees half A, the referee scores half B.

### 139.1 The prediction failed; the ratio did not move

70 states with at least four living opponents.

| search panel | fires | referee dv | % of true | t vs true | agrees |
|---|---|---|---|---|---|
| true half (held out) | 49% | +0.441 | 100% | — | 100% |
| mirror (no opp info) | 63% | +0.302 | **68%** | −1.75 | 49% |
| true field (in-sample) | 40% | +0.521 | 118% | +1.25 | 54% |

Outcome **C** of the three named beforehand. Searching against your graders is
worth **+18%** — real, in the predicted direction, and **not significant at
n=70** (t = +1.25). Removing it leaves opponent-free advice at 68% against
138.1's 70%: unchanged, and if anything marginally worse.

So 138.2's caveat was correct as a description of the design and wrong as a
prediction about the result. Recorded as a failed prediction.

**One thing must not be spun.** The mirror's t-statistic fell from −3.11 to
−1.75, which would ordinarily read as "the deficit is no longer significant".
It is not evidence the surrogates improved. The *ratio* is identical; what
changed is that held-out grading is noisier and smaller in absolute terms
(+0.441 against +0.745), so the same relative gap is resolved less sharply. A
weaker t against an unchanged point estimate is a weaker measurement, not a
better result.

### 139.2 What is now known about the 30%

Three explanations have been tested and none accounts for it:

| explanation | tested in | verdict |
|---|---|---|
| simulation volume (more fights) | 137.1 | no — matching fight count did not close it |
| breadth (several boards, any source) | 138.1 | no — four surrogates all land at 67–71% |
| in-sample advantage over the graders | 139.1 | no — worth +18%, n.s., ratio unchanged |

What survives: a panel must be roughly the right **power level** (138.1's
stage-agnostic arm at 44% establishes the floor), and beyond that every
substitute for the actual contemporary field is worth the same 68–71%. The
mechanism carrying the remainder is still unidentified, and it is now the
narrowest it has been — three candidates eliminated rather than one.

The untested one worth naming: real lobby opponents draw from the **same shared
champion pool** as the player, so their boards are anti-correlated with the
player's own in a way no foreign board can be. That is a testable difference
and this entry does not test it.

### 139.3 Still open

- The pool-correlation hypothesis above, untested.
- Riot's third-party tool policy (136.5), unread, still gating any automated
  reader.
- The per-round data entry cost of the typed path (137.3), still needing a
  person rather than a probe.
- The decision is unchanged: ship the mirror (137.2), do not build a library
  (138.3). Two entries of adversarial testing have not moved it.

---

## 140. Two more explanations refuted, and a plateau (08-20)

139.3 named the shared champion pool as the untested explanation for the ~30%
that opponent-free board advice gives up: real lobby opponents draw from the
same pool, so their boards are *anti*-correlated with the player's in a way no
foreign board is.

A prior was stated against it before testing. The mirror is *maximally*
correlated with the hero and a library panel is essentially *un*correlated, and
138.1 measured both at 70-71%; if pool structure drove the gap those two should
already have differed.

### 140.1 Pool overlap is not the mechanism

Power is held fixed first (board size within ±1 of the hero's) and overlap
ranks only within that band, so the arms differ in champion overlap rather than
in strength. The real field shares **10.3%** of the player's champions on
average, so there was ample anti-correlation for the mechanism to exploit.

| search panel | fires | referee dv | % of true | t vs true |
|---|---|---|---|---|
| true field (shipped) | 51% | +0.745 | 100% | — |
| mirror (no opp info) | 65% | +0.525 | 70% | −3.11 |
| library, low overlap | 48% | +0.580 | 78% | −2.08 |
| library, high overlap | 49% | +0.535 | 72% | −1.87 |

**low − high = +0.046 survivors/fight, t = +0.83, n = 80.** Outcome **C**: in
the hypothesised direction and indistinguishable from zero.

The first version of this run reported only each arm's distance from the true
field, which cannot settle whether the two differ from *each other* — B and C
differ on exactly that. The direct paired comparison was added and rerun.
**Quoting two arms' distances from a third is not a comparison between them.**

### 140.2 A real confound in my own design, which explained nothing

A power diagnostic (no combat, 80 states) checked whether library panels were
matched in strength or merely in unit count:

| panel | units | mean star | mean cost | items/unit |
|---|---|---|---|---|
| true field | 6.26 | 1.60 | 2.17 | 0.62 |
| library (size-matched) | 6.52 | 1.78 | 2.02 | 0.58 |
| hero | 6.44 | 1.65 | 2.06 | 0.58 |

Well matched — but it exposed something else. `opponent_panel` takes the
**strongest** living seats, which 106 chose deliberately. Every surrogate built
across 137-140 is matched to the **hero's** strength instead: the mirror *is*
the hero, size-matching targets the hero's board. So all of them fight average
boards while the true field fights the top of the lobby. That is a genuine
confound in four entries of arms, and it needs no scouting to fix — "what a
strong board looks like at this stage" is prior knowledge.

Fixing it made things **worse**: a strongest-board library panel scores **60%**
(t = −2.58), below both size-matched (71%) and the mirror (70%). The confound
was real and is not the explanation. Recorded as a refuted prediction, not
quietly dropped.

### 140.3 The plateau, and five eliminated explanations

| explanation | tested in | verdict |
|---|---|---|
| simulation volume | 137.1 | no — matching fight count did not close it |
| breadth from any source | 138.1 | no — four surrogates at 67–71% |
| in-sample advantage | 139.1 | no — +18%, n.s., ratio unchanged |
| shared-pool anti-correlation | 140.1 | no — +0.046, t = +0.83 |
| panel strength selection | 140.2 | no — worse, 60% |

Opponent-free board advice sits at **60–78% of true-field value however the
panel is built**, across six differently-constructed surrogates. Only gross
power mismatch moves it (the 44% stage-agnostic arm). This is now a
well-tested plateau rather than a single measurement, and **the cause is
unidentified after five hypotheses**.

Stating that plainly instead of reaching for a sixth. The useful summary is
negative and stable: *no construction of fake opponents tested here recovers
what the actual contemporary field provides, and none of the obvious reasons
why is correct.*

### 140.4 Still open

- The mechanism, still unidentified. Five candidates eliminated is a narrower
  question than 138.4 posed, not an answer.
- Riot's third-party tool policy (136.5), unread, still gating any automated
  reader.
- The per-round data entry cost of the typed path (137.3), still needing a
  person rather than a probe.
- The decision is **unchanged for the fourth entry running**: ship the mirror
  (137.2), do not build a library (138.3). It has now survived attacks from
  five directions, which is the strongest thing that can be said for it.

---

## 141. What a comparison costs here, and why everything looks like a null (08-20)

Asked after a session in which **three separate results reversed on more data**:
the board-search budget pilot (n=6 said 103% of reference, n=80 said 67%), the
teacher econ table (n=60 said `slowroll6` best, n=120 said `fast8`), and an
apparent 0.45 action-space tax (n=120 said +0.450 at t=+1.57, n=400 said
−0.150 at t=−1.01, i.e. the sign flipped).

Three reversals in a day is not bad luck. It is a statement about the
instrument, and this entry prices it.

### 141.1 There is no action-space tax

`scripted_policy` reimplements `GreedyPolicy` through the RL action space, and
its own docstring names the diagnostic: if a sensible heuristic cannot reach
~4.5 against the same heuristic bots, the action space is handicapping the
agent. `TFTEnv.reset` uses `match_seed = seed` and `default_opponent(i)` for
seats 1-7, so the same seed builds an identical `Match` with identical
opponents in either harness and the two are pairable seed for seed.

**The n=120 result was noise and its sign did not survive.** Recorded because a
recommendation was nearly built on it: an 0.45 handicap in the cloning target
would have meant every result in this log was measured against an artificially
depressed teacher. It is not there.

### 141.2 The price list

From the n=400 paired run, the standard deviation of seed-paired placement
differences is **≈ 2.97**. That fixes the cost of every comparison:

| effect | games per arm for t = 2 |
|---|---|
| 0.50 placement | ~140 |
| 0.30 placement | ~390 |
| 0.15 placement | **~1,570** |

Set against what is actually on offer: the board search is worth 0.243 (108.2,
corrected in 130.1); native `fast8` vs `standard` is **+0.033 at t = +0.19**;
the whole named-archetype choice barely registers without the teacher's
handicap to recover from. Most candidate improvements sit at or below the noise
floor of the metric used to detect them.

This is the same wall as 130 (per-decision value 46× below its noise) and 94
(ES at 3-6 days), reached from a third direction. **Methods have not been
failing; the instrument cannot resolve them.**

### 141.3 A denser instrument buys 1.4x, not 10x

`RoundReport` already carries `won`, `damage_taken` and `hp_after` per player
per round -- signals a policy moves every round rather than once a game. One
comparison with a large real effect (fast8 vs no econ, n=200), scored five
ways. `games needed` is relative to placement, since n scales as 1/t².

| metric | diff | t | \|r\| vs placement | games needed |
|---|---|---|---|---|
| placement | −1.695 | −9.33 | 1.00 | 200 |
| **pvp win rate** | +0.146 | **+11.07** | 0.88 | **142** |
| rounds | +3.315 | +9.88 | 0.90 | 178 |
| damage taken | −8.025 | −4.60 | 0.53 | 824 |
| mean hp | +2.647 | +3.96 | 0.43 | 1109 |

Outcome **B**, and barely: pvp win rate is the sharpest at ~1.4× and does not
change what is affordable. Damage taken and mean HP are **worse** than
placement despite accumulating every round -- they correlate 0.53 and 0.43,
which is the failure this probe was built to catch: precise measurement of
something other than winning.

**The noise is the game's, not the metric's.** Re-instrumenting does not
rescue the budget.

### 141.4 What follows

The useful reading is not "everything is too expensive" but a rule about which
questions are worth asking:

- **An effect of 0.5 costs ~140 games**, which is minutes. Large levers are
  cheap to test and always were. `fast8` against no econ is −1.695 natively --
  effects that size exist.
- **An effect of 0.15 costs ~1,570 games** and should not be attempted casually.
  Most of the last thirty entries have been in this regime.
- A screen at n=200 resolves anything ≥0.45 at t≈2. That is the natural
  default, and anything it cannot see is not worth chasing without a budget
  decision made deliberately.

Adopt pvp win rate as a secondary readout where it is free -- it is 1.4× and
correlates 0.88 -- but not as a substitute for placement.

### 141.5 Still open

- Whether the 1.4× efficiency measured on a **large** effect holds for the
  small ones that matter. It was measured where measurement is easy, which is
  exactly the objection this project raises against other people's numbers.
- The joint `EconStrategy` parameter search, still untried, now priced: only
  worth running if its effects are ≥0.3, and native archetype choice at +0.033
  argues they are not.
- Riot's third-party tool policy (136.5) and the typed path's data entry cost
  (137.3), both still needing a person rather than a probe.

---

## 142. The joint econ search finds nothing, and the held-out stage is why we know (08-21)

Entry 72 compared four hand-written archetypes and picked the best. The
parameters themselves have never been searched, and they interact: when to roll
depends on when to level, which depends on what is being rolled for. Every
existing A/B varies one at a time, which is the method that misses the optimum
in a coupled space.

Run at the user's direction after I advised against it on 141's pricing. The
advice was to skip it; recording that the measurement was worth having anyway,
because a bound is more useful than a prior.

### 142.1 Design, priced before running

The genome covers the family containing `fast8` and `standard`: a monotone
five-point level curve, one roll-down window with a floor, an optional restore
round, `save_floor`, and `desperation_hp`. Both shapes the `EconStrategy`
docstring warns about are reachable -- "roll down once then rebuild" and "roll
the surplus forever" -- since collapsing them is the documented way to get this
wrong.

Two stages, because selecting the best of many noisy estimates is winner's
curse. 60 candidates screened at n=200 (which 141.2 prices at ~0.42
resolution), then the leaders confirmed on **800 disjoint seeds**. Re-running
the screen seeds would re-confirm the luck that won the screen.

### 142.2 Nothing beats the hand-written archetypes

Screen, 62 arms at n=200. Best candidate reached t = −1.28 against `fast8` --
**nothing was significant even on the screen**, and the hand-written archetypes
ranked 3rd and 6th of 62.

Held out, n=800 fresh seeds:

| arm | screen | held-out | regression | vs fast8 | t |
|---|---|---|---|---|---|
| c33 | 4.145 | 4.200 | +0.055 | **+0.217** | **2.60** |
| c06 | 4.225 | 4.131 | −0.094 | +0.149 | 1.87 |
| standard | 4.245 | 4.004 | −0.241 | +0.021 | 0.28 |
| fast8 | 4.360 | 3.982 | −0.378 | — | — |

Both screen winners are **worse** than `fast8` on held-out seeds, `c33`
significantly (t = 2.60, and the sign says worse). Outcome **B**.

An arithmetic check made this predictable mid-run and is worth keeping: the
best of 47 screened candidates led `fast8` by 0.215, while the *expected*
best-of-47 lead under pure noise at n=200 (SE ≈ 0.21) is ~2.3 SE ≈ 0.48. The
leader was doing worse than chance alone would produce if every candidate were
truly equal -- i.e. the candidates were genuinely worse on average, and the
hand-written strategies sit near a local optimum.

### 142.3 Two traps the design caught

- **A pattern in the screen's top five was an artifact.** All five picked
  `save_floor` 60, above the documented interest cap of 50 -- exactly the kind
  of cross-parameter signal a joint search exists to find, and it was flagged
  as provisional at the time. Both finalists carried it and both are worse.
  Five correlated picks out of 60 is not evidence.
- **Both baselines moved 0.24-0.38 between the two seed blocks.** `fast8` reads
  4.360 on the screen block and 3.982 on the held-out block. Any comparison
  across blocks would have been meaningless; only the within-block paired
  contrasts above are readable. This is lesson 12 in a new form.

### 142.4 What it bounds, and what it does not

**Bounds:** 60 random samples of the curve-plus-rolldown family contain no
improvement over `fast8`/`standard` large enough to survive n=800. Combined
with 141's native archetype difference of +0.033 at t=0.19, the economy
parameters look flat near the incumbents.

**Does not bound:** 60 samples is sparse coverage of a ~9-dimensional discrete
space, and this is a statement about what *random search* finds, not about what
exists. The reroll family (`target_cost`, `target_count`, `commit_level`,
`pivot_at`) was excluded to keep the dimension manageable and is untouched
here.

**Cost:** ~20,000 games, 3h40m on 8 workers. My estimate beforehand was ~1
hour, so the pricing was off by 3.5x -- worth knowing before budgeting another.

### 142.5 Still open

- The reroll-family parameters, unsearched.
- Whether a *local* search around `fast8` (rather than uniform random) finds
  what random sampling missed. Cheaper per candidate to justify only if there
  is reason to expect a nearby optimum, and 142.2 argues the incumbents are
  already at one.
- The typed path's data entry cost (137.3), still needing a person.

---
