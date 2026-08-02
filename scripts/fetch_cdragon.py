"""Fetch real Set data from Community Dragon and normalise it into our schema.

Implements doc 02 sec 1.1. Riot's payload is an internal client dump, so every
field mapping in here was derived empirically from the live JSON rather than
from a published schema -- see ``docs/02_data_schema_and_sourcing.md`` sec 1.2
for the shape notes and ``docs/99_judgement_calls.md`` sec 8 for the calls made
where Riot's data does not answer the question.

Usage::

    python scripts/fetch_cdragon.py                      # live fetch, writes data/
    python scripts/fetch_cdragon.py --patch 17.8         # pin a patch
    python scripts/fetch_cdragon.py --dry-run            # report, write nothing
    python scripts/fetch_cdragon.py --source payload.json --teamplanner tp.json

The normalise_* functions are pure (dict in, dict out) so tests can drive them
from a fixture without touching the network.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.schema import ITEM_STAT_KEYS, STAR_LEVELS  # noqa: E402

log = logging.getLogger("fetch_cdragon")

CDRAGON_TFT_URL = "https://raw.communitydragon.org/{patch}/cdragon/tft/en_us.json"
TEAMPLANNER_URL = (
    "https://raw.communitydragon.org/{patch}/plugins/rcp-be-lol-game-data"
    "/global/default/v1/tftchampions-teamplanner.json"
)

# --------------------------------------------------------------------------
# Normalisation tables.
#
# These describe *Riot's encoding*, not game balance, which is why they live in
# the fetch script rather than in a data file: they change when Riot renames an
# internal field, not when a patch retunes a number.
# --------------------------------------------------------------------------

# Star scaling is not in the payload -- Riot ships one scalar per stat and the
# game applies a per-star multiplier. Values per the LoL wiki's TFT:Champion
# page: AD 100/150/225%, health 100/180/324%.
STAR_HEALTH_MULTIPLIER = 1.8
STAR_ATTACK_DAMAGE_MULTIPLIER = 1.5

# Riot's 13 role strings collapsed onto the 5 roles doc 01 sec 3.2 models.
# This drives mana_per_attack, so it feeds combat directly.
ROLE_MAP: Mapping[str, str] = {
    # Riot pairs a damage type (AD/AP/H) with a team role. "Carry" is the
    # payload's name for Marksman and "Reaper" for Assassin.
    "ADCarry": "Marksman",
    "APCarry": "Marksman",
    "HCarry": "Marksman",
    "ADReaper": "Assassin",
    "APReaper": "Assassin",
    "ADFighter": "Fighter",
    "APFighter": "Fighter",
    "HFighter": "Fighter",
    "ADCaster": "Caster",
    "APCaster": "Caster",
    # Riot's sixth team role: "unique champions" that generate resources
    # their own way. Previously folded into Caster, which applied
    # mana-per-attack rules that do not apply to them (doc 99 entry 9.2).
    "ADSpecialist": "Specialist",
    "APSpecialist": "Specialist",
    "HSpecialist": "Specialist",
    "ADTank": "Tank",
    "APTank": "Tank",
}

# Riot item variables that map onto a modelled stat, with the scale needed to
# reach our units. Riot is inconsistent here: ``AD`` is already a fraction
# (0.35 == +35%) while ``AS`` and ``CritChance`` are percentages (35.0 == 35%).
# Anything not listed falls through to ``params`` -- deliberately conservative,
# since guessing the units of an unknown key silently corrupts stats.
ITEM_STAT_MAP: Mapping[str, tuple[str, float]] = {
    "Health": ("health", 1.0),
    "Armor": ("armor", 1.0),
    "MagicResist": ("magic_resist", 1.0),
    "AP": ("ability_power", 1.0),
    "AD": ("attack_damage_pct", 1.0),
    "AS": ("attack_speed_pct", 0.01),
    "CritChance": ("crit_chance", 0.01),
    "DamageAmp": ("damage_amp", 1.0),
    "StatOmnivamp": ("omnivamp", 1.0),
    "Mana": ("mana", 1.0),
}

# The 10 basic components, identified by Riot's own ``component`` tag.
COMPONENT_TAG = "component"

# Origin vs class is not published by Riot. Doc 02 sec 3.1/3.2 lists them from
# the wiki; anything unlisted defaults to "origin" and is reported.
CLASS_TRAITS = frozenset(
    {
        "Bastion", "Brawler", "Challenger", "Commander", "Conduit",
        "Divine Duelist", "Fateweaver", "Marauder", "Party Animal",
        "Replicator", "Rogue", "Shepherd", "Sniper", "Vanguard", "Voyager",
    }
)

# effect_id values we actually implement, keyed by Riot item apiName. Items not
# listed get effect_id null and keep only their stats (doc 02 sec 2: partial
# coverage must still load and fight).
IMPLEMENTED_ITEM_EFFECTS: Mapping[str, str] = {
    "TFT_Item_SpearOfShojin": "spear_of_shojin_bonus_mana_on_attack",
    "TFT_Item_GuinsoosRageblade": "guinsoos_stacking_attack_speed",
}


# --------------------------------------------------------------------------
# Ability classification
#
# Riot names ability variables inconsistently (240 distinct keys across 63
# Set 17 champions: Damage, APDamage, ADDamage, DamageAP, DamageAD, ...), so
# guessing an effect from key names alone is unreliable. The *description*
# carries semantic markup that is far better evidence:
#
#   "...dealing <physicalDamage>@TotalDamage@ (%i:scaleAD%)</physicalDamage>"
#
# The damage-type tag is authoritative and classifies 60 of 63 abilities; the
# other 3 genuinely deal no damage. Structure therefore comes from the markup,
# and only the magnitude lookup falls back on key names -- narrowed by the
# damage type, so a physical ability never picks up an AP variable.
#
# Where the evidence is ambiguous the ability is left unimplemented rather than
# approximated: a wrong ability looks healthy and silently corrupts combat,
# whereas an unimplemented one warns once and no-ops (doc 02 sec 2).
# --------------------------------------------------------------------------

_TAG = re.compile(r"<(\w+)>")
_MARKUP = re.compile(r"<[^>]+>|&nbsp;|@[^@]+@|%i:\w+%")

# Prose cues, checked against the markup-stripped description.
_SHIELD_CUE = re.compile(r"\bshield", re.I)
_HEAL_CUE = re.compile(r"\bheal", re.I)
_STUN_CUE = re.compile(r"\bstun|\bknock ?up|\bstasis", re.I)
_AOE_CUE = re.compile(
    r"\bnearby\b|\bwithin\b|\bhex (?:radius|rift)\b|\ball enemies\b|\bcone\b|\bsplash\b|\barea\b",
    re.I,
)

# Magnitude variables, in preference order, per damage type. Magic abilities
# carry flat damage scaled by AP; physical ones carry a percentage of AD.
_MAGIC_DAMAGE_KEYS = ("Damage", "MagicDamage", "BaseDamage", "DamageAP", "APDamage")
_PHYSICAL_DAMAGE_KEYS = ("ADDamage", "DamageAD", "PhysicalDamage")
_SHIELD_KEYS = ("Shield", "ShieldAmount", "ShieldAP", "BaseShield")
_SHIELD_DURATION_KEYS = ("ShieldDuration", "Duration")
_STUN_DURATION_KEYS = ("StunDuration", "CCDuration", "KnockupDuration")
_SPLASH_RADIUS_KEYS = ("SpellHexRadius", "HexRadius", "HexRange", "HexRadiusBase", "Radius")

# Volley counts. Many abilities fire N projectiles "each dealing X", and
# modelling that as one hit understates a carry by the volley size (entry
# 11.3). Only applied when a count variable *and* an "each"-style cue are both
# present, so a single-hit ability is never silently multiplied.
_HIT_COUNT_KEYS = ("BaseBullets", "NumBullets")
# Riot names volley counts `Num<Projectile>` or `BaseNum<Projectile>`
# (NumShurikens, BaseNumSlashes, BaseNumMissiles, NumProjectiles). Excluded:
# counts of *targets* rather than hits, and any `...Per...` name, which is a
# per-something rate rather than a total (NumProcsPerSimulatedAttack).
_HIT_COUNT_RE = re.compile(
    r"^(?:Base)?Num(?!Targets|Enemies|Allies|Units|Champions|Procs)[A-Z]\w*$"
)
_TARGET_COUNT_KEYS = ("NumTargets", "NumEnemies", "MinimumNumTargets", "NumUnits")
_EACH_CUE = re.compile(r"\beach\b|\bper (?:rocket|arrow|bullet|attack|missile)\b", re.I)
_NEAREST_N = re.compile(r"nearest (\d+)|(\d+) (?:nearby )?(?:targets|enemies)", re.I)


# Fallback magnitude search, for champions whose damage variable is not one of
# the common names (AurelionSol's DamagePerSecond, Chogath's BonusDamage,
# Talon's ADBleedDamage). Names that modify a damage rather than *being* one
# are excluded, and the search only succeeds when exactly one candidate
# remains -- several champions carry three damage variables with nothing to say
# which belongs to the cast (Pyke, Fizz, Sona), and those must stay declined.
_DAMAGE_NAME = re.compile(r"damage", re.I)
_NOT_A_MAGNITUDE = re.compile(
    r"amp|mult|reduction|percent|increase|threshold|ratio|conversion|store|falloff",
    re.I,
)
# A per-second value is a channel: it needs a duration to become a total.
_PER_SECOND = re.compile(r"persecond$", re.I)
# Riot encodes AD scaling in a trailing "AD" (MissileAD, BoltAD).
_AD_SUFFIX = re.compile(r"AD$")
_DURATION_KEYS = ("Duration", "ChannelDuration", "SpellDuration", "TotalSpellTime")


def _sole_damage_param(params: Mapping[str, Any]) -> tuple[str, Any] | None:
    """The champion's one damage variable, or ``None`` if it is not unique."""
    candidates = sorted(
        k
        for k, v in params.items()
        if _DAMAGE_NAME.search(k)
        and not _NOT_A_MAGNITUDE.search(k)
        and isinstance(v, (int, float, list))
    )
    if len(candidates) != 1:
        return None
    return candidates[0], params[candidates[0]]


def _first_param(params: Mapping[str, Any], names: Sequence[str]) -> tuple[str, Any] | None:
    for name in names:
        if name in params:
            return name, params[name]
    return None


def _scaled(value: Any, factor: float) -> Any:
    """Apply a factor to a scalar or to each entry of a per-star list."""
    if isinstance(value, list):
        return [round(float(v) * factor, 4) for v in value]
    return round(float(value) * factor, 4)


def classify_ability(desc: str, params: Mapping[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Pick an ``effect_id`` and canonical params from Riot's description.

    Returns ``(None, {})`` when the evidence does not support a confident
    mapping, which leaves the ability unimplemented on purpose.
    """
    desc = desc or ""
    tags = set(_TAG.findall(desc))
    prose = _MARKUP.sub(" ", desc)

    # A champion with both a passive and an active carries damage numbers for
    # both, and nothing in the payload says which variable belongs to which:
    # the @Var@ references in the text are computed display names that do not
    # resolve back to raw variables. Verified failure -- Kindred's ADDamage
    # (115/175/900% AD) is her *passive*, while her active fires arrows for
    # 75/115/600% AD. Rather than cast the wrong number, decline.
    if "spellPassive" in tags and "spellActive" in tags:
        return None, {}

    if "physicalDamage" in tags:
        damage_type = "physical"
    elif "magicDamage" in tags:
        damage_type = "magic"
    elif "trueDamage" in tags:
        damage_type = "true"
    else:
        damage_type = None

    has_shield = bool(_SHIELD_CUE.search(prose))
    has_heal = bool(_HEAL_CUE.search(prose))
    has_stun = bool(_STUN_CUE.search(prose))
    has_aoe = bool(_AOE_CUE.search(prose))

    canonical: dict[str, Any] = {}

    # -- damage magnitude -------------------------------------------------
    damage_found = False
    flat_physical = False
    magnitude_key: str | None = None
    if damage_type == "physical":
        hit = _first_param(params, _PHYSICAL_DAMAGE_KEYS)
        if hit is None:
            # Riot encodes the scaling type in the suffix: Corki's MissileAD
            # is [28, 42, 280] -- a percentage of AD, exactly like Jinx's
            # ADDamage. These do not contain the word "damage", so the generic
            # fallback below would otherwise miss them and pick up an
            # unrelated variable instead.
            suffixed = sorted(
                k for k, v in params.items()
                if _AD_SUFFIX.search(k) and isinstance(v, (int, float, list))
            )
            if len(suffixed) == 1:
                hit = (suffixed[0], params[suffixed[0]])
        if hit is not None:
            # These are percentages of AD (Briar 120/180/285 == 120% AD).
            canonical["ad_ratio"] = _scaled(hit[1], 0.01)
            damage_found = True
            magnitude_key = hit[0]
        else:
            # No ratio-named variable: a plain damage number on a physical
            # ability is an absolute value, not a share of AD.
            hit = _sole_damage_param(params)
            if hit is not None:
                canonical["damage"] = hit[1]
                canonical["ap_ratio"] = 0.0  # flat: does not scale with AP
                damage_found = True
                flat_physical = True
                magnitude_key = hit[0]
    elif damage_type in ("magic", "true"):
        hit = _first_param(params, _MAGIC_DAMAGE_KEYS) or _sole_damage_param(params)
        if hit is not None:
            canonical["damage"] = hit[1]
            canonical["ap_ratio"] = 1.0
            damage_found = True
            magnitude_key = hit[0]

    # -- shield -----------------------------------------------------------
    shield_found = False
    if has_shield:
        hit = _first_param(params, _SHIELD_KEYS)
        if hit is not None:
            canonical["shield"] = hit[1]
            duration = _first_param(params, _SHIELD_DURATION_KEYS)
            canonical["duration"] = duration[1] if duration else 0
            shield_found = True

    # -- volley size ------------------------------------------------------
    # Both counts are evidence-gated: a count variable alone is not enough,
    # since plenty of abilities carry an unrelated count.
    hits = None
    if damage_found and _EACH_CUE.search(prose):
        hit = _first_param(params, _HIT_COUNT_KEYS)
        if hit is None:
            # Sorted so the pick is deterministic when a champion declares
            # more than one count.
            matches = sorted(
                k for k in params if _HIT_COUNT_RE.match(k) and "Per" not in k
            )
            hit = (matches[0], params[matches[0]]) if matches else None
        if hit is not None:
            hits = hit[1]
    # A channel states damage per second; the total is that times its
    # duration, delivered as one hit per second.
    if hits is None and magnitude_key and _PER_SECOND.search(magnitude_key):
        duration = _first_param(params, _DURATION_KEYS)
        if duration is not None and not isinstance(duration[1], list):
            seconds = int(duration[1])
            if seconds >= 1:
                hits = seconds

    targets = None
    if damage_found:
        hit = _first_param(params, _TARGET_COUNT_KEYS)
        if hit is not None and _NEAREST_N.search(prose):
            targets = hit[1]

    # -- pick the effect --------------------------------------------------
    if damage_found and (hits is not None or targets is not None):
        # A volley is incompatible with the single-hit stun/splash shapes, so
        # it takes precedence: getting the magnitude right matters more than
        # also modelling the rider.
        if hits is not None:
            canonical["hits"] = hits
        if targets is not None:
            canonical["targets"] = targets
        if damage_type == "physical":
            return (
                "flat_physical_damage" if flat_physical else "multi_hit_physical_damage"
            ), canonical
        return "multi_hit_magic_damage", canonical
    if damage_found and has_stun:
        stun = _first_param(params, _STUN_DURATION_KEYS)
        if stun is not None and damage_type != "physical":
            canonical["stun_duration"] = stun[1]
            return "single_target_magic_damage_stun", canonical
    if damage_found and has_aoe and damage_type != "physical":
        radius = _first_param(params, _SPLASH_RADIUS_KEYS)
        if radius is not None:
            canonical["splash_radius"] = radius[1]
            return "splash_magic_damage", canonical
    if damage_found and has_heal and damage_type == "physical":
        # The heal effect is defined as a fraction of damage dealt; only take
        # it when Riot gives an explicit fraction, never invent one.
        heal = _first_param(params, ("HealPercent", "PercentHeal", "Omnivamp"))
        if heal is not None:
            canonical["heal_ratio"] = _scaled(heal[1], 0.01)
            return "single_target_physical_damage_heal", canonical
    if damage_found:
        if damage_type == "physical":
            return (
                "flat_physical_damage" if flat_physical else "single_target_physical_damage"
            ), canonical
        return "single_target_magic_damage", canonical
    if shield_found:
        return "shield_self", canonical
    return None, {}


class FetchError(RuntimeError):
    """Raised when the payload cannot be fetched or is shaped unexpectedly."""


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def fetch_json(url: str, timeout: float = 300.0) -> Any:
    """GET and parse a CDragon document, translating the two failure modes
    that are easy to hit and hard to diagnose into actionable errors."""
    log.info("GET %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "tft_rl/fetch_cdragon"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if resp.status != 200:
                raise FetchError(f"{url} returned HTTP {resp.status}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FetchError(
                f"{url} returned 404. CDragon paths use the *League* patch "
                "number (e.g. '15.16'), not the TFT set or its in-game patch "
                "label -- '17.8' is not a valid path. Use 'latest' unless you "
                "specifically need to pin."
            ) from exc
        raise FetchError(f"{url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc.reason):
            raise FetchError(
                "TLS certificate verification failed. A framework Python "
                "install often ships without a CA bundle -- run this from the "
                "project venv, or run 'Install Certificates.command' from your "
                f"Python installation. ({exc.reason})"
            ) from exc
        raise FetchError(f"could not reach {url}: {exc.reason}") from exc


def select_set(payload: Mapping[str, Any], set_number: int) -> Mapping[str, Any]:
    """Pick the base set entry, excluding PVE/TURBO/PAIRS/event variants.

    ``setData`` holds every historical set plus a variant per game mode; the
    base mutator is exactly ``TFTSet<N>``.
    """
    entries = payload.get("setData")
    if not isinstance(entries, list):
        raise FetchError("payload has no 'setData' list -- CDragon shape changed")
    mutator = f"TFTSet{set_number}"
    for entry in entries:
        if entry.get("mutator") == mutator:
            return entry
    available = sorted({e.get("mutator") for e in entries if e.get("mutator")})
    raise FetchError(f"no setData entry with mutator {mutator!r}; have {available}")


def playable_champion_ids(teamplanner: Mapping[str, Any], set_number: int) -> dict[str, int]:
    """Map ``character_id -> cost`` for units that actually appear in the shop.

    The main payload's champion list also contains PVE monsters and summons
    (Set 17: 83 entries vs 64 real units), and nothing in it distinguishes
    them. The team-planner file lists only shop units, so it is the filter.
    """
    key = f"TFTSet{set_number}"
    entries = teamplanner.get(key)
    if not isinstance(entries, list):
        raise FetchError(
            f"teamplanner has no {key!r} list; have {sorted(teamplanner)}"
        )
    return {e["character_id"]: e["tier"] for e in entries if e.get("character_id")}


def trait_name_to_id(teamplanner: Mapping[str, Any], set_number: int) -> dict[str, str]:
    """Map trait display name -> trait apiName.

    Needed because champions reference traits by display name while the trait
    list is keyed by apiName, and several apiNames share a display name
    (Set 17 has 8 "Stargazer" variants). The team-planner file pairs the two
    unambiguously for the traits that playable units actually carry.
    """
    key = f"TFTSet{set_number}"
    mapping: dict[str, set[str]] = {}
    for champ in teamplanner.get(key) or []:
        for trait in champ.get("traits") or []:
            name, tid = trait.get("name"), trait.get("id")
            if name and tid:
                mapping.setdefault(name, set()).add(tid)
    resolved = {}
    for name, ids in mapping.items():
        if len(ids) > 1:
            log.warning("trait %r maps to multiple ids %s; taking first", name, sorted(ids))
        resolved[name] = sorted(ids)[0]
    return resolved


# --------------------------------------------------------------------------
# Champions
# --------------------------------------------------------------------------


def _num(value: Any, default: float) -> float:
    """Coerce a Riot stat to a number.

    Some entries ship an explicit null for stats that unit does not use
    (Set 17's Miss Fortune has no ``damage``), so ``dict.get(k, default)`` is
    not enough -- the key is present with a null value.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _star_scaled(base: float, multiplier: float) -> list[float]:
    return [round(base * multiplier**i, 2) for i in range(STAR_LEVELS)]


def _ability_params(variables: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce Riot's length-7 variable arrays to per-star triples.

    Indices 1..3 are star levels 1..3. Index 0 is a placeholder, index 4 is an
    unused 4-star slot and 5..6 are padding -- verified across the Set 17
    payload, where 151 of the 168 varying variables rise monotonically over
    exactly indices 1..3.
    """
    params: dict[str, Any] = {}
    for var in variables or []:
        name, value = var.get("name"), var.get("value")
        if not name or not isinstance(value, list) or len(value) < 4:
            continue
        stars = [value[i] for i in (1, 2, 3)]
        if any(v is None for v in stars):
            continue
        rounded = [round(float(v), 4) for v in stars]
        # Collapse to a scalar when the value does not scale with star level,
        # which keeps the data files readable.
        params[name] = rounded[0] if len(set(rounded)) == 1 else rounded
    return params


def normalise_champion(
    entry: Mapping[str, Any],
    *,
    cost: int,
    trait_ids: Mapping[str, str],
    role_mana: Mapping[str, float],
) -> dict[str, Any]:
    stats = entry.get("stats") or {}
    api_name = entry["apiName"]

    role = ROLE_MAP.get(entry.get("role") or "")
    if role is None:
        # One Set 17 unit ships role: null. Range is the best available proxy.
        role = "Fighter" if _num(stats.get("range"), 1) <= 1 else "Caster"
        log.warning("%s has role %r; defaulting to %s", api_name, entry.get("role"), role)

    traits = []
    for name in entry.get("traits") or []:
        tid = trait_ids.get(name)
        if tid is None:
            log.warning("%s references unknown trait %r; dropping it", api_name, name)
            continue
        traits.append(tid)

    ability = entry.get("ability") or {}
    raw_params = _ability_params(ability.get("variables") or [])
    effect_id, canonical = classify_ability(ability.get("desc") or "", raw_params)
    if effect_id is None:
        # Unclassifiable: keep a stable per-champion id so the params survive
        # in the data file and the gap shows up as one warn-once.
        effect_id = f"ability_{api_name}"
    # Raw variables are kept alongside the canonical keys so a future effect
    # implementation has the original numbers to work from.
    ability_params = {**raw_params, **canonical}
    return {
        "id": api_name,
        "display_name": entry.get("name") or api_name,
        "cost": cost,
        "traits": traits,
        "role": role,
        "stats": {
            "health": _star_scaled(_num(stats.get("hp"), 1.0), STAR_HEALTH_MULTIPLIER),
            "armor": _num(stats.get("armor"), 0.0),
            "magic_resist": _num(stats.get("magicResist"), 0.0),
            "attack_damage": _star_scaled(
                _num(stats.get("damage"), 1.0), STAR_ATTACK_DAMAGE_MULTIPLIER
            ),
            "attack_speed": round(_num(stats.get("attackSpeed"), 0.7), 4),
            "attack_range": int(_num(stats.get("range"), 1)),
            "starting_mana": _num(stats.get("initialMana"), 0.0),
            # A few units ship mana 0, meaning "not mana-gated" rather than
            # "casts instantly"; the schema requires a positive pool, so fall
            # back to the usual 100 (see docs/99_judgement_calls.md 8.5).
            "max_mana": _num(stats.get("mana"), 0.0) or 100.0,
            "mana_per_attack": float(role_mana[role]),
            "crit_chance": round(_num(stats.get("critChance"), 0.25), 4),
            "crit_damage": round(_num(stats.get("critMultiplier"), 1.4), 4),
        },
        "ability": {
            "name": ability.get("name") or f"{entry.get('name', api_name)} Ability",
            "cast_mode": "mana",
            "cooldown_seconds": None,
            "effect_id": effect_id,
            "params": ability_params,
        },
    }


# --------------------------------------------------------------------------
# Traits
# --------------------------------------------------------------------------


def normalise_trait(entry: Mapping[str, Any]) -> dict[str, Any]:
    api_name = entry["apiName"]
    display = entry.get("name") or api_name
    breakpoints = []
    for effect in entry.get("effects") or []:
        count = effect.get("minUnits")
        if not isinstance(count, int) or count < 1:
            continue
        params = {
            k: v
            for k, v in (effect.get("variables") or {}).items()
            if v is not None
        }
        breakpoints.append(
            {
                "count": count,
                "effect_id": f"trait_{api_name}_{count}",
                "params": params,
            }
        )
    breakpoints.sort(key=lambda b: b["count"])
    # Duplicate counts would make the highest-tier lookup ambiguous.
    deduped, seen = [], set()
    for bp in breakpoints:
        if bp["count"] in seen:
            log.warning("trait %s has duplicate breakpoint %d; keeping first", api_name, bp["count"])
            continue
        seen.add(bp["count"])
        deduped.append(bp)
    return {
        "id": api_name,
        "display_name": display,
        "category": "class" if display in CLASS_TRAITS else "origin",
        "breakpoints": deduped,
    }


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


def _split_item_effects(
    effects: Mapping[str, Any]
) -> tuple[dict[str, float], dict[str, Any]]:
    """Split Riot's flat effect dict into modelled stats and leftover params."""
    stats: dict[str, float] = {}
    leftovers: dict[str, Any] = {}
    for key, value in (effects or {}).items():
        if value is None:
            continue
        mapped = ITEM_STAT_MAP.get(key)
        if mapped is None:
            leftovers[key] = value
            continue
        our_key, scale = mapped
        if our_key not in ITEM_STAT_KEYS:  # guards against a stale table
            leftovers[key] = value
            continue
        try:
            stats[our_key] = stats.get(our_key, 0.0) + round(float(value) * scale, 4)
        except (TypeError, ValueError):
            leftovers[key] = value
    return stats, leftovers


def normalise_item(
    entry: Mapping[str, Any],
    *,
    category: str,
    emblem_trait_id: str | None = None,
    radiant_of: str | None = None,
) -> dict[str, Any]:
    api_name = entry["apiName"]
    stats, leftovers = _split_item_effects(entry.get("effects") or {})

    if emblem_trait_id is not None:
        effect_id: str | None = f"emblem_{emblem_trait_id}"
    elif api_name in IMPLEMENTED_ITEM_EFFECTS:
        effect_id = IMPLEMENTED_ITEM_EFFECTS[api_name]
    elif leftovers:
        # Riot variables we do not model yet. A stable per-item id keeps the
        # numbers in the data file and makes the gap visible as a single
        # warn-once, rather than silently discarding them; the item's stats
        # still apply regardless (doc 02 sec 2).
        effect_id = f"item_{api_name}"
    else:
        # Nothing to model at all -- an explicit no-op, so the item is not
        # mistaken for an unimplemented effect.
        effect_id = "no_effect"

    # The schema forbids params without an effect_id; emblems read their trait
    # from the effect_id itself and take no params.
    params = leftovers if (leftovers and emblem_trait_id is None) else {}

    return {
        "id": api_name,
        "display_name": entry.get("name") or api_name,
        "is_component": category == "component",
        "category": category,
        "recipe": list(entry.get("composition") or []),
        "unique": bool(entry.get("unique")),
        "stats": stats,
        "effect_id": effect_id,
        "radiant_version_of": radiant_of,
        **({"params": params} if params else {}),
    }


def collect_items(
    payload: Mapping[str, Any],
    set_entry: Mapping[str, Any],
    trait_ids: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Select the craftable item pool: components, advanced items and emblems.

    Radiant/artifact/consumable and set-mechanic items are out of scope for
    now -- they need mechanics the engine does not model.
    """
    by_api = {it["apiName"]: it for it in payload.get("items") or [] if it.get("apiName")}
    set_item_ids = [a for a in (set_entry.get("items") or []) if a in by_api]

    components = {
        a for a in set_item_ids if COMPONENT_TAG in (by_api[a].get("tags") or [])
    }
    out = [normalise_item(by_api[a], category="component") for a in sorted(components)]

    trait_by_display = {name: tid for name, tid in trait_ids.items()}
    for api in sorted(set_item_ids):
        entry = by_api[api]
        recipe = entry.get("composition") or []
        if api in components or len(recipe) != 2:
            continue
        if not all(c in components for c in recipe):
            continue
        name = entry.get("name") or ""
        if name.endswith(" Emblem"):
            # Real emblems ship an empty associatedTraits and an apiName that
            # does not always contain the trait (FavoredEmblemItem is the
            # Arbiter emblem), so the display name is the reliable key.
            trait_display = name[: -len(" Emblem")]
            tid = trait_by_display.get(trait_display)
            if tid is None:
                log.warning("emblem %s names unknown trait %r; skipping", api, trait_display)
                continue
            out.append(normalise_item(entry, category="emblem", emblem_trait_id=tid))
        else:
            out.append(normalise_item(entry, category="advanced"))
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def _backfill_missing_base_stats(champions: list[dict[str, Any]]) -> None:
    """Replace non-positive base health/AD with the median for that cost tier.

    A handful of units ship ``damage: 0`` (Set 17: LeBlanc and Riven) even
    though they clearly auto-attack in game -- their real value presumably
    lives in a system we do not read. Zero AD would make them unable to attack
    or to generate mana, so it cannot be passed through. The cost-tier median
    keeps the substitute in a sensible range and re-derives itself each patch
    rather than baking in a constant.
    """
    for key, multiplier in (
        ("health", STAR_HEALTH_MULTIPLIER),
        ("attack_damage", STAR_ATTACK_DAMAGE_MULTIPLIER),
    ):
        by_cost: dict[int, list[float]] = {}
        for champ in champions:
            base = champ["stats"][key][0]
            if base > 0:
                by_cost.setdefault(champ["cost"], []).append(base)
        for champ in champions:
            if champ["stats"][key][0] > 0:
                continue
            peers = sorted(by_cost.get(champ["cost"]) or [])
            if not peers:
                log.error("%s has no %s and no peers to infer from", champ["id"], key)
                continue
            median = peers[len(peers) // 2]
            log.warning(
                "%s has no base %s; substituting the cost-%d median %.1f",
                champ["id"], key, champ["cost"], median,
            )
            champ["stats"][key] = _star_scaled(median, multiplier)


def build_dataset(
    payload: Mapping[str, Any],
    teamplanner: Mapping[str, Any],
    set_number: int,
    role_mana: Mapping[str, float],
) -> dict[str, list[dict[str, Any]]]:
    set_entry = select_set(payload, set_number)
    costs = playable_champion_ids(teamplanner, set_number)
    trait_ids = trait_name_to_id(teamplanner, set_number)

    # Traits with no breakpoints are placeholders, not real traits (Set 17's
    # "Choose Trait" marker on Miss Fortune). Drop them before champions are
    # normalised so no champion is left referencing one.
    all_traits = [normalise_trait(t) for t in set_entry.get("traits") or []]
    valid_trait_ids = {t["id"] for t in all_traits if t["breakpoints"]}
    for t in all_traits:
        if not t["breakpoints"]:
            log.warning("trait %s has no breakpoints; dropping it", t["id"])

    champions = []
    for entry in set_entry.get("champions") or []:
        api = entry.get("apiName")
        if api not in costs:
            continue
        if not (entry.get("traits") or []):
            # The team-planner list is not purely shop units: Set 17 includes
            # the PVE boss "Apex Primordian" at tier 5. A real shop unit always
            # has at least one trait.
            log.warning("%s has no traits; treating as non-shop unit", api)
            continue
        declared = entry.get("cost")
        if declared is not None and declared != costs[api]:
            log.warning(
                "%s cost disagrees: payload %s vs team-planner tier %s; using tier",
                api, declared, costs[api],
            )
        champion = normalise_champion(
            entry, cost=costs[api], trait_ids=trait_ids, role_mana=role_mana
        )
        champion["traits"] = [t for t in champion["traits"] if t in valid_trait_ids]
        if not champion["traits"]:
            log.warning("%s has no usable traits after filtering; skipping", api)
            continue
        champions.append(champion)
    _backfill_missing_base_stats(champions)
    champions.sort(key=lambda c: (c["cost"], c["id"]))

    # Keep only traits some shop unit can actually field.
    used_trait_ids = {t for c in champions for t in c["traits"]}
    traits = sorted(
        (t for t in all_traits if t["id"] in used_trait_ids), key=lambda t: t["id"]
    )

    items = collect_items(payload, set_entry, trait_ids)
    return {"champions": champions, "traits": traits, "items": items}


def write_dataset(
    dataset: Mapping[str, list[dict[str, Any]]],
    out_dir: Path,
    *,
    set_number: int,
    patch: str,
) -> None:
    for name in ("champions", "traits", "items"):
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(dataset[name], indent=2) + "\n", encoding="utf-8")
        log.info("wrote %s (%d entries)", path, len(dataset[name]))
    version = {
        "set": set_number,
        "patch": patch,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": CDRAGON_TFT_URL.format(patch=patch),
    }
    (out_dir / "VERSION.json").write_text(
        json.dumps(version, indent=2) + "\n", encoding="utf-8"
    )
    log.info("wrote %s", out_dir / "VERSION.json")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", default="latest", help="CDragon patch, e.g. 17.8")
    parser.add_argument("--set", dest="set_number", type=int, default=17)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--source", type=Path, help="local en_us.json instead of fetching")
    parser.add_argument("--teamplanner", type=Path, help="local teamplanner json")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        payload = (
            json.loads(args.source.read_text(encoding="utf-8"))
            if args.source
            else fetch_json(CDRAGON_TFT_URL.format(patch=args.patch))
        )
        teamplanner = (
            json.loads(args.teamplanner.read_text(encoding="utf-8"))
            if args.teamplanner
            else fetch_json(TEAMPLANNER_URL.format(patch=args.patch))
        )
    except (FetchError, OSError, json.JSONDecodeError) as exc:
        log.error("could not load source data: %s", exc)
        return 1

    config = json.loads((args.out / "config.json").read_text(encoding="utf-8"))
    role_mana = config["role_mana_per_attack"]

    try:
        dataset = build_dataset(payload, teamplanner, args.set_number, role_mana)
    except FetchError as exc:
        log.error("%s", exc)
        return 1

    for name, rows in dataset.items():
        log.info("normalised %d %s", len(rows), name)
    if args.dry_run:
        log.info("dry run -- nothing written")
        return 0

    write_dataset(dataset, args.out, set_number=args.set_number, patch=args.patch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
