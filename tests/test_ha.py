"""Real HA framework classes, temporary config, fake transport, no live devices."""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
from types import MappingProxyType
import unittest
from unittest.mock import AsyncMock, Mock, patch

if importlib.util.find_spec("homeassistant") is None:
    raise unittest.SkipTest("Requires real Home Assistant 2026.10.4 runtime")

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.yutai_wifi import async_setup_entry, async_unload_entry
from custom_components.yutai_wifi.client import (
    CannotConnect,
    CommandFailed,
    Identity,
    PlugClient,
    Snapshot,
    UnsupportedModel,
    WrongDevice,
)
from custom_components.yutai_wifi.config_flow import YutaiWifiConfigFlow
from custom_components.yutai_wifi.const import DOMAIN
from custom_components.yutai_wifi.coordinator import PlugCoordinator
from custom_components.yutai_wifi.diagnostics import async_get_config_entry_diagnostics
from custom_components.yutai_wifi.sensor import DESCRIPTIONS, PlugSensor
from custom_components.yutai_wifi.switch import PlugSwitch

MAC = "020000000001"
TOKEN = "11" * 16
HOST = "198.51.100.10"
MODEL = "yutai.plug.jdls1"


def snapshot(mac=MAC, on=False):
    return Snapshot(
        Identity(MODEL, mac, "test", "test"),
        {
            "relay": on,
            "energy": 0.25,
            "power": 5,
            "current": 0.04,
            "voltage": 230,
        },
    )


def make_entry(mac=MAC):
    return config_entries.ConfigEntry(
        data={"host": HOST, "token": TOKEN, "mac": mac, "model": MODEL},
        discovery_keys=MappingProxyType({}),
        domain=DOMAIN,
        minor_version=1,
        options={},
        source=config_entries.SOURCE_USER,
        subentries_data=[],
        title="Synthetic socket",
        unique_id=mac,
        version=1,
    )


class HATests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yutai-wifi-test-")
        self.addCleanup(self.temp.cleanup)
        self.hass = HomeAssistant(self.temp.name)
        self.hass.config_entries = config_entries.ConfigEntries(self.hass, {})
        self.entry = make_entry()
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        self.patches = []
        self.mock("homeassistant.config_entries.ConfigEntries._async_schedule_save")
        self.mock(
            "custom_components.yutai_wifi.client.PlugClient._get_device",
            side_effect=AssertionError("Real device I/O is forbidden in framework tests"),
        )
        self.client = Mock()
        self.client.read.return_value = snapshot()
        self.client.set_relay.side_effect = lambda on: snapshot(on=on)
        self.coordinator = PlugCoordinator(self.hass, self.entry, self.client)

    def mock(self, target, **kwargs):
        item = patch(target, **kwargs)
        self.patches.append(item)
        return item.start()

    async def asyncTearDown(self):
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        for item in reversed(self.patches):
            item.stop()

    def flow(self, reconfigure=False):
        flow = YutaiWifiConfigFlow()
        flow.hass = self.hass
        flow.handler = DOMAIN
        flow.context = {"source": "reconfigure" if reconfigure else "user"}
        if reconfigure:
            flow.context["entry_id"] = self.entry.entry_id
        return flow

    async def test_refresh_and_entities_use_real_framework(self):
        await self.coordinator.async_refresh()
        switch = PlugSwitch(self.coordinator, self.entry)
        self.assertTrue(switch.available)
        self.assertFalse(switch.is_on)
        for description in DESCRIPTIONS:
            entity = PlugSensor(self.coordinator, self.entry, description)
            self.assertTrue(entity.available)
            self.assertEqual(entity.unique_id, f"{MAC}_{description.key}")
        energy = next(item for item in DESCRIPTIONS if item.key == "energy")
        self.assertIsNone(energy.state_class)
        self.client.set_relay.assert_not_called()

    async def test_entity_partial_and_whole_failure_availability(self):
        data = snapshot()
        data.values["voltage"] = None
        self.client.read.return_value = data
        await self.coordinator.async_refresh()
        voltage = PlugSensor(self.coordinator, self.entry, DESCRIPTIONS[0])
        self.assertFalse(voltage.available)
        self.assertIsNone(voltage.native_value)
        self.assertTrue(PlugSwitch(self.coordinator, self.entry).available)
        self.client.read.side_effect = CannotConnect()
        await self.coordinator.async_refresh()
        self.assertFalse(PlugSwitch(self.coordinator, self.entry).available)

    async def test_commands_update_only_confirmed_state(self):
        await self.coordinator.async_refresh()
        switch = PlugSwitch(self.coordinator, self.entry)
        await switch.async_turn_on()
        self.assertTrue(switch.is_on)
        await switch.async_turn_off()
        self.assertFalse(switch.is_on)
        self.assertEqual([call.args for call in self.client.set_relay.call_args_list], [(True,), (False,)])

    async def test_command_failure_marks_unavailable_and_raises(self):
        await self.coordinator.async_refresh()
        self.client.set_relay.side_effect = CommandFailed()
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.async_set_relay(True)
        self.assertFalse(self.coordinator.last_update_success)
        self.assertFalse(self.coordinator.data.values["relay"])

    async def test_identity_failure_becomes_sanitized_update_error(self):
        for error in (CannotConnect(), WrongDevice(), UnsupportedModel()):
            self.client.read.side_effect = error
            with self.assertRaises(UpdateFailed) as caught:
                await self.coordinator._async_update_data()
            self.assertNotIn(TOKEN, str(caught.exception))

    async def test_two_coordinators_have_separate_state_and_entity_ids(self):
        other_entry = make_entry("020000000002")
        other_client = Mock()
        other_client.read.return_value = snapshot(other_entry.unique_id)
        other = PlugCoordinator(self.hass, other_entry, other_client)
        await self.coordinator.async_refresh()
        await other.async_refresh()
        await self.coordinator.async_set_relay(True)
        first_switch = PlugSwitch(self.coordinator, self.entry)
        second_switch = PlugSwitch(other, other_entry)
        self.assertTrue(first_switch.is_on)
        self.assertFalse(second_switch.is_on)
        self.assertNotEqual(first_switch.unique_id, second_switch.unique_id)
        self.assertNotEqual(first_switch.device_info["identifiers"], second_switch.device_info["identifiers"])
        other_client.set_relay.assert_not_called()

    async def test_cancellation_does_not_release_io_lock_early(self):
        entered, release = Event(), Event()

        def slow_read():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Synthetic deadline")
            return snapshot()

        self.client.read.side_effect = slow_read
        read_task = asyncio.create_task(self.coordinator._async_update_data())
        await asyncio.to_thread(entered.wait, 1)
        read_task.cancel()
        command = asyncio.create_task(self.coordinator.async_set_relay(True))
        try:
            await asyncio.sleep(0.03)
            self.client.set_relay.assert_not_called()
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await read_task
        await command
        self.client.set_relay.assert_called_once_with(True)

    async def test_flow_invalid_fields_never_start_network(self):
        result = await self.flow().async_step_user({"host": "localhost", "token": "bad"})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"host": "invalid_host", "token": "invalid_token"})

    async def test_flow_adds_second_device_without_shared_identity(self):
        self.mock(
            "custom_components.yutai_wifi.config_flow.PlugClient.read", return_value=snapshot("020000000002")
        )
        result = await self.flow().async_step_user({"host": HOST, "token": TOKEN, "name": "Desk"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "Desk")
        self.assertEqual(result["data"]["mac"], "020000000002")

    async def test_flow_duplicate_physical_device_aborts(self):
        self.mock("custom_components.yutai_wifi.config_flow.PlugClient.read", return_value=snapshot())
        with self.assertRaises(AbortFlow) as caught:
            await self.flow().async_step_user({"host": HOST, "token": TOKEN})
        self.assertEqual(caught.exception.reason, "already_configured")

    async def test_flow_connection_model_and_identity_errors(self):
        for error, expected in (
            (CannotConnect(), "cannot_connect"),
            (UnsupportedModel(), "unsupported_model"),
            (WrongDevice(), "wrong_device"),
        ):
            with patch.object(PlugClient, "read", side_effect=error):
                result = await self.flow().async_step_user({"host": HOST, "token": TOKEN})
            self.assertEqual(result["errors"]["base"], expected)

    async def test_reconfigure_form_does_not_prefill_token(self):
        result = await self.flow(True).async_step_reconfigure()
        for field in result["data_schema"].schema:
            if str(field) == "token":
                default = field.default() if callable(field.default) else field.default
                self.assertNotEqual(default, TOKEN)

    async def test_reconfigure_keeps_blank_token_and_checks_identity(self):
        flow = self.flow(True)
        captured = []

        def read(client):
            captured.append(client)
            return snapshot()

        with (
            patch.object(PlugClient, "read", read),
            patch.object(
                flow,
                "async_update_reload_and_abort",
                return_value={"type": "abort", "reason": "reconfigure_successful"},
            ) as update,
        ):
            result = await flow.async_step_reconfigure({"host": "198.51.100.11", "token": ""})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(captured[0]._expected_mac, MAC)
        self.assertEqual(captured[0]._token, TOKEN)
        self.assertEqual(update.call_args.kwargs["data_updates"]["host"], "198.51.100.11")

    async def test_setup_first_refresh_only_reads_and_unload_only_unloads(self):
        object.__setattr__(self.entry, "state", config_entries.ConfigEntryState.SETUP_IN_PROGRESS)
        forward = self.mock(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups", new_callable=AsyncMock
        )
        unload = self.mock(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        )
        with patch("custom_components.yutai_wifi.client.PlugClient", return_value=self.client):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
        forward.assert_awaited_once()
        self.client.set_relay.assert_not_called()
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        unload.assert_awaited_once()
        self.client.set_relay.assert_not_called()

    async def test_failed_first_refresh_never_forwards_platforms(self):
        object.__setattr__(self.entry, "state", config_entries.ConfigEntryState.SETUP_IN_PROGRESS)
        self.client.read.side_effect = CannotConnect()
        forward = self.mock(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups", new_callable=AsyncMock
        )
        with patch("custom_components.yutai_wifi.client.PlugClient", return_value=self.client):
            with self.assertRaises(ConfigEntryNotReady):
                await async_setup_entry(self.hass, self.entry)
        forward.assert_not_awaited()

    async def test_diagnostics_omit_credentials_identifiers_and_measurements(self):
        await self.coordinator.async_refresh()
        self.entry.runtime_data = self.coordinator
        result = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(set(result), {"model", "poll_seconds", "last_update_success", "available_fields"})
        encoded = json.dumps(result)
        for secret in (TOKEN, HOST, MAC, "Synthetic socket", "230"):
            self.assertNotIn(secret, encoded)


if __name__ == "__main__":
    unittest.main()
