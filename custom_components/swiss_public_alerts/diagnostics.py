"""Diagnostics download (Settings → Devices & services → entry menu →
Download diagnostics): what the entry is configured with, what the
coordinators last fetched and the current state of the entry's entities, so
an issue report can carry the facts instead of a description of them.

Coordinates, distances, credentials and the entry's title, unique id and
name are redacted; of the last error only the type is kept, its text can repeat a
request URL. Entity ids and names stay readable and can contain a place name.
Long lists and texts are cut, the counts are kept.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

REDACTED = "**REDACTED**"
TO_REDACT = {"address", "lat", "latitude", "lon", "longitude", "plz"}
MAX_ITEMS = 25
MAX_TEXT = 300


def _secret(key: Any) -> bool:
    """A key in TO_REDACT, or any distance: the points the distances lead to
    (car parks, stations, epicentres) are public, so a handful of them is
    enough to work out the place they were measured from."""
    key = str(key).lower()
    return key in TO_REDACT or "distance" in key


def _entity_state(entity_id: str, state: Any) -> Any:
    """An entity's state, unless it is a distance: the state of a map marker
    is its distance from the home zone, and distance sensors measure from
    the configured place."""
    if state is None:
        return None
    is_distance = entity_id.startswith("geo_location.") or state.attributes.get("device_class") == "distance"
    if is_distance and state.state not in ("unknown", "unavailable"):
        return REDACTED
    return state.state


def _compact(value: Any, depth: int = 0) -> Any:
    """A JSON-safe, size-limited copy of a value, with the keys in TO_REDACT replaced."""
    if depth > 8:
        return "…"
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        items = list(value.items())
        out = {
            str(k): (REDACTED if _secret(k) and v not in (None, "") else _compact(v, depth + 1))
            for k, v in items[:MAX_ITEMS]
        }
        if len(items) > MAX_ITEMS:
            out["…"] = f"{len(items) - MAX_ITEMS} more keys ({len(items)} total)"
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        out = [_compact(v, depth + 1) for v in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            out.append(f"… {len(items) - MAX_ITEMS} more ({len(items)} total)")
        return out
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _entry_values(values: Any) -> dict[str, Any]:
    """Entry data or options; names the user typed can describe a place."""
    return {
        k: REDACTED if k in ("name", "location") and v not in (None, "") else v
        for k, v in _compact(dict(values)).items()
    }


def _coordinator_info(coordinator: Any) -> dict[str, Any]:
    interval = getattr(coordinator, "update_interval", None)
    exception = getattr(coordinator, "last_exception", None)
    return {
        "last_update_success": getattr(coordinator, "last_update_success", None),
        "last_exception": type(exception).__name__ if exception else None,
        "update_interval_seconds": interval.total_seconds() if isinstance(interval, timedelta) else interval,
        "data": _compact(getattr(coordinator, "data", None)),
    }


def _coordinators(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {}
    return {"alertswiss": getattr(runtime, "alertswiss", None), "hazards": getattr(runtime, "hazards", None)}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    registry = er.async_get(hass)
    entities = []
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(reg.entity_id)
        entities.append(
            {
                "entity_id": reg.entity_id,
                "unique_id": reg.unique_id,
                "disabled_by": reg.disabled_by,
                "hidden_by": reg.hidden_by,
                "state": _entity_state(reg.entity_id, state),
                "attributes": _compact(dict(state.attributes)) if state else None,
            }
        )
    return {
        "entry": {
            "title": REDACTED,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "unique_id": REDACTED if entry.unique_id else None,
            "state": str(entry.state),
            "data": _entry_values(entry.data),
            "options": _entry_values(entry.options),
        },
        "coordinators": {name: _coordinator_info(c) for name, c in _coordinators(hass, entry).items() if c is not None},
        "entities": entities,
    }
