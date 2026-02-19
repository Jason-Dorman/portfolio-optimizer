"""Unit tests for ORM model structure.

Verifies table names, nullability, composite PKs, constraints, and
package registration. No database connection is required.
"""

import src.infrastructure.persistence  # noqa: F401 — registers all mappers
from src.infrastructure.database import Base
from src.infrastructure.persistence.models import __all__ as models_all
from src.infrastructure.persistence.models.backtesting import BacktestSummary
from src.infrastructure.persistence.models.drift import DriftCheckPosition
from src.infrastructure.persistence.models.estimation import AssumptionCov
from src.infrastructure.persistence.models.holdings import CurrentHoldingsPosition
from src.infrastructure.persistence.models.optimization import OptimizationResult
from src.infrastructure.persistence.models.reference import Asset, UniverseAsset
from src.infrastructure.persistence.models.screening import ScreeningRun


# --- Table names ---

def test_asset_tablename():
    assert Asset.__tablename__ == "assets"


def test_screening_run_tablename():
    assert ScreeningRun.__tablename__ == "screening_runs"


# --- Nullable / not-null columns ---

def test_asset_sector_is_nullable():
    assert Asset.__table__.c["sector"].nullable is True


def test_asset_ticker_is_not_nullable():
    assert Asset.__table__.c["ticker"].nullable is False


def test_current_holdings_position_market_value_is_nullable():
    assert CurrentHoldingsPosition.__table__.c["market_value"].nullable is True


def test_drift_check_position_explanation_is_nullable():
    # Required only when breached=True; enforced at application layer
    assert DriftCheckPosition.__table__.c["explanation"].nullable is True


# --- Composite primary keys ---

def test_assumption_cov_has_three_column_pk():
    pk_cols = [c.name for c in AssumptionCov.__table__.primary_key.columns]
    assert len(pk_cols) == 3


def test_universe_asset_has_two_column_pk():
    pk_cols = [c.name for c in UniverseAsset.__table__.primary_key.columns]
    assert len(pk_cols) == 2


# --- 1:1 PK-as-FK tables ---

def test_optimization_result_pk_is_also_fk():
    col = OptimizationResult.__table__.c["run_id"]
    assert col.primary_key is True
    assert len(col.foreign_keys) == 1


def test_backtest_summary_pk_is_also_fk():
    col = BacktestSummary.__table__.c["backtest_id"]
    assert col.primary_key is True
    assert len(col.foreign_keys) == 1


# --- Constraints ---

def test_screening_run_has_reference_consistency_check():
    constraint_names = {c.name for c in ScreeningRun.__table__.constraints}
    assert "ck_screening_runs_reference_consistency" in constraint_names


def test_screening_run_reference_ids_are_nullable():
    assert ScreeningRun.__table__.c["reference_snapshot_id"].nullable is True
    assert ScreeningRun.__table__.c["reference_universe_id"].nullable is True


# --- Package registration ---

def test_all_models_registered_in_base_metadata():
    registered = set(Base.metadata.tables.keys())
    assert "assets" in registered
    assert "assumption_cov" in registered
    assert "drift_check_positions" in registered


def test_models_package_exports_24_classes():
    assert len(models_all) == 24
