"""Thin async HTTP client for the OnPeak Compass availability API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from longshotel.config import Settings
from longshotel.models import Hotel


def _build_url(settings: Settings) -> str:
    """Construct the availability endpoint URL."""
    return (
        f"{settings.base_url}/e/{settings.event_code}"
        f"/{settings.block_index}/avail"
    )


def _build_params(settings: Settings) -> dict[str, str]:
    """Query-string parameters expected by the OnPeak API."""
    return {
        "arrive": settings.arrive,
        "depart": settings.depart,
        "_": str(int(time.time() * 1000)),  # cache-buster
    }


_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "longshotel/0.1.0",
}


async def fetch_hotels(
    settings: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[Hotel]:
    """Fetch the current hotel availability list.

    Parameters
    ----------
    settings:
        Application settings.  Defaults are used when *None*.
    client:
        An optional pre-built ``httpx.AsyncClient`` (useful for testing
        with ``respx``).

    Returns
    -------
    list[Hotel]
        Parsed hotel objects sorted by distance from the venue.
    """
    if settings is None:
        settings = Settings()

    url = _build_url(settings)
    params = _build_params(settings)

    if client is None:
        async with httpx.AsyncClient(headers=_HEADERS) as _client:
            resp = await _client.get(url, params=params, timeout=15)
    else:
        resp = await client.get(url, params=params, timeout=15)

    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    # The API returns hotels as a dict keyed by string index ("0", "1", …)
    raw_hotels: dict[str, Any] = data.get("hotels", {})

    hotels: list[Hotel] = []
    for _key, hotel_data in raw_hotels.items():
        try:
            hotels.append(Hotel.model_validate(hotel_data))
        except Exception:
            # Skip malformed entries but don't crash
            continue

    # Sort by distance from venue (closest first)
    hotels.sort(key=lambda h: h.distance)
    return hotels


async def fetch_available_hotels(
    settings: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[Hotel]:
    """Convenience wrapper that returns only hotels with rooms available."""
    hotels = await fetch_hotels(settings, client=client)
    return [h for h in hotels if h.is_available]
