"""Tests for src/domain/models/backtest.py."""

import pytest
from datetime import date
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.backtest import (
    BacktestConfig,
    BacktestPoint,
    BacktestRun,
    BacktestSummary,
)
from src.domain.models.enums import BacktestStrategy, RebalFrequency


TODAY = date(2025, 6, 1)


# --- BacktestConfig ---

def test_backtest_config_monthly_construction():
    cfg = BacktestConfig(
        strategy=BacktestStrategy.TANGENCY_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        window_length=60,
    )
    assert cfg.rebal_freq == RebalFrequency.MONTHLY


def test_backtest_config_quarterly_no_threshold_needed():
    cfg = BacktestConfig(
        strategy=BacktestStrategy.MVP_REBAL,
        rebal_freq=RebalFrequency.QUARTERLY,
        window_length=20,
    )
    assert cfg.rebal_threshold is None


def test_backtest_config_threshold_with_value():
    cfg = BacktestConfig(
        strategy=BacktestStrategy.EW_REBAL,
        rebal_freq=RebalFrequency.THRESHOLD,
        rebal_threshold=0.05,
        window_length=12,
    )
    assert cfg.rebal_threshold == 0.05


def test_backtest_config_threshold_without_value_raises():
    with pytest.raises(ValidationError):
        BacktestConfig(
            strategy=BacktestStrategy.TANGENCY_REBAL,
            rebal_freq=RebalFrequency.THRESHOLD,
            rebal_threshold=None,
            window_length=60,
        )


def test_backtest_config_transaction_cost_defaults_zero():
    cfg = BacktestConfig(
        strategy=BacktestStrategy.MVP_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        window_length=12,
    )
    assert cfg.transaction_cost_bps == 0.0


def test_backtest_config_window_length_zero_raises():
    with pytest.raises(ValidationError):
        BacktestConfig(
            strategy=BacktestStrategy.MVP_REBAL,
            rebal_freq=RebalFrequency.MONTHLY,
            window_length=0,
        )


# --- BacktestPoint ---

def test_backtest_point_without_benchmark():
    pt = BacktestPoint(
        backtest_id=uuid4(),
        obs_date=TODAY,
        portfolio_value=1.05,
        portfolio_ret=0.05,
        portfolio_ret_net=0.049,
        turnover=0.0,
        drawdown=0.0,
    )
    assert pt.benchmark_ret is None


def test_backtest_point_with_benchmark():
    pt = BacktestPoint(
        backtest_id=uuid4(),
        obs_date=TODAY,
        portfolio_value=1.05,
        portfolio_ret=0.05,
        portfolio_ret_net=0.049,
        benchmark_ret=0.04,
        active_ret=0.009,
        turnover=0.0,
        drawdown=0.0,
    )
    assert pt.active_ret == 0.009


def test_backtest_point_benchmark_without_active_ret_raises():
    with pytest.raises(ValidationError):
        BacktestPoint(
            backtest_id=uuid4(),
            obs_date=TODAY,
            portfolio_value=1.05,
            portfolio_ret=0.05,
            portfolio_ret_net=0.049,
            benchmark_ret=0.04,
            active_ret=None,
            turnover=0.0,
            drawdown=0.0,
        )


def test_backtest_point_active_ret_without_benchmark_raises():
    with pytest.raises(ValidationError):
        BacktestPoint(
            backtest_id=uuid4(),
            obs_date=TODAY,
            portfolio_value=1.05,
            portfolio_ret=0.05,
            portfolio_ret_net=0.049,
            benchmark_ret=None,
            active_ret=0.009,
            turnover=0.0,
            drawdown=0.0,
        )


def test_backtest_point_drawdown_zero_valid():
    pt = BacktestPoint(
        backtest_id=uuid4(),
        obs_date=TODAY,
        portfolio_value=1.10,
        portfolio_ret=0.05,
        portfolio_ret_net=0.049,
        turnover=0.0,
        drawdown=0.0,
    )
    assert pt.drawdown == 0.0


def test_backtest_point_drawdown_negative_valid():
    pt = BacktestPoint(
        backtest_id=uuid4(),
        obs_date=TODAY,
        portfolio_value=0.90,
        portfolio_ret=-0.10,
        portfolio_ret_net=-0.101,
        turnover=0.0,
        drawdown=-0.10,
    )
    assert pt.drawdown == -0.10


def test_backtest_point_drawdown_positive_raises():
    with pytest.raises(ValidationError):
        BacktestPoint(
            backtest_id=uuid4(),
            obs_date=TODAY,
            portfolio_value=1.10,
            portfolio_ret=0.05,
            portfolio_ret_net=0.049,
            turnover=0.0,
            drawdown=0.05,
        )


def test_backtest_point_turnover_defaults_zero():
    pt = BacktestPoint(
        backtest_id=uuid4(),
        obs_date=TODAY,
        portfolio_value=1.0,
        portfolio_ret=0.0,
        portfolio_ret_net=0.0,
        drawdown=0.0,
    )
    assert pt.turnover == 0.0


# --- BacktestSummary ---

def test_backtest_summary_construction():
    s = BacktestSummary(
        backtest_id=uuid4(),
        total_return=0.45,
        annualized_return=0.09,
        annualized_vol=0.12,
        sharpe=0.75,
        max_drawdown=-0.18,
        var_95=0.022,
        cvar_95=0.031,
        avg_turnover=0.25,
    )
    assert s.max_drawdown == -0.18


def test_backtest_summary_max_drawdown_positive_raises():
    with pytest.raises(ValidationError):
        BacktestSummary(
            backtest_id=uuid4(),
            total_return=0.45,
            annualized_return=0.09,
            annualized_vol=0.12,
            sharpe=0.75,
            max_drawdown=0.05,
            var_95=0.022,
            cvar_95=0.031,
            avg_turnover=0.25,
        )


def test_backtest_summary_tracking_error_none_when_no_benchmark():
    s = BacktestSummary(
        backtest_id=uuid4(),
        total_return=0.45,
        annualized_return=0.09,
        annualized_vol=0.12,
        sharpe=0.75,
        max_drawdown=-0.18,
        var_95=0.022,
        cvar_95=0.031,
        avg_turnover=0.25,
    )
    assert s.tracking_error is None


def test_backtest_summary_with_benchmark_stats():
    s = BacktestSummary(
        backtest_id=uuid4(),
        total_return=0.45,
        annualized_return=0.09,
        annualized_vol=0.12,
        sharpe=0.75,
        max_drawdown=-0.18,
        var_95=0.022,
        cvar_95=0.031,
        avg_turnover=0.25,
        tracking_error=0.04,
        information_ratio=0.50,
    )
    assert s.information_ratio == 0.50


# --- BacktestRun ---

def _cfg() -> BacktestConfig:
    return BacktestConfig(
        strategy=BacktestStrategy.TANGENCY_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        window_length=60,
        transaction_cost_bps=10.0,
    )


def test_backtest_run_construction():
    run = BacktestRun(
        universe_id=uuid4(),
        config=_cfg(),
        survivorship_bias_note="Universe fixed at current composition.",
    )
    assert run.survivorship_bias_note != ""


def test_backtest_run_id_auto_generated():
    run = BacktestRun(
        universe_id=uuid4(),
        config=_cfg(),
        survivorship_bias_note="Note.",
    )
    assert run.backtest_id is not None


def test_backtest_run_points_empty_by_default():
    run = BacktestRun(
        universe_id=uuid4(),
        config=_cfg(),
        survivorship_bias_note="Note.",
    )
    assert run.points == []


def test_backtest_run_create_factory_sets_universe():
    uid = uuid4()
    run = BacktestRun.create(universe_id=uid, config=_cfg())
    assert run.universe_id == uid


def test_backtest_run_create_default_survivorship_note_populated():
    run = BacktestRun.create(universe_id=uuid4(), config=_cfg())
    assert len(run.survivorship_bias_note) > 0


def test_backtest_run_create_benchmark_none_by_default():
    run = BacktestRun.create(universe_id=uuid4(), config=_cfg())
    assert run.benchmark_asset_id is None


def test_backtest_run_create_with_benchmark():
    bid = uuid4()
    run = BacktestRun.create(universe_id=uuid4(), config=_cfg(), benchmark_asset_id=bid)
    assert run.benchmark_asset_id == bid
