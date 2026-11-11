"""One authenticated physical device per entry; configuration performs reads only."""

import probatio as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .client import CannotConnect, PlugClient, UnsupportedModel, WrongDevice, normalize_host, normalize_token
from .const import CONF_MAC, CONF_MODEL, CONF_TOKEN, DOMAIN
from .models import PROFILES


class YutaiWifiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._configure("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._configure("reconfigure", user_input)

    async def _configure(self, step, user_input):
        errors = {}
        entry = self._get_reconfigure_entry() if step == "reconfigure" else None
        if user_input is not None:
            try:
                host = normalize_host(user_input.get(CONF_HOST, ""))
            except (ValueError, AttributeError):
                errors[CONF_HOST] = "invalid_host"
            token_input = user_input.get(CONF_TOKEN, "").strip()
            try:
                token = normalize_token(token_input or (entry.data[CONF_TOKEN] if entry else ""))
            except (ValueError, AttributeError):
                errors[CONF_TOKEN] = "invalid_token"
            if not errors:
                client = PlugClient(
                    host,
                    token,
                    expected_mac=entry.data[CONF_MAC] if entry else None,
                    expected_model=entry.data[CONF_MODEL] if entry else None,
                )
                try:
                    snapshot = await self.hass.async_add_executor_job(client.read)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except UnsupportedModel:
                    errors["base"] = "unsupported_model"
                except WrongDevice:
                    errors["base"] = "wrong_device"
                else:
                    identity = snapshot.identity
                    await self.async_set_unique_id(identity.mac)
                    if entry:
                        self._abort_if_unique_id_mismatch()
                    else:
                        self._abort_if_unique_id_configured()
                    data = {
                        CONF_HOST: host,
                        CONF_TOKEN: token,
                        CONF_MAC: identity.mac,
                        CONF_MODEL: identity.model,
                    }
                    if entry:
                        return self.async_update_reload_and_abort(entry, data_updates=data)
                    name = user_input.get(CONF_NAME, "").strip() or PROFILES[identity.model].name
                    return self.async_create_entry(title=name, data=data)

        host_field = (
            vol.Required(CONF_HOST, default=entry.data[CONF_HOST]) if entry else vol.Required(CONF_HOST)
        )
        token_field = vol.Optional(CONF_TOKEN) if entry else vol.Required(CONF_TOKEN)
        fields = {
            host_field: TextSelector(),
            token_field: TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
        if not entry:
            fields[vol.Optional(CONF_NAME)] = TextSelector()
        return self.async_show_form(step_id=step, data_schema=vol.Schema(fields), errors=errors)
