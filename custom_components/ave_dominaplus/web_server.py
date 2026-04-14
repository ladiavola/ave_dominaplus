"""WebSocket connection to the AVE web server."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from defusedxml import ElementTree as DefusedET

from .ave_map import AveMap
from .ave_thermostat import AveThermostatProperties
from .const import (
    AVE_FAMILY_ANTITHEFT,
    AVE_FAMILY_ANTITHEFT_AREA,
    AVE_FAMILY_CAMERA,
    AVE_FAMILY_DIMMER,
    AVE_FAMILY_KEYPAD,
    AVE_FAMILY_MOTION_SENSOR,
    AVE_FAMILY_ONOFFLIGHTS,
    AVE_FAMILY_SCENARIO,
    AVE_FAMILY_SHUTTER_HUNG,
    AVE_FAMILY_SHUTTER_ROLLING,
    AVE_FAMILY_SHUTTER_SLIDING,
    AVE_FAMILY_THERMOSTAT,
)

if TYPE_CHECKING:
    from types import MappingProxyType

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class AveWebServerSettings:
    """AVE web server settings class."""

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
        self.get_entity_names = False
        self.fetch_sensor_areas = False
        self.fetch_sensors = False
        self.fetch_lights = False
        self.fetch_covers = False
        self.fetch_scenarios = False
        self.fetch_thermostats = False
        self.onOffLightsAsSwitch = True


class AveWebServer:
    """AVE web server class."""

    def __init__(
        self,
        settings_data: MappingProxyType[str, Any],
        hass: HomeAssistant,
    ) -> None:
        """Initialize."""
        self.settings = AveWebServerSettings()
        try:
            self.settings = AveWebServerSettings()
            self.settings.host = settings_data["ip_address"]
            self.settings.get_entity_names = settings_data["get_entities_names"]
            self.settings.fetch_sensor_areas = settings_data["fetch_sensor_areas"]
            self.settings.fetch_sensors = settings_data["fetch_sensors"]
            self.settings.fetch_lights = settings_data["fetch_lights"]
            self.settings.fetch_covers = settings_data.get("fetch_covers", True)
            self.settings.fetch_thermostats = settings_data["fetch_thermostats"]
            self.settings.onOffLightsAsSwitch = settings_data.get(
                "onOffLightsAsSwitch", True
            )
        except KeyError:
            _LOGGER.exception("Missing key in settings data")
        self.mac_address = ""
        self.systeminfo: dict[str, str] = {}
        self.hass = hass
        self._ws_session: aiohttp.ClientSession | None = None
        self.ws_conn: Any = None
        self._connected = False
        self._has_connected_once = False
        self._logged_unavailable = False
        self._availability_entities: set[Any] = set()
        self.device_list: list[Any] = []
        self.wtstask: asyncio.Task
        self.started = False
        self.closed = False
        self.raw_ldi: list[Any] = []
        self.binary_sensors: dict = {}  # Track binary sensors by unique ID
        self.update_binary_sensor: Any = None
        self.async_add_bs_entities: Any = None
        self.switches: dict = {}  # Track switches by unique ID
        self.async_add_sw_entities: Any = None
        self.update_switch: Any = None
        self.lights: dict = {}  # Track dimmer lights by unique ID
        self.async_add_lg_entities: Any = None
        self.update_light: Any = None
        self.covers: dict = {}  # Track covers by unique ID
        self.async_add_cv_entities: Any = None
        self.update_cover: Any = None
        self.thermostats: dict = {}  # Track thermostats by ID
        self.all_thermostats_raw: dict = {}  # Track thermostats that are not on the map by device ID
        self.async_add_th_entities: Any = None
        self.update_thermostat: Any = None
        self.ave_map: AveMap = AveMap()
        self._ldi_done = asyncio.Event()
        self._thermostat_lm_done = asyncio.Event()
        self._thermostat_lmc_done = asyncio.Event()
        self._connect_actions_task: asyncio.Task | None = None
        self._thermostat_fetch_task: asyncio.Task | None = None
        self.numbers: dict = {}  # Track number entities by unique ID
        self.async_add_number_entities: Any = None
        self.update_th_offset: Any = None

    async def set_update_binary_sensor(self, func) -> None:
        """Set the set_update_binary_sensor method for binary sensors."""
        self.update_binary_sensor = func

    async def set_update_switch(self, func) -> None:
        """Set the set_update_switch method for switches."""
        self.update_switch = func

    async def set_update_light(self, func) -> None:
        """Set the set_update_light method for dimmer lights."""
        self.update_light = func

    async def set_update_cover(self, func) -> None:
        """Set the set_update_cover method for covers."""
        self.update_cover = func

    async def set_update_thermostat(self, func) -> None:
        """Set the set_update_thermostat method for thermostats."""
        self.update_thermostat = func

    async def set_async_add_bs_entities(self, func) -> None:
        """Set the async_add_entities method for binary sensors."""
        if self.async_add_bs_entities is None:
            self.async_add_bs_entities = func

    async def set_async_add_sw_entities(self, func) -> None:
        """Set the async_add_entities method for switches."""
        if self.async_add_sw_entities is None:
            self.async_add_sw_entities = func

    async def set_async_add_lg_entities(self, func) -> None:
        """Set the async_add_entities method for dimmer lights."""
        if self.async_add_lg_entities is None:
            self.async_add_lg_entities = func

    async def set_async_add_cv_entities(self, func) -> None:
        """Set the async_add_entities method for covers."""
        if self.async_add_cv_entities is None:
            self.async_add_cv_entities = func

    async def set_async_add_th_entities(self, func) -> None:
        """Set the async_add_entities method for thermostats."""
        if self.async_add_th_entities is None:
            self.async_add_th_entities = func

    async def set_async_add_number_entities(self, func) -> None:
        """Set the async_add_entities method for number entities."""
        if self.async_add_number_entities is None:
            self.async_add_number_entities = func

    async def set_update_th_offset(self, func) -> None:
        """Set the method to add/update thermostat offset number entities."""
        if self.update_th_offset is None:
            self.update_th_offset = func

    async def is_connected(self) -> bool:
        """Return if the web server is connected."""
        return self._connected

    @property
    def connected(self) -> bool:
        """Return if the web server is connected (sync property)."""
        return self._connected

    def _iter_connection_entities(self):
        """Iterate all runtime entities that should refresh availability."""
        seen: set[int] = set()

        for entity in self._availability_entities:
            entity_id = id(entity)
            if entity_id in seen:
                continue
            seen.add(entity_id)
            yield entity

        for collection in (
            self.binary_sensors,
            self.switches,
            self.lights,
            self.covers,
            self.thermostats,
            self.numbers,
        ):
            for entity in collection.values():
                entity_id = id(entity)
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                yield entity

    def register_availability_entity(self, entity: Any) -> None:
        """Register an entity for connectivity-driven availability updates."""
        self._availability_entities.add(entity)

    def unregister_availability_entity(self, entity: Any) -> None:
        """Unregister an entity for connectivity-driven availability updates."""
        self._availability_entities.discard(entity)

    def _notify_connection_state_changed(self) -> None:
        """Force entity state refresh when connectivity changes."""
        for entity in self._iter_connection_entities():
            if getattr(entity, "hass", None) is None:
                continue
            if getattr(entity, "entity_id", None) is None:
                continue
            try:
                entity.async_write_ha_state()
            except RuntimeError:
                _LOGGER.debug(
                    "Skipping availability refresh for entity %s due to runtime state",
                    entity,
                    exc_info=True,
                )

    def _set_connected(self, connected: bool, *, log_transition: bool = True) -> None:
        """Update connection flag and log only on edge transitions."""
        if self._connected == connected:
            return

        self._connected = connected

        if connected:
            self._has_connected_once = True
            if log_transition and self._logged_unavailable:
                _LOGGER.info(
                    "Connection to AVE web server restored",
                    extra={"host": self.settings.host},
                )
                self._logged_unavailable = False
        elif (
            log_transition and self._has_connected_once and not self._logged_unavailable
        ):
            _LOGGER.warning(
                "Connection to AVE web server unavailable",
                extra={"host": self.settings.host},
            )
            self._logged_unavailable = True

        self._notify_connection_state_changed()

    async def authenticate(self) -> bool:
        """Authenticate with the WebSocket server."""
        try:
            if self._ws_session is None or self._ws_session.closed:
                self._ws_session = aiohttp.ClientSession()

            self.ws_conn = await self._ws_session.ws_connect(
                f"ws://{self.settings.host}:14001",
                protocols=["binary"],
                heartbeat=15,
            )
            self._set_connected(True)
            self.mac_address = await self.tryget_mac_address()
            self.systeminfo = await self.tryget_systeminfo()
            _LOGGER.debug("Connected to WebSocket server at %s", self.settings.host)
        except aiohttp.ClientError as err:
            self._set_connected(False)
            if self.ws_conn:
                with suppress(Exception):
                    await self.ws_conn.close()
                self.ws_conn = None
            if self._ws_session and not self._ws_session.closed:
                with suppress(Exception):
                    await self._ws_session.close()
            self._ws_session = None
            _LOGGER.debug(
                "Failed to connect to WebSocket server at %s: %s",
                self.settings.host,
                err,
            )
            return False
        except Exception:
            self._set_connected(False)
            if self.ws_conn:
                with suppress(Exception):
                    await self.ws_conn.close()
                self.ws_conn = None
            if self._ws_session and not self._ws_session.closed:
                with suppress(Exception):
                    await self._ws_session.close()
            self._ws_session = None
            _LOGGER.exception("Unexpected error while connecting to WebSocket server")
            return False
        return True

    async def disconnect(self) -> None:
        """Disconnect from the web server."""
        self.closed = True
        if self._connect_actions_task and not self._connect_actions_task.done():
            self._connect_actions_task.cancel()
            self._connect_actions_task = None
        if self._thermostat_fetch_task and not self._thermostat_fetch_task.done():
            self._thermostat_fetch_task.cancel()
            self._thermostat_fetch_task = None
        if self.ws_conn:
            await self.ws_conn.close()
            self.ws_conn = None
            _LOGGER.info("WebSocket disconnected!", extra={"host": self.settings.host})
        if self._ws_session and not self._ws_session.closed:
            await self._ws_session.close()
        self._ws_session = None
        self._set_connected(False, log_transition=False)

    async def start(self) -> None:
        """Start the WebSocket connection and listen for messages."""
        if self.started:
            _LOGGER.debug("WebSocket connection already started")
            return

        self.started = True
        _LOGGER.debug("Starting WebSocket connection")

        while not self.closed:
            try:
                if not self._connected or self.ws_conn is None or self.ws_conn.closed:
                    _LOGGER.debug("Attempting to connect to WebSocket server")
                    if not await self.authenticate():
                        await asyncio.sleep(5)
                        continue

                if self.started:
                    self._connect_actions_task = asyncio.create_task(
                        self.on_connect_actions()
                    )

                async for msg in self.ws_conn:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        await self.on_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        _LOGGER.debug("WebSocket error", extra={"error": msg.data})
                        break

                self._set_connected(False)

            except Exception:
                _LOGGER.exception("WebSocket connection error")
                self._set_connected(False)
                await asyncio.sleep(5)  # Retry after a delay

        _LOGGER.debug("WebSocket connection stopped")

    async def on_connect_actions(self) -> None:
        """Actions to perform after connecting to the web server."""
        if self.ws_conn is None or self.ws_conn.closed:
            return

        self._ldi_done.clear()
        # await self.send_ws_command("LDI")  # Get device list (legacy)
        await self.send_ws_command("LI2")  # Get device list (with addresses)
        if not await self._wait_for_ldi():
            return

        if self.settings.fetch_lights:
            # Get status by family type 1 (switches) and 2 (dimmers)
            await self.send_ws_command("GSF", [str(AVE_FAMILY_ONOFFLIGHTS)])
            await self.send_ws_command("GSF", [str(AVE_FAMILY_DIMMER)])

        if self.settings.fetch_covers:
            await self.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_ROLLING)])
            await self.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_SLIDING)])
            await self.send_ws_command("GSF", [str(AVE_FAMILY_SHUTTER_HUNG)])

        # Get status by family type 12 (motion detection areas)
        if self.settings.fetch_sensor_areas:
            await self.send_ws_command("GSF", [str(AVE_FAMILY_ANTITHEFT_AREA)])
            await self.send_ws_command("WSF", [str(AVE_FAMILY_ANTITHEFT_AREA)])

        if self.settings.fetch_thermostats:
            await self._start_thermostats_fetch_flow()

        await self.send_ws_command("SU3")  # Start streaming updates (most of them)

        # Starts streaming some other updates (UPD for TLO and XU, NET and CLD)
        # await self.send_ws_command("SU2")

    async def _start_thermostats_fetch_flow(self) -> None:
        """Start thermostat bootstrap flow without blocking message handling."""

        """Some thermostats updates come with mapCommandId as a reference instead of device ID
        so we need to fetch the map and commands to be able to link thermostats to their device ID and get their names if the setting is enabled.
        """
        self.ave_map = AveMap()
        self._thermostat_lm_done.clear()
        self._thermostat_lmc_done.clear()

        if self._thermostat_fetch_task and not self._thermostat_fetch_task.done():
            self._thermostat_fetch_task.cancel()

        await self.send_ws_command("LM")
        self._thermostat_fetch_task = asyncio.create_task(self._termostats_fetch_flow())

    async def _wait_for_ldi(self) -> bool:
        """Wait for at least one LDI response before thermostat bootstrap."""
        try:
            await asyncio.wait_for(self._ldi_done.wait(), 15.0)
        except TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for LDI response; skipping thermostat bootstrap"
            )
            return False
        return True

    async def _termostats_fetch_flow(self) -> None:
        # 1) wait until LM responses are received and the map is loaded
        try:
            await asyncio.wait_for(self._thermostat_lm_done.wait(), 15.0)
        except TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for LM responses; skipping thermostat map"
            )
            return

        # 2) send LMC for each area once the LM map is loaded
        if self.ave_map.areas_loaded and self.ws_conn and not self.ws_conn.closed:
            if not self.ave_map.areas:
                _LOGGER.debug("LM map returned no areas")
                return
            for map_id in self.ave_map.areas:
                await self.send_ws_command("LMC", [map_id])
        else:
            _LOGGER.debug("Map not loaded or ws disconnected; skipping LMC send")
            return

        # 3) wait for all LMC responses (commands loaded)
        try:
            await asyncio.wait_for(self._thermostat_lmc_done.wait(), 15.0)
        except TimeoutError:
            _LOGGER.warning("Timed out waiting for LMC responses; proceeding")

        # 4) request thermostat status snapshots
        for device_id in self.all_thermostats_raw:
            await self.send_ws_command("WTS", [str(device_id)])

    def value_to_hex(self, value):
        """Return the hexadecimal value of a number."""
        return hex(value)[2:].upper()

    async def build_crc(self, rawstring):
        """Build CRC for the given string."""
        crc = 0
        for char in rawstring:
            crc ^= ord(char)
        crc = 0xFF - crc
        msb = self.value_to_hex(crc >> 4)
        lsb = self.value_to_hex(crc & 0xF)
        return msb + lsb

    async def on_message(self, message) -> None:
        """Handle incoming messages from the web server."""
        # _LOGGER.debug("Received message: %s", message)
        try:
            # Ensure the message is decoded if it's in bytes
            if isinstance(message, bytes):
                message = message.decode("utf-8")  # Decode bytes to string using UTF-8
            # log_with_timestamp(message)
            messages = message.split(chr(0x04))
            for msg in messages:
                if len(msg) < 3:
                    continue
                str_msg = msg[1:-3]
                cmd_params, *records_data = str_msg.split(chr(0x1E))
                command, *parameters = cmd_params.split(chr(0x1D))
                records = [record.split(chr(0x1D)) for record in records_data]
                await self.manage_incoming_messages_messages(
                    command, parameters, records
                )
        except Exception:
            _LOGGER.exception("Error processing message")

    async def send_ws_command(
        self,
        command: str,
        parameters: list[Any] | None = None,
        records: list[list[Any]] | None = None,
    ) -> None:
        """Send a command to the web server."""
        message = chr(0x02) + command
        payload = ""
        if parameters is not None:
            payload += chr(0x1D)
            if isinstance(parameters, (list, tuple)):
                pieces = [str(item) for item in parameters]
            else:
                pieces = str(parameters).split(",")
            payload += chr(0x1D).join(pieces)
        if records is not None:
            if not isinstance(records, (list, tuple)):
                records = str(records).split(",")
            for record in records:  # pyright: ignore[reportOptionalIterable]
                payload += chr(0x1E)
                if isinstance(record, (list, tuple)):
                    record_string = ",".join(str(item) for item in record)
                else:
                    record_string = str(record)
                pieces = record_string.split(",")
                payload += chr(0x1D).join(pieces)
        message += payload
        message += chr(0x03)
        crc = await self.build_crc(message)
        full_message = message + crc + chr(0x04)
        if not self.ws_conn or self.ws_conn.closed:
            _LOGGER.debug(
                "Skipping command %s because WebSocket is not connected", command
            )
            return

        try:
            await self.ws_conn.send_str(full_message)
        except Exception:
            self._set_connected(False)
            _LOGGER.debug(
                "Failed to send command %s because WebSocket is not connected",
                command,
                exc_info=True,
            )
            return

        escaped_message = full_message.encode("unicode_escape").decode("ascii")
        _LOGGER.debug("Sent command: %s", escaped_message)

    async def manage_incoming_messages_messages(
        self, command: str, parameters: list[Any], records: list[list[Any]]
    ) -> None:
        """Manage commands received from the web server."""
        if command == "pong":
            pass
        elif command == "ack":
            _LOGGER.debug("Received ACK for command: %s", parameters[0])
        elif command == "ping":
            await self.send_ws_command("PONG")
        elif command == "gsf":
            self.manage_gsf(parameters, records)
        elif command == "upd":
            self.manage_upd(parameters, records)
        elif command in {"ldi", "li2"}:
            self.manage_ldi_li2(parameters, records, command)
        elif command == "lm":
            self.manage_lm(parameters, records)
        elif command == "lmc":
            self.manage_lmc(parameters, records)
        elif command == "wts":
            self.manage_wts(parameters, records)
        elif command == "cld":
            # cloud commands received from SU2
            pass
        elif command == "net":
            # IOT commands received from SU2
            pass
        elif command == "nack":
            _LOGGER.warning(
                "Received NACK for command: %s",
                parameters[0] if len(parameters) > 0 else "Unknown",
            )
        else:
            _LOGGER.warning(
                "Received unknown command %s",
                command,
                extra={
                    "command": command,
                    "parameters": parameters,
                    "records": records,
                },
            )

    def manage_upd(self, parameters, records) -> None:
        """Manage UPD commands received from the web server."""
        _LOGGER.debug(
            "Received UPD command. Parameters: %s | Records: %s",
            parameters,
            records,
        )
        if parameters[0] == "WS":
            device_type, device_id, device_status = (
                int(parameters[1]),
                int(parameters[2]),
                int(parameters[3]),
            )
            if device_id > 200000:
                # Devices with ID > 2000000 must be scenarios or something...
                pass
            elif device_type == AVE_FAMILY_ONOFFLIGHTS and self.settings.fetch_lights:
                if self.settings.onOffLightsAsSwitch:
                    self.update_switch(
                        self, device_type, device_id, device_status, None
                    )
                else:
                    self.update_light(self, device_type, device_id, device_status, None)
            elif device_type == AVE_FAMILY_DIMMER and self.settings.fetch_lights:
                self.update_light(self, device_type, device_id, device_status, None)
            elif (
                device_type
                in (
                    AVE_FAMILY_SHUTTER_ROLLING,
                    AVE_FAMILY_SHUTTER_SLIDING,
                    AVE_FAMILY_SHUTTER_HUNG,
                )
                and self.settings.fetch_covers
            ):
                self.update_cover(self, device_type, device_id, device_status, None)
            # elif device_type in [12, 13]:
            #     _LOGGER.debug(
            #         "Received async Antitheft status update. "
            #         "Device ID: %s, Device Type: %s, Status: %s",
            #         device_id,
            #         device_type,
            #         device_status,
            #     )
            # else:
            # if device_type in [1, 2, 22, 9, 3, 16, 19, 6]:
            #     """Limited to [Lighting / Energy / Shutters / Scenarios]
            #     for security reasons"""
            #     pass
        elif parameters[0] == "X" and parameters[1] == "A":  # ANTITHEFT AREA
            if not self.settings.fetch_sensor_areas:
                return

            """parameters[2] is the area ID.
            all other parameters are == 0 when triggered,
            parameters[6] == 1 when cleared"""

            area_progressive = int(parameters[2])
            # area_engaged = int(parameters[3])
            # area_in_alarm = int(parameters[5])
            area_clear = int(parameters[6])
            status = 1
            if area_clear > 0:
                status = 0
            self.update_binary_sensor(
                self, AVE_FAMILY_ANTITHEFT_AREA, area_progressive, status
            )
            # f"XA - areaID: {area_progressive}
            # - engaged: {area_engaged}
            # - clear: {area_clear}
            # - alarm: {area_in_alarm}")
        elif parameters[0] == "X" and parameters[1] == "S":  # ANTITHEFT SENSOR
            if not self.settings.fetch_sensors:
                return
            self.update_binary_sensor(
                self, AVE_FAMILY_MOTION_SENSOR, int(parameters[2]), int(parameters[4])
            )
        elif parameters[0] == "X" and parameters[1] == "U":
            # ANTITHEFT UNIT (requires SU2)
            _LOGGER.debug("XU Antitheft Unit - engaged", extra={"id": parameters[2]})
        elif parameters[0] == "X" and parameters[1] == "A":
            # ANTITHEFT AREA (not handled yed)
            pass
        elif parameters[0] == "WT":
            # Serveral updates for thermostats, using Device ID as identifier
            if parameters[1] == "O":
                self.update_thermostat(
                    server=self,
                    parameters=parameters,
                    records=records,
                    command=None,
                    properties=None,
                    ave_device_id=None,
                )
                self.update_th_offset(
                    server=self,
                    family=AVE_FAMILY_THERMOSTAT,
                    ave_device_id=int(parameters[2]),
                    offset_value=int(parameters[3]) / 10,
                )
        elif parameters[0] in ["TM", "TW", "TP"]:
            # Thermostats update with device ID as identifier
            self.update_thermostat(
                server=self,
                parameters=parameters,
                records=records,
                command=None,
                properties=None,
                ave_device_id=None,
            )
        elif parameters[0] in ["TT", "TR", "TL", "TLO", "TO", "TS"]:
            # THERMOSTAT updates with command ID as identifier
            if (
                not self.ave_map
                or not self.ave_map.areas_loaded
                or not self.ave_map.command_loaded
            ):
                _LOGGER.debug("Received th update before map/commands loaded; skipping")
                return
            _command = self.ave_map.get_command_by_id_and_family(
                int(parameters[1]), AVE_FAMILY_THERMOSTAT
            )
            if not _command:
                _LOGGER.debug(
                    "Received th update for unknown command ID %s; skipping",
                    parameters[1],
                )
                return
            self.update_thermostat(
                server=self,
                parameters=parameters,
                records=records,
                command=_command,
                properties=None,
                ave_device_id=None,
            )
        elif parameters[0] in ["GUI", "D"]:
            # Reload gui or update icon
            pass
        elif parameters[0] in [
            "HO",
            "VMM",
            "TAF",
            "TK",
            "UMI",
            "S",
            "VI",
            "A",
            "CS1",
            "CS2",
            "CS3",
            "abl",
            "LL",
            "SRE",
            "STO",
            "RGB",
            "grp",
            "epv",
            "htl",
        ]:
            """
            Not handled known updates
            HO: fot TS1 devices
            WMM: daikin mode
            TAF: thermostat anti freezing
            TK: themrostat keyboard lock
            UMI: humidity probe
            S: tutondo
            VI: vivaldi
            A , CS1, CS2, CS3: alarm
            abl: abano
            LL: label update
            SRE, STO: alarm silence
            RGB : colorwheel update
            grp: group dimmer?
            epv: economizer values
            htl: hotel
            """
        else:
            _LOGGER.debug(
                "Received not unknown UPD %s",
                parameters[0],
                extra={"parameters": parameters},
            )

    def manage_gsf(self, parameters: list[Any], records: list[list[Any]]) -> None:
        """Manage GSF Get Status by Family responses."""
        _LOGGER.debug(
            "Received GSF (Get status by family) response for family %s, parameters: %s | records: %s",
            parameters[0],
            parameters,
            records,
        )
        if parameters[0] in [
            str(AVE_FAMILY_ANTITHEFT),
            str(AVE_FAMILY_ANTITHEFT_AREA),
        ]:  # Motion detection types
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                self.update_binary_sensor(
                    self, int(parameters[0]), device_id, device_status
                )

        if parameters[0] == str(AVE_FAMILY_ONOFFLIGHTS):
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                if self.settings.onOffLightsAsSwitch:
                    self.update_switch(
                        self, AVE_FAMILY_ONOFFLIGHTS, device_id, device_status, None
                    )
                else:
                    self.update_light(
                        self, AVE_FAMILY_ONOFFLIGHTS, device_id, device_status, None
                    )
                # send_mqtt_message(device_id, device_status)

        if parameters[0] == str(AVE_FAMILY_DIMMER):
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                if self.update_light is not None:
                    self.update_light(
                        self, AVE_FAMILY_DIMMER, device_id, device_status, None
                    )

        if parameters[0] in [
            str(AVE_FAMILY_SHUTTER_ROLLING),
            str(AVE_FAMILY_SHUTTER_SLIDING),
            str(AVE_FAMILY_SHUTTER_HUNG),
        ]:
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                if self.update_cover is not None:
                    self.update_cover(
                        self,
                        int(parameters[0]),
                        device_id,
                        device_status,
                        None,
                    )

    def manage_ldi_li2(
        self, parameters: list[Any], records: list[list[Any]], command: str
    ) -> None:
        """Manage LDI/LI2 List Devices commands received from the web server."""
        _LOGGER.debug(
            "Parsing %s (List Devices) command, parameters: %s | records: %s",
            command,
            parameters,
            records,
        )
        self.raw_ldi = []
        for record in records:
            try:
                device_id, device_name, device_type, address = (
                    int(record[0]),
                    str(record[1]),
                    int(record[2]),
                    record[3],
                )
                # record[3] contains the decimal representation of the address
                address_dec = None
                address_hex = None
                if command == "li2":
                    try:
                        address_dec = int(str(address).strip())
                    except Exception:
                        _LOGGER.debug(
                            "Failed parsing address '%s'; leaving address_dec unset",
                            address,
                        )
                        address_dec = None
                    # Store address as two-digit uppercase hex string when available
                    address_hex = (
                        format(address_dec & 0xFF, "02X")
                        if address_dec is not None
                        else ""
                    )
                self.raw_ldi.append(
                    {
                        "device_id": device_id,
                        "device_name": device_name,
                        "device_type": device_type,
                        "address_dec": address_dec,
                        "address_hex": address_hex,
                    }
                )
                if device_name and device_name[0] == "$":
                    # RGBW, unhandled
                    continue
                if device_name and device_name[-1] == "$":
                    # DALI, unhandled
                    continue
                if device_type == AVE_FAMILY_ANTITHEFT_AREA:
                    # Antitheft area
                    self.update_binary_sensor(
                        self, AVE_FAMILY_ANTITHEFT_AREA, device_id, -1, device_name
                    )
                elif device_type == AVE_FAMILY_KEYPAD:
                    # Keypad
                    pass
                elif device_type == AVE_FAMILY_ONOFFLIGHTS:
                    if self.settings.onOffLightsAsSwitch:
                        self.update_switch(
                            self,
                            AVE_FAMILY_ONOFFLIGHTS,
                            device_id,
                            -1,
                            device_name,
                            address_dec,
                        )
                    else:
                        self.update_light(
                            self,
                            AVE_FAMILY_ONOFFLIGHTS,
                            device_id,
                            -1,
                            device_name,
                            address_dec,
                        )
                    # Light
                elif device_type == AVE_FAMILY_DIMMER:
                    self.update_light(
                        self,
                        AVE_FAMILY_DIMMER,
                        device_id,
                        -1,
                        device_name,
                        address_dec,
                    )
                    # Dimmer light
                elif device_type in (
                    AVE_FAMILY_SHUTTER_ROLLING,
                    AVE_FAMILY_SHUTTER_SLIDING,
                    AVE_FAMILY_SHUTTER_HUNG,
                ):
                    self.update_cover(
                        self,
                        device_type,
                        device_id,
                        -1,
                        device_name,
                        address_dec,
                    )
                elif device_type == AVE_FAMILY_THERMOSTAT:
                    # All thermostats
                    self.all_thermostats_raw[device_id] = {
                        "device_name": device_name,
                        "address_dec": address_dec,
                        "address_hex": address_hex,
                    }
                elif device_type == AVE_FAMILY_SCENARIO:
                    # Scenario
                    pass
                elif device_type == AVE_FAMILY_CAMERA:
                    # Camera
                    pass
                else:
                    _LOGGER.debug(
                        "Unknown device type %s for %s, skipping",
                        device_type,
                        device_name,
                    )
                    continue
            except Exception:
                _LOGGER.exception("Error parsing device record: %s", record)
        self._ldi_done.set()

    def manage_lm(self, parameters, records) -> None:
        """Manage LM List Map commands received from the web server."""
        _LOGGER.debug(
            "Parsing LM (List Map) command, parameters: %s | records: %s",
            parameters,
            records,
        )
        self.ave_map.load_areas_from_wsrecords(records)
        self.ave_map.areas_loaded = True
        self._thermostat_lm_done.set()

    def manage_lmc(self, parameters, records) -> None:
        """Manage LMC List Map Commands responses."""
        _LOGGER.debug(
            "Parsing LMC response, parameters: %s | records: %s",
            parameters,
            records,
        )
        area_id = int(parameters[0])
        self.ave_map.load_area_commands(area_id, records)
        if self.ave_map.command_loaded:
            self._thermostat_lmc_done.set()

    def manage_wts(self, parameters: list[Any], records: list[list[Any]]) -> None:
        """Manage WTS command responses."""
        _LOGGER.debug(
            "Parsing WTS response, parameters: %s | records: %s",
            parameters,
            records,
        )
        device_id = int(parameters[0])
        thermostat_properties = AveThermostatProperties.from_wts(parameters, records)
        thermostat_properties.device_name = (
            f"thermostat_{thermostat_properties.device_id}"
        )
        if self.settings.get_entity_names:
            thermostat_properties.device_name = self.all_thermostats_raw[device_id][
                "device_name"
            ]

        self.update_thermostat(
            server=self,
            parameters=parameters,
            records=records,
            command=None,
            properties=thermostat_properties,
            ave_device_id=device_id,
            address_dec=self.all_thermostats_raw[device_id].get("address_dec"),
        )
        if thermostat_properties.offset is not None:
            self.update_th_offset(
                server=self,
                family=AVE_FAMILY_THERMOSTAT,
                ave_device_id=device_id,
                offset_value=thermostat_properties.offset,
                name=thermostat_properties.device_name,
                address_dec=self.all_thermostats_raw[device_id].get("address_dec"),
            )

    async def switch_turn_on(self, device_id: int) -> None:
        """Turn on the switch."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "11"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def switch_turn_off(self, device_id: int) -> None:
        """Turn off the switch."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "12"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def switch_toggle(self, device_id: int) -> None:
        """Toggle the switch."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "10"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def dimmer_turn_on(self, device_id: int, brightness_ave: int) -> None:
        """Turn on the dimmer."""
        clamped_level = max(0, min(31, int(brightness_ave)))
        if clamped_level == 0:
            await self.dimmer_turn_off(device_id)
            return

        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "3"])
            await self.send_ws_command("SIL", [str(device_id)], [[clamped_level]])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def dimmer_turn_off(self, device_id: int) -> None:
        """Turn off the dimmer."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "4"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def dimmer_toggle(self, device_id: int) -> None:
        """Toggle the dimmer."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EBI", [str(device_id), "2"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def cover_open(self, device_id: int) -> None:
        """Open the cover."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EAI", [str(device_id), "8"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def cover_close(self, device_id: int) -> None:
        """Close the cover."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EAI", [str(device_id), "9"])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def cover_stop(self, device_id: int, command: str) -> None:
        """Stop the cover according to AVE movement direction command."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("EAI", [str(device_id), command])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def send_thermostat_sts(
        self, parameters: list[Any], records: list[list[Any]]
    ) -> None:
        """Send a command to update the thermostat season/temperatures."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("STS", parameters, records)
        else:
            _LOGGER.error("WebSocket is not connected")

    async def thermostat_on_off(self, device_id: int, on_off: int) -> None:
        """Turn the thermostat on or off."""
        if self.ws_conn and not self.ws_conn.closed:
            await self.send_ws_command("TOO", [str(device_id), str(on_off)])
        else:
            _LOGGER.error("WebSocket is not connected")

    async def call_bridge(self, command: str) -> tuple[int, str | None]:
        """Call a xml "rest" bridge for common commands."""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"http://{self.settings.host}/bridge.php"
                params = {"command": command}
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.text()
                        _LOGGER.debug("Bridge response: %s", data)
                        return response.status, data
                    _LOGGER.error("Failed to call bridge. Status: %s", response.status)
                    return response.status, None
            except Exception:
                _LOGGER.exception("Error calling bridge")
                return 900, None

    async def tryget_mac_address(self) -> str | None:
        """Try to get the MAC address of the webserver."""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"http://{self.settings.host}/revealcode.php"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.text()
                        # _LOGGER.debug("revealcode response: %s", data)

                        try:
                            root = DefusedET.fromstring(data)
                            xml_mac = root.findtext("macaddress")
                            if xml_mac:
                                return xml_mac.strip().lower()
                        except DefusedET.ParseError:
                            _LOGGER.exception("Invalid XML in revealcode response")
                        _LOGGER.warning(
                            "No macaddress tag found in revealcode response"
                        )
                        return None
                    _LOGGER.error(
                        "Failed to get WebServer MAC address. Status: %s",
                        response.status,
                    )
                    return None
            except Exception:
                _LOGGER.exception("Error getting WebServer MAC ADDRESS")
                return None

    async def tryget_systeminfo(self) -> dict[str, str]:
        """Try to get selected system information from the webserver."""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"http://{self.settings.host}/systeminfo.php"
                async with session.get(url) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to get WebServer system info. Status: %s",
                            response.status,
                        )
                        return {}

                    data = await response.text()
                    try:
                        root = DefusedET.fromstring(data)
                    except DefusedET.ParseError:
                        _LOGGER.exception("Invalid XML in systeminfo response")
                        return {}

                    keys = [
                        "remotesupport",
                        "os",
                        "app",
                        "launcher",
                        "DPServer",
                        "DPClient",
                        "firmware",
                        "cloud",
                        "iot",
                    ]

                    systeminfo: dict[str, str] = {}
                    for key in keys:
                        element = root.find(key)
                        if element is not None and element.text is not None:
                            systeminfo[key] = element.text.strip()

                    return systeminfo
            except Exception:
                _LOGGER.exception("Error getting WebServer system info")
                return {}

    async def get_device_list_bridge(self) -> tuple[int, str | None]:
        """Get the device list from the bridge."""
        return await self.call_bridge("LDI")
