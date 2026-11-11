"""Stable per-device entity identity."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, CONF_MODEL, DOMAIN


class PlugEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data[CONF_MAC]}_{key}"
        self.key = key
        identity = coordinator.data.identity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_MAC])},
            name=entry.title,
            manufacturer="Yutai",
            model=entry.data[CONF_MODEL],
            sw_version=identity.firmware,
            hw_version=identity.hardware,
        )

    @property
    def available(self):
        return super().available and self.coordinator.data.values.get(self.key) is not None
