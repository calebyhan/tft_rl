# TFT Data Schema & Sourcing Guide

Purpose: defines the clean JSON schema the engine consumes, and how to get
real, current Set 17 (Space Gods, patch 17.8) data into that schema. This
part of the project *will* go stale — re-run the fetch when Set 18
(Enchanted Wilds, launching 2026-08-26) goes live, or any time you want to
re-sync with balance patches.

## Amendments

- **2026-08-01** — Section 2: `ItemDef` gains an optional `params` object, for
  effect magnitudes that are not stats the wearer gains (Bramble Vest's
  reflect, Dragon's Claw's reduction). Without it, that whole class of item
  effect cannot be data-driven. The section also now documents two existing
  conventions: the `emblem_<TraitId>` effect-id form, and the reserved
  `targets` key on trait breakpoint params.
- **2026-08-01 (milestone 8)** — Section 1 rewritten against the *real*
  CDragon payload rather than assumptions. Several statements below were
  wrong and are corrected in place: patch pinning uses League patch numbers,
  the champion list needs a second endpoint to filter out PVE units, and
  per-star stats are derived rather than published. New section 1.2 records
  the payload's actual shape. New section 4 defines `config.json` (entry 2.1,
  now closed).

Important constraint: the data-fetch step needs normal internet access. It is
*not* runnable from a network-locked sandbox — but it was verified end to end
from this one, which does have access, so the mappings below are observed
rather than guessed.

## 1. Source of truth: Community Dragon (CDragon)

CDragon publishes Riot's TFT game data as JSON, rebuilt from client/LCU
files (not officially maintained by Riot, but the de facto standard source
the whole TFT tooling community uses).

Key endpoints. Replace `latest` to pin a version — but note the path segment
is the **League client patch number** (`15.16`, `16.1`), *not* the TFT set or
its in-game patch label. `17.8` is not a valid path and returns 404; the fetch
script turns that into an explanatory error.

- `https://raw.communitydragon.org/latest/cdragon/tft/en_us.json`
  — the main combined file: champions, traits, items, and augments in one
  document, in Riot's native (somewhat messy) internal shape. ~26 MB.
- `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/tftchampions-teamplanner.json`
  — **required, not optional.** The main payload cannot tell a shop unit from
  a PVE monster or summon (Set 17: 83 entries for 63 real units), and this
  file lists only real units, with their cost as `tier`. It also pairs trait
  display names with trait ids, which the main payload does not.
- Data Dragon (`ddragon.leagueoflegends.com`) also publishes simplified
  `tft-champion.json`, `tft-item.json`, `tft-augments.json` files, but Riot's
  own docs note ddragon's spell/stat data is **less accurate** than what
  CDragon derives — prefer CDragon as primary source, use ddragon only for
  quick sanity cross-checks or image asset paths.
- Data Dragon (`ddragon.leagueoflegends.com`) also publishes simplified
  `tft-champion.json`, `tft-item.json`, `tft-augments.json` files, but Riot's
  own docs note ddragon's spell/stat data is **less accurate** than what
  CDragon derives — prefer CDragon as primary source, use ddragon only for
  quick sanity cross-checks or image asset paths.

### 1.1 Fetch script responsibilities (implement as `scripts/fetch_cdragon.py`)
1. GET the `cdragon/tft/en_us.json` file for a pinned patch (default to
   `latest` if none specified).
2. Select the set from `setData` (a *list*, not the `sets` map — `sets` also
   exists but is sparser). Each entry has a `mutator`; the base set is
   exactly `TFTSet<N>`. Filtering on `number` alone is wrong, because the
   game-mode variants (`TFTSet17_PVEMODE`, `_TURBO`, `_PAIRS`,
   `TFTSetEvent5YR`) share the same number.
3. Normalize each champion entry into the Champion Def schema (Section 2)
   — this means renaming/reshaping Riot's internal field names
   (`apiName`, `stats.hp`, `stats.damage`, `ability.variables`, etc. — exact
   field names must be inspected directly from the fetched payload since
   they aren't publicly documented in a stable schema) into the clean shape
   below.
4. Normalize traits and items the same way into their Def schemas. Note for
   items specifically:
   - Riot's item effect variables must be split between `stats` (bonuses the
     wearer gains) and `params` (everything else) — see Section 2.
   - Emblems must get `effect_id: "emblem_<TraitId>"`, matching the trait id
     used in `traits.json`, or the loader will reject them.
5. Write output to `data/champions.json`, `data/traits.json`,
   `data/items.json` and `data/VERSION.json`. It must **not** write
   `data/config.json` — see section 4.
6. Log any champion/trait/item that failed to parse rather than silently
   dropping it, so gaps are visible.
7. The loader rejects **unknown fields** as well as missing ones, so the
   normalizer must drop Riot's extra keys rather than passing them through.
   That strictness is deliberate (a renamed field fails loudly instead of
   silently dropping a stat) but expect to hit it while iterating.

Because Riot's raw internal JSON field names are not stable/documented and
must be discovered empirically from the live payload, budget real
iteration time for this script — expect to inspect the actual fetched JSON
structure and adjust field mappings rather than trusting a fixed field list
written from memory.

### 1.2 What the payload actually looks like

Observed 2026-08-01 against `latest` (Set 17). Recorded because none of it is
documented by Riot, and every item here cost real inspection time.

**Champions** live at `setData[i].champions`. Relevant fields: `apiName`,
`name`, `cost`, `role`, `traits` (display names), and a flat `stats` object
with `hp`, `damage`, `armor`, `magicResist`, `attackSpeed`, `range`,
`initialMana`, `mana`, `critChance`, `critMultiplier`.

Four things that are *not* as the schema in section 2 might suggest:

- **Stats are single scalars, not per-star arrays.** Riot ships the 1-star
  value and the game applies a per-star multiplier. The fetch script derives
  the triples using the LoL wiki's figures — health ×1.8/star (100/180/324%)
  and attack damage ×1.5/star (100/150/225%). These are *approximations*: real
  per-champion values can differ slightly.
- **`role` uses Riot's 13-value taxonomy** (`ADCarry`, `APTank`, `APReaper`,
  `ADSpecialist`, …), which must be collapsed onto the five roles doc 01
  sec 3.2 models. This drives `mana_per_attack`, so it feeds combat directly.
  At least one unit ships `role: null`.
- **Nulls appear where you would expect a number.** Set 17's Miss Fortune has
  `damage: null`; `dict.get(key, default)` does not save you, because the key
  is present. Some units ship `mana: 0` (Caitlyn) or `damage: 0` (LeBlanc,
  Riven) — all of which the engine's schema rejects.
- **`ability.variables` is a list of `{name, value}` where `value` has 7
  entries.** Star levels 1–3 are at **indices 1, 2, 3**. Index 0 is a
  placeholder, index 4 an unused 4-star slot, 5–6 padding. Verified across the
  set: 151 of 168 varying variables rise monotonically over exactly 1..3.

**Traits** live at `setData[i].traits` with `apiName`, `name`, and `effects`
(a list of `{minUnits, maxUnits, style, variables}` → our breakpoints).
Champions reference traits by **display name**, and display names are not
unique — Set 17 has 8 apiNames named "Stargazer". The team-planner file is
what disambiguates. Some traits have an empty `effects` list (the "Choose
Trait" placeholder) and must be dropped. Riot does **not** publish
origin-vs-class, so that split is curated from the lists in section 3.

**Items** live at the top-level `items` list (all sets, ~3680 entries);
`setData[i].items` holds the apiNames in scope for the set. Fields:
`apiName`, `name`, `composition` (recipe), `unique`, `associatedTraits`,
`tags`, and a flat `effects` dict. Notes:

- The 10 basic components carry the literal tag `component`.
- **Units are inconsistent between keys.** `AD` is already a fraction
  (`0.35` = +35%) while `AS` and `CritChance` are percentages (`35.0` = 35%).
  Never map an unrecognised key by guessing its units — leave it in `params`.
- **`associatedTraits` is empty on real emblems**, and the apiName does not
  reliably name the trait (`TFT17_Item_FavoredEmblemItem` is the *Arbiter*
  emblem). Match on the display name: `"<Trait> Emblem"`.
- Many `tags` and some `effects` keys are untranslated hashes (`{d8d00bcc}`).

## 2. Clean schema definitions (what the engine actually consumes)

```jsonc
// champions.json — list of ChampionDef
{
  "id": "TFT17_Jinx",              // stable internal id, matches CDragon apiName
  "display_name": "Jinx",
  "cost": 4,
  "traits": ["BattleCat", "Sniper"], // origin(s) + class(es), by trait id
  "role": "Marksman",       // Assassin | Marksman | Fighter | Caster | Tank
                             // (Set 15+ role revamp; drives mana_per_attack
                             // below and whether taking-damage mana applies)
  "stats": {
    "health": [800, 1440, 2600],    // per star level 1/2/3
    "armor": 35,
    "magic_resist": 35,
    "attack_damage": [60, 90, 150], // per star level (or single value if
                                     // AD doesn't scale — verify per champ)
    "attack_speed": 0.75,           // attacks per second at base
    "attack_range": 4,              // in hexes
    "starting_mana": 0,
    "max_mana": 100,
    "mana_per_attack": 10,          // role-derived: 10 Assassin/Marksman/
                                     // Fighter, 7 Caster, 5 Tank (doc 01 sec 3.2)
    "crit_chance": 0.25,
    "crit_damage": 1.4
  },
  "ability": {
    "name": "Get Excited!",
    "cast_mode": "mana",            // "mana" | "cooldown"
    "cooldown_seconds": null,       // set if cast_mode == "cooldown"
    "effect_id": "jinx_get_excited",// key into the effects registry (code)
    "params": {                     // raw ability variables, per star level
      "damage": [180, 270, 2000],
      "attack_speed_bonus": 0.75
    }
  }
}
```

```jsonc
// traits.json — list of TraitDef
{
  "id": "BattleCat",
  "display_name": "Battle Cat",
  "category": "origin",            // "origin" | "class" (verify exact
                                     // wording used this set — Set 17 wiki
                                     // groups them as "Origins" / "Class")
  "breakpoints": [
    { "count": 2, "effect_id": "battlecat_2", "params": {} },
    { "count": 4, "effect_id": "battlecat_4", "params": {} },
    { "count": 6, "effect_id": "battlecat_6", "params": {} }
  ]
}
```

```jsonc
// items.json — list of ItemDef
{
  "id": "TFT_Item_InfinityEdge",
  "display_name": "Infinity Edge",
  "is_component": false,
  "recipe": ["TFT_Item_BFSword", "TFT_Item_SparringGloves"], // null/empty
                                                               // if component
  "unique": false,
  "stats": {                        // flat stat bonuses, additive
    "attack_damage": 65,
    "crit_chance": 0.20
  },
  "params": {},                     // magnitudes the effect needs that are NOT
                                     // stats the wearer gains (see below).
                                     // Infinity Edge needs none — its numbers
                                     // are all stats. Bramble Vest, by
                                     // contrast, would carry
                                     // {"reflect": 80, "max_attacker_range": 1}
  "effect_id": "infinity_edge_crit_amp", // hook for conditional/on-hit logic
                                          // beyond flat stats; null if the
                                          // item is pure stats
  "radiant_version_of": null,       // set if this IS a radiant upgrade,
                                     // pointing back at the base item id
  "category": "advanced"            // "component" | "advanced" | "artifact"
                                     // | "radiant" | "emblem" | "consumable"
}
```

**`params` vs `stats`** (*added 2026-08-01*). An effect implementation reads
`stats` overlaid with `params`, with `params` winning on key collisions:

- `stats` are bonuses the wearer actually gains, and are applied to derived
  stats whether or not the `effect_id` is implemented. Where an effect's
  magnitude *is* one of those bonuses, it should read the stat directly —
  Spear of Shojin's bonus mana per attack is its `mana: 15` stat.
- `params` carry numbers that are not stats: Bramble Vest's reflected damage,
  Dragon's Claw's magic-damage reduction, a proc chance, a duration. Without
  this field those effects have nowhere to read their numbers from and cannot
  be data-driven at all, which is why the schema was extended. It mirrors
  `AbilityDef.params` and `TraitBreakpoint.params`, which already work this way.
- Setting `params` without an `effect_id` is a validation error — nothing
  would ever read them.

Two further conventions the engine relies on, both chosen to avoid adding more
fields to this schema:

- **Emblems** declare the trait they grant via `effect_id: "emblem_<TraitId>"`
  (e.g. `"emblem_Sniper"`). The loader validates that the trait exists. The
  fetch script must normalise real emblems into this form.
- **Trait breakpoint params** may set the reserved key `targets`, either
  `"trait_members"` (default — the bonus applies only to units with the trait)
  or `"team"` (it applies to the whole board). Any breakpoint param whose key
  names a modelled stat is applied as a flat bonus automatically, so a purely
  statistical trait needs no Python at all.

The `effect_id` / ability `effect_id` fields are intentionally an
indirection layer: the JSON says *which* code hook implements the behavior,
the actual behavior lives in a small Python effects registry
(`engine/effects.py` in the architecture doc) keyed by these ids. This
keeps data files declarative and lets the coding agent implement abilities
incrementally — champions/items without an implemented `effect_id` should
still load and fight with correct stats/auto-attacks, just without their
special ability firing (log a warning, don't crash).

## 3. Current Set 17 ("Space Gods") reference lists

Pulled directly from the LoL Wiki's live Set 17 page (2026-07-31) so the
coding agent has a concrete, correct checklist rather than an invented one.
Use these to sanity-check the fetch script's output — if the champion/trait/
item counts don't roughly match, the parser is misconfigured.

> **Amended 2026-08-01.** Riot's live data disagrees with the wiki on the
> champion count: the fetch script normalises **63** shop units, not the 52
> listed in 3.3 below. The trait lists in 3.1/3.2 do reconcile exactly
> (20 origins + 15 classes = 35 traits, matching the fetch output), and the
> component list in 3.4 matches to the letter. Where the two disagree, Riot's
> payload wins — the wiki page lags balance patches. The lists are still worth
> keeping as an order-of-magnitude check: a parser that emits 12 or 300
> champions is broken regardless of which source is right.

### 3.1 Origins (traits)
Anima, Arbiter, Bulwark, Dark Lady, Dark Star, Doomer, Eradicator,
Factory New, Galaxy Hunter, Gun Goddess, Mecha, Meeple, N.O.V.A., Oracle,
Primordian, Psionic, Redeemer, Space Groove, Stargazer, Timebreaker.

### 3.2 Classes
Bastion, Brawler, Challenger, Commander, Conduit, Divine Duelist,
Fateweaver, Marauder, Party Animal, Replicator, Rogue, Shepherd, Sniper,
Vanguard, Voyager.

### 3.3 Champions (52 total, alphabetical — cost not listed on this page,
pull cost per-champion from the individual champion pages or the CDragon
payload directly)
Aatrox, Akali, Aurelion Sol, Aurora, Bard, Bel'Veth, Blitzcrank, Briar,
Caitlyn, Cho'Gath, Corki, Diana, Ezreal, Fiora, Fizz, Galio, Gnar, Gragas,
Graves, Gwen, Illaoi, Jax, Jhin, Jinx, Kai'Sa, Karma, Kindred, LeBlanc,
Leona, Lissandra, Lulu, Maokai, Master Yi, Meepsie, Milio, Miss Fortune,
Mordekaiser, Morgana, Nami, Nasus, Nunu & Willump, Ornn, Pantheon, Poppy,
Pyke, Rammus, Rek'Sai, Rhaast, Riven, Samira, Shen, Sona, Tahm Kench,
Talon, Teemo, Twisted Fate, Urgot, Veigar, Vex, Viktor, Xayah, Zed, Zoe.

### 3.4 Items — Basic components
B.F. Sword, Chain Vest, Frying Pan, Giant's Belt, Needlessly Large Rod,
Negatron Cloak, Recurve Bow, Sparring Gloves, Spatula, Tear of the Goddess.

### 3.5 Items — Advanced (completed, from 2 components)
Adaptive Helm, Archangel's Staff, Bloodthirster, Blue Buff, Bramble Vest,
Crownguard, Deathblade, Dragon's Claw, Edge of Night, Evenshroud, Gargoyle
Stoneplate, Giant Slayer, Guinsoo's Rageblade, Hand of Justice, Hextech
Gunblade, Infinity Edge, Ionic Spark, Jeweled Gauntlet, Kraken's Fury
(Kraken Slayer-derived, note the in-game display name differs from the
underlying asset name), Last Whisper, Morellonomicon, Nashor's Tooth,
Protector's Vow, Quicksilver, Rabadon's Deathcap, Red Buff, Spear of
Shojin, Spirit Visage, Steadfast Heart, Sterak's Gage, Striker's Flail
(displays as Guardbreaker asset), Sunfire Cape, Tactician's Cape,
Tactician's Crown, Tactician's Shield, Thief's Gloves, Titan's Resolve,
Void Staff, Warmog's Armor.

### 3.6 Items — Craftable trait emblems
Arbiter, Bastion, Brawler, Challenger, Dark Star, Marauder, Meeple,
N.O.V.A., Primordian, Rogue, Shepherd, Space Groove, Stargazer,
Timebreaker, Vanguard, Voyager Emblems.

### 3.7 Items — Uncraftable emblems
Anima, Psionic, Sniper Emblems.

### 3.8 Items — Artifacts (obtained via augments/encounters, not
combination)
Aegis of Dawn, Aegis of Dusk, Ahri's Aura, Blighting Jewel, Cappa Juice,
Dawncore, Death's Defiance, Ekko's Patience, Eternal Pact, Evelynn's
Instinct, Fishbones, Flickerblades, Gambler's Blade, Gold Collector,
Hellfire Hatchet, Hullcrusher, Infinity Force, Lich Bane, Lightshield
Crest, Luden's Tempest, Mittens, Mogul's Mail, Prowler's Claw, Rapid
Firecannon, Seeker's Armguard, Silvermere Dawn, Sniper's Focus, Soraka's
Miracle, Statikk Shiv, Talisman of Ascension, The Indomitable, Thresh's
Lantern, Titanic Hydra, Varus's Obsession, Void Gauntlet, Wit's End,
Yasuo's Bladework, Zhonya's Paradox.

### 3.9 Radiant items
Each advanced item has a Radiant counterpart with a distinct display name
(e.g. Radiant Infinity Edge displays as "Zenith Edge", Radiant Bloodthirster
as "Blessed Bloodthirster") — the wiki lists ~26 radiant items matching most
of the advanced-item list. Map these via `radiant_version_of` back to the
base item id.

### 3.10 Consumables (non-item-slot, encounter/blessing mechanics specific
to Set 17's "God Blessing" theme)
Acceleration Hex, Blessing: Prosperity(+), Blessing: Size, Blessing: Speed,
Blessing: Wealth, Champion Duplicator, Cosmic/Cryogenic/Solar/Starlight/
Storm Hex, Golden Item Remover, Lesser Champion Duplicator, Lucky Item
Chest, Magnetic Remover, Masterwork Upgrade, Mecha-Former, Pocket
Recombobulator, Reforger, Striker Selector, Tiny Champion Duplicator.
Treat these as a separate `consumables.json` if implementing Set 17's
Blessing mechanic (Section 8 of doc 01) — safe to stub/skip for the v1
milestone since they're set-specific event mechanics, not core econ/combat.

## 4. Champion cost tiers and pool sizes (verified, patch 17.8)

| Cost | Pool copies per unique champion (shared across lobby) |
|------|----------------------------------------------------------|
| 1    | 30 |
| 2    | 25 |
| 3    | 18 |
| 4    | 10 |
| 5    | 9  |

Exact per-champion cost assignment (which champions are 1-cost vs 5-cost)
must come from the CDragon payload's `cost` field per champion — don't guess
this from champion "feel," it changes with balance patches. The team-planner
file's `tier` is the same number and makes a good cross-check; the two agreed
on all 63 units when this was last run.

## 4b. `data/config.json` — the constants file

*Added 2026-08-01, closing judgement entry 2.1.* The engine consumes a fifth
data file that earlier revisions of this document did not define. Doc 03
sec 2.7/2.8 requires the shop-odds and XP tables be data rather than code, and
no other file has a home for them.

**The fetch script does not write this file, and must not.** Riot publishes
none of it: searching the entire 26 MB payload for `shopOdds`, `poolSize`,
`xpTable` or `rerollCost` returns zero hits, and `setData` carries only
champions, traits, items and augments. These values are instead
community-documented — stable across sets and heavily datamined — so they are
curated by hand and a re-fetch must never clobber them.

Top-level keys: `shop_odds` (level → 5 probabilities summing to 1.0),
`pool_sizes`, `xp_to_next_level`, `max_level`, `passive_xp_per_round`,
`xp_purchase_gold`, `xp_purchase_amount`, `base_income`, `income_ramp`,
`interest_per_gold`, `interest_cap`, `streak_bonus`, `pvp_win_gold`,
`reroll_cost`, `shop_slots`, `shop_draw_weighting`, `bench_size`,
`max_items_per_unit`, `starting_gold`, `starting_hp`, `role_mana_per_attack`,
`stage_base_damage`, `star_damage_multiplier`, `round_structure`, `combat`,
`augments`, plus two bookkeeping blocks:

- **`provenance`** — classifies every constant as `riot_published` (currently
  empty), `community_documented`, or `engine_artifact` (values with no
  real-world referent at all, like `combat.tick_seconds`). This exists so a
  future maintainer can tell at a glance which numbers a re-fetch could ever
  improve and which are ours forever.
- **`unverified`** — free-text notes naming tables whose exact values are not
  confirmed. The loader logs these at startup, so an approximation can never
  quietly harden into an assumed fact.

The `augments` block schedules augment reveals (doc 01 sec 8):

```json
"augments": { "rounds": [[2,1],[3,2],[4,2]], "tiers": ["silver","gold","prismatic"], "choices": 3 }
```

`rounds` and `tiers` are parallel — the *n*-th reveal offers `choices`
augments of `tiers[n]`. An empty or absent block disables augments entirely,
which is how the frozen starter fixture keeps loading unchanged.

## 4c. `data/augments.json` — **synthetic, not Riot data**

*Added 2026-08-01 at milestone 9.* A list of
`{id, display_name, tier, effect_id, params}`. `tier` is one of
`silver`/`gold`/`prismatic`. As with traits and items, `params` keys naming a
modelled stat are applied board-wide with no code at all, and `effect_id` keys
into `engine.augments.AUGMENT_EFFECTS` for anything that is not a stat.

**This is the one data file not sourced from Riot, and the exception is
deliberate.** The Set 17 CDragon payload carries 43 `TFT17_Augment_*` entries,
but (a) none of them declares a tier — the closest signal is a roman numeral in
the icon path, which resolves for only 30 of the 43 — and (b) they are almost
all bespoke God/carry augments ("Gain a Nasus. Your strongest Nasus becomes an
Attack Fighter with…"), not the flat-stat and econ augments doc 01 sec 8 says
to wire up first. Importing them faithfully would yield 43 augments that all
warn-and-no-op. See docs/99_judgement_calls.md 17.1 for the full survey.

The shipped file is therefore 14 generic archetypes exercising every hook the
system supports. It is labelled `engine_artifact` in `config.json`'s provenance
block and listed under `unverified`. The *system* is complete and general —
importing a real pool is a data edit, not a code change.

The file is required only when `config.augments` schedules reveal rounds, so a
dataset predating the feature still loads.

## 4d. `data/creeps.json` — PvE monsters and creep waves

*Added 2026-08-02 at milestone 10.* An object (not a list) with two keys:

- **`monsters`** — entries in the *champion* schema. Riot publishes these: the
  Set 17 payload carries `TFT17_PVE_Minion` / `_Krug` / `_Raptor` / `_Gromp` /
  `_ElderDragon`, which the `teamplanner` playable-unit filter had been
  excluding. They legitimately break two champion rules — no traits, and
  `max_mana: 0` (they never cast) — so the loader parses them in an `is_creep`
  mode that relaxes exactly those two checks.
- **`waves`** — `{stage, round, display_name, units, loot}`. `units` are
  `{creep_id, row, col}` on the creep half-board. `loot` is a list of weighted
  `{weight, gold, components}` options, one of which is drawn on a win.

Monsters are kept **out of `champions.json` deliberately**: `SharedPool` and
the shop are built from `GameData.champions`, so a creep listed there would
become purchasable.

Wave composition and drop rates are **judgement calls**, not Riot data — see
docs/99_judgement_calls.md 20.2. The monster stats are Riot's.

The file is optional; without it PvE rounds resolve as free wins that drop
nothing, which is how the frozen starter fixture still runs.

## 5. Starter sample dataset (for immediate engine bring-up)

Before running the full fetch, hand-author a **small (~10-15 champion)**
sample slice covering: at least 2 champions per cost tier, 4-5 traits with
at least one 2-breakpoint and one 4-breakpoint trait represented, and
5-8 items covering a mix of stat-only and effect-hook items. This lets the
engine (hex grid, combat loop, econ, shop) be built and smoke-tested end to
end before the full-fidelity data pull is wired in. Keep this sample
data's schema byte-for-byte identical to the full schema above so swapping
in real data later requires no code changes — only a file replacement.

## 6. Versioning

Store a `data/VERSION.json` with `{"set": 17, "patch": "<cdragon path>",
"fetched_at": "<iso timestamp>", "source": "<url>"}` written by the fetch
script, so the engine/RL env can log which data version it trained/ran
against — useful once Set 18 lands and old checkpoints need to be understood
as "Set 17 data."

`patch` records the CDragon path segment that was requested, so it reads
`"latest"` on an unpinned fetch. That is honest but not reproducible: pin a
League patch number (see section 1) when a run needs to be repeatable.
