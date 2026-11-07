"""Merge snapshots and push updates into a shutter-oriented repository."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .models import (
    ADJUSTABLE_POSITION_KEYS,
    MEASURED_POSITION_KEYS,
    PRODUCT_FAMILIES,
    DeviceDefinition,
    DeviceRecord,
    DeviceValueRecord,
    GatewaySnapshot,
    PositionSemantics,
    RoomRecord,
    Shutter,
    ShutterMotion,
    localized,
    normalize_key,
)


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


class DeviceRepository:
    """Authoritative in-memory state built from full and delta snapshots."""

    def __init__(self) -> None:
        self._rooms: dict[int, RoomRecord] = {}
        self._devices: dict[int, DeviceRecord] = {}
        self._values: dict[int, DeviceValueRecord] = {}
        self._definitions_by_designation: dict[str, DeviceDefinition] = {}
        self._definitions_by_type: dict[str, DeviceDefinition] = {}
        self._translations: dict[str, str] = {}
        self.compatibility_version = "0"
        self.language_version = "0"
        self.last_timestamp = 0
        self.last_update_monotonic: float | None = None

    @property
    def component_count(self) -> int:
        return len(self._devices)

    @property
    def all_rooms(self) -> tuple[RoomRecord, ...]:
        return tuple(
            sorted(
                self._rooms.values(),
                key=lambda room: room.room_name.casefold(),
            )
        )

    @property
    def all_device_records(self) -> tuple[DeviceRecord, ...]:
        return tuple(self._devices.values())

    @property
    def translations(self) -> Mapping[str, str]:
        return dict(self._translations)

    def apply(self, snapshot: GatewaySnapshot) -> None:
        if snapshot.is_full_reload:
            self._rooms.clear()
            self._devices.clear()
            self._values.clear()

        if snapshot.definitions:
            self._definitions_by_designation.clear()
            self._definitions_by_type.clear()
            for definition in snapshot.definitions:
                designation = definition.designation_key
                if designation:
                    self._definitions_by_designation[designation] = definition
                for candidate in (
                    definition.device_typ_client,
                    definition.device_typ_server,
                ):
                    key = normalize_key(candidate)
                    if key:
                        self._definitions_by_type[key] = definition

        if snapshot.translations:
            self._translations.update(snapshot.translations)
        if snapshot.compatibility_configuration_version:
            self.compatibility_version = snapshot.compatibility_configuration_version
        if snapshot.language_translation_version:
            self.language_version = snapshot.language_translation_version
        if snapshot.current_timestamp and snapshot.current_timestamp > 0:
            self.last_timestamp = snapshot.current_timestamp

        for room in snapshot.rooms:
            self.apply_room(room)
        for value in snapshot.values:
            self.apply_value(value)
        for device in snapshot.devices:
            self.apply_device(device)

    def apply_device(self, device: DeviceRecord) -> None:
        self._devices[device.device_id] = device
        if device.value is not None:
            self.apply_value(
                DeviceValueRecord(
                    device_id=device.device_id,
                    master_device_id=device.effective_master_id,
                    value=device.value,
                    value_target=device.value_target,
                    value_current=device.value_current,
                    timestamp=device.value_timestamp,
                )
            )

    def apply_value(self, value: DeviceValueRecord) -> None:
        existing = self._values.get(value.device_id)
        if (
            existing is not None
            and existing.timestamp is not None
            and value.timestamp is not None
            and value.timestamp < existing.timestamp
        ):
            return
        self._values[value.device_id] = value

    def apply_room(self, room: RoomRecord) -> None:
        if room.is_deleted:
            self._rooms.pop(room.room_id, None)
        else:
            self._rooms[room.room_id] = room

    def definition_for(self, device: DeviceRecord) -> DeviceDefinition | None:
        designation = normalize_key(device.device_designation)
        if designation and designation in self._definitions_by_designation:
            return self._definitions_by_designation[designation]
        for candidate in (device.device_typ_client, device.device_typ_server):
            key = normalize_key(candidate)
            if key and key in self._definitions_by_type:
                return self._definitions_by_type[key]
        return None

    def component_kind(self, device: DeviceRecord) -> str | None:
        definition = self.definition_for(device)
        if definition is not None and definition.normalized_kind:
            return definition.normalized_kind
        haystack = " ".join(
            normalize_key(candidate) or ""
            for candidate in (
                device.device_designation,
                device.device_typ_client,
                device.device_typ_server,
            )
        )
        if any(
            marker in haystack
            for marker in ("rollingshutter", "schellenbergblind", "radioreceiver")
        ):
            return "rollingshutter"
        if "position" in haystack:
            return "position"
        return None

    def value_for(self, device: DeviceRecord) -> Any:
        value = self._values.get(device.device_id)
        return value.value if value is not None else device.value

    def target_for(self, device: DeviceRecord) -> Any:
        value = self._values.get(device.device_id)
        if value is not None and value.value_target is not None:
            return value.value_target
        return device.value_target

    def timestamp_for(self, device: DeviceRecord) -> int | None:
        value = self._values.get(device.device_id)
        if value is not None and value.timestamp is not None:
            return value.timestamp
        return device.value_timestamp

    def _position_semantics(
        self,
        position: DeviceRecord | None,
        definition: DeviceDefinition | None,
    ) -> tuple[PositionSemantics, str | None]:
        key = normalize_key(
            position.device_designation
            if position is not None
            else (definition.device_designation if definition is not None else None)
        )
        if not key and definition is not None:
            key = definition.designation_key
        if key in MEASURED_POSITION_KEYS:
            return PositionSemantics.MEASURED, key
        if key in ADJUSTABLE_POSITION_KEYS:
            return PositionSemantics.ADJUSTABLE, key
        return PositionSemantics.UNKNOWN, key or None

    def _product_family(self, motor: DeviceRecord) -> str | None:
        key = normalize_key(motor.device_designation)
        if key and key in PRODUCT_FAMILIES:
            return PRODUCT_FAMILIES[key]
        return None

    def make_shutters(self) -> tuple[Shutter, ...]:
        groups: dict[int, list[DeviceRecord]] = defaultdict(list)
        for device in self._devices.values():
            groups[device.effective_master_id].append(device)

        shutters: list[Shutter] = []
        for master_id, components in groups.items():
            components.sort(key=lambda item: item.device_id)
            motor = next(
                (
                    component
                    for component in components
                    if self.component_kind(component) == "rollingshutter"
                ),
                None,
            )
            if motor is None:
                continue
            position = next(
                (
                    component
                    for component in components
                    if self.component_kind(component) == "position"
                ),
                None,
            )
            motor_definition = self.definition_for(motor)
            position_definition = self.definition_for(position) if position else None
            position_semantics, position_key = self._position_semantics(
                position, position_definition
            )

            up_value = (
                motor_definition.command_value({"up", "shutterup", "auf"})
                if motor_definition is not None
                else None
            )
            down_value = (
                motor_definition.command_value({"down", "shutterdown", "ab"})
                if motor_definition is not None
                else None
            )
            stop_value = (
                motor_definition.command_value({"stop", "shutterstop", "halt"})
                if motor_definition is not None
                else None
            )

            position_min: float | None = None
            position_max: float | None = None
            position_step = 1.0
            if position_definition is not None:
                position_min = position_definition.minimum
                position_max = position_definition.maximum
                if position_definition.step is not None and position_definition.step > 0:
                    position_step = position_definition.step
            if (
                position_semantics is not PositionSemantics.UNKNOWN
                and position_min is None
                and position_max is None
            ):
                # The verified Schellenberg definitions use this range.
                position_min, position_max = 0.0, 100.0

            raw_value = self.value_for(motor)
            motor_value = _int_value(raw_value)
            if motor_value is not None and motor_value == up_value:
                motion = ShutterMotion.UP
            elif motor_value is not None and motor_value == down_value:
                motion = ShutterMotion.DOWN
            elif motor_value is not None and motor_value == stop_value:
                motion = ShutterMotion.STOPPED
            else:
                motion = ShutterMotion.UNKNOWN

            raw_position = _float_value(self.value_for(position)) if position is not None else None
            raw_target = _float_value(self.target_for(position)) if position is not None else None
            room_id = motor.room_id or next(
                (component.room_id for component in components if component.room_id),
                None,
            )
            room = self._rooms.get(room_id) if room_id is not None else None
            raw_name = motor.master_device_name or next(
                (
                    component.master_device_name
                    for component in components
                    if component.master_device_name
                ),
                None,
            )
            if not raw_name:
                raw_name = motor.device_name
            name = localized(raw_name, self._translations) or "Rollladen"
            room_name = (
                localized(room.room_name, self._translations) if room is not None else None
            ) or "Ohne Raum"
            manufacturer = motor.manufacturer or next(
                (component.manufacturer for component in components if component.manufacturer),
                None,
            )
            rssi_component = next(
                (
                    component
                    for component in components
                    if "rssi"
                    in " ".join(
                        normalize_key(candidate) or ""
                        for candidate in (
                            component.device_designation,
                            component.device_typ_client,
                            component.device_name,
                        )
                    )
                ),
                None,
            )
            rssi_raw = (
                _int_value(self.value_for(rssi_component)) if rssi_component is not None else None
            )

            shutters.append(
                Shutter(
                    master_id=master_id,
                    name=name,
                    room_id=room_id,
                    room_name=room_name,
                    manufacturer=manufacturer,
                    motor_component_id=motor.device_id,
                    position_component_id=position.device_id if position else None,
                    up_value=up_value if up_value is not None else 1,
                    down_value=down_value if down_value is not None else 2,
                    stop_value=stop_value if stop_value is not None else 0,
                    position_min=position_min,
                    position_max=position_max,
                    position_step=position_step,
                    raw_position=raw_position,
                    raw_target_position=raw_target,
                    position_semantics=position_semantics,
                    position_definition_key=position_key,
                    motion=motion,
                    motion_timestamp=(self.timestamp_for(motor) if motor is not None else None),
                    position_timestamp=(
                        self.timestamp_for(position) if position is not None else None
                    ),
                    rssi_raw=rssi_raw,
                    product_family=self._product_family(motor),
                )
            )

        return tuple(
            sorted(
                shutters,
                key=lambda shutter: (
                    shutter.room_name.casefold(),
                    shutter.name.casefold(),
                    shutter.master_id,
                ),
            )
        )

    def shutter_for_master(self, master_id: int) -> Shutter | None:
        return next(
            (shutter for shutter in self.make_shutters() if shutter.master_id == master_id),
            None,
        )

    def device_for_component(self, component_id: int) -> DeviceRecord | None:
        return self._devices.get(component_id)
