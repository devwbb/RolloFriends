# Beta release checklist

Stand: 07.11.2026. This file distinguishes the current local test mode from a
future public Marketplace/HACS release.

## Current decision

Public beta version target: **0.2.0-beta.1**.
GitHub repository: **`devwbb/RolloFriends`** (public `main`; no release/tag yet).

- **Local beta:** approved for controlled testing on the current HA test VM.
- **Technical recommendation:** conditional **Go** for a limited public beta,
  after the public-distribution gates below are completed.
- **Unrestricted production release:** no.
- **Public beta publication approval:** not yet given.
- **Remote repository:** exists (public `main`).
- **Release tag / Marketplace entry:** none.

## Functional and safety gates

- [x] Home Assistant 2026.11.0 loads the integration and the expected cover
      entities.
- [x] Login and full snapshot verified.
- [x] TLS pinning, digest authentication and mDNS identity probe tested.
- [x] Config flow and reconfigure form exercised live; reauth paths covered by
      automated tests.
- [x] Diagnostics redact username/password and contain no token or password.
- [x] No automatic command retry on timeout or session expiry.
- [x] Parallel-client session expiry regression test: one transmitted command,
      no replay after reconnect.
- [x] Stop settling separates motor state, fresh measurement and final
      `confirmed`; regression tests pass.
- [x] Deploy the Phase-5 stop correction to the HA test VM and verify the
      settling sequence with an approved live stop test.
- [ ] Re-test the refined same-value late-position path live; the command budget
      was exhausted after the initial trips per device.
- [x] Verify the cover entities and a connected/fresh integration after HA
      restarts.
- [x] Verify version `0.2.0-beta.1` loads in the manifest; Python package is
      `0.2.0b1`.
- [x] Verify RSSI 0 does not make the connection or a shutter unavailable.
- [x] Remove internal device labels, IDs, private addresses and live evidence
      from the public tree; keep them in the ignored local `internal/` folder.
- [ ] Re-run the pending → confirmed validation on the approved test shutters after the stop correction.
- [ ] Clarify the external controller causing the unrelated shutter movements.
- [ ] Movement-test at least a representative subset of the remaining
      shutters before claiming general device support.
- [ ] Decide whether to publish `aiosmartfriends` to PyPI or keep the vendored
      copy for the public package.

## Automated quality gates

- [x] `pytest tests` — 59 passed.
- [x] `pytest tests_ha` — 39 passed.
- [x] Ruff.
- [x] Mypy strict for the library.
- [x] Manifest/HACS metadata, translations and brand icon tests.
- [x] Git working tree clean and no credentials or local artifacts staged.
- [ ] Keep the public `public-beta` branch as an independent root history; do
      not merge the internal main branch.
- [x] Run the public HACS/hassfest validation against the GitHub repository.

## Public distribution gates

- [x] Create the public GitHub repository `devwbb/RolloFriends`.
- [ ] Verify `codeowners`, documentation URL and issue-tracker URL.
- [ ] Create a release/tag and update `manifest.json`/`CHANGELOG.md`.
- [x] Validate the repository with HACS/Marketplace action and hassfest.
- [ ] Review the README/installation instructions against the actual release.
- [ ] Verify no `.env`, tokens, private hostnames, or test artifacts are in the
      release tag.
- [ ] Explicit publication approval from the owner.
- [ ] Announce only after the public repository and release are live.

## Known residual risks

- A test shutter can remain `pending`/`unknown` for several minutes; the box may not emit a measured position until a later command.
- One test shutter can report target positions one percentage point high.
- A fresh measured position is not a guarantee that the box will not report a
  later position; the 10-second stop quiet window reduces, but cannot eliminate,
  this hardware behavior.
- External SmartFriends clients, physical switches, or box-side programs can
  move shutters independently of Home Assistant. The source of the unrelated shutter movement is still
  unknown.
- Parallel clients sharing one SmartFriends account may cause session churn;
  the no-retry behavior is tested, but real multi-client behavior is not fully
  characterized.
- Only a limited subset of shutters has been movement-tested.

## Approval rule

Do not create a remote repository, tag, release, Marketplace entry, or public
announcement without explicit approval. Local commits and local test reports are
allowed.
