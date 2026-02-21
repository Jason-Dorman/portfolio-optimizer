"""Tests for SqlScenarioRepository — mapping and create guards."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.persistence.repositories.scenarios import SqlScenarioRepository


def _orm_def(**overrides):
    defaults = {
        "scenario_id": uuid4(),
        "name": "Equity Crash -30%",
        "shocks": {"equity": -0.30},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_result(**overrides):
    defaults = {
        "result_id": uuid4(),
        "run_id": uuid4(),
        "scenario_id": uuid4(),
        "shocked_return": -0.12,
        "shocked_vol": 0.22,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _def_to_domain mapping ---

def test_def_to_domain_maps_name():
    assert SqlScenarioRepository._def_to_domain(_orm_def(name="Rate Spike")).name == "Rate Spike"


def test_def_to_domain_maps_shocks_dict():
    result = SqlScenarioRepository._def_to_domain(_orm_def(shocks={"equity": -0.20}))
    assert result.shocks == {"equity": -0.20}


# --- _result_to_domain mapping ---

def test_result_to_domain_maps_shocked_return():
    result = SqlScenarioRepository._result_to_domain(_orm_result(shocked_return=-0.15))
    assert result.shocked_return == -0.15


def test_result_to_domain_maps_shocked_vol_none():
    result = SqlScenarioRepository._result_to_domain(_orm_result(shocked_vol=None))
    assert result.shocked_vol is None


# --- create guard ---

async def test_create_raises_not_implemented():
    repo = SqlScenarioRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.create(None)  # type: ignore[arg-type]


async def test_update_raises():
    repo = SqlScenarioRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]
