"""Helpers for AVE entity unique_id v2 handling."""

from collections.abc import Iterable


def build_uid(
    mac_address: str | None, family: int, ave_device_id: int, address_dec: int
) -> str:
    """Build a normalized v2 unique ID."""
    return f"ave_{mac_address}_family_{family}_{ave_device_id}_0x{address_dec:02X}"


def parse_uid(unique_id: str) -> tuple[str | None, int, int, int | None] | None:
    """Parse mac, family, device_id and optional address_dec from a v2 unique_id."""
    parts = unique_id.split("_")
    try:
        family_idx = parts.index("family")
    except ValueError:
        return None

    if len(parts) <= family_idx + 2:
        return None

    try:
        mac_address = "_".join(parts[1:family_idx]).strip() or None
        family = int(parts[family_idx + 1])
        ave_device_id = int(parts[family_idx + 2])

        address_dec = None
        if len(parts) > family_idx + 3:
            address_raw = parts[family_idx + 3].strip()
            if address_raw:
                if address_raw.lower().startswith("0x"):
                    address_dec = int(address_raw, 16)
                else:
                    address_dec = int(address_raw, 10)
    except ValueError:
        return None

    return mac_address, family, ave_device_id, address_dec


def find_unique_id(
    unique_ids: Iterable[str],
    family: int,
    ave_device_id: int,
    mac_address: str | None = None,
) -> str | None:
    """Find an already registered unique_id by family and AVE device id."""
    for unique_id in unique_ids:
        parsed = parse_uid(unique_id)
        if parsed is None:
            continue

        parsed_mac, parsed_family, parsed_device_id, _parsed_address_dec = parsed
        if mac_address and parsed_mac and parsed_mac != mac_address:
            continue
        if parsed_family == family and parsed_device_id == ave_device_id:
            return unique_id

    return None
