"""Tests for src/domain/models/assets.py."""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.assets import Asset, Universe, UniverseAsset
from src.domain.models.enums import AssetClass, Geography, UniverseType


# --- Asset ---

def test_asset_construction():
    a = Asset(
        ticker="SPY",
        name="SPDR S&P 500 ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )
    assert a.ticker == "SPY"


def test_asset_sector_defaults_to_none():
    a = Asset(
        ticker="BND",
        name="Vanguard Total Bond",
        asset_class=AssetClass.FIXED_INCOME,
        sub_class="investment_grade",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )
    assert a.sector is None


def test_asset_sector_set_when_provided():
    a = Asset(
        ticker="XLK",
        name="Technology Select Sector SPDR",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        sector="Information Technology",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )
    assert a.sector == "Information Technology"


def test_asset_id_auto_generated():
    a = Asset(
        ticker="GLD",
        name="SPDR Gold Shares",
        asset_class=AssetClass.COMMODITY,
        sub_class="precious_metals",
        geography=Geography.GLOBAL,
        currency="USD",
        is_etf=True,
    )
    assert a.asset_id is not None


def test_asset_create_factory_sets_ticker():
    a = Asset.create(
        ticker="EEM",
        name="iShares MSCI Emerging Markets",
        asset_class=AssetClass.EQUITY,
        sub_class="em_equity",
        geography=Geography.EMERGING,
        currency="USD",
        is_etf=True,
    )
    assert a.ticker == "EEM"


def test_asset_create_factory_sector_defaults_none():
    a = Asset.create(
        ticker="EEM",
        name="iShares MSCI Emerging Markets",
        asset_class=AssetClass.EQUITY,
        sub_class="em_equity",
        geography=Geography.EMERGING,
        currency="USD",
        is_etf=True,
    )
    assert a.sector is None


def test_asset_is_frozen():
    a = Asset(
        ticker="SPY",
        name="SPDR S&P 500 ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )
    with pytest.raises(ValidationError):
        a.ticker = "QQQ"  # type: ignore[misc]


# --- Universe ---

def test_universe_create_active_type():
    u = Universe.create_active(name="Core ETFs", description="Core portfolio")
    assert u.universe_type == UniverseType.ACTIVE


def test_universe_create_candidate_pool_type():
    u = Universe.create_candidate_pool(name="Screening Pool", description="Candidates")
    assert u.universe_type == UniverseType.CANDIDATE_POOL


def test_universe_construction():
    u = Universe(
        name="My Universe",
        description="Test universe",
        universe_type=UniverseType.ACTIVE,
    )
    assert u.name == "My Universe"


def test_universe_id_auto_generated():
    u = Universe.create_active(name="Test", description="Test")
    assert u.universe_id is not None


# --- UniverseAsset ---

def test_universe_asset_construction():
    ua = UniverseAsset(universe_id=uuid4(), asset_id=uuid4())
    assert ua.is_benchmark is False


def test_universe_asset_is_benchmark_true():
    ua = UniverseAsset(universe_id=uuid4(), asset_id=uuid4(), is_benchmark=True)
    assert ua.is_benchmark is True
