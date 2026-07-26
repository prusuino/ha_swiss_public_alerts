"""Automatic dashboard and card-resource management for Swiss Public Alerts.

Uses Home Assistant's internal Lovelace storage API (there is no public
integration API for this; the approach is verified against current HA core).
Dashboard creation is idempotent: once created it is never touched again, so
user edits survive restarts. The only exception is additive: when the natural
hazards data source is enabled later, its section is appended once to the
existing dashboard (never modifying existing cards). Removing the config
entry removes the dashboard and the card resource again.
"""

from __future__ import annotations

import json
import logging

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.lovelace import dashboard as ll_dashboard
from homeassistant.components.lovelace.const import (
    CONF_ALLOW_SINGLE_WORD,
    CONF_ICON,
    CONF_REQUIRE_ADMIN,
    CONF_SHOW_IN_SIDEBAR,
    CONF_TITLE,
    CONF_URL_PATH,
    DOMAIN as LOVELACE_DOMAIN,
    LOVELACE_DATA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, STATIC_URL_BASE

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "alertswiss-meldungen"
DASHBOARD_TITLE = "Alerts"
DASHBOARD_ICON = "mdi:alert-circle-outline"

CARD_VERSION = "1.3.0"
TICKER_RESOURCE_BASE = f"{STATIC_URL_BASE}/alertswiss-ticker-card.js"
TICKER_RESOURCE_URL = f"{TICKER_RESOURCE_BASE}?v={CARD_VERSION}"


async def async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the ticker card resource and create the dashboard if missing."""
    await _async_ensure_resource(hass)

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning(
            "Lovelace data not available — could not set up the Alerts dashboard"
        )
        return
    if DASHBOARD_URL_PATH in lovelace_data.dashboards:
        # Never overwrite user changes; only append the natural hazards
        # section once if that data source was enabled after creation.
        await _async_append_hazards_section(hass, entry, lovelace_data)
        return

    dashboards_collection = ll_dashboard.DashboardsCollection(hass)
    await dashboards_collection.async_load()
    try:
        item = await dashboards_collection.async_create_item(
            {
                CONF_URL_PATH: DASHBOARD_URL_PATH,
                CONF_TITLE: DASHBOARD_TITLE,
                CONF_ICON: DASHBOARD_ICON,
                CONF_SHOW_IN_SIDEBAR: True,
                CONF_REQUIRE_ADMIN: False,
                CONF_ALLOW_SINGLE_WORD: True,
            }
        )
    except (HomeAssistantError, vol.Invalid) as err:
        _LOGGER.warning("Could not create the Alerts dashboard: %s", err)
        return

    storage = ll_dashboard.LovelaceStorage(hass, item)
    lovelace_data.dashboards[DASHBOARD_URL_PATH] = storage
    await storage.async_save(_build_config(hass, entry))

    frontend.async_register_built_in_panel(
        hass,
        LOVELACE_DOMAIN,
        frontend_url_path=DASHBOARD_URL_PATH,
        require_admin=False,
        show_in_sidebar=True,
        sidebar_title=DASHBOARD_TITLE,
        sidebar_icon=DASHBOARD_ICON,
        config={"mode": "storage"},
        update=False,
    )
    _LOGGER.info("Alerts dashboard automatically set up at /%s", DASHBOARD_URL_PATH)


async def _async_ensure_resource(hass: HomeAssistant) -> None:
    """Register the bundled ticker card as a Lovelace module resource."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    resources = getattr(lovelace_data, "resources", None)
    if resources is None:
        _LOGGER.warning(
            "Lovelace resources not available — add %s as a module resource "
            "manually to use the ticker card",
            TICKER_RESOURCE_URL,
        )
        return
    if not hasattr(resources, "async_create_item"):
        _LOGGER.info(
            "Lovelace runs in YAML mode — add %s as a module resource to use "
            "the ticker card",
            TICKER_RESOURCE_URL,
        )
        return

    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    for item in resources.async_items():
        if TICKER_RESOURCE_BASE in item.get("url", ""):
            if item.get("url") != TICKER_RESOURCE_URL:
                await resources.async_update_item(item["id"], {"url": TICKER_RESOURCE_URL})
                _LOGGER.info("Updated ticker card resource to %s", TICKER_RESOURCE_URL)
            return

    await resources.async_create_item({"res_type": "module", "url": TICKER_RESOURCE_URL})
    _LOGGER.info("Registered ticker card resource %s", TICKER_RESOURCE_URL)


async def async_remove_dashboard(hass: HomeAssistant) -> None:
    """Remove the auto-created dashboard and the ticker card resource."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        return

    try:
        dashboards_collection = ll_dashboard.DashboardsCollection(hass)
        await dashboards_collection.async_load()
        for item in dashboards_collection.async_items():
            if item.get(CONF_URL_PATH) == DASHBOARD_URL_PATH:
                await dashboards_collection.async_delete_item(item["id"])
                lovelace_data.dashboards.pop(DASHBOARD_URL_PATH, None)
                frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
                _LOGGER.info("Removed dashboard /%s", DASHBOARD_URL_PATH)
                break
    except (HomeAssistantError, vol.Invalid) as err:
        _LOGGER.warning("Could not remove the Alerts dashboard: %s", err)

    try:
        resources = getattr(lovelace_data, "resources", None)
        if resources is not None and hasattr(resources, "async_delete_item"):
            if not resources.loaded:
                await resources.async_load()
                resources.loaded = True
            for item in list(resources.async_items()):
                if TICKER_RESOURCE_BASE in item.get("url", ""):
                    await resources.async_delete_item(item["id"])
                    _LOGGER.info("Removed ticker card resource")
                    break
    except HomeAssistantError as err:
        _LOGGER.warning("Could not remove the ticker card resource: %s", err)


_HAZARD_SUFFIXES = (
    "highest_hazard",
    "hazard_wind",
    "hazard_thunderstorm",
    "hazard_rain",
    "hazard_snow",
    "hazard_slippery_roads",
    "hazard_heat_wave",
    "hazard_frost",
    "hazard_forestfire",
    "hazard_flood",
    "hazard_avalanches",
    "hazard_drought",
    "hazard_earthquake",
)


def _entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Resolve the entry's entity ids by unique-id suffix."""
    registry = er.async_get(hass)
    ids: dict[str, str] = {}
    suffixes = (
        "active_alerts",
        "home_alerts",
        "home_affected",
        "heartbeat_age",
    ) + _HAZARD_SUFFIXES
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        for suffix in suffixes:
            if reg_entry.unique_id == f"{entry.entry_id}_{suffix}":
                ids[suffix] = reg_entry.entity_id
    return ids


def _hazards_markdown(ids: dict[str, str]) -> str:
    """Jinja template rendering the official warning texts of active hazards."""
    entities = ", ".join(
        f"'{ids[suffix]}'" for suffix in _HAZARD_SUFFIXES[1:] if suffix in ids
    )
    return (
        "{% set entities = [" + entities + "] %}\n"
        "{% set active = namespace(any=false) %}\n"
        "{% for e in entities if states(e) | int(0) > 0 %}\n"
        "{% set active.any = true %}\n"
        "#### {{ (state_attr(e, 'friendly_name') or e) | replace('Naturgefahrenportal ', '') }}"
        " — Stufe {{ states(e) }}\n"
        "{{ state_attr(e, 'description') }}\n"
        "{% if state_attr(e, 'outlook_level') %}*Vorwarnung: Stufe "
        "{{ state_attr(e, 'outlook_level') }}*\n{% endif %}"
        "{% if state_attr(e, 'expires') %}*Gültig bis "
        "{{ as_timestamp(state_attr(e, 'expires')) | timestamp_custom('%d.%m.%Y %H:%M') }}*\n"
        "{% endif %}\n"
        "{% endfor %}\n"
        "{% if not active.any %}Zurzeit keine Naturgefahren-Warnungen für diesen Ort."
        "{% endif %}"
    )


def _hazards_text_card(ids: dict[str, str]) -> dict:
    """Markdown card with the official warning texts, stacked vertically."""
    return {
        "type": "markdown",
        "content": _hazards_markdown(ids),
        "grid_options": {"columns": 12},
    }


def _hazards_section(ids: dict[str, str], include_text: bool = False) -> dict:
    """Build the natural hazards dashboard section (native cards only).

    The warning-text card normally lives in the narrow "Zuhause" column so
    the texts stack vertically; include_text adds it here instead for the
    self-contained section appended to pre-existing dashboards.
    """
    tiles = [
        {
            "type": "tile",
            "entity": ids[suffix],
            "color": "amber",
            "grid_options": {"columns": 6},
        }
        for suffix in _HAZARD_SUFFIXES[1:]
        if suffix in ids
    ]
    cards = [
        {
            "type": "heading",
            "heading": "Naturgefahren",
            "icon": "mdi:alert-octagram",
            "badges": [
                {
                    "type": "entity",
                    "entity": ids["highest_hazard"],
                    "show_state": True,
                }
            ],
        },
        {
            "type": "tile",
            "entity": ids["highest_hazard"],
            "color": "red",
            "grid_options": {"columns": 12},
        },
    ]
    if include_text:
        cards.append(_hazards_text_card(ids))
    return {"type": "grid", "column_span": 2, "cards": [*cards, *tiles]}


async def _async_append_hazards_section(
    hass: HomeAssistant, entry: ConfigEntry, lovelace_data
) -> None:
    """Append the hazards section to an existing dashboard exactly once."""
    ids = _entity_ids(hass, entry)
    if "highest_hazard" not in ids:
        return  # hazards source not enabled
    storage = lovelace_data.dashboards.get(DASHBOARD_URL_PATH)
    if storage is None:
        return
    try:
        config = await storage.async_load(False)
    except HomeAssistantError as err:
        _LOGGER.debug("Could not load dashboard config: %s", err)
        return
    if not isinstance(config, dict) or not config.get("views"):
        return
    if ids["highest_hazard"] in json.dumps(config):
        return  # already present (auto-added earlier or placed by the user)
    sections = config["views"][0].setdefault("sections", [])
    sections.append(_hazards_section(ids, include_text=True))
    try:
        await storage.async_save(config)
    except HomeAssistantError as err:
        _LOGGER.warning("Could not add the hazards section to the dashboard: %s", err)
        return
    _LOGGER.info("Added the natural hazards section to the Alerts dashboard")


def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Build the initial dashboard configuration."""
    ids = _entity_ids(hass, entry)
    active = ids.get("active_alerts", "sensor.alertswiss_active_alerts")
    home_count = ids.get("home_alerts", "sensor.alertswiss_home_alerts")
    affected = ids.get("home_affected", "binary_sensor.alertswiss_home_affected")

    home_extra = []
    sections_extra = []
    if "highest_hazard" in ids:
        home_extra.append(_hazards_text_card(ids))
        sections_extra.append(_hazards_section(ids))

    return {
        "views": [
            {
                "title": "Meldungen",
                "path": "meldungen",
                "type": "sections",
                "icon": DASHBOARD_ICON,
                "max_columns": 2,
                "header": {
                    "layout": "responsive",
                    "card": {
                        "type": "markdown",
                        "text_only": True,
                        "content": "# Behördenmeldungen Alertswiss\nOffizielle Meldungen des Bundesamts für Bevölkerungsschutz",
                    },
                },
                "sections": [
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "custom:alertswiss-ticker-card",
                                "entity": active,
                                "seconds_per_item": 4,
                                "empty_text": "Keine aktiven Meldungen",
                            }
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Zuhause", "icon": "mdi:home-alert"},
                            {"type": "tile", "entity": affected, "color": "red", "grid_options": {"columns": 6}},
                            {"type": "tile", "entity": home_count, "name": "Anzahl Meldungen", "color": "orange", "grid_options": {"columns": 6}},
                            {"type": "custom:alertswiss-alert-card", "entity": affected},
                            *home_extra,
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Karte", "icon": "mdi:map-marker-alert"},
                            {
                                "type": "map",
                                "geo_location_sources": [DOMAIN],
                                "entities": ["zone.home"],
                                "default_zoom": 8,
                                "theme_mode": "auto",
                                "grid_options": {"columns": 12, "rows": 6},
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "Alle Meldungen Schweiz",
                                "icon": "mdi:format-list-bulleted",
                                "badges": [{"type": "entity", "entity": active, "show_state": True}],
                            },
                            {
                                "type": "custom:alertswiss-list-card",
                                "entity": active,
                                "show_time": True,
                                "show_distance": True,
                            },
                        ],
                    },
                    *sections_extra,
                ],
            },
        ]
    }
