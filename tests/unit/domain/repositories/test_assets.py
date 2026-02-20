"""Tests for src/domain/repositories/assets.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.assets import AssetRepository


def _concrete() -> AssetRepository:
    class _Impl(AssetRepository):
        async def get_by_id(self, asset_id): return "found"
        async def get_by_ticker(self, ticker): return None
        async def list(self, ticker=None, asset_class=None, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None

    return _Impl()


def test_asset_repository_is_abstract():
    with pytest.raises(TypeError):
        AssetRepository()  # type: ignore[abstract]


def test_asset_repository_concrete_instantiates():
    assert _concrete() is not None


def test_asset_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "found"
