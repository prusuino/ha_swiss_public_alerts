"""Sensors for the Swiss Public Alerts integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlertswissCoordinator, HazardsCoordinator, RuntimeData
from .api import _clean_text
from .const import DOMAIN, HAZARD_ICONS, HAZARD_TYPES, MAX_LISTED_ALERTS
from .entity import AlertswissEntity, HazardsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensors."""
    data: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    if data.alertswiss is not None:
        entities += [
            ActiveAlertsSensor(data.alertswiss),
            HomeAlertsSensor(data.alertswiss),
            HeartbeatSensor(data.alertswiss),
        ]
    if data.hazards is not None:
        entities += [HazardLevelSensor(data.hazards, t) for t in HAZARD_TYPES]
        entities.append(HighestHazardSensor(data.hazards))
    async_add_entities(entities)


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


class HazardLevelSensor(HazardsEntity, SensorEntity):
    """Danger level (0-5) of one natural hazard process at the location."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: HazardsCoordinator, hazard_type: str) -> None:
        key = hazard_type.replace("-", "_")
        super().__init__(coordinator, f"hazard_{key}")
        self._hazard_type = hazard_type
        self._attr_translation_key = f"hazard_{key}"
        self._attr_icon = HAZARD_ICONS.get(hazard_type, "mdi:alert")

    def _state(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.states.get(self._hazard_type)

    @property
    def native_value(self) -> int | None:
        state = self._state()
        return state.level if state else None

    @property
    def extra_state_attributes(self) -> dict:
        state = self._state()
        if state is None:
            return {}
        return {
            "location": self.coordinator.client.location.name,
            "description": _clean_text(state.description),
            "outlook_level": state.outlook_level,
            "expires": state.expires_iso,
        }


class HighestHazardSensor(HazardsEntity, SensorEntity):
    """Highest natural hazard danger level at the location across all processes."""

    _attr_translation_key = "highest_hazard"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:alert-octagram"

    def __init__(self, coordinator: HazardsCoordinator) -> None:
        super().__init__(coordinator, "highest_hazard")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.max_level

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        states = self.coordinator.data.states
        return {
            "location": self.coordinator.client.location.name,
            "levels": {t.replace("-", "_"): s.level for t, s in states.items()},
            "active": sorted(
                (t.replace("-", "_") for t, s in states.items() if s.level >= 2),
                key=lambda t: -states[t.replace("_", "-")].level,
            ),
        }
