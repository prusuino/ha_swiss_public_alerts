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
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
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

    _GAP = (STATE_UNAVAILABLE, STATE_UNKNOWN)

    class _AcrossGaps:
        """Lets a trigger see a change that follows a gap without a value.

        The core skips every change out of "unavailable" or "unknown". While
        the feed cannot be reached the entities are unavailable, so an alert
        published during the outage would switch the home-affected entity
        from unavailable to on, and the core would not fire. Such a change
        is let through here and judged against the last state seen before
        the gap. The core asks is_valid_state for every state with a value
        and only then is_valid_transition, so the states are remembered
        there.
        """

        _excluded_from_states = frozenset()

        def __init__(self, hass: HomeAssistant, config) -> None:
            super().__init__(hass, config)
            self._last_state: dict[str, str] = {}
            self._previous_state: dict[str, str | None] = {}

        def entity_filter(self, entities: set[str]) -> set[str]:
            # Start from what the entities show now, so that an outage right
            # after the automation starts is judged against a known state.
            kept = _own_entities(self._hass, super().entity_filter(entities))
            for entity_id in kept:
                state = self._hass.states.get(entity_id)
                if entity_id not in self._last_state and state is not None and state.state not in _GAP:
                    self._last_state[entity_id] = state.state
            return kept

        def is_valid_state(self, state: State, report_not_triggered) -> bool:
            self._previous_state[state.entity_id] = self._last_state.get(state.entity_id)
            self._last_state[state.entity_id] = state.state
            return super().is_valid_state(state, report_not_triggered)

        def _before_gap(self, to_state: State) -> str | None:
            return self._previous_state.get(to_state.entity_id)

    class _HomeAlertStarted(_AcrossGaps, make_entity_target_state_trigger(HOME_DOMAIN_SPECS, STATE_ON)):
        """The home-affected entity switches to on.

        After a gap it fires unless the entity was already on before it. With
        nothing known from before the gap it fires: an alert for the home is
        worth one notification too many rather than one too few."""

        def is_valid_transition(self, from_state: State, to_state: State) -> bool:
            if from_state.state in _GAP:
                return self._before_gap(to_state) != STATE_ON
            return super().is_valid_transition(from_state, to_state)

    class _HomeAlertCleared(_AcrossGaps, make_entity_target_state_trigger(HOME_DOMAIN_SPECS, STATE_OFF)):
        """The home-affected entity switches to off.

        After a gap it fires only when the entity was on before it; nothing
        known from before is no reason to announce an all-clear."""

        def is_valid_transition(self, from_state: State, to_state: State) -> bool:
            if from_state.state in _GAP:
                return self._before_gap(to_state) == STATE_ON
            return super().is_valid_transition(from_state, to_state)

    class _AlertCountIncreased(_AcrossGaps, EntityTriggerBase):
        """A count sensor goes up: at least one new alert was published.

        After a gap the count is compared with the last one before it."""

        _domain_specs = COUNT_DOMAIN_SPECS

        def is_valid_state(self, state: State, report_not_triggered) -> bool:
            super().is_valid_state(state, report_not_triggered)
            return _number(state) is not None

        def is_valid_transition(self, from_state: State, to_state: State) -> bool:
            before, after = _number(from_state), _number(to_state)
            if before is None:
                try:
                    before = float(self._before_gap(to_state))
                except (TypeError, ValueError):
                    before = None
            return before is not None and after is not None and after > before

    TRIGGERS: dict[str, type[Trigger]] = {
        "home_alert_started": _HomeAlertStarted,
        "home_alert_cleared": _HomeAlertCleared,
        "alert_count_increased": _AlertCountIncreased,
    }


async def async_get_triggers(hass: HomeAssistant) -> dict:
    """Return the triggers of this integration."""
    return TRIGGERS
