"""Backtest domain models.

BacktestConfig  — strategy and estimation parameters for a backtest run
BacktestPoint   — per-period observation (portfolio value, returns, drawdown)
BacktestSummary — aggregate performance statistics for a completed backtest
BacktestRun     — run configuration with full history and summary
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import BacktestStrategy, RebalFrequency


class BacktestConfig(BaseModel):
    """Strategy and simulation parameters for a backtest run.

    rebal_threshold is required when rebal_freq is THRESHOLD and ignored
    for calendar-based frequencies (MONTHLY / QUARTERLY).

    transaction_cost_bps is expressed in basis points (e.g. 10 = 10 bps = 0.10 %).
    Internally the cost model is: cost = (transaction_cost_bps / 10_000) × turnover.
    """

    model_config = ConfigDict(frozen=True)

    strategy: BacktestStrategy
    rebal_freq: RebalFrequency
    rebal_threshold: float | None = Field(default=None, gt=0.0, le=1.0)
    window_length: int = Field(gt=0)  # lookback in periods (consistent with frequency)
    transaction_cost_bps: float = Field(default=0.0, ge=0.0)
    constraints: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _threshold_required_when_freq_threshold(self) -> BacktestConfig:
        if self.rebal_freq == RebalFrequency.THRESHOLD and self.rebal_threshold is None:
            raise ValueError(
                "rebal_threshold is required when rebal_freq is THRESHOLD"
            )
        return self


class BacktestPoint(BaseModel):
    """A single period observation in the backtest time series.

    portfolio_value   — wealth index (starts at 1.0 at inception)
    portfolio_ret     — gross period return
    portfolio_ret_net — net-of-transaction-cost return
    benchmark_ret     — benchmark return same period; None if no benchmark
    active_ret        — portfolio_ret_net − benchmark_ret; None if no benchmark
    turnover          — rebalancing turnover on this date; 0.0 on non-rebalance dates
    drawdown          — running drawdown DD_t = V_t / max(V_u≤t) − 1  (≤ 0)
    """

    model_config = ConfigDict(frozen=True)

    backtest_id: UUID
    obs_date: date
    portfolio_value: float = Field(gt=0.0)
    portfolio_ret: float
    portfolio_ret_net: float
    benchmark_ret: float | None = None
    active_ret: float | None = None
    turnover: float = Field(default=0.0, ge=0.0)
    drawdown: float = Field(le=0.0)

    @model_validator(mode="after")
    def _active_ret_consistent(self) -> BacktestPoint:
        if self.benchmark_ret is not None and self.active_ret is None:
            raise ValueError(
                "active_ret must be set when benchmark_ret is provided"
            )
        if self.benchmark_ret is None and self.active_ret is not None:
            raise ValueError(
                "active_ret must be None when benchmark_ret is None"
            )
        return self


class BacktestSummary(BaseModel):
    """Aggregate performance statistics for a completed backtest.

    max_drawdown ≤ 0 (drawdown convention from DATA-MODEL.md §4.8).
    var_95 / cvar_95 are positive values representing loss magnitudes:
      VaR_α  = −Quantile_α(r)
      CVaR_α = −E[r | r ≤ Quantile_α(r)]
    tracking_error and information_ratio are None when no benchmark is used.
    """

    model_config = ConfigDict(frozen=True)

    backtest_id: UUID
    total_return: float
    annualized_return: float
    annualized_vol: float = Field(ge=0.0)
    sharpe: float
    max_drawdown: float = Field(le=0.0)
    var_95: float = Field(ge=0.0)
    cvar_95: float = Field(ge=0.0)
    avg_turnover: float = Field(ge=0.0)
    tracking_error: float | None = Field(default=None, ge=0.0)
    information_ratio: float | None = None


class BacktestRun(BaseModel):
    """A backtest run with its full history and aggregate summary.

    survivorship_bias_note is always populated — it documents the known
    limitation that the universe reflects assets as currently defined and
    historical delistings are not adjusted (per SYSTEM-SPEC.md §1.5).
    """

    backtest_id: UUID = Field(default_factory=uuid4)
    universe_id: UUID
    benchmark_asset_id: UUID | None = None
    config: BacktestConfig
    survivorship_bias_note: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    points: list[BacktestPoint] = Field(default_factory=list)
    summary: BacktestSummary | None = None

    @classmethod
    def create(
        cls,
        universe_id: UUID,
        config: BacktestConfig,
        benchmark_asset_id: UUID | None = None,
        survivorship_bias_note: str = (
            "Universe reflects assets as currently defined. "
            "Historical delistings are not adjusted (v1 limitation)."
        ),
    ) -> BacktestRun:
        return cls(
            universe_id=universe_id,
            benchmark_asset_id=benchmark_asset_id,
            config=config,
            survivorship_bias_note=survivorship_bias_note,
        )
