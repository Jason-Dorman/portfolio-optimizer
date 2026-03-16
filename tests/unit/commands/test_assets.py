"""Unit tests for src/commands/assets.py."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.commands.assets import CreateAssetCommand, CreateAssetHandler
from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography


def _make_asset(**overrides) -> Asset:
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


def _make_command(**overrides) -> CreateAssetCommand:
    defaults = dict(
        ticker="spy",
        name="SPDR S&P 500 ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="usd",
        is_etf=True,
    )
    defaults.update(overrides)
    return CreateAssetCommand(**defaults)


def _make_repo(existing=None, created=None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_ticker.return_value = existing
    if created is not None:
        repo.create.return_value = created
    else:
        repo.create.side_effect = lambda asset: asset
    return repo


# ── Command validation ──────────────────────────────────────────────────────


def test_command_ticker_stored_as_provided():
    cmd = _make_command(ticker="qqq")
    assert cmd.ticker == "qqq"  # handler normalises, not the command


def test_command_requires_ticker():
    with pytest.raises(ValidationError):
        CreateAssetCommand(
            name="x",
            asset_class=AssetClass.EQUITY,
            sub_class="x",
            geography=Geography.US,
            currency="USD",
            is_etf=True,
        )  # type: ignore[call-arg]


def test_command_sector_defaults_none():
    assert _make_command().sector is None


# ── CreateAssetHandler ──────────────────────────────────────────────────────


async def test_handle_normalises_ticker_to_uppercase():
    repo = _make_repo()
    handler = CreateAssetHandler(asset_repo=repo)
    await handler.handle(_make_command(ticker="spy"))
    repo.get_by_ticker.assert_awaited_once_with("SPY")


async def test_handle_normalises_currency_to_uppercase():
    repo = _make_repo()
    created_assets = []
    repo.create.side_effect = lambda a: (created_assets.append(a), a)[1]
    handler = CreateAssetHandler(asset_repo=repo)
    await handler.handle(_make_command(currency="usd"))
    assert created_assets[0].currency == "USD"


async def test_handle_returns_created_asset():
    expected = _make_asset()
    repo = _make_repo(created=expected)
    result = await CreateAssetHandler(asset_repo=repo).handle(_make_command())
    assert result is expected


async def test_handle_raises_409_when_ticker_exists():
    repo = _make_repo(existing=_make_asset())
    with pytest.raises(HTTPException) as exc_info:
        await CreateAssetHandler(asset_repo=repo).handle(_make_command())
    assert exc_info.value.status_code == 409


async def test_handle_409_message_contains_ticker():
    repo = _make_repo(existing=_make_asset())
    with pytest.raises(HTTPException) as exc_info:
        await CreateAssetHandler(asset_repo=repo).handle(_make_command(ticker="SPY"))
    assert "SPY" in exc_info.value.detail


async def test_handle_calls_create_when_no_existing_asset():
    repo = _make_repo()
    await CreateAssetHandler(asset_repo=repo).handle(_make_command())
    repo.create.assert_awaited_once()


async def test_handle_sets_sector_on_created_asset():
    repo = _make_repo()
    created_assets = []
    repo.create.side_effect = lambda a: (created_assets.append(a), a)[1]
    handler = CreateAssetHandler(asset_repo=repo)
    await handler.handle(_make_command(sector="Technology"))
    assert created_assets[0].sector == "Technology"
