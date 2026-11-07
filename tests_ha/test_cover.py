from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import pytest
from custom_components.smartfriends_box import cover as cover_module
from custom_components.smartfriends_box.coordinator import (
    SmartFriendsCoordinator,
    SmartFriendsData,
)
from custom_components.smartfriends_box.cover import SmartFriendsCover
from custom_components.smartfriends_box.vendor.aiosmartfriends import (
    CommandReceipt,
    ConnectionState,
    GatewayInfo,
    PositionSemantics,
    Shutter,
    ShutterMotion,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.snapshot_calls: list[bool] = []
        self.acknowledged = True
        self.is_connected = True

    async def async_set_device_value(self, component_id: int, value: int) -> CommandReceipt:
        self.calls.append((component_id, value))
        return CommandReceipt(acknowledged=self.acknowledged, sent=True)

    async def async_get_snapshot(self, *, full: bool = False) -> object:
        self.snapshot_calls.append(full)
        return object()


class FakeCoordinator:
    last_update_success = True

    def __init__(self, shutter: Shutter) -> None:
        self.client = FakeClient()
        self.refresh_calls = 0
        self.data = SmartFriendsData(
            shutters={shutter.master_id: shutter},
            connected=True,
            fresh=True,
            last_snapshot_at=datetime.now(UTC),
            last_error=None,
            gateway=GatewayInfo("synthetic"),
            state=ConnectionState.CONNECTED,
        )

    def is_entity_available(self, master_id: int) -> bool:
        return master_id in self.data.shutters and self.data.available

    def async_add_listener(self, callback):
        return lambda: None

    async def async_request_read_only_refresh(self) -> bool:
        self.refresh_calls += 1
        return True


def shutter(
    *,
    raw: float | None = 35,
    semantics: PositionSemantics = PositionSemantics.MEASURED,
    motion: ShutterMotion = ShutterMotion.STOPPED,
    motion_ts: int | None = 1,
    position_ts: int | None = 1,
    rssi: int | None = 3,
) -> Shutter:
    return Shutter(
        master_id=9001,
        name="Test Rollo",
        room_id=100,
        room_name="Wohnzimmer",
        manufacturer="Schellenberg",
        motor_component_id=9002,
        position_component_id=9003,
        up_value=1,
        down_value=2,
        stop_value=0,
        position_min=0,
        position_max=100,
        position_step=1,
        raw_position=raw,
        raw_target_position=30,
        position_semantics=semantics,
        position_definition_key=(
            "SchellenbergPosition"
            if semantics is PositionSemantics.MEASURED
            else "SchellenbergPosition_Adjustable"
        ),
        motion=motion,
        motion_timestamp=motion_ts,
        position_timestamp=position_ts,
        rssi_raw=rssi,
    )


def make_entity(item: Shutter | None = None) -> tuple[SmartFriendsCover, FakeCoordinator]:
    item = item or shutter()
    coordinator = FakeCoordinator(item)
    entity = SmartFriendsCover(coordinator, "AABBCCDDEEFF", item)
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    return entity, coordinator


def test_position_mapping_and_closed_state() -> None:
    entity, _ = make_entity()
    assert entity.current_cover_position == 65
    assert entity.is_closed is False
    assert entity.assumed_state is False
    assert entity.supported_features == 15


def test_closed_endpoint_and_unknown_position() -> None:
    entity, coordinator = make_entity(shutter(raw=100))
    assert entity.current_cover_position == 0
    assert entity.is_closed is True

    coordinator.data = SmartFriendsData(
        shutters={9001: shutter(raw=None)},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    assert entity.current_cover_position is None
    assert entity.is_closed is None


def test_adjustable_devices_are_assumed_state() -> None:
    entity, _ = make_entity(shutter(semantics=PositionSemantics.ADJUSTABLE))
    assert entity.assumed_state is True


@pytest.mark.asyncio
async def test_open_close_stop_targets_motor_component() -> None:
    entity, coordinator = make_entity()
    await entity.async_open_cover()
    await entity.async_close_cover()
    await entity.async_stop_cover()
    assert coordinator.client.calls == [(9002, 1), (9002, 2), (9002, 0)]


@pytest.mark.asyncio
async def test_position_targets_position_component_and_inverts() -> None:
    entity, coordinator = make_entity()
    await entity.async_set_cover_position(position=80)
    assert coordinator.client.calls == [(9003, 20)]


@pytest.mark.asyncio
async def test_position_command_is_skipped_when_already_reached() -> None:
    entity, coordinator = make_entity(shutter(raw=20))
    await entity.async_set_cover_position(position=80)
    assert coordinator.client.calls == []


@pytest.mark.asyncio
async def test_unacknowledged_command_is_not_retried() -> None:
    entity, coordinator = make_entity()
    coordinator.client.acknowledged = False
    await entity.async_open_cover()
    assert coordinator.client.calls == [(9002, 1)]
    assert entity.is_opening is False


def test_initial_motion_value_does_not_start_movement() -> None:
    entity, _ = make_entity(shutter(motion=ShutterMotion.UP, motion_ts=10, position_ts=9))
    assert entity.is_opening is False


def test_fresh_motor_transition_starts_and_stop_ends_movement() -> None:
    entity, coordinator = make_entity()
    opening = shutter(motion=ShutterMotion.UP, motion_ts=2, position_ts=1)
    coordinator.data = SmartFriendsData(
        shutters={9001: opening},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    entity._handle_coordinator_update()
    assert entity.is_opening is True

    stopped = shutter(motion=ShutterMotion.STOPPED, motion_ts=3, position_ts=2)
    coordinator.data = SmartFriendsData(
        shutters={9001: stopped},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    entity._handle_coordinator_update()
    assert entity.is_opening is False


def test_unavailable_when_coordinator_is_stale() -> None:
    entity, coordinator = make_entity()
    coordinator.data = SmartFriendsData(
        shutters=coordinator.data.shutters,
        connected=False,
        fresh=False,
        last_snapshot_at=None,
        last_error="offline",
        gateway=None,
        state=ConnectionState.RECONNECTING,
    )
    assert entity.available is False
    assert entity.current_cover_position is None


def test_movement_clears_when_intermediate_target_is_reached() -> None:
    entity, coordinator = make_entity()
    entity._movement = "opening"
    entity._command_direction = "opening"
    entity._command_target_ha = 50
    entity._command_at = time.monotonic()
    entity._command_deadline = time.monotonic() + 30
    reached = shutter(raw=50, motion=ShutterMotion.STOPPED, motion_ts=5, position_ts=5)
    coordinator.data = SmartFriendsData(
        shutters={9001: reached},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    entity._handle_coordinator_update()
    assert entity.is_opening is False
    assert entity.current_cover_position == 50
    assert entity._command_target_ha is None


def test_value_target_is_never_reported_as_measured_position() -> None:
    entity, _ = make_entity(shutter(raw=35))
    assert entity.shutter is not None
    assert entity.shutter.raw_target_position == 30
    assert entity.current_cover_position == 65
    assert entity.position_status == "confirmed"
    assert entity.extra_state_attributes["box_target"] == 30
    assert entity.extra_state_attributes["position_fresh"] is True
    assert entity.extra_state_attributes["motor_status"] == "stopped"
    assert entity.extra_state_attributes["stop_status"] == "not_requested"


@pytest.mark.asyncio
async def test_target_command_stays_pending_until_target_position_arrives() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    await entity.async_set_cover_position(position=80)
    assert coordinator.client.calls == [(9003, 20)]
    assert entity.position_status == "pending"
    assert entity.extra_state_attributes["command_target"] == 80
    assert entity.extra_state_attributes["position_pending"] is True
    # The old measured position remains visible briefly, but never the target.
    assert entity.current_cover_position == 65

    intermediate = shutter(raw=15, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2)
    coordinator.data = SmartFriendsData(
        shutters={9001: intermediate},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    entity._handle_coordinator_update()
    assert entity.current_cover_position == 85
    assert entity.position_status == "moving"
    assert entity.extra_state_attributes["position_pending"] is True

    reached = shutter(raw=20, motion=ShutterMotion.STOPPED, motion_ts=3, position_ts=3)
    coordinator.data = SmartFriendsData(
        shutters={9001: reached},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )
    entity._handle_coordinator_update()
    assert entity.current_cover_position == 80
    assert entity.position_status == "confirmed"
    assert entity.extra_state_attributes["position_pending"] is False
    assert "command_target" not in entity.extra_state_attributes


def test_pending_position_becomes_unknown_after_confirmation_window() -> None:
    entity, _ = make_entity(shutter(raw=35))
    entity._command_pending = True
    entity._position_unconfirmed = True
    entity._position_pending_until = time.monotonic() - 1
    assert entity.position_status == "pending"
    assert entity.current_cover_position is None
    assert entity.is_closed is None


def test_unconfirmed_target_warning_is_emitted_only_once(caplog: pytest.LogCaptureFixture) -> None:
    entity, _ = make_entity(shutter(raw=35))
    entity._command_pending = True
    entity._command_target_ha = 80
    entity._command_at = time.monotonic() - 31
    entity._command_deadline = time.monotonic() - 1
    with caplog.at_level(logging.WARNING, logger=cover_module.__name__):
        entity._handle_coordinator_update()
        entity._handle_coordinator_update()
    messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(messages) == 1
    assert "still pending" in messages[0]
    assert entity.extra_state_attributes["command_target"] == 80


def _mark_stop_pending(entity: SmartFriendsCover, *, motion_ts: int, position_ts: int) -> None:
    entity._command_pending = True
    entity._command_target_ha = None
    entity._command_at = time.monotonic()
    entity._command_deadline = time.monotonic() + 30
    entity._position_unconfirmed = True
    entity._position_pending_until = time.monotonic() + 30
    entity._motion_timestamp_at_command = motion_ts
    entity._position_timestamp_at_command = position_ts
    entity._stop_status = "awaiting_motor_stop"
    entity._stop_settle_reference = None


def _set_coordinator_state(coordinator: FakeCoordinator, item: Shutter) -> None:
    coordinator.data = SmartFriendsData(
        shutters={9001: item},
        connected=True,
        fresh=True,
        last_snapshot_at=datetime.now(UTC),
        last_error=None,
        gateway=GatewayInfo("synthetic"),
        state=ConnectionState.CONNECTED,
    )


def test_stop_requires_stable_position_after_motor_stop() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)

    # A fresh STOPPED and a fresh measurement begin the settling window; this
    # is deliberately not a final confirmation yet.
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "settling"
    assert entity.position_status == "settling"
    assert entity.position_pending is True
    assert entity.motor_status == "stopped"
    assert entity.position_fresh is True
    assert entity.extra_state_attributes["position_pending"] is True
    assert "command_target" not in entity.extra_state_attributes

    # Only the quiet-window finalizer makes the stop final.
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"
    assert entity.position_status == "confirmed"
    assert entity.position_pending is False
    assert entity._command_pending is False


def test_stop_does_not_confirm_from_stale_stopped_feedback() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=1, position_ts=1),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "awaiting_motor_stop"
    assert entity.position_status == "pending"
    assert entity.position_pending is True

    # A new measured value starts settling, but finalization still waits.
    _set_coordinator_state(
        coordinator,
        shutter(raw=25, motion=ShutterMotion.STOPPED, motion_ts=1, position_ts=2),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "settling"
    assert entity.current_cover_position == 75
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"
    assert entity.current_cover_position == 75


def test_stop_settling_resets_when_a_later_position_arrives() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "settling"
    assert entity.current_cover_position == 65

    # The box may report a later measured position after the first STOPPED.
    _set_coordinator_state(
        coordinator,
        shutter(raw=45, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=3),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "settling"
    assert entity.current_cover_position == 55
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"
    assert entity.current_cover_position == 55


@pytest.mark.asyncio
async def test_read_only_refresh_does_not_resend_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cover_module, "READ_ONLY_REFRESH_DELAYS", (0.0,))
    entity, coordinator = make_entity(shutter(raw=35))
    entity.hass = object()  # type: ignore[assignment]
    await entity.async_open_cover()
    await asyncio.sleep(0.01)
    assert coordinator.client.calls == [(9002, 1)]
    assert coordinator.refresh_calls == 1
    entity._cancel_refresh_tasks()


@pytest.mark.asyncio
async def test_coordinator_read_only_refresh_is_full_and_rate_limited() -> None:
    coordinator = object.__new__(SmartFriendsCoordinator)
    coordinator.client = FakeClient()
    coordinator._read_only_refresh_lock = asyncio.Lock()
    coordinator._last_read_only_refresh = 0.0
    coordinator.data = None

    assert await coordinator.async_request_read_only_refresh() is True
    assert coordinator.client.snapshot_calls == [True]
    assert coordinator.client.calls == []

    assert await coordinator.async_request_read_only_refresh() is False
    assert coordinator.client.snapshot_calls == [True]


@pytest.mark.asyncio
async def test_stop_settle_task_finalizes_after_quiet_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cover_module, "STOP_SETTLE_TIME", 0.01)
    entity, coordinator = make_entity(shutter(raw=35))
    entity.hass = object()  # type: ignore[assignment]
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "settling"
    await asyncio.sleep(0.05)
    assert entity.stop_status == "confirmed"
    assert entity.position_status == "confirmed"
    assert entity.position_pending is False
    entity._cancel_stop_settle()


def test_later_position_supersedes_confirmed_stop() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"

    # A delayed or new box position must not leave the old stop marked final.
    _set_coordinator_state(
        coordinator,
        shutter(raw=45, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=3),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "superseded"
    assert entity.current_cover_position == 55


def test_same_value_with_new_timestamp_keeps_stop_confirmed() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"

    # A repeated measurement of the same raw value is not a new endpoint.
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=3),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "confirmed"
    assert entity.current_cover_position == 65


def test_same_value_stale_update_keeps_stop_but_marks_position_stale() -> None:
    entity, coordinator = make_entity(shutter(raw=35))
    _mark_stop_pending(entity, motion_ts=1, position_ts=1)
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=2, position_ts=2),
    )
    entity._handle_coordinator_update()
    entity._finalize_stop()
    assert entity.stop_status == "confirmed"

    # The same raw value remains the same endpoint even if the box reports a
    # stale measurement; position freshness is exposed separately.
    _set_coordinator_state(
        coordinator,
        shutter(raw=35, motion=ShutterMotion.STOPPED, motion_ts=1000, position_ts=3),
    )
    entity._handle_coordinator_update()
    assert entity.stop_status == "confirmed"
    assert entity.position_fresh is False
    assert entity.position_status == "stale"


def test_rssi_zero_does_not_make_connection_or_shutter_unavailable() -> None:
    entity, _ = make_entity(shutter(raw=35, rssi=0))
    assert entity.available is True
    assert entity.position_status == "confirmed"
    assert entity.extra_state_attributes["radio_quality"] == 0
    assert entity.current_cover_position == 65
    assert entity.supported_features == 15
