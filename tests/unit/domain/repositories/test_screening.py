"""Tests for src/domain/repositories/screening.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.screening import ScreeningRepository


def _concrete() -> ScreeningRepository:
    class _Impl(ScreeningRepository):
        async def get_by_id(self, screening_id): return "found"
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def get_scores(self, screening_id, limit=50, offset=0): return ["score1", "score2"]

    return _Impl()


def test_screening_repository_is_abstract():
    with pytest.raises(TypeError):
        ScreeningRepository()  # type: ignore[abstract]


def test_screening_repository_concrete_instantiates():
    assert _concrete() is not None


def test_screening_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_screening_repository_get_scores_returns_list():
    result = asyncio.run(_concrete().get_scores(uuid4()))
    assert len(result) == 2
