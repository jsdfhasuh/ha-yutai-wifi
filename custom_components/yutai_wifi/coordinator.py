"""Serialized executor I/O, bounded polling, and verified command state."""

import asyncio
from datetime import timedelta
import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import CannotConnect, CommandFailed, UnsupportedModel, WrongDevice
from .const import DOMAIN, POLL_SECONDS

_LOGGER = logging.getLogger(__name__)


class PlugCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=POLL_SECONDS),
            always_update=False,
        )
        self.client = client
        self._io_lock = asyncio.Lock()

    async def _run(self, method, *args):
        future = self.hass.async_add_executor_job(method, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # A cancelled coroutine must not release the I/O lock before its thread ends.
            try:
                await future
            except Exception:
                pass
            raise

    async def _async_update_data(self):
        async with self._io_lock:
            try:
                return await self._run(self.client.read)
            except (CannotConnect, UnsupportedModel, WrongDevice):
                raise UpdateFailed("Local device identity or property read failed") from None

    async def async_set_relay(self, on):
        async with self._io_lock:
            try:
                snapshot = await self._run(self.client.set_relay, on)
            except (CannotConnect, CommandFailed, UnsupportedModel, WrongDevice):
                self.async_set_update_error(UpdateFailed("Relay result is unconfirmed"))
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                ) from None
            self.async_set_updated_data(snapshot)
