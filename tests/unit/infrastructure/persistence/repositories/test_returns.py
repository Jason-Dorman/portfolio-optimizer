"""Tests for SqlReturnRepository — mapping and bulk_insert edge cases."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from src.domain.models.enums import Frequency, ReturnType
from src.infrastructure.persistence.repositories.returns import SqlReturnRepository


def _orm_point(**overrides):
    defaults = {
        "asset_id": uuid4(),
        "bar_date": date(2025, 1, 2),
        "frequency": "daily",
        "return_type": "simple",
        "ret": 0.012,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _to_domain mapping ---

def test_to_domain_maps_frequency_enum():
    assert SqlReturnRepository._to_domain(_orm_point()).frequency == Frequency.DAILY


def test_to_domain_maps_return_type_enum():
    assert SqlReturnRepository._to_domain(_orm_point(return_type="log")).return_type == ReturnType.LOG


def test_to_domain_maps_ret_value():
    assert SqlReturnRepository._to_domain(_orm_point(ret=0.05)).ret == 0.05


# --- bulk_insert edge cases ---

async def test_bulk_insert_empty_list_returns_zero():
    repo = SqlReturnRepository(AsyncMock())
    assert await repo.bulk_insert([]) == 0
