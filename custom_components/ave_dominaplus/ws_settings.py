"""Web server settings for AVE Domina Plus integration."""

from types import MappingProxyType
from typing import Any


class AveWebServerSettings:
    """Web server settings class."""

    host: str
    get_entity_names: bool
    fetch_sensor_areas: bool
    fetch_sensors: bool
    fetch_lights: bool
    fetch_covers: bool
    fetch_scenarios: bool
    fetch_thermostats: bool

    def __init__(self) -> None:
        """Initialize the settings."""
        self.host = ""
        self.get_entity_names = True
        self.fetch_sensor_areas = False
        self.fetch_sensors = False
        self.fetch_lights = True
        self.fetch_covers = True
        self.fetch_scenarios = True
        self.fetch_thermostats = True
        self.on_off_lights_as_switch = True

    @staticmethod
    def from_config_entry_options(
        options: MappingProxyType[str, Any],
    ) -> "AveWebServerSettings":
        """Create settings from config entry options."""
        settings = AveWebServerSettings()
        settings.host = options["ip_address"]
        settings.get_entity_names = options.get("get_entities_names", True)
        settings.fetch_sensor_areas = options.get("fetch_sensor_areas", False)
        settings.fetch_sensors = options.get("fetch_sensors", False)
        settings.fetch_lights = options.get("fetch_lights", True)
        settings.fetch_covers = options.get("fetch_covers", True)
        settings.fetch_scenarios = options.get("fetch_scenarios", True)
        settings.fetch_thermostats = options.get("fetch_thermostats", True)
        settings.on_off_lights_as_switch = options.get("on_off_lights_as_switch", True)
        return settings
