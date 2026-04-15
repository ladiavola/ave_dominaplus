1. Calendar renamed to Schedule in calendar.py.
2. Sunrise and sunset tags added to scheduled event summaries in calendar.py.
3. New config option fetch_scenario_schedule added end-to-end:
- Schema and defaults in config_flow.py
- Runtime setting in web_server.py
- Diagnostics flag in diagnostics.py
- UI strings in strings.json, en.json, it.json.
4. When fetch_scenario_schedule is disabled, schedule fetch is fully skipped and cached schedule tasks are cleared in calendar.py, so the calendar tracks only trigger/execution events.
5. Tests updated and passing:
- New behavior checks in test_calendar.py
- Config flow fixtures in test_config_flow.py, conftest.py
- Diagnostics fixture in test_diagnostics.py

How schedule refresh works now:

1. Trigger points:
- Called during calendar update in calendar.py
- Called when Home Assistant asks events for a date range in calendar.py

2. Gating:
- If fetch_scenario_schedule is false, refresh exits immediately and disables schedule generation in calendar.py

3. Throttling:
- Refresh is rate-limited to every 5 minutes via _SCHEDULE_REFRESH_INTERVAL in calendar.py

4. Data read path:
- Reads GST records via bridge
- Reads gst.php tasks XML via web_server.py
- Enriches tasks with sunrise/sunset metadata in calendar.py

5. Event generation model:
- No infinite pre-fill. Events are generated on demand only for the requested window in calendar.py
- Window is clamped to a bounded horizon (past/future limits) in calendar.py
- The single next event uses a 90-day lookahead in calendar.py

Validation run:
- Focused suite passed: test_calendar.py + test_config_flow.py + tests/test_diagnostics.py, 49 passed.