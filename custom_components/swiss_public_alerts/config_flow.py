"""Config flow for the Swiss Public Alerts integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import AlertswissApiError, AlertswissClient
from .const import (
    CONF_DATA_SOURCES,
    CONF_LANGUAGE,
    CONF_MINIMUM_SEVERITY,
    CONF_PLZ,
    CONF_UPDATE_INTERVAL,
    DATA_SOURCES,
    DEFAULT_DATA_SOURCES,
    DEFAULT_LANGUAGE,
    DEFAULT_MINIMUM_SEVERITY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LANGUAGES,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    SEVERITIES,
    SOURCE_ALERTSWISS,
    SOURCE_HAZARDS,
)
from .hazards import HazardsApiError, HazardsClient, find_location, load_locations


def _schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DATA_SOURCES,
                default=defaults.get(CONF_DATA_SOURCES, DEFAULT_DATA_SOURCES),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=DATA_SOURCES,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key="data_sources",
                )
            ),
            vol.Optional(CONF_PLZ, default=defaults.get(CONF_PLZ, "")): TextSelector(),
            vol.Required(
                CONF_LANGUAGE, default=defaults.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=LANGUAGES,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="language",
                )
            ),
            vol.Required(
                CONF_MINIMUM_SEVERITY,
                default=defaults.get(CONF_MINIMUM_SEVERITY, DEFAULT_MINIMUM_SEVERITY),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SEVERITIES,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="minimum_severity",
                )
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=30,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


async def _validate(hass: HomeAssistant, user_input: dict) -> dict[str, str]:
    """Validate the selected sources; returns a dict of form errors."""
    errors: dict[str, str] = {}
    sources = user_input.get(CONF_DATA_SOURCES) or []
    if not sources:
        errors[CONF_DATA_SOURCES] = "no_source"
        return errors

    session = async_get_clientsession(hass)
    if SOURCE_ALERTSWISS in sources:
        client = AlertswissClient(session, user_input[CONF_LANGUAGE])
        try:
            await client.async_fetch()
        except AlertswissApiError:
            errors["base"] = "cannot_connect"

    if SOURCE_HAZARDS in sources:
        plz = str(user_input.get(CONF_PLZ) or "").strip()
        if not plz:
            errors[CONF_PLZ] = "plz_required"
        else:
            locations = await hass.async_add_executor_job(load_locations)
            location = find_location(locations, plz)
            if location is None:
                errors[CONF_PLZ] = "plz_unknown"
            else:
                hazards = HazardsClient(session, user_input[CONF_LANGUAGE], location)
                try:
                    await hazards.async_fetch()
                except HazardsApiError:
                    errors["base"] = "cannot_connect"
    return errors


class SwissPublicAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
                user_input[CONF_PLZ] = str(user_input.get(CONF_PLZ) or "").strip()
                return self.async_create_entry(title="Swiss Public Alerts", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SwissPublicAlertsOptionsFlow()


class SwissPublicAlertsOptionsFlow(OptionsFlow):
    """Allow changing all settings without re-adding the integration."""

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
                user_input[CONF_PLZ] = str(user_input.get(CONF_PLZ) or "").strip()
                return self.async_create_entry(title="", data=user_input)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            defaults = {**defaults, **user_input}
        return self.async_show_form(
            step_id="init", data_schema=_schema(defaults), errors=errors
        )
