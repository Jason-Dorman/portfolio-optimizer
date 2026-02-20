"""Tests for src/domain/repositories/backtest.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.backtest import BacktestRepository


def _concrete() -> BacktestRepository:
    class _Impl(BacktestRepository):
        async def get_by_id(self, backtest_id): return "found"
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def get_points(self, backtest_id): return ["pt1", "pt2"]
        async def get_summary(self, backtest_id): return "summary"

    return _Impl()


def test_backtest_repository_is_abstract():
    with pytest.raises(TypeError):
        BacktestRepository()  # type: ignore[abstract]


def test_backtest_repository_concrete_instantiates():
    assert _concrete() is not None


def test_backtest_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_backtest_repository_get_points_returns_list():
    result = asyncio.run(_concrete().get_points(uuid4()))
    assert len(result) == 2


def test_backtest_repository_get_summary_returns_value():
    result = asyncio.run(_concrete().get_summary(uuid4()))
    assert result == "summary"
