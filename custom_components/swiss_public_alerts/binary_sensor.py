"""Binary sensor for the Swiss Public Alerts integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlertswissCoordinator, RuntimeData
from .const import DOMAIN, SEVERITY_RANK
from .entity import AlertswissEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensor."""
    data: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    if data.alertswiss is None:
        return
    async_add_entities([HomeAffectedBinarySensor(data.alertswiss)])


class HomeAffectedBinarySensor(AlertswissEntity, BinarySensorEntity):
    """On when at least one alert area covers the home location.

    No device class on purpose: "safety" would render as unsafe/safe in the
    frontend; the translation_key provides affected/not-affected state names.
    """

    _attr_translation_key = "home_affected"

    def __init__(self, coordinator: AlertswissCoordinator) -> None:
        super().__init__(coordinator, "home_affected")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.home_alerts())

    @property
    def icon(self) -> str:
        return "mdi:home-alert" if self.is_on else "mdi:home-outline"

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.coordinator.home_alerts()
        if not alerts:
            return {"alert_count": 0}
        top = max(
            alerts,
            key=lambda a: (
                SEVERITY_RANK.get(a.severity, 0),
                a.published.timestamp() if a.published else 0,
            ),
        )
        return {
            "alert_count": len(alerts),
            **top.summary,
            "description": top.description,
            "instructions": list(top.instructions),
            "alerts": self.coordinator.summaries(alerts, full=True),
        }
