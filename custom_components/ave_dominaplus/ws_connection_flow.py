"""Connection bootstrap and thermostat workflow helpers for AVE webserver."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .ave_map import AveMap
from .const import (
    AVE_FAMILY_ANTITHEFT_AREA,
    AVE_FAMILY_DIMMER,
    AVE_FAMILY_ONOFFLIGHTS,
    AVE_FAMILY_SCENARIO,
    AVE_FAMILY_SHUTTER_HUNG,
    AVE_FAMILY_SHUTTER_ROLLING,
    AVE_FAMILY_SHUTTER_SLIDING,
)

if TYPE_CHECKING:
    from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


async def on_connect_actions(server: AveWebServer) -> None:
    """Actions to perform after connecting to the web server."""
    if server.ws_conn is None or server.ws_conn.closed:
        return

    server.ldi_done.clear()
    # await server.send_ws_command("LDI")  # Get device list (legacy)
    await server.send_ws_command("LI2")  # Get device list (with addresses)
    if not await wait_for_ldi(server):
        return

    if server.settings.fetch_lights:
        # Get status by family type 1 (switches) and 2 (dimmers)
        await server.send_ws_command("GSF", [str(AVE_FAMILY_ONOFFLIGHTS)])
        await server.send_ws_command("GSF", [str(AVE_FAMILY_DIMMER)])

    if server.settings.fetch_covers:
        await server.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_ROLLING)])
        await server.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_SLIDING)])
        await server.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_HUNG)])

    if server.settings.fetch_scenarios:
        # probably useless. Evaluate getting WSF instead
        await server.send_ws_command("GSF", [str(AVE_FAMILY_SCENARIO)])

    # Get status by family type 12 (motion detection areas)
    if server.settings.fetch_sensor_areas:
        await server.send_ws_command("GSF", [str(AVE_FAMILY_ANTITHEFT_AREA)])
        await server.send_ws_command("WSF", [str(AVE_FAMILY_ANTITHEFT_AREA)])

    if server.settings.fetch_thermostats:
        await start_thermostats_fetch_flow(server)

    await server.send_ws_command("SU3")  # Start streaming updates (most of them)

    # Starts streaming some other updates (UPD for TLO and XU, NET and CLD)
    # await server.send_ws_command("SU2")


async def start_thermostats_fetch_flow(server: AveWebServer) -> None:
    """Start thermostat bootstrap flow without blocking message handling."""

    # Some thermostat updates use mapCommandId instead of device_id. Reset the map
    # and command-loading state so later updates can be correlated correctly.
    server.ave_map = AveMap()
    server.thermostat_lm_done.clear()
    server.thermostat_lmc_done.clear()

    if server.thermostat_fetch_task and not server.thermostat_fetch_task.done():
        server.thermostat_fetch_task.cancel()

    await server.send_ws_command("LM")
    server.thermostat_fetch_task = asyncio.create_task(thermostats_fetch_flow(server))


async def wait_for_ldi(server: AveWebServer) -> bool:
    """Wait for at least one LDI response before thermostat bootstrap."""
    try:
        await asyncio.wait_for(server.ldi_done.wait(), 15.0)
    except TimeoutError:
        _LOGGER.warning(
            "Timed out waiting for LDI response; skipping thermostat bootstrap"
        )
        return False
    return True


async def thermostats_fetch_flow(server: AveWebServer) -> None:
    """Some thermostats send updates using mapCommandId instead of device_id, so we need to fetch the map and commands before we can correlate updates to devices."""
    # 1) wait until LM responses are received and the map is loaded
    try:
        await asyncio.wait_for(server.thermostat_lm_done.wait(), 15.0)
    except TimeoutError:
        _LOGGER.warning("Timed out waiting for LM responses; skipping thermostat map")
        return

    # 2) send LMC for each area once the LM map is loaded
    if server.ave_map.areas_loaded and server.ws_conn and not server.ws_conn.closed:
        if not server.ave_map.areas:
            _LOGGER.debug("LM map returned no areas")
            return
        for map_id in server.ave_map.areas:
            await server.send_ws_command("LMC", [map_id])
    else:
        _LOGGER.debug("Map not loaded or ws disconnected; skipping LMC send")
        return

    # 3) wait for all LMC responses (commands loaded)
    try:
        await asyncio.wait_for(server.thermostat_lmc_done.wait(), 15.0)
    except TimeoutError:
        _LOGGER.warning("Timed out waiting for LMC responses; proceeding")

    # 4) request thermostat status snapshots
    for device_id in server.all_thermostats_raw:
        await server.send_ws_command("WTS", [str(device_id)])
