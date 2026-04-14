"""Tests for AVE map and command utilities."""

from __future__ import annotations

from custom_components.ave_dominaplus.ave_map import AveMap, AveMapCommand


def test_read_record_value_handles_missing_index() -> None:
    """Record reader should return empty string for out-of-range indexes."""
    assert AveMapCommand._read_record_value(["a", "b"], 1) == "b"
    assert AveMapCommand._read_record_value(["a", "b"], 9) == ""


def test_from_ws_records_parses_valid_command() -> None:
    """Command parser should populate all typed fields on valid records."""
    command = AveMapCommand.from_ws_records(
        [
            "10",
            "Heat",
            "2",
            "11",
            "12",
            "icod",
            "i1",
            "i2",
            "i3",
            "i4",
            "i5",
            "i6",
            "i7",
            "icoc",
            "44",
            "4",
        ]
    )

    assert command.command_id == 10
    assert command.command_name == "Heat"
    assert command.command_type == 2
    assert command.command_X == 11
    assert command.command_Y == 12
    assert command.icod == "icod"
    assert command.ico7 == "i7"
    assert command.icoc == "icoc"
    assert command.device_id == 44
    assert command.device_family == 4


def test_from_ws_records_handles_bad_values() -> None:
    """Parser should tolerate malformed records and keep defaults."""
    command = AveMapCommand.from_ws_records(["bad", "name"])

    assert command.command_id == -1
    assert command.command_name == ""
    assert command.device_id == -1
    assert command.device_family == -1


def test_load_areas_and_commands_and_query_by_keys() -> None:
    """Map should load areas/commands and support family/id based lookups."""
    ave_map = AveMap()
    ave_map.load_areas_from_wsrecords([["1", "Ground", "1"], ["2", "First", "2"]])

    assert ave_map.areas_loaded is True
    assert len(ave_map.areas) == 2
    assert ave_map.command_loaded is False

    area_1_record = [
        "100",
        "Thermo 1",
        "0",
        "0",
        "0",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "10",
        "4",
    ]
    area_2_record = [
        "200",
        "Dimmer 1",
        "0",
        "0",
        "0",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "20",
        "2",
    ]

    ave_map.load_area_commands(1, [area_1_record])
    assert ave_map.areas[1].commands_loaded is True
    assert ave_map.command_loaded is False

    ave_map.load_area_commands(2, [area_2_record])
    assert ave_map.areas[2].commands_loaded is True
    assert ave_map.command_loaded is True

    family_4 = ave_map.get_commands_by_family(4)
    assert len(family_4) == 1
    assert family_4[0].command_id == 100

    assert ave_map.get_command_by_id_and_family(100, 4) is not None
    assert ave_map.get_command_by_deviceid(10) is not None
    assert ave_map.get_command_by_deviceid_and_family(10, 4) is not None
    assert ave_map.get_command_by_id_and_family(999, 4) is None
    assert ave_map.get_command_by_deviceid(999) is None


def test_load_area_commands_ignores_unknown_area() -> None:
    """Loading commands for unknown area should be a no-op."""
    ave_map = AveMap()
    ave_map.load_area_commands(99, [["1"]])

    assert ave_map.command_loaded is False
