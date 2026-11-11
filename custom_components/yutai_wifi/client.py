"""Synchronous, identity-checked MiIO boundary, with no cloud login or raw API."""

from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address
import logging
import re
from threading import Lock, local

from .const import REQUEST_TIMEOUT
from .models import PROFILES


class CannotConnect(Exception):
    """Communication, credentials, or reply validation failed."""


class UnsupportedModel(Exception):
    """No reviewed profile exists for the authenticated model."""


class WrongDevice(Exception):
    """The address now belongs to another authenticated physical device."""


class CommandFailed(Exception):
    """A command was rejected or its result could not be confirmed."""


def normalize_host(value: str) -> str:
    address = IPv4Address(value.strip())
    if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_reserved:
        raise ValueError("Invalid device address")
    return str(address)


def normalize_token(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("Invalid token format")
    return value


def normalize_mac(value: str) -> str:
    value = value.replace(":", "").replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{12}", value) or value == "0" * 12:
        raise ValueError("Invalid device identity")
    return value


_LOG_CONTEXT = local()


class _TransportLogFilter(logging.Filter):
    def filter(self, record):
        # python-miio debug messages can contain tokens and raw network payloads.
        return not getattr(_LOG_CONTEXT, "private_request", False)


_LOG_FILTER = _TransportLogFilter()


@contextmanager
def _private_transport():
    for name in ("miio.device", "miio.miioprotocol"):
        logging.getLogger(name).addFilter(_LOG_FILTER)
    previous = getattr(_LOG_CONTEXT, "private_request", False)
    _LOG_CONTEXT.private_request = True
    try:
        yield
    finally:
        _LOG_CONTEXT.private_request = previous


@dataclass(frozen=True)
class Identity:
    model: str
    mac: str
    firmware: str | None
    hardware: str | None


@dataclass(frozen=True)
class Snapshot:
    identity: Identity
    values: dict[str, bool | int | float | None]


class PlugClient:
    """One client per config entry; socket operations are serialized per device."""

    def __init__(self, host, token, *, expected_mac=None, expected_model=None, device_factory=None):
        self._host = normalize_host(host)
        self._token = normalize_token(token)
        self._expected_mac = normalize_mac(expected_mac) if expected_mac else None
        self._expected_model = expected_model
        self._factory = device_factory
        self._device = None
        self._lock = Lock()

    def _get_device(self):
        if self._device is None:
            factory = self._factory
            if factory is None:
                from miio import Device

                factory = Device
            self._device = factory(self._host, self._token, timeout=REQUEST_TIMEOUT)
            self._device.retry_count = 0
        return self._device

    def _identity(self) -> Identity:
        info = self._get_device().info(skip_cache=True)
        model = info.model
        mac = normalize_mac(info.mac_address)
        if self._expected_mac and self._expected_mac != mac:
            raise WrongDevice()
        if self._expected_model and self._expected_model != model:
            raise WrongDevice()
        if model not in PROFILES:
            raise UnsupportedModel()
        return Identity(model, mac, info.firmware_version, info.hardware_version)

    def _read(self, identity) -> Snapshot:
        profile = PROFILES[identity.model]
        request = [{"did": p.key, "siid": p.siid, "piid": p.piid} for p in profile.properties]
        response = self._get_device().send("get_properties", request, retry_count=0)
        if not isinstance(response, list):
            raise CannotConnect()
        known = {(p.siid, p.piid): p for p in profile.properties}
        values = {p.key: None for p in profile.properties}
        seen = set()
        for item in response:
            if not isinstance(item, dict):
                raise CannotConnect()
            pair = (item.get("siid"), item.get("piid"))
            if any(type(number) is not int for number in pair) or pair not in known or pair in seen:
                raise CannotConnect()
            seen.add(pair)
            prop = known[pair]
            if item.get("did") != prop.key:
                raise CannotConnect()
            if type(item.get("code")) is not int:
                raise CannotConnect()
            if item["code"] == 0 and prop.valid(item.get("value")):
                values[prop.key] = item["value"]
        if values["relay"] is None:
            raise CannotConnect()
        return Snapshot(identity, values)

    def read(self) -> Snapshot:
        with self._lock, _private_transport():
            try:
                return self._read(self._identity())
            except (CannotConnect, UnsupportedModel, WrongDevice):
                raise
            except Exception:
                raise CannotConnect() from None

    def set_relay(self, on: bool) -> Snapshot:
        if type(on) is not bool:
            raise ValueError("Relay state must be a boolean")
        with self._lock, _private_transport():
            try:
                identity = self._identity()
                relay = next(p for p in PROFILES[identity.model].properties if p.key == "relay")
                request = [{"did": "relay", "siid": relay.siid, "piid": relay.piid, "value": on}]
                response = self._get_device().send("set_properties", request, retry_count=0)
                if not isinstance(response, list) or len(response) != 1:
                    raise CommandFailed()
                result = response[0]
                if (
                    not isinstance(result, dict)
                    or any(
                        type(result.get(key)) is not int or result[key] != expected
                        for key, expected in (("siid", relay.siid), ("piid", relay.piid), ("code", 0))
                    )
                    or result.get("did") != "relay"
                ):
                    raise CommandFailed()
                snapshot = self._read(identity)
                if snapshot.values["relay"] is not on:
                    raise CommandFailed()
                return snapshot
            except (UnsupportedModel, WrongDevice, CommandFailed):
                raise
            except Exception:
                # A timeout may follow a successful physical action. Never retry a write.
                raise CommandFailed() from None
