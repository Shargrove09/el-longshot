"""Tests for Discord notification functions."""

import json

import httpx
import pytest
import respx

from longshotel.config import Settings
from longshotel.models import Hotel
from longshotel.notifications import (
    send_discord_notification,
    send_discord_soldout_notification,
    send_discord_summary,
)

WEBHOOK_URL = "https://discord.com/api/webhooks/test/fake"
BOT_TOKEN = "fake-bot-token"
USER_ID = "123456789"

_BASE = dict(
    event_code="TEST",
    block_index=1,
    base_url="https://compass.onpeak.com",
    arrive="2026-07-21",
    depart="2026-07-27",
)


def _webhook_settings() -> Settings:
    return Settings(
        **_BASE,
        discord_webhook_url=WEBHOOK_URL,
        discord_bot_token=None,
        discord_user_id=None,
    )


def _bot_settings() -> Settings:
    return Settings(**_BASE, discord_bot_token=BOT_TOKEN, discord_user_id=USER_ID)

AVAILABLE_HOTEL_DATA = {
    "hotelId": 1001,
    "name": "Hotel Alpha",
    "hotelChain": "Chain A",
    "latitude": 32.71,
    "longitude": -117.16,
    "distance": 0.3,
    "distanceUnits": "Miles",
    "starRatingDecimal": 4,
    "amenities": [{"type": "Pool"}],
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
        "lowestAvgRateNumeric": 150,
        "inclusiveLowestAvgRateNumeric": 160,
        "showInclusiveLowestAvgRate": False,
    },
}


@respx.mock
@pytest.mark.asyncio
async def test_send_discord_notification_posts_message() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    hotel = Hotel.model_validate(AVAILABLE_HOTEL_DATA)
    await send_discord_notification(_webhook_settings(), [hotel])

    assert route.called
    payload = route.calls[0].request.content
    assert b"Hotel Alpha" in payload
    assert b"New Hotel Availability" in payload


@respx.mock
@pytest.mark.asyncio
async def test_send_discord_notification_skips_empty_list() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    await send_discord_notification(_webhook_settings(), [])
    assert not route.called


@respx.mock
@pytest.mark.asyncio
async def test_send_discord_soldout_notification_posts_message() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    hotel = Hotel.model_validate(SOLDOUT_HOTEL_DATA)
    await send_discord_soldout_notification(_webhook_settings(), [hotel])

    assert route.called
    payload = route.calls[0].request.content
    assert b"Hotel Beta" in payload
    assert b"Sold Out" in payload


@respx.mock
@pytest.mark.asyncio
async def test_send_discord_soldout_notification_skips_empty_list() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    await send_discord_soldout_notification(_webhook_settings(), [])
    assert not route.called


@respx.mock
@pytest.mark.asyncio
async def test_send_discord_summary_posts_message() -> None:
    route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    available = Hotel.model_validate(AVAILABLE_HOTEL_DATA)
    soldout = Hotel.model_validate(SOLDOUT_HOTEL_DATA)
    await send_discord_summary(_webhook_settings(), [available, soldout])

    assert route.called
    payload = route.calls[0].request.content
    assert b"Summary" in payload
    assert b"Hotel Alpha" in payload
    assert b"Hotel Beta" in payload
    assert b"1 available" in payload
    assert b"1 sold out" in payload


# ── Bot DM tests ─────────────────────────────────────────────────────────

DM_CHANNEL_URL = "https://discord.com/api/v10/users/@me/channels"
DM_MSG_URL = "https://discord.com/api/v10/channels/99999/messages"


@respx.mock
@pytest.mark.asyncio
async def test_bot_dm_notification_creates_channel_and_sends() -> None:
    respx.post(DM_CHANNEL_URL).mock(
        return_value=httpx.Response(200, json={"id": "99999"})
    )
    msg_route = respx.post(DM_MSG_URL).mock(
        return_value=httpx.Response(200, json={})
    )
    hotel = Hotel.model_validate(AVAILABLE_HOTEL_DATA)
    await send_discord_notification(_bot_settings(), [hotel])

    assert msg_route.called
    payload = msg_route.calls[0].request.content
    assert b"Hotel Alpha" in payload


@respx.mock
@pytest.mark.asyncio
async def test_bot_dm_takes_priority_over_webhook() -> None:
    """When both bot and webhook are configured, bot DM is used."""
    respx.post(DM_CHANNEL_URL).mock(
        return_value=httpx.Response(200, json={"id": "99999"})
    )
    msg_route = respx.post(DM_MSG_URL).mock(
        return_value=httpx.Response(200, json={})
    )
    webhook_route = respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(204)
    )
    settings = Settings(
        **_BASE,
        discord_bot_token=BOT_TOKEN,
        discord_user_id=USER_ID,
        discord_webhook_url=WEBHOOK_URL,
    )
    hotel = Hotel.model_validate(AVAILABLE_HOTEL_DATA)
    await send_discord_notification(settings, [hotel])

    assert msg_route.called
    assert not webhook_route.called


@respx.mock
@pytest.mark.asyncio
async def test_bot_dm_summary_is_chunked_to_discord_limit() -> None:
    """Large summaries are split so each Discord message is <= 2000 chars."""
    respx.post(DM_CHANNEL_URL).mock(
        return_value=httpx.Response(200, json={"id": "99999"})
    )
    msg_route = respx.post(DM_MSG_URL).mock(
        return_value=httpx.Response(200, json={})
    )

    hotels = []
    for i in range(80):
        hotel_data = {
            **AVAILABLE_HOTEL_DATA,
            "hotelId": 2000 + i,
            "name": f"Hotel Very Long Name {i:03d} for SDCC Downtown Convention Area",
            "hotelChain": "Chain Name With Extra Words",
            "distance": 0.1 + (i / 100),
        }
        hotels.append(Hotel.model_validate(hotel_data))

    await send_discord_summary(_bot_settings(), hotels)

    assert msg_route.call_count > 1
    for call in msg_route.calls:
        payload = json.loads(call.request.content.decode("utf-8"))
        assert len(payload["content"]) <= 2000
