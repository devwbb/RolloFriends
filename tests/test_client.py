from __future__ import annotations

import asyncio
import logging

import pytest

from aiosmartfriends import (
    EVENT_DEVICE_VALUE,
    ConnectionState,
    SmartFriendsAuthenticationError,
    SmartFriendsClient,
    SmartFriendsSessionExpired,
)
from aiosmartfriends.discovery import async_probe_identity, normalize_mac, parse_mdns_identity
from aiosmartfriends.transport import create_pinned_ssl_context
from tests.fake_box import FakeBox, PlainSnapshotBox, plain_transport_factory


async def wait_until(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached in time")


def make_client(fake: FakeBox, **kwargs) -> SmartFriendsClient:
    defaults = {
        "auto_reconnect": False,
        "poll_interval": 60,
        "fast_poll_interval": 0.1,
        "connect_timeout": 2,
        "command_timeout": 0.5,
        "transport_factory": plain_transport_factory,
        "ssl_context": object(),
    }
    defaults.update(kwargs)
    return SmartFriendsClient(
        "127.0.0.1",
        fake.port,
        "testuser",
        "testpass",
        **defaults,
    )


@pytest.mark.asyncio
async def test_connect_login_snapshot_and_disconnect() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(fake)
    try:
        gateway = await client.async_connect()
        assert gateway.hardware == "TestBox"
        assert gateway.shs_version == "5.1.5-release"
        assert client.state is ConnectionState.CONNECTED
        assert len(client.shutters) == 1
        shutter = client.shutters[0]
        assert shutter.master_id == 9001
        assert shutter.motor_component_id == 9002
        assert shutter.position_component_id == 9003
        assert shutter.ha_position == 65
        assert fake.login_count == 1
    finally:
        await client.async_disconnect()
        await fake.stop()
    assert client.state is ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_login_rejection_is_authentication_error() -> None:
    fake = FakeBox(reject_login=True)
    await fake.start()
    client = make_client(fake)
    try:
        with pytest.raises(SmartFriendsAuthenticationError):
            await client.async_connect()
        assert client.state is ConnectionState.FAILED
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_command_targets_component_id_and_is_not_retried_on_timeout() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(fake)
    try:
        await client.async_connect()
        receipt = await client.async_set_device_value(9002, 1)
        assert receipt.acknowledged
        commands = [c for c in fake.commands if c.get("command") == "setDeviceValue"]
        assert commands == [
            {
                "command": "setDeviceValue",
                "sessionID": "synthetic-session",
                "deviceID": 9002,
                "value": 1,
            }
        ]

        fake.no_ack = True
        client.command_timeout = 0.05
        receipt = await client.async_set_device_value(9002, 2)
        assert receipt.sent
        assert not receipt.acknowledged
        await asyncio.sleep(0.2)
        commands = [c for c in fake.commands if c.get("command") == "setDeviceValue"]
        assert len(commands) == 2
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_push_updates_state_and_emits_event() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(fake)
    events = []
    client.add_event_listener(lambda event: events.append(event))
    try:
        await client.async_connect()
        await fake.send_push(
            {
                "responseCode": 2,
                "responseMessage": "newDeviceValue",
                "response": {
                    "deviceID": 9003,
                    "masterDeviceID": 9001,
                    "value": 80,
                    "valueTimestamp": 20_261_021_090_100,
                },
            }
        )
        await wait_until(lambda: client.shutters[0].raw_position == 80)
        assert client.shutters[0].ha_position == 20
        assert any(event.kind == EVENT_DEVICE_VALUE for event in events)
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_delta_poll_updates_state() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(fake, poll_interval=0.05)
    try:
        await client.async_connect()
        fake.next_delta_value = 42
        await wait_until(lambda: client.shutters[0].raw_position == 42)
        assert client.shutters[0].ha_position == pytest.approx(58)
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_reconnect_after_transport_loss() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(
        fake,
        auto_reconnect=True,
        poll_interval=60,
        reconnect_delays=(0.05, 0.05, 0.05),
    )
    try:
        await client.async_connect()
        await fake.close_connections()
        await wait_until(
            lambda: client.state is ConnectionState.CONNECTED and fake.connection_count >= 2,
            timeout=3,
        )
        assert len(client.shutters) == 1
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_session_expired_reconnects() -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(
        fake,
        auto_reconnect=True,
        poll_interval=60,
        reconnect_delays=(0.05, 0.05, 0.05),
    )
    try:
        await client.async_connect()
        await fake.send_session_expired()
        await wait_until(
            lambda: client.state is ConnectionState.CONNECTED and fake.connection_count >= 2,
            timeout=3,
        )
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_notices_5_and_20_do_not_close_requests() -> None:
    fake = FakeBox()
    fake.send_notices = True
    await fake.start()
    client = make_client(fake)
    try:
        gateway = await client.async_connect()
        assert gateway.session_id == "synthetic-session"
    finally:
        await client.async_disconnect()
        await fake.stop()


@pytest.mark.asyncio
async def test_identity_probe_is_read_only() -> None:
    fake = PlainSnapshotBox()
    await fake.start()
    try:
        identity = await async_probe_identity(
            "127.0.0.1",
            fake.port,
            timeout=1,
            transport_factory=plain_transport_factory,
            ssl_context=object(),
        )
        assert identity.mac_address == "AABBCCDDEEFF"
        assert identity.is_configured is True
    finally:
        await fake.stop()


def test_mdns_identity_parsing() -> None:
    identity = parse_mdns_identity(
        {"MacAddress": b"aa:bb:cc:dd:ee:ff", "Domain": b"D19033"},
        "Smart_Friends_Box-Test",
    )
    assert identity.mac_address == "AABBCCDDEEFF"
    assert identity.domain == "D19033"
    assert normalize_mac("not-a-mac") is None


def test_pinned_tls_context() -> None:
    context = create_pinned_ssl_context()
    assert context.check_hostname is False
    assert context.verify_mode.name == "CERT_REQUIRED"
    assert context.minimum_version.name == "TLSv1_2"
    assert context.get_ca_certs()


@pytest.mark.asyncio
async def test_no_credentials_in_debug_logs(caplog) -> None:
    fake = FakeBox()
    await fake.start()
    client = make_client(fake)
    caplog.set_level(logging.DEBUG)
    try:
        await client.async_connect()
        await client.async_set_device_value(9002, 1)
    finally:
        await client.async_disconnect()
        await fake.stop()
    text = caplog.text
    assert "testpass" not in text
    assert "synthetic-session" not in text
    assert "MDEyMzQ1Njc4OWFiY2RlZg" not in text


@pytest.mark.asyncio
async def test_parallel_clients_session_expiry_does_not_retry_command() -> None:
    fake = FakeBox()
    fake.no_ack = True
    await fake.start()
    first = make_client(
        fake,
        auto_reconnect=True,
        poll_interval=60,
        reconnect_delays=(0.05, 0.05, 0.05),
    )
    second = make_client(
        fake,
        auto_reconnect=True,
        poll_interval=60,
        reconnect_delays=(0.05, 0.05, 0.05),
    )
    try:
        await first.async_connect()
        await second.async_connect()
        command = asyncio.create_task(first.async_set_device_value(9002, 1))
        await wait_until(
            lambda: sum(1 for item in fake.commands if item.get("command") == "setDeviceValue") == 1
        )
        await fake.send_session_expired()
        with pytest.raises(SmartFriendsSessionExpired):
            await command
        await wait_until(
            lambda: (
                first.state is ConnectionState.CONNECTED
                and second.state is ConnectionState.CONNECTED
                and fake.connection_count >= 4
            ),
            timeout=5,
        )
        await asyncio.sleep(0.1)
        assert sum(1 for item in fake.commands if item.get("command") == "setDeviceValue") == 1
    finally:
        await first.async_disconnect()
        await second.async_disconnect()
        await fake.stop()
