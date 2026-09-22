"""Fetch real TFT ranked matches from Riot's match-v1 API.

The reference side of the fidelity comparison doc 99 entry 96.5 asks for.
Every ceiling and every mispricing measured in this project so far has been
judged against the engine's own economy and the engine's own combat; entry 76
priced a 3-star against the engine's combat, which structurally cannot detect
an error in the constants `data/config.json` flags as `engine_artifact`. Real
match data is the only comparator outside that loop.

**What the API can and cannot give.** `/tft/match/v1/matches/{id}` returns
*end-of-game state per participant* -- no per-round trajectory. There is no
reference counterpart to `scripts/engine_profile.py`'s living-player table of
"gold at 4-3". What there is instead is a cross-section: a participant with
`last_round = R` shows their level, gold and board *at R*, because that is when
they died. `scripts/reference_profile.py` reduces that; `engine_profile.py`
grew a matching at-elimination view so the two sides are conditioned the same
way. Comparing a living-player mean against a dying-player cross-section would
be a mismatched comparison wearing a table.

Usage::

    echo 'RIOT_KEY=RGAPI-...' >> .env       # gitignored; see .env.example
    python scripts/fetch_riot_matches.py --band challenger --matches 1000
    python scripts/fetch_riot_matches.py --band diamond --matches 1000

Writes ``data/reference/matches_<band>_<date>.json`` -- a *subset* of each
match, plus a provenance block recording region, band, queue, set filter and
fetch date. It never writes anything the engine loads, and in particular never
`data/config.json` (doc 99 sec 2.1).

Resumable: re-running with the same band and date appends only matches not
already in the file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

REFERENCE_DIR = REPO_ROOT / "data" / "reference"

# Ranked Standard. Hyper Roll (1130), Double Up (1160) and the rotating modes
# have different round structures and player counts, so letting them into the
# sample would silently corrupt every elimination-round and game-length figure
# without changing anything that looks wrong.
RANKED_STANDARD_QUEUE = 1100

# match-v1 is on the regional routing hosts; league-v1 is on the platform ones.
REGIONAL_HOST = "https://{region}.api.riotgames.com"
PLATFORM_HOST = "https://{platform}.api.riotgames.com"

# The apex tiers are single-page endpoints; everything below is paged by
# tier+division. Keys are what `--band` accepts.
APEX_BANDS = {
    "challenger": "challenger",
    "grandmaster": "grandmaster",
    "master": "master",
}
# Riot's edge sits behind Cloudflare, which rejects urllib's default
# `Python-urllib/3.12` signature with a 403 carrying `error code: 1010` -- an
# *edge* error, not Riot's JSON `{"status": {...}}` 403. Read as an auth
# failure it sends you off regenerating a perfectly good key. Any ordinary
# User-Agent passes.
USER_AGENT = "tft-rl-research/0.1 (+https://github.com/; stdlib urllib)"

DIVISION_BANDS = {
    "diamond": ("DIAMOND", "I"),
    "emerald": ("EMERALD", "I"),
    "platinum": ("PLATINUM", "I"),
    "gold": ("GOLD", "I"),
    "silver": ("SILVER", "I"),
}


def read_api_key() -> str:
    """The Riot key, from the environment or the gitignored `.env`.

    Stdlib only, matching `fetch_cdragon.py`'s no-dependency precedent -- one
    `KEY=value` per line, `#` comments and blanks skipped. A real environment
    variable wins over the file.
    """
    for name in ("RIOT_KEY", "RIOT_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() in ("RIOT_KEY", "RIOT_API_KEY"):
                return value.strip().strip("'\"")
    return ""


class RateLimiter:
    """Token bucket honouring both of a development key's published limits.

    20 requests/second and 100 requests/2 minutes. The second one binds for any
    run long enough to matter, and exceeding it costs a 429 plus a penalty
    window, so it is cheaper to wait than to discover it.
    """

    def __init__(self, per_second: int = 20, per_two_minutes: int = 100) -> None:
        self.limits = [(per_second, 1.0), (per_two_minutes, 120.0)]
        self.history: deque[float] = deque()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self.history and now - self.history[0] > 120.0:
                self.history.popleft()
            waits = [
                window - (now - self._nth_oldest(count))
                for count, window in self.limits
                if self._nth_oldest(count) is not None
                and now - self._nth_oldest(count) < window
            ]
            if not waits:
                self.history.append(now)
                return
            time.sleep(max(waits) + 0.01)

    def _nth_oldest(self, count: int) -> float | None:
        """Timestamp of the request `count` slots back, or None if fewer sent."""
        if len(self.history) < count:
            return None
        return self.history[len(self.history) - count]


class RiotClient:
    def __init__(self, api_key: str, verbose: bool = True) -> None:
        self.api_key = api_key
        self.limiter = RateLimiter()
        self.verbose = verbose
        self.requests_made = 0

    def get(self, url: str, retries: int = 4) -> Any:
        for attempt in range(retries + 1):
            self.limiter.acquire()
            request = urllib.request.Request(url, headers={
                "X-Riot-Token": self.api_key,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    self.requests_made += 1
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                if error.code == 429:
                    delay = float(error.headers.get("Retry-After", 10))
                    if self.verbose:
                        print(f"  429; sleeping {delay:.0f}s", flush=True)
                    time.sleep(delay + 1)
                    continue
                if error.code in (500, 502, 503, 504) and attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                # 401/403 means the key is missing, wrong or expired. Say so
                # rather than letting it read as a network problem.
                if error.code in (401, 403):
                    body = error.read()[:200].decode(errors="replace")
                    hint = (
                        "Cloudflare edge block, not an auth failure -- the "
                        "User-Agent header was rejected."
                        if "1010" in body else
                        "The key is missing, malformed or expired. "
                        "Development keys last 24 hours; regenerate at "
                        "https://developer.riotgames.com/ and update .env."
                    )
                    raise SystemExit(
                        f"Riot API returned {error.code} for {url}\n"
                        f"body: {body}\n{hint}"
                    ) from error
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"exhausted retries for {url}")


def band_puuids(client: RiotClient, band: str, platform: str) -> list[str]:
    """PUUIDs of players currently in `band`."""
    host = PLATFORM_HOST.format(platform=platform)
    if band in APEX_BANDS:
        url = f"{host}/tft/league/v1/{APEX_BANDS[band]}?queue=RANKED_TFT"
        entries = client.get(url).get("entries", [])
    else:
        tier, division = DIVISION_BANDS[band]
        url = (f"{host}/tft/league/v1/entries/{tier}/{division}"
               f"?queue=RANKED_TFT&page=1")
        entries = client.get(url)
    puuids = [e["puuid"] for e in entries if e.get("puuid")]
    if not puuids and entries:
        raise SystemExit(
            f"league-v1 returned {len(entries)} entries for {band} but none "
            "carried a `puuid` field. Riot has changed the response shape; the "
            "summonerId->puuid hop would need restoring."
        )
    return puuids


def match_ids(client: RiotClient, puuid: str, region: str, count: int) -> list[str]:
    host = REGIONAL_HOST.format(region=region)
    url = (f"{host}/tft/match/v1/matches/by-puuid/{puuid}/ids"
           f"?start=0&count={count}")
    return client.get(url)


def subset_match(match: dict) -> dict | None:
    """Keep only the fields the reference distributions and fights consume.

    Items and augments were dropped until doc 99 entry 160.162, which fights
    real final boards in the engine and cannot do so faithfully without them.

    Returns None for anything outside ranked standard -- the queue filter is
    applied on the detail response rather than the id query because match-v1's
    id endpoint has no reliable queue parameter for TFT.
    """
    info = match.get("info", {})
    # Both conditions, deliberately. The first Double Up match sampled while
    # writing this carried `queue_id 1160` with *paired* eliminations -- two
    # participants sharing a `last_round` and a `time_eliminated` to the
    # millisecond. Four teams' worth of elimination rounds reported as eight
    # players' would bias the window distribution late and look like nothing.
    if info.get("queue_id") != RANKED_STANDARD_QUEUE:
        return None
    if info.get("tft_game_type") not in (None, "standard"):
        return None
    participants = []
    for participant in info.get("participants", []):
        participants.append({
            "placement": participant.get("placement"),
            "last_round": participant.get("last_round"),
            "level": participant.get("level"),
            "gold_left": participant.get("gold_left"),
            "time_eliminated": participant.get("time_eliminated"),
            "players_eliminated": participant.get("players_eliminated"),
            "units": [
                {
                    "character_id": unit.get("character_id"),
                    "tier": unit.get("tier"),
                    "rarity": unit.get("rarity"),
                    "items": list(unit.get("itemNames") or []),
                }
                for unit in participant.get("units", [])
            ],
            "augments": list(participant.get("augments") or []),
        })
    return {
        "match_id": match.get("metadata", {}).get("match_id"),
        "game_version": info.get("game_version"),
        "tft_set_core_name": info.get("tft_set_core_name"),
        "tft_set_number": info.get("tft_set_number"),
        "queue_id": info.get("queue_id"),
        "tft_game_type": info.get("tft_game_type"),
        "game_length": info.get("game_length"),
        "game_datetime": info.get("game_datetime"),
        "participants": participants,
    }


def refetch(
    client: RiotClient,
    source: Path,
    out: Path,
    region: str,
) -> tuple[list[dict], dict]:
    """Re-download every match id in ``source`` at the current subset.

    Lets an older sample gain fields it was fetched without (items and
    augments, doc 99 entry 160.162) while keeping the exact same games.
    Resumable: ids already in ``out`` are skipped.
    """
    payload = json.loads(source.read_text())
    ids = [m["match_id"] for m in payload.get("matches", []) if m.get("match_id")]
    matches, done = load_existing(out)
    provenance = dict(
        payload.get("provenance", {}),
        refetched_from=str(source.name),
        refetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    host = REGIONAL_HOST.format(region=region)
    missing = 0
    for match_id in ids:
        if match_id in done:
            continue
        try:
            raw = client.get(f"{host}/tft/match/v1/matches/{match_id}")
        except urllib.error.HTTPError as error:
            print(f"  match {match_id} failed: {error.code}", flush=True)
            missing += 1
            continue
        subset = subset_match(raw)
        if subset is None:
            missing += 1
            continue
        matches.append(subset)
        done.add(match_id)
        if len(matches) % 50 == 0:
            write_output(out, matches, dict(provenance, n_matches=len(matches)))
            print(f"  {len(matches)}/{len(ids)} matches "
                  f"({client.requests_made} requests)", flush=True)
    provenance = dict(
        provenance,
        n_matches=len(matches),
        n_participants=sum(len(m["participants"]) for m in matches),
        refetch_missing=missing,
        requests_made=client.requests_made,
        completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return matches, provenance


def load_existing(path: Path) -> tuple[list[dict], set[str]]:
    if not path.exists():
        return [], set()
    payload = json.loads(path.read_text())
    matches = payload.get("matches", [])
    return matches, {m["match_id"] for m in matches if m.get("match_id")}


def write_output(
    path: Path, matches: list[dict], provenance: dict
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"provenance": provenance, "matches": matches}, indent=1
    ))


def collect(
    client: RiotClient,
    band: str,
    region: str,
    platform: str,
    target: int,
    ids_per_player: int,
    set_number: int | None,
    existing_ids: set[str],
    existing: list[dict],
    path: Path,
    provenance: dict,
) -> tuple[list[dict], dict]:
    print(f"resolving {band} players on {platform}...", flush=True)
    puuids = band_puuids(client, band, platform)
    print(f"  {len(puuids)} players", flush=True)

    seen = set(existing_ids)
    matches = list(existing)
    skipped_queue = 0
    skipped_set = 0

    for index, puuid in enumerate(puuids):
        if len(matches) >= target:
            break
        try:
            ids = match_ids(client, puuid, region, ids_per_player)
        except urllib.error.HTTPError as error:
            print(f"  match ids failed for player {index}: {error.code}",
                  flush=True)
            continue
        for match_id in ids:
            if len(matches) >= target:
                break
            if match_id in seen:
                continue
            seen.add(match_id)
            host = REGIONAL_HOST.format(region=region)
            try:
                raw = client.get(f"{host}/tft/match/v1/matches/{match_id}")
            except urllib.error.HTTPError as error:
                print(f"  match {match_id} failed: {error.code}", flush=True)
                continue
            subset = subset_match(raw)
            if subset is None:
                skipped_queue += 1
                continue
            if set_number is not None and subset.get("tft_set_number") not in (
                None, set_number
            ):
                skipped_set += 1
                continue
            matches.append(subset)
            if len(matches) % 50 == 0:
                provenance = dict(provenance, n_matches=len(matches))
                write_output(path, matches, provenance)
                print(f"  {len(matches)}/{target} matches "
                      f"({client.requests_made} requests)", flush=True)

    provenance = dict(
        provenance,
        n_matches=len(matches),
        n_participants=sum(len(m["participants"]) for m in matches),
        players_sampled=len(puuids),
        skipped_wrong_queue=skipped_queue,
        skipped_wrong_set=skipped_set,
        requests_made=client.requests_made,
        completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return matches, provenance


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", default="challenger",
                        choices=sorted(APEX_BANDS | DIVISION_BANDS))
    parser.add_argument("--region", default="americas",
                        choices=["americas", "europe", "asia", "sea"],
                        help="regional routing host for match-v1")
    parser.add_argument("--platform", default="na1",
                        help="platform routing host for league-v1 (na1, euw1)")
    parser.add_argument("--matches", type=int, default=1000)
    parser.add_argument("--ids-per-player", type=int, default=10)
    parser.add_argument(
        "--set", type=int, default=17, dest="set_number",
        help="keep only this TFT set; 0 disables the filter",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--refetch", type=Path, default=None,
        help="re-download the match ids in this file at the current subset",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    api_key = read_api_key()
    if not api_key:
        print(
            "No Riot key found in RIOT_KEY, RIOT_API_KEY or .env.\n"
            "Get one from https://developer.riotgames.com/ (a development key "
            "is free and lasts 24 hours) and add it to the gitignored .env:\n"
            "    RIOT_KEY=RGAPI-...",
            file=sys.stderr,
        )
        return 2

    if args.refetch:
        out = args.out or args.refetch.with_name(f"{args.refetch.stem}_full.json")
        matches, provenance = refetch(
            RiotClient(api_key), args.refetch, out, args.region)
        write_output(out, matches, provenance)
        print(f"\n{len(matches)} matches -> {out} "
              f"({provenance['refetch_missing']} not refetched)")
        return 0

    out = args.out or (
        REFERENCE_DIR / f"matches_{args.band}_{date.today().isoformat()}.json"
    )
    existing, existing_ids = load_existing(out)
    if existing:
        print(f"resuming: {len(existing)} matches already in {out}")

    provenance = {
        "_comment": (
            "Real-TFT reference sample for the fidelity comparison of doc 99 "
            "entry 97. Fetched by scripts/fetch_riot_matches.py. Nothing here "
            "is loaded by the engine."
        ),
        "source": "riot match-v1",
        "band": args.band,
        "region": args.region,
        "platform": args.platform,
        "queue_id": RANKED_STANDARD_QUEUE,
        "set_filter": args.set_number or None,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    client = RiotClient(api_key)
    matches, provenance = collect(
        client, args.band, args.region, args.platform, args.matches,
        args.ids_per_player, args.set_number or None, existing_ids, existing,
        out, provenance,
    )
    write_output(out, matches, provenance)

    versions = sorted({m.get("game_version") for m in matches})
    print(f"\n{len(matches)} matches, "
          f"{provenance['n_participants']} participants -> {out}")
    print(f"patches present: {versions[:6]}"
          f"{' ...' if len(versions) > 6 else ''}")
    print(f"skipped: {provenance['skipped_wrong_queue']} wrong queue, "
          f"{provenance['skipped_wrong_set']} wrong set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
