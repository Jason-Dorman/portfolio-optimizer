"""Tests for src/domain/repositories/prices.py."""

import asyncio
import pytest

from src.domain.repositories.prices import PriceRepository


def _concrete() -> PriceRepository:
    class _Impl(PriceRepository):
        async def get_prices(self, asset_id, frequency, start=None, end=None): return []
        async def get_latest_date(self, asset_id, frequency): return None
        async def bulk_insert(self, bars): return len(bars)

    return _Impl()


def test_price_repository_is_abstract():
    with pytest.raises(TypeError):
        PriceRepository()  # type: ignore[abstract]


def test_price_repository_concrete_instantiates():
    assert _concrete() is not None


def test_price_repository_bulk_insert_returns_count():
    result = asyncio.run(_concrete().bulk_insert(["a", "b", "c"]))
    assert result == 3


def test_price_repository_get_latest_date_none_when_empty():
    from uuid import uuid4
    from src.domain.models.enums import Frequency
    result = asyncio.run(_concrete().get_latest_date(uuid4(), Frequency.DAILY))
    assert result is None
