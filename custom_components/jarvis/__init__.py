"""Jarvis as a Home Assistant conversation agent (Phase 9, spec 2026-11-09-1).

Home Assistant hands the agent a transcript; the agent posts it to
`jarvis-gateway`'s `POST /turn` and streams Jarvis's text back into HA's chat
log. HA's own STT and TTS integrations do the listening and the speaking.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the conversation entity.

    Returns a boolean: 2026.10.4 requires one, and 2026.11.0 still accepts one
    from a custom integration.
    """
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the conversation entity."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
