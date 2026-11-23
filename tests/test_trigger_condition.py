"""The triggers and conditions for the automation editor, tried with real
automations while the faked feed changes: when they fire, when they stay
quiet, and that entities of other integrations in the target are ignored."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.swiss_public_alerts import condition, trigger

from .common import Feeds, circle_item, entity_id, feed, item, refresh, setup

FOREIGN_BINARY = "binary_sensor.front_door"
FOREIGN_SENSOR = "sensor.steps"


async def _automation(hass: HomeAssistant, *, trigger: dict | None = None, condition: dict | None = None) -> list:
    calls = async_mock_service(hass, "test", "automation")
    config = {
        "alias": "Tell me",
        "trigger": trigger or {"trigger": "event", "event_type": "check_now"},
        "action": {"action": "test.automation"},
    }
    if condition:
        config["condition"] = condition
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()
    assert hass.states.get("automation.tell_me") is not None, "the automation was rejected"
    return calls


async def _check(hass: HomeAssistant, calls: list) -> bool:
    before = len(calls)
    hass.bus.async_fire("check_now")
    await hass.async_block_till_done()
    return len(calls) > before


async def test_platforms_offer_their_triggers_and_conditions(hass: HomeAssistant) -> None:
    assert set(await trigger.async_get_triggers(hass)) == {"home_alert_started", "home_alert_cleared", "alert_count_increased"}
    assert set(await condition.async_get_conditions(hass)) == {"home_is_affected", "home_is_not_affected"}


async def test_home_alert_started_and_cleared(hass: HomeAssistant, feeds: Feeds) -> None:
    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    hass.states.async_set(FOREIGN_BINARY, "off")
    target = {"entity_id": [home, FOREIGN_BINARY]}
    started = await _automation(hass, trigger={"trigger": "swiss_public_alerts.home_alert_started", "target": target})

    hass.states.async_set(FOREIGN_BINARY, "on")  # not ours
    await hass.async_block_till_done()
    assert len(started) == 0
    feeds.alertswiss = feed(circle_item())  # an alert elsewhere
    await refresh(hass, entry)
    assert len(started) == 0
    feeds.alertswiss = feed(circle_item(), item("POA-HOME"))
    await refresh(hass, entry)
    assert len(started) == 1


async def test_home_alert_cleared(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-HOME"))
    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    cleared = await _automation(hass, trigger={"trigger": "swiss_public_alerts.home_alert_cleared", "target": {"entity_id": home}})
    feeds.alertswiss = feed(item("POA-HOME", allClear=True))
    await refresh(hass, entry)
    assert len(cleared) == 1


async def test_alert_count_increased(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-A"))
    entry = await setup(hass, feeds)
    count = entity_id(hass, entry, "active_alerts")
    hass.states.async_set(FOREIGN_SENSOR, "1")
    calls = await _automation(hass, trigger={"trigger": "swiss_public_alerts.alert_count_increased", "target": {"entity_id": [count, FOREIGN_SENSOR]}})

    hass.states.async_set(FOREIGN_SENSOR, "2")  # not ours
    await hass.async_block_till_done()
    assert len(calls) == 0
    feeds.alertswiss = feed(item("POA-A"), circle_item())
    await refresh(hass, entry)
    assert len(calls) == 1
    feeds.alertswiss = feed(item("POA-A"))  # fewer: quiet
    await refresh(hass, entry)
    assert len(calls) == 1
    from custom_components.swiss_public_alerts.api import AlertswissApiError

    feeds.alertswiss = AlertswissApiError("down")  # unavailable is no number
    await refresh(hass, entry)
    feeds.alertswiss = feed(item("POA-A"), circle_item(), item("POA-C"))
    await refresh(hass, entry)
    assert len(calls) == 2  # two more alerts than before the outage

    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    feeds.alertswiss = feed(item("POA-A"), circle_item(), item("POA-C"))
    await refresh(hass, entry)
    assert len(calls) == 2  # the same count as before the outage: quiet


async def test_an_alert_published_during_an_outage_still_starts(hass: HomeAssistant, feeds: Feeds) -> None:
    from custom_components.swiss_public_alerts.api import AlertswissApiError

    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    started = await _automation(hass, trigger={"trigger": "swiss_public_alerts.home_alert_started", "target": {"entity_id": home}})

    # known to be off, then the feed fails, and comes back with an alert for the home
    feeds.alertswiss = feed(circle_item())
    await refresh(hass, entry)
    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    assert hass.states.get(home).state == "unavailable"
    feeds.alertswiss = feed(item("POA-HOME"))
    await refresh(hass, entry)
    assert len(started) == 1

    # another outage while the alert stays: no second notification
    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    feeds.alertswiss = feed(item("POA-HOME"))
    await refresh(hass, entry)
    assert len(started) == 1


async def test_nothing_known_before_the_gap_fires_started_but_not_cleared(hass: HomeAssistant, feeds: Feeds) -> None:
    from custom_components.swiss_public_alerts.api import AlertswissApiError

    feeds.alertswiss = feed(item("POA-HOME"))
    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    # the automations start while the entity is unavailable
    calls = await _automation(hass, trigger=[
        {"trigger": "swiss_public_alerts.home_alert_started", "target": {"entity_id": home}, "id": "started"},
        {"trigger": "swiss_public_alerts.home_alert_cleared", "target": {"entity_id": home}, "id": "cleared"},
    ])
    feeds.alertswiss = feed(item("POA-HOME"))
    await refresh(hass, entry)
    assert len(calls) == 1  # started: rather one notification too many than one too few

    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    feeds.alertswiss = feed()
    await refresh(hass, entry)
    assert len(calls) == 2  # cleared: it was on before the gap


async def test_cleared_stays_quiet_when_nothing_is_known_from_before(hass: HomeAssistant, feeds: Feeds) -> None:
    from custom_components.swiss_public_alerts.api import AlertswissApiError

    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    feeds.alertswiss = AlertswissApiError("down")
    await refresh(hass, entry)
    cleared = await _automation(hass, trigger={"trigger": "swiss_public_alerts.home_alert_cleared", "target": {"entity_id": home}})
    feeds.alertswiss = feed()
    await refresh(hass, entry)
    assert len(cleared) == 0


async def test_conditions(hass: HomeAssistant, feeds: Feeds) -> None:
    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    hass.states.async_set(FOREIGN_BINARY, "on")
    affected = await _automation(hass, condition={"condition": "swiss_public_alerts.home_is_affected", "target": {"entity_id": [home, FOREIGN_BINARY]}})
    assert await _check(hass, affected) is False  # the foreign "on" does not count
    feeds.alertswiss = feed(item("POA-HOME"))
    await refresh(hass, entry)
    assert await _check(hass, affected) is True


async def test_condition_not_affected(hass: HomeAssistant, feeds: Feeds) -> None:
    feeds.alertswiss = feed(item("POA-HOME"))
    entry = await setup(hass, feeds)
    home = entity_id(hass, entry, "home_affected", "binary_sensor")
    calm = await _automation(hass, condition={"condition": "swiss_public_alerts.home_is_not_affected", "target": {"entity_id": home}})
    assert await _check(hass, calm) is False
    feeds.alertswiss = feed()
    await refresh(hass, entry)
    assert await _check(hass, calm) is True
