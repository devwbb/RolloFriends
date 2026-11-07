from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.smartfriends_box.diagnostics import async_get_config_entry_diagnostics
from custom_components.smartfriends_box.vendor.aiosmartfriends import (
    ConnectionState,
    GatewayInfo,
    PositionSemantics,
    Shutter,
    ShutterMotion,
)


def test_diagnostics_redacts_secrets() -> None:
    shutter = Shutter(
        master_id=9001,
        name="Test",
        room_id=None,
        room_name="Ohne Raum",
        manufacturer=None,
        motor_component_id=9002,
        position_component_id=9003,
        up_value=1,
        down_value=2,
        stop_value=0,
        position_min=0,
        position_max=100,
        position_step=1,
        raw_position=35,
        raw_target_position=30,
        position_semantics=PositionSemantics.MEASURED,
        position_definition_key="SchellenbergPosition",
        motion=ShutterMotion.STOPPED,
        motion_timestamp=1,
        position_timestamp=1,
    )
    data = SimpleNamespace(
        shutters={9001: shutter},
        connected=True,
        fresh=True,
        last_snapshot_at=None,
        last_error=None,
    )
    client = SimpleNamespace(
        gateway=GatewayInfo("secret-session", hardware="TestBox", shs_version="5.1.5-release"),
        state=ConnectionState.CONNECTED,
        repository=SimpleNamespace(component_count=2),
    )
    runtime = SimpleNamespace(coordinator=SimpleNamespace(data=data), client=client)
    entry = SimpleNamespace(
        data={"host": "192.0.2.1", "username": "secret-user", "password": "secret-pass"},
        runtime_data=runtime,
    )
    diagnostics = asyncio.run(async_get_config_entry_diagnostics(None, entry))
    text = str(diagnostics)
    assert "secret-user" not in text
    assert "secret-pass" not in text
    assert "secret-session" not in text
    assert diagnostics["shutter_count"] == 1
