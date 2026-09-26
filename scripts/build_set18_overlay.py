"""Build the Set 18 magnitude overlay CommunityDragon cannot supply.

Set 18 is TFT's first set on Unreal, and CDragon's payload carries its roster,
ids and base stats but stubs for ability variables, roles and every live
`DA_*` item (doc 99 entry 161.2). The numbers come from three sources, each
incomplete on its own (161.10, 161.11):

* tftraits.com/set18 -- 18.3 tooltip text, roles and trait categories, keyed
  by the CDragon id in each image name. Drops a value silently when it has
  none, rather than printing `?`.
* tactics.tools/info/units -- *named* ability variables with their scaling
  stat, frozen at 18.2.
* The official 18.3 / 18.3b notes -- hand-entered below as `NOTE_DELTAS`,
  applied on top of the 18.2 values.
* vntft.com/items/emblem -- emblem stat lines, an 18.2 snapshot, dated
  forward by `EMBLEM_DELTAS`.
* The official 18.2 notes -- item passive changes, `ITEM_DELTAS`, applied
  only where tactics.tools' current tooltip prints the new value.

Each reconciled value records where it came from: `both` (the 18.2 value is
printed unchanged in the 18.3 text), `notes 18.3` / `notes 18.3b`,
`disagree` (the two sites differ and no note settles it -- flagged, not
resolved) or `single source`.

Usage::

    python scripts/build_set18_overlay.py --out data/set18/overlay.json
    python scripts/build_set18_overlay.py --cache runs/set18_sources --out ...

The parse and reconcile functions are pure (text in, dict out) so tests drive
them from trimmed copies of the real pages.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

log = logging.getLogger("build_set18_overlay")

SOURCES = {
    "tftraits": "https://tftraits.com/set18/",
    "tactics_units": "https://tactics.tools/info/units",
    "tactics_items": "https://tactics.tools/info/items",
    "vntft_emblems": "https://vntft.com/items/emblem",
}


@dataclass(frozen=True)
class Delta:
    """One official note line: `unit`'s variable moved from `old` to `new`."""

    unit: str
    old: tuple[float, ...]
    new: tuple[float, ...]
    patch: str


# Official notes after 18.2, one entry per ability variable the notes change.
# `old` must equal tactics.tools' 18.2 value, which is how the entry finds its
# variable; a delta that matches nothing is reported, never dropped.
NOTE_DELTAS: tuple[Delta, ...] = (
    Delta("DA_Karma18", (120, 180, 270), (125, 185, 300), "18.3"),
    Delta("DA_18_Veigar", (175, 265, 395), (200, 300, 450), "18.3"),
    Delta("DA_18_Veigar", (265, 400, 595), (300, 450, 675), "18.3"),
    Delta("DA_18_Alistar", (200, 260, 320), (230, 300, 400), "18.3"),
    Delta("DA_18_Alistar", (100, 150, 225), (180, 270, 420), "18.3"),
    Delta("DA_Gromp18_AP", (160, 240, 360), (175, 265, 410), "18.3"),
    Delta("DA_Murkwolf18", (60, 90, 135), (65, 100, 160), "18.3"),
    Delta("DA_18_Warwick", (215, 325, 500), (230, 345, 535), "18.3"),
    Delta("DA_18_Warwick", (0.2, 0.2, 0.2), (0.25, 0.25, 0.25), "18.3"),
    Delta("DA_18_Azir", (43, 65, 103), (46, 69, 110), "18.3"),
    Delta("DA_18_Cassiopeia", (400, 600, 950), (425, 630, 1020), "18.3"),
    Delta("DA_18_Rammus", (350, 450, 550), (400, 550, 725), "18.3"),
    Delta("DA_18_Lillia", (325, 475), (350, 525), "18.3"),
    Delta("DA_Nidalee18_AP", (300, 450), (330, 500), "18.3"),
    Delta("DA_Taric18", (100, 225), (75, 150), "18.3"),
    Delta("DA_Taric18", (250, 375), (275, 450), "18.3"),
    Delta("DA_18_KhaZix", (285, 400, 580), (265, 370, 535), "18.3b"),
    Delta("DA_18_KhaZix", (310, 445, 660), (285, 410, 605), "18.3b"),
)

# tactics.tools stat label -> (Riot effect key, factor into Riot's units).
# Riot's units are what `fetch_cdragon._split_item_effects` already expects:
# AD and omnivamp as fractions, AS and crit as percentages.
ITEM_STAT_LABELS: Mapping[str, tuple[str, float]] = {
    "Attack damage": ("AD", 0.01),
    "Ability power": ("AP", 1.0),
    "Armor": ("Armor", 1.0),
    "Magic resist": ("MagicResist", 1.0),
    "Health": ("Health", 1.0),
    "Attack speed": ("AS", 1.0),
    "Critical strike change": ("CritChance", 1.0),
    "Omnivamp": ("StatOmnivamp", 0.01),
    "Damage Amplification": ("DamageAmp", 0.01),
    "Mana Regen": ("ManaRegen", 1.0),
    "Mana": ("Mana", 1.0),
}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


# --------------------------------------------------------------------------
# tftraits
# --------------------------------------------------------------------------


def parse_tftraits_champions(page: str) -> dict[str, dict[str, Any]]:
    """Every champion panel, keyed by the lower-cased CDragon apiName."""
    out: dict[str, dict[str, Any]] = {}
    for block in re.split(r'(?=<div id="champ-)', page)[1:]:
        img = re.search(r"/champions/([a-z0-9_]+)\.png", block)
        if not img:
            continue
        sub = re.search(r'<div class="sub muted">(.*?)</div></div></div>', block, re.S)
        role_label = _text(sub.group(1)).split("·")[-1].strip() if sub else ""
        ability = re.search(r'<p class="set18-ability-name">(.*?)</p>', block, re.S)
        texts = re.findall(r'<p class="muted trait-desc">(.*?)</p>', block, re.S)
        stats = re.findall(r'<p class="muted">(.*?)</p>', block, re.S)
        mana = re.search(r"(\d+)/(\d+) Mana", _text(stats[-1])) if stats else None
        out[img.group(1)] = {
            "role": role_label.replace(" ", ""),
            "ability": _text(ability.group(1)) if ability else None,
            "text": " | ".join(_text(t) for t in texts),
            "mana": [int(mana.group(1)), int(mana.group(2))] if mana else None,
        }
    return out


def parse_tftraits_traits(page: str) -> dict[str, dict[str, Any]]:
    """Every trait section: its class/origin category and per-tier text."""
    out: dict[str, dict[str, Any]] = {}
    for block in re.split(r'(?=<[a-z]+ [^>]*id="trait-)', page)[1:]:
        img = re.search(r"/traits/([a-z0-9_]+)\.png", block)
        kind = re.search(r'<span class="muted set18-kind">(\w+)</span>', block)
        if not img or not kind:
            continue
        tiers = {
            int(count): _text(desc)
            for count, desc in re.findall(
                r'<span class="units"[^>]*>(\d+)</span><span class="trait-desc">(.*?)</span>',
                block, re.S,
            )
        }
        out[img.group(1)] = {"category": kind.group(1), "tiers": tiers}
    return out


# --------------------------------------------------------------------------
# tactics.tools
# --------------------------------------------------------------------------


def parse_tactics_units(page: str) -> dict[str, dict[str, Any]]:
    """Unit cards: ability name, mana and the named variable rows."""
    out: dict[str, dict[str, Any]] = {}
    for card in re.split(r'(?=<div class=" rounded text-white1 w-\[291px\])', page)[1:]:
        uid = re.search(r"/img/ability/([A-Za-z0-9_]+)\.jpg", card)
        if not uid:
            continue
        parts = card.split('<hr class="my-[10px] mx-1 border-white2"/>')
        variables = []
        if len(parts) > 1:
            body = parts[1].split('<div class="MuiTabs-root')[0]
            rows = re.findall(
                r'<div class="flex flex-wrap justify-between">(.*?)</span></div></div>', body, re.S
            )
            for row in rows:
                label = re.search(r"<span>([^<:]+):\s*</span>", row)
                stars = re.search(r"\[(.*?)\]", _text(row).replace(" ", ""))
                if not (label and stars):
                    continue
                variables.append({
                    "name": label.group(1).strip(),
                    "stars": [float(v) for v in _NUM.findall(stars.group(1))],
                    "scales": sorted(set(re.findall(r'alt="([^"]+)" width="14"', row))),
                })
        name = re.search(r'<div class="font-medium text-sm">(.*?)</div>', card)
        out[uid.group(1)] = {
            "ability": _text(name.group(1)) if name else None,
            "variables": variables,
        }
    return out


def parse_tactics_items(page: str) -> dict[str, dict[str, Any]]:
    """Item cards as Riot-style `effects` plus the tooltip text."""
    out: dict[str, dict[str, Any]] = {}
    for card in re.split(r'(?=<div class="p-4 rounded text-white1)', page)[1:]:
        head = re.search(
            r'alt="([^"]+)" src="https://ap\.tft\.tools/img/items_s14/([A-Za-z0-9_]+)\.png\?w=36"',
            card,
        )
        if not head:
            continue
        top = card.split('<div class="flex items-center ml-auto">')[0]
        statline = re.search(r'<div class="leading-tight text-\[13px\]">(.*)', top, re.S)
        effects: dict[str, float] = {}
        unknown: list[str] = []
        if statline:
            pending = None
            for value, label in re.findall(r"<span>([^<]*)</span>|alt=\"([^\"]+)\"", statline.group(1)):
                number = _NUM.search(value) if value else None
                if number:
                    pending = float(number.group())
                elif label and pending is not None:
                    key = ITEM_STAT_LABELS.get(label)
                    if key is None:
                        unknown.append(label)
                    else:
                        effects[key[0]] = round(pending * key[1], 4)
                    pending = None
        desc = re.search(r'<div class="leading-tight text-sm leading-tight">(.*?)</div></div>', card, re.S)
        out[head.group(2)] = {
            "name": html.unescape(head.group(1)),
            "effects": effects,
            "desc": _text(desc.group(1)) if desc else "",
            **({"unknown_stats": unknown} if unknown else {}),
        }
    return out


@dataclass(frozen=True)
class ItemDelta:
    item: str
    key: str  # the Riot passive variable, as the legacy twin names it
    old: float  # the twin's value; recorded for provenance, not matched
    new: float
    patch: str


# 18.2 changes to item *passives* (doc 99 entry 161.11). tactics.tools gives
# the current stat line but not the passive's variables, which the fetcher
# takes from the pre-18.2 legacy twin; these date that twin forward.
ITEM_DELTAS: tuple[ItemDelta, ...] = (
    ItemDelta("DA_Bloodthirster", "HealthThreshold", 40.0, 50.0, "18.2"),
    ItemDelta("DA_Bloodthirster", "ShieldHealthPercent", 25.0, 30.0, "18.2"),
    ItemDelta("DA_EdgeOfNight", "HealthThreshold", 60.0, 40.0, "18.2"),
    ItemDelta("DA_EdgeOfNight", "MissingHealthRestore", 0.2, 0.15, "18.2"),
    ItemDelta("DA_HandOfJustice", "AD_NotStatBar", 0.15, 0.18, "18.2"),
    ItemDelta("DA_HandOfJustice", "AP_NotStatBar", 15.0, 18.0, "18.2"),
    ItemDelta("DA_HandOfJustice", "StatOmnivamp_NotStatBar", 0.12, 0.15, "18.2"),
)


@dataclass(frozen=True)
class TraitDelta:
    trait: str
    count: int
    key: str  # Riot's variable name, as the fetcher restores it from its hash
    old: float  # CDragon's value; the fetcher refuses the delta if it differs
    new: float
    patch: str


# CDragon's trait numbers are a mixed snapshot: some 18.2 changes are in it
# (Hunter's 3s, Blackthorn's health, Solar's 8%), some are not (Rapidfire,
# Solar's resists), and none of 18.3's (doc 99 entry 161.15). Each line is the
# official notes, and each new value must also be printed in tftraits' 18.3
# tier text, which 161.10 found agrees with the notes 8 of 8.
TRAIT_DELTAS: tuple[TraitDelta, ...] = (
    TraitDelta("DA_18_Hunter", 4, "HunterAD", 0.45, 0.40, "18.3"),
    TraitDelta("DA_18_Hunter", 5, "HunterAD", 0.65, 0.60, "18.3"),
    TraitDelta("DA_18_Rapidfire", 4, "ASperAttack", 0.09, 0.08, "18.2"),
    TraitDelta("DA_18_Rapidfire", 5, "ASperAttack", 0.15, 0.12, "18.2"),
    TraitDelta("DA_18_Coven", 3, "EssencePerLoss", 18.0, 22.0, "18.3"),
    TraitDelta("DA_18_Coven", 4, "EssencePerLoss", 25.0, 28.0, "18.3"),
    TraitDelta("DA_18_Coven", 5, "EssencePerLoss", 32.0, 35.0, "18.3"),
    TraitDelta("DA_18_Defender", 6, "DefenderDefenseGain", 120.0, 115.0, "18.3"),
    TraitDelta("DA_18_Inferno", 5, "HPBurnPerSecond", 3.5, 3.0, "18.3"),
    TraitDelta("DA_18_Inferno", 7, "HPBurnPerSecond", 4.5, 4.0, "18.3"),
    # The notes give 3/4/6/9 => 3/4/6/8; CDragon's 2/3/5/8 is neither, so its
    # lower tiers are dated to the notes' 18.3 values.
    TraitDelta("DA_18_Invoker", 2, "InvokerManaBonus", 2.0, 3.0, "18.3"),
    TraitDelta("DA_18_Invoker", 3, "InvokerManaBonus", 3.0, 4.0, "18.3"),
    TraitDelta("DA_18_Invoker", 4, "InvokerManaBonus", 5.0, 6.0, "18.3"),
    TraitDelta("DA_18_Solar", 3, "Threshold1ArmorMagicResist", 15.0, 12.0, "18.2"),
)

# Where tftraits and CDragon disagree and no note settles it: CDragon's value
# is kept, and the disagreement travels with the data rather than being
# resolved by guess. (trait, count, key, CDragon, tftraits, why kept)
TRAIT_DISPUTES: tuple[tuple[str, int, str, float, float, str], ...] = (
    ("DA_Juggernaut18", 4, "TeamDurability", 0.06, 0.04,
     "tftraits prints 4% at both 2 and 4; no note from 18.1 to 18.3 changes it"),
    ("DA_18_Blackthorn", 4, "StatMultiplier", 0.3, 0.0,
     "tftraits prints 0%; the 18.3 notes say Blackthorn's tooltip shows wrong stats"),
    ("DA_18_Sprykin", 5, "TeamwideRatio", 0.5, 0.0,
     "tftraits prints 0% at 5 and 100% at 7; no note changes it"),
)


def apply_trait_deltas(
    traits: Mapping[str, Mapping[str, Any]], deltas: Iterable[TraitDelta]
) -> dict[str, dict[str, Any]]:
    """Attach each delta to its trait, if the 18.3 tier text prints the new value."""
    out = {tid: dict(t) for tid, t in traits.items()}
    for d in deltas:
        trait = out.get(d.trait.lower())
        tiers = (trait or {}).get("tiers") or {}
        text = tiers.get(d.count) or tiers.get(str(d.count)) or ""
        if trait is None or not _printed([d.new], text):
            log.warning("trait delta %s %d %s %s->%s is not in the 18.3 text; skipped",
                        d.trait, d.count, d.key, d.old, d.new)
            continue
        trait.setdefault("deltas", []).append(
            {"count": d.count, "key": d.key, "old": d.old, "new": d.new,
             "source": f"notes {d.patch}"})
    for tid, count, key, cdragon, text_value, why in TRAIT_DISPUTES:
        if tid.lower() in out:
            out[tid.lower()].setdefault("disputed", []).append(
                {"count": count, "key": key, "kept": cdragon, "tftraits": text_value, "why": why})
    return out


def apply_item_deltas(
    items: Mapping[str, Mapping[str, Any]], deltas: Iterable[ItemDelta]
) -> dict[str, dict[str, Any]]:
    """Add each delta's new value to its item's effects, as a passive variable.

    Applied only when the current tooltip prints the new value too, so every
    passive value in the overlay has two sources; one it does not print warns.
    """
    out = {iid: {**it, "effects": dict(it["effects"])} for iid, it in items.items()}
    for d in deltas:
        item = out.get(d.item)
        if item is None or not _printed([d.new], item.get("desc", "")):
            log.warning("item delta %s %s %s->%s is not in the current text; skipped",
                        d.item, d.key, d.old, d.new)
            continue
        item["effects"][d.key] = d.new
        item["passive_source"] = f"notes {d.patch}"
    return out


# --------------------------------------------------------------------------
# vntft emblems
# --------------------------------------------------------------------------

# Emblem stat-line wording -> (Riot effect key, factor into Riot's units).
EMBLEM_STAT_WORDS: Mapping[str, tuple[str, float]] = {
    "AD": ("AD", 0.01),
    "AP": ("AP", 1.0),
    "Health": ("Health", 1.0),
    "Armor": ("Armor", 1.0),
    "MR": ("MagicResist", 1.0),
    "Magic Resist": ("MagicResist", 1.0),
    "AS": ("AS", 1.0),
    "Attack Speed": ("AS", 1.0),
    "Critical Strike Chance": ("CritChance", 1.0),
    "Mana regeneration": ("ManaRegen", 1.0),
}

# 18.3 changes to an emblem's *stat* line. Changes to an emblem's passive
# (Hunter's per-takedown AD, Juggernaut's mana on death) live in its text and
# belong to the engine's emblem work, not to these numbers.
EMBLEM_DELTAS: tuple[tuple[str, str, float, float, str], ...] = (
    ("Invoker Emblem", "ManaRegen", 3.0, 2.0, "18.3"),
    ("Hunter Emblem", "TakedownAD", 0.18, 0.15, "18.3"),
)

# The numbers in each emblem's passive text, as parameters its engine hook
# reads (doc 99 entry 161.14). CDragon stubs Set 18's variables, so Riot's
# names are unknown and these are ours. Each value must also be printed in
# vntft's text or it is skipped; an 18.3 change goes in `EMBLEM_DELTAS`.
EMBLEM_PASSIVES: Mapping[str, Mapping[str, float]] = {
    "Brawler Emblem": {"MaxHealthMagicDamage": 0.025},
    "Executioner Emblem": {"ExecuteThreshold": 0.08},
    "Hunter Emblem": {"TakedownAD": 0.18},
    "Invoker Emblem": {"ManaSpentToAP": 0.08},
    "Rapidfire Emblem": {"TargetMaxHealthTrueDamage": 0.01},
    "Ravager Emblem": {"AmpPerStep": 0.03, "HealingPerStep": 300.0},
    "Spellweaver Emblem": {"ManaOnAllyCast": 2.0},
    "Vanguard Emblem": {"SurviveSeconds": 22.0, "PlayerHealth": 1.0},
}


def parse_vntft_emblems(page: str) -> dict[str, dict[str, Any]]:
    """Emblems by display name: stat lines as Riot effect keys, plus the text."""
    out: dict[str, dict[str, Any]] = {}
    for block in re.split(r'(?=<li class="list_search)', page)[1:]:
        name = re.search(r'href="#">([^<]+ Emblem)</a>', block)
        if not name:
            continue
        effects: dict[str, float] = {}
        unparsed: list[str] = []
        for line in re.findall(r"<li>\s*\+(.*?)</li>", block, re.S):
            line = _text(line)
            match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%?\s*(.+)", line)
            key = EMBLEM_STAT_WORDS.get(match.group(2).strip()) if match else None
            if key is None:
                unparsed.append(line)
                continue
            effects[key[0]] = round(float(match.group(1)) * key[1], 4)
        paragraphs = re.findall(r"<p>(?!<img|<ul)(.*?)</p>", block, re.S)
        out[html.unescape(name.group(1))] = {
            "effects": effects,
            "desc": " ".join(_text(p) for p in paragraphs if _text(p)),
            **({"unparsed": unparsed} if unparsed else {}),
        }
    return out


def add_emblem_passives(
    emblems: Mapping[str, Mapping[str, Any]],
    passives: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, Any]]:
    """Add each passive's parameters to its emblem's effects, if the text agrees."""
    out = {name: {**e, "effects": dict(e["effects"])} for name, e in emblems.items()}
    for name, params in passives.items():
        emblem = out.get(name)
        if emblem is None:
            continue
        for key, value in params.items():
            if not _printed([value], emblem.get("desc", "")):
                log.warning("emblem passive %s %s=%s is not in its text; skipped", name, key, value)
                continue
            emblem["effects"][key] = value
    return out


def apply_emblem_deltas(
    emblems: Mapping[str, Mapping[str, Any]],
    deltas: Iterable[tuple[str, str, float, float, str]],
) -> dict[str, dict[str, Any]]:
    """Date vntft's 18.2 snapshot forward; a delta that does not match warns."""
    out = {name: {**e, "effects": dict(e["effects"]), "source": "vntft 18.2"}
           for name, e in emblems.items()}
    for name, key, old, new, patch in deltas:
        emblem = out.get(name)
        if emblem is None or emblem["effects"].get(key) != old:
            log.warning("emblem delta %s %s %s->%s matched nothing", name, key, old, new)
            continue
        emblem["effects"][key] = new
        emblem["source"] = f"notes {patch}"
    return out


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _renderings(stars: Sequence[float]) -> list[str]:
    """The ways a per-star list appears in tftraits' text."""
    forms = ["/".join(_fmt(v) for v in stars)]
    if max(stars) < 30:  # a ratio, printed as a percentage
        forms.append("/".join(_fmt(round(v * 100, 2)) for v in stars))
    if len(set(stars)) == 1:  # constant across stars, printed once
        forms += [_fmt(stars[0]), f"{_fmt(round(stars[0] * 100, 2))}%"]
    return forms


def _printed(stars: Sequence[float], text: str) -> bool:
    return any(re.search(rf"(?<![\d./]){re.escape(f)}(?![\d/])", text) for f in _renderings(stars))


def _near_miss(stars: Sequence[float], text: str) -> list[float] | None:
    """A per-star list in `text` that agrees with `stars` on all but one star."""
    for match in re.findall(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?){2}", text):
        other = [float(v) for v in match.split("/")]
        if len(other) == len(stars[:3]) and sum(
            a != b for a, b in zip(other, stars[:3], strict=True)
        ) == 1:
            return other
    return None


def reconcile(
    units: Mapping[str, Mapping[str, Any]],
    champions: Mapping[str, Mapping[str, Any]],
    deltas: Iterable[Delta],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Name every variable from tactics.tools and date it to 18.3 or later."""
    deltas = list(deltas)
    used: set[Delta] = set()
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for uid, unit in units.items():
        text = (champions.get(uid.lower()) or {}).get("text", "")
        values: dict[str, dict[str, Any]] = {}
        for var in unit["variables"]:
            stars = [float(v) for v in var["stars"][:3]]
            entry: dict[str, Any] = {"scales": var["scales"]}
            delta = next(
                (d for d in deltas if d.unit == uid
                 and tuple(round(s, 4) for s in stars[: len(d.old)]) == d.old),
                None,
            )
            if delta is not None:
                used.add(delta)
                entry.update(stars=list(map(float, delta.new)) + stars[len(delta.new):],
                             source=f"notes {delta.patch}")
            elif text and _printed(stars, text):
                entry.update(stars=stars, source="both")
            elif text and (alt := _near_miss(stars, text)) is not None:
                entry.update(stars=stars, source="disagree", alternative=alt)
            else:
                entry.update(stars=stars, source="single source")
            values[var["name"]] = entry
        out[uid] = values
    for delta in deltas:
        if delta not in used:
            log.warning("note delta for %s %s matched no 18.2 variable", delta.unit, delta.old)
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def _load(name: str, cache: Path | None) -> str:
    if cache is not None and (cache / f"{name}.html").exists():
        return (cache / f"{name}.html").read_text(encoding="utf-8")
    req = urllib.request.Request(SOURCES[name], headers={"User-Agent": "Mozilla/5.0 tft_rl"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        page = resp.read().decode("utf-8", "ignore")
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{name}.html").write_text(page, encoding="utf-8")
    return page


def build(pages: Mapping[str, str]) -> dict[str, Any]:
    champions = parse_tftraits_champions(pages["tftraits"])
    units = parse_tactics_units(pages["tactics_units"])
    return {
        "provenance": {
            "_comment": (
                "Set 18 magnitudes CDragon does not ship (doc 99 entry 161.12). "
                "Built by scripts/build_set18_overlay.py; never hand-edit."
            ),
            "sources": dict(SOURCES),
            "note_deltas": [f"{d.unit} {d.old}->{d.new} ({d.patch})" for d in NOTE_DELTAS],
            "item_deltas": [f"{d.item} {d.key} {d.old}->{d.new} ({d.patch})" for d in ITEM_DELTAS],
            "trait_deltas": [f"{d.trait} {d.count} {d.key} {d.old}->{d.new} ({d.patch})"
                             for d in TRAIT_DELTAS],
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "champions": {
            uid: {**champions.get(uid.lower(), {}), "variables": variables}
            for uid, variables in reconcile(units, champions, NOTE_DELTAS).items()
        },
        "traits": apply_trait_deltas(parse_tftraits_traits(pages["tftraits"]), TRAIT_DELTAS),
        "items": apply_item_deltas(parse_tactics_items(pages["tactics_items"]), ITEM_DELTAS),
        "emblems": apply_emblem_deltas(
            add_emblem_passives(parse_vntft_emblems(pages["vntft_emblems"]), EMBLEM_PASSIVES),
            EMBLEM_DELTAS,
        ),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, help="read/write raw pages here")
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    overlay = build({name: _load(name, args.cache) for name in SOURCES})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(overlay, indent=1) + "\n", encoding="utf-8")
    sources: dict[str, int] = {}
    for champion in overlay["champions"].values():
        for value in champion["variables"].values():
            sources[value["source"]] = sources.get(value["source"], 0) + 1
    log.info("wrote %s: %d champions, %d traits, %d items; variables by source %s",
             args.out, len(overlay["champions"]), len(overlay["traits"]),
             len(overlay["items"]), sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
