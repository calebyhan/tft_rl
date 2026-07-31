# TFT Data Schema & Sourcing Guide

Purpose: defines the clean JSON schema the engine consumes, and how to get
real, current Set 17 (Space Gods, patch 17.8) data into that schema. This
part of the project *will* go stale — re-run the fetch when Set 18
(Enchanted Wilds, launching 2026-08-26) goes live, or any time you want to
re-sync with balance patches.

Important constraint: the data-fetch step must run on a machine with normal
internet access (it can't run from this sandbox, which is locked to package
registries + GitHub). The coding agent building this should implement the
fetch/normalize script per the spec below and run it locally / in CI, not
try to hit communitydragon.org from a locked-down sandbox.

## 1. Source of truth: Community Dragon (CDragon)

CDragon publishes Riot's TFT game data as JSON, rebuilt from client/LCU
files (not officially maintained by Riot, but the de facto standard source
the whole TFT tooling community uses).

Key endpoints (replace `latest` with a specific patch number like `17.8` to
pin a version instead of always tracking newest):

- `https://raw.communitydragon.org/latest/cdragon/tft/en_us.json`
  — the main combined file: champions, traits, items, and augments in one
  document, in Riot's native (somewhat messy) internal shape. This is the
  best single source — richer than the individual ddragon files.
- `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/tftchampions-teamplanner.json`
  — champion ID list per set, used for things like team-planner codes; not
  needed for core data but useful for champion ID <-> display-name mapping
  sanity checks.
- Data Dragon (`ddragon.leagueoflegends.com`) also publishes simplified
  `tft-champion.json`, `tft-item.json`, `tft-augments.json` files, but Riot's
  own docs note ddragon's spell/stat data is **less accurate** than what
  CDragon derives — prefer CDragon as primary source, use ddragon only for
  quick sanity cross-checks or image asset paths.

### 1.1 Fetch script responsibilities (implement as `scripts/fetch_cdragon.py`)
1. GET the `cdragon/tft/en_us.json` file for a pinned patch (default to
   `latest` if none specified).
2. The file's top-level shape (verify against the live payload, this can
   shift) generally groups data under keys like `sets` (map of set number ->
   champions/traits for that set), `items`. Filter to the target set number
   (Set 17 = key likely `"17"` or similar under `sets`) since the file
   contains historical sets too.
3. Normalize each champion entry into the Champion Def schema (Section 2)
   — this means renaming/reshaping Riot's internal field names
   (`apiName`, `stats.hp`, `stats.damage`, `ability.variables`, etc. — exact
   field names must be inspected directly from the fetched payload since
   they aren't publicly documented in a stable schema) into the clean shape
   below.
4. Normalize traits and items the same way into their Def schemas.
5. Write output to `data/champions.json`, `data/traits.json`,
   `data/items.json` in this repo, overwriting the sample/starter data.
6. Log any champion/trait/item that failed to parse rather than silently
   dropping it, so gaps are visible.

Because Riot's raw internal JSON field names are not stable/documented and
must be discovered empirically from the live payload, budget real
iteration time for this script — expect to inspect the actual fetched JSON
structure and adjust field mappings rather than trusting a fixed field list
written from memory.

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
  "effect_id": "infinity_edge_crit_amp", // hook for conditional/on-hit logic
                                          // beyond flat stats; null if the
                                          // item is pure stats
  "radiant_version_of": null,       // set if this IS a radiant upgrade,
                                     // pointing back at the base item id
  "category": "advanced"            // "component" | "advanced" | "artifact"
                                     // | "radiant" | "emblem" | "consumable"
}
```

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

Exact per-champion cost assignment (which of the 52 champions above are
1-cost vs 5-cost) must come from the CDragon payload's `cost` field per
champion — don't guess this from champion "feel," it changes with balance
patches.

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

Store a `data/VERSION.json` with `{"set": 17, "patch": "17.8", "fetched_at":
"<iso timestamp>"}` written by the fetch script, so the engine/RL env can
log which data version it trained/ran against — useful once Set 18 lands
and old checkpoints need to be understood as "Set 17 data."
