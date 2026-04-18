"""Tests for AVE thermostat datatypes."""

from __future__ import annotations

import pytest

from custom_components.ave_dominaplus.ave_thermostat import AveThermostatProperties


def test_from_wts_parses_full_record() -> None:
    """WTS parsing should map record values to typed thermostat properties."""
    props = AveThermostatProperties.from_wts(
        parameters=["12"],
        records=[["resp", "2", "cfg", "15", "1", "234", "M", "210", "0", "1"]],
    )

    assert props.device_id == 12
    assert props.device_name == "12"
    assert props.device_response == "resp"
    assert props.fan_level == 2
    assert props.configuration == "cfg"
    assert props.offset == 1.5
    assert props.season == "1"
    assert props.temperature == 23.4
    assert props.mode == "M"
    assert props.set_point == 21.0
    assert props.forced_mode == 0
    assert props.local_off == 1


def test_from_wts_forced_mode_overrides_mode() -> None:
    """Forced mode flag should force mode value to 1F."""
    props = AveThermostatProperties.from_wts(
        parameters=["7"],
        records=[["resp", "1", "cfg", "0", "0", "200", "S", "190", "1", "0"]],
    )

    assert props.mode == "1F"
    assert props.forced_mode == 1


def test_from_wts_handles_missing_optional_values() -> None:
    """Missing record values should fall back to safe defaults."""
    props = AveThermostatProperties.from_wts(parameters=["5"], records=[[]])

    assert props.device_id == 5
    assert props.device_response == ""
    assert props.fan_level == -1
    assert props.configuration == ""
    assert props.offset is None
    assert props.season == ""
    assert props.temperature == 0.0
    assert props.mode == ""
    assert props.set_point is None
    assert props.forced_mode == 0
    assert props.local_off is None


def test_from_wts_raises_on_missing_parameters() -> None:
    """Parsing should fail when parameter list is empty or missing."""
    with pytest.raises(ValueError, match="Parameters list is empty or None"):
        AveThermostatProperties.from_wts(parameters=[], records=[])


def test_from_wts_raises_on_invalid_device_id() -> None:
    """Parsing should fail when first parameter is not a numeric device ID."""
    with pytest.raises(ValueError, match="First parameter must be a valid device ID"):
        AveThermostatProperties.from_wts(parameters=["bad"], records=[])
