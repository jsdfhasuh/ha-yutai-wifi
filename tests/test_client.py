"""Synthetic protocol tests. No real tokens, cloud account or device access."""

from copy import deepcopy
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.yutai_wifi.client import (
    CannotConnect,
    CommandFailed,
    PlugClient,
    UnsupportedModel,
    WrongDevice,
    normalize_host,
    normalize_mac,
    normalize_token,
)
from custom_components.yutai_wifi.models import JDLS1, PROFILES

HOST = "198.51.100.10"
TOKEN = "11" * 16
MAC = "02:00:00:00:00:01"


def response(relay=False):
    values = {"relay": relay, "energy": 0.25, "power": 5, "current": 0.04, "voltage": 230}
    return [
        {"did": prop.key, "siid": prop.siid, "piid": prop.piid, "code": 0, "value": values[prop.key]}
        for prop in JDLS1.properties
    ]


class FakeDevice:
    def __init__(self, *_args, **_kwargs):
        self.calls = []
        self.info_count = 0
        self.model = JDLS1.model
        self.mac = MAC
        self.reply = response()
        self.ack = [{"did": "relay", "siid": 2, "piid": 1, "code": 0}]
        self.apply_write = True
        self.error = None
        self.handshake_count = 0
        self.needs_handshake = True
        self.handshake_error = None

    def send_handshake(self):
        self.handshake_count += 1
        if self.handshake_error:
            raise self.handshake_error
        self.needs_handshake = False

    def info(self, *, skip_cache):
        assert skip_cache is True
        self.info_count += 1
        if self.needs_handshake:
            raise TimeoutError("Synthetic stale MiIO session")
        if self.error:
            raise self.error
        logging.getLogger("miio.miioprotocol").warning("private fixture %s", TOKEN)
        return SimpleNamespace(
            model=self.model, mac_address=self.mac, firmware_version="test", hardware_version="test"
        )

    def send(self, method, parameters, *, retry_count):
        assert retry_count == 0
        self.calls.append((method, deepcopy(parameters)))
        if method == "get_properties":
            return deepcopy(self.reply)
        if method == "set_properties":
            if self.apply_write:
                self.reply[0]["value"] = parameters[0]["value"]
            if isinstance(self.ack, Exception):
                raise self.ack
            return deepcopy(self.ack)
        raise AssertionError("Unexpected network method")


def make_client(device=None, **kwargs):
    device = device or FakeDevice()
    return PlugClient(HOST, TOKEN, device_factory=lambda *a, **k: device, **kwargs), device


class ClientTests(unittest.TestCase):
    def test_read_only_and_no_cloud_identity_required(self):
        client, device = make_client()
        snapshot = client.read()
        self.assertEqual(snapshot.identity.mac, normalize_mac(MAC))
        self.assertEqual(snapshot.values["voltage"], 230)
        self.assertEqual([method for method, _ in device.calls], ["get_properties"])
        self.assertEqual(len(device.calls[0][1]), 5)
        self.assertEqual(device.retry_count, 0)

    def test_identity_is_rechecked_on_every_read(self):
        client, device = make_client(expected_mac=MAC, expected_model=JDLS1.model)
        client.read()
        client.read()
        self.assertEqual(device.info_count, 2)
        self.assertEqual(device.handshake_count, 2)

    def test_idle_poll_resynchronizes_before_identity_read(self):
        client, device = make_client()
        client.read()
        device.needs_handshake = True
        self.assertEqual(client.read().values["voltage"], 230)
        self.assertEqual(device.handshake_count, 2)
        self.assertEqual([method for method, _ in device.calls], ["get_properties", "get_properties"])

    def test_write_after_idle_handshakes_but_never_replays_write(self):
        client, device = make_client()
        client.read()
        device.needs_handshake = True
        self.assertTrue(client.set_relay(True).values["relay"])
        self.assertEqual(device.handshake_count, 2)
        self.assertEqual(sum(method == "set_properties" for method, _ in device.calls), 1)

    def test_handshake_failure_is_sanitized_and_next_read_recovers(self):
        client, device = make_client()
        device.handshake_error = TimeoutError(TOKEN)
        with self.assertRaises(CannotConnect) as caught:
            client.read()
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertEqual(device.calls, [])
        device.handshake_error = None
        self.assertEqual(client.read().values["voltage"], 230)

    def test_unknown_model_rejected_without_property_commands(self):
        client, device = make_client()
        device.model = "yutai.plug.unknown"
        with self.assertRaises(UnsupportedModel):
            client.read()
        self.assertEqual(device.calls, [])

    def test_mac_and_model_changes_refuse_reads_and_writes(self):
        for changed in ("mac", "model"):
            for command in (False, True):
                with self.subTest(changed=changed, command=command):
                    client, device = make_client(expected_mac=MAC, expected_model=JDLS1.model)
                    setattr(device, changed, "02:00:00:00:00:02" if changed == "mac" else "other.plug.model")
                    with self.assertRaises(WrongDevice):
                        client.set_relay(True) if command else client.read()
                    self.assertEqual(device.calls, [])

    def test_bad_identity_sanitized(self):
        client, device = make_client()
        device.mac = None
        with self.assertRaises(CannotConnect) as caught:
            client.read()
        self.assertEqual(str(caught.exception), "")

    def test_library_error_sanitized(self):
        client, device = make_client()
        device.error = RuntimeError(TOKEN)
        with self.assertRaises(CannotConnect) as caught:
            client.read()
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_library_logs_suppressed_only_inside_request(self):
        client, _ = make_client()
        with self.assertLogs("miio.miioprotocol", level="WARNING") as captured:
            client.read()
            logging.getLogger("miio.miioprotocol").warning("unrelated operation")
        self.assertEqual(len(captured.output), 1)
        self.assertNotIn(TOKEN, captured.output[0])

    def test_partial_measurement_failure_is_unavailable_not_zero(self):
        client, device = make_client()
        device.reply[2] = {"did": "power", "siid": 3, "piid": 2, "code": -1}
        snapshot = client.read()
        self.assertIsNone(snapshot.values["power"])
        self.assertEqual(snapshot.values["voltage"], 230)

    def test_missing_optional_measurement_is_not_stale(self):
        client, device = make_client()
        self.assertEqual(client.read().values["voltage"], 230)
        device.reply.pop()
        self.assertIsNone(client.read().values["voltage"])

    def test_invalid_numeric_values_unavailable(self):
        for value in (True, "230", -1, 65536, float("inf"), float("nan"), 230.5, None):
            with self.subTest(value=value):
                client, device = make_client()
                device.reply[4]["value"] = value
                self.assertIsNone(client.read().values["voltage"])

    def test_zero_measurements_are_valid(self):
        client, device = make_client()
        for item in device.reply[1:]:
            item["value"] = 0
        self.assertEqual(list(client.read().values.values()), [False, 0, 0, 0, 0])

    def test_bad_relay_or_missing_relay_fails(self):
        for value in (0, 1, "on", None):
            client, device = make_client()
            device.reply[0]["value"] = value
            with self.subTest(value=value), self.assertRaises(CannotConnect):
                client.read()
        client, device = make_client()
        device.reply.pop(0)
        with self.assertRaises(CannotConnect):
            client.read()

    def test_reordered_reply_is_matched_by_identity(self):
        client, device = make_client()
        device.reply.reverse()
        self.assertEqual(client.read().values["current"], 0.04)

    def test_malformed_or_ambiguous_replies_fail(self):
        invalid = [None, {}, [None], response() + [response()[0]]]
        for key, value in (("siid", True), ("piid", 999), ("did", "wrong"), ("code", False)):
            items = response()
            items[0][key] = value
            invalid.append(items)
        for reply in invalid:
            client, device = make_client()
            device.reply = reply
            with self.subTest(reply=reply), self.assertRaises(CannotConnect):
                client.read()

    def test_on_off_have_readback_and_no_toggle_method(self):
        client, device = make_client(expected_mac=MAC, expected_model=JDLS1.model)
        self.assertIs(client.set_relay(True).values["relay"], True)
        self.assertIs(client.set_relay(False).values["relay"], False)
        self.assertEqual(
            [call[0] for call in device.calls],
            ["set_properties", "get_properties", "set_properties", "get_properties"],
        )
        self.assertEqual(device.info_count, 2)

    def test_failed_ack_is_not_success_and_is_not_retried(self):
        invalid = [
            None,
            [],
            {},
            [None],
            [{"did": "relay", "siid": 2, "piid": 1, "code": -1}],
            [{"did": "relay", "siid": 2, "piid": 1, "code": False}],
            [{"did": "other", "siid": 2, "piid": 1, "code": 0}],
            TimeoutError(TOKEN),
        ]
        for ack in invalid:
            client, device = make_client()
            device.ack = ack
            with self.subTest(ack=type(ack)), self.assertRaises(CommandFailed):
                client.set_relay(True)
            self.assertEqual(len(device.calls), 1)

    def test_ack_without_state_change_is_failure(self):
        client, device = make_client()
        device.apply_write = False
        with self.assertRaises(CommandFailed):
            client.set_relay(True)

    def test_two_devices_keep_separate_state(self):
        first, first_device = make_client()
        second, second_device = make_client()
        first.set_relay(True)
        self.assertIs(first.read().values["relay"], True)
        self.assertIs(second.read().values["relay"], False)
        self.assertIsNot(first_device, second_device)

    def test_non_boolean_write_rejected_before_network(self):
        client, device = make_client()
        for value in (0, 1, "on", None):
            with self.assertRaises(ValueError):
                client.set_relay(value)
        self.assertEqual(device.info_count, 0)


class ValidationTests(unittest.TestCase):
    def test_host_accepts_only_specific_ipv4(self):
        self.assertEqual(normalize_host(" 198.51.100.10 "), HOST)
        for value in (
            "localhost",
            "::1",
            "0.0.0.0",
            "127.0.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "example.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_host(value)

    def test_token_format(self):
        self.assertEqual(normalize_token("AB" * 16), "ab" * 16)
        for value in ("", "x" * 32, "a" * 31, "a" * 33):
            with self.assertRaises(ValueError):
                normalize_token(value)

    def test_mac_normalization_and_profile_boundary(self):
        self.assertEqual(normalize_mac(MAC), "020000000001")
        self.assertEqual(normalize_mac("02-00-00-00-00-01"), "020000000001")
        with self.assertRaises(ValueError):
            normalize_mac("00:00:00:00:00:00")
        self.assertEqual(list(PROFILES), ["yutai.plug.jdls1"])


if __name__ == "__main__":
    unittest.main()
