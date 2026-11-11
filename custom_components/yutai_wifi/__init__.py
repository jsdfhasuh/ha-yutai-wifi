"""Yutai Wi-Fi local integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import CONF_MAC, CONF_MODEL, CONF_TOKEN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import CONF_HOST, Platform

    from .client import PlugClient
    from .coordinator import PlugCoordinator

    client = PlugClient(
        entry.data[CONF_HOST],
        entry.data[CONF_TOKEN],
        expected_mac=entry.data[CONF_MAC],
        expected_model=entry.data[CONF_MODEL],
    )
    coordinator = PlugCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.SWITCH])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.SWITCH])
