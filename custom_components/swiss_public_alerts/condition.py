"""Conditions for Swiss Public Alerts (Alertswiss).

"Home location is affected" and "Home location is not affected" for the
automation editor's condition list. A target that expands to other entities
is narrowed to the ones this integration created.

The condition platform API arrived in Home Assistant 2026.11. On an older
version the module still imports, but offers no conditions.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

try:
    from homeassistant.helpers.automation import DomainSpec
    from homeassistant.helpers.condition import Condition, make_entity_state_condition
except ImportError:  # Home Assistant before 2026.11: no condition platform API
    CONDITIONS: dict = {}
else:
    HOME_DOMAIN_SPECS = {BINARY_SENSOR_DOMAIN: DomainSpec()}

    def _own_entities(hass: HomeAssistant, entities: set[str]) -> set[str]:
        """Keep only entities created by this integration."""
        registry = er.async_get(hass)
        return {
            entity_id
            for entity_id in entities
            if (entry := registry.async_get(entity_id)) is not None
            and entry.platform == DOMAIN
        }

    class _HomeIsAffected(make_entity_state_condition(HOME_DOMAIN_SPECS, STATE_ON)):
        """The home-affected entity is on."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities))

    class _HomeIsNotAffected(make_entity_state_condition(HOME_DOMAIN_SPECS, STATE_OFF)):
        """The home-affected entity is off."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities))

    CONDITIONS: dict[str, type[Condition]] = {
        "home_is_affected": _HomeIsAffected,
        "home_is_not_affected": _HomeIsNotAffected,
    }


async def async_get_conditions(hass: HomeAssistant) -> dict:
    """Return the conditions of this integration."""
    return CONDITIONS
