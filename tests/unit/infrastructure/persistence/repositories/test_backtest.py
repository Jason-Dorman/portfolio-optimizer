"""Tests for SqlBacktestRepository — mapping and immutability."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.models.enums import BacktestStrategy, RebalFrequency
from src.infrastructure.persistence.repositories.backtest import (
    SqlBacktestRepository,
    _point_to_domain,
    _run_to_domain,
    _summary_to_domain,
)


def _orm_point(**overrides):
    defaults = {
        "backtest_id": uuid4(),
        "obs_date": date(2024, 1, 2),
        "portfolio_value": 1.05,
        "portfolio_ret": 0.005,
        "portfolio_ret_net": 0.0049,
        "benchmark_ret": None,
        "active_ret": None,
        "turnover": 0.0,
        "drawdown": -0.02,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_summary(**overrides):
    defaults = {
        "backtest_id": uuid4(),
        "total_return": 0.45,
        "annualized_return": 0.08,
        "annualized_vol": 0.12,
        "sharpe": 0.67,
        "max_drawdown": -0.18,
        "var_95": 0.02,
        "cvar_95": 0.03,
        "avg_turnover": 0.05,
        "tracking_error": None,
        "information_ratio": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_run(**overrides):
    defaults = {
        "backtest_id": uuid4(),
        "universe_id": uuid4(),
        "benchmark_asset_id": None,
        "strategy": "MVP_REBAL",
        "rebal_freq": "monthly",
        "rebal_threshold": None,
        "window_length": 36,
        "transaction_cost_bps": 10.0,
        "constraints": {},
        "survivorship_bias_note": "Universe reflects current assets only.",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _point_to_domain mapping ---

def test_point_to_domain_maps_drawdown():
    assert _point_to_domain(_orm_point(drawdown=-0.05)).drawdown == -0.05


def test_point_to_domain_maps_portfolio_value():
    assert _point_to_domain(_orm_point(portfolio_value=1.10)).portfolio_value == 1.10


def test_point_to_domain_maps_benchmark_ret_none():
    assert _point_to_domain(_orm_point(benchmark_ret=None)).benchmark_ret is None


# --- _summary_to_domain mapping ---

def test_summary_to_domain_maps_sharpe():
    assert _summary_to_domain(_orm_summary(sharpe=1.23)).sharpe == 1.23


def test_summary_to_domain_maps_max_drawdown():
    assert _summary_to_domain(_orm_summary(max_drawdown=-0.25)).max_drawdown == -0.25


# --- _run_to_domain mapping ---

def test_run_to_domain_builds_config_strategy():
    result = _run_to_domain(_orm_run(strategy="MVP_REBAL"), [], None)
    assert result.config.strategy == BacktestStrategy.MVP_REBAL


def test_run_to_domain_builds_config_rebal_freq():
    result = _run_to_domain(_orm_run(rebal_freq="quarterly"), [], None)
    assert result.config.rebal_freq == RebalFrequency.QUARTERLY


def test_run_to_domain_summary_none_when_not_provided():
    result = _run_to_domain(_orm_run(), [], None)
    assert result.summary is None


# --- immutability guards ---

async def test_update_raises():
    repo = SqlBacktestRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlBacktestRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
