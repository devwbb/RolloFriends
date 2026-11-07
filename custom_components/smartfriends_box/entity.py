"""Base entity and device registry mapping for RolloFriends."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SmartFriendsCoordinator
from .vendor.aiosmartfriends import Shutter


class SmartFriendsEntity(CoordinatorEntity[SmartFriendsCoordinator]):
    """Common entity with a stable device identity per shutter master."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartFriendsCoordinator,
        master_id: int,
        mac: str,
        initial_shutter: Shutter,
    ) -> None:
        super().__init__(coordinator)
        self._master_id = master_id
        self._mac = mac
        self._initial_shutter = initial_shutter
        self._attr_unique_id = f"{mac}_{master_id}"

    @property
    def shutter(self) -> Shutter | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.shutters.get(self._master_id)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.is_entity_available(self._master_id)

    @property
    def device_info(self) -> DeviceInfo:
        shutter = self.shutter or self._initial_shutter
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._mac}_{self._master_id}")},
            name=shutter.name,
            manufacturer=shutter.manufacturer or MANUFACTURER,
            model=shutter.product_family or "SmartFriends Rollladen",
        )
        hass = getattr(self, "hass", None)
        if hass is not None:
            registry = dr.async_get(hass)
            hub = registry.async_get_device_by_identifier(
                (DOMAIN, self._mac), self.coordinator.config_entry.entry_id
            )
            if hub is not None:
                info["via_device_id"] = hub.id
        if shutter.room_name and shutter.room_name != "Ohne Raum":
            info["suggested_area"] = shutter.room_name
        return info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        shutter = self.shutter
        if shutter is None:
            return {}
        attributes: dict[str, Any] = {
            "box_position": shutter.raw_position,
            "box_target": shutter.raw_target_position,
            "position_semantics": shutter.position_semantics.value,
        }
        if shutter.rssi_raw is not None:
            attributes["radio_quality"] = shutter.rssi_raw
        return attributes
