from __future__ import annotations

from aiosmartfriends.models import (
    DeviceRecord,
    DeviceValueRecord,
    GatewaySnapshot,
    PositionSemantics,
    RoomRecord,
    parse_snapshot,
)
from aiosmartfriends.protocol import parse_wire_message
from aiosmartfriends.repository import DeviceRepository
from tests.test_models import SNAPSHOT


def make_repository() -> DeviceRepository:
    repository = DeviceRepository()
    repository.apply(parse_snapshot(parse_wire_message(SNAPSHOT), full_reload=True))
    return repository


def test_builds_shutter_from_master_and_components() -> None:
    repository = make_repository()
    shutters = repository.make_shutters()
    assert len(shutters) == 1
    shutter = shutters[0]
    assert shutter.master_id == 9001
    assert shutter.motor_component_id == 9002
    assert shutter.position_component_id == 9003
    assert shutter.motor_component_id != shutter.master_id
    assert shutter.name == "Test Rollo"
    assert shutter.room_name == "Wohnzimmer"
    assert shutter.product_family == "Rollodrive PREMIUM"
    assert shutter.position_semantics is PositionSemantics.MEASURED
    assert shutter.raw_position == 35
    assert shutter.raw_target_position == 30
    assert shutter.ha_position == 65
    assert shutter.motion.value == "up"


def test_empty_delta_keeps_components() -> None:
    repository = make_repository()
    before = repository.make_shutters()
    repository.apply(
        GatewaySnapshot(
            current_timestamp=20_261_021_090_100,
            compatibility_configuration_version=None,
            language_translation_version=None,
            rooms=(),
            devices=(),
            values=(),
            definitions=(),
            translations={},
            is_full_reload=False,
        )
    )
    assert repository.component_count == 2
    assert repository.make_shutters() == before


def test_delta_with_new_value_updates_only_one_shutter() -> None:
    repository = make_repository()
    repository.apply_value(
        DeviceValueRecord(
            device_id=9003,
            master_device_id=9001,
            value=80,
            timestamp=20_261_021_090_100,
        )
    )
    shutter = repository.make_shutters()[0]
    assert shutter.raw_position == 80
    assert shutter.ha_position == 20


def test_older_value_does_not_overwrite_newer() -> None:
    repository = make_repository()
    repository.apply_value(
        DeviceValueRecord(
            device_id=9003,
            master_device_id=9001,
            value=80,
            timestamp=20_261_021_090_100,
        )
    )
    repository.apply_value(
        DeviceValueRecord(
            device_id=9003,
            master_device_id=9001,
            value=10,
            timestamp=20_261_021_090_000,
        )
    )
    assert repository.make_shutters()[0].raw_position == 80


def test_device_info_push_updates_name_and_motion() -> None:
    repository = make_repository()
    repository.apply_device(
        DeviceRecord(
            device_id=9002,
            master_device_id=9001,
            device_name="Motor",
            master_device_name="Neuer Name",
            device_designation="${SchellenbergRolloDrive}",
            device_typ_client="${RollingShutter}",
            device_typ_server="actuator",
            room_id=100,
            value=2,
            value_timestamp=20_261_021_090_100,
        )
    )
    shutter = repository.make_shutters()[0]
    assert shutter.name == "Neuer Name"
    assert shutter.motion.value == "down"


def test_deleted_room_does_not_remove_shutter() -> None:
    repository = make_repository()
    repository.apply_room(RoomRecord(room_id=100, room_name="", is_deleted=True))
    assert repository.make_shutters()[0].master_id == 9001


def test_full_reload_clears_removed_devices() -> None:
    repository = make_repository()
    repository.apply(
        GatewaySnapshot(
            current_timestamp=1,
            compatibility_configuration_version="350",
            language_translation_version="124",
            rooms=(),
            devices=(),
            values=(),
            definitions=(),
            translations={},
            is_full_reload=True,
        )
    )
    assert repository.make_shutters() == ()
    assert repository.compatibility_version == "350"


def test_translation_resolution_for_name_and_room() -> None:
    repository = make_repository()
    # The fixture already resolves the room through the translation table.
    shutter = repository.make_shutters()[0]
    assert shutter.room_name == "Wohnzimmer"
    assert shutter.name == "Test Rollo"


def test_receiver_without_position_has_no_position_feature() -> None:
    repository = make_repository()
    repository.apply_device(
        DeviceRecord(
            device_id=9012,
            master_device_id=9011,
            device_name="Motor",
            master_device_name="Empfänger",
            device_designation="${SchellenbergRadioReceiverModuleSwitch}",
            device_typ_client="${SchellenbergRadioReceiverModuleSwitch}",
            device_typ_server="actuator",
            room_id=100,
            value=0,
            value_timestamp=20_261_021_090_000,
        )
    )
    receiver = next(s for s in repository.make_shutters() if s.master_id == 9011)
    assert receiver.position_component_id is None
    assert not receiver.supports_position
    assert receiver.product_family == "Funk-Empfangsschalter"
