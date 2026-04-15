"""Shared pytest fixtures for AVE dominaplus tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ave_dominaplus.const import DOMAIN
from homeassistant.const import CONF_IP_ADDRESS

MOCK_USER_INPUT: dict[str, object] = {
    CONF_IP_ADDRESS: "192.168.1.10",
    "get_entities_names": True,
    "fetch_sensor_areas": True,
    "fetch_sensors": True,
    "fetch_lights": True,
    "fetch_covers": True,
    "fetch_scenarios": True,
    "fetch_thermostats": True,
    "on_off_lights_as_switch": True,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: bool,
) -> None:
    """Enable loading custom integrations in tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a standard config entry for integration setup tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="AVE webserver aa:bb:cc:dd:ee:ff",
        data=MOCK_USER_INPUT,
        unique_id="aa:bb:cc:dd:ee:ff",
    )
