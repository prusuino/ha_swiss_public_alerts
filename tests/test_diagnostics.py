"""The diagnostics download: what it tells and what it keeps to itself."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_public_alerts.const import DOMAIN
from custom_components.swiss_public_alerts.diagnostics import REDACTED, _compact, async_get_config_entry_diagnostics

from .common import Feeds, feed, item, setup


async def test_diagnostics_of_a_running_entry(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"))
    entry = await setup(hass, feeds)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    json.dumps(diag)  # must be plain JSON

    assert diag["entry"]["title"] == REDACTED and diag["entry"]["unique_id"] == REDACTED
    assert diag["entry"]["state"] == "ConfigEntryState.LOADED"
    assert diag["entry"]["data"]["language"] == "de"
    fetched = diag["coordinators"]["alertswiss"]
    assert fetched["last_update_success"] is True and fetched["last_exception"] is None
    assert fetched["update_interval_seconds"] == 600
    assert "hazards" not in diag["coordinators"]
    ids = {e["unique_id"] for e in diag["entities"]}
    assert f"{entry.entry_id}_active_alerts" in ids and f"{entry.entry_id}_POA-A" in ids
    # the home coordinates never leave: the marker's position is the alert's, the entry holds none
    assert str(hass.config.latitude) not in json.dumps(diag["entry"])


async def test_diagnostics_of_an_entry_that_is_not_loaded(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data={"name": "Daheim", "language": "de", "location": ""})
    entry.add_to_hass(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["coordinators"] == {} and diag["entities"] == []
    assert diag["entry"]["unique_id"] is None
    assert diag["entry"]["data"] == {"name": REDACTED, "language": "de", "location": ""}


def test_compact_limits_and_redacts():
    @dataclass
    class Thing:
        latitude: float
        label: str

    value = _compact({
        "latitude": 46.9, "lon": 7.4, "address": "Musterweg 1",
        "when": datetime(2026, 11, 23, 12, tzinfo=timezone.utc), "day": date(2026, 11, 23), "span": timedelta(minutes=5),
        "long": "x" * 1000, "many": list(range(100)), "set": {1}, "thing": Thing(46.9, "ok"), "other": object(),
        "flag": True, "none": None,
    })
    assert value["latitude"] == REDACTED and value["lon"] == REDACTED and value["address"] == REDACTED
    assert value["when"].startswith("2026-11-23") and value["day"] == "2026-11-23"
    assert len(value["long"]) < 400 and len(value["many"]) <= 27
    assert value["thing"]["latitude"] == REDACTED and value["thing"]["label"] == "ok"
    assert isinstance(value["other"], str) and value["flag"] is True and value["none"] is None
