# Validation summary

RolloFriends was validated against a SmartFriends Box and Home Assistant
2026.11.0 in a local test environment. Internal device labels, room names, and
component identifiers are intentionally omitted from this public summary.

## Automated checks

- `tests/`: 59 passed.
- `tests_ha/`: 39 passed.
- Ruff: clean for project sources.
- Mypy strict for the standalone library: clean.
- Home Assistant `ha core check`: successful.
- Manifest, HACS metadata, translations, brand asset, and vendored-library sync
  tests pass.

## Live validation, generic summary

- Read-only login and full snapshot completed.
- The integration loaded the expected cover entities after multiple controlled Home Assistant restarts.
- A limited set of approved test shutters was used for movement tests. Other shutters were
  not commanded.
- Target positions, stop commands, `valueTarget` handling, delayed positions,
  and stale/unknown states were observed.
- Stop settling was observed as `awaiting_motor_stop → settling → confirmed`.
  The measured settling windows were approximately 10 seconds, and no
  confirmation occurred before the quiet window.
- A later box update arriving after confirmation was handled explicitly as
  `superseded` when it represented a changed state. A repeat of the same raw
  position does not invalidate a confirmed stop.
- One session-expiry/reconnect occurred without a command replay.
- The integration remained `connected` and `fresh` after the final restart.
- The latest single-device stop validation used exactly one close command and
  one stop command. It observed `awaiting_motor_stop → settling → confirmed`;
  the settling duration was 10.09 seconds and confirmation occurred after
  13.95 seconds. No later position was reported during a 130-second observation
  window, so the same-value late-update path remains covered by unit tests
  rather than this live run.

## Known device and protocol behaviour

RSSI values can alternate between 0 and 3, and position reports can be delayed.
These are treated as known SmartFriends Box/radio properties, not as evidence
that the integration or the shutter is unavailable. The integration evaluates:

- connection freshness separately from RSSI;
- radio quality separately from availability;
- position validity and stop finality separately from radio quality.

RSSI 0 alone does not mark the integration connection or a shutter unavailable.
Repeated long-running RF diagnostics are not part of the release tests.

## Known limitations

- Only a limited subset of shutters has been exercised with movement commands. Other devices
  may expose different timing or position semantics.
- Radio feedback can be delayed substantially; a later measurement may arrive
  after a stop was confirmed.
- Adjustable position components are reported as assumed-state.
- The integration is local-only and does not implement pairing, scenes, groups,
  firmware updates, or account management.
- The public distribution repository, release, and Marketplace/HACS approval do
  not exist yet.

## Evidence

Detailed device-specific development reports are retained outside the public
release tree. They must not be included in a public repository or release
archive unless separately sanitized and approved.
