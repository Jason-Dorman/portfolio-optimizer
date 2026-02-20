"""Tests for src/domain/repositories/holdings.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.holdings import HoldingsRepository


def _concrete() -> HoldingsRepository:
    class _Impl(HoldingsRepository):
        async def get_by_id(self, snapshot_id): return "found"
        async def get_latest(self): return "latest"
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None

    return _Impl()


def test_holdings_repository_is_abstract():
    with pytest.raises(TypeError):
        HoldingsRepository()  # type: ignore[abstract]


def test_holdings_repository_concrete_instantiates():
    assert _concrete() is not None


def test_holdings_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_holdings_repository_get_latest_returns_value():
    result = asyncio.run(_concrete().get_latest())
    assert result == "latest"
