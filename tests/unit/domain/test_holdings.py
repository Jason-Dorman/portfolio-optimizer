"""Tests for src/domain/models/holdings.py."""

import pytest
from datetime import date
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.holdings import HoldingsPosition, HoldingsSnapshot


TODAY = date(2025, 6, 1)


# --- HoldingsPosition ---

def test_holdings_position_construction():
    pos = HoldingsPosition(snapshot_id=uuid4(), asset_id=uuid4(), weight=0.5)
    assert pos.weight == 0.5


def test_holdings_position_market_value_defaults_none():
    pos = HoldingsPosition(snapshot_id=uuid4(), asset_id=uuid4(), weight=0.5)
    assert pos.market_value is None


def test_holdings_position_market_value_stored():
    pos = HoldingsPosition(
        snapshot_id=uuid4(), asset_id=uuid4(), weight=0.5, market_value=10_000.0
    )
    assert pos.market_value == 10_000.0


def test_holdings_position_weight_below_zero_raises():
    with pytest.raises(ValidationError):
        HoldingsPosition(snapshot_id=uuid4(), asset_id=uuid4(), weight=-0.1)


def test_holdings_position_weight_above_one_raises():
    with pytest.raises(ValidationError):
        HoldingsPosition(snapshot_id=uuid4(), asset_id=uuid4(), weight=1.1)


# --- HoldingsSnapshot ---

def test_holdings_snapshot_empty_positions_valid():
    snap = HoldingsSnapshot(label="Empty", snapshot_date=TODAY)
    assert snap.positions == []


def test_holdings_snapshot_weights_sum_to_one_valid():
    sid = uuid4()
    snap = HoldingsSnapshot(
        label="My Portfolio",
        snapshot_date=TODAY,
        positions=[
            HoldingsPosition(snapshot_id=sid, asset_id=uuid4(), weight=0.6),
            HoldingsPosition(snapshot_id=sid, asset_id=uuid4(), weight=0.4),
        ],
    )
    assert len(snap.positions) == 2


def test_holdings_snapshot_weights_not_sum_to_one_raises():
    sid = uuid4()
    with pytest.raises(ValidationError):
        HoldingsSnapshot(
            label="Bad",
            snapshot_date=TODAY,
            positions=[
                HoldingsPosition(snapshot_id=sid, asset_id=uuid4(), weight=0.6),
                HoldingsPosition(snapshot_id=sid, asset_id=uuid4(), weight=0.5),
            ],
        )


def test_holdings_snapshot_id_auto_generated():
    snap = HoldingsSnapshot(label="Test", snapshot_date=TODAY)
    assert snap.snapshot_id is not None


# --- HoldingsSnapshot.from_market_values ---

def test_from_market_values_count():
    a1, a2 = uuid4(), uuid4()
    snap = HoldingsSnapshot.from_market_values(
        label="Brokerage",
        snapshot_date=TODAY,
        positions=[(a1, 200.0), (a2, 800.0)],
    )
    assert len(snap.positions) == 2


def test_from_market_values_normalises_first_weight():
    a1, a2 = uuid4(), uuid4()
    snap = HoldingsSnapshot.from_market_values(
        label="Brokerage",
        snapshot_date=TODAY,
        positions=[(a1, 200.0), (a2, 800.0)],
    )
    assert abs(snap.positions[0].weight - 0.2) < 1e-9


def test_from_market_values_weights_sum_to_one():
    a1, a2, a3 = uuid4(), uuid4(), uuid4()
    snap = HoldingsSnapshot.from_market_values(
        label="Brokerage",
        snapshot_date=TODAY,
        positions=[(a1, 100.0), (a2, 300.0), (a3, 600.0)],
    )
    total = sum(p.weight for p in snap.positions)
    assert abs(total - 1.0) < 1e-9


def test_from_market_values_preserves_market_value():
    a1, a2 = uuid4(), uuid4()
    snap = HoldingsSnapshot.from_market_values(
        label="Brokerage",
        snapshot_date=TODAY,
        positions=[(a1, 200.0), (a2, 800.0)],
    )
    assert snap.positions[0].market_value == 200.0


def test_from_market_values_all_positions_share_snapshot_id():
    a1, a2 = uuid4(), uuid4()
    snap = HoldingsSnapshot.from_market_values(
        label="Brokerage",
        snapshot_date=TODAY,
        positions=[(a1, 500.0), (a2, 500.0)],
    )
    assert snap.positions[0].snapshot_id == snap.positions[1].snapshot_id


def test_from_market_values_zero_total_raises():
    with pytest.raises(ValueError, match="positive"):
        HoldingsSnapshot.from_market_values(
            label="Zero",
            snapshot_date=TODAY,
            positions=[(uuid4(), 0.0)],
        )


def test_from_market_values_negative_total_raises():
    with pytest.raises(ValueError, match="positive"):
        HoldingsSnapshot.from_market_values(
            label="Negative",
            snapshot_date=TODAY,
            positions=[(uuid4(), -100.0)],
        )
