"""Geolocation events for the Swiss Public Alerts integration.

Each active alert with a geographic area becomes a geolocation event whose
marker is placed on the area centroid, so alerts show up on the built-in
Home Assistant map (same pattern as the meteorological geo_location sources).
Markers follow the coordinator: while the feed is unreachable they are
unavailable, like the sensors, instead of showing a stale alert. Once an
alert has expired its marker is removed for good, from the state machine
and from the entity registry alike, because an alert id never returns.
"""

from __future__ import annotations

import logging

from homeassistant.components.geo_location import (
    DOMAIN as GEO_LOCATION_DOMAIN,
    GeolocationEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AlertswissCoordinator, RuntimeData
from .api import Alert
from .const import ATTRIBUTION, DOMAIN, STATIC_URL_BASE

_LOGGER = logging.getLogger(__name__)


def marker_unique_id(entry_id: str, identifier: str) -> str:
    """Unique id of the marker for one alert.

    The config entry id is part of it, so the marker is scoped to its entry
    rather than to the alert alone.
    """
    return f"{entry_id}_{identifier}"


def current_alerts(coordinator: AlertswissCoordinator) -> dict[str, Alert]:
    """The alerts that get a marker for the coordinator's current data."""
    return {
        alert.identifier: alert
        for alert in coordinator.relevant_alerts()
        if alert.centroid is not None
    }


@callback
def async_remove_stale_markers(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: AlertswissCoordinator
) -> None:
    """Drop the registry entries of markers whose alert is no longer in the feed.

    Runs once per setup. Before 1.3.0 an expired alert was only taken out of
    the state machine; its entity registry entry stayed behind and came back
    on every start as an unavailable "restored" entity. This removes those
    leftovers. Only geo_location entities of this integration that belong to
    this config entry are considered, and of those only the ones whose unique
    id the sync would not create for the current data. Live markers, the
    sensors, other config entries and other integrations are never touched,
    and a second run finds nothing to do.
    """
    if coordinator.data is None:
        # The first refresh failed, so there is no data to compare against
        # and every marker would look stale. Skip rather than delete markers
        # that may well be live; the next start with a working feed cleans up.
        return
    registry = er.async_get(hass)
    live = {
        marker_unique_id(entry.entry_id, identifier)
        for identifier in current_alerts(coordinator)
    }
    removed = 0
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registry_entry.domain != GEO_LOCATION_DOMAIN
            or registry_entry.platform != DOMAIN
            or registry_entry.unique_id in live
        ):
            continue
        registry.async_remove(registry_entry.entity_id)
        removed += 1
    if removed:
        _LOGGER.info(
            "Removed %d map marker(s) of expired alerts from the entity registry",
            removed,
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up geolocation events and keep them in sync with the feed."""
    data: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    if data.alertswiss is None:
        return
    coordinator = data.alertswiss
    registry = er.async_get(hass)
    tracked: dict[str, AlertGeolocationEvent] = {}

    @callback
    def _remove(entity: AlertGeolocationEvent) -> None:
        # Removing the registry entry is the complete operation: the entity
        # listens for its own registry removal and takes itself out of the
        # state machine. A marker without a registry entry (not registered
        # yet) is removed as a plain entity instead.
        entity_id = registry.async_get_entity_id(
            GEO_LOCATION_DOMAIN, DOMAIN, entity.unique_id
        )
        if entity_id is not None:
            registry.async_remove(entity_id)
        else:
            entity.schedule_removal()

    @callback
    def _sync() -> None:
        # Runs on every coordinator notification — including a failed
        # refresh, which keeps the previous alerts but flips
        # last_update_success. The in-place update below then writes state
        # for every surviving marker, which is what publishes the
        # availability change (see AlertGeolocationEvent.available).
        current = current_alerts(coordinator)
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
                _remove(tracked.pop(identifier))
        if new_entities:
            async_add_entities(new_entities)

    async_remove_stale_markers(hass, entry, coordinator)
    entry.async_on_unload(coordinator.async_add_listener(_sync))
    _sync()


class AlertGeolocationEvent(GeolocationEvent):
    """A single alert as a map marker. Lifecycle (appearing/disappearing) is
    managed by the sync function above; the alert data is refreshed in place
    on every coordinator update, and availability follows the coordinator's
    last refresh."""

    _attr_attribution = ATTRIBUTION
    _attr_source = DOMAIN
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_should_poll = False
    _attr_icon = "mdi:alert"
    # Hidden from auto-generated maps (default map dashboard / strategies) so
    # alerts only appear on map cards that reference the source explicitly.
    # This applies to entities registered for the first time; whether an
    # existing entity stays hidden is the user's decision alone and is never
    # rewritten from here.
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: AlertswissCoordinator, alert: Alert) -> None:
        self._coordinator = coordinator
        self._alert = alert
        self._attr_unique_id = marker_unique_id(
            coordinator.entry.entry_id, alert.identifier
        )

    def update_alert(self, alert: Alert) -> None:
        """Refresh the underlying alert data."""
        self._alert = alert
        if self.hass:
            self.async_write_ha_state()

    def schedule_removal(self) -> None:
        """Remove this event from the state machine alone.

        Fallback for a marker that has no entity registry entry; a registered
        marker is removed through the registry by the sync function.
        """
        if self.hass:
            self.hass.async_create_task(self.async_remove(force_remove=True))

    @property
    def available(self) -> bool:
        """Like the sensors: while the feed is unreachable the marker is
        unavailable instead of showing its last known alert indefinitely.
        Not a CoordinatorEntity (the lifecycle is managed by the sync
        function), so this reads the coordinator directly; the sync function
        writes state after every refresh, failed ones included, so a flip
        reaches the state machine."""
        return self._coordinator.last_update_success

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
