"""Climate sensor platform for AVE dominaplus integration."""

import logging
from typing import Any

from homeassistant.components.climate import DEFAULT_MAX_TEMP, ClimateEntity
from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .ave_map import AveMapCommand
from .ave_thermostat import AveThermostatProperties
from .const import AVE_FAMILY_THERMOSTAT, BRAND_PREFIX
from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)

PRESET_SCHEDULE = "Schedule"
PRESET_MANUAL = "Manual"


async def async_setup_entry(
    _hass: HomeAssistant | None,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AVE dominaplus thermostats.

    Args:
        _hass: Home Assistant instance.
        entry: Config entry for the integration.
        async_add_entities: Callback to add entities to Home Assistant.

    """
    webserver: AveWebServer = entry.runtime_data
    if not webserver:
        _LOGGER.error("AVE dominaplus: Web server not initialized")
        connection_error = "Can't reach webserver"
        raise ConfigEntryNotReady(connection_error)

    await webserver.set_async_add_th_entities(async_add_entities)
    await webserver.set_update_thermostat(update_thermostat)
    await adopt_existing_sensors(webserver, entry)
    if not webserver.settings.fetch_thermostats:
        return


async def adopt_existing_sensors(server: AveWebServer, entry: ConfigEntry) -> None:
    """Adopt existing sensors from the entity registry."""
    try:
        entity_registry = er.async_get(server.hass)
        if entity_registry is None:
            return
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        for entity in entities:
            if not (entity.platform == "ave_dominaplus" and entity.domain == "climate"):
                continue
            # Check if the sensor is already registered
            if entity.unique_id not in server.thermostats:
                # Create a new sensor instance
                family = int(entity.unique_id.split("_")[3])
                ave_device_id = int(entity.unique_id.split("_")[4])
                name = None
                if entity.name is not None:
                    name = entity.name
                elif entity.original_name is not None:
                    name = entity.original_name
                properties = AveThermostatProperties()
                properties.device_id = ave_device_id
                thermostat = AveThermostat(
                    unique_id=entity.unique_id,
                    family=family,
                    ave_properties=properties,
                    webserver=server,
                    name=name,
                )

                thermostat.hass = server.hass
                thermostat.entity_id = entity.entity_id

                server.thermostats[entity.unique_id] = thermostat
                server.async_add_th_entities([thermostat])
                _LOGGER.info(
                    "Adopted existing thermostat entity with name %s with unique_id %s",
                    thermostat.name,
                    thermostat.unique_id,
                )
    except Exception:
        _LOGGER.exception("Error adopting existing sensors")
        # raise ConfigEntryNotReady("Error adopting existing sensors") from e


def set_sensor_uid(webserver: AveWebServer, family, ave_device_id) -> str:
    """Set the unique ID for the sensor."""
    return f"ave_{webserver.mac_address}_thermostat_{family}_{ave_device_id}"


def update_thermostat(
    server: AveWebServer,
    parameters: list[str],
    records: list[list[str]],
    command: AveMapCommand | None = None,
    properties: AveThermostatProperties | None = None,
    ave_device_id: int | None = None,
) -> None:
    """Update thermostat from WS records."""
    if properties is not None and ave_device_id is not None:
        # Bulk update/set from WTS
        _update_thermostat(
            server=server,
            family=AVE_FAMILY_THERMOSTAT,
            ave_device_id=properties.device_id,
            properties=properties,
        )
    if command is not None:
        # Updates from WTS that uses command ids as identifiers
        match parameters[0]:
            case "TT":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=command.device_id,
                    property_name="temperature",
                    property_value=int(parameters[2]) / 10,
                )
            case "TL":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=command.device_id,
                    property_name="fan_level",
                    property_value=int(parameters[2]),
                )
            case "TLO":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=command.device_id,
                    property_name="local_off",
                    property_value=(1 if int(parameters[2]) == 0 else 0),
                )
            case "TO":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=command.device_id,
                    property_name="offset",
                    property_value=int(parameters[2]),
                )
            case "TS":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=command.device_id,
                    property_name="season",
                    property_value=int(parameters[2]),
                )
    elif parameters[0] == "WT":
        match parameters[1]:
            case "O":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    property_name="offset",
                    property_value=int(parameters[3]) / 10,
                )
            case "S":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    property_name="season",
                    property_value=int(parameters[3]) / 10,
                )
            case "T":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    property_name="temperature",
                    property_value=int(parameters[3]) / 10,
                )
            case "L":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    property_name="fan_level",
                    property_value=int(parameters[3]),
                )
            case "Z":
                _update_thermostat(
                    server=server,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    property_name="local_off",
                    property_value=int(parameters[3]),
                )
    elif parameters[0] == "TM":
        _update_thermostat(
            server=server,
            family=AVE_FAMILY_THERMOSTAT,
            ave_device_id=int(parameters[1]),
            property_name="mode",
            property_value=parameters[2],
        )
    elif parameters[0] == "TW":
        _update_thermostat(
            server=server,
            family=AVE_FAMILY_THERMOSTAT,
            ave_device_id=int(parameters[1]),
            property_name="window_state",
            property_value=parameters[2],
        )
    elif parameters[0] == "TP":
        _update_thermostat(
            server=server,
            family=AVE_FAMILY_THERMOSTAT,
            ave_device_id=int(parameters[1]),
            property_name="set_point",
            property_value=int(parameters[2]) / 10,
        )


def _update_thermostat(
    server: AveWebServer,
    family: int,
    ave_device_id: int,
    properties: AveThermostatProperties | None = None,
    property_name: str | None = None,
    property_value: Any = None,
) -> None:
    """Create or update thermostat based on incoming data from webserver."""

    unique_id = set_sensor_uid(server, family, ave_device_id)
    already_exists = unique_id in server.thermostats
    if already_exists:
        # Update the existing sensor's state
        thermostat: AveThermostat = server.thermostats[unique_id]
        _LOGGER.debug(
            " Updating thermostat %s device_id %s", thermostat.name, ave_device_id
        )

        if properties is not None:
            thermostat.update_all_properties(properties)
            if properties.device_name is not None and server.settings.get_entity_names:
                thermostat.set_ave_name(properties.device_name)
                if not check_name_changed(server.hass, unique_id):
                    thermostat.set_name(properties.device_name)
        elif property_name is not None and property_value is not None:
            thermostat.update_specific_property(property_name, property_value)
    else:
        if properties is None:
            _LOGGER.debug(
                "Received update for thermostat device_id %s "
                "but properties is None; skipping",
                ave_device_id,
            )
            return
        # Create a new thermostat entity
        entity_name = None
        if server.settings.get_entity_names:
            if properties.device_name is None:
                _LOGGER.debug(
                    "Cannot create thermostat entity for device_id %s because device_name is None and get_entity_names is enabled. Waiting for discovery message",
                    ave_device_id,
                )
                return
            entity_name = properties.device_name

        thermostat = AveThermostat(
            unique_id=unique_id,
            family=family,
            ave_properties=properties,
            webserver=server,
            name=entity_name,
        )

        _LOGGER.info("Creating new thermostat entity %s", entity_name)
        server.thermostats[unique_id] = thermostat
        server.async_add_th_entities(
            [thermostat]
        )  # Add the new sensor to Home Assistant


def check_name_changed(hass: HomeAssistant, unique_id: str) -> bool:
    """Check if the name of the sensor has changed."""
    entity_registry = er.async_get(hass)

    entry_id = entity_registry.async_get_entity_id(
        "climate", "ave_dominaplus", unique_id
    )
    if entry_id:
        entity_entry = entity_registry.async_get(entry_id)
        if entity_entry is not None:
            return (
                entity_entry.name is not None
                and entity_entry.original_name != entity_entry.name
            )
    return False


class AveThermostat(ClimateEntity):
    """Representation of a thermostat controller."""

    _attr_should_poll = False

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_fan_modes = [FAN_OFF, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_fan_mode = FAN_OFF
    _attr_hvac_modes = [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
    _attr_hvac_mode = HVACMode.OFF
    _attr_max_temp = DEFAULT_MAX_TEMP
    _attr_preset_modes = [PRESET_MANUAL, PRESET_SCHEDULE]
    _attr_target_temperature_step = PRECISION_TENTHS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "thermostat"
    _attr_name = None
    _away: bool | None = None
    _connected: bool | None = None

    def __init__(
        self,
        unique_id: str,
        family: int,
        ave_properties: AveThermostatProperties,
        webserver: AveWebServer,
        name: str | None = None,
    ) -> None:
        """Initialize the thermostat sensor."""
        self._unique_id = unique_id
        self._attr_unique_id = unique_id
        self.family = family
        self._webserver = webserver
        self.hass = self._webserver.hass
        self.ave_properties: AveThermostatProperties = ave_properties
        self.ave_name = ""
        if name is not None:
            self._name = name
        elif ave_properties.device_name is None:
            self._name = self.build_name()
        else:
            self._name = ave_properties.device_name
            self.ave_name = ave_properties.device_name

        self._selected_schedule = None
        self.update_all_properties(ave_properties, first_update=True)

    def update_from_wts(self, parameters: list[str], records: list[list[str]]):
        """Update the thermostat properties from WTS data."""
        ave_properties = AveThermostatProperties.from_wts(parameters, records)
        _LOGGER.debug(
            "Updating thermostat from WTS data. Parsed properties: %s",
            ave_properties,
        )
        self.update_all_properties(ave_properties)

    def update_all_properties(
        self, properties: AveThermostatProperties, first_update: bool = False
    ):
        """Update all properties of the thermostat."""
        self.ave_properties = properties
        self._attr_current_temperature = self.ave_properties.temperature
        self._attr_target_temperature = self.ave_properties.set_point

        if self.ave_properties.mode in {"1F", "1", "M"}:
            self._attr_preset_mode = PRESET_MANUAL
        else:
            self._attr_preset_mode = PRESET_SCHEDULE

        if str(self.ave_properties.season) == "0":
            self._attr_hvac_mode = HVACMode.COOL
        else:
            self._attr_hvac_mode = HVACMode.HEAT

        if int(self.ave_properties.fan_level) >= 0:
            self.update_from_fan_level(
                int(self.ave_properties.fan_level), first_update=first_update
            )

        if str(self.ave_properties.local_off) == "1":
            self._attr_hvac_mode = HVACMode.OFF

        if not first_update:
            self.async_write_ha_state()

    def update_specific_property(self, property_name: str, value: Any) -> None:
        """Update a specific property of the thermostat."""
        if property_name == "temperature":
            self._attr_current_temperature = value
            self.ave_properties.temperature = value
        elif property_name == "set_point":
            self._attr_target_temperature = value
            self.ave_properties.set_point = value
        elif property_name == "mode":
            if value in {"1F", "1", "M"}:
                self._attr_preset_mode = PRESET_MANUAL
            else:
                self._attr_preset_mode = PRESET_SCHEDULE
            self.ave_properties.mode = value
        elif property_name == "fan_level":
            _fan_level: int = int(value) if value is not None else -1
            self.update_from_fan_level(_fan_level)
        elif property_name == "local_off":
            self.ave_properties.local_off = str(value)
            if self.ave_properties.local_off == "1":
                self._attr_hvac_mode = HVACMode.OFF
            elif str(self.ave_properties.season) == "0":
                self._attr_hvac_mode = HVACMode.COOL
            else:
                self._attr_hvac_mode = HVACMode.HEAT
        elif property_name == "offset":
            # Offset is not directly represented in Home Assistant
            self.ave_properties.offset = value
        elif property_name == "season":
            if value == 0:
                self._attr_hvac_mode = HVACMode.COOL
            elif value == 1:
                self._attr_hvac_mode = HVACMode.HEAT
            self.ave_properties.season = value
        elif property_name == "window_state":
            # Window state is not directly represented in Home Assistant
            pass

        self.async_write_ha_state()

    def update_from_fan_level(self, fan_level: int, first_update: bool = False) -> None:
        """Update the thermostat properties based on the fan level."""
        if fan_level <= 0:
            self._attr_hvac_action = HVACAction.OFF
        elif self._attr_hvac_mode == HVACMode.HEAT:
            self._attr_hvac_action = HVACAction.HEATING
        elif self._attr_hvac_mode == HVACMode.COOL:
            self._attr_hvac_action = HVACAction.COOLING

        match fan_level:
            case 0:
                self._attr_fan_mode = FAN_OFF
            case 1:
                self._attr_fan_mode = FAN_LOW
            case 2:
                self._attr_fan_mode = FAN_MEDIUM
            case 3:
                self._attr_fan_mode = FAN_HIGH

        if not first_update:
            self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        season = None
        season = (
            self.ave_properties.season
            if (
                self.ave_properties.season is not None
                and self.ave_properties.season != ""
            )
            else None
        )
        if season is None:
            _LOGGER.error(
                "Cannot set temperature: season not defined for device_id %s",
                self.ave_properties.device_id,
            )
            return
        temperature = kwargs.get("temperature")
        if temperature is None:
            _LOGGER.error(
                "Cannot set temperature: temperature not provided for device_id %s",
                self.ave_properties.device_id,
            )
            return
        parameters = [str(self.ave_properties.device_id)]
        records = [[season, 1, int(temperature * 10)]]
        if self._webserver:
            await self._webserver.send_thermostat_sts(
                parameters=parameters, records=records
            )

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode.

        Fan mode is readonly in AVE dominaplus thermostats,
        so this method does nothing.
        """
        return

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new target preset mode."""
        season = None
        season = (
            self.ave_properties.season
            if (
                self.ave_properties.season is not None
                and self.ave_properties.season != ""
            )
            else None
        )
        if season is None:
            _LOGGER.error(
                "Cannot set preset mode: season not defined for device_id %s",
                self.ave_properties.device_id,
            )
            return
        if self._attr_target_temperature is None:
            _LOGGER.error(
                "Cannot set preset mode: target temperature not defined for device_id %s",
                self.ave_properties.device_id,
            )
            return
        parameters = [str(self.ave_properties.device_id)]
        _mode = 1 if preset_mode == PRESET_MANUAL else 0
        records = [[season, _mode, int(self._attr_target_temperature * 10)]]
        if self._webserver:
            await self._webserver.send_thermostat_sts(
                parameters=parameters, records=records
            )

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self._webserver.thermostat_on_off(
                device_id=self.ave_properties.device_id, on_off=0
            )
        elif hvac_mode in {HVACMode.HEAT, HVACMode.COOL}:
            if self._attr_target_temperature is None:
                _LOGGER.error(
                    "Cannot set hvac mode: target temperature not defined for device_id %s",
                    self.ave_properties.device_id,
                )
                return
            season = 1 if hvac_mode == HVACMode.HEAT else 0
            parameters = [str(self.ave_properties.device_id)]
            _mode = 1 if self._attr_preset_mode == PRESET_MANUAL else 0
            records = [[season, _mode, int(self._attr_target_temperature * 10)]]
            if self._webserver:
                await self._webserver.send_thermostat_sts(
                    parameters=parameters, records=records
                )

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self._webserver.thermostat_on_off(
            device_id=self.ave_properties.device_id, on_off=1
        )

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self._webserver.thermostat_on_off(
            device_id=self.ave_properties.device_id, on_off=0
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "AVE_family": self.family,
            "AVE_device_id": self.ave_properties.device_id,
            "AVE_name": self.ave_properties.device_name,
            "Temperature offset": self.ave_properties.offset,
            "AVE webserver MAC": self._webserver.mac_address
            if self._webserver
            else None,
        }

    def update_ave_properties(self, properties: AveThermostatProperties) -> None:
        """Update the AVE properties of the thermostat."""
        self.ave_properties = properties
        self.async_write_ha_state()

    def set_ave_name(self, name: str | None) -> None:
        """Set the AVE name of the sensor."""
        if name is not None:
            self.ave_name = name

    def set_name(self, name: str | None) -> None:
        """Set the name of the sensor."""
        if name is None:
            return
        self._name = name
        self.async_write_ha_state()

    def build_name(self) -> str:
        """Build the name of the sensor based on its family and device ID."""
        suffix = "thermostat"
        mac = self._webserver.mac_address if self._webserver else "unknown"
        return f"{BRAND_PREFIX} {mac} {suffix} {self.ave_properties.device_id}"
