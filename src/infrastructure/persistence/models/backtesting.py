"""Backtesting layer ORM models: backtest_runs, backtest_points, backtest_summary."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Double, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class BacktestRun(Base):
    """Configuration and metadata for a historical backtest simulation.

    survivorship_bias_note is always populated to document the known limitation.
    benchmark_asset_id is nullable — not all backtests require a benchmark.
    """

    __tablename__ = "backtest_runs"

    backtest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universes.universe_id"), nullable=False
    )
    benchmark_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), nullable=True
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)      # TANGENCY_REBAL / MVP_REBAL / EW_REBAL
    rebal_freq: Mapped[str] = mapped_column(Text, nullable=False)     # monthly / quarterly / threshold
    rebal_threshold: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    window_length: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_cost_bps: Mapped[float] = mapped_column(Double, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False)
    survivorship_bias_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    universe: Mapped["Universe"] = relationship(
        "Universe", foreign_keys=[universe_id], back_populates="backtest_runs"
    )
    benchmark_asset: Mapped[Optional["Asset"]] = relationship(
        "Asset", foreign_keys=[benchmark_asset_id], back_populates="backtest_benchmark_roles"
    )
    points: Mapped[list["BacktestPoint"]] = relationship(
        back_populates="backtest_run", cascade="all, delete-orphan"
    )
    summary: Mapped[Optional["BacktestSummary"]] = relationship(
        back_populates="backtest_run", uselist=False, cascade="all, delete-orphan"
    )


class BacktestPoint(Base):
    """Daily time-series observation within a backtest.

    turnover is stored as 0.0 (not NULL) on non-rebalance dates to simplify
    aggregation (e.g. SUM(turnover)) without COALESCE.
    Composite PK: (backtest_id, obs_date).
    """

    __tablename__ = "backtest_points"

    backtest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.backtest_id", ondelete="CASCADE"),
        primary_key=True,
    )
    obs_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    portfolio_value: Mapped[float] = mapped_column(Double, nullable=False)
    portfolio_ret: Mapped[float] = mapped_column(Double, nullable=False)
    portfolio_ret_net: Mapped[float] = mapped_column(Double, nullable=False)
    benchmark_ret: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    active_ret: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    turnover: Mapped[float] = mapped_column(Double, nullable=False)   # 0.0 on non-rebal dates
    drawdown: Mapped[float] = mapped_column(Double, nullable=False)

    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="points")


class BacktestSummary(Base):
    """Aggregate performance statistics for a completed backtest.

    1:1 with BacktestRun — backtest_id is both PK and FK.
    """

    __tablename__ = "backtest_summary"

    backtest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backtest_runs.backtest_id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_return: Mapped[float] = mapped_column(Double, nullable=False)
    annualized_return: Mapped[float] = mapped_column(Double, nullable=False)
    annualized_vol: Mapped[float] = mapped_column(Double, nullable=False)
    sharpe: Mapped[float] = mapped_column(Double, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Double, nullable=False)
    var_95: Mapped[float] = mapped_column(Double, nullable=False)
    cvar_95: Mapped[float] = mapped_column(Double, nullable=False)
    avg_turnover: Mapped[float] = mapped_column(Double, nullable=False)
    tracking_error: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    information_ratio: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    backtest_run: Mapped["BacktestRun"] = relationship(back_populates="summary")
