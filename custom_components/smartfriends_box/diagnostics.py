"""Diagnostics support for RolloFriends."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import SmartFriendsData
from .vendor.aiosmartfriends import Shutter

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "mac",
    "mac_address",
    "session_id",
    "sessionID",
    "digest",
    "salt",
    "sessionSalt",
}


def _entity_state(hass: HomeAssistant, mac: str, master_id: int) -> dict[str, Any]:
    entity_id = er.async_get(hass).async_get_entity_id("cover", DOMAIN, f"{mac}_{master_id}")
    if entity_id is None:
        return {"entity_id": None}
    state = hass.states.get(entity_id)
    if state is None:
        return {"entity_id": entity_id}
    return {
        "entity_id": entity_id,
        "entity_state": state.state,
        "entity_position": state.attributes.get("current_position"),
        "entity_is_closed": state.attributes.get("is_closed"),
        "entity_available": state.state != "unavailable",
        "position_status": state.attributes.get("position_status"),
        "position_pending": state.attributes.get("position_pending"),
        "position_fresh": state.attributes.get("position_fresh"),
        "motor_status": state.attributes.get("motor_status"),
        "stop_status": state.attributes.get("stop_status"),
        "command_target": state.attributes.get("command_target"),
    }


def _shutter_diagnostics(
    shutter: Shutter,
    *,
    hass: HomeAssistant | None,
    mac: str,
) -> dict[str, Any]:
    result = {
        "master_id": shutter.master_id,
        "name": shutter.name,
        "room": shutter.room_name,
        "manufacturer": shutter.manufacturer,
        "product_family": shutter.product_family,
        "motor_component_id": shutter.motor_component_id,
        "position_component_id": shutter.position_component_id,
        "position_semantics": shutter.position_semantics.value,
        "position_min": shutter.position_min,
        "position_max": shutter.position_max,
        "position_step": shutter.position_step,
        "raw_position": shutter.raw_position,
        "raw_target_position": shutter.raw_target_position,
        "ha_position": shutter.ha_position,
        "is_closed": shutter.is_closed,
        "motion": shutter.motion.value,
        "signal_quality": shutter.rssi_raw,
        "motion_timestamp": shutter.motion_timestamp,
        "position_timestamp": shutter.position_timestamp,
        "position_definition_key": shutter.position_definition_key,
    }
    if hass is not None:
        result.update(_entity_state(hass, mac, shutter.master_id))
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    data: SmartFriendsData | None = coordinator.data
    gateway = runtime.client.gateway
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "gateway": {
            "hardware": gateway.hardware if gateway else None,
            "software": gateway.shs_version if gateway else None,
            "api_major_version": gateway.api_major_version if gateway else None,
            "administrator_rights": gateway.administrator_rights if gateway else None,
        },
        "connection": {
            "state": runtime.client.state.value,
            "connected": data.connected if data else False,
            "fresh": data.fresh if data else False,
            "last_snapshot_at": (
                data.last_snapshot_at.isoformat() if data and data.last_snapshot_at else None
            ),
            "last_error": (data.last_error[:300] if data and data.last_error else None),
        },
        "component_count": runtime.client.repository.component_count,
        "shutter_count": len(data.shutters) if data else 0,
        "shutters": (
            [
                _shutter_diagnostics(
                    shutter,
                    hass=hass,
                    mac=getattr(runtime, "mac", ""),
                )
                for shutter in data.shutters.values()
            ]
            if data
            else []
        ),
        "recent_events": getattr(coordinator, "recent_events", []),
    }
