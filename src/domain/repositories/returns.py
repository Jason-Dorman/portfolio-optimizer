"""Return series repository interface.

ReturnRepository is a specialised time-series interface and does not extend
the generic Repository[T] base — return points are derived from price bars,
inserted in bulk, and queried by asset + date range + return type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from src.domain.models.enums import Frequency, ReturnType
from src.domain.models.market_data import ReturnPoint


class ReturnRepository(ABC):
    """Read/write interface for return series data."""

    @abstractmethod
    async def get_returns(
        self,
        asset_id: UUID,
        frequency: Frequency,
        return_type: ReturnType,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ReturnPoint]:
        """Return computed return points for one asset in ascending date order.

        start and end are inclusive.  When omitted the full available history
        for the given frequency and return_type is returned.
        """

    @abstractmethod
    async def bulk_insert(self, points: list[ReturnPoint]) -> int:
        """Upsert return points (insert or update on conflict).

        Returns the number of rows affected.  All points in a single call must
        share the same frequency and return_type.
        """
