"""Tests for src/domain/models/assumptions.py."""

import pytest
from datetime import date
from pydantic import ValidationError
from uuid import UUID, uuid4

from src.domain.models.assumptions import (
    AssetStats,
    AssumptionSet,
    CovarianceEntry,
    CovarianceMatrix,
)
from src.domain.models.enums import CovMethod, Estimator, Frequency, ReturnType


# UUIDs with a known lexicographic ordering for covariance tests
_LOW = UUID("00000000-0000-0000-0000-000000000001")
_HIGH = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
_UNKNOWN = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

_LOOKBACK_START = date(2020, 1, 1)
_LOOKBACK_END = date(2024, 12, 31)


# --- AssetStats ---

def test_asset_stats_construction():
    stats = AssetStats(
        assumption_id=uuid4(), asset_id=uuid4(), mu_annual=0.08, sigma_annual=0.15
    )
    assert stats.mu_annual == 0.08


def test_asset_stats_sigma_zero_raises():
    with pytest.raises(ValidationError):
        AssetStats(assumption_id=uuid4(), asset_id=uuid4(), mu_annual=0.08, sigma_annual=0.0)


def test_asset_stats_sigma_negative_raises():
    with pytest.raises(ValidationError):
        AssetStats(assumption_id=uuid4(), asset_id=uuid4(), mu_annual=0.08, sigma_annual=-0.1)


# --- CovarianceEntry ---

def test_covariance_entry_i_lt_j_unchanged():
    entry = CovarianceEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, cov_annual=0.01
    )
    assert entry.asset_id_i == _LOW


def test_covariance_entry_i_gt_j_swapped():
    entry = CovarianceEntry(
        assumption_id=uuid4(), asset_id_i=_HIGH, asset_id_j=_LOW, cov_annual=0.01
    )
    assert entry.asset_id_i == _LOW


def test_covariance_entry_swapped_j_becomes_high():
    entry = CovarianceEntry(
        assumption_id=uuid4(), asset_id_i=_HIGH, asset_id_j=_LOW, cov_annual=0.01
    )
    assert entry.asset_id_j == _HIGH


def test_covariance_entry_same_ids_ok():
    entry = CovarianceEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_LOW, cov_annual=0.04
    )
    assert entry.cov_annual == 0.04


# --- CovarianceMatrix ---

def _make_matrix() -> CovarianceMatrix:
    aid = uuid4()
    entry = CovarianceEntry(
        assumption_id=aid, asset_id_i=_LOW, asset_id_j=_HIGH, cov_annual=0.02
    )
    return CovarianceMatrix(assumption_id=aid, entries=[entry])


def test_covariance_matrix_get_forward_lookup():
    mat = _make_matrix()
    assert mat.get_covariance(_LOW, _HIGH) == 0.02


def test_covariance_matrix_get_reverse_lookup():
    mat = _make_matrix()
    assert mat.get_covariance(_HIGH, _LOW) == 0.02


def test_covariance_matrix_get_missing_returns_none():
    mat = _make_matrix()
    assert mat.get_covariance(_UNKNOWN, _LOW) is None


def test_covariance_matrix_from_full_matrix_entry_count():
    aid = uuid4()
    a, b = uuid4(), uuid4()
    mat = CovarianceMatrix.from_full_matrix(
        assumption_id=aid,
        asset_ids=[a, b],
        matrix=[[0.04, 0.01], [0.01, 0.09]],
    )
    assert len(mat.entries) == 3  # (a,a), (a,b), (b,b)


def test_covariance_matrix_from_full_matrix_diagonal_value():
    aid = uuid4()
    a, b = _LOW, _HIGH
    mat = CovarianceMatrix.from_full_matrix(
        assumption_id=aid,
        asset_ids=[a, b],
        matrix=[[0.04, 0.01], [0.01, 0.09]],
    )
    assert mat.get_covariance(a, a) == 0.04


def test_covariance_matrix_from_full_matrix_dimension_mismatch_raises():
    with pytest.raises(ValueError, match="3×3"):
        CovarianceMatrix.from_full_matrix(
            assumption_id=uuid4(),
            asset_ids=[uuid4(), uuid4(), uuid4()],  # 3 IDs
            matrix=[[0.04, 0.01], [0.01, 0.09]],   # 2×2 matrix
        )


# --- AssumptionSet ---

def test_assumption_set_construction():
    a = AssumptionSet(
        universe_id=uuid4(),
        frequency=Frequency.MONTHLY,
        return_type=ReturnType.SIMPLE,
        lookback_start=_LOOKBACK_START,
        lookback_end=_LOOKBACK_END,
        annualization_factor=12,
        rf_annual=0.045,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )
    assert a.rf_annual == 0.045


def test_assumption_set_psd_repair_defaults_false():
    a = AssumptionSet(
        universe_id=uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        lookback_start=_LOOKBACK_START,
        lookback_end=_LOOKBACK_END,
        annualization_factor=252,
        rf_annual=0.05,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )
    assert a.psd_repair_applied is False


def test_assumption_set_lookback_end_before_start_raises():
    with pytest.raises(ValidationError):
        AssumptionSet(
            universe_id=uuid4(),
            frequency=Frequency.MONTHLY,
            return_type=ReturnType.SIMPLE,
            lookback_start=date(2024, 1, 1),
            lookback_end=date(2020, 1, 1),
            annualization_factor=12,
            rf_annual=0.05,
            estimator=Estimator.HISTORICAL,
            cov_method=CovMethod.SAMPLE,
        )


def test_assumption_set_lookback_same_date_raises():
    d = date(2024, 1, 1)
    with pytest.raises(ValidationError):
        AssumptionSet(
            universe_id=uuid4(),
            frequency=Frequency.MONTHLY,
            return_type=ReturnType.SIMPLE,
            lookback_start=d,
            lookback_end=d,
            annualization_factor=12,
            rf_annual=0.05,
            estimator=Estimator.HISTORICAL,
            cov_method=CovMethod.SAMPLE,
        )


def test_assumption_set_create_derives_annualisation_from_frequency():
    a = AssumptionSet.create(
        universe_id=uuid4(),
        frequency=Frequency.MONTHLY,
        return_type=ReturnType.SIMPLE,
        lookback_start=_LOOKBACK_START,
        lookback_end=_LOOKBACK_END,
        rf_annual=0.05,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )
    assert a.annualization_factor == 12


def test_assumption_set_create_uses_explicit_annualisation_factor():
    a = AssumptionSet.create(
        universe_id=uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        lookback_start=_LOOKBACK_START,
        lookback_end=_LOOKBACK_END,
        rf_annual=0.05,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
        annualization_factor=260,  # custom trading calendar
    )
    assert a.annualization_factor == 260


def test_assumption_set_annualization_factor_zero_raises():
    with pytest.raises(ValidationError):
        AssumptionSet(
            universe_id=uuid4(),
            frequency=Frequency.MONTHLY,
            return_type=ReturnType.SIMPLE,
            lookback_start=_LOOKBACK_START,
            lookback_end=_LOOKBACK_END,
            annualization_factor=0,
            rf_annual=0.05,
            estimator=Estimator.HISTORICAL,
            cov_method=CovMethod.SAMPLE,
        )
