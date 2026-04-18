"""Tests for AVE webserver HTTP helper methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from custom_components.ave_dominaplus.web_server import AveWebServer
from homeassistant.core import HomeAssistant


class _FakeResponse:
    """Minimal async context manager response for aiohttp call tests."""

    def __init__(self, status: int, text_value: str) -> None:
        self.status = status
        self._text_value = text_value

    async def text(self) -> str:
        return self._text_value

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    """Minimal async context manager session for aiohttp patching."""

    def __init__(
        self, response: _FakeResponse | None = None, exc: Exception | None = None
    ):
        self._response = response
        self._exc = exc

    def get(self, url, params=None):
        del url, params
        if self._exc is not None:
            raise self._exc
        if self._response is None:
            raise RuntimeError("No fake response configured")
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _new_server(hass: HomeAssistant) -> AveWebServer:
    """Build webserver fixture for HTTP helper tests."""
    settings = {
        "ip_address": "192.168.1.10",
        "get_entities_names": True,
        "fetch_sensor_areas": True,
        "fetch_sensors": True,
        "fetch_lights": True,
        "fetch_covers": True,
        "fetch_thermostats": True,
        "on_off_lights_as_switch": True,
    }
    return AveWebServer(settings, hass)


async def test_call_bridge_returns_data_on_200(hass: HomeAssistant) -> None:
    """Bridge helper should return status and body on successful response."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(200, "ok"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        status, data = await server.call_bridge("LDI")

    assert status == 200
    assert data == "ok"


async def test_call_bridge_returns_none_on_non_200(hass: HomeAssistant) -> None:
    """Bridge helper should return None payload on non-200 responses."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(500, "error"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        status, data = await server.call_bridge("LDI")

    assert status == 500
    assert data is None


async def test_call_bridge_returns_900_on_exception(hass: HomeAssistant) -> None:
    """Bridge helper should return synthetic 900 status on request errors."""
    server = _new_server(hass)
    session = _FakeSession(exc=RuntimeError("network"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        status, data = await server.call_bridge("LDI")

    assert status == 900
    assert data is None


async def test_tryget_mac_address_parses_valid_xml(hass: HomeAssistant) -> None:
    """MAC helper should parse and normalize macaddress from XML body."""
    server = _new_server(hass)
    session = _FakeSession(
        _FakeResponse(200, "<root><macaddress>AA:BB:CC:DD:EE:FF</macaddress></root>")
    )

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        mac = await server.tryget_mac_address()

    assert mac == "aa:bb:cc:dd:ee:ff"


async def test_tryget_mac_address_returns_none_on_missing_tag(
    hass: HomeAssistant,
) -> None:
    """MAC helper should return None when XML has no macaddress tag."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(200, "<root><other>n/a</other></root>"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        mac = await server.tryget_mac_address()

    assert mac is None


async def test_tryget_mac_address_returns_none_on_invalid_xml(
    hass: HomeAssistant,
) -> None:
    """MAC helper should return None on XML parsing errors."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(200, "<broken"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        mac = await server.tryget_mac_address()

    assert mac is None


async def test_tryget_systeminfo_parses_known_keys(hass: HomeAssistant) -> None:
    """System info helper should extract configured XML keys only."""
    server = _new_server(hass)
    xml = """
    <root>
      <os>linux</os>
      <firmware>1.2.3</firmware>
      <cloud>enabled</cloud>
      <unknown>ignored</unknown>
    </root>
    """
    session = _FakeSession(_FakeResponse(200, xml))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        systeminfo = await server.tryget_systeminfo()

    assert systeminfo == {"os": "linux", "firmware": "1.2.3", "cloud": "enabled"}


async def test_tryget_systeminfo_returns_empty_on_invalid_xml(
    hass: HomeAssistant,
) -> None:
    """System info helper should return empty dict on parse errors."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(200, "<broken"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        systeminfo = await server.tryget_systeminfo()

    assert systeminfo == {}


async def test_tryget_systeminfo_returns_empty_on_non_200(hass: HomeAssistant) -> None:
    """System info helper should return empty dict for non-200 responses."""
    server = _new_server(hass)
    session = _FakeSession(_FakeResponse(500, "error"))

    with patch(
        "custom_components.ave_dominaplus.web_server.aiohttp.ClientSession",
        return_value=session,
    ):
        systeminfo = await server.tryget_systeminfo()

    assert systeminfo == {}


async def test_get_device_list_bridge_delegates_to_call_bridge(
    hass: HomeAssistant,
) -> None:
    """Device list helper should delegate to call_bridge with LDI command."""
    server = _new_server(hass)
    server.call_bridge = AsyncMock(return_value=(200, "payload"))

    status, payload = await server.get_device_list_bridge()

    server.call_bridge.assert_awaited_once_with("LDI")
    assert status == 200
    assert payload == "payload"
