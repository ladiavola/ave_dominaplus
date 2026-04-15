"""Tests for AVE scenarios calendar platform."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

from custom_components.ave_dominaplus import calendar as ave_calendar
from custom_components.ave_dominaplus.const import DOMAIN
from custom_components.ave_dominaplus.web_server import AveWebServer
from homeassistant.core import HomeAssistant
from homeassistant.helpers import sun
from homeassistant.util import dt as dt_util


def _new_server(hass: HomeAssistant, **overrides) -> AveWebServer:
    """Build a webserver with defaults suitable for calendar tests."""
    settings: dict[str, object] = {
        "ip_address": "192.168.1.10",
        "get_entities_names": True,
        "fetch_sensor_areas": True,
        "fetch_sensors": True,
        "fetch_lights": True,
        "fetch_covers": True,
        "fetch_scenarios": True,
        "fetch_scenario_schedule": True,
        "fetch_thermostats": True,
        "on_off_lights_as_switch": True,
    }
    settings.update(overrides)
    server = AveWebServer(settings, hass)
    server.mac_address = "aa:bb:cc:dd:ee:ff"
    server.binary_sensors = {}
    server.async_add_bs_entities = Mock()
    server.call_bridge = AsyncMock(
        return_value=(
            200,
            "<?xml version='1.0'?><root><records></records></root>",
        )
    )
    server.call_gst_tasks_xml = AsyncMock(return_value=(404, None))
    return server


async def test_calendar_setup_entry_adds_entity_and_callback(
    hass: HomeAssistant,
) -> None:
    """Calendar setup should add one scenarios calendar and register callback."""
    server = _new_server(hass, fetch_scenarios=True)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    await ave_calendar.async_setup_entry(hass, entry, async_add)

    async_add.assert_called_once()
    added_entities = async_add.call_args.args[0]
    assert len(added_entities) == 1
    entity = added_entities[0]
    assert isinstance(entity, ave_calendar.DominaplusScenariosCalendar)
    assert entity.name == "Schedule"
    assert callable(server.update_scenario_calendar)
    assert server.scenario_calendar_entity is entity
    assert entity.device_info is not None
    assert entity.device_info.get("identifiers") == {
        (DOMAIN, "endpoint_aa:bb:cc:dd:ee:ff_scenarios")
    }


async def test_calendar_setup_entry_skips_when_scenarios_disabled(
    hass: HomeAssistant,
) -> None:
    """Calendar setup should no-op when scenarios feature is disabled."""
    server = _new_server(hass, fetch_scenarios=False)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    await ave_calendar.async_setup_entry(hass, entry, async_add)

    async_add.assert_not_called()
    assert getattr(server, "scenario_calendar_entity", None) is None


async def test_calendar_collects_scenario_execution_events(hass: HomeAssistant) -> None:
    """Scenario running updates should create calendar events with scenario names."""
    server = _new_server(hass, fetch_scenarios=True)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    await ave_calendar.async_setup_entry(hass, entry, async_add)
    entity = async_add.call_args.args[0][0]

    # Name snapshot (status -1) followed by running/stop transitions.
    server.update_scenario_calendar(server, 29, -1, "Wake Up")
    server.update_scenario_calendar(server, 29, 1, "Wake Up")
    server.update_scenario_calendar(server, 29, 0, "Wake Up")

    now = dt_util.now()
    events = await entity.async_get_events(
        hass,
        now - timedelta(hours=1),
        now + timedelta(hours=1),
    )

    assert events
    assert events[-1].summary == "Scenario Wake Up"


async def test_calendar_loads_gst_schedules_for_multiple_scenarios(
    hass: HomeAssistant,
) -> None:
    """One scenarios calendar should expose scheduled events for all scenarios."""
    server = _new_server(hass, fetch_scenarios=True)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    now = dt_util.now()
    next_slot = now + timedelta(minutes=2)
    month_mask = (1 << next_slot.month - 1) | (1 << now.month - 1)
    day_mask = 1 << next_slot.weekday()
    gst_payload = (
        "<?xml version='1.0'?>"
        "<root><records>"
        f"<record><dato0>10</dato0><dato1>29</dato1><dato2>{month_mask}</dato2>"
        f"<dato3>{day_mask}</dato3><dato4>{next_slot.hour}</dato4>"
        f"<dato5>{next_slot.minute}</dato5></record>"
        f"<record><dato0>11</dato0><dato1>30</dato1><dato2>{month_mask}</dato2>"
        f"<dato3>{day_mask}</dato3><dato4>{next_slot.hour}</dato4>"
        f"<dato5>{next_slot.minute}</dato5></record>"
        "</records></root>"
    )
    server.call_bridge = AsyncMock(return_value=(200, gst_payload))

    await ave_calendar.async_setup_entry(hass, entry, async_add)
    entity = async_add.call_args.args[0][0]

    server.update_scenario_calendar(server, 29, -1, "Wake Up")
    server.update_scenario_calendar(server, 30, -1, "Good Night")

    events = await entity.async_get_events(
        hass,
        now - timedelta(minutes=1),
        now + timedelta(days=1),
    )

    summaries = {event.summary for event in events}
    assert "Scenario Wake Up schedule" in summaries
    assert "Scenario Good Night schedule" in summaries
    server.call_bridge.assert_awaited_once_with("GST")


async def test_calendar_uses_gst_php_for_astronomic_recurring_events(
    hass: HomeAssistant,
) -> None:
    """Astronomic schedules should follow sunrise/sunset metadata from gst.php."""
    server = _new_server(hass, fetch_scenarios=True)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    now = dt_util.now()
    month_mask = 1 << now.month - 1
    day_mask = (1 << 7) - 1
    gst_payload = (
        "<?xml version='1.0'?>"
        "<root><records>"
        f"<record><dato0>10</dato0><dato1>29</dato1><dato2>{month_mask}</dato2>"
        f"<dato3>{day_mask}</dato3><dato4>20</dato4><dato5>45</dato5></record>"
        "</records></root>"
    )
    gst_tasks_payload = (
        "<?xml version='1.0'?>"
        "<DPConfig><schedulerTasks>"
        f"<schedulerTask><monthsBmp>{month_mask}</monthsBmp><daysBmp>{day_mask}</daysBmp>"
        "<hour>100</hour><minute>15</minute><scenarioId>29</scenarioId></schedulerTask>"
        "</schedulerTasks></DPConfig>"
    )
    server.call_bridge = AsyncMock(return_value=(200, gst_payload))
    server.call_gst_tasks_xml = AsyncMock(return_value=(200, gst_tasks_payload))

    await ave_calendar.async_setup_entry(hass, entry, async_add)
    entity = async_add.call_args.args[0][0]
    entity.hass = hass
    server.update_scenario_calendar(server, 29, -1, "Wake Up")

    base_date = now.date()

    def _fake_astral_event(_hass, event, current_date):
        del _hass, event
        return datetime.combine(
            current_date,
            datetime.min.time(),
            tzinfo=dt_util.DEFAULT_TIME_ZONE,
        ) + timedelta(hours=6)

    original = sun.get_astral_event_date
    sun.get_astral_event_date = _fake_astral_event
    try:
        events = await entity.async_get_events(
            hass,
            datetime.combine(
                base_date,
                datetime.min.time(),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            ),
            datetime.combine(
                base_date,
                datetime.max.time(),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            ),
        )
    finally:
        sun.get_astral_event_date = original

    schedule_events = [e for e in events if "schedule" in e.summary]
    assert schedule_events
    sunrise_events = [e for e in events if "[sunrise]" in e.summary]
    assert sunrise_events
    assert sunrise_events[0].start_datetime_local.hour == 6
    assert sunrise_events[0].start_datetime_local.minute == 15


async def test_calendar_does_not_expand_schedules_for_distant_future(
    hass: HomeAssistant,
) -> None:
    """Recurring schedules should not be expanded indefinitely into distant years."""
    server = _new_server(hass, fetch_scenarios=True)
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    now = dt_util.now()
    month_mask = (1 << 12) - 1
    day_mask = (1 << 7) - 1
    gst_payload = (
        "<?xml version='1.0'?>"
        "<root><records>"
        f"<record><dato0>10</dato0><dato1>29</dato1><dato2>{month_mask}</dato2>"
        f"<dato3>{day_mask}</dato3><dato4>20</dato4><dato5>45</dato5></record>"
        "</records></root>"
    )
    server.call_bridge = AsyncMock(return_value=(200, gst_payload))

    await ave_calendar.async_setup_entry(hass, entry, async_add)
    entity = async_add.call_args.args[0][0]
    server.update_scenario_calendar(server, 29, -1, "Wake Up")

    start = now + timedelta(days=1000)
    end = start + timedelta(days=30)
    events = await entity.async_get_events(hass, start, end)
    schedule_events = [e for e in events if e.summary.endswith("schedule")]
    assert schedule_events == []


async def test_calendar_skips_schedule_fetch_when_option_disabled(
    hass: HomeAssistant,
) -> None:
    """When fetch_scenario_schedule is disabled, only execution events remain."""
    server = _new_server(
        hass,
        fetch_scenarios=True,
        fetch_scenario_schedule=False,
    )
    entry = SimpleNamespace(runtime_data=server, entry_id="entry-1")
    async_add = Mock()

    await ave_calendar.async_setup_entry(hass, entry, async_add)
    entity = async_add.call_args.args[0][0]
    server.update_scenario_calendar(server, 29, 1, "Wake Up")
    server.update_scenario_calendar(server, 29, 0, "Wake Up")

    now = dt_util.now()
    events = await entity.async_get_events(
        hass,
        now - timedelta(hours=1),
        now + timedelta(hours=1),
    )

    assert events
    assert all("schedule" not in event.summary for event in events)
    cast(AsyncMock, server.call_bridge).assert_not_awaited()
    cast(AsyncMock, server.call_gst_tasks_xml).assert_not_awaited()
