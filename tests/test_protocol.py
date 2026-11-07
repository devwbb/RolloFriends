from __future__ import annotations

import pytest

from aiosmartfriends.exceptions import SmartFriendsProtocolError
from aiosmartfriends.protocol import (
    accepts_device_command_ack,
    accepts_hello,
    accepts_login,
    accepts_snapshot,
    command_login,
    command_set_device_value,
    get_case_insensitive,
    parse_wire_message,
)


def test_parse_response_with_nested_timestamp() -> None:
    message = parse_wire_message(
        b'{"response":{"currentTimestamp":20261021090000},"responseCode":1,"responseMessage":"success"}'
    )
    assert message.response_code == 1
    assert message.response_message == "success"
    assert message.current_timestamp == 20_261_021_090_000


def test_parse_top_level_timestamp_and_case_insensitive_keys() -> None:
    message = parse_wire_message(
        b'{"response":{"sessionid":"abc"},"responsecode":"1","currenttimestamp":"42"}'
    )
    assert message.response_code == 1
    assert message.current_timestamp == 42
    assert accepts_login(message)


def test_parse_rejects_invalid_json_and_missing_code() -> None:
    with pytest.raises(SmartFriendsProtocolError):
        parse_wire_message(b"not json")
    with pytest.raises(SmartFriendsProtocolError):
        parse_wire_message(b'{"response":{}}')


def test_hello_and_snapshot_expectations() -> None:
    hello = parse_wire_message(b'{"responseCode":1,"response":{"salt":"a","sessionSalt":"b"}}')
    assert accepts_hello(hello)
    assert not accepts_snapshot(hello)
    snapshot = parse_wire_message(
        b'{"responseCode":1,"response":{"newDeviceInfos":[],"currentTimestamp":1}}'
    )
    assert accepts_snapshot(snapshot)


def test_device_ack_rejects_snapshot_and_admin_shapes() -> None:
    ack = parse_wire_message(b'{"responseCode":1,"response":{}}')
    snapshot = parse_wire_message(
        b'{"responseCode":1,"response":{"newDeviceValues":[],"currentTimestamp":1}}'
    )
    users = parse_wire_message(b'{"responseCode":1,"response":{"allUsers":[]}}')
    assert accepts_device_command_ack(ack)
    assert not accepts_device_command_ack(snapshot)
    assert not accepts_device_command_ack(users)


def test_explicit_error_in_code_one_is_detected() -> None:
    message = parse_wire_message(
        b'{"responseCode":1,"responseMessage":"not allowed","response":{"errorCode":42}}'
    )
    assert message.has_explicit_error
    assert message.server_error_code == 42
    assert message.server_error_message == "not allowed"


def test_commands_target_component_id_not_master() -> None:
    command = command_set_device_value(9002, 1)
    assert command == {"command": "setDeviceValue", "deviceID": 9002, "value": 1}
    login = command_login("user", "digest")
    assert login["cSymbol"] == "D19033i"
    assert login["shcVersion"] == "3.6.2"
    assert login["shApiVersion"] == "3.3"


def test_get_case_insensitive() -> None:
    assert get_case_insensitive({"MasterDeviceID": 1}, "masterDeviceID") == 1
    assert get_case_insensitive(None, "x", 3) == 3
