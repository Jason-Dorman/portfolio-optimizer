"""Tests for src/domain/models/optimization.py."""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.optimization import (
    AssetBound,
    OptimizationConstraints,
    OptimizationResult,
    OptimizationRun,
    PortfolioWeight,
    RiskDecomposition,
)
from src.domain.models.enums import Objective, OptimizationStatus, RunType


# --- Helpers ---

def _valid_result(run_id=None) -> OptimizationResult:
    return OptimizationResult(
        run_id=run_id or uuid4(),
        exp_return=0.08,
        variance=0.04,
        stdev=0.2,
        sharpe=1.5,
        hhi=0.25,
        effective_n=4.0,
        explanation="Diversified across four assets.",
    )


def _constraints() -> OptimizationConstraints:
    return OptimizationConstraints.long_only_unconstrained()


# --- AssetBound ---

def test_asset_bound_construction():
    ab = AssetBound(asset_id=uuid4(), min_weight=0.0, max_weight=0.30)
    assert ab.max_weight == 0.30


def test_asset_bound_min_equals_max_valid():
    ab = AssetBound(asset_id=uuid4(), min_weight=0.10, max_weight=0.10)
    assert ab.min_weight == ab.max_weight


def test_asset_bound_min_greater_than_max_raises():
    with pytest.raises(ValidationError):
        AssetBound(asset_id=uuid4(), min_weight=0.50, max_weight=0.10)


# --- OptimizationConstraints ---

def test_optimization_constraints_defaults():
    c = OptimizationConstraints()
    assert c.long_only is True


def test_optimization_constraints_asset_bounds_empty_by_default():
    c = OptimizationConstraints()
    assert c.asset_bounds == []


def test_optimization_constraints_long_only_unconstrained():
    c = OptimizationConstraints.long_only_unconstrained()
    assert c.leverage_cap is None


def test_optimization_constraints_concentration_cap_above_one_raises():
    with pytest.raises(ValidationError):
        OptimizationConstraints(concentration_cap=1.1)


# --- RiskDecomposition ---

def test_risk_decomposition_construction():
    rd = RiskDecomposition(asset_id=uuid4(), mcr=0.10, crc=0.05, prc=0.25)
    assert rd.prc == 0.25


# --- PortfolioWeight ---

def test_portfolio_weight_construction():
    pw = PortfolioWeight(
        run_id=uuid4(), asset_id=uuid4(), weight=0.25, mcr=0.10, crc=0.05, prc=0.25
    )
    assert pw.weight == 0.25


def test_portfolio_weight_above_one_raises():
    with pytest.raises(ValidationError):
        PortfolioWeight(
            run_id=uuid4(), asset_id=uuid4(), weight=1.1, mcr=0.1, crc=0.05, prc=0.25
        )


def test_portfolio_weight_risk_decomposition_property_type():
    pw = PortfolioWeight(
        run_id=uuid4(), asset_id=uuid4(), weight=0.25, mcr=0.10, crc=0.05, prc=0.25
    )
    assert isinstance(pw.risk_decomposition, RiskDecomposition)


def test_portfolio_weight_risk_decomposition_asset_id():
    aid = uuid4()
    pw = PortfolioWeight(run_id=uuid4(), asset_id=aid, weight=0.25, mcr=0.10, crc=0.05, prc=0.25)
    assert pw.risk_decomposition.asset_id == aid


# --- OptimizationResult ---

def test_optimization_result_construction():
    r = _valid_result()
    assert r.exp_return == 0.08


def test_optimization_result_sharpe_none_allowed():
    r = OptimizationResult(
        run_id=uuid4(),
        exp_return=0.08,
        variance=0.04,
        stdev=0.2,
        sharpe=None,
        hhi=0.25,
        effective_n=4.0,
        explanation="MVP — Sharpe not computed.",
    )
    assert r.sharpe is None


def test_optimization_result_stdev_inconsistent_raises():
    with pytest.raises(ValidationError):
        OptimizationResult(
            run_id=uuid4(),
            exp_return=0.08,
            variance=0.05,   # 0.2² = 0.04 ≠ 0.05
            stdev=0.2,
            hhi=0.25,
            effective_n=4.0,
            explanation="Test",
        )


def test_optimization_result_effective_n_inconsistent_raises():
    with pytest.raises(ValidationError):
        OptimizationResult(
            run_id=uuid4(),
            exp_return=0.08,
            variance=0.04,
            stdev=0.2,
            hhi=0.25,
            effective_n=3.0,  # 1/0.25 = 4.0 ≠ 3.0
            explanation="Test",
        )


# --- OptimizationRun: status / reason invariant ---

def test_optimization_run_success_no_reason():
    run = OptimizationRun(
        assumption_id=uuid4(),
        run_type=RunType.MVP,
        objective=Objective.MIN_VAR,
        constraints=_constraints(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.infeasibility_reason is None


def test_optimization_run_success_with_reason_raises():
    with pytest.raises(ValidationError):
        OptimizationRun(
            assumption_id=uuid4(),
            run_type=RunType.MVP,
            objective=Objective.MIN_VAR,
            constraints=_constraints(),
            status=OptimizationStatus.SUCCESS,
            infeasibility_reason="Should not be here",
        )


def test_optimization_run_infeasible_with_reason():
    run = OptimizationRun(
        assumption_id=uuid4(),
        run_type=RunType.TANGENCY,
        objective=Objective.MAX_SHARPE,
        constraints=_constraints(),
        status=OptimizationStatus.INFEASIBLE,
        infeasibility_reason="All expected returns are below the risk-free rate.",
    )
    assert run.status == OptimizationStatus.INFEASIBLE


def test_optimization_run_infeasible_without_reason_raises():
    with pytest.raises(ValidationError):
        OptimizationRun(
            assumption_id=uuid4(),
            run_type=RunType.MVP,
            objective=Objective.MIN_VAR,
            constraints=_constraints(),
            status=OptimizationStatus.INFEASIBLE,
            infeasibility_reason=None,
        )


def test_optimization_run_infeasible_empty_reason_raises():
    with pytest.raises(ValidationError):
        OptimizationRun(
            assumption_id=uuid4(),
            run_type=RunType.MVP,
            objective=Objective.MIN_VAR,
            constraints=_constraints(),
            status=OptimizationStatus.INFEASIBLE,
            infeasibility_reason="",
        )


def test_optimization_run_error_with_reason():
    run = OptimizationRun(
        assumption_id=uuid4(),
        run_type=RunType.MVP,
        objective=Objective.MIN_VAR,
        constraints=_constraints(),
        status=OptimizationStatus.ERROR,
        infeasibility_reason="Solver convergence failure.",
    )
    assert run.status == OptimizationStatus.ERROR


def test_optimization_run_error_without_reason_raises():
    with pytest.raises(ValidationError):
        OptimizationRun(
            assumption_id=uuid4(),
            run_type=RunType.MVP,
            objective=Objective.MIN_VAR,
            constraints=_constraints(),
            status=OptimizationStatus.ERROR,
        )


# --- OptimizationRun: FRONTIER_POINT target_return ---

def test_optimization_run_frontier_point_with_target():
    run = OptimizationRun(
        assumption_id=uuid4(),
        run_type=RunType.FRONTIER_POINT,
        objective=Objective.MIN_VAR,
        constraints=_constraints(),
        target_return=0.07,
        status=OptimizationStatus.SUCCESS,
    )
    assert run.target_return == 0.07


def test_optimization_run_frontier_point_without_target_raises():
    with pytest.raises(ValidationError):
        OptimizationRun(
            assumption_id=uuid4(),
            run_type=RunType.FRONTIER_POINT,
            objective=Objective.MIN_VAR,
            constraints=_constraints(),
            target_return=None,
            status=OptimizationStatus.SUCCESS,
        )


# --- create_mvp factory ---

def test_create_mvp_locks_run_type():
    run = OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.run_type == RunType.MVP


def test_create_mvp_locks_objective():
    run = OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.objective == Objective.MIN_VAR


def test_create_mvp_infeasible_with_reason():
    run = OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.INFEASIBLE,
        infeasibility_reason="No feasible solution found.",
    )
    assert run.infeasibility_reason == "No feasible solution found."


def test_create_mvp_weights_default_empty():
    run = OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.weights == []


def test_create_mvp_accepts_weights():
    pw = PortfolioWeight(run_id=uuid4(), asset_id=uuid4(), weight=1.0, mcr=0.2, crc=0.1, prc=1.0)
    run = OptimizationRun.create_mvp(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
        weights=[pw],
    )
    assert len(run.weights) == 1


# --- create_tangency factory ---

def test_create_tangency_locks_run_type():
    run = OptimizationRun.create_tangency(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.run_type == RunType.TANGENCY


def test_create_tangency_locks_objective():
    run = OptimizationRun.create_tangency(
        assumption_id=uuid4(),
        status=OptimizationStatus.SUCCESS,
    )
    assert run.objective == Objective.MAX_SHARPE


def test_create_tangency_infeasible_with_reason():
    run = OptimizationRun.create_tangency(
        assumption_id=uuid4(),
        status=OptimizationStatus.INFEASIBLE,
        infeasibility_reason="No asset exceeds the risk-free rate.",
    )
    assert run.status == OptimizationStatus.INFEASIBLE


# --- create_frontier_point factory ---

def test_create_frontier_point_locks_run_type():
    run = OptimizationRun.create_frontier_point(
        assumption_id=uuid4(),
        target_return=0.08,
        status=OptimizationStatus.SUCCESS,
    )
    assert run.run_type == RunType.FRONTIER_POINT


def test_create_frontier_point_stores_target_return():
    run = OptimizationRun.create_frontier_point(
        assumption_id=uuid4(),
        target_return=0.08,
        status=OptimizationStatus.SUCCESS,
    )
    assert run.target_return == 0.08


def test_create_frontier_point_infeasible_with_reason():
    run = OptimizationRun.create_frontier_point(
        assumption_id=uuid4(),
        target_return=0.20,
        status=OptimizationStatus.INFEASIBLE,
        infeasibility_reason="Target return 20% exceeds achievable maximum of 12%.",
    )
    assert run.infeasibility_reason is not None
