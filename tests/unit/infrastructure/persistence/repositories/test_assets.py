"""Tests for SqlAssetRepository — mapping and session interaction."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography
from src.infrastructure.persistence.repositories.assets import SqlAssetRepository


def _orm_asset(**overrides):
    defaults = {
        "asset_id": uuid4(),
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF",
        "asset_class": "equity",
        "sub_class": "large_cap_us",
        "sector": None,
        "geography": "us",
        "currency": "USD",
        "is_etf": True,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_session(scalar_result=None):
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=scalar_result)
    )
    return session


def _domain_asset(**overrides):
    defaults = dict(
        ticker="SPY",
        name="SPDR S&P 500 ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )
    defaults.update(overrides)
    return Asset(**defaults)


# --- _to_domain mapping ---

def test_to_domain_maps_ticker():
    assert SqlAssetRepository._to_domain(_orm_asset(ticker="QQQ")).ticker == "QQQ"


def test_to_domain_maps_asset_class_enum():
    assert SqlAssetRepository._to_domain(_orm_asset()).asset_class == AssetClass.EQUITY


def test_to_domain_maps_geography_enum():
    assert SqlAssetRepository._to_domain(_orm_asset()).geography == Geography.US


def test_to_domain_preserves_none_sector():
    assert SqlAssetRepository._to_domain(_orm_asset(sector=None)).sector is None


def test_to_domain_maps_sector_when_set():
    result = SqlAssetRepository._to_domain(_orm_asset(sector="Information Technology"))
    assert result.sector == "Information Technology"


# --- session interaction ---

async def test_get_by_id_returns_none_when_not_found():
    repo = SqlAssetRepository(_mock_session(scalar_result=None))
    assert await repo.get_by_id(uuid4()) is None


async def test_get_by_id_returns_domain_object_when_found():
    orm_row = _orm_asset()
    repo = SqlAssetRepository(_mock_session(scalar_result=orm_row))
    result = await repo.get_by_id(orm_row.asset_id)
    assert result.ticker == orm_row.ticker


async def test_update_raises_when_asset_not_found():
    repo = SqlAssetRepository(_mock_session(scalar_result=None))
    with pytest.raises(ValueError):
        await repo.update(_domain_asset())
