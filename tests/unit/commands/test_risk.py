"""Unit tests for src/commands/risk.py."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import HTTPException

from src.commands.risk import (
    ApplyScenarioCommand,
    ApplyScenarioHandler,
    CreateScenarioCommand,
    CreateScenarioHandler,
    RunBacktestCommand,
    RunBacktestHandler,
    RunDriftCheckCommand,
    RunDriftCheckHandler,
)
from src.domain.models.assets import Asset, Universe
from src.domain.models.backtest import BacktestConfig, BacktestRun
from src.domain.models.drift import DriftCheck
from src.domain.models.enums import (
    AssetClass,
    BacktestStrategy,
    Frequency,
    Geography,
    RebalFrequency,
    RunType,
)
from src.domain.models.optimization import OptimizationConstraints, OptimizationRun, PortfolioWeight
from src.domain.models.scenarios import ScenarioDefinition
from src.domain.services.backtest import BacktestPointResult, BacktestResult, BacktestSummaryResult
from src.domain.services.drift import DriftResult


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_asset(ticker: str = "SPY") -> Asset:
    return Asset(
        ticker=ticker,
        name="Test ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )


def _make_opt_run(run_id=None) -> OptimizationRun:
    run_id = run_id or uuid4()
    from src.domain.models.enums import OptimizationStatus
    return OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
        constraints=OptimizationConstraints.long_only_unconstrained(),
        infeasibility_reason=None,
        result=None,
        weights=[],
        reference_snapshot_id=None,
        solver_meta=None,
    )


def _make_portfolio_weights(asset_ids, run_id=None) -> list[PortfolioWeight]:
    rid = run_id or uuid4()
    return [
        PortfolioWeight(run_id=rid, asset_id=aid, weight=1.0 / len(asset_ids), mcr=0.0, crc=0.0, prc=0.0)
        for aid in asset_ids
    ]


def _make_drift_result(asset_ids) -> DriftResult:
    # raw_positions: list[tuple[UUID, target_weight, current_weight, explanation | None]]
    raw = [(aid, 0.5, 0.5, None) for aid in asset_ids]
    return DriftResult(
        check_date=date(2024, 1, 31),
        threshold=0.05,
        any_breach=False,
        raw_positions=raw,
    )


def _make_backtest_result() -> BacktestResult:
    config = BacktestConfig(
        strategy=BacktestStrategy.TANGENCY_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        rebal_threshold=None,
        window_length=60,
        transaction_cost_bps=0.0,
        rf=0.0,
        constraints=OptimizationConstraints.long_only_unconstrained(),
    )
    point = BacktestPointResult(
        obs_date=date(2023, 1, 2),
        portfolio_value=1.01,
        portfolio_ret=0.01,
        portfolio_ret_net=0.009,
        benchmark_ret=None,
        active_ret=None,
        turnover=0.0,
        drawdown=0.0,
    )
    summary = BacktestSummaryResult(
        total_return=0.10,
        annualized_return=0.10,
        annualized_vol=0.15,
        sharpe=0.5,
        max_drawdown=-0.05,
        var_95=0.02,
        cvar_95=0.03,
        avg_turnover=0.05,
        tracking_error=None,
        information_ratio=None,
    )
    return BacktestResult(
        config=config,
        points=[point],
        summary=summary,
        survivorship_bias_note="Test note",
    )


# ── RunDriftCheckHandler ─────────────────────────────────────────────────────


def _make_drift_handler(asset_ids=None, opt_run=None, weights=None, drift_result=None):
    asset_ids = asset_ids or [uuid4(), uuid4()]
    opt_run = opt_run or _make_opt_run()
    weights = weights or _make_portfolio_weights(asset_ids, run_id=opt_run.run_id)
    drift_result = drift_result or _make_drift_result(asset_ids)

    optimization_repo = AsyncMock()
    optimization_repo.get_by_id.return_value = opt_run
    optimization_repo.get_weights.return_value = weights

    from types import SimpleNamespace
    price_repo = AsyncMock()
    bars = [
        SimpleNamespace(bar_date=date(2023, 1, d + 2), adj_close=100.0 + d)
        for d in range(5)
    ]
    price_repo.get_prices.return_value = bars

    asset_repo = AsyncMock()
    asset_repo.get_by_id.return_value = _make_asset()

    drift_repo = AsyncMock()
    drift_repo.create.side_effect = lambda dc: dc

    drift_service = MagicMock()
    drift_service.compute_drift.return_value = drift_result

    return RunDriftCheckHandler(
        optimization_repo=optimization_repo,
        price_repo=price_repo,
        asset_repo=asset_repo,
        drift_repo=drift_repo,
        drift_service=drift_service,
    )


def _drift_cmd(**overrides):
    defaults = dict(
        run_id=uuid4(),
        check_date=date(2024, 1, 31),
    )
    defaults.update(overrides)
    return RunDriftCheckCommand(**defaults)


async def test_drift_raises_404_when_run_not_found():
    handler = _make_drift_handler()
    handler._optimization_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_drift_cmd())
    assert exc_info.value.status_code == 404


async def test_drift_raises_422_when_no_weights():
    handler = _make_drift_handler()
    handler._optimization_repo.get_weights.return_value = []
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_drift_cmd())
    assert exc_info.value.status_code == 422


async def test_drift_calls_compute_drift():
    handler = _make_drift_handler()
    await handler.handle(_drift_cmd())
    handler._drift_service.compute_drift.assert_called_once()


async def test_drift_persists_drift_check():
    handler = _make_drift_handler()
    await handler.handle(_drift_cmd())
    handler._drift_repo.create.assert_awaited_once()


async def test_drift_returns_drift_check():
    handler = _make_drift_handler()
    result = await handler.handle(_drift_cmd())
    assert isinstance(result, DriftCheck)


# ── RunBacktestHandler ───────────────────────────────────────────────────────


def _make_backtest_handler(
    universe=None,
    asset_ids=None,
    price_bars=None,
    benchmark_asset=None,
    backtest_result=None,
):
    asset_ids = asset_ids or [uuid4(), uuid4()]
    universe = universe or Universe.create_active(name="Test", description="")

    universe_repo = AsyncMock()
    universe_repo.get_by_id.return_value = universe
    universe_repo.get_asset_ids.return_value = asset_ids

    from types import SimpleNamespace
    price_repo = AsyncMock()
    bars = [
        SimpleNamespace(bar_date=date(2023, 1, d + 2), adj_close=100.0 + d)
        for d in range(10)
    ]
    price_repo.get_prices.return_value = bars if price_bars is None else price_bars

    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = benchmark_asset

    backtest_repo = AsyncMock()
    backtest_repo.create.side_effect = lambda r: r

    backtest_service = MagicMock()
    backtest_service.run_backtest.return_value = backtest_result or _make_backtest_result()

    return RunBacktestHandler(
        universe_repo=universe_repo,
        asset_repo=asset_repo,
        price_repo=price_repo,
        backtest_repo=backtest_repo,
        backtest_service=backtest_service,
    )


def _backtest_cmd(**overrides):
    defaults = dict(
        universe_id=uuid4(),
        strategy=BacktestStrategy.TANGENCY_REBAL,
        rebal_freq=RebalFrequency.MONTHLY,
        window_length=60,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
    )
    defaults.update(overrides)
    return RunBacktestCommand(**defaults)


async def test_backtest_raises_404_when_universe_not_found():
    handler = _make_backtest_handler()
    handler._universe_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_backtest_cmd())
    assert exc_info.value.status_code == 404


async def test_backtest_raises_422_when_no_assets():
    handler = _make_backtest_handler()
    handler._universe_repo.get_asset_ids.return_value = []
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_backtest_cmd())
    assert exc_info.value.status_code == 422


async def test_backtest_raises_422_when_no_price_data():
    handler = _make_backtest_handler(price_bars=[])
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_backtest_cmd())
    assert exc_info.value.status_code == 422


async def test_backtest_benchmark_not_found_raises_404():
    handler = _make_backtest_handler(benchmark_asset=None)
    cmd = _backtest_cmd(benchmark_ticker="SPY")
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 404


async def test_backtest_no_benchmark_no_asset_lookup():
    handler = _make_backtest_handler()
    await handler.handle(_backtest_cmd(benchmark_ticker=None))
    handler._asset_repo.get_by_ticker.assert_not_awaited()


async def test_backtest_calls_run_backtest():
    handler = _make_backtest_handler()
    await handler.handle(_backtest_cmd())
    handler._backtest_service.run_backtest.assert_called_once()


async def test_backtest_persists_run():
    handler = _make_backtest_handler()
    await handler.handle(_backtest_cmd())
    handler._backtest_repo.create.assert_awaited_once()


async def test_backtest_with_valid_benchmark_loads_benchmark_prices():
    benchmark = _make_asset("SPY")
    handler = _make_backtest_handler(benchmark_asset=benchmark)
    await handler.handle(_backtest_cmd(benchmark_ticker="SPY"))
    handler._asset_repo.get_by_ticker.assert_awaited_once_with("SPY")


# ── CreateScenarioHandler ────────────────────────────────────────────────────


async def test_create_scenario_persists_definition():
    scenario_repo = AsyncMock()
    expected = ScenarioDefinition(name="Crash", shocks={"equity": -0.30})
    scenario_repo.create_definition.return_value = expected
    handler = CreateScenarioHandler(scenario_repo=scenario_repo)
    cmd = CreateScenarioCommand(name="Crash", shocks={"equity": -0.30})
    result = await handler.handle(cmd)
    assert result is expected
    scenario_repo.create_definition.assert_awaited_once()


async def test_create_scenario_passes_correct_name():
    scenario_repo = AsyncMock()
    created = []
    scenario_repo.create_definition.side_effect = lambda s: (created.append(s), s)[1]
    handler = CreateScenarioHandler(scenario_repo=scenario_repo)
    cmd = CreateScenarioCommand(name="Rate Spike", shocks={"duration": 2.0})
    await handler.handle(cmd)
    assert created[0].name == "Rate Spike"


# ── ApplyScenarioHandler ─────────────────────────────────────────────────────


async def test_apply_scenario_raises_501():
    scenario_repo = AsyncMock()
    handler = ApplyScenarioHandler(scenario_repo=scenario_repo)
    cmd = ApplyScenarioCommand(run_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(uuid4(), cmd)
    assert exc_info.value.status_code == 501


async def test_apply_scenario_never_calls_repo():
    scenario_repo = AsyncMock()
    handler = ApplyScenarioHandler(scenario_repo=scenario_repo)
    with pytest.raises(HTTPException):
        await handler.handle(uuid4(), ApplyScenarioCommand(run_id=uuid4()))
    scenario_repo.assert_not_awaited()
