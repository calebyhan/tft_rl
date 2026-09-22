"""The Riot fetcher keeps items and augments, and can refetch a stored sample.

Doc 99 entry 160.162 fights real final boards in the engine, which needs the
items and augments the original subset dropped. No network: a fake client
stands in for Riot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_riot_matches as fetch  # noqa: E402


def _raw(match_id: str, items=("TFT_Item_InfinityEdge",), augments=("TFT17_Augment_X",)):
    unit = {"character_id": "TFT17_Nasus", "tier": 2, "rarity": 0}
    if items is not None:
        unit["itemNames"] = list(items)
    participant = {"placement": 1, "last_round": 30, "level": 8, "gold_left": 3,
                   "time_eliminated": 1800.0, "players_eliminated": 2,
                   "units": [unit]}
    if augments is not None:
        participant["augments"] = list(augments)
    return {"metadata": {"match_id": match_id},
            "info": {"queue_id": fetch.RANKED_STANDARD_QUEUE, "tft_game_type": "standard",
                     "tft_set_number": 17, "participants": [participant]}}


def test_subset_keeps_items_and_augments():
    kept = fetch.subset_match(_raw("NA1_1"))["participants"][0]
    assert kept["units"][0]["items"] == ["TFT_Item_InfinityEdge"]
    assert kept["augments"] == ["TFT17_Augment_X"]


def test_subset_tolerates_payloads_without_them():
    kept = fetch.subset_match(_raw("NA1_1", items=None, augments=None))["participants"][0]
    assert kept["units"][0]["items"] == []
    assert kept["augments"] == []


class _FakeClient:
    def __init__(self):
        self.urls = []
        self.requests_made = 0

    def get(self, url):
        self.urls.append(url)
        self.requests_made += 1
        return _raw(url.rsplit("/", 1)[-1])


def test_refetch_downloads_exactly_the_stored_ids(tmp_path):
    source = tmp_path / "matches_challenger.json"
    source.write_text(json.dumps({
        "provenance": {"band": "challenger"},
        "matches": [{"match_id": "NA1_1"}, {"match_id": "NA1_2"}, {"match_id": "NA1_3"}],
    }))
    out = tmp_path / "matches_challenger_full.json"
    fetch.write_output(out, [fetch.subset_match(_raw("NA1_2"))], {})

    client = _FakeClient()
    matches, provenance = fetch.refetch(client, source, out, "americas")

    assert [url.rsplit("/", 1)[-1] for url in client.urls] == ["NA1_1", "NA1_3"]
    assert sorted(m["match_id"] for m in matches) == ["NA1_1", "NA1_2", "NA1_3"]
    assert provenance["band"] == "challenger"
    assert provenance["refetched_from"] == source.name
    assert provenance["refetch_missing"] == 0
    assert all(m["participants"][0]["units"][0]["items"] for m in matches
               if m["match_id"] != "NA1_2")
