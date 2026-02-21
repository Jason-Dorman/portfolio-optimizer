"""Tests for the get_repositories() DI factory."""

from unittest.mock import AsyncMock

from src.infrastructure.persistence.repositories import (
    Repositories,
    SqlAssetRepository,
    SqlAssumptionRepository,
    SqlBacktestRepository,
    SqlDriftRepository,
    SqlHoldingsRepository,
    SqlOptimizationRepository,
    SqlPriceRepository,
    SqlReturnRepository,
    SqlScenarioRepository,
    SqlScreeningRepository,
    SqlUniverseRepository,
    get_repositories,
)


def _repos():
    return get_repositories(AsyncMock())


def test_get_repositories_returns_repositories_instance():
    assert isinstance(_repos(), Repositories)


def test_repositories_assets_is_correct_type():
    assert isinstance(_repos().assets, SqlAssetRepository)


def test_repositories_universes_is_correct_type():
    assert isinstance(_repos().universes, SqlUniverseRepository)


def test_repositories_holdings_is_correct_type():
    assert isinstance(_repos().holdings, SqlHoldingsRepository)


def test_repositories_prices_is_correct_type():
    assert isinstance(_repos().prices, SqlPriceRepository)


def test_repositories_returns_is_correct_type():
    assert isinstance(_repos().returns, SqlReturnRepository)


def test_repositories_assumptions_is_correct_type():
    assert isinstance(_repos().assumptions, SqlAssumptionRepository)


def test_repositories_screening_is_correct_type():
    assert isinstance(_repos().screening, SqlScreeningRepository)


def test_repositories_optimization_is_correct_type():
    assert isinstance(_repos().optimization, SqlOptimizationRepository)


def test_repositories_drift_is_correct_type():
    assert isinstance(_repos().drift, SqlDriftRepository)


def test_repositories_backtest_is_correct_type():
    assert isinstance(_repos().backtest, SqlBacktestRepository)


def test_repositories_scenarios_is_correct_type():
    assert isinstance(_repos().scenarios, SqlScenarioRepository)


def test_repositories_dataclass_has_eleven_fields():
    assert len(Repositories.__dataclass_fields__) == 11
