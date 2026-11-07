"""Typed protocol models and snapshot parsing."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .protocol import WireMessage, get_case_insensitive

PRODUCT_FAMILIES = {
    "schellenbergrollodrive": "Rollodrive PREMIUM",
    "schellenbergrollodriveunidirectional": "Rollodrive PREMIUM",
    "schellenbergradioreceivermoduleswitch": "Funk-Empfangsschalter",
    "schellenbergradioreceivermoduleswitchunidirectional": "Funk-Empfangsschalter",
}

MEASURED_POSITION_KEYS = {"schellenbergposition"}
ADJUSTABLE_POSITION_KEYS = {"schellenbergpositionadjustable"}


class PositionSemantics(StrEnum):
    MEASURED = "measured"
    ADJUSTABLE = "adjustable"
    UNKNOWN = "unknown"

    @property
    def is_physically_measured(self) -> bool:
        return self is PositionSemantics.MEASURED


class ShutterMotion(StrEnum):
    UP = "up"
    DOWN = "down"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


def strip_language_lookup(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) > 3 and trimmed.startswith("${") and trimmed.endswith("}"):
        return trimmed[2:-1].strip()
    return trimmed or None


def normalize_key(value: str | None) -> str:
    stripped = strip_language_lookup(value) or ""
    return stripped.replace("_", "").casefold()


def localized(value: str | None, translations: Mapping[str, str]) -> str | None:
    """Resolve up to six chained translation keys."""

    current = value.strip() if isinstance(value, str) else None
    if not current:
        return None
    for _ in range(6):
        next_value: str | None = None
        lookup_key = strip_language_lookup(current)
        if lookup_key and lookup_key in translations:
            candidate = translations[lookup_key]
            if isinstance(candidate, str) and candidate and candidate != current:
                next_value = candidate
        if next_value is None and current in translations:
            candidate = translations[current]
            if isinstance(candidate, str) and candidate and candidate != current:
                next_value = candidate
        if next_value is None:
            return lookup_key or current
        current = next_value
    return current


def _as_int(value: Any) -> int | None:
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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _object_list(value: Any) -> list[Mapping[str, Any]]:
    """Accept an object, an array, or the legacy ``{"values": [...]}`` form."""

    if isinstance(value, Mapping):
        values = value.get("values")
        if isinstance(values, list):
            return [item for item in values if isinstance(item, Mapping)]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    session_id: str
    hardware: str | None = None
    shs_version: str | None = None
    api_major_version: str | None = None
    mac_address: str | None = None
    administrator_rights: bool | None = None


@dataclass(frozen=True, slots=True)
class BoxIdentity:
    mac_address: str | None = None
    is_configured: bool | None = None
    owner_created: bool | None = None
    owner_setup: bool | None = None
    email_validated: bool | None = None

    def has_identity_data(self) -> bool:
        return any(
            value is not None
            for value in (
                self.mac_address,
                self.is_configured,
                self.owner_created,
                self.owner_setup,
                self.email_validated,
            )
        )


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    acknowledged: bool
    sent: bool = True
    response_code: int | None = None
    response_message: str | None = None


@dataclass(frozen=True, slots=True)
class SwitchingValue:
    name: str
    value: int

    @property
    def normalized_name(self) -> str:
        return normalize_key(self.name)

    @classmethod
    def from_json(cls, value: Any) -> SwitchingValue | None:
        if not isinstance(value, Mapping):
            return None
        name = value.get("name")
        number = _as_int(value.get("value"))
        if not isinstance(name, str) or number is None:
            return None
        return cls(name=name, value=number)


@dataclass(frozen=True, slots=True)
class DeviceDefinition:
    device_designation: str
    device_typ_client: str | None = None
    device_typ_server: str | None = None
    device_type_name: str | None = None
    kind: str | None = None
    model: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    switching_values: tuple[SwitchingValue, ...] = ()
    hidden: Mapping[str, bool] = field(default_factory=dict)

    @property
    def normalized_kind(self) -> str | None:
        return normalize_key(self.kind) or None

    @property
    def is_hidden_in_overview(self) -> bool:
        return bool(self.hidden.get("deviceOverview"))

    @property
    def designation_key(self) -> str:
        return normalize_key(self.device_designation)

    def command_value(self, names: Iterable[str]) -> int | None:
        wanted = {name.casefold() for name in names}
        for item in self.switching_values:
            if item.normalized_name in wanted:
                return item.value
        return None

    @classmethod
    def from_json(cls, value: Any) -> DeviceDefinition | None:
        if not isinstance(value, Mapping):
            return None
        designation = value.get("deviceDesignation")
        device_type = value.get("deviceType")
        if not isinstance(designation, str) or not isinstance(device_type, Mapping):
            return None
        hidden_object = value.get("hidden")
        hidden: dict[str, bool] = {}
        if isinstance(hidden_object, Mapping):
            for key, item in hidden_object.items():
                if isinstance(key, str):
                    parsed = _as_bool(item)
                    if parsed is not None:
                        hidden[key] = parsed
        switching = device_type.get("switchingValues")
        switching_values = tuple(
            item
            for item in (
                SwitchingValue.from_json(entry)
                for entry in (switching if isinstance(switching, list) else [])
            )
            if item is not None
        )
        return cls(
            device_designation=designation,
            device_typ_client=_as_str(value.get("deviceTypClient")),
            device_typ_server=_as_str(value.get("deviceTypServer")),
            device_type_name=_as_str(device_type.get("type")),
            kind=_as_str(device_type.get("kind")),
            model=_as_str(device_type.get("model")),
            minimum=_as_float(device_type.get("min")),
            maximum=_as_float(device_type.get("max")),
            step=_as_float(device_type.get("step")),
            switching_values=switching_values,
            hidden=hidden,
        )


def _as_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_version(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    return _as_str(value)


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: int
    master_device_id: int
    device_name: str | None = None
    master_device_name: str | None = None
    device_designation: str | None = None
    device_typ_client: str | None = None
    device_typ_server: str | None = None
    product_designation: str | None = None
    manufacturer: str | None = None
    room_id: int | None = None
    first_level: bool = False
    is_hidden: bool = False
    value: Any = None
    value_target: Any = None
    value_current: Any = None
    value_timestamp: int | None = None

    @property
    def effective_master_id(self) -> int:
        return self.master_device_id if self.master_device_id > 0 else self.device_id

    @classmethod
    def from_json(cls, value: Any) -> DeviceRecord | None:
        if not isinstance(value, Mapping):
            return None
        device_id = _as_int(get_case_insensitive(value, "deviceID"))
        if device_id is None:
            device_id = _as_int(get_case_insensitive(value, "id"))
        if device_id is None:
            return None
        room_id = _as_int(get_case_insensitive(value, "roomID"))
        hidden_value = get_case_insensitive(value, "hidden")
        hidden = _as_bool(hidden_value)
        if hidden is None and isinstance(hidden_value, Mapping):
            hidden = _as_bool(hidden_value.get("deviceOverview"))
        return cls(
            device_id=device_id,
            master_device_id=_as_int(get_case_insensitive(value, "masterDeviceID")) or 0,
            device_name=_as_str(
                get_case_insensitive(value, "deviceName") or get_case_insensitive(value, "name")
            ),
            master_device_name=_as_str(get_case_insensitive(value, "masterDeviceName")),
            device_designation=_as_str(get_case_insensitive(value, "deviceDesignation")),
            device_typ_client=_as_str(get_case_insensitive(value, "deviceTypClient")),
            device_typ_server=_as_str(get_case_insensitive(value, "deviceTypServer")),
            product_designation=_as_str(get_case_insensitive(value, "productDesignation")),
            manufacturer=_as_str(get_case_insensitive(value, "manufacturer")),
            room_id=room_id if room_id and room_id > 0 else None,
            first_level=bool(_as_bool(get_case_insensitive(value, "firstLevel"))),
            is_hidden=bool(hidden),
            value=get_case_insensitive(value, "value"),
            value_target=get_case_insensitive(value, "valueTarget"),
            value_current=get_case_insensitive(value, "valueCurrent"),
            value_timestamp=_as_int(get_case_insensitive(value, "valueTimestamp")),
        )

    @classmethod
    def parse_list(cls, value: Any) -> tuple[DeviceRecord, ...]:
        return tuple(
            record
            for record in (cls.from_json(item) for item in _object_list(value))
            if record is not None
        )


@dataclass(frozen=True, slots=True)
class DeviceValueRecord:
    device_id: int
    master_device_id: int
    value: Any
    value_target: Any = None
    value_current: Any = None
    timestamp: int | None = None

    @property
    def effective_master_id(self) -> int:
        return self.master_device_id if self.master_device_id > 0 else self.device_id

    @classmethod
    def from_json(cls, value: Any) -> DeviceValueRecord | None:
        if not isinstance(value, Mapping):
            return None
        device_id = _as_int(get_case_insensitive(value, "deviceID"))
        if device_id is None or "value" not in value:
            return None
        return cls(
            device_id=device_id,
            master_device_id=_as_int(get_case_insensitive(value, "masterDeviceID")) or 0,
            value=get_case_insensitive(value, "value"),
            value_target=get_case_insensitive(value, "valueTarget"),
            value_current=get_case_insensitive(value, "valueCurrent"),
            timestamp=_as_int(get_case_insensitive(value, "valueTimestamp")),
        )

    @classmethod
    def parse_list(cls, value: Any) -> tuple[DeviceValueRecord, ...]:
        return tuple(
            record
            for record in (cls.from_json(item) for item in _object_list(value))
            if record is not None
        )


@dataclass(frozen=True, slots=True)
class RoomRecord:
    room_id: int
    room_name: str
    icon_name: str | None = None
    favorite: bool = False
    is_deleted: bool = False

    @classmethod
    def from_json(cls, value: Any) -> RoomRecord | None:
        if not isinstance(value, Mapping):
            return None
        room_id = _as_int(get_case_insensitive(value, "roomID"))
        if room_id is None:
            return None
        return cls(
            room_id=room_id,
            room_name=_as_str(get_case_insensitive(value, "roomName")) or "",
            icon_name=_as_str(get_case_insensitive(value, "iconName")),
            favorite=bool(_as_bool(get_case_insensitive(value, "favorite"))),
            is_deleted=bool(_as_bool(get_case_insensitive(value, "deletedRoom"))),
        )

    @classmethod
    def parse_list(cls, value: Any) -> tuple[RoomRecord, ...]:
        return tuple(
            record
            for record in (cls.from_json(item) for item in _object_list(value))
            if record is not None
        )


@dataclass(frozen=True, slots=True)
class GatewaySnapshot:
    current_timestamp: int | None
    compatibility_configuration_version: str | None
    language_translation_version: str | None
    rooms: tuple[RoomRecord, ...]
    devices: tuple[DeviceRecord, ...]
    values: tuple[DeviceValueRecord, ...]
    definitions: tuple[DeviceDefinition, ...]
    translations: Mapping[str, str]
    is_full_reload: bool


def _collect_translations(value: Any) -> dict[str, str]:
    translations: dict[str, str] = {}
    entries: list[Mapping[str, Any]] = []
    if isinstance(value, list):
        entries = [item for item in value if isinstance(item, Mapping)]
    elif isinstance(value, Mapping):
        nested = value.get("values")
        if isinstance(nested, list):
            entries = [item for item in nested if isinstance(item, Mapping)]
    for entry in entries:
        key = entry.get("key")
        translated = entry.get("value")
        if isinstance(key, str) and isinstance(translated, str):
            translations[key] = translated
    return translations


def _parse_definitions(compatibility: Any) -> tuple[DeviceDefinition, ...]:
    result: list[DeviceDefinition] = []
    seen: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if "deviceType" in value:
                definition = DeviceDefinition.from_json(value)
                if definition is not None:
                    key = definition.designation_key
                    if key and key not in seen:
                        seen.add(key)
                        result.append(definition)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(compatibility)
    return tuple(result)


def parse_snapshot(message: WireMessage, *, full_reload: bool) -> GatewaySnapshot:
    response = message.response
    devices = DeviceRecord.parse_list(get_case_insensitive(response, "newDeviceInfos"))
    values = DeviceValueRecord.parse_list(get_case_insensitive(response, "newDeviceValues"))
    rooms = RoomRecord.parse_list(get_case_insensitive(response, "newRoomInfos"))

    compatibility = get_case_insensitive(response, "newCompatibilityConfiguration")
    definitions = _parse_definitions(compatibility)
    compatibility_version: str | None = None
    language_version: str | None = None
    translations: dict[str, str] = {}

    if isinstance(compatibility, Mapping):
        compatibility_version = _as_version(
            get_case_insensitive(compatibility, "compatibilityConfigurationVersion")
        )
    language = get_case_insensitive(response, "newLanguageTranslation")
    if isinstance(language, Mapping):
        language_version = _as_version(get_case_insensitive(language, "languageTranslationVersion"))
        translations.update(
            _collect_translations(get_case_insensitive(language, "newTranslatedStrings"))
        )
    elif isinstance(language, list):
        translations.update(_collect_translations(language))

    timestamp = message.current_timestamp
    if timestamp is None:
        timestamp = _as_int(get_case_insensitive(response, "currentTimestamp"))

    return GatewaySnapshot(
        current_timestamp=timestamp,
        compatibility_configuration_version=compatibility_version,
        language_translation_version=language_version,
        rooms=rooms,
        devices=devices,
        values=values,
        definitions=definitions,
        translations=translations,
        is_full_reload=full_reload,
    )


@dataclass(frozen=True, slots=True)
class Shutter:
    master_id: int
    name: str
    room_id: int | None
    room_name: str
    manufacturer: str | None
    motor_component_id: int
    position_component_id: int | None
    up_value: int
    down_value: int
    stop_value: int
    position_min: float | None
    position_max: float | None
    position_step: float
    raw_position: float | None
    raw_target_position: float | None
    position_semantics: PositionSemantics
    position_definition_key: str | None
    motion: ShutterMotion
    motion_timestamp: int | None
    position_timestamp: int | None
    rssi_raw: int | None = None
    product_family: str | None = None

    @property
    def supports_position(self) -> bool:
        return (
            self.position_component_id is not None
            and self.position_min is not None
            and self.position_max is not None
            and self.position_max > self.position_min
            and self.position_semantics is not PositionSemantics.UNKNOWN
        )

    @property
    def supports_absolute_position(self) -> bool:
        return self.supports_position

    @property
    def position_span(self) -> float | None:
        if self.position_min is None or self.position_max is None:
            return None
        span = self.position_max - self.position_min
        return span if span > 0 else None

    @property
    def ha_position(self) -> float | None:
        span = self.position_span
        position_max = self.position_max
        if span is None or self.raw_position is None or position_max is None:
            return None
        value = (position_max - self.raw_position) / span * 100
        return min(max(value, 0.0), 100.0)

    @property
    def is_closed(self) -> bool | None:
        position = self.ha_position
        if position is None:
            return None
        return position <= 0.5

    def box_target_for_ha_position(self, ha_position: float) -> int | None:
        span = self.position_span
        if (
            not self.supports_position
            or span is None
            or self.position_min is None
            or self.position_max is None
        ):
            return None
        clamped = min(max(ha_position, 0.0), 100.0)
        raw = self.position_max - (clamped / 100.0) * span
        step = self.position_step if self.position_step > 0 else 1.0
        stepped = self.position_min + round((raw - self.position_min) / step) * step
        return round(min(max(stepped, self.position_min), self.position_max))

    def is_at_ha_position(self, ha_position: float) -> bool:
        current = self.ha_position
        if current is None:
            return False
        return abs(current - ha_position) <= 0.5

    def is_at_box_target(self, box_target: int) -> bool:
        if self.raw_target_position is None:
            return False
        return abs(self.raw_target_position - box_target) <= 0.5
