"""Config flow for the Swiss Public Alerts integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import AlertswissApiError, AlertswissClient
from .const import (
    CONF_LANGUAGE,
    CONF_MINIMUM_SEVERITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_MINIMUM_SEVERITY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LANGUAGES,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    SEVERITIES,
)


def _schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
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


class SwissPublicAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            client = AlertswissClient(
                async_get_clientsession(self.hass), user_input[CONF_LANGUAGE]
            )
            try:
                await client.async_fetch()
            except AlertswissApiError:
                errors["base"] = "cannot_connect"
            else:
                user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
                return self.async_create_entry(title="Swiss Public Alerts", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SwissPublicAlertsOptionsFlow()


class SwissPublicAlertsOptionsFlow(OptionsFlow):
    """Allow changing language, severity and interval without re-adding."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults))
