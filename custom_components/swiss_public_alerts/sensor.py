"""Sensors for the Swiss Public Alerts integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlertswissCoordinator
from .const import DOMAIN, MAX_LISTED_ALERTS
from .entity import AlertswissEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensors."""
    coordinator: AlertswissCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ActiveAlertsSensor(coordinator),
            HomeAlertsSensor(coordinator),
            HeartbeatSensor(coordinator),
        ]
    )


class ActiveAlertsSensor(AlertswissEntity, SensorEntity):
    """Number of active alerts in Switzerland."""

    _attr_translation_key = "active_alerts"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: AlertswissCoordinator) -> None:
        super().__init__(coordinator, "active_alerts")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.relevant_alerts())

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.coordinator.relevant_alerts()[:MAX_LISTED_ALERTS]
        return {"alerts": self.coordinator.summaries(alerts)}


class HomeAlertsSensor(AlertswissEntity, SensorEntity):
    """Number of active alerts covering the home location."""

    _attr_translation_key = "home_alerts"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-alert"

    def __init__(self, coordinator: AlertswissCoordinator) -> None:
        super().__init__(coordinator, "home_alerts")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.home_alerts())

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.coordinator.home_alerts()[:MAX_LISTED_ALERTS]
        return {"alerts": self.coordinator.summaries(alerts)}


class HeartbeatSensor(AlertswissEntity, SensorEntity):
    """Age of the Alertswiss feed heartbeat (feed health indicator)."""

    _attr_translation_key = "heartbeat_age"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: AlertswissCoordinator) -> None:
        super().__init__(coordinator, "heartbeat_age")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.heartbeat_age_seconds
