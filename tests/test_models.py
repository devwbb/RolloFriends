from __future__ import annotations

import pytest

from aiosmartfriends.models import (
    PositionSemantics,
    Shutter,
    ShutterMotion,
    localized,
    parse_snapshot,
    strip_language_lookup,
)
from aiosmartfriends.protocol import parse_wire_message

SNAPSHOT = b"""
{"responseCode":1,"responseMessage":"success","response":{
 "currentTimestamp":20261021090000,
 "newCompatibilityConfiguration":{"compatibilityConfigurationVersion":349,"compatibleRadioStandards":[{"compatibleDevices":[
  {"deviceDesignation":"${SchellenbergRolloDrive}","deviceTypClient":"${RollingShutter}","deviceTypServer":"actuator","deviceType":{"kind":"rollingShutter","type":"actuator","model":"listbox","switchingValues":[{"name":"${Stop}","value":0},{"name":"${Up}","value":1},{"name":"${Down}","value":2}]}},
  {"deviceDesignation":"${SchellenbergPosition}","deviceTypClient":"${SchellenbergPosition}","deviceTypServer":"analogActuator","deviceType":{"kind":"position","type":"actuator","model":"analog","min":0,"max":100,"step":1}},
  {"deviceDesignation":"${SchellenbergRssi}","deviceTypClient":"${Status}","deviceType":{"kind":"default","type":"sensor","model":"text"},"hidden":{"deviceOverview":true}}
 ]}]},
 "newRoomInfos":[{"roomID":100,"roomName":"${Rooms.LivingRoom}"}],
 "newDeviceInfos":[
  {"deviceID":9002,"masterDeviceID":9001,"deviceName":"${Motor}","masterDeviceName":"Test Rollo","deviceDesignation":"${SchellenbergRolloDrive}","deviceTypClient":"${RollingShutter}","deviceTypServer":"actuator","manufacturer":"Alfred Schellenberg GmbH","roomID":100,"firstLevel":true,"value":1,"valueTimestamp":20261021085900},
  {"deviceID":9003,"masterDeviceID":9001,"deviceName":"${Position}","masterDeviceName":"Test Rollo","deviceDesignation":"${SchellenbergPosition}","deviceTypClient":"${SchellenbergPosition}","deviceTypServer":"analogActuator","manufacturer":"Alfred Schellenberg GmbH","roomID":100,"value":35,"valueTarget":30,"valueTimestamp":20261021085900}
 ],
 "newDeviceValues":[{"deviceID":9002,"masterDeviceID":9001,"value":1,"valueTimestamp":20261021085900},{"deviceID":9003,"masterDeviceID":9001,"value":35,"valueTimestamp":20261021085900}],
 "newLanguageTranslation":{"languageTranslationVersion":123,"newTranslatedStrings":[{"key":"Rooms.LivingRoom","value":"Wohnzimmer"},{"key":"Motor","value":"Motor"}]}
}}
"""


def test_parse_snapshot() -> None:
    snapshot = parse_snapshot(parse_wire_message(SNAPSHOT), full_reload=True)
    assert snapshot.current_timestamp == 20_261_021_090_000
    assert snapshot.compatibility_configuration_version == "349"
    assert snapshot.language_translation_version == "123"
    assert len(snapshot.rooms) == 1
    assert len(snapshot.devices) == 2
    assert len(snapshot.values) == 2
    assert len(snapshot.definitions) == 3
    assert snapshot.translations["Rooms.LivingRoom"] == "Wohnzimmer"


def test_localized_chain_and_strip() -> None:
    assert strip_language_lookup("${Rooms.BedRoom}") == "Rooms.BedRoom"
    assert localized("${Rooms.BedRoom}", {"Rooms.BedRoom": "Schlafzimmer"}) == "Schlafzimmer"
    assert (
        localized(
            "${Rooms.BedRoom}",
            {"Rooms.BedRoom": "${Rooms.Bedroom}", "Rooms.Bedroom": "Schlafzimmer"},
        )
        == "Schlafzimmer"
    )


def test_position_mapping_and_target() -> None:
    shutter = Shutter(
        master_id=9001,
        name="Test",
        room_id=100,
        room_name="Wohnzimmer",
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
    assert shutter.ha_position == 65
    assert shutter.is_closed is False
    assert shutter.box_target_for_ha_position(20) == 80
    assert shutter.box_target_for_ha_position(0) == 100
    assert shutter.box_target_for_ha_position(100) == 0
    assert shutter.is_at_ha_position(65)


def test_position_mapping_clamps_and_unknown() -> None:
    shutter = Shutter(
        master_id=1,
        name="X",
        room_id=None,
        room_name="Ohne Raum",
        manufacturer=None,
        motor_component_id=2,
        position_component_id=3,
        up_value=1,
        down_value=2,
        stop_value=0,
        position_min=0,
        position_max=100,
        position_step=1,
        raw_position=None,
        raw_target_position=None,
        position_semantics=PositionSemantics.UNKNOWN,
        position_definition_key=None,
        motion=ShutterMotion.UNKNOWN,
        motion_timestamp=None,
        position_timestamp=None,
    )
    assert shutter.ha_position is None
    assert shutter.is_closed is None
    assert not shutter.supports_position
    assert shutter.box_target_for_ha_position(50) is None


def test_unknown_position_semantics_has_no_position_feature() -> None:
    shutter = Shutter(
        master_id=1,
        name="X",
        room_id=None,
        room_name="Ohne Raum",
        manufacturer=None,
        motor_component_id=2,
        position_component_id=3,
        up_value=1,
        down_value=2,
        stop_value=0,
        position_min=0,
        position_max=100,
        position_step=1,
        raw_position=50,
        raw_target_position=None,
        position_semantics=PositionSemantics.UNKNOWN,
        position_definition_key=None,
        motion=ShutterMotion.UNKNOWN,
        motion_timestamp=None,
        position_timestamp=None,
    )
    assert not shutter.supports_absolute_position


def test_object_list_accepts_values_envelope() -> None:
    message = parse_wire_message(
        b'{"responseCode":1,"response":{"newDeviceValues":{"values":[{"deviceID":1,"value":2}]}}}'
    )
    snapshot = parse_snapshot(message, full_reload=False)
    assert snapshot.values[0].device_id == 1


@pytest.mark.parametrize("raw,expected", [(0, 100), (35, 65), (100, 0)])
def test_inverse_scale(raw: float, expected: float) -> None:
    shutter = Shutter(
        master_id=1,
        name="X",
        room_id=None,
        room_name="Ohne Raum",
        manufacturer=None,
        motor_component_id=2,
        position_component_id=3,
        up_value=1,
        down_value=2,
        stop_value=0,
        position_min=0,
        position_max=100,
        position_step=1,
        raw_position=raw,
        raw_target_position=None,
        position_semantics=PositionSemantics.MEASURED,
        position_definition_key="SchellenbergPosition",
        motion=ShutterMotion.STOPPED,
        motion_timestamp=None,
        position_timestamp=None,
    )
    assert shutter.ha_position == expected
