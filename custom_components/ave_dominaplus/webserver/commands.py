"""Command helpers for AVE webserver outgoing actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from custom_components.ave_dominaplus.web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


def _is_ws_connected(server: AveWebServer) -> bool:
    """Return True when websocket transport is available for sending commands."""
    return bool(server.ws_conn and not server.ws_conn.closed)


async def switch_turn_on(server: AveWebServer, device_id: int) -> None:
    """Turn on the switch."""
    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "11"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def switch_turn_off(server: AveWebServer, device_id: int) -> None:
    """Turn off the switch."""
    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "12"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def switch_toggle(server: AveWebServer, device_id: int) -> None:
    """Toggle the switch."""
    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "10"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def scenario_execute(server: AveWebServer, device_id: int) -> None:
    """Execute a scenario."""
    if _is_ws_connected(server):
        await server.send_ws_command("ESI", [str(device_id), "0"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def dimmer_turn_on(
    server: AveWebServer, device_id: int, brightness_ave: int
) -> None:
    """Turn on the dimmer."""
    clamped_level = max(0, min(31, int(brightness_ave)))
    if clamped_level == 0:
        await server.dimmer_turn_off(device_id)
        return

    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "3"])
        await server.send_ws_command("SIL", [str(device_id)], [[clamped_level]])
    else:
        _LOGGER.error("WebSocket is not connected")


async def dimmer_turn_off(server: AveWebServer, device_id: int) -> None:
    """Turn off the dimmer."""
    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "4"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def dimmer_toggle(server: AveWebServer, device_id: int) -> None:
    """Toggle the dimmer."""
    if _is_ws_connected(server):
        await server.send_ws_command("EBI", [str(device_id), "2"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def cover_open(server: AveWebServer, device_id: int) -> None:
    """Open the cover."""
    if _is_ws_connected(server):
        await server.send_ws_command("EAI", [str(device_id), "8"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def cover_close(server: AveWebServer, device_id: int) -> None:
    """Close the cover."""
    if _is_ws_connected(server):
        await server.send_ws_command("EAI", [str(device_id), "9"])
    else:
        _LOGGER.error("WebSocket is not connected")


async def cover_stop(server: AveWebServer, device_id: int, command: str) -> None:
    """Stop the cover according to AVE movement direction command."""
    if _is_ws_connected(server):
        await server.send_ws_command("EAI", [str(device_id), command])
    else:
        _LOGGER.error("WebSocket is not connected")


async def send_thermostat_sts(
    server: AveWebServer,
    parameters: list[Any],
    records: list[list[Any]],
) -> None:
    """Send a command to update the thermostat season/temperatures."""
    if _is_ws_connected(server):
        await server.send_ws_command("STS", parameters, records)
    else:
        _LOGGER.error("WebSocket is not connected")


async def thermostat_on_off(server: AveWebServer, device_id: int, on_off: int) -> None:
    """Turn the thermostat on or off."""
    if _is_ws_connected(server):
        await server.send_ws_command("TOO", [str(device_id), str(on_off)])
    else:
        _LOGGER.error("WebSocket is not connected")
