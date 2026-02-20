"""Tests for src/domain/repositories/drift.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.drift import DriftRepository


def _concrete() -> DriftRepository:
    class _Impl(DriftRepository):
        async def get_by_id(self, drift_id): return "found"
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def get_positions(self, drift_id): return ["pos1", "pos2", "pos3"]

    return _Impl()


def test_drift_repository_is_abstract():
    with pytest.raises(TypeError):
        DriftRepository()  # type: ignore[abstract]


def test_drift_repository_concrete_instantiates():
    assert _concrete() is not None


def test_drift_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_drift_repository_get_positions_returns_list():
    result = asyncio.run(_concrete().get_positions(uuid4()))
    assert len(result) == 3
