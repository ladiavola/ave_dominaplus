"""Tests for integration setup and unload lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ave_dominaplus import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ave_dominaplus.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady


async def test_async_setup_returns_true(hass: HomeAssistant) -> None:
    """Test integration async_setup always returns True."""
    assert await async_setup(hass, {DOMAIN: {}}) is True


async def test_async_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup entry success path."""
    mock_webserver = AsyncMock()
    mock_webserver.authenticate.return_value = True
    mock_webserver.disconnect = AsyncMock()
    mock_webserver.start = AsyncMock()

    with (
        patch("custom_components.ave_dominaplus.AveWebServer", return_value=mock_webserver),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ) as forward_setups,
    ):
        result = await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

    assert result is True
    assert mock_config_entry.runtime_data is mock_webserver
    forward_setups.assert_awaited_once()
    mock_webserver.authenticate.assert_awaited_once()
    mock_webserver.start.assert_awaited_once()


async def test_async_setup_entry_not_ready_on_auth_failure(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup entry raises ConfigEntryNotReady when auth fails."""
    mock_webserver = AsyncMock()
    mock_webserver.authenticate.return_value = False

    with (
        patch("custom_components.ave_dominaplus.AveWebServer", return_value=mock_webserver),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(return_value=True),
        ) as forward_setups,
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, mock_config_entry)

    forward_setups.assert_not_awaited()


async def test_async_setup_entry_disconnects_on_forward_error(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup entry disconnects webserver if platform forwarding fails."""
    mock_webserver = AsyncMock()
    mock_webserver.authenticate.return_value = True
    mock_webserver.disconnect = AsyncMock()

    with (
        patch("custom_components.ave_dominaplus.AveWebServer", return_value=mock_webserver),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(side_effect=RuntimeError("forward failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="forward failed"):
            await async_setup_entry(hass, mock_config_entry)

    mock_webserver.disconnect.assert_awaited_once()


async def test_async_unload_entry_disconnects_on_success(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test unload entry disconnects webserver when unload succeeds."""
    mock_webserver = AsyncMock()
    mock_webserver.disconnect = AsyncMock()
    mock_config_entry.runtime_data = mock_webserver

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=True),
    ) as unload_platforms:
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is True
    unload_platforms.assert_awaited_once()
    mock_webserver.disconnect.assert_awaited_once()


async def test_async_unload_entry_no_disconnect_on_failure(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test unload entry does not disconnect webserver when unload fails."""
    mock_webserver = AsyncMock()
    mock_webserver.disconnect = AsyncMock()
    mock_config_entry.runtime_data = mock_webserver

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=False),
    ) as unload_platforms:
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is False
    unload_platforms.assert_awaited_once()
    mock_webserver.disconnect.assert_not_awaited()
