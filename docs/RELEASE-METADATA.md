# Public beta release metadata (prepared, not released)

The public repository is **`devwbb/RolloFriends`**. Its cleaned `main` branch is
published; no release tag or GitHub release has been created.

## Identity

| Field | Value |
|---|---|
| Project | RolloFriends |
| Integration domain | `smartfriends_box` |
| Manifest version | `0.2.0-beta.1` |
| Python package version | `0.2.0b1` |
| Release tag | `v0.2.0-beta.1` |
| GitHub repository | `devwbb/RolloFriends` |
| Codeowner | `@devwbb` |
| Documentation URL | `https://github.com/devwbb/RolloFriends` |
| Issue tracker URL | `https://github.com/devwbb/RolloFriends/issues` |
| Release type | pre-release |

The manifest and changelog point to the public repository. Tagging and
publishing the release require separate approval.

## Release title and summary

Suggested title:

> RolloFriends 0.2.0-beta.1

Suggested pre-release summary:

> First limited public beta of the native SmartFriends Box integration. Includes
> pinned TLS, config flows, discovery, cover entities, diagnostics, and separate
> motor/fresh-position/stop-finality state handling. Only a limited subset of
> test shutters has been exercised with movement commands; RSSI 0 and delayed
> position feedback are known box/radio properties.

## Release notes checklist

- [ ] Version and tag match.
- [ ] Installation is local custom-component and/or approved Marketplace/HACS
      path.
- [ ] Both test-shutter scope and known device limitations are stated.
- [ ] RSSI 0 and delayed positions are described as device/protocol properties,
      not general integration failure.
- [ ] No credentials, private addresses, internal evidence, or personal
      environment details are included.
- [ ] Link to `docs/VALIDATION.md` and `docs/BETA-CHECKLIST.md`.
- [ ] Use `docs/RELEASE-NOTES-0.2.0-beta.1.md` as the release body.
- [ ] Upgrade/rollback instructions are present.
- [ ] Pre-release flag is set.

## HACS and Marketplace metadata

- [ ] `hacs.json` remains at the repository root.
- [ ] `custom_components/smartfriends_box/manifest.json` has resolving
      documentation and issue-tracker URLs.
- [ ] `brand/icon.png` is present.
- [ ] The repository contains exactly one integration below
      `custom_components/`.
- [x] HACS/Marketplace action validation passes against the real repository.
- [ ] The release tag is visible to the Marketplace/HACS release selector.

The repository exists. Do not create the tag, release, or Marketplace entry
until the release checklist and explicit publication approval are complete.
