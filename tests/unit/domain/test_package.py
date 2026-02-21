"""Tests for src/domain/models/__init__.py — package exports."""

from src.domain.models import __all__ as domain_all
from src.domain.models import (
    # spot-check one import from each module
    AssetClass,
    Asset,
    HoldingsSnapshot,
    AssumptionSet,
    ScreeningRun,
    OptimizationRun,
    DriftCheck,
    BacktestRun,
    ScenarioDefinition,
)


def test_domain_models_exports_45_names():
    assert len(domain_all) == 45


def test_asset_class_importable_from_package():
    assert AssetClass.EQUITY == "equity"


def test_asset_importable_from_package():
    assert Asset.__name__ == "Asset"


def test_holdings_snapshot_importable_from_package():
    assert HoldingsSnapshot.__name__ == "HoldingsSnapshot"


def test_assumption_set_importable_from_package():
    assert AssumptionSet.__name__ == "AssumptionSet"


def test_screening_run_importable_from_package():
    assert ScreeningRun.__name__ == "ScreeningRun"


def test_optimization_run_importable_from_package():
    assert OptimizationRun.__name__ == "OptimizationRun"


def test_drift_check_importable_from_package():
    assert DriftCheck.__name__ == "DriftCheck"


def test_backtest_run_importable_from_package():
    assert BacktestRun.__name__ == "BacktestRun"


def test_scenario_definition_importable_from_package():
    assert ScenarioDefinition.__name__ == "ScenarioDefinition"
