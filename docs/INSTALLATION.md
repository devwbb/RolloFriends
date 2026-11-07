# Installation

RolloFriends is a Home Assistant custom integration for the SmartFriends Box.
The current beta is **0.2.0-beta.1**. Home Assistant 2026.11 includes the
**Marketplace**; a separate HACS installation is not required. The repository
remains compatible with `hacs.json` and the HACS action.

## Requirements

- Home Assistant Core **2026.11.0** or newer for the tested target.
- Network access from Home Assistant to the SmartFriends Box on TCP port
  **4300**.
- A SmartFriends user account. Use a dedicated account where possible.
- The box must expose at least one master device with a `rollingShutter`
  component.
- No Python package installation is required: the `aiosmartfriends` client is
  bundled under `custom_components/smartfriends_box/vendor`.

## Installation via Home Assistant Marketplace

1. Open **Settings → Marketplace**.
2. Open the **Add from link** tab.
3. Enter `https://github.com/devwbb/RolloFriends`.
4. Select **Integration** as the type and select **Add**.
5. If prompted, connect GitHub. The Marketplace requires this connection to add
   a custom repository.
6. Open the RolloFriends repository page and select **Include pre-releases** from
   the overflow menu.
7. Install **0.2.0-beta.1**. If necessary, use **Install another version** and
   select the beta explicitly.
8. Restart Home Assistant when prompted.
9. Open **Settings → Devices & services → Add integration** and select
   **RolloFriends**. The setup dialog is titled “Connect SmartFriends Box”.
10. Enter host/IP, port `4300`, SmartFriends username, and password.

Direct Marketplace link:

<https://my.home-assistant.io/redirect/marketplace_repository/?owner=devwbb&repository=RolloFriends&category=integration>

Setup performs a login and one full snapshot without moving a shutter. Updates
installed through the Marketplace keep the existing config entry; restart Home
Assistant after an update.

### Beta limitations

- The integration exposes the SmartFriends Box cover entities found in the
  reference environment.
- Real movement commands have been exercised on a limited subset of cover
  entities only.
- RSSI 0/3 is not a standalone availability indicator. Connection freshness,
  radio quality, and position validity are separate.
- Position feedback can be delayed; a later measurement can arrive after a stop
  was confirmed.
- Unconfirmed device commands are never retried automatically.
- Adjustable position devices are exposed as assumed-state.

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

## Marketplace distribution

This distinction matters:

| Mode | Status | Requirements |
|---|---|---|
| Local `custom_components` test | Available now | Copy the directory and restart |
| Home Assistant Marketplace | GitHub pre-release published | Marketplace GitHub connection for custom repository; custom-repository install pending validation |

Home Assistant 2026.11 includes the **Marketplace** directly. The GitHub
pre-release `v0.2.0-beta.1` is published. Adding the repository as a custom
repository requires a GitHub connection in the Marketplace; without it the
Marketplace cannot add custom repositories. The public repository contains one
integration below `custom_components/<domain>/`, a root `hacs.json`, a
`brand/icon.png`, and a valid manifest, and the HACS action passes.

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
