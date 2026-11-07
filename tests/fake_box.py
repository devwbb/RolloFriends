from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Mapping
from typing import Any

from aiosmartfriends.auth import digest as make_digest
from aiosmartfriends.transport import BoxTransport
from tests.test_models import SNAPSHOT

SALT = "MDEyMzQ1Njc4OWFiY2RlZg=="
SESSION_SALT = "ZmVkY2JhOTg3NjU0MzIxMA=="
SESSION_ID = "synthetic-session"
MAC = "AABBCCDDEEFF"


def snapshot_document() -> dict[str, Any]:
    return json.loads(SNAPSHOT)


class FakeBox:
    """Small asyncio test server implementing the documented wire protocol."""

    def __init__(self, *, password: str = "testpass", reject_login: bool = False) -> None:
        self.password = password
        self.reject_login = reject_login
        self.server: asyncio.Server | None = None
        self.port = 0
        self.connections: list[asyncio.StreamWriter] = []
        self.connection_count = 0
        self.login_count = 0
        self.commands: list[dict[str, Any]] = []
        self.no_ack = False
        self.send_notices = False
        self.next_delta_value: int | None = None
        self._writer_lock = asyncio.Lock()
        self._full_document = snapshot_document()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        sockets = self.server.sockets or []
        self.port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        await self.close_connections()

    async def close_connections(self) -> None:
        writers = list(self.connections)
        self.connections.clear()
        for writer in writers:
            writer.close()
        for writer in writers:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.5)

    async def send_push(self, payload: Mapping[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        async with self._writer_lock:
            writers = list(self.connections)
        for writer in writers:
            if not writer.is_closing():
                writer.write(data)
                await writer.drain()

    async def send_session_expired(self) -> None:
        await self.send_push(
            {"responseCode": 8, "responseMessage": "sessionExpired", "response": {}}
        )

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connection_count += 1
        async with self._writer_lock:
            self.connections.append(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    await self._handle_message(message, writer)
        except (ConnectionError, asyncio.CancelledError):
            return
        finally:
            if writer in self.connections:
                self.connections.remove(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.5)

    async def _write(self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]) -> None:
        if writer.is_closing():
            return
        writer.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        await writer.drain()

    async def _maybe_notices(self, writer: asyncio.StreamWriter) -> None:
        if not self.send_notices:
            return
        await self._write(
            writer,
            {
                "responseCode": 5,
                "responseMessage": "please update",
                "response": {"nextCommand": "success"},
            },
        )
        await self._write(
            writer,
            {"responseCode": 20, "responseMessage": "loginFinished", "response": {}},
        )

    async def _handle_message(
        self,
        message: dict[str, Any],
        writer: asyncio.StreamWriter,
    ) -> None:
        command = message.get("command")
        if command == "helo":
            await self._maybe_notices(writer)
            await self._write(
                writer,
                {
                    "responseCode": 1,
                    "responseMessage": "success",
                    "response": {
                        "majorApiVersion": "3",
                        "salt": SALT,
                        "sessionSalt": SESSION_SALT,
                    },
                },
            )
        elif command == "login":
            if self.reject_login or message.get("digest") != make_digest(
                self.password, SALT, SESSION_SALT
            ):
                await self._write(
                    writer,
                    {
                        "responseCode": -1,
                        "responseMessage": "invalid credentials",
                        "response": {"errorCode": 2},
                    },
                )
                return
            self.login_count += 1
            await self._maybe_notices(writer)
            await self._write(
                writer,
                {
                    "responseCode": 1,
                    "responseMessage": "success",
                    "response": {
                        "sessionID": SESSION_ID,
                        "hardware": "TestBox",
                        "shsVersion": "5.1.5-release",
                        "macAddress": MAC,
                    },
                },
            )
        elif command == "getAllNewInfos":
            self.commands.append(message)
            timestamp = int(message.get("timestamp", 0))
            if timestamp == 0:
                await self._write(writer, self._full_document)
            else:
                values: list[dict[str, Any]] = []
                if self.next_delta_value is not None:
                    values.append(
                        {
                            "deviceID": 9003,
                            "masterDeviceID": 9001,
                            "value": self.next_delta_value,
                            "valueTimestamp": 20_261_021_090_100,
                        }
                    )
                    self.next_delta_value = None
                await self._write(
                    writer,
                    {
                        "responseCode": 1,
                        "responseMessage": "success",
                        "response": {
                            "currentTimestamp": 20_261_021_090_100,
                            "newDeviceInfos": [],
                            "newDeviceValues": values,
                            "newRoomInfos": [],
                        },
                    },
                )
        elif command == "setDeviceValue":
            self.commands.append(message)
            if self.no_ack:
                return
            await self._write(writer, {"responseCode": 1, "response": {}})
        elif command == "logout":
            await self._write(writer, {"responseCode": 1, "response": {}})
        elif command == "getServerInfo":
            await self._write(
                writer,
                {
                    "responseCode": 1,
                    "responseMessage": "success",
                    "response": {
                        "macAddress": MAC,
                        "isConfigured": True,
                        "ownerCreated": True,
                        "ownerSetup": True,
                    },
                },
            )
        elif command == "keepalive":
            return
        else:
            await self._write(
                writer,
                {
                    "responseCode": -1,
                    "responseMessage": "unknown command",
                    "response": {"errorCode": 99},
                },
            )


async def plain_transport_factory(
    host: str,
    port: int,
    *,
    ssl_context: Any,
    timeout: float,
) -> BoxTransport:
    reader, writer = await asyncio.open_connection(host, port)
    return BoxTransport(reader, writer, host, port)


class PlainSnapshotBox:
    """Tiny server used by discovery tests; responds only to getServerInfo."""

    def __init__(self, mac: str = MAC) -> None:
        self.mac = mac
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        sockets = self.server.sockets or []
        self.port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            message = json.loads(line)
            if message.get("command") != "getServerInfo":
                writer.close()
                return
            writer.write(
                json.dumps(
                    {
                        "responseCode": 1,
                        "responseMessage": "success",
                        "response": {
                            "macAddress": self.mac,
                            "isConfigured": True,
                            "ownerCreated": True,
                            "ownerSetup": True,
                        },
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
