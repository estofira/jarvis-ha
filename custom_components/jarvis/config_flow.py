"""Config flow for Jarvis (Phase 9, spec 2026-11-09-1 §6.3).

Three fields: the gateway URL, Home Assistant's own bearer, and the language.
The language is also an option, so the O3 fallback is a settings change rather
than a reinstall. The bearer is stored in the config entry, as every HA
integration stores its credential.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BEARER,
    CONF_LANGUAGE,
    CONF_URL,
    DEFAULT_LANGUAGE,
    DOMAIN,
    LANGUAGES,
    VALIDATE_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class _InvalidAuth(Exception):
    """The gateway refused the bearer."""


class _CannotConnect(Exception):
    """The gateway did not answer as a gateway would."""


async def _validate(hass: HomeAssistant, url: str, bearer: str) -> None:
    """Two probes, neither of which reaches a model (§6.3).

    `POST /turn` with an empty object: the gateway checks the bearer before the
    body, so `400` proves the bearer and `401` refuses it. Anything else, a
    `200` included, means something other than the gateway answered.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(f"{url}/healthz", timeout=VALIDATE_TIMEOUT) as resp:
            if resp.status != 200:
                _LOGGER.debug("validate: healthz status=%s", resp.status)
                raise _CannotConnect
        async with session.post(
            f"{url}/turn",
            json={},
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=VALIDATE_TIMEOUT,
        ) as resp:
            status = resp.status
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        # The exception's type only: its text can carry the URL.
        _LOGGER.debug("validate: %s", type(err).__name__)
        raise _CannotConnect from err
    _LOGGER.debug("validate: turn status=%s", status)
    if status == 401:
        raise _InvalidAuth
    if status != 400:
        raise _CannotConnect


def _language_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_LANGUAGE, default=default): vol.In(LANGUAGES)})


class JarvisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Jarvis gateway."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            bearer = user_input[CONF_BEARER].strip()
            self._async_abort_entries_match({CONF_URL: url})
            try:
                await _validate(self.hass, url, bearer)
            except _InvalidAuth:
                errors["base"] = "invalid_auth"
            except _CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Jarvis",
                    data={CONF_URL: url, CONF_BEARER: bearer},
                    options={CONF_LANGUAGE: user_input[CONF_LANGUAGE]},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): str,
                vol.Required(CONF_BEARER): str,
                vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): vol.In(LANGUAGES),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JarvisOptionsFlow()


class JarvisOptionsFlow(OptionsFlow):
    """Change the language. Read per turn, so no reload is needed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        return self.async_show_form(step_id="init", data_schema=_language_schema(current))
