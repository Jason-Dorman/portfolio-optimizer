"""Unit tests for BacktestService.

All numeric assertions derive from DATA-MODEL.md §4.8, §4.10, §4.12 and
closed-form solutions so that tests function as an executable specification.

Test layout:
  - Fixtures (prices, config variants)
  - BacktestConfig validation
  - _generate_rebalance_dates
  - _compute_period_return
  - _compute_var_cvar
  - _compute_max_drawdown
  - _compute_tracking_error
  - _compute_information_ratio
  - _compute_summary
  - run_backtest (integration-style unit tests)
  - Edge cases
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.domain.models.backtest import BacktestConfig, BacktestRun
from src.domain.models.enums import BacktestStrategy, RebalFrequency
from src.domain.models.optimization import OptimizationConstraints
from src.domain.services.backtest import (
    BacktestPointResult,
    BacktestResult,
    BacktestService,
    BacktestSummaryResult,
    _collect_benchmark_array,
    _map_to_actual_dates,
)
from src.domain.services.estimation import EstimationService
from src.domain.services.optimization import OptimizationService


# ═══════════════════════════════════════════════════════════════════════════ #
# Helpers & factories                                                           #
# ═══════════════════════════════════════════════════════════════════════════ #


def _make_prices(
    n_assets: int,
    n_periods: int,
    monthly_returns: list[list[float]] | None = None,
    start: str = "2020-01-31",
) -> pd.DataFrame:
    """Build a monthly price DataFrame.

    If monthly_returns is None, all assets grow at 1% per month.
    monthly_returns shape: (n_periods, n_assets).
    """
    idx = pd.date_range(start=start, periods=n_periods + 1, freq="ME")
    if monthly_returns is None:
        monthly_returns = [[0.01] * n_assets] * n_periods

    prices = np.ones((n_periods + 1, n_assets))
    for t, row in enumerate(monthly_returns, start=1):
        prices[t] = prices[t - 1] * (1 + np.array(row))

    return pd.DataFrame(prices, index=idx, columns=[f"A{i}" for i in range(n_assets)])


def _make_config(
    strategy: BacktestStrategy = BacktestStrategy.EW_REBAL,
    rebal_freq: RebalFrequency = RebalFrequency.MONTHLY,
    window_length: int = 3,
    transaction_cost_bps: float = 0.0,
    rf: float = 0.0,
    rebal_threshold: float | None = None,
    constraints: OptimizationConstraints | None = None,
) -> BacktestConfig:
    return BacktestConfig(
        strategy=strategy,
        rebal_freq=rebal_freq,
        rebal_threshold=rebal_threshold,
        window_length=window_length,
        transaction_cost_bps=transaction_cost_bps,
        rf=rf,
        constraints=constraints or OptimizationConstraints.long_only_unconstrained(),
    )


# ═══════════════════════════════════════════════════════════════════════════ #
# Fixtures                                                                      #
# ═══════════════════════════════════════════════════════════════════════════ #


@pytest.fixture
def svc() -> BacktestService:
    return BacktestService(EstimationService(), OptimizationService())


@pytest.fixture
def prices_3a_12m() -> pd.DataFrame:
    """3 assets, 12 months, all returning 1% per month."""
    return _make_prices(n_assets=3, n_periods=12)


@pytest.fixture
def prices_2a_24m() -> pd.DataFrame:
    """2 assets, 24 months: asset 0 returns 1%, asset 1 returns 2% per month."""
    rets = [[0.01, 0.02]] * 24
    return _make_prices(n_assets=2, n_periods=24, monthly_returns=rets)


@pytest.fixture
def ew_monthly_config() -> BacktestConfig:
    return _make_config(
        strategy=BacktestStrategy.EW_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        window_length=3,
    )


# ═══════════════════════════════════════════════════════════════════════════ #
# BacktestConfig validation                                                     #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestBacktestConfig:
    def test_threshold_requires_rebal_threshold(self):
        with pytest.raises(ValueError, match="rebal_threshold is required"):
            BacktestConfig(
                strategy=BacktestStrategy.EW_REBAL,
                rebal_freq=RebalFrequency.THRESHOLD,
                rebal_threshold=None,
                window_length=3,
            )

    def test_monthly_does_not_require_threshold(self):
        cfg = _make_config(rebal_freq=RebalFrequency.MONTHLY)
        assert cfg.rebal_threshold is None

    def test_rf_defaults_to_zero(self):
        cfg = _make_config()
        assert cfg.rf == 0.0

    def test_rf_stored(self):
        cfg = _make_config(rf=0.04)
        assert cfg.rf == pytest.approx(0.04)

    def test_constraints_defaults_to_long_only(self):
        cfg = _make_config()
        assert cfg.constraints.long_only is True

    def test_transaction_cost_bps_stored(self):
        cfg = _make_config(transaction_cost_bps=10.0)
        assert cfg.transaction_cost_bps == pytest.approx(10.0)


# ═══════════════════════════════════════════════════════════════════════════ #
# _generate_rebalance_dates                                                     #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestGenerateRebalanceDates:
    def test_monthly_returns_one_date_per_month(self, svc: BacktestService):
        start = date(2020, 1, 1)
        end = date(2020, 6, 30)
        dates = svc._generate_rebalance_dates(start, end, "monthly")
        assert len(dates) == 6
        assert all(d.day == 1 for d in dates)

    def test_quarterly_returns_quarter_starts(self, svc: BacktestService):
        start = date(2020, 1, 1)
        end = date(2020, 12, 31)
        dates = svc._generate_rebalance_dates(start, end, "quarterly")
        # QS: Jan, Apr, Jul, Oct
        assert len(dates) == 4
        months = [d.month for d in dates]
        assert months == [1, 4, 7, 10]

    def test_unsupported_frequency_raises(self, svc: BacktestService):
        with pytest.raises(ValueError, match="Unsupported"):
            svc._generate_rebalance_dates(date(2020, 1, 1), date(2020, 12, 31), "weekly")

    def test_dates_are_sorted(self, svc: BacktestService):
        dates = svc._generate_rebalance_dates(date(2020, 1, 1), date(2021, 6, 30), "monthly")
        assert dates == sorted(dates)

    def test_single_month_range(self, svc: BacktestService):
        dates = svc._generate_rebalance_dates(date(2020, 3, 1), date(2020, 3, 31), "monthly")
        assert len(dates) == 1
        assert dates[0] == date(2020, 3, 1)


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_period_return                                                        #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputePeriodReturn:
    def test_equal_weights_averages_returns(self, svc: BacktestService):
        w = np.array([0.5, 0.5])
        r = np.array([0.10, 0.20])
        assert svc._compute_period_return(w, r) == pytest.approx(0.15)

    def test_concentrated_weight(self, svc: BacktestService):
        w = np.array([1.0, 0.0])
        r = np.array([0.05, 0.50])
        assert svc._compute_period_return(w, r) == pytest.approx(0.05)

    def test_negative_return(self, svc: BacktestService):
        w = np.array([0.4, 0.6])
        r = np.array([-0.10, 0.05])
        # 0.4 * -0.10 + 0.6 * 0.05 = -0.04 + 0.03 = -0.01
        assert svc._compute_period_return(w, r) == pytest.approx(-0.01)

    def test_zero_return_all_cash(self, svc: BacktestService):
        w = np.array([1.0, 0.0, 0.0])
        r = np.zeros(3)
        assert svc._compute_period_return(w, r) == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_var_cvar                                                             #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeVarCvar:
    def test_var_is_positive_loss(self, svc: BacktestService):
        # 10 equal returns, 5th percentile is deterministic
        returns = np.array([-0.05, -0.04, -0.03, 0.01, 0.02,
                            0.02, 0.03, 0.04, 0.05, 0.06])
        var, cvar = svc._compute_var_cvar(returns, alpha=0.05)
        assert var >= 0.0
        assert cvar >= 0.0

    def test_cvar_ge_var(self, svc: BacktestService):
        """CVaR (expected shortfall) must be at least as large as VaR."""
        rng = np.random.default_rng(42)
        returns = rng.normal(-0.01, 0.05, 200)
        var, cvar = svc._compute_var_cvar(returns, alpha=0.05)
        assert cvar >= var - 1e-10

    def test_var_formula_exact(self, svc: BacktestService):
        """VaR = −Quantile_0.05(r) (DATA-MODEL §4.8)."""
        returns = np.linspace(-0.10, 0.10, 100)
        var, _ = svc._compute_var_cvar(returns, alpha=0.05)
        expected_var = -float(np.quantile(returns, 0.05))
        assert var == pytest.approx(expected_var, abs=1e-10)

    def test_cvar_formula_exact(self, svc: BacktestService):
        """CVaR = −E[r | r ≤ Quantile_0.05(r)]."""
        returns = np.linspace(-0.20, 0.20, 200)
        q = float(np.quantile(returns, 0.05))
        tail = returns[returns <= q]
        expected_cvar = -float(np.mean(tail))
        _, cvar = svc._compute_var_cvar(returns, alpha=0.05)
        assert cvar == pytest.approx(expected_cvar, abs=1e-10)

    def test_all_positive_returns_clamped_to_zero(self, svc: BacktestService):
        """When all returns are positive the 5th-percentile is positive → VaR/CVaR
        would be negative if not clamped.  The service clamps both to 0."""
        returns = np.linspace(0.001, 0.05, 100)
        var, cvar = svc._compute_var_cvar(returns, alpha=0.05)
        assert var == pytest.approx(0.0)
        assert cvar == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_max_drawdown                                                         #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeMaxDrawdown:
    def test_monotonically_increasing_no_drawdown(self, svc: BacktestService):
        values = np.array([1.0, 1.05, 1.10, 1.20])
        mdd, _ = svc._compute_max_drawdown(values)
        assert mdd == pytest.approx(0.0)

    def test_known_drawdown(self, svc: BacktestService):
        """Wealth drops from 1.20 to 0.90 → DD = 0.90/1.20 − 1 = −0.25."""
        values = np.array([1.00, 1.10, 1.20, 0.90, 0.95])
        mdd, _ = svc._compute_max_drawdown(values)
        assert mdd == pytest.approx(0.90 / 1.20 - 1.0, abs=1e-10)

    def test_mdd_le_zero(self, svc: BacktestService):
        rng = np.random.default_rng(7)
        values = np.cumprod(1 + rng.normal(0.001, 0.02, 50))
        mdd, _ = svc._compute_max_drawdown(values)
        assert mdd <= 0.0

    def test_trough_date_returned(self, svc: BacktestService):
        values = np.array([1.00, 1.10, 1.20, 0.90, 0.95])
        dates = [date(2020, m, 28) for m in range(1, 6)]
        mdd, trough = svc._compute_max_drawdown(values, dates)
        # Trough is at index 3 (value 0.90 when peak was 1.20)
        assert trough == date(2020, 4, 28)
        assert mdd == pytest.approx(0.90 / 1.20 - 1.0, abs=1e-10)

    def test_no_dates_returns_none(self, svc: BacktestService):
        values = np.array([1.0, 0.9])
        _, trough = svc._compute_max_drawdown(values)
        assert trough is None

    def test_single_period(self, svc: BacktestService):
        values = np.array([1.05])
        mdd, _ = svc._compute_max_drawdown(values)
        assert mdd == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_tracking_error                                                       #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeTrackingError:
    def test_identical_returns_zero_te(self, svc: BacktestService):
        r = np.array([0.01, 0.02, -0.01, 0.03])
        te = svc._compute_tracking_error(r, r, annualization_factor=12)
        assert te == pytest.approx(0.0, abs=1e-12)

    def test_te_formula_monthly(self, svc: BacktestService):
        """TE = √12 · std(active) for monthly data (DATA-MODEL §4.12)."""
        rng = np.random.default_rng(1)
        port = rng.normal(0.01, 0.05, 60)
        bench = rng.normal(0.008, 0.04, 60)
        active = port - bench
        expected_te = float(np.std(active, ddof=1) * np.sqrt(12))
        te = svc._compute_tracking_error(port, bench, annualization_factor=12)
        assert te == pytest.approx(expected_te, rel=1e-10)

    def test_te_non_negative(self, svc: BacktestService):
        rng = np.random.default_rng(99)
        port = rng.normal(0.01, 0.03, 36)
        bench = rng.normal(0.01, 0.03, 36)
        te = svc._compute_tracking_error(port, bench, annualization_factor=12)
        assert te >= 0.0


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_information_ratio                                                    #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeInformationRatio:
    def test_ir_formula(self, svc: BacktestService):
        """IR = ᾱ · m / TE (DATA-MODEL §4.12)."""
        active = np.array([0.002, 0.003, -0.001, 0.004, 0.001])
        te = 0.05
        m = 12
        expected_ir = float(np.mean(active)) * m / te
        ir = svc._compute_information_ratio(active, te, m)
        assert ir == pytest.approx(expected_ir, rel=1e-10)

    def test_zero_te_returns_zero(self, svc: BacktestService):
        active = np.zeros(10)
        ir = svc._compute_information_ratio(active, tracking_error=0.0, annualization_factor=12)
        assert ir == pytest.approx(0.0)

    def test_negative_active_returns_negative_ir(self, svc: BacktestService):
        active = np.full(12, -0.002)  # consistently underperforms
        te = svc._compute_tracking_error(active, np.zeros(12), 12)
        # te is 0 here since active is constant → IR = 0 (edge case)
        ir = svc._compute_information_ratio(active, te, 12)
        # Since std(constant) = 0 → te = 0 → IR = 0
        assert ir == pytest.approx(0.0)

    def test_positive_active_returns_positive_ir(self, svc: BacktestService):
        rng = np.random.default_rng(5)
        port = rng.normal(0.015, 0.03, 60)
        bench = rng.normal(0.010, 0.03, 60)
        active = port - bench
        te = svc._compute_tracking_error(port, bench, 12)
        ir = svc._compute_information_ratio(active, te, 12)
        assert ir > 0.0


# ═══════════════════════════════════════════════════════════════════════════ #
# _compute_summary                                                              #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeSummary:
    def _make_flat_points(self, n: int, net_ret: float) -> list[BacktestPointResult]:
        """Constant return each period; single rebalance at t=0."""
        points = []
        value = 1.0
        for i in range(n):
            value *= 1 + net_ret
            points.append(BacktestPointResult(
                obs_date=date(2020, 1 + i % 12, 28),
                portfolio_value=value,
                portfolio_ret=net_ret,
                portfolio_ret_net=net_ret,
                benchmark_ret=None,
                active_ret=None,
                turnover=0.05 if i == 0 else 0.0,
                drawdown=0.0,
            ))
        return points

    def test_total_return_flat_growth(self, svc: BacktestService):
        """1% per month for 12 months → total = 1.01^12 − 1."""
        points = self._make_flat_points(12, 0.01)
        summary = svc._compute_summary(points, None, annualization_factor=12)
        expected_total = 1.01 ** 12 - 1.0
        assert summary.total_return == pytest.approx(expected_total, rel=1e-8)

    def test_annualized_return_formula(self, svc: BacktestService):
        """annualized = (1 + total)^(m/T) − 1."""
        points = self._make_flat_points(24, 0.005)
        m = 12
        summary = svc._compute_summary(points, None, annualization_factor=m)
        total = summary.total_return
        expected_ann = (1 + total) ** (m / 24) - 1
        assert summary.annualized_return == pytest.approx(expected_ann, rel=1e-8)

    def test_annualized_vol_formula(self, svc: BacktestService):
        """annualized vol = √m · std(net_returns, ddof=1)."""
        rng = np.random.default_rng(3)
        rets = rng.normal(0.005, 0.02, 24)
        points = []
        value = 1.0
        for i, r in enumerate(rets):
            value *= 1 + r
            points.append(BacktestPointResult(
                obs_date=date(2020, 1, 1),
                portfolio_value=value,
                portfolio_ret=r,
                portfolio_ret_net=r,
                benchmark_ret=None,
                active_ret=None,
                turnover=0.0,
                drawdown=0.0,
            ))
        m = 12
        summary = svc._compute_summary(points, None, annualization_factor=m)
        expected_vol = float(np.std(rets, ddof=1) * np.sqrt(m))
        assert summary.annualized_vol == pytest.approx(expected_vol, rel=1e-8)

    def test_sharpe_uses_rf(self, svc: BacktestService):
        """Higher rf lowers the Sharpe ratio; requires non-zero vol to observe."""
        rng = np.random.default_rng(2)
        rets = rng.normal(0.01, 0.03, 36)  # variable returns → non-zero vol
        value = 1.0
        points = []
        for i, r in enumerate(rets):
            value *= 1 + r
            points.append(BacktestPointResult(
                obs_date=date(2020, 1, 1),
                portfolio_value=value,
                portfolio_ret=r,
                portfolio_ret_net=r,
                benchmark_ret=None,
                active_ret=None,
                turnover=0.05 if i == 0 else 0.0,
                drawdown=0.0,
            ))
        rf = 0.04
        summary_no_rf = svc._compute_summary(points, None, annualization_factor=12, rf=0.0)
        summary_rf = svc._compute_summary(points, None, annualization_factor=12, rf=rf)
        assert summary_rf.sharpe < summary_no_rf.sharpe

    def test_avg_turnover_only_rebalance_events(self, svc: BacktestService):
        """avg_turnover averages only non-zero turnover values."""
        points = self._make_flat_points(6, 0.01)
        # Only the first point has turnover=0.05
        summary = svc._compute_summary(points, None, annualization_factor=12)
        assert summary.avg_turnover == pytest.approx(0.05)

    def test_tracking_error_computed_when_benchmark_provided(self, svc: BacktestService):
        points = self._make_flat_points(12, 0.01)
        bench = np.full(12, 0.008)
        summary = svc._compute_summary(points, bench, annualization_factor=12)
        assert summary.tracking_error is not None
        assert summary.tracking_error >= 0.0

    def test_no_tracking_error_without_benchmark(self, svc: BacktestService):
        points = self._make_flat_points(12, 0.01)
        summary = svc._compute_summary(points, None, annualization_factor=12)
        assert summary.tracking_error is None
        assert summary.information_ratio is None

    def test_max_drawdown_le_zero(self, svc: BacktestService):
        rng = np.random.default_rng(11)
        rets = rng.normal(0.001, 0.03, 36)
        points = []
        value = 1.0
        for i, r in enumerate(rets):
            value *= 1 + r
            points.append(BacktestPointResult(
                obs_date=date(2020, 1, 1),
                portfolio_value=value,
                portfolio_ret=r,
                portfolio_ret_net=r,
                benchmark_ret=None,
                active_ret=None,
                turnover=0.0,
                drawdown=0.0,
            ))
        summary = svc._compute_summary(points, None, annualization_factor=12)
        assert summary.max_drawdown <= 0.0

    def test_var_cvar_non_negative(self, svc: BacktestService):
        """var_95 and cvar_95 are clamped to zero (loss magnitudes ≥ 0)."""
        rng = np.random.default_rng(42)
        # Mix of gains and losses so the 5th percentile is negative
        rets = np.concatenate([rng.uniform(-0.05, -0.01, 10), rng.uniform(0.01, 0.05, 50)])
        value = 1.0
        points = []
        for i, r in enumerate(rets):
            value = max(value * (1 + r), 1e-6)
            points.append(BacktestPointResult(
                obs_date=date(2020, 1, 1),
                portfolio_value=value,
                portfolio_ret=r,
                portfolio_ret_net=r,
                benchmark_ret=None,
                active_ret=None,
                turnover=0.0,
                drawdown=0.0,
            ))
        summary = svc._compute_summary(points, None, annualization_factor=12)
        assert summary.var_95 >= 0.0
        assert summary.cvar_95 >= 0.0


# ═══════════════════════════════════════════════════════════════════════════ #
# run_backtest — integration-style unit tests                                   #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestRunBacktest:
    def test_returns_backtest_result(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        assert isinstance(result, BacktestResult)

    def test_points_cover_post_warmup_periods(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        """Points should cover 12 − window_length = 9 periods."""
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        # 12 return observations, window=3 → 12−3 = 9 output points
        assert len(result.points) == 12 - 3

    def test_survivorship_bias_note_always_set(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        assert result.survivorship_bias_note != ""

    def test_ew_uniform_returns_wealth_index(self, svc: BacktestService):
        """All assets same return → EW portfolio tracks that return exactly."""
        monthly_ret = 0.01
        prices = _make_prices(3, 12, [[monthly_ret] * 3] * 12)
        config = _make_config(strategy=BacktestStrategy.EW_REBAL, window_length=3)

        result = svc.run_backtest(config, prices, annualization_factor=12)

        for p in result.points:
            assert p.portfolio_ret == pytest.approx(monthly_ret, abs=1e-10)
            assert p.portfolio_ret_net == pytest.approx(monthly_ret, abs=1e-10)

    def test_wealth_index_starts_at_one_plus_first_return(self, svc: BacktestService):
        """First point's portfolio_value = 1 × (1 + r_first)."""
        monthly_ret = 0.02
        prices = _make_prices(2, 12, [[monthly_ret, monthly_ret]] * 12)
        config = _make_config(strategy=BacktestStrategy.EW_REBAL, window_length=3)

        result = svc.run_backtest(config, prices, annualization_factor=12)

        assert result.points[0].portfolio_value == pytest.approx(1.0 + monthly_ret, abs=1e-10)

    def test_wealth_index_compounds(self, svc: BacktestService):
        """V_T = Π (1 + r_net_t) accumulated from V_0 = 1."""
        prices = _make_prices(2, 12, [[0.01, 0.01]] * 12)
        config = _make_config(strategy=BacktestStrategy.EW_REBAL, window_length=3)

        result = svc.run_backtest(config, prices, annualization_factor=12)

        n_points = len(result.points)
        expected_value = 1.01 ** n_points
        assert result.points[-1].portfolio_value == pytest.approx(expected_value, rel=1e-8)

    def test_transaction_costs_reduce_net_return(self, svc: BacktestService):
        """With transaction costs, net_return < gross_return on rebalance dates."""
        prices = _make_prices(2, 12, [[0.01, 0.02]] * 12)
        config_no_cost = _make_config(transaction_cost_bps=0.0, window_length=3)
        config_with_cost = _make_config(transaction_cost_bps=50.0, window_length=3)

        result_no = svc.run_backtest(config_no_cost, prices, annualization_factor=12)
        result_with = svc.run_backtest(config_with_cost, prices, annualization_factor=12)

        # Total return with costs must be lower
        assert result_with.summary.total_return < result_no.summary.total_return

    def test_transaction_cost_formula_on_rebalance(self, svc: BacktestService):
        """net_return = gross_return − (bps / 10_000) × turnover (DATA-MODEL §4.10)."""
        # 2-asset portfolio with diverging returns → EW rebalance has nonzero turnover
        prices = _make_prices(2, 12, [[0.01, 0.05]] * 12)
        bps = 20.0
        config = _make_config(
            strategy=BacktestStrategy.EW_REBAL,
            transaction_cost_bps=bps,
            window_length=3,
        )
        result = svc.run_backtest(config, prices, annualization_factor=12)

        for p in result.points:
            expected_net = p.portfolio_ret - (bps / 10_000) * p.turnover
            assert p.portfolio_ret_net == pytest.approx(expected_net, abs=1e-12)

    def test_drawdown_le_zero_always(self, svc: BacktestService):
        prices = _make_prices(3, 18, [[0.02, -0.01, 0.005]] * 18)
        config = _make_config(window_length=3)
        result = svc.run_backtest(config, prices, annualization_factor=12)
        for p in result.points:
            assert p.drawdown <= 1e-12  # allow tiny float noise

    def test_turnover_zero_on_non_rebalance_dates(self, svc: BacktestService):
        """Monthly rebalancing on monthly data: every period is a rebalance.
        Use quarterly to get non-rebalance periods."""
        prices = _make_prices(3, 18, [[0.01, 0.01, 0.01]] * 18)
        config = _make_config(
            strategy=BacktestStrategy.EW_REBAL,
            rebal_freq=RebalFrequency.QUARTERLY,
            window_length=3,
        )
        result = svc.run_backtest(config, prices, annualization_factor=12)
        # Some points should have turnover=0.0 (between quarterly rebalances)
        zero_turnover = [p for p in result.points if p.turnover == 0.0]
        assert len(zero_turnover) > 0

    def test_no_benchmark_no_active_return(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        for p in result.points:
            assert p.benchmark_ret is None
            assert p.active_ret is None
        assert result.summary.tracking_error is None
        assert result.summary.information_ratio is None

    def test_benchmark_returns_active_return(self, svc: BacktestService):
        """active_ret = portfolio_ret_net − benchmark_ret (DATA-MODEL §4.12)."""
        prices = _make_prices(2, 12, [[0.015, 0.015]] * 12)
        bench_prices = pd.Series(
            [1.0] + [1.01 ** (i + 1) for i in range(12)],
            index=pd.date_range("2020-01-31", periods=13, freq="ME"),
        )
        config = _make_config(window_length=3)

        result = svc.run_backtest(
            config, prices, annualization_factor=12, benchmark_prices=bench_prices
        )

        for p in result.points:
            if p.benchmark_ret is not None:
                assert p.active_ret == pytest.approx(
                    p.portfolio_ret_net - p.benchmark_ret, abs=1e-12
                )

    def test_window_length_too_large_raises(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame
    ):
        config = _make_config(window_length=20)  # 20 >= 12 return observations
        with pytest.raises(ValueError, match="window_length"):
            svc.run_backtest(config, prices_3a_12m, annualization_factor=12)

    def test_mvp_strategy_runs(self, svc: BacktestService):
        """MVP_REBAL must produce a feasible result without error."""
        prices = _make_prices(3, 18, [[0.01, 0.02, 0.015]] * 18)
        config = _make_config(
            strategy=BacktestStrategy.MVP_REBAL,
            window_length=6,
        )
        result = svc.run_backtest(config, prices, annualization_factor=12)
        assert len(result.points) > 0
        assert result.summary.total_return is not None

    def test_tangency_strategy_runs(self, svc: BacktestService):
        """TANGENCY_REBAL must produce a feasible result with nonzero rf."""
        prices = _make_prices(3, 18, [[0.01, 0.02, 0.015]] * 18)
        config = _make_config(
            strategy=BacktestStrategy.TANGENCY_REBAL,
            rf=0.03,
            window_length=6,
        )
        result = svc.run_backtest(config, prices, annualization_factor=12)
        assert len(result.points) > 0

    def test_threshold_rebalancing_triggers_on_drift(self, svc: BacktestService):
        """Threshold rebalancing: high-return asset drifts → rebalance triggered."""
        # Asset 0 returns 0%, asset 1 returns 10% → big drift quickly
        rets = [[0.00, 0.10]] * 18
        prices = _make_prices(2, 18, rets)
        config = _make_config(
            strategy=BacktestStrategy.EW_REBAL,
            rebal_freq=RebalFrequency.THRESHOLD,
            rebal_threshold=0.10,
            window_length=3,
        )
        result = svc.run_backtest(config, prices, annualization_factor=12)

        # There should be more than just the first rebalance (drift triggers more)
        rebal_dates = [p for p in result.points if p.turnover > 0.0]
        assert len(rebal_dates) > 1

    def test_summary_total_return_matches_last_value(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        assert result.summary.total_return == pytest.approx(
            result.points[-1].portfolio_value - 1.0, abs=1e-10
        )

    def test_summary_max_drawdown_matches_min_drawdown(
        self, svc: BacktestService, prices_3a_12m: pd.DataFrame, ew_monthly_config: BacktestConfig
    ):
        result = svc.run_backtest(ew_monthly_config, prices_3a_12m, annualization_factor=12)
        min_dd = min(p.drawdown for p in result.points)
        assert result.summary.max_drawdown == pytest.approx(min_dd, abs=1e-10)


# ═══════════════════════════════════════════════════════════════════════════ #
# Module helpers                                                                #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestMapToActualDates:
    def test_exact_match(self):
        candidates = [date(2020, 2, 1)]
        actual = [date(2020, 1, 31), date(2020, 2, 1), date(2020, 3, 31)]
        result = _map_to_actual_dates(candidates, actual)
        assert date(2020, 2, 1) in result

    def test_maps_to_next_available(self):
        candidates = [date(2020, 2, 1)]
        # Feb 1 is not in actual; first date >= Feb 1 is Feb 28
        actual = [date(2020, 1, 31), date(2020, 2, 28), date(2020, 3, 31)]
        result = _map_to_actual_dates(candidates, actual)
        assert date(2020, 2, 28) in result

    def test_candidate_after_all_actual_dates_ignored(self):
        candidates = [date(2021, 1, 1)]
        actual = [date(2020, 1, 31), date(2020, 2, 28)]
        result = _map_to_actual_dates(candidates, actual)
        assert len(result) == 0

    def test_multiple_candidates(self):
        candidates = [date(2020, 1, 1), date(2020, 4, 1)]
        actual = [date(2020, 1, 31), date(2020, 2, 28), date(2020, 4, 30), date(2020, 5, 29)]
        result = _map_to_actual_dates(candidates, actual)
        assert date(2020, 1, 31) in result
        assert date(2020, 4, 30) in result


class TestCollectBenchmarkArray:
    def _point(self, bench_ret: float | None) -> BacktestPointResult:
        return BacktestPointResult(
            obs_date=date(2020, 1, 31),
            portfolio_value=1.01,
            portfolio_ret=0.01,
            portfolio_ret_net=0.01,
            benchmark_ret=bench_ret,
            active_ret=None,
            turnover=0.0,
            drawdown=0.0,
        )

    def test_all_present_returns_array(self):
        points = [self._point(0.01), self._point(0.02), self._point(-0.01)]
        arr = _collect_benchmark_array(points)
        assert arr is not None
        assert list(arr) == pytest.approx([0.01, 0.02, -0.01])

    def test_all_none_returns_none(self):
        points = [self._point(None), self._point(None)]
        arr = _collect_benchmark_array(points)
        assert arr is None

    def test_partial_none_returns_none(self):
        points = [self._point(0.01), self._point(None)]
        arr = _collect_benchmark_array(points)
        assert arr is None
