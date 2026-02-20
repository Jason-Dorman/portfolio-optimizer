"""Tests for CorrelationEntry and CorrelationMatrix in src/domain/models/assumptions.py."""

import pytest
from pydantic import ValidationError
from uuid import UUID, uuid4

from src.domain.models.assumptions import CorrelationEntry, CorrelationMatrix


_LOW = UUID("00000000-0000-0000-0000-000000000001")
_HIGH = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
_UNKNOWN = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


# --- CorrelationEntry ---

def test_correlation_entry_i_lt_j_unchanged():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, corr=0.5
    )
    assert entry.asset_id_i == _LOW


def test_correlation_entry_i_gt_j_swapped():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_HIGH, asset_id_j=_LOW, corr=0.5
    )
    assert entry.asset_id_i == _LOW


def test_correlation_entry_swapped_j_becomes_high():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_HIGH, asset_id_j=_LOW, corr=0.5
    )
    assert entry.asset_id_j == _HIGH


def test_correlation_entry_corr_above_one_raises():
    with pytest.raises(ValidationError):
        CorrelationEntry(
            assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, corr=1.01
        )


def test_correlation_entry_corr_below_neg_one_raises():
    with pytest.raises(ValidationError):
        CorrelationEntry(
            assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, corr=-1.01
        )


def test_correlation_entry_corr_at_positive_boundary_valid():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, corr=1.0
    )
    assert entry.corr == 1.0


def test_correlation_entry_corr_at_negative_boundary_valid():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_HIGH, corr=-1.0
    )
    assert entry.corr == -1.0


def test_correlation_entry_diagonal_same_ids_corr_one():
    entry = CorrelationEntry(
        assumption_id=uuid4(), asset_id_i=_LOW, asset_id_j=_LOW, corr=1.0
    )
    assert entry.corr == 1.0


# --- CorrelationMatrix ---

def _make_matrix() -> CorrelationMatrix:
    aid = uuid4()
    entry = CorrelationEntry(
        assumption_id=aid, asset_id_i=_LOW, asset_id_j=_HIGH, corr=0.6
    )
    return CorrelationMatrix(assumption_id=aid, entries=[entry])


def test_correlation_matrix_get_forward_lookup():
    mat = _make_matrix()
    assert mat.get_correlation(_LOW, _HIGH) == 0.6


def test_correlation_matrix_get_reverse_lookup():
    mat = _make_matrix()
    assert mat.get_correlation(_HIGH, _LOW) == 0.6


def test_correlation_matrix_get_missing_returns_none():
    mat = _make_matrix()
    assert mat.get_correlation(_UNKNOWN, _LOW) is None


def test_correlation_matrix_empty_entries_returns_none():
    mat = CorrelationMatrix(assumption_id=uuid4(), entries=[])
    assert mat.get_correlation(_LOW, _HIGH) is None
