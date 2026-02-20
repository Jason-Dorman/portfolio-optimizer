"""Tests for src/domain/repositories/returns.py."""

import asyncio
import pytest

from src.domain.repositories.returns import ReturnRepository


def _concrete() -> ReturnRepository:
    class _Impl(ReturnRepository):
        async def get_returns(self, asset_id, frequency, return_type, start=None, end=None): return []
        async def bulk_insert(self, points): return len(points)

    return _Impl()


def test_return_repository_is_abstract():
    with pytest.raises(TypeError):
        ReturnRepository()  # type: ignore[abstract]


def test_return_repository_concrete_instantiates():
    assert _concrete() is not None


def test_return_repository_bulk_insert_returns_count():
    result = asyncio.run(_concrete().bulk_insert(["x", "y"]))
    assert result == 2
