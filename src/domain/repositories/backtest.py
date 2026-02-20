"""Backtest repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.backtest import BacktestPoint, BacktestRun, BacktestSummary

from .base import Repository


class BacktestRepository(Repository[BacktestRun]):
    """Read/write interface for BacktestRun aggregates.

    Backtest runs are immutable after creation.  create() persists the run,
    the full time-series (points), and the summary stats atomically.

    get_points() and get_summary() allow lightweight access to sub-components
    without loading the full run (which may contain hundreds of BacktestPoints).
    """

    async def get(self, id: UUID) -> BacktestRun | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, backtest_id: UUID) -> BacktestRun | None:
        """Return the backtest run with embedded points and summary, or None."""

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[BacktestRun]:
        """Return a page of backtest runs ordered by creation time descending."""

    @abstractmethod
    async def create(self, entity: BacktestRun) -> BacktestRun:
        """Persist the run, all time-series points, and the summary atomically."""

    @abstractmethod
    async def get_points(self, backtest_id: UUID) -> list[BacktestPoint]:
        """Return all time-series observations for the backtest in ascending date order."""

    @abstractmethod
    async def get_summary(self, backtest_id: UUID) -> BacktestSummary | None:
        """Return aggregate performance statistics for the backtest, or None."""
