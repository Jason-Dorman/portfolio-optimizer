"""Schwab MarketData v1 API adapter.

Handles:
  - Historical OHLC bars  (GET /pricehistory)
  - Real-time quotes      (GET /quotes)
  - Instrument search     (GET /instruments)

Authentication is delegated to SchwabOAuthService; this adapter never
stores credentials or tokens directly (Dependency Inversion).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING

import httpx

from src.domain.models.enums import Frequency
from src.infrastructure.vendors.base import VendorAdapter
from src.infrastructure.vendors.exceptions import AuthenticationRequired, RateLimitError
from src.infrastructure.vendors.schemas import VendorPriceBar

if TYPE_CHECKING:
    from src.infrastructure.auth.schwab_oauth import SchwabOAuthService

logger = logging.getLogger(__name__)

_FREQ_MAP: dict[Frequency, str] = {
    Frequency.DAILY: "daily",
    Frequency.WEEKLY: "weekly",
    Frequency.MONTHLY: "monthly",
}


def _to_epoch_ms(d: date) -> int:
    """Convert a calendar date to UTC-midnight epoch milliseconds."""
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp() * 1000)


def _parse_candle(candle: dict, ticker: str, frequency: Frequency, pulled_at: datetime) -> VendorPriceBar:
    bar_date = datetime.fromtimestamp(candle["datetime"] / 1000, tz=timezone.utc).date()
    return VendorPriceBar(
        ticker=ticker,
        bar_date=bar_date,
        frequency=frequency,
        open=candle["open"],
        high=candle["high"],
        low=candle["low"],
        close=candle["close"],
        volume=candle.get("volume"),
        pulled_at=pulled_at,
    )


class SchwabAdapter(VendorAdapter):
    """Adapter for the Schwab MarketData v1 API."""

    _BASE_URL = "https://api.schwabapi.com/marketdata/v1"

    def __init__(self, oauth_service: SchwabOAuthService) -> None:
        self._oauth = oauth_service
        self._client = httpx.AsyncClient()

    # ------------------------------------------------------------------ #
    # VendorAdapter interface                                              #
    # ------------------------------------------------------------------ #

    async def fetch_price_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        frequency: Frequency,
    ) -> list[VendorPriceBar]:
        params = {
            "symbol": ticker,
            "periodType": "year",
            "frequencyType": _FREQ_MAP[frequency],
            "frequency": 1,
            "startDate": _to_epoch_ms(start_date),
            "endDate": _to_epoch_ms(end_date),
        }
        response = await self._get(f"{self._BASE_URL}/pricehistory", params)
        data = response.json()
        pulled_at = datetime.now(timezone.utc)
        return [
            _parse_candle(candle, ticker, frequency, pulled_at)
            for candle in data.get("candles", [])
        ]

    async def get_quotes(self, tickers: list[str]) -> dict[str, float]:
        response = await self._get(
            f"{self._BASE_URL}/quotes",
            {"symbols": ",".join(tickers)},
        )
        data = response.json()
        return {
            symbol: quote["quote"]["lastPrice"]
            for symbol, quote in data.items()
        }

    async def search_instruments(self, query: str) -> list[dict]:
        response = await self._get(
            f"{self._BASE_URL}/instruments",
            {"symbol": query, "projection": "symbol-search"},
        )
        data = response.json()
        return [
            {
                "ticker": item["symbol"],
                "name": item.get("description", ""),
                "exchange": item.get("exchange", ""),
                "asset_type": item.get("assetType", ""),
            }
            for item in data.get("instruments", [])
        ]

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _get_headers(self) -> dict[str, str]:
        token = await self._oauth.get_valid_access_token()
        if not token:
            raise AuthenticationRequired(
                "Schwab not connected. Please connect in Settings."
            )
        return {"Authorization": f"Bearer {token}"}

    async def _get(self, url: str, params: dict) -> httpx.Response:
        """Execute a GET request, retrying once after a token refresh on 401."""
        headers = await self._get_headers()
        response = await self._client.get(url, headers=headers, params=params)

        if response.status_code == 401:
            refreshed = await self._oauth.refresh_access_token()
            if not refreshed:
                raise AuthenticationRequired("Session expired. Please reconnect.")
            headers = await self._get_headers()
            response = await self._client.get(url, headers=headers, params=params)

        if response.status_code == 429:
            raise RateLimitError("Schwab rate limit reached. Please wait.")

        response.raise_for_status()
        return response
