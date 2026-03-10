"""Abstract base for all vendor adapters.

Every concrete adapter must implement all three methods.  The interface is
intentionally narrow — if a vendor does not support a method (e.g. no
search), raise NotImplementedError rather than adding optional methods here
(Interface Segregation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.models.enums import Frequency
from src.infrastructure.vendors.schemas import VendorPriceBar


class VendorAdapter(ABC):
    """Contract every market-data vendor adapter must satisfy."""

    @abstractmethod
    async def fetch_price_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        frequency: Frequency,
    ) -> list[VendorPriceBar]:
        """Fetch historical OHLC bars for one ticker."""

    @abstractmethod
    async def get_quotes(self, tickers: list[str]) -> dict[str, float]:
        """Return current last-price for each ticker.

        Keys are the tickers as provided; missing tickers are omitted.
        """

    @abstractmethod
    async def search_instruments(self, query: str) -> list[dict]:
        """Search for instruments matching a query string.

        Each result dict contains at minimum:
            ticker     (str)
            name       (str)
            exchange   (str)
            asset_type (str)
        """
