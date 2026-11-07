# RolloFriends

RolloFriends is a native Home Assistant custom integration for the SmartFriends
Box 2.0. It speaks the box protocol directly over pinned TLS and exposes the
supported shutters as Home Assistant cover entities.

Current beta version: **0.2.0-beta.1**.

Target public repository: <https://github.com/devwbb/RolloFriends> (repository
not created or published yet).

The integration bundles a byte-identical copy of the standalone
`aiosmartfriends` library. The canonical library source lives under
`src/aiosmartfriends`; `scripts/sync_vendor.py` refreshes the bundled copy.

## Status and beta readiness

| Area | Status |
|---|---|
| Local Home Assistant test installation | Working on Home Assistant 2026.11.0 |
| Library and integration tests | 98 automated tests passing |
| Read-only box verification | Login and full snapshot; exact component and shutter counts are not published |
| Approved movement tests | A limited subset of shutters in the local test environment |
| Public Marketplace/HACS distribution | **Not published and not approved** |
| Overall beta readiness | Local beta candidate; public release preparation in progress |

The project is not affiliated with SmartFriends, Schellenberg, Enexoma, or Home
Assistant. It is an independent protocol implementation.

## Safety and scope

- TLS is pinned to the Enexoma root certificate in
  `src/aiosmartfriends/certs/enexoma-root2.pem`. Hostname matching is disabled
  because the box certificate uses `CN=homeserver`; chain, signature and
  validity are still checked against that single pinned root.
- No command is automatically retried after an unconfirmed acknowledgement.
- No local position interpolation or invented travel times.
- No pairing, user management, scenes, groups, or firmware updates in 0.2.
- Credentials are stored only in the Home Assistant config entry and are
  redacted from diagnostics. No credentials belong in this repository.
- The connection is local; VPN/WireGuard is supported by the network stack.
- A command acknowledgement is not proof of movement. A target is confirmed
  only by a fresh measured position.

## Supported devices

The integration imports every master device with a `rollingShutter` component.
The reference box exposes multiple such devices, including Rollodrive and radio receiver switches. A position component is optional; devices without one expose open,
close and stop only.

SmartFriends reports positions as **0 = open, 100 = closed**. Home Assistant uses
the inverse convention. The conversion is performed exactly once at the entity
boundary:

| Box value | Home Assistant position |
|---:|---:|
| 0 | 100 (open) |
| 35 | 65 |
| 100 | 0 (closed) |

Measured positions (`SchellenbergPosition`) and adjustable positions
(`SchellenbergPosition_Adjustable`) are distinguished internally. Adjustable
devices are marked as assumed-state because their box value is not proof of a
physical endpoint. `valueTarget` is treated only as a goal.

## Installation

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for local installation,
updates, troubleshooting, and credentials handling.

Home Assistant 2026.11 includes HACS as the built-in **Marketplace**. HACS and
the Marketplace only manage public GitHub repositories. The planned repository
is `devwbb/RolloFriends`; it is not created or published yet. Do not add it as a
public integration until the repository, release, documentation URL, and
explicit approval exist.

The box advertises its service as `_smartHOME._tcp.local.` with an uppercase
`HOME`; the manifest lists both that spelling and the lower-case form.

## Configuration

Only four fields are required:

- host / IP address
- port (default 4300)
- username
- password

The verified protocol constants (`D19033i`, `3.6.2`, `3.3`) are internal
defaults. A reauthentication flow handles a rejected password; a reconfigure
flow changes host, port, or username. Setup performs a login and one full
snapshot without moving a shutter.

## State updates

- The client owns exactly one TCP/TLS connection, one request gate, one poll
  task, and one reconnect loop.
- `getAllNewInfos` polls every 5 seconds. After a command the interval drops to
  1.5 seconds for about 30 seconds.
- Push events (`newDeviceValue`, `newDeviceInfo`, `newRoomInfo`) are applied
  immediately.
- Full snapshots rebuild state; deltas merge by timestamp. Older values never
  overwrite newer ones.
- Entities become unavailable when the last successful snapshot is older than
  30 seconds.
- `position_status` distinguishes `unavailable`, `unknown`, `stale`, `moving`,
  `pending`, `settling` and `confirmed`. `position_pending` and, while a target
  is outstanding, `command_target` are exposed as attributes.
- `motor_status`, `position_fresh` and `stop_status` separately describe motor
  state, measurement freshness, and stop finality. A stop enters `settling` for
  a 10-second quiet window before `confirmed`; a later measured position resets
  that window or, after confirmation, marks the stop `superseded`. A fresh
  measurement is not treated as proof of an immutable final position.
- A command target comes from `valueTarget` only as a goal. It is never used as
  the measured `current_position`, and no intermediate positions are invented.
- If confirmation is still missing, the entity waits for a fresh measured
  position, requests a read-only full snapshot after 20 s and 90 s, and logs one
  warning after 30 s. No device command is resent.
- Reconnect uses 2/4/8/16/30-second backoff and always starts with a full
  snapshot.

Opening/closing flags are set only after a fresh motor transition or position
change. A position is reported as unknown when the box position is missing,
stale, or unconfirmed beyond the allowed confirmation window.

## Tests and live validation

```bash
.venv/bin/python -m pytest tests -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest tests_ha -q -p pytest_asyncio.plugin
.venv/bin/ruff check .
.venv/bin/mypy
```

Current results: **59 library/packaging tests**, **39 Home Assistant
mapping/state tests**, Ruff clean, and strict mypy clean for the library.

Live validation covered the tested protocol paths, target/stop behavior,
pending/stale states, delayed position feedback, session expiry, and restart
behavior. Internal device labels and detailed test artifacts are intentionally
not part of the public tree. See:

- [`docs/VALIDATION.md`](docs/VALIDATION.md) — generic validation summary and
  known limitations.
- [`docs/BETA-CHECKLIST.md`](docs/BETA-CHECKLIST.md) — release gates.
- [`docs/GITHUB-RELEASE-CHECKLIST.md`](docs/GITHUB-RELEASE-CHECKLIST.md) —
  public release steps.
- [`docs/VENDORING-DECISION.md`](docs/VENDORING-DECISION.md) — library
  distribution decision.
- [`docs/RELEASE-METADATA.md`](docs/RELEASE-METADATA.md) — placeholder URLs and
  release metadata, not final until the repository exists.

## Known limitations

- Only a limited subset of shutters has been exercised with movement commands. Other devices
  may have different timing or position semantics.
- RSSI may alternate between 0 and 3, and position feedback can be delayed.
  These are known device/radio properties. RSSI 0 alone does not mean the box
  connection or a shutter is unavailable; connection freshness, radio quality,
  and position validity are separate signals.
- A later box measurement can arrive after a stop was confirmed. The
  integration marks a changed endpoint as `superseded`; it does not claim an
  immutable final position.
- Adjustable position components are exposed as assumed-state.
- Public Marketplace/HACS distribution has not yet been created or approved.

## Development

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the repository layout,
development environment, architecture, test commands, live-test safety rules,
and the future public-release checklist.

## License

MIT. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
