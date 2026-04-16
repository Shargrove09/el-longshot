"""Application configuration via environment variables / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All tuneable knobs live here.

    Override any value with an environment variable prefixed ``LONGSHOTEL_``,
    e.g. ``LONGSHOTEL_ARRIVE=2026-07-20``.
    """

    # ── OnPeak event parameters ──────────────────────────────────────────
    event_code: str = "43CCI2026HIR"
    """The event slug that appears in the Compass URL path."""

    block_index: int = 3
    """The block index that appears before ``/avail`` in the URL."""

    base_url: str = "https://compass.onpeak.com"
    """OnPeak Compass base URL."""

    arrive: str = "2026-07-21"
    """Check-in date in YYYY-MM-DD format."""

    depart: str = "2026-07-27"
    """Check-out date in YYYY-MM-DD format."""

    # ── Monitoring ───────────────────────────────────────────────────────
    poll_interval_seconds: int = 60
    """How often to poll the API when running in monitor mode."""

    # ── Notifications (optional) ─────────────────────────────────────────
    discord_webhook_url: str | None = None
    """If set, availability changes are posted to this Discord webhook."""

    # ── Display ──────────────────────────────────────────────────────────
    show_soldout: bool = False
    """Whether to display sold-out hotels in the results table."""

    model_config = {"env_prefix": "LONGSHOTEL_", "env_file": ".env"}
