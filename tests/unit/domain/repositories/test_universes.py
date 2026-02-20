"""Tests for src/domain/repositories/universes.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.universes import UniverseRepository


def _concrete() -> UniverseRepository:
    class _Impl(UniverseRepository):
        async def get_by_id(self, universe_id): return "found"
        async def list(self, universe_type=None, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def add_assets(self, universe_id, asset_ids, is_benchmark=False): return "updated"
        async def remove_assets(self, universe_id, asset_ids): return "updated"

    return _Impl()


def test_universe_repository_is_abstract():
    with pytest.raises(TypeError):
        UniverseRepository()  # type: ignore[abstract]


def test_universe_repository_concrete_instantiates():
    assert _concrete() is not None


def test_universe_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"


def test_universe_repository_add_assets_returns_updated():
    result = asyncio.run(_concrete().add_assets(uuid4(), [uuid4()]))
    assert result == "updated"


def test_universe_repository_remove_assets_returns_updated():
    result = asyncio.run(_concrete().remove_assets(uuid4(), [uuid4()]))
    assert result == "updated"
