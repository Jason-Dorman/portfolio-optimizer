"""Tests for SqlOptimizationRepository — mapping and immutability."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.models.optimization import OptimizationConstraints
from src.infrastructure.persistence.repositories.optimization import (
    SqlOptimizationRepository,
    _run_to_domain,
    _weight_to_domain,
)


def _orm_weight(**overrides):
    defaults = {
        "run_id": uuid4(),
        "asset_id": uuid4(),
        "weight": 0.25,
        "mcr": 0.12,
        "crc": 0.03,
        "prc": 0.20,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_run(**overrides):
    defaults = {
        "run_id": uuid4(),
        "assumption_id": uuid4(),
        "run_type": "MVP",
        "objective": "MIN_VAR",
        "constraints": {"long_only": True, "asset_bounds": [], "leverage_cap": None,
                        "concentration_cap": None, "turnover_cap": None},
        "reference_snapshot_id": None,
        "target_return": None,
        "status": "SUCCESS",
        "infeasibility_reason": None,
        "solver_meta": None,
        "created_at": datetime.now(timezone.utc),
        "result": None,
        "weights": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _weight_to_domain mapping ---

def test_weight_to_domain_maps_mcr():
    assert _weight_to_domain(_orm_weight(mcr=0.15)).mcr == 0.15


def test_weight_to_domain_maps_weight():
    assert _weight_to_domain(_orm_weight(weight=0.30)).weight == 0.30


def test_weight_to_domain_maps_prc():
    assert _weight_to_domain(_orm_weight(prc=0.25)).prc == 0.25


# --- _run_to_domain mapping ---

def test_run_to_domain_deserializes_constraints():
    result = _run_to_domain(_orm_run())
    assert isinstance(result.constraints, OptimizationConstraints)


def test_run_to_domain_constraints_long_only_true():
    result = _run_to_domain(_orm_run())
    assert result.constraints.long_only is True


def test_run_to_domain_maps_status_enum():
    from src.domain.models.enums import OptimizationStatus
    result = _run_to_domain(_orm_run(status="SUCCESS"))
    assert result.status == OptimizationStatus.SUCCESS


# --- immutability guards ---

async def test_update_raises():
    repo = SqlOptimizationRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlOptimizationRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
