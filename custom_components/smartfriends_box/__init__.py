"""RolloFriends — native SmartFriends Box integration."""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_HOST,
    CONF_PORT,
    DEFAULT_C_SYMBOL,
    DEFAULT_PORT,
    DEFAULT_SH_API_VERSION,
    DEFAULT_SHC_VERSION,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import SmartFriendsCoordinator
from .vendor.aiosmartfriends import (
    SmartFriendsAuthenticationError,
    SmartFriendsClient,
    SmartFriendsError,
    normalize_mac,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SmartFriendsRuntimeData:
    client: SmartFriendsClient
    coordinator: SmartFriendsCoordinator
    mac: str


type SmartFriendsConfigEntry = ConfigEntry[SmartFriendsRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SmartFriendsConfigEntry) -> bool:
    """Set up one SmartFriends Box from a config entry."""

    host = entry.data[CONF_HOST]
    port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    client = SmartFriendsClient(
        host,
        port,
        username,
        password,
        c_symbol=DEFAULT_C_SYMBOL,
        shc_version=DEFAULT_SHC_VERSION,
        sh_api_version=DEFAULT_SH_API_VERSION,
        auto_reconnect=True,
        poll_interval=5.0,
    )
    coordinator = SmartFriendsCoordinator(hass, entry, client)

    try:
        gateway = await client.async_connect()
        await coordinator.async_config_entry_first_refresh()
    except SmartFriendsAuthenticationError as err:
        await coordinator.async_shutdown()
        raise ConfigEntryAuthFailed(
            "The SmartFriends Box rejected the configured credentials"
        ) from err
    except SmartFriendsError as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady("The SmartFriends Box is not reachable") from err
    except Exception as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady("SmartFriends setup failed") from err

    mac = normalize_mac(entry.unique_id) or normalize_mac(gateway.mac_address)
    if mac is None:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady("The SmartFriends Box did not provide a stable MAC address")

    entry.runtime_data = SmartFriendsRuntimeData(
        client=client,
        coordinator=coordinator,
        mac=mac,
    )

    _async_register_hub_device(hass, entry, mac, gateway.hardware, gateway.shs_version)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(
        "RolloFriends connected to %s with %s shutter(s)",
        host,
        len(client.shutters),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartFriendsConfigEntry) -> bool:
    """Unload the integration and close its one box connection."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.coordinator.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: SmartFriendsConfigEntry) -> None:
    """Best-effort cleanup when the config entry is removed."""

    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        await runtime.coordinator.async_shutdown()


def _async_register_hub_device(
    hass: HomeAssistant,
    entry: SmartFriendsConfigEntry,
    mac: str,
    hardware: str | None,
    software: str | None,
) -> None:
    registry = dr.async_get(hass)
    connections = set()
    with contextlib.suppress(ValueError):
        connections.add((dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac)))
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac)},
        connections=connections,
        name="SmartFriends Box",
        manufacturer=MANUFACTURER,
        model=hardware or "SmartFriends Box",
        sw_version=software,
    )
