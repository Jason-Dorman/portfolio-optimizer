"""Tests for SqlPriceRepository — mapping, bulk_insert edge cases."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.models.enums import Frequency
from src.domain.models.market_data import PriceBar
from src.infrastructure.persistence.repositories.prices import SqlPriceRepository


def _orm_bar(**overrides):
    defaults = {
        "asset_id": uuid4(),
        "vendor_id": uuid4(),
        "bar_date": date(2025, 1, 2),
        "frequency": "daily",
        "adj_close": 450.0,
        "close": 451.0,
        "volume": 1_000_000,
        "pulled_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _price_bar(**overrides):
    defaults = dict(
        asset_id=uuid4(),
        bar_date=date(2025, 1, 2),
        frequency=Frequency.DAILY,
        adj_close=450.0,
        vendor_id=uuid4(),
    )
    defaults.update(overrides)
    return PriceBar(**defaults)


# --- _to_domain mapping ---

def test_to_domain_maps_frequency_enum():
    assert SqlPriceRepository._to_domain(_orm_bar()).frequency == Frequency.DAILY


def test_to_domain_maps_vendor_id():
    vid = uuid4()
    assert SqlPriceRepository._to_domain(_orm_bar(vendor_id=vid)).vendor_id == vid


def test_to_domain_maps_adj_close():
    assert SqlPriceRepository._to_domain(_orm_bar(adj_close=500.0)).adj_close == 500.0


# --- bulk_insert edge cases ---

async def test_bulk_insert_empty_list_returns_zero():
    repo = SqlPriceRepository(AsyncMock())
    assert await repo.bulk_insert([]) == 0


async def test_bulk_insert_raises_when_vendor_id_is_none():
    repo = SqlPriceRepository(AsyncMock())
    bar = _price_bar(vendor_id=None)
    with pytest.raises(ValueError, match="vendor_id"):
        await repo.bulk_insert([bar])
