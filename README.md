# RolloFriends

RolloFriends is a native Home Assistant custom integration for the SmartFriends
Box 2.0. It speaks the box protocol directly over pinned TLS and exposes the
supported shutters as Home Assistant cover entities.

Current beta version: **0.2.0-beta.1**.

Public repository: <https://github.com/devwbb/RolloFriends>
Public pre-release: <https://github.com/devwbb/RolloFriends/releases/tag/v0.2.0-beta.1>

The integration bundles a byte-identical copy of the standalone
`aiosmartfriends` library. The canonical library source lives under
`src/aiosmartfriends`; `scripts/sync_vendor.py` refreshes the bundled copy.

## Installation via Home Assistant Marketplace

Home Assistant **2026.11** includes the **Marketplace** directly. HACS is no
longer a separate installation step, although the repository continues to ship
`hacs.json` and is checked by the HACS action.

1. Open **Settings → Marketplace**.
2. Open the **Add from link** tab.
3. Enter `https://github.com/devwbb/RolloFriends`.
4. Select **Integration** as the type and select **Add**.
5. If the Marketplace asks for a GitHub connection, connect GitHub and then
   continue. Custom repositories cannot be added without it.
6. Open the RolloFriends repository page and use the overflow menu to select
   **Include pre-releases**.
7. Install version **0.2.0-beta.1**. If it is not preselected, choose
   **Install another version** and select `0.2.0-beta.1`.
8. Restart Home Assistant when the Marketplace asks for it.
9. Open **Settings → Devices & services → Add integration** and select
   **RolloFriends** (the setup dialog is titled “Connect SmartFriends Box”).
10. Enter the SmartFriends Box address, port `4300`, username, and password.

Direct Marketplace link:

<https://my.home-assistant.io/redirect/marketplace_repository/?owner=devwbb&repository=RolloFriends&category=integration>

The box must be reachable from Home Assistant on TCP port `4300`. Setup only
logs in and reads one full snapshot; it does not move a shutter. Existing config
entries are preserved when the integration is updated after a restart.

More details, manual installation, updates, and troubleshooting:
[`docs/INSTALLATION.md`](docs/INSTALLATION.md).


## Status and beta readiness

| Area | Status |
|---|---|
| Local Home Assistant test installation | Working on Home Assistant 2026.11.0 |
| Library and integration tests | 98 automated tests passing |
| Read-only box verification | Login and full snapshot; exact component and shutter counts are not published |
| Approved movement tests | A limited subset of shutters in the local test environment |
| Public distribution | GitHub pre-release `v0.2.0-beta.1`; Marketplace custom-repository install path |
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
The reference box exposes multiple such devices, including Rollodrive and radio
receiver switches. A position component is optional; devices without one expose
open, close and stop only.

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

The primary installation method is the integrated Home Assistant Marketplace
described above. Manual installation remains available for development and
offline testing:

1. Copy `custom_components/smartfriends_box` into
   `/config/custom_components/smartfriends_box`.
2. Run `ha core check`.
3. Restart Home Assistant.
4. Add **RolloFriends** under **Settings → Devices & services**.

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

- Only a limited subset of shutters has been exercised with movement commands.
  Other devices may have different timing or position semantics.
- RSSI may alternate between 0 and 3, and position feedback can be delayed.
  These are known device/radio properties. RSSI 0 alone does not mean the box
  connection or a shutter is unavailable; connection freshness, radio quality,
  and position validity are separate signals.
- A later box measurement can arrive after a stop was confirmed. The
  integration marks a changed endpoint as `superseded`; it does not claim an
  immutable final position.
- Adjustable position components are exposed as assumed-state.
- The GitHub pre-release exists. The Marketplace custom-repository installation path still requires a Marketplace GitHub connection and was not exercised on the test VM.

## Development

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the repository layout,
development environment, architecture, test commands, live-test safety rules,
and the public-release checklist.

## Credits and protocol references

RolloFriends is an independent implementation. It was informed by the following
third-party protocol work; the full statements and license details are in
[`NOTICE.md`](NOTICE.md):

- [`LoPablo/smartFriendsApi`](https://github.com/LoPablo/smartFriendsApi)
  (ISC, Copyright 2020 Pascâl Hartmann) — protocol reference for the box port,
  TLS trust anchor, digest authentication, `helo`/`login`/`getAllNewInfos`/
  `setDeviceValue`, and newline framing.
- [`GimpArm/smartfriends-bridge`](https://github.com/GimpArm/smartfriends-bridge)
  (GPL-3.0) — behavioral reference for the observed message structure,
  master/component grouping, command values, and the position inversion used by
  its MQTT template. No code was copied or translated.

A self-contained copy of the notice ships with the integration in
[`custom_components/smartfriends_box/NOTICE.md`](custom_components/smartfriends_box/NOTICE.md)
for manual installations that copy only the component directory.

## License

MIT. See [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
