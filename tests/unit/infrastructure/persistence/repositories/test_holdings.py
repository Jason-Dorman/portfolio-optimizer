"""Tests for SqlHoldingsRepository — mapping and immutability guards."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.persistence.repositories.holdings import (
    SqlHoldingsRepository,
    _snapshot_to_domain,
)


def _orm_position(snapshot_id, **overrides):
    defaults = {
        "snapshot_id": snapshot_id,
        "asset_id": uuid4(),
        "weight": 0.5,
        "market_value": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_snapshot(**overrides):
    sid = uuid4()
    defaults = {
        "snapshot_id": sid,
        "label": "My Portfolio",
        "snapshot_date": date(2025, 1, 1),
        "created_at": datetime.now(timezone.utc),
        "positions": [_orm_position(sid, weight=1.0)],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- mapping ---

def test_snapshot_to_domain_includes_positions_when_requested():
    row = _orm_snapshot()
    result = _snapshot_to_domain(row, include_positions=True)
    assert len(result.positions) == 1


def test_snapshot_to_domain_omits_positions_when_not_requested():
    row = _orm_snapshot()
    result = _snapshot_to_domain(row, include_positions=False)
    assert result.positions == []


def test_snapshot_to_domain_maps_label():
    result = _snapshot_to_domain(_orm_snapshot(label="Q1 2025"), include_positions=False)
    assert result.label == "Q1 2025"


def test_snapshot_to_domain_maps_position_weight():
    row = _orm_snapshot()
    result = _snapshot_to_domain(row, include_positions=True)
    assert result.positions[0].weight == 1.0


# --- immutability guards ---

async def test_update_raises():
    repo = SqlHoldingsRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlHoldingsRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
