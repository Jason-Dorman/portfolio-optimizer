"""Tests for SqlDriftRepository — mapping and immutability."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.persistence.repositories.drift import (
    SqlDriftRepository,
    _check_to_domain,
    _position_to_domain,
)


def _orm_position(**overrides):
    defaults = {
        "drift_id": uuid4(),
        "asset_id": uuid4(),
        "target_weight": 0.20,
        "current_weight": 0.26,
        "drift_abs": 0.06,
        "breached": True,
        "explanation": "SPY drifted 6 pp above target.",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_check(**overrides):
    defaults = {
        "drift_id": uuid4(),
        "run_id": uuid4(),
        "check_date": date(2025, 6, 1),
        "threshold_pct": 0.05,
        "any_breach": True,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _position_to_domain mapping ---

def test_position_to_domain_maps_breached():
    assert _position_to_domain(_orm_position(breached=True)).breached is True


def test_position_to_domain_maps_drift_abs():
    assert _position_to_domain(_orm_position(drift_abs=0.06)).drift_abs == 0.06


def test_position_to_domain_maps_explanation():
    result = _position_to_domain(_orm_position(explanation="Drift exceeded."))
    assert result.explanation == "Drift exceeded."


# --- _check_to_domain mapping ---

def test_check_to_domain_maps_any_breach():
    assert _check_to_domain(_orm_check(any_breach=False), []).any_breach is False


def test_check_to_domain_embeds_positions():
    positions = [_position_to_domain(_orm_position())]
    result = _check_to_domain(_orm_check(), positions)
    assert len(result.positions) == 1


# --- immutability guards ---

async def test_update_raises():
    repo = SqlDriftRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlDriftRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
