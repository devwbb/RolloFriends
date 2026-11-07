# Development

## Repository layout

```
src/aiosmartfriends/                 standalone async protocol client
custom_components/smartfriends_box/ native Home Assistant integration
  vendor/aiosmartfriends/           byte-identical runtime copy
tests/                              library, protocol and packaging tests
tests_ha/                           Home Assistant mapping/state tests
scripts/                            read-only probe and vendor sync
docs/                               test and operator documentation
```

`src/aiosmartfriends` is the canonical library. The integration vendors it so a
local test installation does not need a PyPI package. After changing the
library, run:

```bash
python3 scripts/sync_vendor.py
.venv/bin/python -m pytest tests/test_packaging.py -q
```

The packaging test fails if the vendored copy differs.

## Environment

Requires Python 3.13+ and Home Assistant 2026.11.0 for the HA tests.

```bash
uv venv --python 3.13 .venv
uv pip install -e '.[test]'
uv pip install -r requirements_ha_test.txt
```

The upstream `pytest-homeassistant-custom-component` release pins Home Assistant
2026.10.4, so this project does not use it for the 2026.11 target. The HA tests
import the installed 2026.11 packages directly and run with plugin autoload
disabled.

## Checks

```bash
.venv/bin/python -m pytest tests -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/python -m pytest tests_ha -q -p pytest_asyncio.plugin
.venv/bin/ruff check .
.venv/bin/mypy
```

`mypy` is configured in strict mode for the standalone library. Home Assistant
types are exercised through the HA tests; the integration is not part of the
strict mypy package set because third-party HA stubs are not installed here.

## Architecture notes

- The client owns one TCP/TLS connection, one request gate, one poll task, and
  one reconnect loop.
- Requests are newline-delimited JSON and ambiguous without request IDs. Only
  one request may be in flight; responses are matched by shape.
- TLS is pinned to the Enexoma root and hostname matching is intentionally
  disabled because the box leaf uses `CN=homeserver`.
- The integration coordinator is a passive cache fed by client events. It does
  not open a second connection or poll.
- Cover entities map box raw positions to Home Assistant positions exactly once.
  `valueTarget` is a goal, never a measured position.
- `position_status` is an attribute, not a Cover state. Home Assistant still
  receives only the standard Cover states. `motor_status`, `position_fresh`,
  and `stop_status` keep motor state, measurement freshness, and stop finality
  separate. A stop stays `settling` for a 10-second quiet window before
  `confirmed`; later measured positions restart that window.
- A delayed target confirmation triggers read-only full snapshots at 20 s and
  90 s, rate-limited to one refresh per 10 s. No command retry is performed.
- Session expiry fails the pending request and reconnects; it never replays a
  `setDeviceValue`. The parallel-client regression test asserts exactly one
  transmitted command.
- Diagnostics redact credentials and intentionally expose only bounded,
  operational data.

## Live testing safety

Live tests are not part of the default suite. They require a local `.env` and
must be run deliberately. The public tree contains only the read-only probe:

```bash
.venv/bin/python scripts/live_read_only.py
```

Device-specific movement harnesses and detailed evidence are kept outside the
public tree in the local-only `internal/` directory (ignored by Git). They must
not be published unless separately sanitized and approved.

Only explicitly approved devices may move. Never put credentials in the
repository, command line, or test output. Stop on unexpected movement or
confirmed missing feedback, and never retry an unconfirmed command.

## Adding support for another protocol shape

1. Add or adjust parsing in `src/aiosmartfriends` with a captured, synthetic
   fixture in `tests/`.
2. Preserve master/component IDs and the 0 = open, 100 = closed convention at
   the model boundary.
3. Add a regression test for command target and component selection.
4. Sync the vendor copy and run all checks.
5. Do not perform movement tests on additional devices without explicit
   approval.

## Release preparation

The detailed GitHub release sequence is in
[`GITHUB-RELEASE-CHECKLIST.md`](GITHUB-RELEASE-CHECKLIST.md). The library
distribution choice is documented in
[`VENDORING-DECISION.md`](VENDORING-DECISION.md).

Target version: `0.2.0-beta.1` (Python package `0.2.0b1`).

The public beta branch is an independent root history. Do not merge the
internal main branch into it. The release metadata URL placeholders must be
replaced with the actual repository values before publication.

Do not create a remote, tag, release, or Marketplace entry without explicit
approval.
