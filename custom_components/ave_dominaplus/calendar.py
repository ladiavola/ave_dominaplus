"""Calendar platform for AVE dominaplus integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import date, datetime, time as dt_time, timedelta
import logging

from defusedxml import ElementTree as DefusedET

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import sun
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import AVE_FAMILY_SCENARIO
from .device_info import (
    build_scenarios_parent_device_info,
    ensure_scenarios_parent_device,
)
from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1
_MAX_EVENTS = 256
_SCHEDULE_REFRESH_INTERVAL = timedelta(minutes=5)
_SCHEDULE_EVENT_DURATION = timedelta(minutes=1)
_SCHEDULE_LOOKAHEAD_DAYS = 90
_SCHEDULE_MAX_PAST_DAYS = 30
_SCHEDULE_MAX_FUTURE_DAYS = 400
_MAX_ASTRONOMIC_OFFSET_HOURS = 23


@dataclass(frozen=True)
class ScenarioScheduleTask:
    """One scheduler row returned by GST."""

    task_id: int
    scenario_id: int
    months_mask: int
    days_mask: int
    hour: int
    minute: int
    astronomic_type: str | None = None
    astronomic_hour_offset: int | None = None
    astronomic_minute_offset: int | None = None


async def async_setup_entry(
    _hass: HomeAssistant | None,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AVE dominaplus scenarios calendar."""
    webserver: AveWebServer = entry.runtime_data
    if not webserver or not webserver.settings.fetch_scenarios:
        return

    ensure_scenarios_parent_device(webserver, entry.entry_id)

    entity = DominaplusScenariosCalendar(webserver, entry.entry_id)
    webserver.scenario_calendar_entity = entity
    webserver.update_scenario_calendar = update_scenario_calendar
    async_add_entities([entity])


def update_scenario_calendar(
    server: AveWebServer,
    ave_device_id: int,
    device_status: int,
    name: str | None = None,
) -> None:
    """Propagate scenario status updates to the scenarios calendar entity."""
    calendar_entity = getattr(server, "scenario_calendar_entity", None)
    if calendar_entity is None:
        return
    calendar_entity.handle_scenario_update(
        ave_device_id=ave_device_id,
        device_status=device_status,
        name=name,
    )


class DominaplusScenariosCalendar(CalendarEntity):
    """Calendar timeline of scenario executions."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, webserver: AveWebServer, entry_id: str) -> None:
        """Initialize the scenarios calendar."""
        self._webserver = webserver
        self._attr_unique_id = f"ave_scenarios_calendar_{entry_id}"
        self._attr_name = "Schedule"
        self._attr_device_info = build_scenarios_parent_device_info(webserver)
        self._events: list[CalendarEvent] = []
        self._active_events: dict[int, CalendarEvent] = {}
        self._scenario_names: dict[int, str] = {}
        self._schedule_tasks: list[ScenarioScheduleTask] = []
        self._last_schedule_refresh: datetime | None = None
        self._schedule_refresh_lock = asyncio.Lock()

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or current event."""
        now = dt_util.now()
        candidates = [event for event in self._events if event.end_datetime_local > now]
        if self._is_schedule_fetch_enabled():
            next_schedule = self._next_schedule_event(now)
            if next_schedule is not None:
                candidates.append(next_schedule)
        if not candidates:
            return None
        return min(candidates, key=lambda item: item.start_datetime_local)

    async def async_update(self) -> None:
        """Refresh scheduler tasks from bridge endpoint."""
        await self._refresh_schedule_tasks()

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        del hass
        await self._refresh_schedule_tasks()

        execution_events = [
            event
            for event in self._events
            if event.end_datetime_local >= start_date
            and event.start_datetime_local <= end_date
        ]
        if not self._is_schedule_fetch_enabled():
            execution_events.sort(key=lambda item: item.start_datetime_local)
            return execution_events

        schedule_events = self._build_schedule_events(start_date, end_date)
        events = execution_events + schedule_events
        events.sort(key=lambda item: item.start_datetime_local)
        return events

    def handle_scenario_update(
        self,
        *,
        ave_device_id: int,
        device_status: int,
        name: str | None,
    ) -> None:
        """Handle scenario status updates from AVE websocket callbacks."""
        if name:
            clean_name = name.strip()
            if clean_name:
                self._scenario_names[ave_device_id] = clean_name

        if device_status < 0:
            # Snapshot updates only refresh known names.
            self._update_active_summary(ave_device_id)
            self._write_state_if_ready()
            return

        now = dt_util.now()
        if device_status > 0:
            if ave_device_id not in self._active_events:
                event = CalendarEvent(
                    start=now,
                    end=now + timedelta(minutes=1),
                    summary=self._summary_for(ave_device_id),
                )
                self._active_events[ave_device_id] = event
                self._events.append(event)
        else:
            event = self._active_events.pop(ave_device_id, None)
            if event is not None:
                end = now
                if end <= event.start_datetime_local:
                    end = event.start_datetime_local + timedelta(seconds=1)
                event.end = end

        self._update_active_summary(ave_device_id)
        self._trim_events()
        self._write_state_if_ready()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant."""
        if getattr(self._webserver, "scenario_calendar_entity", None) is self:
            self._webserver.scenario_calendar_entity = None
            self._webserver.update_scenario_calendar = None
        await super().async_will_remove_from_hass()

    def _summary_for(self, ave_device_id: int) -> str:
        """Build a stable calendar summary for one scenario."""
        scenario_name = self._scenario_names.get(ave_device_id)
        if scenario_name is None:
            scenario_name = self._scenario_name_from_raw_ldi(ave_device_id)
            if scenario_name:
                self._scenario_names[ave_device_id] = scenario_name
        if not scenario_name:
            return f"Scenario {ave_device_id}"
        if scenario_name.lower().startswith("scenario "):
            return scenario_name
        return f"Scenario {scenario_name}"

    def _summary_for_schedule(self, task: ScenarioScheduleTask) -> str:
        """Build summary for one scheduled scenario task."""
        base = f"{self._summary_for(task.scenario_id)} schedule"
        if task.astronomic_type == "sunrise":
            return f"{base} [sunrise]"
        if task.astronomic_type == "sunset":
            return f"{base} [sunset]"
        return base

    def _is_schedule_fetch_enabled(self) -> bool:
        """Return True when scenario scheduler fetch is enabled in options."""
        settings = getattr(self._webserver, "settings", None)
        if settings is None:
            return True
        return bool(getattr(settings, "fetch_scenario_schedule", True))

    def _scenario_name_from_raw_ldi(self, ave_device_id: int) -> str | None:
        """Lookup scenario name from LI2/LDI cache when available."""
        raw_ldi = getattr(self._webserver, "raw_ldi", [])
        for record in raw_ldi:
            if not isinstance(record, dict):
                continue
            if record.get("device_type") != AVE_FAMILY_SCENARIO:
                continue
            if record.get("device_id") != ave_device_id:
                continue
            name = str(record.get("device_name") or "").strip()
            if name:
                return name
        return None

    def _update_active_summary(self, ave_device_id: int) -> None:
        """Refresh active event summary when scenario names are learned late."""
        event = self._active_events.get(ave_device_id)
        if event is None:
            return
        event.summary = self._summary_for(ave_device_id)

    def _trim_events(self) -> None:
        """Keep event timeline bounded while preserving active entries."""
        if len(self._events) <= _MAX_EVENTS:
            return

        active_ids = {id(event) for event in self._active_events.values()}
        kept: list[CalendarEvent] = []
        for event in reversed(self._events):
            if len(kept) >= _MAX_EVENTS and id(event) not in active_ids:
                continue
            kept.append(event)
        self._events = list(reversed(kept))

    async def _refresh_schedule_tasks(self) -> None:
        """Refresh scheduler data from bridge.php?command=GST."""
        if not self._is_schedule_fetch_enabled():
            if self._schedule_tasks:
                self._schedule_tasks = []
                self._write_state_if_ready()
            return

        now = dt_util.utcnow()
        if (
            self._last_schedule_refresh is not None
            and now - self._last_schedule_refresh < _SCHEDULE_REFRESH_INTERVAL
        ):
            return

        async with self._schedule_refresh_lock:
            now = dt_util.utcnow()
            if (
                self._last_schedule_refresh is not None
                and now - self._last_schedule_refresh < _SCHEDULE_REFRESH_INTERVAL
            ):
                return

            status, payload = await self._webserver.call_bridge("GST")
            self._last_schedule_refresh = now

            if status != 200 or not payload:
                _LOGGER.debug(
                    "Skipping scheduler refresh due to bridge failure (status=%s)",
                    status,
                )
                return

            tasks = self._parse_scheduler_tasks(payload)
            gst_status, gst_payload = await self._webserver.call_gst_tasks_xml()
            if gst_status == 200 and gst_payload:
                tasks = self._enrich_tasks_with_astronomic_data(tasks, gst_payload)

            if tasks == self._schedule_tasks:
                return

            self._schedule_tasks = tasks
            self._write_state_if_ready()

    def _parse_scheduler_tasks(self, payload: str) -> list[ScenarioScheduleTask]:
        """Parse GST XML payload into scheduler tasks."""
        try:
            root = DefusedET.fromstring(payload)
        except DefusedET.ParseError:
            _LOGGER.debug("Invalid GST XML payload", exc_info=True)
            return []

        records = root.find("records")
        if records is None:
            return []

        tasks: list[ScenarioScheduleTask] = []
        for record in records.findall("record"):
            values = [record.findtext(f"dato{i}") for i in range(6)]
            if any(value is None for value in values):
                continue
            non_null_values = [value for value in values if value is not None]
            if len(non_null_values) != 6:
                continue

            (
                task_id,
                scenario_id,
                months_mask,
                days_mask,
                hour,
                minute,
            ) = non_null_values
            try:
                tasks.append(
                    ScenarioScheduleTask(
                        task_id=int(task_id),
                        scenario_id=int(scenario_id),
                        months_mask=int(months_mask),
                        days_mask=int(days_mask),
                        hour=int(hour),
                        minute=int(minute),
                    )
                )
            except (TypeError, ValueError):
                _LOGGER.debug("Skipping malformed GST record", exc_info=True)

        return tasks

    def _next_schedule_event(self, start: datetime) -> CalendarEvent | None:
        """Return first upcoming scheduled scenario event."""
        schedule_events = self._build_schedule_events(
            start,
            start + timedelta(days=_SCHEDULE_LOOKAHEAD_DAYS),
            limit=1,
        )
        if not schedule_events:
            return None
        return schedule_events[0]

    def _enrich_tasks_with_astronomic_data(
        self,
        tasks: list[ScenarioScheduleTask],
        payload: str,
    ) -> list[ScenarioScheduleTask]:
        """Attach sunrise/sunset offsets from gst.php XML to parsed GST rows."""
        try:
            root = DefusedET.fromstring(payload)
        except DefusedET.ParseError:
            _LOGGER.debug("Invalid gst.php XML payload", exc_info=True)
            return tasks

        xml_tasks = self._extract_scheduler_xml_rows(root)
        if not xml_tasks:
            return tasks

        indexed: dict[tuple[int, int, int], list[tuple[str, int, int]]] = {}
        by_scenario: dict[int, list[tuple[str, int, int]]] = {}
        for xml_task in xml_tasks:
            task_type = xml_task.get("type")
            hour_offset = xml_task.get("hour_offset")
            minute_offset = xml_task.get("minute_offset")
            scenario_id = xml_task.get("scenario_id")
            months_mask = xml_task.get("months_mask")
            days_mask = xml_task.get("days_mask")

            if (
                not isinstance(task_type, str)
                or not isinstance(hour_offset, int)
                or not isinstance(minute_offset, int)
                or not isinstance(scenario_id, int)
            ):
                continue

            candidate = (task_type, hour_offset, minute_offset)
            by_scenario.setdefault(scenario_id, []).append(candidate)
            if isinstance(months_mask, int) and isinstance(days_mask, int):
                indexed.setdefault((scenario_id, months_mask, days_mask), []).append(
                    candidate
                )

        enriched: list[ScenarioScheduleTask] = []
        for task in tasks:
            candidate = None
            key = (task.scenario_id, task.months_mask, task.days_mask)
            indexed_candidates = indexed.get(key)
            if indexed_candidates:
                candidate = indexed_candidates.pop(0)
            else:
                scenario_candidates = by_scenario.get(task.scenario_id)
                if scenario_candidates:
                    candidate = scenario_candidates.pop(0)

            if candidate is None:
                enriched.append(task)
                continue

            task_type, hour_offset, minute_offset = candidate
            if task_type == "sunset":
                enriched.append(
                    replace(
                        task,
                        astronomic_type="sunset",
                        astronomic_hour_offset=hour_offset,
                        astronomic_minute_offset=minute_offset,
                    )
                )
            elif task_type == "sunrise":
                enriched.append(
                    replace(
                        task,
                        astronomic_type="sunrise",
                        astronomic_hour_offset=hour_offset,
                        astronomic_minute_offset=minute_offset,
                    )
                )
            else:
                enriched.append(task)

        return enriched

    def _extract_scheduler_xml_rows(self, root) -> list[dict[str, object]]:
        """Extract schedulerTask rows from gst.php XML with tolerant tag parsing."""
        rows: list[dict[str, object]] = []
        for element in root.iter():
            if self._xml_local_name(element.tag) != "schedulertask":
                continue

            hour_text = self._find_text_ci(element, "hour")
            minute_text = self._find_text_ci(element, "minute")
            scenario_text = self._find_text_ci(element, "scenarioid")
            months_text = self._find_text_ci(element, "monthsbmp")
            days_text = self._find_text_ci(element, "daysbmp")
            if hour_text is None or minute_text is None or scenario_text is None:
                continue

            try:
                xml_hour = int(hour_text)
                xml_minute = int(minute_text)
                scenario_id = int(scenario_text)
                months_mask = int(months_text) if months_text is not None else None
                days_mask = int(days_text) if days_text is not None else None
            except ValueError:
                continue

            if xml_hour >= (200 - _MAX_ASTRONOMIC_OFFSET_HOURS):
                rows.append(
                    {
                        "type": "sunset",
                        "hour_offset": xml_hour - 200,
                        "minute_offset": xml_minute,
                        "scenario_id": scenario_id,
                        "months_mask": months_mask,
                        "days_mask": days_mask,
                    }
                )
            elif xml_hour >= (100 - _MAX_ASTRONOMIC_OFFSET_HOURS):
                rows.append(
                    {
                        "type": "sunrise",
                        "hour_offset": xml_hour - 100,
                        "minute_offset": xml_minute,
                        "scenario_id": scenario_id,
                        "months_mask": months_mask,
                        "days_mask": days_mask,
                    }
                )

        return rows

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        """Return lowercase XML tag name without namespace."""
        return tag.rsplit("}", 1)[-1].lower()

    def _find_text_ci(self, element, tag_name: str) -> str | None:
        """Find child text by tag name with case-insensitive matching."""
        target = tag_name.lower()
        for child in list(element):
            if self._xml_local_name(child.tag) == target:
                text = child.text
                if text is None:
                    return None
                clean = text.strip()
                if clean:
                    return clean
                return None
        return None

    def _build_schedule_events(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        limit: int | None = None,
    ) -> list[CalendarEvent]:
        """Expand scheduler tasks into concrete events for the requested interval."""
        if not self._schedule_tasks:
            return []

        start_local = dt_util.as_local(start_date)
        end_local = dt_util.as_local(end_date)
        if end_local < start_local:
            return []

        now = dt_util.now()
        oldest_allowed = now - timedelta(days=_SCHEDULE_MAX_PAST_DAYS)
        newest_allowed = now + timedelta(days=_SCHEDULE_MAX_FUTURE_DAYS)
        if end_local < oldest_allowed or start_local > newest_allowed:
            return []
        start_local = max(start_local, oldest_allowed)
        end_local = min(end_local, newest_allowed)

        events: list[CalendarEvent] = []
        current_date = start_local.date()
        while current_date <= end_local.date():
            for task in self._schedule_tasks:
                if not self._task_applies_to_date(task, current_date):
                    continue

                occurrence = self._task_occurrence_datetime(task, current_date)
                if occurrence is None:
                    continue

                occurrence_end = occurrence + _SCHEDULE_EVENT_DURATION
                if occurrence_end < start_local or occurrence > end_local:
                    continue

                events.append(
                    CalendarEvent(
                        start=occurrence,
                        end=occurrence_end,
                        summary=self._summary_for_schedule(task),
                    )
                )

            current_date += timedelta(days=1)

        events.sort(key=lambda item: item.start_datetime_local)
        if limit is None:
            return events
        return events[:limit]

    def _task_applies_to_date(self, task: ScenarioScheduleTask, day: date) -> bool:
        """Return True when month/day masks include this date."""
        if task.months_mask <= 0 or task.days_mask <= 0:
            return False

        month_bit = day.month - 1
        weekday_bit = day.weekday()  # Monday=0, matching AVE day mask bit order.
        month_active = bool(task.months_mask & (1 << month_bit))
        weekday_active = bool(task.days_mask & (1 << weekday_bit))
        return month_active and weekday_active

    def _task_occurrence_datetime(
        self,
        task: ScenarioScheduleTask,
        day: date,
    ) -> datetime | None:
        """Compute one occurrence for a task on the provided date."""
        if task.astronomic_type is not None:
            occurrence = self._astronomic_occurrence_datetime(task, day)
            if occurrence is not None:
                return occurrence

        if 0 <= task.hour <= 23 and 0 <= task.minute <= 59:
            return datetime.combine(
                day,
                dt_time(task.hour, task.minute),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )

        return self._astronomic_occurrence_datetime(task, day)

    def _astronomic_occurrence_datetime(
        self,
        task: ScenarioScheduleTask,
        day: date,
    ) -> datetime | None:
        """Compute occurrence from sunrise/sunset offsets encoded in GST."""
        event_name: str
        if task.astronomic_type == "sunset":
            event_name = "sunset"
            hour_offset = task.astronomic_hour_offset
            minute_offset = task.astronomic_minute_offset
        elif task.astronomic_type == "sunrise":
            event_name = "sunrise"
            hour_offset = task.astronomic_hour_offset
            minute_offset = task.astronomic_minute_offset
        elif task.hour >= (200 - _MAX_ASTRONOMIC_OFFSET_HOURS):
            event_name = "sunset"
            hour_offset = task.hour - 200
            minute_offset = task.minute
        elif task.hour >= (100 - _MAX_ASTRONOMIC_OFFSET_HOURS):
            event_name = "sunrise"
            hour_offset = task.hour - 100
            minute_offset = task.minute
        else:
            return None

        if hour_offset is None or minute_offset is None:
            return None

        if abs(hour_offset) > _MAX_ASTRONOMIC_OFFSET_HOURS:
            return None
        if abs(minute_offset) > 59:
            return None
        if self.hass is None:
            return None

        solar_base = sun.get_astral_event_date(self.hass, event_name, day)
        if solar_base is None:
            return None

        return dt_util.as_local(solar_base) + timedelta(
            hours=hour_offset,
            minutes=minute_offset,
        )

    def _write_state_if_ready(self) -> None:
        """Write HA state only when entity is attached."""
        if self.hass is None or self.entity_id is None:
            return
        try:
            self.async_write_ha_state()
        except RuntimeError:
            _LOGGER.debug(
                "Skipping scenarios calendar state write due to runtime state",
                exc_info=True,
            )
