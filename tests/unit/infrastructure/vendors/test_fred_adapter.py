"""Unit tests for FredAdapter."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.infrastructure.vendors.fred import FredAdapter


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _http_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


def _obs(obs_date: str, value: str) -> dict:
    return {"date": obs_date, "value": value}


# --------------------------------------------------------------------------- #
# fetch_risk_free_series                                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_returns_list_of_date_float_tuples():
    adapter = FredAdapter(api_key="test-key")
    body = {"observations": [_obs("2024-01-02", "5.25")]}

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.fetch_risk_free_series(date(2024, 1, 1), date(2024, 1, 31))

    assert result == [(date(2024, 1, 2), 0.0525)]


@pytest.mark.asyncio
async def test_converts_percent_to_decimal():
    adapter = FredAdapter(api_key="test-key")
    body = {"observations": [_obs("2024-01-02", "4.00")]}

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.fetch_risk_free_series(date(2024, 1, 1), date(2024, 1, 31))

    assert result[0][1] == pytest.approx(0.04)


@pytest.mark.asyncio
async def test_drops_missing_sentinel():
    adapter = FredAdapter(api_key="test-key")
    body = {
        "observations": [
            _obs("2024-01-01", "."),   # FRED missing
            _obs("2024-01-02", "5.0"),
        ]
    }

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.fetch_risk_free_series(date(2024, 1, 1), date(2024, 1, 31))

    assert len(result) == 1
    assert result[0][0] == date(2024, 1, 2)


@pytest.mark.asyncio
async def test_empty_observations():
    adapter = FredAdapter(api_key="test-key")
    body = {"observations": []}

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.fetch_risk_free_series(date(2024, 1, 1), date(2024, 1, 31))

    assert result == []


@pytest.mark.asyncio
async def test_multiple_observations_in_order():
    adapter = FredAdapter(api_key="test-key")
    body = {
        "observations": [
            _obs("2024-01-02", "5.25"),
            _obs("2024-01-03", "5.30"),
        ]
    }

    with patch.object(adapter._client, "get", return_value=_http_response(200, body)):
        result = await adapter.fetch_risk_free_series(date(2024, 1, 1), date(2024, 1, 31))

    assert result[0] == (date(2024, 1, 2), pytest.approx(0.0525))
    assert result[1] == (date(2024, 1, 3), pytest.approx(0.053))
