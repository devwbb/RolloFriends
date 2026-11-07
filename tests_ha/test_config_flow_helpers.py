from __future__ import annotations

from types import SimpleNamespace

import pytest
from custom_components.smartfriends_box import config_flow
from custom_components.smartfriends_box.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from custom_components.smartfriends_box.vendor.aiosmartfriends import (
    BoxIdentity,
    GatewayInfo,
    SmartFriendsAuthenticationError,
    SmartFriendsCertificateError,
    SmartFriendsConnectionError,
    SmartFriendsTimeout,
)


class FakeClient:
    gateway = GatewayInfo("session", hardware="TestBox", mac_address="aabbccddeeff")
    shutters = (object(),)
    error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def async_connect(self):
        if self.error is not None:
            raise self.error
        return self.gateway

    async def async_disconnect(self) -> None:
        pass


@pytest.mark.asyncio
async def test_validate_credentials_success(monkeypatch) -> None:
    monkeypatch.setattr(config_flow, "SmartFriendsClient", FakeClient)
    validation, errors = await config_flow._validate_credentials(
        "192.0.2.1", 4300, "user", "password"
    )
    assert errors == {}
    assert validation is not None
    assert validation.mac == "AABBCCDDEEFF"
    assert validation.title == "SmartFriends Box TestBox"
    assert validation.shutter_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [
        (SmartFriendsAuthenticationError("x"), "invalid_auth"),
        (SmartFriendsCertificateError("x"), "certificate_error"),
        (SmartFriendsConnectionError("x"), "cannot_connect"),
        (SmartFriendsTimeout("x"), "cannot_connect"),
    ],
)
async def test_validate_credentials_errors(monkeypatch, error, expected) -> None:
    class FailingClient(FakeClient):
        def __init__(self, *args, **kwargs) -> None:
            self.error = error

    monkeypatch.setattr(config_flow, "SmartFriendsClient", FailingClient)
    validation, errors = await config_flow._validate_credentials(
        "192.0.2.1", 4300, "user", "password"
    )
    assert validation is None
    assert errors == {"base": expected}


@pytest.mark.asyncio
async def test_validate_credentials_no_shutters(monkeypatch) -> None:
    class EmptyClient(FakeClient):
        shutters = ()

    monkeypatch.setattr(config_flow, "SmartFriendsClient", EmptyClient)
    validation, errors = await config_flow._validate_credentials(
        "192.0.2.1", 4300, "user", "password"
    )
    assert validation is None
    assert errors == {"base": "no_supported_devices"}


@pytest.mark.asyncio
async def test_validate_credentials_missing_mac(monkeypatch) -> None:
    class NoMacClient(FakeClient):
        gateway = GatewayInfo("session", hardware="TestBox", mac_address=None)

    monkeypatch.setattr(config_flow, "SmartFriendsClient", NoMacClient)
    validation, errors = await config_flow._validate_credentials(
        "192.0.2.1", 4300, "user", "password"
    )
    assert validation is None
    assert errors == {"base": "no_identity"}


def _flow_with_entry(kind: str):
    entry = SimpleNamespace(
        data={
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 4300,
            CONF_USERNAME: "test-user",
            CONF_PASSWORD: "old-password",
        },
        title="SmartFriends Box TestBox",
        unique_id="AABBCCDDEEFF",
    )
    flow = object.__new__(config_flow.SmartFriendsConfigFlow)
    if kind == "reauth":
        flow._get_reauth_entry = lambda: entry
    else:
        flow._get_reconfigure_entry = lambda: entry
    flow.async_update_reload_and_abort = lambda entry, **kwargs: {
        "type": "abort",
        "entry": entry,
        "kwargs": kwargs,
    }
    flow.async_show_form = lambda **kwargs: {"type": "form", "kwargs": kwargs}
    flow.add_suggested_values_to_schema = lambda schema, values: schema
    return flow, entry


@pytest.mark.asyncio
async def test_reauth_confirm_updates_only_password(monkeypatch) -> None:
    flow, entry = _flow_with_entry("reauth")

    async def validate(host, port, username, password):
        assert username == "test-user"
        assert password == "new-password"
        return (
            config_flow._Validation(
                host=host,
                port=port,
                username=username,
                password=password,
                mac=entry.unique_id,
                title=entry.title,
                shutter_count=1,
            ),
            {},
        )

    monkeypatch.setattr(config_flow, "_validate_credentials", validate)
    result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new-password"})
    assert result["type"] == "abort"
    assert result["kwargs"]["data_updates"] == {CONF_PASSWORD: "new-password"}
    assert result["kwargs"]["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_reauth_confirm_shows_validation_error(monkeypatch) -> None:
    flow, _ = _flow_with_entry("reauth")

    async def validate(host, port, username, password):
        return None, {"base": "invalid_auth"}

    monkeypatch.setattr(config_flow, "_validate_credentials", validate)
    result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "wrong"})
    assert result["type"] == "form"
    assert result["kwargs"]["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_reconfigure_updates_connection_but_not_password(monkeypatch) -> None:
    flow, entry = _flow_with_entry("reconfigure")

    async def validate(host, port, username, password):
        assert password == "old-password"
        return (
            config_flow._Validation(
                host=host,
                port=port,
                username=username,
                password=password,
                mac=entry.unique_id,
                title=entry.title,
                shutter_count=1,
            ),
            {},
        )

    monkeypatch.setattr(config_flow, "_validate_credentials", validate)
    result = await flow.async_step_reconfigure(
        {CONF_HOST: "192.0.2.2", CONF_PORT: 4301, CONF_USERNAME: "new-user"}
    )
    assert result["type"] == "abort"
    updates = result["kwargs"]["data_updates"]
    assert updates == {
        CONF_HOST: "192.0.2.2",
        CONF_PORT: 4301,
        CONF_USERNAME: "new-user",
    }
    assert CONF_PASSWORD not in updates


@pytest.mark.asyncio
async def test_reconfigure_rejects_different_box_identity(monkeypatch) -> None:
    flow, _ = _flow_with_entry("reconfigure")

    async def validate(host, port, username, password):
        return (
            config_flow._Validation(
                host=host,
                port=port,
                username=username,
                password=password,
                mac="112233445566",
                title="Other box",
                shutter_count=1,
            ),
            {},
        )

    monkeypatch.setattr(config_flow, "_validate_credentials", validate)
    result = await flow.async_step_reconfigure(
        {CONF_HOST: "192.0.2.2", CONF_PORT: 4300, CONF_USERNAME: "test-user"}
    )
    assert result["type"] == "form"
    assert result["kwargs"]["errors"] == {"base": "identity_mismatch"}


def _discovery_flow():
    flow = object.__new__(config_flow.SmartFriendsConfigFlow)
    flow.context = {}
    flow._unique_id = None

    async def set_unique_id(unique_id):
        flow._unique_id = unique_id

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = lambda **kwargs: None
    flow.add_suggested_values_to_schema = lambda schema, values: schema
    flow.async_show_form = lambda **kwargs: {"type": "form", "kwargs": kwargs}
    flow.async_abort = lambda **kwargs: {"type": "abort", "kwargs": kwargs}
    return flow


def _discovery_info(properties):
    return SimpleNamespace(
        type="_smartHOME._tcp.local.",
        ip_address="192.0.2.30",
        port=4300,
        properties=properties,
        name="Smart_Friends_Box-Test",
    )


@pytest.mark.asyncio
async def test_zeroconf_flow_accepts_matching_identity(monkeypatch) -> None:
    flow = _discovery_flow()

    async def probe(host, port, *, timeout):
        assert (host, port, timeout) == ("192.0.2.30", 4300, 5)
        return BoxIdentity(mac_address="AABBCCDDEEFF", is_configured=True)

    monkeypatch.setattr(config_flow, "async_probe_identity", probe)
    result = await flow.async_step_zeroconf(_discovery_info({"macaddress": "aabbccddeeff"}))
    assert flow._unique_id == "AABBCCDDEEFF"
    assert flow._discovered_host == "192.0.2.30"
    assert flow._discovered_port == 4300
    assert result["type"] == "form"
    assert result["kwargs"]["step_id"] == "discovery_confirm"


@pytest.mark.asyncio
async def test_zeroconf_flow_rejects_identity_mismatch(monkeypatch) -> None:
    flow = _discovery_flow()

    async def probe(host, port, *, timeout):
        return BoxIdentity(mac_address="112233445566", is_configured=True)

    monkeypatch.setattr(config_flow, "async_probe_identity", probe)
    result = await flow.async_step_zeroconf(_discovery_info({"macaddress": "aabbccddeeff"}))
    assert result["type"] == "abort"
    assert result["kwargs"]["reason"] == "identity_mismatch"
    assert flow._unique_id is None
