"""Unit tests for src/commands/holdings.py."""

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.commands.holdings import (
    CreateHoldingsSnapshotCommand,
    CreateHoldingsSnapshotHandler,
    HoldingsPositionInput,
)
from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography
from src.domain.models.holdings import HoldingsSnapshot


def _make_asset(ticker: str = "SPY") -> Asset:
    return Asset(
        ticker=ticker,
        name="Test ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )


def _make_snapshot() -> HoldingsSnapshot:
    aid = uuid4()
    sid = uuid4()
    from src.domain.models.holdings import HoldingsPosition
    return HoldingsSnapshot(
        snapshot_id=sid,
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPosition(snapshot_id=sid, asset_id=aid, weight=1.0)],
    )


def _make_repos(asset: Asset | None = None, snapshot: HoldingsSnapshot | None = None):
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = asset or _make_asset()
    holdings_repo = AsyncMock()
    holdings_repo.create.return_value = snapshot or _make_snapshot()
    return holdings_repo, asset_repo


# ── HoldingsPositionInput validator ────────────────────────────────────────


def test_position_both_weight_and_market_value_raises():
    with pytest.raises(ValidationError):
        HoldingsPositionInput(ticker="SPY", weight=0.5, market_value=1000.0)


def test_position_neither_weight_nor_market_value_raises():
    with pytest.raises(ValidationError):
        HoldingsPositionInput(ticker="SPY")


def test_position_weight_only_valid():
    pos = HoldingsPositionInput(ticker="SPY", weight=0.5)
    assert pos.weight == 0.5
    assert pos.market_value is None


def test_position_market_value_only_valid():
    pos = HoldingsPositionInput(ticker="SPY", market_value=5000.0)
    assert pos.market_value == 5000.0
    assert pos.weight is None


def test_position_weight_zero_valid():
    pos = HoldingsPositionInput(ticker="SPY", weight=0.0)
    assert pos.weight == 0.0


def test_position_market_value_must_be_positive():
    with pytest.raises(ValidationError):
        HoldingsPositionInput(ticker="SPY", market_value=0.0)


# ── CreateHoldingsSnapshotCommand ──────────────────────────────────────────


def test_command_requires_at_least_one_position():
    with pytest.raises(ValidationError):
        CreateHoldingsSnapshotCommand(
            label="x", snapshot_date=date(2024, 1, 1), positions=[]
        )


# ── CreateHoldingsSnapshotHandler — ticker resolution ──────────────────────


async def test_handle_raises_404_when_ticker_not_found():
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = None
    holdings_repo = AsyncMock()
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPositionInput(ticker="MISSING", weight=1.0)],
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 404


async def test_handle_404_lists_missing_tickers():
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = None
    holdings_repo = AsyncMock()
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPositionInput(ticker="ZZZ", weight=1.0)],
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert "ZZZ" in exc_info.value.detail


async def test_handle_ticker_lookup_is_case_insensitive():
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = _make_asset("SPY")
    holdings_repo = AsyncMock()
    holdings_repo.create.return_value = _make_snapshot()
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPositionInput(ticker="spy", weight=1.0)],
    )
    await handler.handle(cmd)
    asset_repo.get_by_ticker.assert_awaited_once_with("SPY")


# ── CreateHoldingsSnapshotHandler — weight path ─────────────────────────────


async def test_handle_weight_path_creates_snapshot():
    holdings_repo, asset_repo = _make_repos()
    expected = _make_snapshot()
    holdings_repo.create.return_value = expected
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPositionInput(ticker="SPY", weight=1.0)],
    )
    result = await handler.handle(cmd)
    assert result is expected
    holdings_repo.create.assert_awaited_once()


# ── CreateHoldingsSnapshotHandler — market value path ──────────────────────


async def test_handle_market_value_path_calls_from_market_values(monkeypatch):
    holdings_repo, asset_repo = _make_repos()
    expected = _make_snapshot()
    holdings_repo.create.return_value = expected
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="MV Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPositionInput(ticker="SPY", market_value=10000.0)],
    )
    result = await handler.handle(cmd)
    assert result is expected
    holdings_repo.create.assert_awaited_once()


async def test_handle_deduplicates_ticker_lookups():
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = _make_asset("SPY")
    holdings_repo = AsyncMock()
    holdings_repo.create.return_value = _make_snapshot()
    handler = CreateHoldingsSnapshotHandler(
        holdings_repo=holdings_repo, asset_repo=asset_repo
    )
    cmd = CreateHoldingsSnapshotCommand(
        label="Dup",
        snapshot_date=date(2024, 1, 1),
        positions=[
            HoldingsPositionInput(ticker="SPY", weight=0.6),
            HoldingsPositionInput(ticker="spy", weight=0.4),
        ],
    )
    await handler.handle(cmd)
    # Deduplication: SPY only looked up once
    assert asset_repo.get_by_ticker.await_count == 1
