"""Tests for src/domain/repositories/optimization.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.optimization import OptimizationRepository


def _concrete() -> OptimizationRepository:
    class _Impl(OptimizationRepository):
        async def get_by_id(self, run_id): return "found"
        async def list(self, assumption_id=None, status=None, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def get_weights(self, run_id): return ["w1", "w2"]
        async def get_latest_for_universe(self, universe_id): return "latest_run"

    return _Impl()


def test_optimization_repository_is_abstract():
    with pytest.raises(TypeError):
        OptimizationRepository()  # type: ignore[abstract]


def test_optimization_repository_concrete_instantiates():
    assert _concrete() is not None


def test_optimization_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_optimization_repository_get_weights_returns_list():
    result = asyncio.run(_concrete().get_weights(uuid4()))
    assert len(result) == 2


def test_optimization_repository_get_latest_for_universe():
    result = asyncio.run(_concrete().get_latest_for_universe(uuid4()))
    assert result == "latest_run"
