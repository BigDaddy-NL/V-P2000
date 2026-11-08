"""Config flow for V-P2000."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_GROEPEN,
    CONF_GROEPEN_TEKST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME,
    USER_AGENT,
)
from .logic import GroepenError, groepen_to_text, parse_groepen
from .poller import build_url


def _schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_GROEPEN_TEKST): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


async def _api_ok(hass: HomeAssistant, groepen: list[dict[str, Any]]) -> bool:
    try:
        async with async_get_clientsession(hass).get(
            build_url(groepen),
            timeout=aiohttp.ClientTimeout(total=25),
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return False
    return isinstance(data, dict) and isinstance(data.get("meldingen"), list)


async def _validate(
    hass: HomeAssistant, user_input: dict[str, Any], errors: dict[str, str], placeholders: dict[str, str]
) -> dict[str, Any] | None:
    try:
        groepen = parse_groepen(user_input[CONF_GROEPEN_TEKST])
    except GroepenError as err:
        errors[CONF_GROEPEN_TEKST] = err.key
        placeholders["detail"] = err.detail
        return None
    if not await _api_ok(hass, groepen):
        errors["base"] = "geen_verbinding"
        return None
    return {CONF_GROEPEN: groepen, CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}


class V2000ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        if user_input is not None:
            if (options := await _validate(self.hass, user_input, errors, placeholders)) is not None:
                return self.async_create_entry(title=NAME, data={}, options=options)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input or {}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        try:
            groepen = parse_groepen(import_data[CONF_GROEPEN_TEKST])
        except GroepenError:
            return self.async_abort(reason="ongeldige_yaml")
        return self.async_create_entry(
            title=NAME,
            data={},
            options={CONF_GROEPEN: groepen, CONF_SCAN_INTERVAL: int(import_data[CONF_SCAN_INTERVAL])},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return V2000OptionsFlow()


class V2000OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        if user_input is not None:
            if (options := await _validate(self.hass, user_input, errors, placeholders)) is not None:
                return self.async_create_entry(data=options)
        current = {
            CONF_GROEPEN_TEKST: groepen_to_text(self.config_entry.options.get(CONF_GROEPEN, [])),
            CONF_SCAN_INTERVAL: self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input or current),
            errors=errors,
            description_placeholders=placeholders,
        )
