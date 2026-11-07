"""Wire message parsing and command construction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .exceptions import SmartFriendsProtocolError

RESPONSE = 1
PUSH = 2
ERROR = -1
PASSWORD_CHANGE_REQUIRED = 3
NEW_CONFIGURATION = 4
NOTICE = 5
PROGRAMMING_PROCESS = 6
SESSION_EXPIRED = 8
LOGIN_FINISHED = 20

ASYNCHRONOUS_NOTICES = frozenset({NOTICE, LOGIN_FINISHED})

SNAPSHOT_KEYS = frozenset(
    {
        "newDeviceInfos",
        "newDeviceValues",
        "newRoomInfos",
        "newCompatibilityConfiguration",
        "newLanguageTranslation",
        "newSwitchingSequenceInfos",
        "newObjectInfos",
    }
)

ADMIN_OR_SNAPSHOT_KEYS = SNAPSHOT_KEYS | {"allUsers", "currentTimestamp"}


def get_case_insensitive(
    mapping: Mapping[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    """Look up a key case-insensitively, as required for some box firmwares."""

    if not isinstance(mapping, Mapping):
        return default
    if key in mapping:
        return mapping[key]
    wanted = key.casefold()
    for candidate, value in mapping.items():
        if isinstance(candidate, str) and candidate.casefold() == wanted:
            return value
    return default


def _coerce_int(value: Any) -> int | None:
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


@dataclass(frozen=True, slots=True)
class WireMessage:
    """One decoded JSON line from the box."""

    response_code: int
    response_message: str | None
    response: Mapping[str, Any]
    current_timestamp: int | None
    raw: Mapping[str, Any]

    @property
    def is_success_response(self) -> bool:
        return self.response_code == RESPONSE

    @property
    def is_push_event(self) -> bool:
        return self.response_code == PUSH

    @property
    def is_session_expired(self) -> bool:
        return self.response_code == SESSION_EXPIRED

    @property
    def is_asynchronous_notice(self) -> bool:
        return self.response_code in ASYNCHRONOUS_NOTICES

    @property
    def server_error_code(self) -> int | None:
        value = get_case_insensitive(self.response, "errorCode")
        if value is None:
            value = get_case_insensitive(self.raw, "errorCode")
        return _coerce_int(value)

    @property
    def server_error_message(self) -> str:
        message = self.response_message
        if isinstance(message, str) and message.strip():
            return message.strip()
        for key in ("errorMessage", "message", "error"):
            value = get_case_insensitive(self.response, key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Unknown error from the box"

    @property
    def has_explicit_error(self) -> bool:
        code = self.server_error_code
        if code not in (None, 0):
            return True
        message = self.response_message
        return bool(
            isinstance(message, str)
            and message.strip()
            and message.strip().casefold() not in {"success", "ok"}
        )


def parse_wire_message(data: bytes) -> WireMessage:
    """Parse one UTF-8 JSON line into a :class:`WireMessage`."""

    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SmartFriendsProtocolError("The box sent invalid JSON") from err
    if not isinstance(decoded, dict):
        raise SmartFriendsProtocolError("The box sent a non-object JSON message")

    code = _coerce_int(get_case_insensitive(decoded, "responseCode"))
    if code is None:
        raise SmartFriendsProtocolError("The box response has no responseCode")

    raw_response = get_case_insensitive(decoded, "response")
    response: Mapping[str, Any] = raw_response if isinstance(raw_response, dict) else {}
    message = get_case_insensitive(decoded, "responseMessage")
    timestamp = _coerce_int(get_case_insensitive(response, "currentTimestamp"))
    if timestamp is None:
        timestamp = _coerce_int(get_case_insensitive(decoded, "currentTimestamp"))

    return WireMessage(
        response_code=code,
        response_message=message if isinstance(message, str) else None,
        response=response,
        current_timestamp=timestamp,
        raw=decoded,
    )


def accepts_hello(message: WireMessage) -> bool:
    salt = get_case_insensitive(message.response, "salt")
    session_salt = get_case_insensitive(message.response, "sessionSalt")
    return (
        isinstance(salt, str)
        and bool(salt)
        and isinstance(session_salt, str)
        and bool(session_salt)
    )


def accepts_login(message: WireMessage) -> bool:
    session_id = get_case_insensitive(message.response, "sessionID") or get_case_insensitive(
        message.response, "sessionId"
    )
    return isinstance(session_id, str) and bool(session_id.strip())


def accepts_snapshot(message: WireMessage) -> bool:
    return bool(SNAPSHOT_KEYS.intersection(message.response)) or (
        message.current_timestamp is not None
    )


def accepts_device_command_ack(message: WireMessage) -> bool:
    """Reject late snapshots or administration data as a command ack.

    The protocol has no request IDs; shape checking is the only safe way to
    avoid attributing a late snapshot to a motor command.
    """

    return not ADMIN_OR_SNAPSHOT_KEYS.intersection(message.response)


def command_helo(username: str) -> dict[str, Any]:
    return {"command": "helo", "username": username}


def command_login(
    username: str,
    digest_value: str,
    *,
    c_symbol: str = "D19033i",
    shc_version: str = "3.6.2",
    sh_api_version: str = "3.3",
) -> dict[str, Any]:
    return {
        "command": "login",
        "username": username,
        "digest": digest_value,
        "cSymbol": c_symbol,
        "shcVersion": shc_version,
        "shApiVersion": sh_api_version,
    }


def command_get_all_new_infos(
    timestamp: int,
    compatibility_configuration_version: str,
    language_translation_version: str,
) -> dict[str, Any]:
    return {
        "command": "getAllNewInfos",
        "timestamp": timestamp,
        "compatibilityConfigurationVersion": compatibility_configuration_version,
        "languageTranslationVersion": language_translation_version,
    }


def command_set_device_value(component_id: int, value: int) -> dict[str, Any]:
    return {
        "command": "setDeviceValue",
        "deviceID": component_id,
        "value": value,
    }


def command_get_server_info() -> dict[str, Any]:
    return {"command": "getServerInfo"}


def command_logout() -> dict[str, Any]:
    return {"command": "logout"}


def command_keepalive() -> dict[str, Any]:
    """Exposed for diagnostics only; the box does not answer it."""

    return {"command": "keepalive"}
