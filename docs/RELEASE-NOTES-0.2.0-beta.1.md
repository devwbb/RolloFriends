# RolloFriends 0.2.0-beta.1

First limited public beta of the native SmartFriends Box 2.0 integration for
Home Assistant.

## Highlights

- Direct local protocol implementation with pinned TLS.
- Config flow, mDNS discovery, reauth, reconfigure, diagnostics, and German /
  English translations.
- Cover entities with exact box/Home Assistant position conversion.
- Target, open, close, and stop commands without automatic retries after an
  unconfirmed command.
- Separate motor, measurement-freshness, and stop-finality signals
  (`motor_status`, `position_fresh`, `stop_status`).
- A 10-second stop settling window before `confirmed`; later changed measurements
  are marked `superseded`.
- Read-only snapshot refresh when target confirmation is delayed.
- Session-expiry and parallel-client coverage without command replay.

## Known limitations

- The reference environment exposes multiple cover entities.
- Real movement commands have been exercised on a limited subset of cover entities only.
- RSSI 0/3 is not a standalone availability indicator. The integration evaluates
  connection freshness, radio quality, and position validity separately.
- Position feedback can be delayed; a later measurement may arrive after a stop
  was confirmed.
- The integration never automatically retries an unconfirmed device command.
- Adjustable position devices are exposed as assumed-state.
- Broader device validation is required before a stable release.

## Installation

Use the Home Assistant Marketplace/HACS path after the release is published, or
copy `custom_components/smartfriends_box` into the Home Assistant configuration.
Setup performs a login and one full snapshot without moving a shutter.

## Validation

- 59 library/packaging tests and 39 Home Assistant tests passing.
- Ruff and strict mypy checks passing.
- Hassfest validation passing on the public tree.
- HACS repository checks passing.
- Local Home Assistant restart and reconnect validation completed.

No GitHub release or tag has been published yet.
