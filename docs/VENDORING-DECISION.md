# Vendoring versus PyPI decision

## Current state

`aiosmartfriends` is vendored byte-for-byte under
`custom_components/smartfriends_box/vendor/aiosmartfriends`. The integration
manifest has no Python requirements, and `scripts/sync_vendor.py` plus a
packaging test enforce synchronization with `src/aiosmartfriends`.

## Option A: keep vendoring

Advantages:

- installation works without a PyPI release or network package resolution;
- exact dependency version travels with the integration;
- no dependency-version drift between the library and the integration;
- HACS/Marketplace installations can be self-contained.

Costs:

- duplicated source tree and review surface;
- two version numbers/commit points must stay synchronized;
- dependency vulnerability and update scanning must cover both copies;
- a public consumer cannot easily use the library independently.

## Option B: publish `aiosmartfriends` on PyPI

Advantages:

- standard Home Assistant custom-integration dependency model;
- manifest can pin `aiosmartfriends==<version>`;
- one canonical source package, smaller repository and integration;
- independent library users can depend on it.

Costs:

- requires PyPI project ownership, release automation, and a trusted publishing
  process;
- installation depends on PyPI availability and resolver behavior;
- the integration and library releases must be coordinated;
- HACS/Marketplace users can encounter package-install failures.

## Option C: hybrid

Publish the library to PyPI but keep a vendor fallback for local builds. This
maximizes flexibility but also keeps two sources of truth and should only be
chosen with explicit synchronization and release automation.

## Recommendation

For the first public beta, keep vendoring until the repository, release process,
and HACS validation are stable. If independent library consumption or standard
HA dependency management becomes a requirement, publish `aiosmartfriends` to
PyPI and switch the manifest to an exact pin, while retaining the sync test
during a transition period.

Do not publish to PyPI as part of the local beta preparation. Publication
requires its own explicit approval, ownership check, and release checklist.

## Decision record

- Chosen option: `TODO`
- Decision owner: `TODO`
- Date: `TODO`
- Rationale: `TODO`
- Follow-up: update `manifest.json`, `pyproject.toml`, `scripts/sync_vendor.py`,
  packaging tests, README, and release notes accordingly.
