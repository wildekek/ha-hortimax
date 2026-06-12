"""Config flow for the Ridder HortiMaX Pro (HortOS) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HortimaxApiClient, HortimaxApiError, HortimaxAuthError
from .const import (
    CONF_BASE_URL,
    CONF_SOURCE_TYPES,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


class HortimaxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def _async_validate(
        self, api_key: str, base_url: str
    ) -> tuple[str | None, list[str]]:
        """Authenticate and list devices; returns (organisation id, devices)."""
        client = HortimaxApiClient(
            async_get_clientsession(self.hass), api_key, base_url
        )
        auth = await client.async_authenticate()
        devices = await client.async_get_device_names()
        org = auth.get("organisation") or {}
        org_id = org.get("id")
        return (str(org_id) if org_id is not None else None, devices)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial step: ask for the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                org_id, devices = await self._async_validate(
                    user_input[CONF_API_KEY], user_input[CONF_BASE_URL]
                )
            except HortimaxAuthError:
                errors["base"] = "invalid_auth"
            except HortimaxApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating HortOS API")
                errors["base"] = "unknown"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    if org_id is not None:
                        await self.async_set_unique_id(org_id)
                        self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Ridder HortiMaX Pro", data=user_input
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start a reauthentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            base_url = reauth_entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            try:
                await self._async_validate(user_input[CONF_API_KEY], base_url)
            except HortimaxAuthError:
                errors["base"] = "invalid_auth"
            except HortimaxApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating HortOS API")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, **user_input},
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> HortimaxOptionsFlow:
        """Return the options flow."""
        return HortimaxOptionsFlow()


class HortimaxOptionsFlow(OptionsFlow):
    """Options: polling interval and source-type filtering."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Selecting every type (or none) means "no filter".
            available = self._available_source_types()
            if set(user_input.get(CONF_SOURCE_TYPES, [])) >= set(available):
                user_input[CONF_SOURCE_TYPES] = []
            return self.async_create_entry(data=user_input)

        available = self._available_source_types()
        selected = self.config_entry.options.get(CONF_SOURCE_TYPES) or available
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
        }
        if available:
            schema[
                vol.Required(CONF_SOURCE_TYPES, default=selected)
            ] = cv.multi_select(available)
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema)
        )

    def _available_source_types(self) -> list[str]:
        """All source types seen on the controllers (ignoring the filter)."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None:
            return sorted(self.config_entry.options.get(CONF_SOURCE_TYPES) or [])
        return sorted(coordinator.all_source_types)
