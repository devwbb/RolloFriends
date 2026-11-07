from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "src" / "aiosmartfriends"
VENDOR = ROOT / "custom_components" / "smartfriends_box" / "vendor" / "aiosmartfriends"
INTEGRATION = ROOT / "custom_components" / "smartfriends_box"


def _files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_manifest_is_valid() -> None:
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == "smartfriends_box"
    assert manifest["name"] == "RolloFriends"
    assert manifest["config_flow"] is True
    assert manifest["version"] == "0.2.0-beta.1"
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["version"] == "0.2.0b1"
    assert manifest["requirements"] == []
    assert manifest["integration_type"] == "hub"
    assert manifest["iot_class"] == "local_push"
    assert manifest["documentation"] == "https://github.com/devwbb/RolloFriends"
    assert manifest["issue_tracker"] == "https://github.com/devwbb/RolloFriends/issues"
    assert manifest["codeowners"] == ["@devwbb"]
    assert "_smarthome._tcp.local." in manifest["zeroconf"]
    assert "_smartHOME._tcp.local." in manifest["zeroconf"]
    keys = list(manifest)
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_hacs_metadata_and_translations() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == "RolloFriends"
    assert hacs["homeassistant"] == "2026.11.0"
    assert hacs["render_readme"] is True
    assert (ROOT / "CHANGELOG.md").is_file()
    assert (ROOT / "docs" / "INSTALLATION.md").is_file()
    assert (ROOT / "docs" / "DEVELOPMENT.md").is_file()
    source = json.loads((INTEGRATION / "strings.json").read_text())
    for language in ("de", "en"):
        translated = json.loads((INTEGRATION / "translations" / f"{language}.json").read_text())
        assert set(source["config"]["step"]) == set(translated["config"]["step"])
        assert set(source["config"]["error"]) == set(translated["config"]["error"])
        assert set(source["config"]["abort"]) == set(translated["config"]["abort"])


def test_brand_icon_is_png() -> None:
    data = (INTEGRATION / "brand" / "icon.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_vendored_library_is_in_sync() -> None:
    assert _files(LIBRARY) == _files(VENDOR)


def test_env_is_ignored_and_not_packaged() -> None:
    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in gitignore
    assert not any((INTEGRATION / ".env").glob("*"))
    assert not (ROOT / "src" / ".env").exists()
