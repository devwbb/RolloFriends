#!/usr/bin/env python3
"""Read-only live check: login, mDNS/identity probe and full snapshot.

Usage:
    .venv/bin/python scripts/live_read_only.py

Credentials are read from the untracked ``.env`` file. Nothing is printed
except box metadata, component counts and shutter names/IDs. No device
command is sent.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from aiosmartfriends import SmartFriendsClient, async_probe_identity


async def main() -> int:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        print("Missing local .env file", file=sys.stderr)
        return 1
    load_dotenv(env_path)
    host = os.environ.get("SMARTFRIENDS_HOST", "").strip()
    port = int(os.environ.get("SMARTFRIENDS_PORT", "4300"))
    username = os.environ.get("SMARTFRIENDS_USER", "").strip()
    password = os.environ.get("SMARTFRIENDS_PASSWORD", "")
    if not host or not username or not password:
        print("SMARTFRIENDS_HOST, SMARTFRIENDS_USER and SMARTFRIENDS_PASSWORD are required", file=sys.stderr)
        return 1

    identity = await async_probe_identity(host, port, timeout=5)
    print(f"identity: mac_present={bool(identity.mac_address)} configured={identity.is_configured}")

    client = SmartFriendsClient(
        host,
        port,
        username,
        password,
        auto_reconnect=False,
        poll_interval=60,
    )
    try:
        gateway = await client.async_connect()
        print(f"login: hardware={gateway.hardware} software={gateway.shs_version}")
        print(f"snapshot: components={client.repository.component_count} shutters={len(client.shutters)}")
        for shutter in client.shutters:
            print(
                f"  master={shutter.master_id} motor={shutter.motor_component_id} "
                f"position={shutter.position_component_id} room={shutter.room_name!r} "
                f"name={shutter.name!r} semantics={shutter.position_semantics.value} "
                f"raw={shutter.raw_position}"
            )
    finally:
        await client.async_disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
