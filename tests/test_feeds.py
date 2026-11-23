"""The two clients against a faked web session, and the natural-hazard
sensors of an entry."""
from __future__ import annotations

import time

import pytest
from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.swiss_public_alerts.api import AlertswissApiError, AlertswissClient
from custom_components.swiss_public_alerts.const import CONF_DATA_SOURCES, CONF_LANGUAGE, CONF_PLZ, DOMAIN, SOURCE_ALERTSWISS, SOURCE_HAZARDS
from custom_components.swiss_public_alerts.hazards import HazardsApiError, HazardsClient, HazardsData, HazardState, find_location, load_locations

from .common import Feeds, entity_id, item, refresh, setup


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        if isinstance(self._payload, Exception):
            raise self._payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    """Answers by the end of the URL; counts the requests."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return _Response(next(v for k, v in self.answers.items() if url.endswith(k)))


async def test_alertswiss_client_reads_the_feed():
    session = _Session({"actual.json": {"heartbeatAgeInMillis": 4114, "alerts": [item("POA-1"), item("TEST", technicalTestAlert=True), "garbage"]}})
    data = await AlertswissClient(session, "fr").async_fetch()
    assert "/fr/home/" in session.urls[0]
    assert [a.identifier for a in data.alerts] == ["POA-1"]
    assert data.heartbeat_age_seconds == 4.114

    no_heartbeat = await AlertswissClient(_Session({"actual.json": {"alerts": []}}), "de").async_fetch()
    assert no_heartbeat.alerts == () and no_heartbeat.heartbeat_age_seconds is None


@pytest.mark.parametrize("answer", [ClientError("down"), TimeoutError(), ["not", "a", "feed"], {"something": "else"}])
async def test_alertswiss_client_errors(answer):
    with pytest.raises(AlertswissApiError):
        await AlertswissClient(_Session({"actual.json": answer}), "de").async_fetch()


def _dangers(level: int = 3) -> dict:
    future = int(time.time()) + 3600
    return {"config": {"timestamp": 1794000000}, "hazards": {"wind": [
        {"warnlevel": level, "areas": [143], "expires": future, "onset": future - 7200, "description": "<b>Sturm</b><br/>Böen bis 110 km/h", "webLinkText": "Mehr"},
    ]}}


async def test_hazards_client_fetches_the_dangers_once_per_version_and_language():
    location = find_location(load_locations(), "8001")
    session = _Session({"versions.json": {"versioned/danger/v3": "v1"}, "dangers.json": _dangers()})
    client = HazardsClient(session, "de", location)
    data = await client.async_fetch()
    assert data.states["wind"].level == 3 and data.version == "v1"
    assert data.states["wind"].onset_iso.startswith("20") and data.states["rain"].onset_iso is None
    assert session.urls[1].endswith("/version__v1/de/dangers.json")

    await client.async_fetch()  # same version: only the small versions file again
    assert len(session.urls) == 3
    client.language = "it"
    await client.async_fetch()
    assert session.urls[-1].endswith("/version__v1/it/dangers.json")
    session.answers["versions.json"] = {"versioned/danger/v3": "v2"}
    await client.async_fetch()
    assert session.urls[-1].endswith("/version__v2/it/dangers.json")


@pytest.mark.parametrize("answers", [
    {"versions.json": ClientError("down")},
    {"versions.json": {"other": "v1"}},
    {"versions.json": ["v1"]},
    {"versions.json": {"versioned/danger/v3": "v1"}, "dangers.json": {"no": "hazards"}},
    {"versions.json": {"versioned/danger/v3": "v1"}, "dangers.json": TimeoutError()},
])
async def test_hazards_client_errors(answers):
    client = HazardsClient(_Session(answers), "de", find_location(load_locations(), "8001"))
    with pytest.raises(HazardsApiError):
        await client.async_fetch()


def test_hazard_state_without_times():
    state = HazardState("wind", 0, None, "", "", None)
    assert state.expires_iso is None and state.onset_iso is None
    assert HazardsData(states={}, version="v", timestamp=None).max_level == 0


BOTH = {CONF_DATA_SOURCES: [SOURCE_ALERTSWISS, SOURCE_HAZARDS], CONF_PLZ: "8001"}


def _hazards(level: int = 3) -> HazardsData:
    client = HazardsClient(None, "de", find_location(load_locations(), "8001"))
    return client._parse(_dangers(level), "v1")


async def test_hazard_sensors(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.hazards = _hazards()
    entry = await setup(hass, feeds, BOTH)
    wind = hass.states.get(entity_id(hass, entry, "hazard_wind"))
    assert wind.state == "3"
    assert wind.attributes["location"] == "Zürich"
    assert wind.attributes["description"] == "Sturm Böen bis 110 km/h"
    assert wind.attributes["onset"].startswith("20") and wind.attributes["expires"].startswith("20")
    assert hass.states.get(entity_id(hass, entry, "hazard_heat_wave")).state == "0"
    highest = hass.states.get(entity_id(hass, entry, "highest_hazard"))
    assert highest.state == "3" and highest.attributes["active"] == ["wind"]
    assert highest.attributes["levels"]["wind"] == 3 and highest.attributes["levels"]["slippery_roads"] == 0

    feeds.hazards = HazardsApiError("down")
    for _ in range(3):
        await refresh(hass, entry)
    assert hass.states.get(entity_id(hass, entry, "hazard_wind")).state == "unavailable"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_hazards_{entry.entry_id}")
    feeds.hazards = _hazards(1)
    await refresh(hass, entry)
    assert hass.states.get(entity_id(hass, entry, "hazard_wind")).state == "1"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_hazards_{entry.entry_id}") is None


async def test_hazards_only_and_an_unknown_postal_code(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.hazards = _hazards()
    entry = await setup(hass, feeds, {CONF_DATA_SOURCES: [SOURCE_HAZARDS], CONF_PLZ: "0000"})
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.alertswiss is None and entry.runtime_data.hazards is None
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"plz_unknown_{entry.entry_id}")
    assert issue.translation_placeholders == {"plz": "0000"}
    assert entity_id(hass, entry, "active_alerts") is None  # no Alertswiss entities, no markers

    # a corrected postal code reloads the entry and the notice is gone
    hass.config_entries.async_update_entry(entry, options={CONF_DATA_SOURCES: [SOURCE_HAZARDS], CONF_PLZ: "8001"})
    await hass.async_block_till_done()
    assert entry.runtime_data.hazards is not None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"plz_unknown_{entry.entry_id}") is None
    assert hass.states.get(entity_id(hass, entry, "hazard_wind")).state == "3"


async def test_options_reload_on_a_new_source_or_place_and_apply_the_rest_in_place(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.hazards = _hazards()
    entry = await setup(hass, feeds, BOTH)
    hazards = entry.runtime_data.hazards

    hass.config_entries.async_update_entry(entry, options={**BOTH, CONF_LANGUAGE: "it"})
    await hass.async_block_till_done()
    assert entry.runtime_data.hazards is hazards and hazards.client.language == "it"

    hass.config_entries.async_update_entry(entry, options={**BOTH, CONF_PLZ: "3011"})
    await hass.async_block_till_done()
    assert entry.runtime_data.hazards is not hazards
    assert entry.runtime_data.hazards.client.location.plz == "3011"

    hass.config_entries.async_update_entry(entry, options={CONF_DATA_SOURCES: [SOURCE_ALERTSWISS]})
    await hass.async_block_till_done()
    assert entry.runtime_data.hazards is None and entry.runtime_data.alertswiss is not None
