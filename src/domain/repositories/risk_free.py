"""Risk-free rate repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date


class RiskFreeRepository(ABC):
    """Read/write interface for risk-free rate time-series data.

    Observations are upserted in bulk (no meaningful single-entity lifecycle).
    They are keyed by (series_code, obs_date) — each series_code identifies
    a FRED series such as DTB3 (3-month T-bill).
    """

    @abstractmethod
    async def bulk_upsert(
        self,
        source: str,
        series_code: str,
        observations: list[tuple[date, float]],
    ) -> int:
        """Upsert (date, rate) pairs for a given source and series.

        Returns the number of rows affected.
        source is a human-readable provider label (e.g. "FRED").
        series_code is the vendor's series identifier (e.g. "DTB3").
        rate is the annualised decimal rate (e.g. 0.0525 for 5.25 %).
        """

    @abstractmethod
    async def get_rate_on(
        self,
        obs_date: date,
        series_code: str = "DTB3",
    ) -> float | None:
        """Return the risk-free rate for the closest available date on or before obs_date.

        Returns None when no observations exist at or before obs_date.
        """

    @abstractmethod
    async def get_latest_rate(self, series_code: str = "DTB3") -> float | None:
        """Return the most recent risk-free rate for the given series, or None."""
