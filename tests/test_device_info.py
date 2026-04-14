"""Tests for AVE hub device registry metadata."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from custom_components.ave_dominaplus.const import (
    AVE_FAMILY_DIMMER,
    AVE_FAMILY_MOTION_SENSOR,
    AVE_FAMILY_THERMOSTAT,
    DOMAIN,
)
from custom_components.ave_dominaplus.device_info import (
    build_endpoint_device_info,
    build_hub_device_info,
)
from custom_components.ave_dominaplus.web_server import AveWebServer
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

    info = build_hub_device_info(cast(AveWebServer, server))

    assert info.get("identifiers") == {(DOMAIN, "hub_aa:bb:cc:dd:ee:ff")}
    assert info.get("connections") == {
        (CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")
    }


def test_device_info_falls_back_to_entry_unique_id() -> None:
    """Fallback to config entry unique id if MAC is not available."""
    server = _server_stub(config_entry_unique_id="AA:BB:CC:DD:EE:FF")

    info = build_hub_device_info(cast(AveWebServer, server))

    assert info.get("identifiers") == {(DOMAIN, "hub_aa:bb:cc:dd:ee:ff")}
    assert info.get("connections") == set()


def test_device_info_falls_back_to_entry_id() -> None:
    """Fallback to config entry id when MAC and unique id are missing."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_hub_device_info(cast(AveWebServer, server))

    assert info.get("identifiers") == {(DOMAIN, "hub_entry-123")}


def test_device_info_falls_back_to_host() -> None:
    """Last-resort fallback uses host when no identifiers are available."""
    server = _server_stub(host="10.0.0.99")

    info = build_hub_device_info(cast(AveWebServer, server))

    assert info.get("identifiers") == {(DOMAIN, "hub_10.0.0.99")}
    assert info.get("manufacturer") == "AVE"
    assert info.get("model") == "AVE dominaplus webserver"
    assert info.get("name") == "Dominaplus Hub"
    assert info.get("configuration_url") == "http://10.0.0.99"


def test_endpoint_device_info_is_nested_under_hub() -> None:
    """Endpoint devices should reference the hub with via_device."""
    server = _server_stub(mac="AA:BB:CC:DD:EE:FF", host="10.0.0.99")

    info = build_endpoint_device_info(
        cast(AveWebServer, server),
        family=AVE_FAMILY_DIMMER,
        ave_device_id=45,
    )

    assert info.get("identifiers") == {(DOMAIN, "endpoint_aa:bb:cc:dd:ee:ff_lighting")}
    assert info.get("via_device") == (DOMAIN, "hub_aa:bb:cc:dd:ee:ff")
    assert info.get("name") == "Dominaplus Lighting"
    assert info.get("model") == "AVE dominaplus lighting"
    assert info.get("manufacturer") == "AVE"
    assert info.get("configuration_url") == "http://10.0.0.99"


def test_endpoint_device_info_uses_entry_fallback_identifier() -> None:
    """Endpoint identifier should fall back to config entry id when needed."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_endpoint_device_info(
        cast(AveWebServer, server),
        family=AVE_FAMILY_THERMOSTAT,
        ave_device_id=7,
    )

    assert info.get("identifiers") == {(DOMAIN, "endpoint_entry-123_thermostat_7")}
    assert info.get("via_device") == (DOMAIN, "hub_entry-123")
    assert info.get("name") == "Thermostat 7"


def test_endpoint_thermostat_name_is_cleaned_for_offset_suffix() -> None:
    """Thermostat device names should drop an "offset" suffix when present."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_endpoint_device_info(
        cast(AveWebServer, server),
        family=AVE_FAMILY_THERMOSTAT,
        ave_device_id=9,
        ave_name="Living Room Offset",
    )

    assert info.get("identifiers") == {(DOMAIN, "endpoint_entry-123_thermostat_9")}
    assert info.get("name") == "Thermostat Living Room"


def test_endpoint_thermostat_name_keeps_existing_prefix() -> None:
    """Thermostat names that already include prefix should not be doubled."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_endpoint_device_info(
        cast(AveWebServer, server),
        family=AVE_FAMILY_THERMOSTAT,
        ave_device_id=10,
        ave_name="Thermostat Studio",
    )

    assert info.get("name") == "Thermostat Studio"


def test_endpoint_motion_sensors_are_grouped() -> None:
    """All antitheft motion sensors should map to one grouped child device."""
    server = _server_stub(config_entry_id="entry-123")

    info = build_endpoint_device_info(
        cast(AveWebServer, server),
        family=AVE_FAMILY_MOTION_SENSOR,
        ave_device_id=44,
    )

    assert info.get("identifiers") == {
        (DOMAIN, "endpoint_entry-123_antitheft_sensors")
    }
    assert info.get("name") == "Dominaplus Antitheft Sensors"
