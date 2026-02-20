"""Tests for src/domain/repositories/assumptions.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.assumptions import AssumptionRepository


def _concrete() -> AssumptionRepository:
    class _Impl(AssumptionRepository):
        async def get_by_id(self, assumption_id): return "found"
        async def list(self, universe_id=None, limit=50, offset=0): return []
        async def create(self, assumption_set, stats, covariance): return assumption_set
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def get_covariance_matrix(self, assumption_id): return "cov"
        async def get_correlation_matrix(self, assumption_id): return "corr"

    return _Impl()


def test_assumption_repository_is_abstract():
    with pytest.raises(TypeError):
        AssumptionRepository()  # type: ignore[abstract]


def test_assumption_repository_concrete_instantiates():
    assert _concrete() is not None


def test_assumption_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_assumption_repository_get_covariance_matrix():
    result = asyncio.run(_concrete().get_covariance_matrix(uuid4()))
    assert result == "cov"


def test_assumption_repository_get_correlation_matrix():
    result = asyncio.run(_concrete().get_correlation_matrix(uuid4()))
    assert result == "corr"
