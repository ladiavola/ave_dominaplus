"""Helpers for Home Assistant device registry metadata."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import BRAND_PREFIX, DOMAIN
from .web_server import AveWebServer


def _hub_identifier(server: AveWebServer) -> str:
    """Build a stable hub identifier for the device registry."""
    if server.mac_address:
        return server.mac_address.lower()
    if server.config_entry_unique_id:
        return server.config_entry_unique_id.lower()
    if server.config_entry_id:
        return server.config_entry_id
    return server.settings.host


def build_hub_device_info(server: AveWebServer) -> DeviceInfo:
    """Return device_info for the AVE hub.

    Keep this stable to avoid changing existing entity IDs/friendly names.
    """
    connections = set()
    if server.mac_address:
        connections.add((CONNECTION_NETWORK_MAC, server.mac_address.lower()))

    return DeviceInfo(
        identifiers={(DOMAIN, f"hub_{_hub_identifier(server)}")},
        connections=connections,
        manufacturer="AVE",
        model="domina plus webserver",
        name=f"{BRAND_PREFIX} Hub",
        configuration_url=f"http://{server.settings.host}",
    )
