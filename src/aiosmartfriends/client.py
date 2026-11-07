"""Long-lived asyncio client for a SmartFriends Box."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import ssl
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .auth import digest as make_digest
from .exceptions import (
    SmartFriendsAuthenticationError,
    SmartFriendsCancelled,
    SmartFriendsCommandRejected,
    SmartFriendsConnectionError,
    SmartFriendsError,
    SmartFriendsNotConnected,
    SmartFriendsProtocolError,
    SmartFriendsServerError,
    SmartFriendsSessionExpired,
    SmartFriendsTimeout,
)
from .framing import LineFramer, encode_message
from .gate import RequestGate
from .models import (
    CommandReceipt,
    ConnectionState,
    DeviceRecord,
    DeviceValueRecord,
    GatewayInfo,
    GatewaySnapshot,
    RoomRecord,
    Shutter,
    parse_snapshot,
)
from .protocol import (
    ERROR,
    PASSWORD_CHANGE_REQUIRED,
    PROGRAMMING_PROCESS,
    PUSH,
    RESPONSE,
    SESSION_EXPIRED,
    WireMessage,
    accepts_device_command_ack,
    accepts_hello,
    accepts_login,
    accepts_snapshot,
    command_get_all_new_infos,
    command_helo,
    command_login,
    command_logout,
    command_set_device_value,
    get_case_insensitive,
    parse_wire_message,
)
from .repository import DeviceRepository
from .transport import BoxTransport, create_pinned_ssl_context

_LOGGER = logging.getLogger(__name__)

TransportFactory = Callable[..., Awaitable[Any]]
Listener = Callable[["ClientEvent"], Awaitable[None] | None]

EVENT_CONNECTION = "connection"
EVENT_SNAPSHOT = "snapshot"
EVENT_DEVICE_VALUE = "device_value"
EVENT_DEVICE_INFO = "device_info"
EVENT_ROOM = "room"
EVENT_ERROR = "error"
EVENT_AUTH_FAILED = "auth_failed"
EVENT_CONFIG_CHANGED = "config_changed"


@dataclass(frozen=True, slots=True)
class ClientEvent:
    kind: str
    data: Any = None


@dataclass(slots=True)
class _Pending:
    future: asyncio.Future[WireMessage]
    expectation: Callable[[WireMessage], bool]


@dataclass(slots=True)
class _Cursor:
    timestamp: int = 0
    compatibility_version: str = "0"
    language_version: str = "0"


class SmartFriendsClient:
    """One connection, one request gate, one poll task, one reconnect loop."""

    def __init__(
        self,
        host: str,
        port: int = 4300,
        username: str = "",
        password: str = "",
        *,
        c_symbol: str = "D19033i",
        shc_version: str = "3.6.2",
        sh_api_version: str = "3.3",
        connect_timeout: float = 12.0,
        command_timeout: float = 2.5,
        full_snapshot_timeout: float = 20.0,
        delta_snapshot_timeout: float = 12.0,
        auto_reconnect: bool = True,
        poll_interval: float = 5.0,
        fast_poll_interval: float = 1.5,
        fast_poll_duration: float = 30.0,
        reconnect_delays: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 30.0),
        transport_factory: TransportFactory | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.host = host.strip()
        self.port = port
        self.username = username.strip()
        self._password = password
        self.c_symbol = c_symbol.strip()
        self.shc_version = shc_version.strip()
        self.sh_api_version = sh_api_version.strip()
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.full_snapshot_timeout = full_snapshot_timeout
        self.delta_snapshot_timeout = delta_snapshot_timeout
        self.auto_reconnect = auto_reconnect
        self.poll_interval = max(poll_interval, 0.05)
        self.fast_poll_interval = max(fast_poll_interval, 0.05)
        self.fast_poll_duration = max(fast_poll_duration, 1.0)
        self._reconnect_delays = reconnect_delays or (2.0, 4.0, 8.0, 16.0, 30.0)
        self._transport_factory = transport_factory or self._default_transport_factory
        self._ssl_context = ssl_context

        self._repository = DeviceRepository()
        self._state = ConnectionState.DISCONNECTED
        self._gateway: GatewayInfo | None = None
        self._transport: Any = None
        self._reader_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._loss_lock = asyncio.Lock()
        self._gate = RequestGate()
        self._framer = LineFramer()
        self._pending: _Pending | None = None
        self._cursor = _Cursor()
        self._listeners: list[Listener] = []
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._running = False
        self._explicit_disconnect = False
        self._reconnect_attempt = 0
        self._last_snapshot_monotonic: float | None = None
        self._last_snapshot_at: datetime | None = None
        self._fast_poll_until = 0.0
        self._next_poll_due = 0.0
        self._force_full_next_poll = False
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Public state

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def gateway(self) -> GatewayInfo | None:
        return self._gateway

    @property
    def repository(self) -> DeviceRepository:
        return self._repository

    @property
    def shutters(self) -> tuple[Shutter, ...]:
        return self._repository.make_shutters()

    @property
    def last_snapshot_at(self) -> datetime | None:
        return self._last_snapshot_at

    @property
    def last_snapshot_monotonic(self) -> float | None:
        return self._last_snapshot_monotonic

    @property
    def is_connected(self) -> bool:
        return self._state is ConnectionState.CONNECTED and self._transport is not None

    def is_fresh(self, max_age: float = 30.0) -> bool:
        if not self.is_connected or self._last_snapshot_monotonic is None:
            return False
        return (asyncio.get_running_loop().time() - self._last_snapshot_monotonic) <= max_age

    def add_event_listener(self, listener: Listener) -> Callable[[], None]:
        if not callable(listener):
            raise TypeError("listener must be callable")
        self._listeners.append(listener)

        def remove() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return remove

    # ------------------------------------------------------------------
    # Lifecycle

    async def async_connect(self) -> GatewayInfo:
        self._validate_configuration()
        if self._running:
            if self._gateway is not None:
                return self._gateway
            raise SmartFriendsConnectionError("Connection setup is already running")

        self._running = True
        self._explicit_disconnect = False
        self._reconnect_attempt = 0
        self._state = ConnectionState.CONNECTING
        self.last_error = None
        self._emit_connection()
        try:
            gateway = await self._establish()
        except asyncio.CancelledError:
            await self._close_transport()
            self._running = False
            self._state = ConnectionState.DISCONNECTED
            self._emit_connection()
            raise
        except Exception as err:
            mapped = self._map_error(err)
            await self._close_transport()
            self._running = False
            self._state = ConnectionState.FAILED
            self.last_error = str(mapped)
            self._emit_connection()
            self._emit(ClientEvent(EVENT_ERROR, mapped))
            raise mapped from err

        self._start_polling()
        return gateway

    async def async_disconnect(self) -> None:
        self._explicit_disconnect = True
        self._running = False
        self._cancel_task("_reconnect_task")
        self._cancel_task("_poll_task")
        if self.is_connected and self._gateway is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    self._perform(
                        command_logout(),
                        expectation=lambda message: True,
                        timeout=1.5,
                        requires_session=True,
                    ),
                    timeout=2.0,
                )
        await self._close_transport()
        self._gateway = None
        self._password = ""
        self._state = ConnectionState.DISCONNECTED
        self._emit_connection()

    async def async_request_fast_poll(self, duration: float = 30.0) -> None:
        if not self._running:
            return
        loop = asyncio.get_running_loop()
        self._fast_poll_until = max(self._fast_poll_until, loop.time() + max(duration, 5.0))
        if self._next_poll_due > 0:
            self._next_poll_due = min(self._next_poll_due, loop.time() + 0.2)

    # ------------------------------------------------------------------
    # Requests

    async def async_get_snapshot(self, *, full: bool = False) -> GatewaySnapshot:
        if not self.is_connected:
            raise SmartFriendsNotConnected("The client is not connected")
        return await self._fetch_snapshot(full=full)

    async def async_set_device_value(
        self,
        component_id: int,
        value: int,
    ) -> CommandReceipt:
        if not self.is_connected:
            raise SmartFriendsNotConnected("The client is not connected")
        if component_id <= 0:
            raise ValueError("component_id must be positive")
        await self.async_request_fast_poll(self.fast_poll_duration)
        try:
            message = await self._perform(
                command_set_device_value(component_id, value),
                expectation=accepts_device_command_ack,
                timeout=self.command_timeout,
                requires_session=True,
                priority=10,
            )
        except SmartFriendsTimeout:
            # The bytes may have been sent. This is neither a failure nor a
            # confirmation, and must never trigger an automatic retry.
            _LOGGER.info("Device command was sent without acknowledgement")
            return CommandReceipt(acknowledged=False, sent=True)
        except SmartFriendsServerError as err:
            raise SmartFriendsCommandRejected(str(err), code=err.code) from err
        return CommandReceipt(
            acknowledged=True,
            sent=True,
            response_code=message.response_code,
            response_message=message.response_message,
        )

    # ------------------------------------------------------------------
    # Establishment and authentication

    async def _establish(self) -> GatewayInfo:
        await self._close_transport()
        self._state = ConnectionState.CONNECTING
        self._emit_connection()
        try:
            context = self._ssl_context
            if context is None:
                context = create_pinned_ssl_context()
            transport = await asyncio.wait_for(
                self._transport_factory(
                    self.host,
                    self.port,
                    ssl_context=context,
                    timeout=self.connect_timeout,
                ),
                timeout=self.connect_timeout,
            )
        except TimeoutError as err:
            raise SmartFriendsConnectionError("Timeout while connecting to the box") from err
        except SmartFriendsError:
            raise
        except Exception as err:
            raise self._map_error(err) from err

        self._transport = transport
        self._framer.reset()
        self._state = ConnectionState.AUTHENTICATING
        self._emit_connection()
        self._start_reader()

        try:
            gateway = await self._authenticate()
            self._gateway = gateway
            await self._fetch_snapshot(full=True)
            self._state = ConnectionState.CONNECTED
            self._reconnect_attempt = 0
            self.last_error = None
            self._emit_connection()
            _LOGGER.info(
                "Connected to SmartFriends box %s (hardware %s, software %s)",
                self.host,
                gateway.hardware or "unknown",
                gateway.shs_version or "unknown",
            )
            return gateway
        except Exception:
            await self._close_transport()
            raise

    async def _authenticate(self) -> GatewayInfo:
        hello_message = await self._perform(
            command_helo(self.username),
            expectation=accepts_hello,
            timeout=10.0,
            requires_session=False,
        )
        salt = get_case_insensitive(hello_message.response, "salt")
        session_salt = get_case_insensitive(hello_message.response, "sessionSalt")
        if not isinstance(salt, str) or not isinstance(session_salt, str):
            raise SmartFriendsAuthenticationError("The box did not return a challenge")
        try:
            digest_value = make_digest(self._password, salt, session_salt)
        except SmartFriendsProtocolError as err:
            raise SmartFriendsAuthenticationError(
                "The box challenge contained invalid salt data"
            ) from err

        try:
            login_message = await self._perform(
                command_login(
                    self.username,
                    digest_value,
                    c_symbol=self.c_symbol,
                    shc_version=self.shc_version,
                    sh_api_version=self.sh_api_version,
                ),
                expectation=accepts_login,
                timeout=10.0,
                requires_session=False,
            )
        except SmartFriendsServerError as err:
            raise SmartFriendsAuthenticationError(str(err)) from err
        session_id = get_case_insensitive(
            login_message.response, "sessionID"
        ) or get_case_insensitive(login_message.response, "sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise SmartFriendsAuthenticationError("The box did not issue a session")
        return GatewayInfo(
            session_id=session_id,
            hardware=_optional_text(get_case_insensitive(login_message.response, "hardware")),
            shs_version=_optional_text(get_case_insensitive(login_message.response, "shsVersion")),
            api_major_version=_optional_text(
                get_case_insensitive(hello_message.response, "majorApiVersion")
            ),
            mac_address=_optional_text(get_case_insensitive(login_message.response, "macAddress")),
            administrator_rights=_optional_bool(get_case_insensitive(login_message.response, "aR")),
        )

    async def _fetch_snapshot(self, *, full: bool) -> GatewaySnapshot:
        timeout = self.full_snapshot_timeout if full else self.delta_snapshot_timeout
        command = command_get_all_new_infos(
            0 if full else self._cursor.timestamp,
            "0" if full else self._cursor.compatibility_version,
            "0" if full else self._cursor.language_version,
        )
        message = await self._perform(
            command,
            expectation=accepts_snapshot,
            timeout=timeout,
            requires_session=True,
        )
        snapshot = parse_snapshot(message, full_reload=full)
        self._repository.apply(snapshot)
        if snapshot.current_timestamp and snapshot.current_timestamp > 0:
            self._cursor.timestamp = snapshot.current_timestamp
        if snapshot.compatibility_configuration_version:
            self._cursor.compatibility_version = snapshot.compatibility_configuration_version
        if snapshot.language_translation_version:
            self._cursor.language_version = snapshot.language_translation_version
        loop = asyncio.get_running_loop()
        self._last_snapshot_monotonic = loop.time()
        self._last_snapshot_at = datetime.now(UTC)
        self._force_full_next_poll = False
        _LOGGER.debug(
            "Applied %s snapshot: %s components",
            "full" if full else "delta",
            self._repository.component_count,
        )
        self._emit(ClientEvent(EVENT_SNAPSHOT, snapshot))
        return snapshot

    async def _perform(
        self,
        command: dict[str, Any],
        *,
        expectation: Callable[[WireMessage], bool],
        timeout: float,
        requires_session: bool,
        priority: int = 0,
    ) -> WireMessage:
        if self._transport is None:
            raise SmartFriendsNotConnected("The client is not connected")
        payload = dict(command)
        if requires_session:
            if self._gateway is None:
                raise SmartFriendsNotConnected("No authenticated session")
            payload["sessionID"] = self._gateway.session_id
        data = encode_message(payload)

        await self._gate.acquire(priority)
        try:
            if self._transport is None:
                raise SmartFriendsNotConnected("The client is not connected")
            loop = asyncio.get_running_loop()
            future: asyncio.Future[WireMessage] = loop.create_future()
            pending = _Pending(future=future, expectation=expectation)
            self._pending = pending
            try:
                await asyncio.wait_for(self._transport.send(data), timeout=timeout)
                message = await asyncio.wait_for(future, timeout=timeout)
            except TimeoutError as err:
                raise SmartFriendsTimeout("The box did not answer in time") from err
            finally:
                if self._pending is pending:
                    self._pending = None

            if message.has_explicit_error:
                raise SmartFriendsServerError(
                    message.server_error_message,
                    code=message.server_error_code,
                )
            return message
        finally:
            self._gate.release()

    # ------------------------------------------------------------------
    # Reader and dispatching

    def _start_reader(self) -> None:
        self._cancel_task("_reader_task")
        self._reader_task = asyncio.create_task(
            self._reader_loop(),
            name="aiosmartfriends-reader",
        )

    async def _reader_loop(self) -> None:
        try:
            while self._running:
                transport = self._transport
                if transport is None:
                    return
                data = await transport.read(65536)
                if not data:
                    raise SmartFriendsConnectionError("The box closed the connection")
                for frame in self._framer.feed(data):
                    self._dispatch_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            await self._handle_transport_loss(self._map_error(err))

    def _dispatch_frame(self, frame: bytes) -> None:
        try:
            message = parse_wire_message(frame)
        except SmartFriendsProtocolError:
            _LOGGER.warning("Discarded an invalid JSON line from the box")
            return

        if message.response_code == RESPONSE:
            pending = self._pending
            if pending is None:
                return
            if message.has_explicit_error:
                if not pending.future.done():
                    pending.future.set_exception(
                        SmartFriendsServerError(
                            message.server_error_message,
                            code=message.server_error_code,
                        )
                    )
                self._emit(
                    ClientEvent(
                        EVENT_ERROR,
                        SmartFriendsServerError(
                            message.server_error_message,
                            code=message.server_error_code,
                        ),
                    )
                )
                return
            if pending.expectation(message):
                if not pending.future.done():
                    pending.future.set_result(message)
            else:
                _LOGGER.debug("Discarded a response with an unexpected shape")
        elif message.response_code == ERROR:
            error = SmartFriendsServerError(
                message.server_error_message,
                code=message.server_error_code,
            )
            pending = self._pending
            if pending is not None and not pending.future.done():
                pending.future.set_exception(error)
            else:
                self._emit(ClientEvent(EVENT_ERROR, error))
        elif message.response_code == PUSH:
            self._handle_push(message)
        elif message.response_code == SESSION_EXPIRED:
            session_error = SmartFriendsSessionExpired("The box session expired")
            pending = self._pending
            if pending is not None and not pending.future.done():
                pending.future.set_exception(session_error)
            self._emit(ClientEvent(EVENT_ERROR, session_error))
            self._spawn_background(self._handle_transport_loss(session_error))
        elif message.response_code == PASSWORD_CHANGE_REQUIRED:
            auth_error = SmartFriendsAuthenticationError(
                "The box requires a password change"
            )
            pending = self._pending
            if pending is not None and not pending.future.done():
                pending.future.set_exception(auth_error)
            self._spawn_background(self._handle_auth_failure(auth_error))
        elif message.response_code == PROGRAMMING_PROCESS:
            _LOGGER.debug("Ignoring a pairing progress message")
        elif message.response_code == 4:
            self._force_full_next_poll = True
            self._emit(ClientEvent(EVENT_CONFIG_CHANGED, message))
        elif message.is_asynchronous_notice:
            return
        else:
            _LOGGER.debug("Ignoring response code %s", message.response_code)

    def _handle_push(self, message: WireMessage) -> None:
        name = (message.response_message or "").casefold()
        if name == "newdevicevalue":
            values = DeviceValueRecord.parse_list(message.response)
            for value in values:
                self._repository.apply_value(value)
                self._emit(ClientEvent(EVENT_DEVICE_VALUE, value))
        elif name == "newdeviceinfo":
            devices = DeviceRecord.parse_list(message.response)
            for device in devices:
                self._repository.apply_device(device)
                self._emit(ClientEvent(EVENT_DEVICE_INFO, device))
        elif name == "newroominfo":
            rooms = RoomRecord.parse_list(message.response)
            for room in rooms:
                self._repository.apply_room(room)
                self._emit(ClientEvent(EVENT_ROOM, room))
        else:
            _LOGGER.debug("Ignoring push event %s", name or "unknown")

    # ------------------------------------------------------------------
    # Polling and reconnect

    def _start_polling(self) -> None:
        self._cancel_task("_poll_task")
        self._next_poll_due = asyncio.get_running_loop().time() + self.poll_interval
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name="aiosmartfriends-poll",
        )

    async def _poll_loop(self) -> None:
        try:
            while self._running:
                loop = asyncio.get_running_loop()
                now = loop.time()
                due = self._next_poll_due
                if now < due:
                    await asyncio.sleep(min(max(due - now, 0.05), 0.5))
                    continue
                if not self.is_connected or self._gate.busy:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    await self._fetch_snapshot(full=self._force_full_next_poll)
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    await self._handle_transport_loss(self._map_error(err))
                    return
                loop = asyncio.get_running_loop()
                self._next_poll_due = loop.time() + (
                    self.fast_poll_interval
                    if loop.time() < self._fast_poll_until
                    else self.poll_interval
                )
        except asyncio.CancelledError:
            raise

    async def _handle_transport_loss(self, reason: Exception) -> None:
        async with self._loss_lock:
            if not self._running or self._explicit_disconnect:
                return
            if self._state in (ConnectionState.RECONNECTING, ConnectionState.FAILED):
                return
            _LOGGER.warning("Connection to the box was lost: %s", reason)
            self.last_error = str(reason)
            self._state = ConnectionState.RECONNECTING
            self._emit_connection()
            await self._close_transport(close_reader=True)
            if not self.auto_reconnect:
                self._running = False
                self._state = ConnectionState.FAILED
                self._emit_connection()
                return
            self._reconnect_task = asyncio.create_task(
                self._reconnect_loop(),
                name="aiosmartfriends-reconnect",
            )

    async def _handle_auth_failure(self, error: Exception) -> None:
        self._running = False
        self._cancel_task("_poll_task")
        self._state = ConnectionState.FAILED
        self.last_error = str(error)
        self._emit(ClientEvent(EVENT_AUTH_FAILED, error))
        self._emit_connection()
        await self._close_transport()

    async def _reconnect_loop(self) -> None:
        try:
            while self.auto_reconnect:
                if not self._should_reconnect():
                    return
                self._reconnect_attempt += 1
                delay = self._reconnect_delay(self._reconnect_attempt)
                await asyncio.sleep(delay)
                if not self._should_reconnect():
                    return
                self._state = ConnectionState.RECONNECTING
                self._emit_connection()
                try:
                    await self._establish()
                except SmartFriendsAuthenticationError as err:
                    await self._handle_auth_failure(err)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    self.last_error = str(self._map_error(err))
                    _LOGGER.warning(
                        "Reconnect attempt %s failed: %s",
                        self._reconnect_attempt,
                        self.last_error,
                    )
                    continue
                self._start_polling()
                return
        finally:
            self._reconnect_task = None

    def _should_reconnect(self) -> bool:
        return self._running and self.auto_reconnect and not self._explicit_disconnect

    def _reconnect_delay(self, attempt: int) -> float:
        index = max(0, attempt - 1)
        if index < len(self._reconnect_delays):
            return self._reconnect_delays[index]
        return self._reconnect_delays[-1]

    # ------------------------------------------------------------------
    # Teardown and helpers

    async def _close_transport(self, *, close_reader: bool = True) -> None:
        self._gate.fail_waiters(SmartFriendsNotConnected("Connection closed"))
        pending = self._pending
        self._pending = None
        if pending is not None and not pending.future.done():
            pending.future.set_exception(
                SmartFriendsNotConnected("Connection closed while waiting for a response")
            )
        transport = self._transport
        self._transport = None
        if close_reader:
            current = asyncio.current_task()
            if self._reader_task is not None and self._reader_task is not current:
                self._reader_task.cancel()
            self._reader_task = None
        if transport is not None:
            with contextlib.suppress(Exception):
                await transport.close()
        self._framer.reset()

    def _cancel_task(self, attribute: str) -> None:
        task = getattr(self, attribute)
        if task is not None and not task.done():
            task.cancel()
        setattr(self, attribute, None)

    def _emit(self, event: ClientEvent) -> None:
        for listener in tuple(self._listeners):
            try:
                result = listener(event)
            except Exception:
                _LOGGER.exception("Event listener failed")
                continue
            if inspect.isawaitable(result):
                self._spawn_background(self._run_listener(result))

    def _spawn_background(self, awaitable: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _run_listener(self, awaitable: Awaitable[None]) -> None:
        try:
            await awaitable
        except Exception:
            _LOGGER.exception("Async event listener failed")

    def _emit_connection(self) -> None:
        self._emit(ClientEvent(EVENT_CONNECTION, self._state))

    def _validate_configuration(self) -> None:
        if not self.host:
            raise SmartFriendsConnectionError("A box host is required")
        if not (1 <= self.port <= 65535):
            raise SmartFriendsConnectionError("The box port is invalid")
        if not self.username:
            raise SmartFriendsAuthenticationError("A username is required")
        if not self._password:
            raise SmartFriendsAuthenticationError("A password is required")
        for value, name in (
            (self.c_symbol, "cSymbol"),
            (self.shc_version, "shcVersion"),
            (self.sh_api_version, "shApiVersion"),
        ):
            if not value:
                raise SmartFriendsConnectionError(f"{name} must not be empty")

    async def _default_transport_factory(
        self,
        host: str,
        port: int,
        *,
        ssl_context: ssl.SSLContext,
        timeout: float,
    ) -> BoxTransport:
        return await BoxTransport.open(
            host,
            port,
            ssl_context=ssl_context,
            timeout=timeout,
        )

    @staticmethod
    def _map_error(error: Exception) -> SmartFriendsError:
        if isinstance(error, SmartFriendsError):
            return error
        if isinstance(error, asyncio.CancelledError):
            return SmartFriendsCancelled("Operation cancelled")
        if isinstance(error, TimeoutError):
            return SmartFriendsTimeout("The box did not answer in time")
        if isinstance(error, ssl.SSLCertVerificationError):
            return SmartFriendsConnectionError("TLS certificate verification failed")
        if isinstance(error, ssl.SSLError):
            return SmartFriendsConnectionError("TLS connection failed")
        if isinstance(error, (ConnectionError, OSError)):
            return SmartFriendsConnectionError("Connection to the box failed")
        return SmartFriendsConnectionError(str(error) or "Connection failed")


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None
