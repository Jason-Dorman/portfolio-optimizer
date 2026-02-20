"""Price repository interface.

PriceRepository is a specialised time-series interface and does not extend
the generic Repository[T] base — price bars have no meaningful single-entity
CRUD lifecycle.  They are ingested in bulk and queried by asset + date range.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from src.domain.models.enums import Frequency
from src.domain.models.market_data import PriceBar


class PriceRepository(ABC):
    """Read/write interface for price bar time-series data."""

    @abstractmethod
    async def get_prices(
        self,
        asset_id: UUID,
        frequency: Frequency,
        start: date | None = None,
        end: date | None = None,
    ) -> list[PriceBar]:
        """Return price bars for one asset in ascending date order.

        start and end are inclusive.  When omitted the full available history
        is returned for the given frequency.
        """

    @abstractmethod
    async def get_latest_date(self, asset_id: UUID, frequency: Frequency) -> date | None:
        """Return the most recent bar_date for the asset/frequency pair, or None."""

    @abstractmethod
    async def bulk_insert(self, bars: list[PriceBar]) -> int:
        """Upsert price bars (insert or update on conflict).

        Returns the number of rows affected.  All bars must share the same
        frequency; mixed frequencies in a single call are not supported.
        """
