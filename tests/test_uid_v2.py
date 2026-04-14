"""Tests for unique ID v2 helper utilities."""

from __future__ import annotations

from custom_components.ave_dominaplus.uid_v2 import build_uid, find_unique_id, parse_uid


def test_build_uid_formats_hex_address() -> None:
    """build_uid should include uppercase two-digit hexadecimal address."""
    assert build_uid("aa:bb:cc:dd:ee:ff", 2, 10, 15) == "ave_aa:bb:cc:dd:ee:ff_family_2_10_0x0F"


def test_parse_uid_with_hex_address() -> None:
    """parse_uid should decode mac/family/device/address from hexadecimal form."""
    parsed = parse_uid("ave_aa:bb:cc:dd:ee:ff_family_2_10_0x1A")
    assert parsed == ("aa:bb:cc:dd:ee:ff", 2, 10, 26)


def test_parse_uid_with_decimal_address() -> None:
    """parse_uid should decode decimal address if present as decimal text."""
    parsed = parse_uid("ave_aa:bb:cc:dd:ee:ff_family_2_10_26")
    assert parsed == ("aa:bb:cc:dd:ee:ff", 2, 10, 26)


def test_parse_uid_without_address() -> None:
    """parse_uid should allow UIDs without address segment."""
    parsed = parse_uid("ave_aa:bb:cc:dd:ee:ff_family_2_10")
    assert parsed == ("aa:bb:cc:dd:ee:ff", 2, 10, None)


def test_parse_uid_returns_none_for_invalid_strings() -> None:
    """parse_uid should return None when the UID cannot be parsed."""
    assert parse_uid("ave_invalid") is None
    assert parse_uid("ave_x_family_notint_10") is None


def test_find_unique_id_matches_family_and_device() -> None:
    """find_unique_id should return matching UID by family and device id."""
    ids = [
        "ave_aa:bb:cc:dd:ee:ff_family_2_10_0x0F",
        "ave_aa:bb:cc:dd:ee:ff_family_3_9_0x11",
    ]
    assert (
        find_unique_id(ids, family=2, ave_device_id=10, mac_address="aa:bb:cc:dd:ee:ff")
        == "ave_aa:bb:cc:dd:ee:ff_family_2_10_0x0F"
    )


def test_find_unique_id_ignores_mac_mismatch_when_both_present() -> None:
    """find_unique_id should skip parsed IDs with explicit different MAC."""
    ids = [
        "ave_11:22:33:44:55:66_family_2_10_0x0F",
        "ave_aa:bb:cc:dd:ee:ff_family_2_10_0x10",
    ]
    assert (
        find_unique_id(ids, family=2, ave_device_id=10, mac_address="aa:bb:cc:dd:ee:ff")
        == "ave_aa:bb:cc:dd:ee:ff_family_2_10_0x10"
    )


def test_find_unique_id_returns_none_when_no_match() -> None:
    """find_unique_id should return None when no candidate matches."""
    ids = ["ave_aa:bb:cc:dd:ee:ff_family_3_9_0x11"]
    assert find_unique_id(ids, family=2, ave_device_id=10) is None
