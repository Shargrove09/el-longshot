"""Tests for the monitor notification dispatch logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from longshotel.config import NotifyMode, Settings
from longshotel.models import Hotel
from longshotel.monitor import run_monitor

WEBHOOK_URL = "https://discord.com/api/webhooks/test/fake"

AVAILABLE_HOTEL_DATA = {
    "hotelId": 1001,
    "name": "Hotel Alpha",
    "hotelChain": "Chain A",
    "latitude": 32.71,
    "longitude": -117.16,
    "distance": 0.3,
    "distanceUnits": "Miles",
    "starRatingDecimal": 4,
    "amenities": [],
    "promotions": [],
    "hasPromo": False,
    "type": "EVENT",
    "starRating": 0,
    "images": {},
    "avail": {
        "hotelId": 1001,
        "status": "AVAILABLE",
        "lowestAvgRateNumeric": 200,
        "inclusiveLowestAvgRateNumeric": 215,
        "showInclusiveLowestAvgRate": True,
        "totalAdditionalFees": 15,
        "additionalFeesMessage": "",
        "additionalFeesLong": "",
        "isServiceFeeIncluded": False,
        "roomsBooked": 5,
        "maxAllowed": 3,
        "groupMax": 3,
        "hotelGroupMax": 100,
        "maxOneBlockReservations": 0,
        "maxMultiBlockReservations": 0,
    },
}

SOLDOUT_HOTEL_DATA = {
    **AVAILABLE_HOTEL_DATA,
    "hotelId": 1002,
    "name": "Hotel Beta",
    "hotelChain": "Chain B",
    "distance": 1.1,
    "avail": {
        **AVAILABLE_HOTEL_DATA["avail"],
        "hotelId": 1002,
        "status": "SOLDOUT",
    },
}


def _hotel(data: dict) -> Hotel:
    return Hotel.model_validate(data)


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        event_code="TEST",
        block_index=1,
        base_url="https://compass.onpeak.com",
        arrive="2026-07-21",
        depart="2026-07-27",
        poll_interval_seconds=1,
        discord_webhook_url=WEBHOOK_URL,
        notify_mode=NotifyMode.changes,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class _StopMonitor(Exception):
    """Raised by the mocked sleep to break the monitor loop."""


async def _sleep_then_stop(_seconds: float) -> None:
    raise _StopMonitor


@pytest.mark.asyncio
async def test_changes_mode_sends_available_and_soldout() -> None:
    """In 'changes' mode, both newly-available and newly-sold-out fire."""
    # Tick 1: both available.  Tick 2: hotel Alpha sold out, Beta available.
    tick1 = [_hotel(AVAILABLE_HOTEL_DATA), _hotel({**SOLDOUT_HOTEL_DATA, "avail": {**SOLDOUT_HOTEL_DATA["avail"], "status": "AVAILABLE"}})]
    tick2_beta_avail = {**SOLDOUT_HOTEL_DATA, "avail": {**SOLDOUT_HOTEL_DATA["avail"], "status": "AVAILABLE"}}
    tick2_alpha_sold = {**AVAILABLE_HOTEL_DATA, "avail": {**AVAILABLE_HOTEL_DATA["avail"], "status": "SOLDOUT"}}
    tick2 = [_hotel(tick2_alpha_sold), _hotel(tick2_beta_avail)]

    fetch_mock = AsyncMock(side_effect=[tick1, tick2])
    send_avail = AsyncMock()
    send_soldout = AsyncMock()

    settings = _make_settings(notify_mode=NotifyMode.changes)

    with (
        patch("longshotel.monitor.fetch_hotels", fetch_mock),
        patch("longshotel.monitor.send_discord_notification", send_avail),
        patch("longshotel.monitor.send_discord_soldout_notification", send_soldout),
        patch("longshotel.monitor.asyncio.sleep", side_effect=[None, _StopMonitor]),
    ):
        with pytest.raises(_StopMonitor):
            await run_monitor(settings)

    # Tick 2 should have triggered both notifications
    send_avail.assert_called_once()
    send_soldout.assert_called_once()


@pytest.mark.asyncio
async def test_every_mode_sends_summary_each_tick() -> None:
    """In 'every' mode, a summary is posted each poll cycle."""
    hotels = [_hotel(AVAILABLE_HOTEL_DATA), _hotel(SOLDOUT_HOTEL_DATA)]
    fetch_mock = AsyncMock(return_value=hotels)
    send_summary = AsyncMock()

    settings = _make_settings(notify_mode=NotifyMode.every)

    with (
        patch("longshotel.monitor.fetch_hotels", fetch_mock),
        patch("longshotel.monitor.send_discord_summary", send_summary),
        patch("longshotel.monitor.asyncio.sleep", side_effect=[None, _StopMonitor]),
    ):
        with pytest.raises(_StopMonitor):
            await run_monitor(settings)

    # Summary called on both tick 1 (initial) and tick 2
    assert send_summary.call_count == 2


@pytest.mark.asyncio
async def test_off_mode_sends_nothing() -> None:
    """In 'off' mode, no Discord notifications are sent."""
    hotels = [_hotel(AVAILABLE_HOTEL_DATA)]
    fetch_mock = AsyncMock(return_value=hotels)
    send_avail = AsyncMock()
    send_soldout = AsyncMock()
    send_summary = AsyncMock()

    settings = _make_settings(notify_mode=NotifyMode.off)

    with (
        patch("longshotel.monitor.fetch_hotels", fetch_mock),
        patch("longshotel.monitor.send_discord_notification", send_avail),
        patch("longshotel.monitor.send_discord_soldout_notification", send_soldout),
        patch("longshotel.monitor.send_discord_summary", send_summary),
        patch("longshotel.monitor.asyncio.sleep", side_effect=_StopMonitor),
    ):
        with pytest.raises(_StopMonitor):
            await run_monitor(settings)

    send_avail.assert_not_called()
    send_soldout.assert_not_called()
    send_summary.assert_not_called()


@pytest.mark.asyncio
async def test_no_webhook_url_disables_notifications() -> None:
    """If no webhook URL is set, notifications are disabled even in 'changes' mode."""
    hotels = [_hotel(AVAILABLE_HOTEL_DATA)]
    fetch_mock = AsyncMock(return_value=hotels)
    send_avail = AsyncMock()

    settings = _make_settings(
        notify_mode=NotifyMode.changes,
        discord_webhook_url=None,
    )

    with (
        patch("longshotel.monitor.fetch_hotels", fetch_mock),
        patch("longshotel.monitor.send_discord_notification", send_avail),
        patch("longshotel.monitor.asyncio.sleep", side_effect=_StopMonitor),
    ):
        with pytest.raises(_StopMonitor):
            await run_monitor(settings)

    send_avail.assert_not_called()
