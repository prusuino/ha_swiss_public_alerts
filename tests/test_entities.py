"""The entities of an entry on a faked feed: the counts, the home-affected
sensor, the map markers and what happens when the feed fails or changes."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.swiss_public_alerts.api import AlertswissApiError
from custom_components.swiss_public_alerts.const import CONF_LANGUAGE, CONF_MINIMUM_SEVERITY, CONF_UPDATE_INTERVAL, DOMAIN
from custom_components.swiss_public_alerts.geo_location import marker_unique_id

from .common import HOLE, SQUARE, Feeds, circle_item, entity_id, feed, item, refresh, setup


def _marker(hass: HomeAssistant, entry, identifier: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("geo_location", DOMAIN, marker_unique_id(entry.entry_id, identifier))


async def test_counts_home_alert_and_markers(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(
        item("POA-HOME"),  # covers the home
        circle_item(),  # elsewhere, a circle
        item("POA-OVER", allClear=True),  # an all-clear is no active alert
        item("POA-TEST", technicalTestAlert=True),
    )
    entry = await setup(hass, feeds)
    assert entry.state is ConfigEntryState.LOADED

    active = hass.states.get(entity_id(hass, entry, "active_alerts"))
    assert active.state == "2"
    listed = {a["identifier"]: a for a in active.attributes["alerts"]}
    assert set(listed) == {"POA-HOME", "POA-CIRCLE"}
    assert listed["POA-HOME"]["distance_km"] == 0.0
    assert listed["POA-CIRCLE"]["distance_km"] > 50  # the circle has a place, so a distance
    assert "description" not in listed["POA-HOME"]  # the long texts stay off the Switzerland-wide list

    home = hass.states.get(entity_id(hass, entry, "home_alerts"))
    assert home.state == "1" and home.attributes["alerts"][0]["identifier"] == "POA-HOME"
    assert hass.states.get(entity_id(hass, entry, "heartbeat_age")).state == "5.0"

    affected = hass.states.get(entity_id(hass, entry, "home_affected", "binary_sensor"))
    assert affected.state == "on"
    assert affected.attributes["alert_count"] == 1
    assert affected.attributes["title"] == "Hochwasser Aare"
    assert affected.attributes["description"] == "Der Pegel steigt weiter."
    assert affected.attributes["instructions"] == ["Keller meiden."]
    assert affected.attributes["contact"] == "Polizeinotruf: 117"
    assert affected.attributes["alerts"][0]["contact"] == "Polizeinotruf: 117"
    assert affected.attributes["icon"] == "mdi:home-alert"

    # one marker per alert with a place, the circle included
    circle = hass.states.get(_marker(hass, entry, "POA-CIRCLE"))
    assert circle.attributes["latitude"] == 46.7697 and circle.attributes["longitude"] == 8.67591
    assert circle.attributes["home_affected"] is False
    assert circle.attributes["entity_picture"].endswith("/severity/minor.svg?v=3")
    assert circle.name == "Bristenstrasse gesperrt"
    here = hass.states.get(_marker(hass, entry, "POA-HOME"))
    assert here.attributes["home_affected"] is True and float(here.state) == 0.0
    assert _marker(hass, entry, "POA-OVER") is None


async def test_the_home_inside_a_circle_or_a_cut_out_zone(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(circle_item(lat="46.5", lon="7.5", radius="0.3"))
    entry = await setup(hass, feeds)
    assert hass.states.get(entity_id(hass, entry, "home_affected", "binary_sensor")).state == "on"

    feeds.alertswiss = feed(item(areas=[{"polygons": [{"coordinates": SQUARE, "excludes": [{"coordinates": HOLE}]}]}]))
    await refresh(hass, entry)
    affected = hass.states.get(entity_id(hass, entry, "home_affected", "binary_sensor"))
    assert affected.state == "off"
    assert affected.attributes["alert_count"] == 0 and affected.attributes["icon"] == "mdi:home-outline"
    assert hass.states.get(entity_id(hass, entry, "active_alerts")).state == "1"


async def test_the_worst_and_newest_alert_leads(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(
        item("POA-A", severity="minor"),
        item("POA-B", severity="severe", title={"title": "Chemieunfall"}),
        item("POA-C", severity="moderate", reference="x,POA-C,not a time"),
    )
    entry = await setup(hass, feeds)
    affected = hass.states.get(entity_id(hass, entry, "home_affected", "binary_sensor"))
    assert affected.attributes["alert_count"] == 3 and affected.attributes["title"] == "Chemieunfall"


async def test_minimum_severity_and_options_apply_without_a_reload(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A", severity="minor"), item("POA-B", severity="severe"), item("POA-C", severity="odd"))
    entry = await setup(hass, feeds)
    coordinator = entry.runtime_data.alertswiss
    assert hass.states.get(entity_id(hass, entry, "active_alerts")).state == "2"  # an unknown severity ranks below minor

    hass.config_entries.async_update_entry(entry, options={CONF_MINIMUM_SEVERITY: "severe", CONF_LANGUAGE: "fr", CONF_UPDATE_INTERVAL: 300})
    await hass.async_block_till_done()
    assert entry.runtime_data.alertswiss is coordinator  # applied in place
    assert coordinator.client.language == "fr" and coordinator.update_interval.total_seconds() == 300
    assert hass.states.get(entity_id(hass, entry, "active_alerts")).state == "1"
    assert _marker(hass, entry, "POA-A") is None  # its marker is gone with it


async def test_markers_follow_the_feed(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"), item("POA-B"))
    entry = await setup(hass, feeds)
    assert _marker(hass, entry, "POA-A") and _marker(hass, entry, "POA-B")

    feeds.alertswiss = feed(item("POA-A", title={"title": "Neuer Titel"}), item("POA-C"))
    await refresh(hass, entry)
    assert hass.states.get(_marker(hass, entry, "POA-A")).name == "Neuer Titel"
    assert _marker(hass, entry, "POA-B") is None  # expired: gone from the registry too
    assert _marker(hass, entry, "POA-C")


async def test_markers_of_expired_alerts_are_cleaned_up_on_setup(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"))
    entry = await setup(hass, feeds)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create("geo_location", DOMAIN, marker_unique_id(entry.entry_id, "POA-OLD"), config_entry=entry)
    other = registry.async_get_or_create("geo_location", "another", "x", config_entry=entry)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(other.entity_id) is not None  # not ours
    assert _marker(hass, entry, "POA-A")


async def test_an_unreachable_feed_makes_everything_unavailable_and_raises_a_repair(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"))
    entry = await setup(hass, feeds)
    marker = _marker(hass, entry, "POA-A")
    issues = ir.async_get(hass)
    issue_id = f"unreachable_alertswiss_{entry.entry_id}"

    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    assert hass.states.get(entity_id(hass, entry, "active_alerts")).state == "unavailable"
    assert hass.states.get(marker).state == "unavailable"  # no stale alert on the map
    assert issues.async_get_issue(DOMAIN, issue_id) is None  # one failure is not worth a notice
    await refresh(hass, entry)
    await refresh(hass, entry)
    assert issues.async_get_issue(DOMAIN, issue_id).translation_key == "unreachable"

    feeds.alertswiss = feed(item("POA-A"))
    await refresh(hass, entry)
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(marker).state != "unavailable"


async def test_a_failed_first_refresh_keeps_the_markers(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"))
    entry = await setup(hass, feeds)
    marker = _marker(hass, entry, "POA-A")
    feeds.alertswiss = AlertswissApiError("down")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert er.async_get(hass).async_get(marker) is not None


async def test_unload_withdraws_the_repairs(hass: HomeAssistant, feeds: Feeds) -> None:
    entry = await setup(hass, feeds)
    entry.runtime_data.alertswiss.issues.raise_now("unreachable", {"host": "alertswiss.ch"}, suffix="alertswiss")
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_alertswiss_{entry.entry_id}")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"unreachable_alertswiss_{entry.entry_id}") is None
    assert entry.state is ConfigEntryState.NOT_LOADED
