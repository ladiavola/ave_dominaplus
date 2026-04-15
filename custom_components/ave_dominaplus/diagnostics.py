"""Diagnostics support for AVE dominaplus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

REDACT_KEYS = {
    "ip_address",
    "host",
    "mac",
    "mac_address",
}


def _mask_mac_tail(value: str) -> str:
    """Mask MAC-like value keeping only the last two octets visible."""
    if ":" not in value:
        if len(value) <= 4:
            return value
        return "*" * (len(value) - 4) + value[-4:]

    parts = value.split(":")
    if len(parts) < 2:
        return value
    hidden = ["**"] * max(len(parts) - 2, 0)
    return ":".join([*hidden, *parts[-2:]])


def _mask_title_mac_tail(title: str) -> str:
    """Mask MAC in title if present, keeping only the tail."""
    words = title.split(" ")
    if not words:
        return title
    last_word = words[-1]
    if ":" not in last_word:
        return title
    words[-1] = _mask_mac_tail(last_word)
    return " ".join(words)


def _mask_device_name(device_name: str) -> str:
    """Mask all chars except first and last."""
    if len(device_name) <= 2:
        return device_name
    return f"{device_name[0]}{'*' * (len(device_name) - 2)}{device_name[-1]}"


def _masked_raw_ldi(raw_ldi: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return raw LDI records with masked device names."""
    masked_records: list[dict[str, Any]] = []
    for record in raw_ldi:
        masked_record = dict(record)
        device_name = masked_record.get("device_name")
        if isinstance(device_name, str):
            masked_record["device_name"] = _mask_device_name(device_name)
        masked_records.append(masked_record)
    return masked_records


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    webserver = config_entry.runtime_data

    runtime: dict[str, Any] = {}
    if webserver is not None:
        runtime = {
            "connected": await webserver.is_connected(),
            "started": webserver.started,
            "closed": webserver.closed,
            "systeminfo": dict(webserver.systeminfo),
            "raw_ldi_count": len(webserver.raw_ldi),
            "raw_ldi": _masked_raw_ldi(webserver.raw_ldi),
            "entity_counts": {
                "binary_sensors": len(webserver.binary_sensors),
                "switches": len(webserver.switches),
                "buttons": len(webserver.buttons),
                "lights": len(webserver.lights),
                "covers": len(webserver.covers),
                "thermostats": len(webserver.thermostats),
                "sensors": len(webserver.numbers),
            },
            "feature_flags": {
                "get_entity_names": webserver.settings.get_entity_names,
                "fetch_sensor_areas": webserver.settings.fetch_sensor_areas,
                "fetch_sensors": webserver.settings.fetch_sensors,
                "fetch_lights": webserver.settings.fetch_lights,
                "fetch_covers": webserver.settings.fetch_covers,
                "fetch_scenarios": webserver.settings.fetch_scenarios,
                "fetch_scenario_schedule": webserver.settings.fetch_scenario_schedule,
                "fetch_thermostats": webserver.settings.fetch_thermostats,
            },
            "thermostat_flow": {
                "known_thermostats_from_ldi": len(webserver.all_thermostats_raw),
                "areas_loaded": webserver.ave_map.areas_loaded,
                "commands_loaded": webserver.ave_map.command_loaded,
                "areas_count": len(webserver.ave_map.areas),
            },
        }

    data = {
        "domain": DOMAIN,
        "entry": {
            "entry_id": config_entry.entry_id,
            "title": _mask_title_mac_tail(config_entry.title),
            "version": config_entry.version,
            "minor_version": config_entry.minor_version,
            "disabled_by": config_entry.disabled_by,
            "source": config_entry.source,
            "unique_id": (
                _mask_mac_tail(config_entry.unique_id)
                if isinstance(config_entry.unique_id, str)
                else config_entry.unique_id
            ),
            "state": str(config_entry.state),
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
        },
        "runtime": runtime,
    }

    return async_redact_data(data, REDACT_KEYS)
