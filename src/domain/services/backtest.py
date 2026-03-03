"""Backtest service: rolling window estimation + rebalancing simulation.

Implements FR15 and DATA-MODEL.md:
  §4.8  — wealth index, drawdown, VaR, CVaR
  §4.10 — rebalancing, turnover, transaction cost model
  §4.12 — benchmark comparison (active return, tracking error, information ratio)

All methods are pure computation — no database access, no UUIDs.
The caller (command handler) is responsible for wrapping BacktestResult
into BacktestRun / BacktestPoint / BacktestSummary for persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.domain.models.backtest import BacktestConfig
from src.domain.models.enums import (
    BacktestStrategy,
    CovMethod,
    Estimator,
    RebalFrequency,
    ReturnType,
)
from src.domain.services.estimation import EstimationService
from src.domain.services.optimization import OptimizationService

logger = logging.getLogger(__name__)

_SURVIVORSHIP_BIAS_NOTE = (
    "Universe reflects assets as currently defined. "
    "Historical delistings are not adjusted (v1 limitation)."
)


# ─────────────────────────────────────────────────────────────────────────── #
# Output types (pure computation — no UUIDs)                                   #
# ─────────────────────────────────────────────────────────────────────────── #


@dataclass(frozen=True)
class BacktestPointResult:
    """Per-period observation from rolling backtest simulation.

    No UUIDs — pure computation layer.  The command handler wraps this into
    BacktestPoint for persistence.

    portfolio_value   — wealth index (starts at 1.0 at inception)
    portfolio_ret     — gross period return before transaction costs
    portfolio_ret_net — net-of-transaction-cost return
    benchmark_ret     — benchmark period return; None when no benchmark provided
    active_ret        — portfolio_ret_net − benchmark_ret; None when no benchmark
    turnover          — Σ|w_new − w_prev| on rebalance dates; 0.0 otherwise
    drawdown          — running DD_t = V_t / max(V_{u≤t}) − 1  (≤ 0)
    """

    obs_date: date
    portfolio_value: float
    portfolio_ret: float
    portfolio_ret_net: float
    benchmark_ret: float | None
    active_ret: float | None
    turnover: float
    drawdown: float


@dataclass(frozen=True)
class BacktestSummaryResult:
    """Aggregate performance statistics — pure computation, no UUIDs.

    max_drawdown ≤ 0 (DATA-MODEL.md §4.8 convention).
    var_95 / cvar_95 are positive loss magnitudes (−quantile / −expected shortfall).
    tracking_error and information_ratio are None when no benchmark is used.
    """

    total_return: float
    annualized_return: float
    annualized_vol: float
    sharpe: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    avg_turnover: float
    tracking_error: float | None
    information_ratio: float | None


@dataclass(frozen=True)
class BacktestResult:
    """Full backtest result from BacktestService.run_backtest().

    No UUIDs — pure computation layer.  The command handler wraps this into
    BacktestRun with BacktestPoint / BacktestSummary for persistence.
    """

    config: BacktestConfig
    points: list[BacktestPointResult]
    summary: BacktestSummaryResult
    survivorship_bias_note: str


# ─────────────────────────────────────────────────────────────────────────── #
# Service                                                                       #
# ─────────────────────────────────────────────────────────────────────────── #


class BacktestService:
    """Pure computation service for rolling backtest simulation.

    Responsibilities (single, focused):
      - Run rolling window estimation + rebalancing for MVP, tangency, or EW.
      - Apply transaction cost: net_return = gross_return − (bps/10_000) × turnover.
      - Compute all BacktestSummaryResult fields: Sharpe, drawdown, VaR/CVaR, TE, IR.
      - Generate survivorship bias note (always populated, FR15 / NFR).

    The class is stateless; all configuration is passed per-call.
    """

    def __init__(
        self,
        estimation_service: EstimationService,
        optimization_service: OptimizationService,
    ) -> None:
        self._estimation = estimation_service
        self._optimization = optimization_service

    # ─────────────────────────────────────────────────────────────────── #
    # Public API                                                           #
    # ─────────────────────────────────────────────────────────────────── #

    def run_backtest(
        self,
        config: BacktestConfig,
        prices: pd.DataFrame,
        annualization_factor: int,
        benchmark_prices: pd.Series | None = None,
    ) -> BacktestResult:
        """Run rolling backtest simulation.

        Algorithm:
          1. Compute simple returns (used for wealth compounding and estimation).
          2. Generate calendar rebalance dates (MONTHLY / QUARTERLY only).
          3. Iterate periods from window_length onwards:
             a. Rebalance when calendar date matches or drift threshold exceeded.
             b. On rebalance: estimate μ, Σ on lookback window → optimize weights.
             c. Compute gross return = w·r; apply transaction cost.
             d. Update wealth index and running drawdown.
             e. Drift weights to reflect price movements.
          4. Compute aggregate summary statistics.

        Simple returns are used throughout for wealth index compounding
        (DATA-MODEL.md §4.11 note; §4.8).

        Args:
            config: Strategy, rebalancing frequency, cost, and constraint params.
            prices: Adjusted close prices. DatetimeIndex; columns are assets.
            annualization_factor: Periods per year (252 daily / 52 weekly / 12 monthly).
            benchmark_prices: Optional benchmark price series with overlapping index.

        Returns:
            BacktestResult with per-period points and aggregate summary.

        Raises:
            ValueError: When prices has fewer rows than window_length + 1.
        """
        returns = self._estimation.compute_returns(prices, ReturnType.SIMPLE)
        obs_dates = returns.index
        n = prices.shape[1]

        if config.window_length >= len(returns):
            raise ValueError(
                f"window_length ({config.window_length}) must be less than the "
                f"number of return observations ({len(returns)})."
            )

        bench_series = _align_benchmark(benchmark_prices, returns.index)

        rebalance_date_set = self._build_rebalance_date_set(
            config, obs_dates, config.window_length
        )

        # Portfolio state
        actual_weights = np.ones(n) / n    # equal-weight before first rebalance
        target_weights = actual_weights.copy()
        portfolio_value = 1.0
        peak_value = 1.0
        tc_rate = config.transaction_cost_bps / 10_000
        first_period = True

        points: list[BacktestPointResult] = []

        for t in range(config.window_length, len(returns)):
            obs_date = obs_dates[t].date()
            r_t = returns.iloc[t].values  # shape (n,)

            is_rebalance = self._should_rebalance(
                first_period, obs_date, config, actual_weights, target_weights,
                rebalance_date_set,
            )
            first_period = False

            turnover = 0.0
            cost = 0.0
            if is_rebalance:
                lookback = returns.iloc[t - config.window_length:t]
                new_weights = self._compute_rebalance_weights(
                    config, lookback, actual_weights, annualization_factor
                )
                turnover = float(np.sum(np.abs(new_weights - actual_weights)))
                cost = tc_rate * turnover
                actual_weights = new_weights
                target_weights = new_weights.copy()

            gross_return = self._compute_period_return(actual_weights, r_t)
            net_return = gross_return - cost

            portfolio_value *= 1.0 + net_return
            peak_value = max(peak_value, portfolio_value)
            drawdown = portfolio_value / peak_value - 1.0

            # Drift actual weights for next period
            growth = actual_weights * (1.0 + r_t)
            total_growth = float(growth.sum())
            if total_growth > 1e-10:
                actual_weights = growth / total_growth

            bench_ret, active_ret = _extract_benchmark_return(bench_series, t, net_return)

            points.append(BacktestPointResult(
                obs_date=obs_date,
                portfolio_value=portfolio_value,
                portfolio_ret=gross_return,
                portfolio_ret_net=net_return,
                benchmark_ret=bench_ret,
                active_ret=active_ret,
                turnover=turnover,
                drawdown=drawdown,
            ))

        bench_array = _collect_benchmark_array(points)
        summary = self._compute_summary(points, bench_array, annualization_factor, config.rf)

        return BacktestResult(
            config=config,
            points=points,
            summary=summary,
            survivorship_bias_note=_SURVIVORSHIP_BIAS_NOTE,
        )

    def _generate_rebalance_dates(
        self,
        start: date,
        end: date,
        frequency: str,
    ) -> list[date]:
        """Generate candidate rebalance dates for calendar-based frequencies.

        Produces month-start (MONTHLY) or quarter-start (QUARTERLY) dates in
        [start, end].  Dates are candidates only; the caller maps them to actual
        trading days via _map_to_actual_dates.

        Args:
            start: First possible rebalance date (inclusive).
            end: Last possible rebalance date (inclusive).
            frequency: 'monthly' or 'quarterly'.

        Returns:
            Sorted list of candidate dates.

        Raises:
            ValueError: For unsupported frequency strings.
        """
        _FREQ_MAP = {"monthly": "MS", "quarterly": "QS"}
        if frequency not in _FREQ_MAP:
            raise ValueError(
                f"Unsupported calendar frequency: {frequency!r}. "
                "Expected 'monthly' or 'quarterly'."
            )
        dates = pd.date_range(start=start, end=end, freq=_FREQ_MAP[frequency])
        return [d.date() for d in dates]

    def _compute_period_return(
        self,
        weights: np.ndarray,
        asset_returns: np.ndarray,
    ) -> float:
        """Compute gross portfolio return for one period.

        DATA-MODEL.md §4.4: r_p = w' · r

        Args:
            weights: Asset weights, shape (n,). Must sum to 1.
            asset_returns: Per-asset simple returns for the period, shape (n,).

        Returns:
            Scalar gross portfolio return.
        """
        return float(np.dot(weights, asset_returns))

    def _compute_summary(
        self,
        points: list[BacktestPointResult],
        benchmark_returns: np.ndarray | None,
        annualization_factor: int,
        rf: float = 0.0,
    ) -> BacktestSummaryResult:
        """Compute aggregate summary statistics from per-period observations.

        Implements DATA-MODEL.md:
          §4.2  — annualized return = (1 + total)^(m/T) − 1; vol = √m · std(r)
          §4.4  — Sharpe = (μ_p − rf) / σ_p
          §4.8  — max drawdown via _compute_max_drawdown
          §4.8  — VaR / CVaR via _compute_var_cvar
          §4.12 — tracking error and information ratio

        Args:
            points: Per-period results (non-empty list).
            benchmark_returns: Aligned benchmark returns, same length as points;
                None when no benchmark was provided.
            annualization_factor: Periods per year (m).
            rf: Annualized risk-free rate for Sharpe computation.

        Returns:
            BacktestSummaryResult with all fields populated.
        """
        net_returns = np.array([p.portfolio_ret_net for p in points])
        values = np.array([p.portfolio_value for p in points])
        rebal_turnovers = np.array([p.turnover for p in points if p.turnover > 0.0])

        T = len(net_returns)
        total_return = float(values[-1] - 1.0)

        annualized_return = float(
            (1.0 + total_return) ** (annualization_factor / T) - 1.0
        )
        annualized_vol = float(
            np.std(net_returns, ddof=1) * np.sqrt(annualization_factor)
        )
        sharpe = (
            (annualized_return - rf) / annualized_vol
            if annualized_vol > 1e-12
            else 0.0
        )

        obs_dates = [p.obs_date for p in points]
        max_drawdown, _ = self._compute_max_drawdown(values, obs_dates)

        var_95, cvar_95 = self._compute_var_cvar(net_returns, alpha=0.05)

        avg_turnover = (
            float(np.mean(rebal_turnovers)) if len(rebal_turnovers) > 0 else 0.0
        )

        tracking_error = None
        information_ratio = None
        if benchmark_returns is not None and len(benchmark_returns) == T:
            active_returns = net_returns - benchmark_returns
            tracking_error = self._compute_tracking_error(
                net_returns, benchmark_returns, annualization_factor
            )
            information_ratio = self._compute_information_ratio(
                active_returns, tracking_error, annualization_factor
            )

        return BacktestSummaryResult(
            total_return=total_return,
            annualized_return=annualized_return,
            annualized_vol=annualized_vol,
            sharpe=sharpe,
            max_drawdown=max_drawdown,
            var_95=var_95,
            cvar_95=cvar_95,
            avg_turnover=avg_turnover,
            tracking_error=tracking_error,
            information_ratio=information_ratio,
        )

    def _compute_var_cvar(
        self,
        returns: np.ndarray,
        alpha: float = 0.05,
    ) -> tuple[float, float]:
        """Compute historical VaR and CVaR at confidence level (1 − alpha).

        DATA-MODEL.md §4.8:
          VaR_α  = −Quantile_α(r_p)                           (positive loss)
          CVaR_α = −E[r_p | r_p ≤ Quantile_α(r_p)]           (positive loss)

        Supported alpha values: 0.05 (95% confidence) and 0.01 (99%).

        Args:
            returns: 1-D array of period returns.
            alpha: Left-tail probability (default 0.05 = 95% confidence).

        Returns:
            (var, cvar) — both ≥ 0, representing loss magnitudes.
        """
        q = float(np.quantile(returns, alpha))
        var = max(0.0, -q)
        tail = returns[returns <= q]
        raw_cvar = -float(np.mean(tail)) if len(tail) > 0 else -q
        cvar = max(0.0, raw_cvar)
        return var, cvar

    def _compute_max_drawdown(
        self,
        values: np.ndarray,
        dates: list[date] | None = None,
    ) -> tuple[float, date | None]:
        """Compute maximum drawdown and the date of the portfolio trough.

        DATA-MODEL.md §4.8:
          DD_t = V_t / max(V_{u≤t}) − 1
          MDD  = min_t DD_t  (≤ 0)

        Args:
            values: Wealth index array V_t, shape (T,).
            dates: Observation dates aligned to values; None to omit date output.

        Returns:
            (mdd, trough_date) where mdd ≤ 0.  trough_date is the date at which
            the portfolio reached its lowest point relative to the prior peak;
            None when dates is not provided.
        """
        running_peak = np.maximum.accumulate(values)
        drawdowns = values / running_peak - 1.0
        trough_idx = int(np.argmin(drawdowns))
        mdd = float(drawdowns[trough_idx])
        trough_date = dates[trough_idx] if dates is not None else None
        return mdd, trough_date

    def _compute_tracking_error(
        self,
        portfolio_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        annualization_factor: int,
    ) -> float:
        """Compute annualized tracking error vs benchmark.

        DATA-MODEL.md §4.12:
          TE = √m · s(α_t)   where   α_t = r_{p,t} − r_{b,t}

        Args:
            portfolio_returns: Per-period net portfolio returns, shape (T,).
            benchmark_returns: Per-period benchmark returns, shape (T,).
            annualization_factor: Periods per year (m).

        Returns:
            Annualized tracking error ≥ 0.
        """
        active = portfolio_returns - benchmark_returns
        return float(np.std(active, ddof=1) * np.sqrt(annualization_factor))

    def _compute_information_ratio(
        self,
        active_returns: np.ndarray,
        tracking_error: float,
        annualization_factor: int,
    ) -> float:
        """Compute information ratio.

        DATA-MODEL.md §4.12:
          IR = ᾱ · m / TE

        Where ᾱ is the mean per-period active return and TE is already annualized.

        Args:
            active_returns: Per-period active returns (r_p − r_b), shape (T,).
            tracking_error: Annualized tracking error from _compute_tracking_error.
            annualization_factor: Periods per year (m).

        Returns:
            Information ratio; 0.0 when tracking_error is effectively zero.
        """
        if tracking_error < 1e-12:
            return 0.0
        mean_active_annual = float(np.mean(active_returns)) * annualization_factor
        return mean_active_annual / tracking_error

    # ─────────────────────────────────────────────────────────────────── #
    # Private helpers                                                      #
    # ─────────────────────────────────────────────────────────────────── #

    def _build_rebalance_date_set(
        self,
        config: BacktestConfig,
        obs_dates: pd.DatetimeIndex,
        start_idx: int,
    ) -> set[date]:
        """Map calendar rebalance candidates to actual trading dates.

        Returns an empty set for THRESHOLD rebalancing (handled per-period).
        """
        if config.rebal_freq == RebalFrequency.THRESHOLD:
            return set()

        start_date = obs_dates[start_idx].date()
        end_date = obs_dates[-1].date()
        candidates = self._generate_rebalance_dates(
            start_date, end_date, config.rebal_freq.value
        )
        actual_dates = [d.date() for d in obs_dates[start_idx:]]
        return _map_to_actual_dates(candidates, actual_dates)

    def _should_rebalance(
        self,
        first_period: bool,
        obs_date: date,
        config: BacktestConfig,
        actual_weights: np.ndarray,
        target_weights: np.ndarray,
        rebalance_date_set: set[date],
    ) -> bool:
        """Determine whether to rebalance at the start of this period."""
        if first_period:
            return True
        if config.rebal_freq == RebalFrequency.THRESHOLD:
            drift = np.abs(actual_weights - target_weights)
            return float(np.max(drift)) > config.rebal_threshold  # type: ignore[arg-type]
        return obs_date in rebalance_date_set

    def _compute_rebalance_weights(
        self,
        config: BacktestConfig,
        lookback: pd.DataFrame,
        prev_weights: np.ndarray,
        annualization_factor: int,
    ) -> np.ndarray:
        """Compute new target weights for a rebalance period.

        EW_REBAL:      returns 1/n for all n assets.
        MVP_REBAL:     minimises portfolio variance.
        TANGENCY_REBAL: maximises Sharpe ratio using config.rf.

        Uses HISTORICAL mean and SAMPLE covariance on the lookback window.
        Applies nearest-PSD repair when the sample covariance is not PSD
        (common for short windows relative to the number of assets).

        Falls back to prev_weights and logs a warning on infeasible optimization.

        Args:
            config: BacktestConfig providing strategy, rf, and constraints.
            lookback: Slice of the returns DataFrame for the estimation window.
            prev_weights: Weights held before the rebalance (used for turnover
                constraint and as fallback on infeasibility).
            annualization_factor: Periods per year passed to estimation.

        Returns:
            New target weight array, shape (n,).
        """
        n = lookback.shape[1]

        if config.strategy == BacktestStrategy.EW_REBAL:
            return np.ones(n) / n

        mu = self._estimation.compute_mu(
            lookback, annualization_factor, estimator=Estimator.HISTORICAL
        )
        sigma = self._estimation.compute_sigma(
            lookback, annualization_factor, method=CovMethod.SAMPLE
        )

        is_psd, _ = self._estimation.validate_psd(sigma)
        if not is_psd:
            sigma, note = self._estimation.repair_psd(sigma)
            logger.warning("Backtest: covariance PSD repair applied: %s", note)

        if config.strategy == BacktestStrategy.TANGENCY_REBAL:
            result = self._optimization.optimize_tangency(
                mu, sigma, config.rf, config.constraints, prev_weights=prev_weights
            )
        else:  # MVP_REBAL
            result = self._optimization.optimize_mvp(
                mu, sigma, config.constraints, prev_weights=prev_weights
            )

        if result.is_feasible and result.weights is not None:
            return result.weights

        logger.warning(
            "Backtest: optimization infeasible at rebalance (%s); holding prev weights.",
            result.infeasibility_reason,
        )
        return prev_weights.copy()


# ─────────────────────────────────────────────────────────────────────────── #
# Module-level helpers                                                          #
# ─────────────────────────────────────────────────────────────────────────── #


def _map_to_actual_dates(
    candidates: list[date],
    actual_dates: list[date],
) -> set[date]:
    """Map candidate calendar dates to the first actual trading date on or after each.

    For example, a month-start candidate of Feb 1 maps to the first trading day
    in February (e.g. Feb 3 for daily data, or Feb 28 for month-end data).

    Args:
        candidates: Candidate rebalance dates from _generate_rebalance_dates.
        actual_dates: Actual observed dates in the prices index (sorted ascending).

    Returns:
        Set of actual trading dates that will trigger a rebalance.
    """
    result: set[date] = set()
    sorted_actual = sorted(actual_dates)
    for cand in candidates:
        for actual in sorted_actual:
            if actual >= cand:
                result.add(actual)
                break
    return result


def _align_benchmark(
    benchmark_prices: pd.Series | None,
    index: pd.DatetimeIndex,
) -> pd.Series | None:
    """Compute and align benchmark simple returns to the prices index."""
    if benchmark_prices is None:
        return None
    bench = benchmark_prices.pct_change().dropna().reindex(index)
    return bench


def _extract_benchmark_return(
    bench_series: pd.Series | None,
    t: int,
    net_return: float,
) -> tuple[float | None, float | None]:
    """Return (benchmark_ret, active_ret) for period t, or (None, None)."""
    if bench_series is None:
        return None, None
    bval = bench_series.iloc[t]
    if np.isnan(bval):
        return None, None
    bench_ret = float(bval)
    active_ret = net_return - bench_ret
    return bench_ret, active_ret


def _collect_benchmark_array(
    points: list[BacktestPointResult],
) -> np.ndarray | None:
    """Build an aligned benchmark return array from points.

    Returns None (suppressing TE/IR) when any period lacks a benchmark value,
    since partial coverage would produce misleading statistics.
    """
    bench_vals = [p.benchmark_ret for p in points]
    if all(v is not None for v in bench_vals):
        return np.array(bench_vals, dtype=float)
    if any(v is not None for v in bench_vals):
        logger.warning(
            "Benchmark missing on %d/%d period(s); TE and IR will not be computed.",
            sum(v is None for v in bench_vals),
            len(bench_vals),
        )
    return None
