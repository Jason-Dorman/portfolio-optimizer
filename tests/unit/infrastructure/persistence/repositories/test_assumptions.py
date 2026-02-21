"""Tests for SqlAssumptionRepository — mapping, correlation math, immutability."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.models.enums import CovMethod, Estimator, Frequency, ReturnType
from src.infrastructure.persistence.repositories.assumptions import SqlAssumptionRepository


def _orm_assumption_set(**overrides):
    defaults = {
        "assumption_id": uuid4(),
        "universe_id": uuid4(),
        "frequency": "monthly",
        "return_type": "simple",
        "lookback_start": date(2020, 1, 1),
        "lookback_end": date(2025, 1, 1),
        "annualization_factor": 12,
        "rf_annual": 0.04,
        "estimator": "historical",
        "cov_method": "sample",
        "psd_repair_applied": False,
        "psd_repair_note": None,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _to_domain mapping ---

def test_to_domain_maps_estimator_enum():
    result = SqlAssumptionRepository._to_domain(_orm_assumption_set(estimator="ewma"))
    assert result.estimator == Estimator.EWMA


def test_to_domain_maps_cov_method_enum():
    result = SqlAssumptionRepository._to_domain(_orm_assumption_set(cov_method="ledoit_wolf"))
    assert result.cov_method == CovMethod.LEDOIT_WOLF


def test_to_domain_maps_rf_annual():
    result = SqlAssumptionRepository._to_domain(_orm_assumption_set(rf_annual=0.05))
    assert result.rf_annual == 0.05


def test_to_domain_maps_frequency_enum():
    result = SqlAssumptionRepository._to_domain(_orm_assumption_set(frequency="daily"))
    assert result.frequency == Frequency.DAILY


# --- get_correlation_matrix ---

async def test_get_correlation_matrix_returns_none_when_assumption_missing():
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    repo = SqlAssumptionRepository(session)
    assert await repo.get_correlation_matrix(uuid4()) is None


async def test_get_covariance_matrix_returns_none_when_assumption_missing():
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    repo = SqlAssumptionRepository(session)
    assert await repo.get_covariance_matrix(uuid4()) is None


# --- immutability guards ---

async def test_update_raises():
    repo = SqlAssumptionRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlAssumptionRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
