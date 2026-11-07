"""Cover entities for SmartFriends Box shutters."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    MOVEMENT_TIMEOUT,
    PENDING_WARNING_AFTER,
    POSITION_CONFIRM_TIMEOUT,
    READ_ONLY_REFRESH_DELAYS,
    STOP_SETTLE_TIME,
)
from .coordinator import SmartFriendsCoordinator
from .entity import SmartFriendsEntity
from .vendor.aiosmartfriends import (
    PositionSemantics,
    Shutter,
    ShutterMotion,
    SmartFriendsCommandRejected,
    SmartFriendsError,
)

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    coordinator: SmartFriendsCoordinator = runtime.coordinator
    mac: str = runtime.mac

    entities: dict[int, SmartFriendsCover] = {}
    for shutter in coordinator.data.shutters.values():
        entity = SmartFriendsCover(coordinator, mac, shutter)
        entities[shutter.master_id] = entity
    if entities:
        async_add_entities(entities.values())

    def add_new_entities() -> None:
        if coordinator.data is None:
            return
        new_entities = []
        for shutter in coordinator.data.shutters.values():
            if shutter.master_id in entities:
                continue
            entity = SmartFriendsCover(coordinator, mac, shutter)
            entities[shutter.master_id] = entity
            new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


class SmartFriendsCover(SmartFriendsEntity, CoverEntity):
    """One master shutter with component-specific command targets."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_name = None

    def __init__(
        self,
        coordinator: SmartFriendsCoordinator,
        mac: str,
        initial_shutter: Shutter,
    ) -> None:
        super().__init__(
            coordinator,
            initial_shutter.master_id,
            mac,
            initial_shutter,
        )
        self._last_motion = initial_shutter.motion
        self._last_motion_timestamp = initial_shutter.motion_timestamp
        self._last_position = initial_shutter.raw_position
        self._last_position_timestamp = initial_shutter.position_timestamp
        self._movement: str | None = None
        self._command_direction: str | None = None
        self._command_target_ha: int | None = None
        self._command_at: float | None = None
        self._command_deadline: float | None = None
        self._position_unconfirmed = False
        self._position_pending_until: float | None = None
        self._position_at_command = initial_shutter.raw_position
        self._position_timestamp_at_command = initial_shutter.position_timestamp
        self._command_pending = False
        self._stop_status = "not_requested"
        self._stop_settle_task: asyncio.Task[None] | None = None
        self._stop_settle_generation = 0
        self._stop_settle_reference: tuple[float | None, int | None] | None = None
        self._motion_timestamp_at_command = initial_shutter.motion_timestamp
        self._pending_warning_sent = False
        self._refresh_tasks: set[asyncio.Task[None]] = set()
        self._command_generation = 0

    @property
    def supported_features(self) -> CoverEntityFeature:
        shutter = self.shutter
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if shutter is not None and shutter.supports_absolute_position:
            features |= CoverEntityFeature.SET_POSITION
        return features

    @property
    def assumed_state(self) -> bool:
        shutter = self.shutter
        return shutter is None or shutter.position_semantics is not PositionSemantics.MEASURED

    @property
    def position_status(self) -> str:
        if not self.available:
            return "unavailable"
        shutter = self.shutter
        if shutter is None:
            return "unknown"
        if self._movement is not None:
            return "moving"
        if self._stop_status == "settling":
            return "settling"
        if self._command_pending or self._position_unconfirmed:
            return "pending"
        if self._position_is_stale(shutter):
            return "stale"
        if shutter.ha_position is not None:
            return "confirmed"
        return "unknown"

    @property
    def motor_status(self) -> str:
        if not self.available:
            return "unavailable"
        shutter = self.shutter
        if shutter is None:
            return "unknown"
        if shutter.motion in (ShutterMotion.UP, ShutterMotion.DOWN):
            return "moving"
        if shutter.motion is ShutterMotion.STOPPED:
            return "stopped"
        return "unknown"

    @property
    def stop_status(self) -> str:
        return self._stop_status

    @property
    def position_pending(self) -> bool:
        return (
            self._command_pending
            or self._position_unconfirmed
            or self._stop_status in ("awaiting_motor_stop", "settling")
        )

    @property
    def position_fresh(self) -> bool:
        shutter = self.shutter
        return bool(
            self.available
            and shutter is not None
            and shutter.ha_position is not None
            and not self._position_is_stale(shutter)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = super().extra_state_attributes
        attributes["position_status"] = self.position_status
        attributes["position_pending"] = self.position_pending
        attributes["position_fresh"] = self.position_fresh
        attributes["motor_status"] = self.motor_status
        attributes["stop_status"] = self._stop_status
        if self._command_target_ha is not None:
            attributes["command_target"] = self._command_target_ha
        return attributes

    @property
    def current_cover_position(self) -> int | None:
        shutter = self.shutter
        if shutter is None or not self.available:
            return None
        if self._position_is_stale(shutter):
            return None
        position = shutter.ha_position
        if position is None:
            return None
        if (
            self._position_unconfirmed
            and self._movement is None
            and self._position_pending_until is not None
            and time.monotonic() >= self._position_pending_until
        ):
            return None
        return round(position)

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        if position is None:
            return None
        return position <= 0

    @property
    def is_opening(self) -> bool:
        return self._movement == "opening"

    @property
    def is_closing(self) -> bool:
        return self._movement == "closing"

    async def async_open_cover(self, **kwargs: Any) -> None:
        shutter = self._require_shutter()
        await self._send_motor(shutter.up_value, "opening", target_ha=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        shutter = self._require_shutter()
        await self._send_motor(shutter.down_value, "closing", target_ha=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        shutter = self._require_shutter()
        await self._send_motor(shutter.stop_value, None, target_ha=None)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        shutter = self._require_shutter()
        if not shutter.supports_absolute_position or shutter.position_component_id is None:
            raise HomeAssistantError("This shutter does not support absolute positions")
        requested = kwargs.get(ATTR_POSITION)
        if not isinstance(requested, int):
            raise HomeAssistantError("A position between 0 and 100 is required")
        requested = min(max(requested, 0), 100)
        if shutter.is_at_ha_position(requested):
            return
        target = shutter.box_target_for_ha_position(requested)
        if target is None:
            raise HomeAssistantError("The box position range is unavailable")
        if shutter.is_at_box_target(target):
            return
        current = shutter.ha_position
        direction: str | None = None
        if current is not None and requested > current:
            direction = "opening"
        elif current is not None and requested < current:
            direction = "closing"
        await self._send_command(
            shutter.position_component_id,
            target,
            expected_direction=direction,
            target_ha=requested,
        )

    async def _send_motor(
        self,
        value: int,
        direction: str | None,
        *,
        target_ha: int | None,
    ) -> None:
        shutter = self._require_shutter()
        await self._send_command(
            shutter.motor_component_id,
            value,
            expected_direction=direction,
            target_ha=target_ha,
        )

    async def _send_command(
        self,
        component_id: int,
        value: int,
        *,
        expected_direction: str | None,
        target_ha: int | None,
    ) -> None:
        shutter = self._require_shutter()
        try:
            receipt = await self.coordinator.client.async_set_device_value(
                component_id,
                value,
            )
        except SmartFriendsCommandRejected as err:
            raise HomeAssistantError(f"The box rejected the command: {err}") from err
        except SmartFriendsError as err:
            raise HomeAssistantError(f"The command could not be sent: {err}") from err

        now = time.monotonic()
        self._cancel_refresh_tasks()
        self._command_generation += 1
        self._pending_warning_sent = False
        self._command_direction = expected_direction
        self._command_target_ha = target_ha
        self._command_at = now
        self._command_deadline = now + MOVEMENT_TIMEOUT
        self._position_unconfirmed = True
        self._command_pending = True
        self._position_pending_until = now + POSITION_CONFIRM_TIMEOUT
        self._position_at_command = shutter.raw_position
        self._position_timestamp_at_command = shutter.position_timestamp
        self._motion_timestamp_at_command = shutter.motion_timestamp
        if expected_direction is None:
            self._movement = None
            self._cancel_stop_settle()
            self._stop_status = "awaiting_motor_stop"
            self._stop_settle_reference = None
        else:
            self._reset_stop_state()
        self._schedule_read_only_refreshes()
        if not receipt.acknowledged:
            _LOGGER.warning(
                "Shutter command for master %s was sent without an acknowledgement",
                shutter.master_id,
            )
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        shutter = self.shutter
        if shutter is None:
            self._movement = None
            super()._handle_coordinator_update()
            return

        now = time.monotonic()
        motion_changed = (
            shutter.motion is not self._last_motion
            or shutter.motion_timestamp != self._last_motion_timestamp
        )
        position_changed = (
            shutter.raw_position != self._last_position
            or shutter.position_timestamp != self._last_position_timestamp
        )

        if position_changed:
            self._position_unconfirmed = False
            self._position_pending_until = None
            if self._stop_status == "confirmed" and (
                self._stop_settle_reference is None
                or shutter.raw_position != self._stop_settle_reference[0]
            ):
                self._stop_status = "superseded"
            if (
                self._movement is not None
                and shutter.ha_position is not None
                and (shutter.ha_position <= 0.5 or shutter.ha_position >= 99.5)
            ):
                self._movement = None
            if (
                self._command_direction is not None
                and self._last_position is not None
                and shutter.raw_position is not None
            ):
                inferred = "opening" if shutter.raw_position < self._last_position else "closing"
                if self._command_direction in (None, inferred):
                    self._movement = inferred
                    if self._command_deadline is not None:
                        self._command_deadline = now + MOVEMENT_TIMEOUT
            if self._stop_status in ("awaiting_motor_stop", "settling"):
                self._restart_stop_settle(now)

        if motion_changed:
            if self._stop_status == "confirmed" and shutter.motion in (
                ShutterMotion.UP,
                ShutterMotion.DOWN,
            ):
                self._stop_status = "superseded"
            if shutter.motion is ShutterMotion.UP:
                if self._command_direction in (None, "opening"):
                    self._movement = "opening"
                    self._command_deadline = now + MOVEMENT_TIMEOUT
            elif shutter.motion is ShutterMotion.DOWN:
                if self._command_direction in (None, "closing"):
                    self._movement = "closing"
                    self._command_deadline = now + MOVEMENT_TIMEOUT
            elif shutter.motion is ShutterMotion.STOPPED:
                if self._last_motion in (ShutterMotion.UP, ShutterMotion.DOWN):
                    self._movement = None
                if self._command_at is not None and self._command_target_ha is not None:
                    self._position_unconfirmed = True
                    self._position_pending_until = now + POSITION_CONFIRM_TIMEOUT
                if self._stop_status in ("awaiting_motor_stop", "settling"):
                    self._start_stop_settle(now)

        if (
            self._command_target_ha is not None
            and shutter.ha_position is not None
            and abs(shutter.ha_position - self._command_target_ha) <= 1
        ):
            self._movement = None
            self._position_unconfirmed = False
            self._position_pending_until = None
            self._command_pending = False
            self._command_deadline = None
            self._command_at = None
            self._command_direction = None
            self._command_target_ha = None
            self._pending_warning_sent = False
            self._cancel_refresh_tasks()

        if self._stop_status in ("awaiting_motor_stop", "settling"):
            if shutter.motion in (ShutterMotion.UP, ShutterMotion.DOWN):
                self._cancel_stop_settle()
                self._stop_status = "awaiting_motor_stop"
                self._position_unconfirmed = True
            elif shutter.motion is ShutterMotion.STOPPED:
                self._start_stop_settle(now)

        if self._command_deadline is not None and now >= self._command_deadline:
            self._movement = None
            self._command_deadline = None
            self._command_direction = None
            if self._command_pending and not self._pending_warning_sent:
                if self._command_target_ha is None:
                    _LOGGER.warning(
                        "Stop confirmation for master %s is still pending after %s s",
                        self._master_id,
                        int(PENDING_WARNING_AFTER),
                    )
                else:
                    _LOGGER.warning(
                        "Position confirmation for master %s (target %s) is still "
                        "pending after %s s",
                        self._master_id,
                        self._command_target_ha,
                        int(PENDING_WARNING_AFTER),
                    )
                self._pending_warning_sent = True

        self._last_motion = shutter.motion
        self._last_motion_timestamp = shutter.motion_timestamp
        self._last_position = shutter.raw_position
        self._last_position_timestamp = shutter.position_timestamp
        super()._handle_coordinator_update()

    def _reset_stop_state(self) -> None:
        self._cancel_stop_settle()
        self._stop_status = "not_requested"
        self._stop_settle_reference = None

    def _cancel_stop_settle(self) -> None:
        task = self._stop_settle_task
        if task is not None and not task.done():
            task.cancel()
        self._stop_settle_task = None
        self._stop_settle_generation += 1

    def _stop_evidence_is_fresh(self, shutter: Shutter) -> bool:
        motion_timestamp = shutter.motion_timestamp
        position_timestamp = shutter.position_timestamp
        motion_fresh = motion_timestamp is not None and (
            self._motion_timestamp_at_command is None
            or motion_timestamp > self._motion_timestamp_at_command
        )
        position_fresh = position_timestamp is not None and (
            self._position_timestamp_at_command is None
            or position_timestamp > self._position_timestamp_at_command
            or not self._position_unconfirmed
        )
        return motion_fresh or position_fresh

    def _start_stop_settle(self, now: float) -> None:
        if self._stop_status != "awaiting_motor_stop":
            return
        shutter = self.shutter
        if shutter is None or shutter.motion is not ShutterMotion.STOPPED:
            return
        if shutter.raw_position is None or shutter.position_timestamp is None:
            return
        if self._position_is_stale(shutter):
            return
        if not self._stop_evidence_is_fresh(shutter):
            return
        self._stop_status = "settling"
        self._stop_settle_reference = (shutter.raw_position, shutter.position_timestamp)
        self._stop_settle_generation += 1
        generation = self._stop_settle_generation
        if getattr(self, "hass", None) is not None:
            self._stop_settle_task = asyncio.create_task(self._finalize_stop_after(generation))

    def _restart_stop_settle(self, now: float) -> None:
        if self._stop_status not in ("awaiting_motor_stop", "settling"):
            return
        self._cancel_stop_settle()
        self._stop_status = "awaiting_motor_stop"
        self._start_stop_settle(now)

    async def _finalize_stop_after(self, generation: int) -> None:
        await asyncio.sleep(STOP_SETTLE_TIME)
        if generation != self._stop_settle_generation:
            return
        self._finalize_stop()

    def _finalize_stop(self) -> None:
        if self._stop_status != "settling":
            return
        shutter = self.shutter
        if shutter is None or shutter.motion is not ShutterMotion.STOPPED:
            return
        if shutter.raw_position is None or shutter.ha_position is None:
            return
        if self._position_is_stale(shutter):
            return
        if self._stop_settle_reference != (
            shutter.raw_position,
            shutter.position_timestamp,
        ):
            return
        self._movement = None
        self._stop_status = "confirmed"
        self._command_pending = False
        self._position_unconfirmed = False
        self._position_pending_until = None
        self._command_at = None
        self._command_deadline = None
        self._command_direction = None
        self._pending_warning_sent = False
        self._stop_settle_task = None
        self._stop_settle_generation += 1
        self._cancel_refresh_tasks()
        self.async_write_ha_state()

    def _schedule_read_only_refreshes(self) -> None:
        if getattr(self, "hass", None) is None:
            return
        if not callable(getattr(self.coordinator, "async_request_read_only_refresh", None)):
            return
        generation = self._command_generation
        for delay in READ_ONLY_REFRESH_DELAYS:
            task = asyncio.create_task(self._read_only_refresh_after(delay, generation))
            self._refresh_tasks.add(task)
            task.add_done_callback(self._refresh_tasks.discard)

    async def _read_only_refresh_after(self, delay: float, generation: int) -> None:
        await asyncio.sleep(delay)
        if generation != self._command_generation:
            return
        if not self._command_pending or getattr(self, "hass", None) is None:
            return
        await self.coordinator.async_request_read_only_refresh()

    def _cancel_refresh_tasks(self) -> None:
        for task in self._refresh_tasks:
            task.cancel()
        self._refresh_tasks.clear()

    def _position_is_stale(self, shutter: Shutter) -> bool:
        if (
            shutter.motion_timestamp is None
            or shutter.position_timestamp is None
            or shutter.motion is ShutterMotion.UNKNOWN
        ):
            return False
        return (shutter.motion_timestamp - shutter.position_timestamp) >= 60

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_refresh_tasks()
        self._cancel_stop_settle()
        await super().async_will_remove_from_hass()

    def _require_shutter(self) -> Shutter:
        shutter = self.shutter
        if shutter is None or not self.available:
            raise HomeAssistantError("SmartFriends data is not current")
        return shutter
