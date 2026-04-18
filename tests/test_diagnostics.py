"""Tests for diagnostics payload and masking helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.ave_dominaplus.diagnostics import (
    _mask_device_name,
    _mask_mac_tail,
    _mask_title_mac_tail,
    _masked_raw_ldi,
    async_get_config_entry_diagnostics,
)


def test_mask_mac_tail_masks_all_but_last_two_octets() -> None:
    """MAC masking should hide all but the last two octets."""
    assert _mask_mac_tail("aa:bb:cc:dd:ee:ff") == "**:**:**:**:ee:ff"


def test_mask_mac_tail_handles_non_colon_values() -> None:
    """Non-colon values should keep short strings and mask long tails."""
    assert _mask_mac_tail("abcd") == "abcd"
    assert _mask_mac_tail("abcdef") == "**cdef"


def test_mask_title_mac_tail_masks_mac_in_title() -> None:
    """Title MAC tail should be masked while preserving title prefix."""
    assert (
        _mask_title_mac_tail("AVE webserver aa:bb:cc:dd:ee:ff")
        == "AVE webserver **:**:**:**:ee:ff"
    )


def test_mask_title_mac_tail_ignores_titles_without_mac() -> None:
    """Titles without a MAC-like suffix should be returned unchanged."""
    assert _mask_title_mac_tail("") == ""
    assert _mask_title_mac_tail("AVE webserver") == "AVE webserver"


def test_masked_raw_ldi_masks_device_name() -> None:
    """Raw LDI diagnostics should mask sensitive device names."""
    masked = _masked_raw_ldi(
        [{"device_id": 1, "device_name": "Kitchen Light", "device_type": 1}]
    )
    assert masked[0]["device_name"] == _mask_device_name("Kitchen Light")


def test_mask_device_name_handles_short_values() -> None:
    """Short names should be returned as-is by masking helper."""
    assert _mask_device_name("A") == "A"
    assert _mask_device_name("AB") == "AB"


async def test_async_get_config_entry_diagnostics_masks_sensitive_data() -> None:
    """Diagnostics payload should redact sensitive data and include runtime counters."""
    runtime_data = SimpleNamespace(
        is_connected=AsyncMock(return_value=True),
        started=True,
        closed=False,
        systeminfo={"version": "1.2.3"},
        raw_ldi=[
            {
                "device_id": 1,
                "device_name": "Kitchen Light",
                "device_type": 1,
                "address_dec": 15,
                "address_hex": "0F",
            }
        ],
        binary_sensors={"a": object()},
        switches={"a": object(), "b": object()},
        buttons={},
        lights={},
        covers={},
        thermostats={},
        all_thermostats_raw={},
        numbers={},
        settings=SimpleNamespace(
            get_entity_names=True,
            fetch_sensor_areas=True,
            fetch_sensors=True,
            fetch_lights=True,
            fetch_covers=True,
            fetch_scenarios=True,
            fetch_thermostats=True,
        ),
        ave_map=SimpleNamespace(areas_loaded=True, command_loaded=False, areas={1: {}}),
    )
    config_entry = SimpleNamespace(
        entry_id="entry-1",
        title="AVE webserver aa:bb:cc:dd:ee:ff",
        version=1,
        minor_version=1,
        disabled_by=None,
        source="user",
        unique_id="aa:bb:cc:dd:ee:ff",
        state="loaded",
        data={"ip_address": "192.168.1.10"},
        options={"host": "192.168.1.10"},
        runtime_data=runtime_data,
    )

    diagnostics = await async_get_config_entry_diagnostics(None, config_entry)

    assert diagnostics["entry"]["title"].endswith("ee:ff")
    assert "aa:bb" not in diagnostics["entry"]["title"]
    assert diagnostics["entry"]["unique_id"].endswith("ee:ff")

    assert diagnostics["entry"]["data"]["ip_address"] != "192.168.1.10"
    assert "*" in diagnostics["entry"]["data"]["ip_address"]
    assert diagnostics["entry"]["options"]["host"] != "192.168.1.10"
    assert "*" in diagnostics["entry"]["options"]["host"]

    assert diagnostics["runtime"]["connected"] is True
    assert diagnostics["runtime"]["entity_counts"]["binary_sensors"] == 1
    assert diagnostics["runtime"]["entity_counts"]["switches"] == 2
    assert diagnostics["runtime"]["raw_ldi"][0]["device_name"] != "Kitchen Light"


async def test_async_get_config_entry_diagnostics_handles_missing_runtime() -> None:
    """Diagnostics should provide an empty runtime payload when runtime_data is missing."""
    config_entry = SimpleNamespace(
        entry_id="entry-1",
        title="AVE webserver aa:bb:cc:dd:ee:ff",
        version=1,
        minor_version=1,
        disabled_by=None,
        source="user",
        unique_id="aa:bb:cc:dd:ee:ff",
        state="loaded",
        data={"ip_address": "192.168.1.10"},
        options={},
        runtime_data=None,
    )

    diagnostics = await async_get_config_entry_diagnostics(None, config_entry)

    assert diagnostics["runtime"] == {}
