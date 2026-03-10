"""FRED API adapter for risk-free rate series.

FredAdapter intentionally does NOT subclass VendorAdapter — FRED exposes only
economic time-series data, not OHLC prices, quotes, or instrument search.
Forcing it to implement those methods would violate Interface Segregation.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_SERIES = "DTB3"  # 3-month T-bill, annualised percent


class FredAdapter:
    """Fetch risk-free rate observations from the St. Louis Fed (FRED).

    Values returned by FRED are expressed as annualised percentages; this
    adapter converts them to decimals (e.g. 5.25 → 0.0525) before returning.
    FRED missing-data sentinel "." is silently dropped.
    """

    _BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient()

    async def fetch_risk_free_series(
        self,
        start_date: date,
        end_date: date,
        series_code: str = _DEFAULT_SERIES,
    ) -> list[tuple[date, float]]:
        """Return (observation_date, rate_decimal) pairs for *series_code*.

        Args:
            start_date: First observation date (inclusive).
            end_date:   Last observation date (inclusive).
            series_code: FRED series ID; defaults to DTB3 (3-month T-bill).
        """
        response = await self._client.get(
            f"{self._BASE_URL}/series/observations",
            params={
                "series_id": series_code,
                "api_key": self._api_key,
                "file_type": "json",
                "observation_start": start_date.isoformat(),
                "observation_end": end_date.isoformat(),
            },
        )
        response.raise_for_status()
        data = response.json()

        return [
            (date.fromisoformat(obs["date"]), float(obs["value"]) / 100)
            for obs in data.get("observations", [])
            if obs["value"] != "."
        ]
