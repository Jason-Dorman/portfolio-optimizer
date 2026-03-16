"""Unit tests for src/commands/optimization.py."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException

from src.commands.optimization import RunOptimizationCommand, RunOptimizationHandler
from src.domain.models.assumptions import AssumptionSet, AssetStats, CovarianceEntry, CovarianceMatrix
from src.domain.models.enums import (
    CovMethod,
    Estimator,
    Frequency,
    OptimizationStatus,
    ReturnType,
    RunType,
)
from src.domain.models.optimization import OptimizationConstraints, OptimizationRun
from src.domain.services.optimization import SolverResult


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_assumption(universe_id=None) -> AssumptionSet:
    return AssumptionSet.create(
        universe_id=universe_id or uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        lookback_start=date(2023, 1, 1),
        lookback_end=date(2023, 12, 31),
        rf_annual=0.04,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )


def _make_stats(assumption_id, asset_ids) -> list[AssetStats]:
    return [
        AssetStats(assumption_id=assumption_id, asset_id=aid, mu_annual=0.08, sigma_annual=0.15)
        for aid in asset_ids
    ]


def _make_covariance(assumption_id, asset_ids) -> CovarianceMatrix:
    entries = [
        CovarianceEntry(
            assumption_id=assumption_id,
            asset_id_i=asset_ids[i],
            asset_id_j=asset_ids[j],
            cov_annual=0.04 if i == j else 0.01,
        )
        for i in range(len(asset_ids))
        for j in range(i, len(asset_ids))
    ]
    return CovarianceMatrix(assumption_id=assumption_id, entries=entries)


def _feasible_solver_result(n: int = 2) -> SolverResult:
    w = np.array([1.0 / n] * n)
    return SolverResult(
        weights=w,
        exp_return=0.08,
        variance=0.04,
        stdev=0.2,
        sharpe=0.2,
        hhi=0.5,
        effective_n=2.0,
        explanation="Test portfolio",
        is_feasible=True,
        infeasibility_reason=None,
        solver_meta={"status": "ok"},
    )


def _infeasible_solver_result() -> SolverResult:
    return SolverResult(
        weights=None,
        exp_return=None,
        variance=None,
        stdev=None,
        sharpe=None,
        hhi=None,
        effective_n=None,
        explanation="Infeasible",
        is_feasible=False,
        infeasibility_reason="Constraints too tight",
        solver_meta=None,
    )


def _make_handler(assumption=None, stats=None, covariance=None, solver_result=None):
    universe_id = uuid4()
    asset_ids = [uuid4(), uuid4()]
    assumption = assumption or _make_assumption(universe_id=universe_id)
    stats = stats or _make_stats(assumption.assumption_id, asset_ids)
    covariance = covariance or _make_covariance(assumption.assumption_id, asset_ids)
    solver_result = solver_result or _feasible_solver_result()

    assumption_repo = AsyncMock()
    assumption_repo.get_by_id.return_value = assumption
    assumption_repo.get_asset_stats.return_value = stats
    assumption_repo.get_covariance_matrix.return_value = covariance

    holdings_repo = AsyncMock()
    holdings_repo.get_by_id.return_value = None

    optimization_repo = AsyncMock()
    optimization_repo.create.side_effect = lambda r: r
    optimization_repo.get_latest_for_universe.return_value = None
    optimization_repo.get_weights.return_value = []

    optimization_service = MagicMock()
    optimization_service.optimize_mvp.return_value = solver_result
    optimization_service.optimize_tangency.return_value = solver_result
    optimization_service.optimize_frontier_point.return_value = solver_result

    return RunOptimizationHandler(
        assumption_repo=assumption_repo,
        holdings_repo=holdings_repo,
        optimization_repo=optimization_repo,
        optimization_service=optimization_service,
    )


def _make_cmd(run_type=RunType.MVP, **overrides):
    defaults = dict(
        assumption_id=uuid4(),
        run_type=run_type,
        constraints=OptimizationConstraints.long_only_unconstrained(),
    )
    defaults.update(overrides)
    return RunOptimizationCommand(**defaults)


# ── Error paths ─────────────────────────────────────────────────────────────


async def test_frontier_series_raises_400():
    handler = _make_handler()
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_make_cmd(run_type=RunType.FRONTIER_SERIES))
    assert exc_info.value.status_code == 400


async def test_assumption_not_found_raises_404():
    handler = _make_handler()
    handler._assumption_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_make_cmd())
    assert exc_info.value.status_code == 404


async def test_no_stats_raises_422():
    handler = _make_handler()
    handler._assumption_repo.get_asset_stats.return_value = []
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_make_cmd())
    assert exc_info.value.status_code == 422


async def test_no_covariance_raises_422():
    handler = _make_handler()
    handler._assumption_repo.get_covariance_matrix.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_make_cmd())
    assert exc_info.value.status_code == 422


async def test_frontier_point_without_target_return_raises_400():
    handler = _make_handler()
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_make_cmd(run_type=RunType.FRONTIER_POINT, target_return=None))
    assert exc_info.value.status_code == 400


# ── Happy paths ──────────────────────────────────────────────────────────────


async def test_mvp_calls_optimize_mvp():
    handler = _make_handler()
    await handler.handle(_make_cmd(run_type=RunType.MVP))
    handler._optimization_service.optimize_mvp.assert_called_once()


async def test_tangency_calls_optimize_tangency():
    handler = _make_handler()
    await handler.handle(_make_cmd(run_type=RunType.TANGENCY))
    handler._optimization_service.optimize_tangency.assert_called_once()


async def test_frontier_point_calls_optimize_frontier_point():
    handler = _make_handler()
    await handler.handle(_make_cmd(run_type=RunType.FRONTIER_POINT, target_return=0.07))
    handler._optimization_service.optimize_frontier_point.assert_called_once()


async def test_feasible_result_persisted_with_success_status():
    handler = _make_handler(solver_result=_feasible_solver_result())
    run = await handler.handle(_make_cmd())
    assert run.status == OptimizationStatus.SUCCESS


async def test_infeasible_result_persisted_with_infeasible_status():
    handler = _make_handler(solver_result=_infeasible_solver_result())
    run = await handler.handle(_make_cmd())
    assert run.status == OptimizationStatus.INFEASIBLE


async def test_feasible_result_has_weights():
    handler = _make_handler(solver_result=_feasible_solver_result(n=2))
    run = await handler.handle(_make_cmd())
    assert len(run.weights) == 2


async def test_infeasible_result_has_no_weights():
    handler = _make_handler(solver_result=_infeasible_solver_result())
    run = await handler.handle(_make_cmd())
    assert run.weights == []


async def test_optimization_repo_create_called():
    handler = _make_handler()
    await handler.handle(_make_cmd())
    handler._optimization_repo.create.assert_awaited_once()


# ── Turnover constraint handling ─────────────────────────────────────────────


async def test_turnover_cap_with_snapshot_loads_snapshot_weights():
    from src.domain.models.holdings import HoldingsPosition, HoldingsSnapshot

    asset_ids = [uuid4(), uuid4()]
    assumption = _make_assumption()
    stats = _make_stats(assumption.assumption_id, asset_ids)
    cov = _make_covariance(assumption.assumption_id, asset_ids)
    handler = _make_handler(assumption=assumption, stats=stats, covariance=cov)

    sid = uuid4()
    snap = HoldingsSnapshot(
        snapshot_id=sid,
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[
            HoldingsPosition(snapshot_id=sid, asset_id=asset_ids[0], weight=0.6),
            HoldingsPosition(snapshot_id=sid, asset_id=asset_ids[1], weight=0.4),
        ],
    )
    handler._holdings_repo.get_by_id.return_value = snap

    constraints = OptimizationConstraints(long_only=True, turnover_cap=0.1)
    cmd = RunOptimizationCommand(
        assumption_id=assumption.assumption_id,
        run_type=RunType.MVP,
        constraints=constraints,
        reference_snapshot_id=sid,
    )
    await handler.handle(cmd)
    handler._holdings_repo.get_by_id.assert_awaited_once_with(sid)


async def test_turnover_cap_no_snapshot_falls_back_to_latest_run():
    handler = _make_handler()
    handler._optimization_repo.get_latest_for_universe.return_value = None
    constraints = OptimizationConstraints(long_only=True, turnover_cap=0.1)
    cmd = _make_cmd(constraints=constraints, reference_snapshot_id=None)
    await handler.handle(cmd)
    handler._optimization_repo.get_latest_for_universe.assert_awaited_once()
