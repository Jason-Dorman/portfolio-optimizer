"""Unit tests for SchwabOAuthService.

Token storage is mocked via AsyncMock implementations of ITokenRepository.
No network or database required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.infrastructure.auth.schwab_oauth import SchwabOAuthService


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _make_svc(tokens: dict | None = None) -> tuple[SchwabOAuthService, AsyncMock]:
    """Return (service, mock_token_repo)."""
    repo = AsyncMock()
    repo.get_tokens.return_value = tokens
    svc = SchwabOAuthService(
        client_id="client-id",
        client_secret="client-secret",
        callback_url="https://127.0.0.1:5000/callback",
        token_repository=repo,
    )
    return svc, repo


def _future_tokens(seconds_until_expiry: int = 1800) -> dict:
    return {
        "access_token": "acc",
        "refresh_token": "ref",
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=seconds_until_expiry),
    }


def _expired_tokens(seconds_ago: int = 120) -> dict:
    return {
        "access_token": "old-acc",
        "refresh_token": "ref",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    }


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


# --------------------------------------------------------------------------- #
# generate_state                                                                #
# --------------------------------------------------------------------------- #

def test_generate_state_returns_string():
    svc, _ = _make_svc()
    assert isinstance(svc.generate_state(), str)


def test_generate_state_is_unique():
    svc, _ = _make_svc()
    assert svc.generate_state() != svc.generate_state()


# --------------------------------------------------------------------------- #
# get_authorization_url                                                         #
# --------------------------------------------------------------------------- #

def test_authorization_url_contains_client_id():
    svc, _ = _make_svc()
    url = svc.get_authorization_url("state123")
    assert "client_id=client-id" in url


def test_authorization_url_contains_response_type_code():
    svc, _ = _make_svc()
    url = svc.get_authorization_url("state123")
    assert "response_type=code" in url


def test_authorization_url_contains_state():
    svc, _ = _make_svc()
    url = svc.get_authorization_url("mystate")
    assert "state=mystate" in url


def test_authorization_url_contains_redirect_uri():
    svc, _ = _make_svc()
    url = svc.get_authorization_url("state123")
    assert "redirect_uri=" in url


# --------------------------------------------------------------------------- #
# handle_callback                                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_handle_callback_returns_true_on_success():
    svc, repo = _make_svc()
    token_response = {
        "access_token": "acc",
        "refresh_token": "ref",
        "expires_in": 1800,
    }
    with patch.object(svc._client, "post", return_value=_http_response(200, token_response)):
        result = await svc.handle_callback("auth-code")

    assert result is True


@pytest.mark.asyncio
async def test_handle_callback_saves_tokens():
    svc, repo = _make_svc()
    token_response = {"access_token": "acc", "refresh_token": "ref", "expires_in": 1800}

    with patch.object(svc._client, "post", return_value=_http_response(200, token_response)):
        await svc.handle_callback("auth-code")

    repo.save_tokens.assert_awaited_once()
    call_kwargs = repo.save_tokens.await_args.kwargs
    assert call_kwargs["access_token"] == "acc"
    assert call_kwargs["refresh_token"] == "ref"


@pytest.mark.asyncio
async def test_handle_callback_returns_false_on_http_error():
    svc, _ = _make_svc()
    with patch.object(svc._client, "post", return_value=_http_response(400, {})):
        result = await svc.handle_callback("bad-code")

    assert result is False


# --------------------------------------------------------------------------- #
# refresh_access_token                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_refresh_returns_false_when_no_tokens():
    svc, _ = _make_svc(tokens=None)
    result = await svc.refresh_access_token()
    assert result is False


@pytest.mark.asyncio
async def test_refresh_returns_true_on_success():
    svc, repo = _make_svc(tokens=_expired_tokens())
    token_response = {"access_token": "new-acc", "refresh_token": "new-ref", "expires_in": 1800}

    with patch.object(svc._client, "post", return_value=_http_response(200, token_response)):
        result = await svc.refresh_access_token()

    assert result is True


@pytest.mark.asyncio
async def test_refresh_uses_fallback_refresh_token_when_omitted():
    """If Schwab omits refresh_token in the refresh response, keep the old one."""
    svc, repo = _make_svc(tokens=_expired_tokens())
    token_response = {"access_token": "new-acc", "expires_in": 1800}  # no refresh_token

    with patch.object(svc._client, "post", return_value=_http_response(200, token_response)):
        await svc.refresh_access_token()

    call_kwargs = repo.save_tokens.await_args.kwargs
    assert call_kwargs["refresh_token"] == "ref"  # from _expired_tokens()


@pytest.mark.asyncio
async def test_refresh_returns_false_on_http_error():
    svc, _ = _make_svc(tokens=_expired_tokens())
    with patch.object(svc._client, "post", return_value=_http_response(401, {})):
        result = await svc.refresh_access_token()

    assert result is False


# --------------------------------------------------------------------------- #
# get_valid_access_token                                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_valid_token_returns_none_when_no_tokens():
    svc, _ = _make_svc(tokens=None)
    result = await svc.get_valid_access_token()
    assert result is None


@pytest.mark.asyncio
async def test_get_valid_token_returns_token_when_not_expired():
    svc, _ = _make_svc(tokens=_future_tokens(1800))
    result = await svc.get_valid_access_token()
    assert result == "acc"


@pytest.mark.asyncio
async def test_get_valid_token_refreshes_when_near_expiry():
    expired = _expired_tokens(120)
    refreshed = {**expired, "access_token": "fresh-acc",
                 "expires_at": datetime.now(timezone.utc) + timedelta(seconds=1800)}

    svc, repo = _make_svc(tokens=expired)
    # get_tokens is called 3 times: (1) initial check, (2) inside refresh, (3) final read
    repo.get_tokens.side_effect = [expired, refreshed, refreshed]
    token_response = {"access_token": "fresh-acc", "refresh_token": "ref", "expires_in": 1800}

    with patch.object(svc._client, "post", return_value=_http_response(200, token_response)):
        result = await svc.get_valid_access_token()

    assert result == "fresh-acc"


@pytest.mark.asyncio
async def test_get_valid_token_returns_none_when_refresh_fails():
    svc, _ = _make_svc(tokens=_expired_tokens(120))
    with patch.object(svc._client, "post", return_value=_http_response(401, {})):
        result = await svc.get_valid_access_token()

    assert result is None


# --------------------------------------------------------------------------- #
# get_connection_status                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_status_not_connected_when_no_tokens():
    svc, _ = _make_svc(tokens=None)
    status = await svc.get_connection_status()
    assert status["connected"] is False
    assert status["needs_reauth"] is False


@pytest.mark.asyncio
async def test_status_connected_with_fresh_tokens():
    svc, _ = _make_svc(tokens=_future_tokens(1800))
    status = await svc.get_connection_status()
    assert status["connected"] is True
    assert status["needs_reauth"] is False


@pytest.mark.asyncio
async def test_status_needs_reauth_after_seven_days():
    old_expires = datetime.now(timezone.utc) - timedelta(days=8)
    tokens = {"access_token": "acc", "refresh_token": "ref", "expires_at": old_expires}
    svc, _ = _make_svc(tokens=tokens)
    status = await svc.get_connection_status()
    assert status["needs_reauth"] is True


# --------------------------------------------------------------------------- #
# disconnect                                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_disconnect_calls_clear_tokens():
    svc, repo = _make_svc()
    await svc.disconnect()
    repo.clear_tokens.assert_awaited_once()
