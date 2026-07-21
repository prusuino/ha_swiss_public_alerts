"""Geolocation events for the Swiss Public Alerts integration.

Each active alert with a geographic area becomes a geolocation event whose
marker is placed on the area centroid, so alerts show up on the built-in
Home Assistant map (same pattern as the meteorological geo_location sources).
"""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlertswissCoordinator
from .api import Alert
from .const import ATTRIBUTION, DOMAIN, STATIC_URL_BASE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up geolocation events and keep them in sync with the feed."""
    coordinator: AlertswissCoordinator = hass.data[DOMAIN][entry.entry_id]
    tracked: dict[str, AlertGeolocationEvent] = {}

    @callback
    def _sync() -> None:
        current = {
            alert.identifier: alert
            for alert in coordinator.relevant_alerts()
            if alert.centroid is not None
        }
        new_entities = []
        for identifier, alert in current.items():
            if identifier in tracked:
                tracked[identifier].update_alert(alert)
            else:
                entity = AlertGeolocationEvent(coordinator, alert)
                tracked[identifier] = entity
                new_entities.append(entity)
        for identifier in list(tracked):
            if identifier not in current:
                tracked.pop(identifier).schedule_removal()
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync))
    _sync()


class AlertGeolocationEvent(GeolocationEvent):
    """A single alert as a map marker."""

    _attr_attribution = ATTRIBUTION
    _attr_source = DOMAIN
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_should_poll = False
    _attr_icon = "mdi:alert"
    # Hidden from auto-generated maps (default map dashboard / strategies) so
    # alerts only appear on map cards that reference the source explicitly.
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: AlertswissCoordinator, alert: Alert) -> None:
        self._coordinator = coordinator
        self._alert = alert
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{alert.identifier}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Retroactively hide entities registered before visible_default was
        # introduced; never overrides an explicit user choice (hidden_by set).
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is not None and entry.hidden_by is None:
            registry.async_update_entity(
                self.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
            )

    def update_alert(self, alert: Alert) -> None:
        """Refresh the underlying alert data."""
        self._alert = alert
        if self.hass:
            self.async_write_ha_state()

    def schedule_removal(self) -> None:
        """Remove this event when the alert disappears from the feed."""
        if self.hass:
            self.hass.async_create_task(self.async_remove(force_remove=True))

    @property
    def name(self) -> str:
        return self._alert.title

    @property
    def entity_picture(self) -> str | None:
        """Alertswiss-style severity symbol as map marker.

        The ?v= query busts the browser cache when the artwork changes
        (the static path is served with long-lived cache headers).
        """
        severity = self._alert.severity if self._alert.severity in (
            "minor", "moderate", "severe") else "unknown"
        return f"{STATIC_URL_BASE}/severity/{severity}.svg?v=3"

    @property
    def latitude(self) -> float | None:
        return self._alert.centroid[0] if self._alert.centroid else None

    @property
    def longitude(self) -> float | None:
        return self._alert.centroid[1] if self._alert.centroid else None

    @property
    def distance(self) -> float | None:
        return self._alert.distance_km(
            self.hass.config.latitude, self.hass.config.longitude
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._alert.summary,
            "home_affected": self._alert.covers(
                self.hass.config.latitude, self.hass.config.longitude
            ),
        }
