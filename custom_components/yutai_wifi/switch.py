"""Explicit ON/OFF only; no toggle actions or automatic power restoration."""

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity

from .entity import PlugEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PlugSwitch(entry.runtime_data, entry)])


class PlugSwitch(PlugEntity, SwitchEntity):
    _attr_translation_key = "relay"
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "relay")

    @property
    def is_on(self):
        return self.coordinator.data.values.get("relay")

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_relay(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_relay(False)
