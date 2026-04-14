"""Tests for AVE hub device registry metadata."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.ave_dominaplus.const import DOMAIN
from custom_components.ave_dominaplus.device_info import build_hub_device_info
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC


def _server_stub(
    *,
    mac: str = "",
    config_entry_unique_id: str | None = None,
    config_entry_id: str | None = None,
    host: str = "192.168.1.10",
):
    """Build a light-weight server stub for device_info tests."""
    return SimpleNamespace(
        mac_address=mac,
        config_entry_unique_id=config_entry_unique_id,
        config_entry_id=config_entry_id,
        settings=SimpleNamespace(host=host),
    )


def test_device_info_uses_mac_identifier_and_connection() -> None:
    """Use MAC as primary stable identifier when available."""
    server = _server_stub(mac="AA:BB:CC:DD:EE:FF")

    info = build_hub_device_info(server)

    assert info["identifiers"] == {(DOMAIN, "hub_aa:bb:cc:dd:ee:ff")}
    assert info["connections"] == {(CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}


def test_device_info_falls_back_to_entry_unique_id() -> None:
    """Fallback to config entry unique id if MAC is not available."""
    server = _server_stub(config_entry_unique_id="AA:BB:CC:DD:EE:FF")

    info = build_hub_device_info(server)

    assert info["identifiers"] == {(DOMAIN, "hub_aa:bb:cc:dd:ee:ff")}
    assert info["connections"] == set()


def test_device_info_falls_back_to_entry_id() -> None:
    """Fallback to config entry id when MAC and unique id are missing."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_hub_device_info(server)

    assert info["identifiers"] == {(DOMAIN, "hub_entry-123")}


def test_device_info_falls_back_to_host() -> None:
    """Last-resort fallback uses host when no identifiers are available."""
    server = _server_stub(host="10.0.0.99")

    info = build_hub_device_info(server)

    assert info["identifiers"] == {(DOMAIN, "hub_10.0.0.99")}
    assert info["manufacturer"] == "AVE"
    assert info["model"] == "domina plus webserver"
    assert info["name"] == "AVE dominaplus Hub"
    assert info["configuration_url"] == "http://10.0.0.99"
