"""Tests that exercise every AVE_UNHANDLED_UPD key through manage_upd."""

from __future__ import annotations

import logging

from custom_components.ave_dominaplus.const import AVE_UNHANDLED_UPD
from tests.web_server_harness import make_server


def test_manage_upd_handles_all_unhandled_upd(hass, caplog) -> None:
    """Call `manage_upd` for every unhandled UPD key and assert it logs."""
    server = make_server(hass)

    caplog.set_level(logging.DEBUG)

    for key, desc in AVE_UNHANDLED_UPD.items():
        caplog.clear()
        # manage_upd expects a parameters list where parameters[0] is the UPD key
        server.manage_upd([key], [])

        # The handler logs a debug message including the description
        matched = any(desc in rec.getMessage() for rec in caplog.records)
        assert matched, f"Expected log for unhandled UPD {key} -> {desc}"
