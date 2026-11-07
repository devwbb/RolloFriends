# GitHub release checklist

This checklist prepares a public beta release. It does not authorize creating
the remote repository or publishing anything.

## Release identity

- [x] Repository owner and codeowner confirmed as `devwbb`.
- [ ] Public repository `devwbb/RolloFriends` created.
- [ ] `manifest.json` documentation and issue-tracker URLs resolve.
- [ ] Repository target remains `https://github.com/devwbb/RolloFriends`.
- [ ] Version set consistently:
  - manifest: `0.2.0-beta.1`
  - Python package: `0.2.0b1`
  - changelog and release tag: `v0.2.0-beta.1`
- [ ] `hacs.json` present at repository root and valid for the current
      Marketplace/HACS schema.
- [ ] `brand/icon.png` present and accepted by the Marketplace.
- [ ] Integration remains directly below `custom_components/smartfriends_box/`.
- [ ] No `requirements` entry is needed while the client is vendored, or the
      PyPI decision has been implemented consistently.
- [ ] `CHANGELOG.md` and known limitations are current.

## Verification before tagging

- [ ] `pytest tests` passes.
- [ ] `pytest tests_ha` passes.
- [ ] Ruff and strict mypy pass.
- [ ] `ha core check` passes on the target HA version.
- [ ] Local installation on the target HA version loads all expected entities.
- [ ] Config flow, reconfigure, reauth, discovery, diagnostics, and restart
      behavior have current evidence.
- [ ] RSSI 0 and delayed position behavior are documented as known device
      properties, not used as a release blocker by themselves.
- [ ] `git status` is clean and the release commit is recorded.

## Repository hygiene

- [ ] No `.env`, tokens, passwords, private keys, or local databases are in the
      tree or release tag.
- [ ] No internal device labels, room names, master/component IDs, private IP
      addresses, or local evidence is in the public tree.
- [ ] The local `internal/` evidence directory remains ignored.
- [ ] The release archive and public history are built from the
      `public-beta` root commit and never merged with the internal local main
      history.
- [ ] The public branch contains exactly one root commit and no parent links
      to the internal history.
- [ ] Test scripts in the public tree are generic and do not address a specific
      installation.

## GitHub and Marketplace

- [ ] Create the GitHub repository and default branch.
- [ ] Push only after explicit approval.
- [ ] Create annotated tag `v0.2.0-beta.1` and a pre-release entry.
- [ ] Include scope, tested devices, known limitations, and installation notes
      in the release notes.
- [ ] Run HACS/Marketplace validation against the real repository.
- [ ] Run hassfest or the current Home Assistant validation workflow.
- [ ] Add the repository to HACS/Marketplace and test a clean install.
- [ ] Confirm upgrade from `0.1.0` to `0.2.0-beta.1` if an older entry exists.

## Go/no-go sign-off

- [ ] Technical owner accepts known device/radio limitations.
- [ ] Security review confirms no credentials or private environment data in
      the public history and release artifacts.
- [ ] Support process and issue triage are ready.
- [ ] Explicit publication approval from the owner.
- [ ] Rollback plan: mark the release pre-release, remove it from Marketplace,
      and publish a fixed patch if a blocking defect is found.

No remote repository, tag, release, or Marketplace entry is created by this
checklist itself.
