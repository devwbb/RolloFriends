# Changelog

All notable changes to RolloFriends are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [0.2.0-beta.1] - 2026-11-07

### Added

- Phase-4 live-validation harness for pending/confirmed states and stop
  behaviour on a limited set of approved shutters.
- Beta documentation: local installation, development workflow, distribution
  boundaries, and security/credential handling.
- Phase-5 analysis of an unrelated shutter movement, stop semantics, and session-expiry handling.
- Separate `motor_status`, `position_fresh`, and `stop_status` state signals.
- A 10-second quiet window after motor stop before a stop becomes final; later
  measured positions reset the window.
- Regression coverage for stale STOPPED feedback, delayed stop positions, and
  parallel-client session expiry without command replay.
- Phase-6 installation and live validation on the HA test VM: approved stop trips observed `awaiting_motor_stop -> settling -> confirmed`, with
  10-second settling windows; late same-value updates no longer supersede a
  confirmed stop.

### Known limitations

- Only a limited subset of test shutters has been exercised with movement commands.
- RSSI values may alternate between 0 and 3 and position feedback may be
  delayed; these are known box/radio properties, not proof that a connection or
  shutter is unavailable.
- A later box measurement can arrive after a stop was confirmed; the
  integration marks a changed endpoint as `superseded`.
- The public GitHub repository exists, but the release tag and Marketplace/HACS
  entry are still pending.

## [0.1.0] - 2026-11-07

### Added

- Async `aiosmartfriends` client with pinned TLS, digest authentication,
  newline-delimited JSON framing, one-request-at-a-time gating, full snapshots,
  deltas, push events, polling, and reconnect handling.
- Native Home Assistant custom integration `smartfriends_box` with config flow,
  discovery, reauth, reconfigure, cover entities, device registry, diagnostics,
  and English/German translations.
- Position mapping between the box convention (`0 = open`, `100 = closed`) and
  Home Assistant, including measured versus adjustable position semantics.
- Target and stop commands with no automatic retry after an unconfirmed command.
- State handling for `pending`, `moving`, `confirmed`, `stale`, `unknown`, and
  `unavailable`, including a read-only snapshot refresh when target confirmation
  is delayed and a sparse warning after 30 seconds.
- Automated library, packaging, Home Assistant mapping, diagnostics, and
  state-handling tests.
- Documentation of live tests, position diagnostics, target/stop behaviour, and
  implementation limits.

### Known limitations

- Only a limited subset of approved test shutters has been exercised with movement commands.
- Radio feedback can be delayed substantially, on some devices; the
  integration does not invent positions or retry commands.
- At the 0.1.0 local snapshot, public distribution had not been prepared. The
  0.2.0-beta.1 public repository supersedes this limitation.

[0.2.0-beta.1]: https://github.com/devwbb/RolloFriends/compare/v0.1.0...v0.2.0-beta.1
[0.1.0]: https://github.com/devwbb/RolloFriends/releases/tag/v0.1.0
