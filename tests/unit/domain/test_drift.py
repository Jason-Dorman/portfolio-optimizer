"""Tests for src/domain/models/drift.py."""

import pytest
from datetime import date
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.drift import DriftCheck, DriftPosition


TODAY = date(2025, 6, 1)


# --- DriftPosition ---

def test_drift_position_not_breached():
    pos = DriftPosition(
        drift_id=uuid4(),
        asset_id=uuid4(),
        target_weight=0.40,
        current_weight=0.43,
        drift_abs=0.03,
        breached=False,
    )
    assert pos.breached is False


def test_drift_position_breached_with_explanation():
    pos = DriftPosition(
        drift_id=uuid4(),
        asset_id=uuid4(),
        target_weight=0.40,
        current_weight=0.47,
        drift_abs=0.07,
        breached=True,
        explanation="SPY has grown from 40% to 47% due to price appreciation.",
    )
    assert pos.explanation is not None


def test_drift_position_not_breached_explanation_optional():
    pos = DriftPosition(
        drift_id=uuid4(),
        asset_id=uuid4(),
        target_weight=0.40,
        current_weight=0.43,
        drift_abs=0.03,
        breached=False,
        explanation=None,
    )
    assert pos.explanation is None


def test_drift_position_breached_without_explanation_raises():
    with pytest.raises(ValidationError):
        DriftPosition(
            drift_id=uuid4(),
            asset_id=uuid4(),
            target_weight=0.40,
            current_weight=0.47,
            drift_abs=0.07,
            breached=True,
            explanation=None,
        )


def test_drift_position_drift_abs_inconsistent_raises():
    with pytest.raises(ValidationError):
        DriftPosition(
            drift_id=uuid4(),
            asset_id=uuid4(),
            target_weight=0.40,
            current_weight=0.43,
            drift_abs=0.10,  # actual |0.43 - 0.40| = 0.03 ≠ 0.10
            breached=False,
        )


def test_drift_position_drift_abs_consistent():
    pos = DriftPosition(
        drift_id=uuid4(),
        asset_id=uuid4(),
        target_weight=0.30,
        current_weight=0.36,
        drift_abs=0.06,
        breached=True,
        explanation="Drifted 6 percentage points above target.",
    )
    assert abs(pos.drift_abs - abs(pos.current_weight - pos.target_weight)) < 1e-9


# --- DriftCheck ---

def test_drift_check_construction():
    dc = DriftCheck(
        run_id=uuid4(),
        check_date=TODAY,
        threshold_pct=0.05,
        any_breach=False,
    )
    assert dc.any_breach is False


def test_drift_check_id_auto_generated():
    dc = DriftCheck(run_id=uuid4(), check_date=TODAY, threshold_pct=0.05, any_breach=False)
    assert dc.drift_id is not None


def test_drift_check_create_no_breaches_any_breach_false():
    a1, a2 = uuid4(), uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[
            (a1, 0.60, 0.62, None),
            (a2, 0.40, 0.38, None),
        ],
        threshold_pct=0.05,
    )
    assert dc.any_breach is False


def test_drift_check_create_with_breach_any_breach_true():
    a1 = uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[
            (a1, 0.40, 0.47, "Position drifted 7 pp above target."),
        ],
        threshold_pct=0.05,
    )
    assert dc.any_breach is True


def test_drift_check_create_position_count():
    a1, a2 = uuid4(), uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[(a1, 0.5, 0.53, None), (a2, 0.5, 0.47, None)],
    )
    assert len(dc.positions) == 2


def test_drift_check_create_computes_drift_abs():
    a1 = uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[(a1, 0.40, 0.43, None)],
    )
    assert abs(dc.positions[0].drift_abs - 0.03) < 1e-9


def test_drift_check_create_positions_share_drift_id():
    a1, a2 = uuid4(), uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[(a1, 0.5, 0.53, None), (a2, 0.5, 0.47, None)],
    )
    assert dc.positions[0].drift_id == dc.positions[1].drift_id


def test_drift_check_create_drift_id_matches_check():
    a1 = uuid4()
    dc = DriftCheck.create(
        run_id=uuid4(),
        check_date=TODAY,
        raw_positions=[(a1, 0.5, 0.52, None)],
    )
    assert dc.positions[0].drift_id == dc.drift_id


def test_drift_check_default_threshold():
    dc = DriftCheck.create(run_id=uuid4(), check_date=TODAY, raw_positions=[])
    assert dc.threshold_pct == 0.05
