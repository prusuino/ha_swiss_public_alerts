"""Config flow tests: one entry only, source validation, postal code checks,
an unreachable feed and the options flow. The feeds are faked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swiss_public_alerts.api import AlertswissApiError, FeedData
from custom_components.swiss_public_alerts.const import (
    CONF_DATA_SOURCES,
    CONF_LANGUAGE,
    CONF_MINIMUM_SEVERITY,
    CONF_PLZ,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    SOURCE_ALERTSWISS,
    SOURCE_HAZARDS,
)
from custom_components.swiss_public_alerts.hazards import HazardsData

FLOW = "custom_components.swiss_public_alerts.config_flow."
INPUT = {CONF_DATA_SOURCES: [SOURCE_ALERTSWISS], CONF_PLZ: "", CONF_LANGUAGE: "de", CONF_MINIMUM_SEVERITY: "minor", CONF_UPDATE_INTERVAL: 600}


@pytest.fixture
def fake_feeds():
    with (
        patch(FLOW + "AlertswissClient.async_fetch", AsyncMock(return_value=FeedData(alerts=(), heartbeat_age_seconds=5.0))),
        patch(FLOW + "HazardsClient.async_fetch", AsyncMock(return_value=HazardsData(states={}, version="v1", timestamp=None))),
    ):
        yield


async def _start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    return result


async def test_setup_with_alertswiss_only(hass: HomeAssistant, enable_custom_integrations, fake_feeds) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Swiss Public Alerts"
    assert result["data"][CONF_DATA_SOURCES] == [SOURCE_ALERTSWISS]
    assert result["data"][CONF_UPDATE_INTERVAL] == 600 and isinstance(result["data"][CONF_UPDATE_INTERVAL], int)
    assert result["result"].unique_id == DOMAIN


async def test_setup_with_hazards_needs_a_known_postal_code(hass: HomeAssistant, enable_custom_integrations, fake_feeds) -> None:
    result = await _start(hass)
    both = {**INPUT, CONF_DATA_SOURCES: [SOURCE_ALERTSWISS, SOURCE_HAZARDS]}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], both)
    assert result["errors"] == {CONF_PLZ: "plz_required"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**both, CONF_PLZ: "0000"})
    assert result["errors"] == {CONF_PLZ: "plz_unknown"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**both, CONF_PLZ: " 8001 "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PLZ] == "8001"


async def test_no_source_is_an_error(hass: HomeAssistant, enable_custom_integrations, fake_feeds) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**INPUT, CONF_DATA_SOURCES: []})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DATA_SOURCES: "no_source"}


async def test_unreachable_feed_is_a_form_error(hass: HomeAssistant, enable_custom_integrations) -> None:
    with patch(FLOW + "AlertswissClient.async_fetch", AsyncMock(side_effect=AlertswissApiError("down"))):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_only_one_entry(hass: HomeAssistant, enable_custom_integrations, fake_feeds) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title="Swiss Public Alerts", data=INPUT).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_validates_like_setup(hass: HomeAssistant, enable_custom_integrations, fake_feeds) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title="Swiss Public Alerts", data=INPUT)
    entry.add_to_hass(hass)
    with patch("custom_components.swiss_public_alerts.async_setup_entry", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**INPUT, CONF_DATA_SOURCES: [SOURCE_HAZARDS], CONF_PLZ: "8001", CONF_LANGUAGE: "fr", CONF_UPDATE_INTERVAL: 300.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DATA_SOURCES] == [SOURCE_HAZARDS]
    assert entry.options[CONF_LANGUAGE] == "fr"
    assert entry.options[CONF_UPDATE_INTERVAL] == 300 and isinstance(entry.options[CONF_UPDATE_INTERVAL], int)
