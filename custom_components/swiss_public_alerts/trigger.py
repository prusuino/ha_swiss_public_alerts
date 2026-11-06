"""Triggers for Swiss Public Alerts (Alertswiss).

"Alert for the home location started" and "cleared" on the home-affected
entity, and "Alert count increased" on the count sensors (active alerts in
Switzerland, alerts for the home location) for the automation editor's
trigger list. A target that expands to other entities is narrowed to the
ones this integration created.

The trigger platform API arrived in Home Assistant 2026.10. On an older
version the module still imports, but offers no triggers.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

try:
    from homeassistant.helpers.automation import DomainSpec
    from homeassistant.helpers.trigger import EntityTriggerBase, Trigger, make_entity_target_state_trigger
except ImportError:  # Home Assistant before 2026.10: no trigger platform API
    TRIGGERS: dict = {}
else:
    HOME_DOMAIN_SPECS = {BINARY_SENSOR_DOMAIN: DomainSpec()}
    COUNT_DOMAIN_SPECS = {SENSOR_DOMAIN: DomainSpec()}

    def _own_entities(hass: HomeAssistant, entities: set[str]) -> set[str]:
        """Keep only entities created by this integration."""
        registry = er.async_get(hass)
        return {
            entity_id
            for entity_id in entities
            if (entry := registry.async_get(entity_id)) is not None
            and entry.platform == DOMAIN
        }

    def _number(state: State) -> float | None:
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    class _HomeAlertStarted(make_entity_target_state_trigger(HOME_DOMAIN_SPECS, STATE_ON)):
        """The home-affected entity switches to on."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities))

    class _HomeAlertCleared(make_entity_target_state_trigger(HOME_DOMAIN_SPECS, STATE_OFF)):
        """The home-affected entity switches to off."""

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities))

    class _AlertCountIncreased(EntityTriggerBase):
        """A count sensor goes up: at least one new alert was published."""

        _domain_specs = COUNT_DOMAIN_SPECS

        def entity_filter(self, entities: set[str]) -> set[str]:
            return _own_entities(self._hass, super().entity_filter(entities))

        def is_valid_state(self, state: State, report_not_triggered) -> bool:
            return _number(state) is not None

        def is_valid_transition(self, from_state: State, to_state: State) -> bool:
            before, after = _number(from_state), _number(to_state)
            return before is not None and after is not None and after > before

    TRIGGERS: dict[str, type[Trigger]] = {
        "home_alert_started": _HomeAlertStarted,
        "home_alert_cleared": _HomeAlertCleared,
        "alert_count_increased": _AlertCountIncreased,
    }


async def async_get_triggers(hass: HomeAssistant) -> dict:
    """Return the triggers of this integration."""
    return TRIGGERS
