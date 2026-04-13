"""Light platform for AVE dominaplus integration."""

import logging
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import AVE_FAMILY_DIMMER, BRAND_PREFIX
from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


def parse_uid(unique_id: str) -> tuple[str | None, int, int, int | None] | None:
    """Parse mac, family, device_id and optional address_dec from a light unique_id."""
    parts = unique_id.split("_")
    try:
        family_idx = parts.index("family")
    except ValueError:
        return None

    if len(parts) <= family_idx + 2:
        return None

    mac_address = "_".join(parts[1:family_idx]).strip() or None

    family = int(parts[family_idx + 1])
    ave_device_id = int(parts[family_idx + 2])

    address_dec = None
    if len(parts) > family_idx + 3:
        address_raw = parts[family_idx + 3].strip()
        if address_raw:
            if address_raw.lower().startswith("0x"):
                address_dec = int(address_raw, 16)
            else:
                address_dec = int(address_raw, 10)

    return mac_address, family, ave_device_id, address_dec


def find_unique_id(
    server: AveWebServer,
    family: int,
    ave_device_id: int,
    mac_address: str | None = None,
) -> str | None:
    """Find an already registered light unique_id by family and AVE device id."""
    for unique_id in server.lights:
        try:
            parsed = parse_uid(unique_id)
        except ValueError:
            continue
        if parsed is None:
            continue
        parsed_mac, parsed_family, parsed_device_id, _parsed_address_dec = parsed
        if mac_address and parsed_mac and parsed_mac != mac_address:
            continue
        if parsed_family == family and parsed_device_id == ave_device_id:
            return unique_id
    return None


async def async_setup_entry(
    _hass: HomeAssistant | None,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AVE dominaplus dimmer lights."""
    webserver: AveWebServer = entry.runtime_data
    if not webserver:
        _LOGGER.error("AVE dominaplus: Web server not initialized")
        connection_error = "Can't reach webserver"
        raise ConfigEntryNotReady(connection_error)

    await webserver.set_async_add_lg_entities(async_add_entities)
    await webserver.set_update_light(update_light)
    if not webserver.settings.fetch_lights:
        return

    await adopt_existing_lights(webserver, entry)


async def adopt_existing_lights(server: AveWebServer, entry: ConfigEntry) -> None:
    """Adopt existing light entities from the entity registry."""
    try:
        entity_registry = er.async_get(server.hass)
        if entity_registry is None:
            return
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        for entity in entities:
            if not (entity.platform == "ave_dominaplus" and entity.domain == "light"):
                continue
            if entity.unique_id in server.lights:
                continue

            try:
                parsed_uid = parse_uid(entity.unique_id)
                if parsed_uid is None:
                    continue
                uid_mac, family, ave_device_id, ave_address_dec = parsed_uid
            except ValueError:
                continue

            if uid_mac and server.mac_address and uid_mac != server.mac_address:
                _LOGGER.debug(
                    "Skipping light with unique_id %s due to MAC mismatch (%s != %s)",
                    entity.unique_id,
                    uid_mac,
                    server.mac_address,
                )
                continue

            if family != AVE_FAMILY_DIMMER:
                continue

            name = None
            if entity.name is not None:
                name = entity.name
            elif entity.original_name is not None:
                name = entity.original_name

            light = DimmerLight(
                unique_id=entity.unique_id,
                family=family,
                ave_device_id=ave_device_id,
                is_on=None,
                webserver=server,
                name=name,
                address_dec=ave_address_dec,
            )
            light.entity_id = entity.entity_id

            server.lights[entity.unique_id] = light
            server.async_add_lg_entities([light])
            _LOGGER.info(
                "Adopted existing dimmer entity with name %s with unique_id %s",
                light.name,
                light.unique_id,
            )
    except Exception:
        _LOGGER.exception("Error adopting existing light entities")


def set_light_uid(
    webserver: AveWebServer, family: int, ave_device_id: int, address_dec: int
) -> str:
    """Set the unique ID for the light."""
    return f"ave_{webserver.mac_address}_family_{family}_{ave_device_id}_0x{address_dec:02X}"


def update_light(
    server: AveWebServer,
    family: int,
    ave_device_id: int,
    device_status: int,
    name: str | None = None,
    address_dec: int | None = None,
) -> None:
    """Create or update dimmer light entities from webserver events."""
    if family != AVE_FAMILY_DIMMER:
        _LOGGER.debug(
            "Not updating light for family %s, device_id %s",
            family,
            ave_device_id,
        )
        return

    if not server.settings.fetch_lights:
        return

    unique_id = None
    if address_dec is not None:
        unique_id = set_light_uid(server, family, ave_device_id, address_dec)
        if unique_id not in server.lights:
            existing_unique_id = find_unique_id(
                server,
                family,
                ave_device_id,
                server.mac_address or None,
            )
            if existing_unique_id is not None:
                unique_id = existing_unique_id
    else:
        unique_id = find_unique_id(
            server,
            family,
            ave_device_id,
            server.mac_address or None,
        )

    already_exists = unique_id in server.lights if unique_id is not None else False

    if already_exists and unique_id is not None:
        light: DimmerLight = server.lights[unique_id]

        if device_status >= 0:
            light.update_state(device_status)

        if name is not None and server.settings.get_entity_names:
            light.set_ave_name(name)
            if not check_name_changed(server.hass, unique_id):
                light.set_name(name)

        if address_dec is not None:
            light.set_address_dec(address_dec)
    else:
        if address_dec is None:
            _LOGGER.error(
                "Cannot create light entity for family %s, device_id %s without address_dec",
                family,
                ave_device_id,
            )
            return
        if unique_id is None:
            unique_id = set_light_uid(server, family, ave_device_id, address_dec)
        entity_name = None
        entity_ave_name = None
        if name is not None and server.settings.get_entity_names:
            entity_name = name
            entity_ave_name = name

        light = DimmerLight(
            unique_id=unique_id,
            family=family,
            ave_device_id=ave_device_id,
            is_on=device_status,
            webserver=server,
            name=entity_name,
            ave_name=entity_ave_name,
            address_dec=address_dec,
        )

        _LOGGER.info("Creating new dimmer light entity %s", name)
        server.lights[unique_id] = light
        server.async_add_lg_entities([light])


def check_name_changed(hass: HomeAssistant, unique_id: str) -> bool:
    """Check if the name of the entity has changed in HA registry."""
    entity_registry = er.async_get(hass)

    entry_id = entity_registry.async_get_entity_id("light", "ave_dominaplus", unique_id)
    if entry_id:
        entity_entry = entity_registry.async_get(entry_id)
        if entity_entry is not None:
            return (
                entity_entry.name is not None
                and entity_entry.original_name != entity_entry.name
            )
    return False


class DimmerLight(LightEntity):
    """Representation of an AVE dimmer light."""

    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(
        self,
        unique_id: str,
        family: int,
        ave_device_id: int,
        is_on: int | None,
        webserver: AveWebServer,
        name=None,
        ave_name: str | None = None,
        address_dec: int | None = None,
    ) -> None:
        """Initialize the dimmer light."""
        self._unique_id = unique_id
        self.ave_device_id = ave_device_id
        self.family = family
        self._webserver = webserver
        self.hass = self._webserver.hass
        self._ave_name = ave_name
        self._address_dec = address_dec
        self._brightness = None

        if self.family == AVE_FAMILY_DIMMER:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        if name is None:
            self._name = self.build_name()
        else:
            self._name = name

        self._attr_is_on = False
        if is_on is not None and is_on >= 0:
            self.update_state(is_on)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the light."""
        if self._webserver:
            await self._webserver.switch_toggle(self.ave_device_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally setting brightness."""
        if not self._webserver:
            return

        brightness_ha = kwargs.get(ATTR_BRIGHTNESS)
        if brightness_ha is None:
            await self._webserver.switch_turn_on(self.ave_device_id)
            return

        brightness_ave = max(1, int((int(brightness_ha) / 255) * 31))
        await self._webserver.dimmer_set_level(self.ave_device_id, brightness_ave)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if self._webserver:
            await self._webserver.switch_turn_off(self.ave_device_id)

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the entity."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def brightness(self) -> int | None:
        """Return the current brightness in HA scale (0..255)."""
        return self._brightness

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "AVE_family": self.family,
            "AVE_device_id": self.ave_device_id,
            "AVE_name": self._ave_name,
            "AVE address_dec": self._address_dec,
            "AVE address_hex": format(self._address_dec & 0xFF, "02X")
            if self._address_dec is not None
            else "",
            "AVE webserver MAC": self._webserver.mac_address,
        }

    def update_state(self, value: int) -> None:
        """Update internal on/off and brightness state."""
        if value is None or int(value) < 0:
            return

        value = int(value)
        changed = False

        new_is_on = value > 0
        if self._attr_is_on != new_is_on:
            self._attr_is_on = new_is_on
            changed = True

        if self.family == AVE_FAMILY_DIMMER and value > 0:
            new_brightness = int((max(0, min(value, 31)) / 31) * 255)
            if self._brightness != new_brightness:
                self._brightness = new_brightness
                changed = True

        if changed:
            self.async_write_ha_state()

    def set_name(self, name: str | None) -> None:
        """Set the entity name."""
        if name is None:
            return
        self._name = name
        self.async_write_ha_state()

    def set_ave_name(self, name: str | None) -> None:
        """Set AVE native name."""
        if name is not None:
            self._ave_name = name
            self.async_write_ha_state()

    def set_address_dec(self, address_dec: int | None) -> None:
        """Set the AVE decimal address."""
        if address_dec is not None and self._address_dec != address_dec:
            self._address_dec = address_dec
            self.async_write_ha_state()

    def build_name(self) -> str:
        """Build default entity name."""
        return f"{BRAND_PREFIX} dimmer {self.ave_device_id}"
