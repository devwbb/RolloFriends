"""Push-fed Home Assistant coordinator for a SmartFriends Box."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DATA_FRESHNESS, DOMAIN, POLL_INTERVAL, READ_ONLY_REFRESH_COOLDOWN
from .vendor.aiosmartfriends import (
    EVENT_AUTH_FAILED,
    EVENT_DEVICE_INFO,
    EVENT_DEVICE_VALUE,
    EVENT_ROOM,
    EVENT_SNAPSHOT,
    ClientEvent,
    ConnectionState,
    GatewayInfo,
    Shutter,
    SmartFriendsClient,
    SmartFriendsError,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SmartFriendsData:
    shutters: dict[int, Shutter]
    connected: bool
    fresh: bool
    last_snapshot_at: datetime | None
    last_error: str | None
    gateway: GatewayInfo | None
    state: ConnectionState

    @property
    def available(self) -> bool:
        return self.connected and self.fresh


class SmartFriendsCoordinator(DataUpdateCoordinator[SmartFriendsData]):
    """A passive cache fed by the client's push and poll events.

    The client owns the only network poll and reconnect loop. This coordinator
    only keeps the Home Assistant view fresh; it never opens a second poll.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SmartFriendsClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.entry_id}",
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self._remove_listener = client.add_event_listener(self._handle_client_event)
        self._reauth_started = False
        self._recent_events: deque[dict[str, object]] = deque(maxlen=500)
        self._read_only_refresh_lock = asyncio.Lock()
        self._last_read_only_refresh = 0.0

    async def _async_update_data(self) -> SmartFriendsData:
        """Return the current client view without starting network I/O."""

        return self._build_data()

    def _build_data(self) -> SmartFriendsData:
        return SmartFriendsData(
            shutters={shutter.master_id: shutter for shutter in self.client.shutters},
            connected=self.client.is_connected,
            fresh=self.client.is_fresh(DATA_FRESHNESS),
            last_snapshot_at=self.client.last_snapshot_at,
            last_error=self.client.last_error,
            gateway=self.client.gateway,
            state=self.client.state,
        )

    def _handle_client_event(self, event: ClientEvent) -> None:
        self._record_event(event)
        if event.kind == EVENT_AUTH_FAILED:
            self._start_reauth()
            return
        if self.data is not None:
            self.async_set_updated_data(self._build_data())

    def _record_event(self, event: ClientEvent) -> None:
        at = datetime.now(UTC).isoformat()
        entry: dict[str, object] = {"at": at, "kind": event.kind}
        data = event.data
        if event.kind == EVENT_SNAPSHOT:
            entry.update(
                {
                    "full": data.is_full_reload,
                    "timestamp": data.current_timestamp,
                    "devices": len(data.devices),
                    "values": len(data.values),
                    "rooms": len(data.rooms),
                    "value_details": [
                        {
                            "device_id": item.device_id,
                            "master_id": item.master_device_id,
                            "value": _safe_value(item.value),
                            "value_target": _safe_value(item.value_target),
                            "box_timestamp": item.timestamp,
                        }
                        for item in data.values[:20]
                    ],
                }
            )
        elif event.kind == EVENT_DEVICE_VALUE:
            entry.update(
                {
                    "device_id": data.device_id,
                    "master_id": data.master_device_id,
                    "value": _safe_value(data.value),
                    "value_target": _safe_value(data.value_target),
                    "box_timestamp": data.timestamp,
                }
            )
        elif event.kind == EVENT_DEVICE_INFO:
            entry.update(
                {
                    "device_id": data.device_id,
                    "master_id": data.master_device_id,
                    "room_id": data.room_id,
                    "value": _safe_value(data.value),
                    "value_target": _safe_value(data.value_target),
                    "box_timestamp": data.value_timestamp,
                }
            )
        elif event.kind == EVENT_ROOM:
            entry["room_id"] = data.room_id
        elif event.kind == "connection":
            entry["state"] = data.value if isinstance(data, ConnectionState) else str(data)
        self._recent_events.append(entry)

    @property
    def recent_events(self) -> list[dict[str, object]]:
        return list(self._recent_events)

    def _start_reauth(self) -> None:
        if self._reauth_started:
            return
        self._reauth_started = True
        _LOGGER.warning("SmartFriends authentication failed; starting reauthentication")
        self.hass.async_create_task(self.config_entry.async_start_reauth(self.hass))

    async def async_shutdown(self) -> None:
        """Stop the client and stop listening for events."""

        self._remove_listener()
        await self.client.async_disconnect()

    async def async_request_read_only_refresh(self) -> bool:
        """Fetch a full snapshot without sending any device command.

        This is used when a commanded target has not been confirmed yet. It is
        rate limited and never retries; a failure leaves the existing state and
        is logged once per attempt.
        """

        if not self.client.is_connected:
            return False
        async with self._read_only_refresh_lock:
            now = monotonic()
            if now - self._last_read_only_refresh < READ_ONLY_REFRESH_COOLDOWN:
                return False
            self._last_read_only_refresh = now
            try:
                await self.client.async_get_snapshot(full=True)
            except SmartFriendsError as err:
                _LOGGER.info("Read-only position refresh failed: %s", err)
                return False
            if self.data is not None:
                self.async_set_updated_data(self._build_data())
            return True

    def is_entity_available(self, master_id: int) -> bool:
        if self.data is None or not self.data.available:
            return False
        return master_id in self.data.shutters


def _safe_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return type(value).__name__
