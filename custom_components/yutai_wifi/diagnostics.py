"""Allowlisted diagnostics; no addresses, names, tokens, payloads or measurements."""

from .const import CONF_MODEL, POLL_SECONDS


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = getattr(entry, "runtime_data", None)
    return {
        "model": entry.data[CONF_MODEL],
        "poll_seconds": POLL_SECONDS,
        "last_update_success": coordinator.last_update_success if coordinator else False,
        "available_fields": sorted(key for key, value in coordinator.data.values.items() if value is not None)
        if coordinator and coordinator.data
        else [],
    }
