"""Unit tests for src/commands/ingest.py."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.commands.ingest import (
    IngestPricesCommand,
    IngestPricesHandler,
    IngestRiskFreeCommand,
    IngestRiskFreeHandler,
)
from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Frequency, Geography


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


def _vendor_bar(ticker: str = "SPY"):
    from src.infrastructure.vendors.schemas import VendorPriceBar
    return VendorPriceBar(
        ticker=ticker,
        bar_date=date(2024, 1, 2),
        frequency=Frequency.DAILY,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000_000,
        pulled_at=datetime.now(timezone.utc),
    )


def _make_prices_handler(
    asset=None,
    vendor_bars=None,
    vendor_id=None,
    bars_inserted=5,
):
    vendor_adapter = AsyncMock()
    vendor_adapter.fetch_price_history.return_value = (
        [_vendor_bar()] if vendor_bars is None else vendor_bars
    )
    vendor_repo = AsyncMock()
    vendor_repo.get_or_create.return_value = vendor_id or uuid4()
    asset_repo = AsyncMock()
    asset_repo.get_by_ticker.return_value = asset if asset is not None else _make_asset()
    price_repo = AsyncMock()
    price_repo.bulk_insert.return_value = bars_inserted
    return IngestPricesHandler(
        vendor_adapter=vendor_adapter,
        vendor_repo=vendor_repo,
        asset_repo=asset_repo,
        price_repo=price_repo,
    )


def _prices_cmd(**overrides):
    defaults = dict(
        tickers=["SPY"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        frequency=Frequency.DAILY,
    )
    defaults.update(overrides)
    return IngestPricesCommand(**defaults)


# ── IngestPricesHandler ─────────────────────────────────────────────────────


async def test_prices_happy_path_returns_bars_inserted():
    handler = _make_prices_handler(bars_inserted=10)
    result = await handler.handle(_prices_cmd())
    assert result.bars_inserted == 10


async def test_prices_happy_path_no_errors():
    handler = _make_prices_handler()
    result = await handler.handle(_prices_cmd())
    assert result.errors == []


async def test_prices_items_requested_matches_command():
    handler = _make_prices_handler()
    result = await handler.handle(_prices_cmd(tickers=["SPY", "QQQ"]))
    assert result.items_requested == 2


async def test_prices_asset_not_found_adds_error_not_raises():
    handler = _make_prices_handler(asset=None)
    handler._asset_repo.get_by_ticker.return_value = None
    result = await handler.handle(_prices_cmd(tickers=["MISSING"]))
    assert len(result.errors) == 1
    assert "MISSING" in result.errors[0]


async def test_prices_asset_not_found_bars_inserted_zero():
    handler = _make_prices_handler(asset=None)
    handler._asset_repo.get_by_ticker.return_value = None
    result = await handler.handle(_prices_cmd(tickers=["MISSING"]))
    assert result.bars_inserted == 0


async def test_prices_vendor_returns_no_bars_adds_error():
    handler = _make_prices_handler(vendor_bars=[])
    result = await handler.handle(_prices_cmd())
    assert len(result.errors) == 1
    assert result.bars_inserted == 0


async def test_prices_calls_get_or_create_vendor():
    handler = _make_prices_handler()
    await handler.handle(_prices_cmd(vendor_name="schwab"))
    handler._vendor_repo.get_or_create.assert_awaited_once_with("schwab")


async def test_prices_ticker_normalised_to_uppercase():
    handler = _make_prices_handler()
    await handler.handle(_prices_cmd(tickers=["spy"]))
    handler._asset_repo.get_by_ticker.assert_awaited_with("SPY")


async def test_prices_partial_success_accumulates_errors_and_bars():
    """One ticker fails (no asset), one succeeds with 3 bars."""
    spy = _make_asset("SPY")
    call_count = 0

    async def get_by_ticker(ticker):
        nonlocal call_count
        call_count += 1
        return spy if ticker == "SPY" else None

    handler = _make_prices_handler(bars_inserted=3)
    handler._asset_repo.get_by_ticker.side_effect = get_by_ticker
    result = await handler.handle(_prices_cmd(tickers=["SPY", "MISSING"]))
    assert result.bars_inserted == 3
    assert len(result.errors) == 1


async def test_prices_vendor_name_in_result():
    handler = _make_prices_handler()
    result = await handler.handle(_prices_cmd(vendor_name="schwab"))
    assert result.vendor_name == "schwab"


# ── IngestRiskFreeHandler ───────────────────────────────────────────────────


def _make_rf_handler(observations=None, upserted=5):
    fred_adapter = AsyncMock()
    fred_adapter.fetch_risk_free_series.return_value = (
        [(date(2024, 1, i + 1), 0.05) for i in range(5)]
        if observations is None
        else observations
    )
    risk_free_repo = AsyncMock()
    risk_free_repo.bulk_upsert.return_value = upserted
    return IngestRiskFreeHandler(fred_adapter=fred_adapter, risk_free_repo=risk_free_repo)


def _rf_cmd(**overrides):
    defaults = dict(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        series_code="DTB3",
    )
    defaults.update(overrides)
    return IngestRiskFreeCommand(**defaults)


async def test_rf_raises_400_when_start_after_end():
    handler = _make_rf_handler()
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_rf_cmd(start_date=date(2024, 2, 1), end_date=date(2024, 1, 1)))
    assert exc_info.value.status_code == 400


async def test_rf_happy_path_bars_inserted():
    handler = _make_rf_handler(upserted=10)
    result = await handler.handle(_rf_cmd())
    assert result.bars_inserted == 10


async def test_rf_vendor_name_includes_series_code():
    handler = _make_rf_handler()
    result = await handler.handle(_rf_cmd(series_code="DTB3"))
    assert "DTB3" in result.vendor_name


async def test_rf_calls_bulk_upsert_with_fred_source():
    handler = _make_rf_handler()
    await handler.handle(_rf_cmd(series_code="DTB3"))
    handler._risk_free_repo.bulk_upsert.assert_awaited_once()
    call_kwargs = handler._risk_free_repo.bulk_upsert.call_args
    assert call_kwargs.kwargs["source"] == "FRED" or call_kwargs.args[0] == "FRED"


async def test_rf_no_errors_in_result():
    handler = _make_rf_handler()
    result = await handler.handle(_rf_cmd())
    assert result.errors == []


async def test_rf_calls_fetch_with_correct_dates():
    handler = _make_rf_handler()
    start = date(2024, 1, 1)
    end = date(2024, 3, 31)
    await handler.handle(_rf_cmd(start_date=start, end_date=end, series_code="DTB3"))
    handler._fred.fetch_risk_free_series.assert_awaited_once_with(
        start_date=start, end_date=end, series_code="DTB3"
    )
