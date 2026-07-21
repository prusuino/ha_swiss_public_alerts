"""The Swiss Public Alerts integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Alert, AlertswissApiError, AlertswissClient, FeedData
from .const import (
    CONF_LANGUAGE,
    CONF_MINIMUM_SEVERITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_MINIMUM_SEVERITY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SEVERITY_RANK,
    STATIC_URL_BASE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "geo_location", "sensor"]


class AlertswissCoordinator(DataUpdateCoordinator[FeedData]):
    """Coordinator polling the Alertswiss feed."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.client = AlertswissClient(
            async_get_clientsession(hass), self._option(entry, CONF_LANGUAGE, DEFAULT_LANGUAGE)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=self._option(entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
        )

    @staticmethod
    def _option(entry: ConfigEntry, key: str, default):
        return entry.options.get(key, entry.data.get(key, default))

    @property
    def minimum_severity_rank(self) -> int:
        severity = self._option(self.entry, CONF_MINIMUM_SEVERITY, DEFAULT_MINIMUM_SEVERITY)
        return SEVERITY_RANK.get(severity, 1)

    def apply_options(self) -> None:
        """Apply changed options without reloading the entry."""
        self.client.language = self._option(self.entry, CONF_LANGUAGE, DEFAULT_LANGUAGE)
        self.update_interval = timedelta(
            seconds=self._option(self.entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )

    async def _async_update_data(self) -> FeedData:
        try:
            return await self.client.async_fetch()
        except AlertswissApiError as err:
            raise UpdateFailed(str(err)) from err

    # ---- filtered views used by all platforms -------------------------------

    def relevant_alerts(self) -> list[Alert]:
        """Active (non all-clear) alerts at or above the configured severity."""
        if self.data is None:
            return []
        min_rank = self.minimum_severity_rank
        return [
            alert
            for alert in self.data.alerts
            if not alert.all_clear and SEVERITY_RANK.get(alert.severity, 0) >= min_rank
        ]

    def home_alerts(self) -> list[Alert]:
        """Relevant alerts whose area covers the Home Assistant home location."""
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        return [alert for alert in self.relevant_alerts() if alert.covers(lat, lon)]

    def summaries(self, alerts: list[Alert], full: bool = False) -> list[dict]:
        """Alert summaries enriched with the distance from the home location.

        With full=True the (potentially long) description and instructions are
        included — used only for the small home-alerts list to keep the
        Switzerland-wide sensor attributes lean.
        """
        lat = self.hass.config.latitude
        lon = self.hass.config.longitude
        result = []
        for alert in alerts:
            distance = alert.distance_km(lat, lon)
            summary = {
                **alert.summary,
                "distance_km": round(distance, 1) if distance is not None else None,
            }
            if full:
                summary["description"] = alert.description
                summary["instructions"] = list(alert.instructions)
            result.append(summary)
        return result


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swiss Public Alerts from a config entry."""
    if not hass.data.get(f"{DOMAIN}_static_registered"):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL_BASE,
                    str(Path(__file__).parent / "static"),
                    cache_headers=True,
                )
            ]
        )
        hass.data[f"{DOMAIN}_static_registered"] = True

    coordinator = AlertswissCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from . import dashboard

    await dashboard.async_ensure_dashboard(hass, entry)

    async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        coordinator.apply_options()
        await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up the auto-created dashboard when the integration is removed."""
    from . import dashboard

    await dashboard.async_remove_dashboard(hass)
