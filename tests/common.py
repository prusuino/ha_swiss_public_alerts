"""Shared pieces of the Swiss Public Alerts tests: feed items shaped like the
real Alertswiss feed (2026-11-23) and an entry set up on faked feeds."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_public_alerts.api import AlertswissClient, FeedData
from custom_components.swiss_public_alerts.const import (
    CONF_DATA_SOURCES,
    CONF_LANGUAGE,
    CONF_MINIMUM_SEVERITY,
    CONF_PLZ,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    SOURCE_ALERTSWISS,
)
from custom_components.swiss_public_alerts.hazards import HazardsClient

# The test home lies inside SQUARE.
HOME = (46.5, 7.5)
SQUARE = [["46.0", "7.0"], ["46.0", "8.0"], ["47.0", "8.0"], ["47.0", "7.0"]]
# A zone cut out of the square, around the test home.
HOLE = [["46.4", "7.4"], ["46.4", "7.6"], ["46.6", "7.6"], ["46.6", "7.4"]]


def item(identifier: str = "POA-1", **changes) -> dict:
    """One alert as the feed sends it: a polygon area in the canton of Bern."""
    base = {
        "identifier": identifier,
        "title": {"title": "Hochwasser Aare"},
        "description": {"description": "Der Pegel steigt weiter."},
        "nationWide": False,
        "instructions": [{"text": "Keller meiden."}],
        "publisherName": "Kanton Bern",
        "link": "https://www.be.ch/hochwasser",
        "links": [{"href": "https://www.be.ch/hochwasser", "text": "Kanton Bern"}],
        "contact": {"contact": "Polizeinotruf: <a href=\"tel:117\">117</a>"},
        "event": "Hochwasser",
        "allClear": False,
        "severity": "moderate",
        "testAlert": False,
        "technicalTestAlert": False,
        "areas": [{
            "description": {"description": "Bern und Umgebung"},
            "polygons": [{"coordinates": SQUARE, "excludes": []}],
            "circles": [],
            "regions": [{"region": "BE"}],
            "regionType": "one",
        }],
        "reference": f"info@alertswiss.ch,{identifier},2026-11-16T10:26:30+01:00",
    }
    base.update(changes)
    return base


def circle_item(identifier: str = "POA-CIRCLE", lat: str = "46.76970", lon: str = "8.67591", radius: str = "0.266602233", **changes) -> dict:
    """An alert whose only area is a circle, like "Bristenstrasse" (Uri)."""
    return item(identifier, **{
        "title": {"title": "Bristenstrasse gesperrt"},
        "publisherName": "Kanton Uri",
        "severity": "minor",
        "areas": [{
            "description": {"description": "Bristenstrasse"},
            "polygons": [],
            "circles": [{"centerPosition": [lat, lon], "radius": radius}],
            "regions": [{"region": "UR"}],
            "regionType": "one",
        }],
        **changes,
    })


def parse(raw: dict, language: str = "de"):
    return AlertswissClient(MagicMock(), language)._parse_alert(raw)


def feed(*items: dict, heartbeat: float | None = 5.0) -> FeedData:
    return FeedData(alerts=tuple(a for a in (parse(i) for i in items) if a is not None), heartbeat_age_seconds=heartbeat)


DATA = {CONF_DATA_SOURCES: [SOURCE_ALERTSWISS], CONF_PLZ: "", CONF_LANGUAGE: "de", CONF_MINIMUM_SEVERITY: "minor", CONF_UPDATE_INTERVAL: 600}


class Feeds:
    """The two faked feeds; change `alertswiss`/`hazards` (a result or an
    exception) and refresh to play a new answer."""

    def __init__(self, alertswiss=None, hazards=None) -> None:
        self.alertswiss = alertswiss if alertswiss is not None else feed()
        self.hazards = hazards

    async def _alertswiss(self, *args):
        if isinstance(self.alertswiss, Exception):
            raise self.alertswiss
        return self.alertswiss

    async def _hazards(self, *args):
        if isinstance(self.hazards, Exception):
            raise self.hazards
        return self.hazards

    def patches(self):
        return (
            patch.object(AlertswissClient, "async_fetch", AsyncMock(side_effect=self._alertswiss)),
            patch.object(HazardsClient, "async_fetch", AsyncMock(side_effect=self._hazards)),
        )


async def setup(hass: HomeAssistant, feeds: Feeds, data: dict | None = None, options: dict | None = None) -> MockConfigEntry:
    """An entry set up on the faked feeds, with the home inside SQUARE."""
    hass.config.latitude, hass.config.longitude = HOME
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title="Swiss Public Alerts", data={**DATA, **(data or {})}, options=options or {})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    for coordinator in (entry.runtime_data.alertswiss, entry.runtime_data.hazards):
        if coordinator is not None:
            await coordinator.async_refresh()
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, suffix: str, domain: str = "sensor") -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{suffix}")
