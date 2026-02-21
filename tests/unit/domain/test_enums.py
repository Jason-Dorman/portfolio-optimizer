"""Tests for src/domain/models/enums.py."""

from src.domain.models.enums import (
    AssetClass,
    BacktestStrategy,
    CovMethod,
    CovRepair,
    Estimator,
    Frequency,
    Geography,
    Objective,
    OptimizationStatus,
    RebalFrequency,
    ReferenceType,
    ReturnType,
    RunType,
    UniverseType,
)


# --- Frequency.periods_per_year ---

def test_frequency_daily_periods_per_year():
    assert Frequency.DAILY.periods_per_year == 252


def test_frequency_weekly_periods_per_year():
    assert Frequency.WEEKLY.periods_per_year == 52


def test_frequency_monthly_periods_per_year():
    assert Frequency.MONTHLY.periods_per_year == 12


# --- String mixin: enums compare equal to their string values ---

def test_asset_class_is_string_comparable():
    assert AssetClass.EQUITY == "equity"


def test_geography_is_string_comparable():
    assert Geography.US == "us"


def test_universe_type_active_value():
    assert UniverseType.ACTIVE == "active"


def test_universe_type_candidate_pool_value():
    assert UniverseType.CANDIDATE_POOL == "candidate_pool"


def test_return_type_simple_value():
    assert ReturnType.SIMPLE == "simple"


def test_return_type_log_value():
    assert ReturnType.LOG == "log"


def test_estimator_historical_value():
    assert Estimator.HISTORICAL == "historical"


def test_cov_method_ledoit_wolf_value():
    assert CovMethod.LEDOIT_WOLF == "ledoit_wolf"


def test_cov_repair_nearest_psd_value():
    assert CovRepair.NEAREST_PSD == "nearest_psd"


def test_cov_method_has_no_nearest_psd():
    assert not any(m.value == "nearest_psd" for m in CovMethod)


def test_optimization_status_success_value():
    assert OptimizationStatus.SUCCESS == "SUCCESS"


def test_optimization_status_infeasible_value():
    assert OptimizationStatus.INFEASIBLE == "INFEASIBLE"


def test_optimization_status_error_value():
    assert OptimizationStatus.ERROR == "ERROR"


def test_run_type_mvp_value():
    assert RunType.MVP == "MVP"


def test_run_type_tangency_value():
    assert RunType.TANGENCY == "TANGENCY"


def test_objective_min_var_value():
    assert Objective.MIN_VAR == "MIN_VAR"


def test_objective_max_sharpe_value():
    assert Objective.MAX_SHARPE == "MAX_SHARPE"


def test_reference_type_current_holdings_value():
    assert ReferenceType.CURRENT_HOLDINGS == "current_holdings"


def test_reference_type_seed_universe_value():
    assert ReferenceType.SEED_UNIVERSE == "seed_universe"


def test_backtest_strategy_tangency_rebal_value():
    assert BacktestStrategy.TANGENCY_REBAL == "TANGENCY_REBAL"


def test_rebal_frequency_threshold_value():
    assert RebalFrequency.THRESHOLD == "threshold"
