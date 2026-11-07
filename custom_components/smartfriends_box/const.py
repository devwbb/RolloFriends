"""Constants for the RolloFriends integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "smartfriends_box"
NAME: Final = "RolloFriends"
MANUFACTURER: Final = "SmartFriends"

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"

DEFAULT_PORT: Final = 4300
DEFAULT_C_SYMBOL: Final = "D19033i"
DEFAULT_SHC_VERSION: Final = "3.6.2"
DEFAULT_SH_API_VERSION: Final = "3.3"

POLL_INTERVAL: Final = timedelta(seconds=5)
DATA_FRESHNESS: Final = 30.0
MOVEMENT_TIMEOUT: Final = 30.0
POSITION_CONFIRM_TIMEOUT: Final = 30.0
STOP_SETTLE_TIME: Final = 10.0
PENDING_WARNING_AFTER: Final = 30.0
READ_ONLY_REFRESH_DELAYS: Final = (20.0, 90.0)
READ_ONLY_REFRESH_COOLDOWN: Final = 10.0

PLATFORMS: Final = ["cover"]

ZEROCONF_TYPE: Final = "_smarthome._tcp.local."
