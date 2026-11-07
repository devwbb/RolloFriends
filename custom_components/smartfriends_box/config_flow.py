"""Config flow for RolloFriends."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_HOST,
    CONF_PORT,
    DEFAULT_C_SYMBOL,
    DEFAULT_PORT,
    DEFAULT_SH_API_VERSION,
    DEFAULT_SHC_VERSION,
    DOMAIN,
    ZEROCONF_TYPE,
)
from .vendor.aiosmartfriends import (
    SmartFriendsAuthenticationError,
    SmartFriendsCertificateError,
    SmartFriendsClient,
    SmartFriendsConnectionError,
    SmartFriendsError,
    SmartFriendsTimeout,
    async_probe_identity,
    normalize_mac,
    parse_mdns_identity,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Validation:
    host: str
    port: int
    username: str
    password: str
    mac: str
    title: str
    shutter_count: int


USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): probatio.All(str, probatio.Length(min=1)),
        probatio.Optional(CONF_PORT, default=DEFAULT_PORT): probatio.All(
            probatio.Coerce(int),
            probatio.Range(min=1, max=65535),
        ),
        probatio.Required(CONF_USERNAME): probatio.All(str, probatio.Length(min=1)),
        probatio.Required(probatio.Secret(CONF_PASSWORD)): str,
    }
)

CREDENTIALS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): probatio.All(str, probatio.Length(min=1)),
        probatio.Required(probatio.Secret(CONF_PASSWORD)): str,
    }
)

PASSWORD_SCHEMA = probatio.Schema(
    {
        probatio.Required(probatio.Secret(CONF_PASSWORD)): str,
    }
)

RECONFIGURE_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): probatio.All(str, probatio.Length(min=1)),
        probatio.Optional(CONF_PORT, default=DEFAULT_PORT): probatio.All(
            probatio.Coerce(int),
            probatio.Range(min=1, max=65535),
        ),
        probatio.Required(CONF_USERNAME): probatio.All(str, probatio.Length(min=1)),
    }
)


async def _validate_credentials(
    host: str,
    port: int,
    username: str,
    password: str,
) -> tuple[_Validation | None, dict[str, str]]:
    """Open one read-only session, validate it, and close it again."""

    client = SmartFriendsClient(
        host,
        port,
        username,
        password,
        c_symbol=DEFAULT_C_SYMBOL,
        shc_version=DEFAULT_SHC_VERSION,
        sh_api_version=DEFAULT_SH_API_VERSION,
        auto_reconnect=False,
        poll_interval=60,
        connect_timeout=12,
    )
    try:
        gateway = await asyncio.wait_for(client.async_connect(), timeout=30)
        shutters = client.shutters
        mac = normalize_mac(gateway.mac_address)
        if mac is None:
            return None, {"base": "no_identity"}
        if not shutters:
            return None, {"base": "no_supported_devices"}
        title = f"SmartFriends Box {gateway.hardware or ''}".strip()
        return (
            _Validation(
                host=host,
                port=port,
                username=username,
                password=password,
                mac=mac,
                title=title,
                shutter_count=len(shutters),
            ),
            {},
        )
    except SmartFriendsAuthenticationError:
        return None, {"base": "invalid_auth"}
    except SmartFriendsCertificateError:
        return None, {"base": "certificate_error"}
    except (SmartFriendsConnectionError, SmartFriendsTimeout) as err:
        _LOGGER.warning("SmartFriends connection validation failed: %s", err)
        return None, {"base": "cannot_connect"}
    except SmartFriendsError as err:
        _LOGGER.warning("SmartFriends protocol validation failed: %s", err)
        return None, {"base": "cannot_connect"}
    except TimeoutError:
        return None, {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error while validating SmartFriends credentials")
        return None, {"base": "unknown"}
    finally:
        await client.async_disconnect()


def _without_password(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {key: value for key, value in data.items() if key != CONF_PASSWORD}


class SmartFriendsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle configuration, discovery, reauth and reconfiguration."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str | None = None
        self._discovered_mac: str | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        validation: _Validation | None = None
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            if not host:
                errors = {"base": "invalid_host"}
            elif not username:
                errors = {"base": "invalid_username"}
            else:
                validation, errors = await _validate_credentials(host, port, username, password)
            if validation is not None:
                await self.async_set_unique_id(validation.mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=validation.title,
                    data={
                        CONF_HOST: validation.host,
                        CONF_PORT: validation.port,
                        CONF_USERNAME: validation.username,
                        CONF_PASSWORD: validation.password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, _without_password(user_input)
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self,
        discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        if discovery_info.type not in (ZEROCONF_TYPE, "_smartHOME._tcp.local."):
            return self.async_abort(reason="not_smartfriends")

        host = str(discovery_info.ip_address)
        port = discovery_info.port or DEFAULT_PORT
        mdns = parse_mdns_identity(discovery_info.properties, discovery_info.name)
        try:
            identity = await async_probe_identity(host, port, timeout=5)
        except SmartFriendsCertificateError:
            return self.async_abort(reason="certificate_error")
        except (SmartFriendsConnectionError, SmartFriendsTimeout, SmartFriendsError):
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected error during SmartFriends discovery")
            return self.async_abort(reason="cannot_connect")

        if (
            mdns.mac_address is not None
            and identity.mac_address is not None
            and mdns.mac_address != identity.mac_address
        ):
            return self.async_abort(reason="identity_mismatch")
        mac = identity.mac_address or mdns.mac_address
        if mac is None:
            return self.async_abort(reason="no_identity")

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
        self._discovered_host = host
        self._discovered_port = port
        self._discovered_name = discovery_info.name
        self._discovered_mac = mac
        self.context["title_placeholders"] = {"name": discovery_info.name or "SmartFriends Box"}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._discovered_host is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            validation, errors = await _validate_credentials(
                self._discovered_host,
                self._discovered_port,
                username,
                password,
            )
            if validation is not None:
                if self._discovered_mac is not None and validation.mac != self._discovered_mac:
                    return self.async_abort(reason="identity_mismatch")
                return self.async_create_entry(
                    title=validation.title,
                    data={
                        CONF_HOST: validation.host,
                        CONF_PORT: validation.port,
                        CONF_USERNAME: validation.username,
                        CONF_PASSWORD: validation.password,
                    },
                )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, _without_password(user_input)
            ),
            errors=errors,
            description_placeholders={
                "name": self._discovered_name or "SmartFriends Box",
                "host": self._discovered_host or "",
            },
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            validation, errors = await _validate_credentials(
                entry.data[CONF_HOST],
                int(entry.data.get(CONF_PORT, DEFAULT_PORT)),
                entry.data[CONF_USERNAME],
                str(user_input[CONF_PASSWORD]),
            )
            if validation is not None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: validation.password},
                    reason="reauth_successful",
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        validation: _Validation | None = None
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            username = str(user_input[CONF_USERNAME]).strip()
            validation, errors = await _validate_credentials(
                host,
                port,
                username,
                entry.data[CONF_PASSWORD],
            )
            if validation is not None:
                if validation.mac != entry.unique_id:
                    errors = {"base": "identity_mismatch"}
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_HOST: validation.host,
                            CONF_PORT: validation.port,
                            CONF_USERNAME: validation.username,
                        },
                        reason="reconfigure_successful",
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                RECONFIGURE_SCHEMA,
                user_input
                or {
                    CONF_HOST: entry.data[CONF_HOST],
                    CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                    CONF_USERNAME: entry.data[CONF_USERNAME],
                },
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )
