"""Unit tests for SchwabAdapter.

All HTTP calls and OAuth interactions are mocked — no network required.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.domain.models.enums import Frequency
from src.infrastructure.vendors.exceptions import AuthenticationRequired, RateLimitError
from src.infrastructure.vendors.schwab import SchwabAdapter, _to_epoch_ms


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _mock_oauth(token: str | None = "valid-token") -> AsyncMock:
    oauth = AsyncMock()
    oauth.get_valid_access_token.return_value = token
    oauth.refresh_access_token.return_value = True
    return oauth


def _http_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "", request=MagicMock(), response=resp
        )
    return resp


def _candle(epoch_ms: int = 1_700_000_000_000) -> dict:
    return {
        "datetime": epoch_ms,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 1_000_000,
    }


# --------------------------------------------------------------------------- #
# _to_epoch_ms                                                                  #
# --------------------------------------------------------------------------- #

def test_to_epoch_ms_returns_int():
    result = _to_epoch_ms(date(2024, 1, 1))
    assert isinstance(result, int)


def test_to_epoch_ms_midnight_utc():
    # 2024-01-01 UTC midnight = 1704067200 seconds
    assert _to_epoch_ms(date(2024, 1, 1)) == 1_704_067_200_000


# --------------------------------------------------------------------------- #
# fetch_price_history                                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_fetch_price_history_returns_vendor_price_bars():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    candle = _candle(1_700_000_000_000)

    with patch.object(adapter._client, "get", return_value=_http_response(
        200, {"candles": [candle]}
    )):
        bars = await adapter.fetch_price_history(
            "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
        )

    assert len(bars) == 1
    bar = bars[0]
    assert bar.ticker == "SPY"
    assert bar.frequency == Frequency.DAILY
    assert bar.close == 103.0
    assert bar.volume == 1_000_000


@pytest.mark.asyncio
async def test_fetch_price_history_maps_epoch_ms_to_date():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    # epoch_ms → 2023-11-14 22:13:20 UTC → date 2023-11-14
    candle = _candle(1_700_000_000_000)

    with patch.object(adapter._client, "get", return_value=_http_response(
        200, {"candles": [candle]}
    )):
        bars = await adapter.fetch_price_history(
            "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
        )

    assert bars[0].bar_date == datetime.fromtimestamp(
        1_700_000_000_000 / 1000, tz=timezone.utc
    ).date()


@pytest.mark.asyncio
async def test_fetch_price_history_empty_candles():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)

    with patch.object(adapter._client, "get", return_value=_http_response(
        200, {"candles": []}
    )):
        bars = await adapter.fetch_price_history(
            "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
        )

    assert bars == []


@pytest.mark.asyncio
async def test_fetch_price_history_raises_auth_required_when_no_token():
    oauth = _mock_oauth(token=None)
    adapter = SchwabAdapter(oauth)

    with pytest.raises(AuthenticationRequired):
        await adapter.fetch_price_history(
            "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
        )


@pytest.mark.asyncio
async def test_fetch_price_history_retries_on_401_and_succeeds():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    candle = _candle()
    first = _http_response(401, {})
    second = _http_response(200, {"candles": [candle]})

    responses = iter([first, second])
    with patch.object(adapter._client, "get", side_effect=lambda *a, **kw: next(responses)):
        bars = await adapter.fetch_price_history(
            "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
        )

    assert len(bars) == 1


@pytest.mark.asyncio
async def test_fetch_price_history_raises_auth_required_when_refresh_fails_after_401():
    oauth = _mock_oauth()
    oauth.refresh_access_token.return_value = False
    adapter = SchwabAdapter(oauth)
    first = _http_response(401, {})

    with patch.object(adapter._client, "get", return_value=first):
        with pytest.raises(AuthenticationRequired):
            await adapter.fetch_price_history(
                "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
            )


@pytest.mark.asyncio
async def test_fetch_price_history_raises_rate_limit_on_429():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)

    with patch.object(adapter._client, "get", return_value=_http_response(429, {})):
        with pytest.raises(RateLimitError):
            await adapter.fetch_price_history(
                "SPY", date(2023, 1, 1), date(2023, 12, 31), Frequency.DAILY
            )


# --------------------------------------------------------------------------- #
# get_quotes                                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_quotes_returns_last_price():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    body = {"SPY": {"quote": {"lastPrice": 450.12}}}

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.get_quotes(["SPY"])

    assert result == {"SPY": 450.12}


@pytest.mark.asyncio
async def test_get_quotes_multiple_tickers():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    body = {
        "SPY": {"quote": {"lastPrice": 450.0}},
        "AGG": {"quote": {"lastPrice": 95.5}},
    }

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.get_quotes(["SPY", "AGG"])

    assert result["SPY"] == 450.0
    assert result["AGG"] == 95.5


# --------------------------------------------------------------------------- #
# search_instruments                                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_search_instruments_maps_fields():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)
    body = {
        "instruments": [
            {
                "symbol": "SPY",
                "description": "SPDR S&P 500 ETF",
                "exchange": "NYSE",
                "assetType": "ETF",
            }
        ]
    }

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        results = await adapter.search_instruments("SPY")

    assert len(results) == 1
    assert results[0] == {
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF",
        "exchange": "NYSE",
        "asset_type": "ETF",
    }


@pytest.mark.asyncio
async def test_search_instruments_empty_result():
    oauth = _mock_oauth()
    adapter = SchwabAdapter(oauth)

    with patch.object(adapter._client, "get", return_value=_http_response(
        200, {"instruments": []}
    )):
        results = await adapter.search_instruments("ZZZZZ")

    assert results == []
