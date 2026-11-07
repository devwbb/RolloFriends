"""Newline-delimited JSON framing for the SmartFriends Box."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .exceptions import SmartFriendsProtocolError

DEFAULT_MAX_FRAME_SIZE = 16 * 1024 * 1024


class LineFramer:
    """Incrementally split a byte stream into non-empty JSON lines.

    The box terminates every message with ``\n``. CRLF, tabs and surrounding
    spaces are tolerated. A frame larger than ``max_frame_size`` is rejected
    instead of being buffered without bound.
    """

    def __init__(self, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> None:
        if max_frame_size < 1:
            raise ValueError("max_frame_size must be positive")
        self.max_frame_size = max_frame_size
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        if not data:
            return []
        self._buffer.extend(data)
        frames: list[bytes] = []

        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            frame = raw.strip(b"\r\t ")
            if not frame:
                continue
            if len(frame) > self.max_frame_size:
                self.reset()
                raise SmartFriendsProtocolError("A message from the box was too large")
            frames.append(frame)

        if len(self._buffer) > self.max_frame_size:
            self.reset()
            raise SmartFriendsProtocolError("A message from the box was too large")
        return frames

    def reset(self) -> None:
        self._buffer.clear()

    @property
    def buffered(self) -> int:
        return len(self._buffer)


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Encode one compact UTF-8 JSON message including its newline."""

    try:
        encoded = json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as err:
        raise SmartFriendsProtocolError("The command could not be encoded") from err
    return encoded + b"\n"
