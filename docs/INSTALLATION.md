# Installation

RolloFriends is a Home Assistant custom integration for the SmartFriends Box.
The target version is **0.2.0-beta.1**. It is currently a **local beta
candidate**, not a published Marketplace/HACS integration.

## Requirements

- Home Assistant Core **2026.11.0** or newer for the tested target.
- Network access from Home Assistant to the SmartFriends Box on TCP port
  **4300**.
- A SmartFriends user account. Use a dedicated account where possible.
- The box must expose at least one master device with a `rollingShutter`
  component.
- No Python package installation is required: the `aiosmartfriends` client is
  bundled under `custom_components/smartfriends_box/vendor`.

## Manual local installation

1. Copy the integration directory:

   ```bash
   cp -R custom_components/smartfriends_box \
     /config/custom_components/smartfriends_box
   ```

2. Validate the Home Assistant configuration if your installation provides the
   CLI:

   ```bash
   ha core check
   ```

3. Restart Home Assistant.

4. Open **Settings → Devices & services → Add integration → RolloFriends**.

5. Either confirm the mDNS-discovered box or enter host/IP, port `4300`, the
   SmartFriends username, and its password.

Setup performs a login and one full snapshot. It does **not** move a shutter.

## Updating a local installation

Copy the updated integration directory over the existing one and restart Home
Assistant. Keep the existing config entry. Do not copy a local `.env`, test
output, or credentials into `/config`.

After a library change, regenerate the vendored copy and run the packaging
test:

```bash
python3 scripts/sync_vendor.py
.venv/bin/python -m pytest tests/test_packaging.py -q
```

## Public Marketplace / HACS distribution

This distinction matters:

| Mode | Status | Requirements |
|---|---|---|
| Local `custom_components` test | Available now | Copy the directory and restart |
| Public Home Assistant Marketplace/HACS | Not available yet | Public GitHub repository, release/tag, published documentation and issue tracker, publication approval |

Home Assistant 2026.11 includes HACS as the built-in **Marketplace**. HACS and
the Marketplace only manage public GitHub repositories. The current
`manifest.json` documentation and issue-tracker URLs point to
`https://github.com/devwbb/RolloFriends`, but that repository does not exist yet.
Do not announce or install this as a public integration until the repository,
release, and approval exist.

HACS expects one integration below `custom_components/<domain>/`, a root
`hacs.json`, a `brand/icon.png`, and a valid manifest. Those files are present;
the remaining blockers are the public repository, release, and documentation
URLs.

## Credentials and privacy

- Credentials are entered in the Home Assistant UI and stored in the config
  entry. They are not part of this repository.
- Diagnostics redact username and password. They contain device metadata,
  positions, connection state, and a bounded recent-event trace; review before
  sharing.
- Set up a dedicated SmartFriends account and restrict access to Home Assistant
  and the box network.
- Never put a real `.env` file, token, or password in Git, issue reports, logs,
  or documentation.

## Troubleshooting

| Symptom | Check |
|---|---|
| `invalid_auth` | Dedicated SmartFriends account, password, and box user permissions |
| `certificate_error` | Box certificate/TLS path; the pinned Enexoma root must validate |
| `cannot_connect` | HA-to-box route, TCP 4300, firewall/VPN |
| No discovery | Enter host and port manually; mDNS may be blocked across VLANs |
| Entity `unknown` or `stale` | No fresh measured position; the integration intentionally does not estimate |
| Entity `pending` | A command is awaiting confirmation; check box/RF and diagnostics |
| Entity `unavailable` | Connection or snapshot freshness is lost |

Do not send repeated commands to force a confirmation. The integration never
automatically retries an unconfirmed command.

RSSI can temporarily show 0 and position feedback can be delayed. These are
known SmartFriends Box/radio properties. RSSI 0 by itself does not make the
connection or a shutter unavailable; connection freshness, radio quality and
position validity are separate.
