"""Additional branch coverage tests for AVE binary sensor platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.ave_dominaplus.binary_sensor import (
    MotionBinarySensor,
    adopt_existing_sensors,
    async_setup_entry,
    check_name_changed,
)
from custom_components.ave_dominaplus.const import (
    AVE_FAMILY_ANTITHEFT_AREA,
    AVE_FAMILY_MOTION_SENSOR,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.exceptions import ConfigEntryNotReady
from tests.web_server_harness import make_server


def _entry(runtime_data, entry_id: str = "entry-1"):
    return SimpleNamespace(runtime_data=runtime_data, entry_id=entry_id)


@pytest.mark.asyncio
async def test_async_setup_entry_raises_when_webserver_missing() -> None:
    """Setup should raise ConfigEntryNotReady when runtime_data is missing."""
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(None, _entry(None), Mock())


@pytest.mark.asyncio
async def test_async_setup_entry_registers_callbacks_and_adds_status_sensor(hass) -> None:
    """Setup should register callbacks, run adoption, and add hub status entity."""
    server = make_server(hass)
    server.set_update_binary_sensor = AsyncMock()
    server.set_async_add_bs_entities = AsyncMock()

    with patch(
        "custom_components.ave_dominaplus.binary_sensor.adopt_existing_sensors",
        new=AsyncMock(),
    ) as adopt_mock:
        add_entities = Mock()
        await async_setup_entry(hass, _entry(server), add_entities)

    server.set_update_binary_sensor.assert_awaited_once()
    server.set_async_add_bs_entities.assert_awaited_once_with(add_entities)
    adopt_mock.assert_awaited_once()
    add_entities.assert_called_once()
    assert len(add_entities.call_args.args[0]) == 1


@pytest.mark.asyncio
async def test_adopt_existing_sensors_returns_when_registry_missing(hass) -> None:
    """Adoption should return cleanly when entity registry is unavailable."""
    server = make_server(hass)

    with patch(
        "custom_components.ave_dominaplus.binary_sensor.er.async_get",
        return_value=None,
    ):
        await adopt_existing_sensors(server, _entry(server))


@pytest.mark.asyncio
async def test_adopt_existing_sensors_filters_disabled_and_adopts_valid_motion(
    hass,
) -> None:
    """Adoption should filter by class/settings and adopt valid motion entries."""
    server = make_server(hass, fetch_sensor_areas=False, fetch_sensors=True)
    server.async_add_bs_entities = Mock()
    server.binary_sensors["ave_motion_13_8"] = object()

    entities = [
        # Wrong domain
        SimpleNamespace(
            platform="ave_dominaplus",
            domain="switch",
            original_device_class="motion",
            unique_id="ave_motion_13_1",
            name="skip",
            original_name=None,
            entity_id="switch.skip",
        ),
        # Wrong device class
        SimpleNamespace(
            platform="ave_dominaplus",
            domain="binary_sensor",
            original_device_class="opening",
            unique_id="ave_motion_13_2",
            name="skip",
            original_name=None,
            entity_id="binary_sensor.skip",
        ),
        # Area family but disabled
        SimpleNamespace(
            platform="ave_dominaplus",
            domain="binary_sensor",
            original_device_class="motion",
            unique_id=f"ave_motion_{AVE_FAMILY_ANTITHEFT_AREA}_3",
            name="Area",
            original_name=None,
            entity_id="binary_sensor.area",
        ),
        # Duplicate existing
        SimpleNamespace(
            platform="ave_dominaplus",
            domain="binary_sensor",
            original_device_class="motion",
            unique_id="ave_motion_13_8",
            name="dup",
            original_name=None,
            entity_id="binary_sensor.dup",
        ),
        # Valid entry, name from original_name fallback
        SimpleNamespace(
            platform="ave_dominaplus",
            domain="binary_sensor",
            original_device_class="motion",
            unique_id=f"ave_motion_{AVE_FAMILY_MOTION_SENSOR}_9",
            name=None,
            original_name="Hall Motion",
            entity_id="binary_sensor.hall_motion",
        ),
    ]

    with (
        patch(
            "custom_components.ave_dominaplus.binary_sensor.er.async_get",
            return_value=Mock(),
        ),
        patch(
            "custom_components.ave_dominaplus.binary_sensor.er.async_entries_for_config_entry",
            return_value=entities,
        ),
    ):
        await adopt_existing_sensors(server, _entry(server))

    expected_uid = f"ave_motion_{AVE_FAMILY_MOTION_SENSOR}_9"
    assert expected_uid in server.binary_sensors
    assert server.binary_sensors[expected_uid].name == "Hall Motion"
    server.async_add_bs_entities.assert_called_once()


@pytest.mark.asyncio
async def test_adopt_existing_sensors_handles_bad_unique_id_exception(hass) -> None:
    """Adoption should swallow errors from malformed legacy unique IDs."""
    server = make_server(hass)
    bad_entity = SimpleNamespace(
        platform="ave_dominaplus",
        domain="binary_sensor",
        original_device_class="motion",
        unique_id="bad_uid",
        name="Bad",
        original_name=None,
        entity_id="binary_sensor.bad",
    )

    with (
        patch(
            "custom_components.ave_dominaplus.binary_sensor.er.async_get",
            return_value=Mock(),
        ),
        patch(
            "custom_components.ave_dominaplus.binary_sensor.er.async_entries_for_config_entry",
            return_value=[bad_entity],
        ),
    ):
        await adopt_existing_sensors(server, _entry(server))


def test_check_name_changed_true_and_false_branches(hass) -> None:
    """Name-change helper should detect override and missing entry paths."""
    registry = Mock()
    registry.async_get_entity_id.return_value = "binary_sensor.test"
    registry.async_get.return_value = SimpleNamespace(name="New", original_name="Old")

    with patch(
        "custom_components.ave_dominaplus.binary_sensor.er.async_get",
        return_value=registry,
    ):
        assert check_name_changed(hass, "uid") is True

    registry.async_get_entity_id.return_value = None
    with patch(
        "custom_components.ave_dominaplus.binary_sensor.er.async_get",
        return_value=registry,
    ):
        assert check_name_changed(hass, "uid") is False


@pytest.mark.asyncio
async def test_motion_sensor_lifecycle_and_property_branches(hass) -> None:
    """Motion entity should cover lifecycle hooks and property guard branches."""
    server = make_server(hass)
    server._set_connected(True)

    motion = MotionBinarySensor(
        unique_id="uid-motion",
        family=AVE_FAMILY_MOTION_SENSOR,
        ave_device_id=5,
        is_motion_detected=None,
        hass=hass,
        webserver=server,
    )
    motion.async_write_ha_state = Mock()

    assert motion.unique_id == "uid-motion"
    assert motion.available is True
    assert motion.is_on is None
    assert motion.device_class == BinarySensorDeviceClass.MOTION
    assert "AVE_name" not in motion.extra_state_attributes

    area = MotionBinarySensor(
        unique_id="uid-area",
        family=AVE_FAMILY_ANTITHEFT_AREA,
        ave_device_id=2,
        is_motion_detected=1,
        hass=hass,
        webserver=server,
        ave_name="Area A",
    )
    area.async_write_ha_state = Mock()
    assert area.extra_state_attributes["AVE_name"] == "Area A"
    assert area.build_name() == "Antitheft Area 2"

    with (
        patch(
            "homeassistant.helpers.entity.Entity.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.helpers.entity.Entity.async_will_remove_from_hass",
            new=AsyncMock(),
        ),
    ):
        await motion.async_added_to_hass()
        await motion.async_will_remove_from_hass()

    # Trigger exception branch in update_state timestamp handling.
    with patch(
        "custom_components.ave_dominaplus.binary_sensor.utcnow",
        side_effect=RuntimeError("clock"),
    ):
        motion.update_state(1)

    # set_name None path and set_ave_name write path.
    motion.set_name(None)
    motion.set_ave_name("Motion")

    # set_name write guarded by hass truthiness.
    motion.hass = None
    motion.set_name("NoWrite")
