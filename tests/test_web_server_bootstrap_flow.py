"""Tests for AVE webserver bootstrap and thermostat fetch flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.ave_dominaplus.web_server import AveWebServer
from homeassistant.core import HomeAssistant


def _new_server(hass: HomeAssistant, **overrides) -> AveWebServer:
    """Build a server fixture for bootstrap-flow tests."""
    settings: dict[str, object] = {
        "ip_address": "192.168.1.10",
        "get_entities_names": True,
        "fetch_sensor_areas": True,
        "fetch_sensors": True,
        "fetch_lights": True,
        "fetch_covers": True,
        "fetch_thermostats": True,
        "onOffLightsAsSwitch": True,
    }
    settings.update(overrides)
    return AveWebServer(settings, hass)


async def test_on_connect_actions_sends_expected_bootstrap_commands(
    hass: HomeAssistant,
) -> None:
    """Connection bootstrap should issue discovery/status/update commands in order."""
    server = _new_server(hass)
    server.ws_conn = SimpleNamespace(closed=False)
    server.send_ws_command = AsyncMock()
    server._wait_for_ldi = AsyncMock(return_value=True)
    server._start_thermostats_fetch_flow = AsyncMock()

    await server.on_connect_actions()

    # Core bootstrap commands should always include LI2 and SU3.
    server.send_ws_command.assert_any_await("LI2")
    server.send_ws_command.assert_any_await("SU3")
    server.send_ws_command.assert_any_await("GSF", ["1"])
    server.send_ws_command.assert_any_await("GSF", ["2"])
    server.send_ws_command.assert_any_await("GSF", ["3"])
    server.send_ws_command.assert_any_await("WSF", ["12"])
    server._start_thermostats_fetch_flow.assert_awaited_once()


async def test_on_connect_actions_stops_when_ldi_wait_fails(hass: HomeAssistant) -> None:
    """Bootstrap should stop early if device list does not arrive in time."""
    server = _new_server(hass)
    server.ws_conn = SimpleNamespace(closed=False)
    server.send_ws_command = AsyncMock()
    server._wait_for_ldi = AsyncMock(return_value=False)
    server._start_thermostats_fetch_flow = AsyncMock()

    await server.on_connect_actions()

    server.send_ws_command.assert_awaited_once_with("LI2")
    server._start_thermostats_fetch_flow.assert_not_awaited()


async def test_on_connect_actions_returns_when_ws_closed(hass: HomeAssistant) -> None:
    """Bootstrap should no-op when websocket is not connected."""
    server = _new_server(hass)
    server.ws_conn = SimpleNamespace(closed=True)
    server.send_ws_command = AsyncMock()

    await server.on_connect_actions()

    server.send_ws_command.assert_not_awaited()


async def test_start_thermostats_fetch_flow_initializes_and_sends_lm(
    hass: HomeAssistant,
) -> None:
    """Thermostat bootstrap starter should reset events, send LM, and spawn task."""
    server = _new_server(hass)
    server.send_ws_command = AsyncMock()
    fake_task = Mock()

    def _create_task(coro):
        coro.close()
        return fake_task

    with patch(
        "custom_components.ave_dominaplus.web_server.asyncio.create_task",
        side_effect=_create_task,
    ):
        await server._start_thermostats_fetch_flow()

    server.send_ws_command.assert_awaited_once_with("LM")
    assert server._thermostat_fetch_task is fake_task


async def test_termostats_fetch_flow_sends_lmc_and_wts_when_ready(
    hass: HomeAssistant,
) -> None:
    """Thermostat fetch flow should request area commands and then WTS snapshots."""
    server = _new_server(hass)
    server.send_ws_command = AsyncMock()
    server.ws_conn = SimpleNamespace(closed=False)
    server.ave_map.areas_loaded = True
    server.ave_map.areas = {1: object(), 2: object()}
    server.all_thermostats_raw = {4: {}, 5: {}}
    server._thermostat_lm_done.set()
    server._thermostat_lmc_done.set()

    await server._termostats_fetch_flow()

    server.send_ws_command.assert_any_await("LMC", [1])
    server.send_ws_command.assert_any_await("LMC", [2])
    server.send_ws_command.assert_any_await("WTS", ["4"])
    server.send_ws_command.assert_any_await("WTS", ["5"])


async def test_termostats_fetch_flow_returns_on_lm_timeout(hass: HomeAssistant) -> None:
    """Thermostat fetch flow should abort when LM wait times out."""
    server = _new_server(hass)
    server.send_ws_command = AsyncMock()

    async def _raise_timeout(coro, _timeout):
        coro.close()
        raise TimeoutError

    with patch(
        "custom_components.ave_dominaplus.web_server.asyncio.wait_for",
        new=AsyncMock(side_effect=_raise_timeout),
    ):
        await server._termostats_fetch_flow()

    server.send_ws_command.assert_not_awaited()


async def test_start_returns_immediately_when_already_started(
    hass: HomeAssistant,
) -> None:
    """Start should return early when websocket loop is already started."""
    server = _new_server(hass)
    server.started = True
    server.authenticate = AsyncMock()

    await server.start()

    server.authenticate.assert_not_awaited()
