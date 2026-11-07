"""Read-only discovery helpers for the SmartFriends Box."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .exceptions import (
    SmartFriendsIdentityError,
    SmartFriendsProtocolError,
    SmartFriendsServerError,
    SmartFriendsTimeout,
)
from .framing import LineFramer, encode_message
from .models import BoxIdentity
from .protocol import (
    ERROR,
    RESPONSE,
    SESSION_EXPIRED,
    WireMessage,
    command_get_server_info,
    get_case_insensitive,
    parse_wire_message,
)
from .transport import BoxTransport, create_pinned_ssl_context

_LOGGER = logging.getLogger(__name__)
_MAC_HEX = re.compile(r"^[0-9A-Fa-f]{12}$")

TransportFactory = Callable[..., Awaitable[BoxTransport]]


def normalize_mac(value: str | bytes | None) -> str | None:
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    hex_only = "".join(character for character in value if character in "0123456789abcdefABCDEF")
    if len(hex_only) != 12 or not _MAC_HEX.fullmatch(hex_only):
        return None
    return hex_only.upper()


@dataclass(frozen=True, slots=True)
class MdnsIdentity:
    mac_address: str | None
    domain: str | None
    name: str | None


def parse_mdns_identity(
    properties: Mapping[str, Any] | None,
    service_name: str | None = None,
) -> MdnsIdentity:
    """Extract the documented TXT fields from an mDNS service."""

    if not isinstance(properties, Mapping):
        properties = {}
    normalized: dict[str, Any] = {}
    for key, value in properties.items():
        if isinstance(key, str):
            normalized[key.casefold()] = value
    return MdnsIdentity(
        mac_address=normalize_mac(normalized.get("macaddress")),
        domain=_as_text(normalized.get("domain")),
        name=service_name,
    )


def _as_text(value: Any) -> str | None:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_identity(message: WireMessage) -> BoxIdentity:
    if message.response_code != RESPONSE:
        raise SmartFriendsIdentityError("The identity probe did not receive a response")
    response = message.response
    identity = BoxIdentity(
        mac_address=normalize_mac(get_case_insensitive(response, "macAddress")),
        is_configured=_as_bool(get_case_insensitive(response, "isConfigured")),
        owner_created=_as_bool(get_case_insensitive(response, "ownerCreated")),
        owner_setup=_as_bool(get_case_insensitive(response, "ownerSetup")),
        email_validated=_as_bool(get_case_insensitive(response, "emailValidated")),
    )
    if not identity.has_identity_data():
        raise SmartFriendsIdentityError("The identity probe returned no identity data")
    return identity


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


async def async_probe_identity(
    host: str,
    port: int,
    *,
    timeout: float = 3.0,
    transport_factory: TransportFactory | None = None,
    ssl_context: Any = None,
) -> BoxIdentity:
    """Send only ``getServerInfo`` over a pinned TLS connection.

    No credentials, session or device command are sent. This function is the
    only network identity check used by discovery.
    """

    factory = transport_factory or BoxTransport.open
    context = ssl_context if ssl_context is not None else create_pinned_ssl_context()
    transport: BoxTransport | None = None
    try:
        transport = await asyncio.wait_for(
            factory(host, port, ssl_context=context, timeout=timeout),
            timeout=timeout,
        )
        await asyncio.wait_for(
            transport.send(encode_message(command_get_server_info())),
            timeout=timeout,
        )
        framer = LineFramer()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise SmartFriendsTimeout("Identity probe timed out")
            data = await asyncio.wait_for(transport.read(65536), timeout=remaining)
            if not data:
                raise SmartFriendsIdentityError("The box closed the identity connection")
            for frame in framer.feed(data):
                message = parse_wire_message(frame)
                if message.response_code == RESPONSE:
                    return _parse_identity(message)
                if message.response_code in (ERROR, SESSION_EXPIRED):
                    raise SmartFriendsServerError(
                        "The box rejected the identity probe",
                        code=message.server_error_code,
                    )
                if message.response_code in (5, 20):
                    continue
                _LOGGER.debug(
                    "Ignoring response code %s during identity probe",
                    message.response_code,
                )
    except TimeoutError as err:
        raise SmartFriendsTimeout("Identity probe timed out") from err
    except SmartFriendsProtocolError:
        raise
    finally:
        if transport is not None:
            await transport.close()
