"""Unit tests for SqlTokenRepository.

The SQLAlchemy session is mocked — no database required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.auth.token_repository import ITokenRepository, SqlTokenRepository


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _expires() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _orm_row(**overrides) -> SimpleNamespace:
    defaults = {
        "provider": "schwab",
        "access_token": "acc",
        "refresh_token": "ref",
        "expires_at": _expires(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_session(scalar_result=None) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()  # session.add() is synchronous in SQLAlchemy
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    session.execute.return_value = result_mock
    return session


# --------------------------------------------------------------------------- #
# ITokenRepository protocol satisfaction                                        #
# --------------------------------------------------------------------------- #

def test_sql_token_repository_satisfies_protocol():
    session = _mock_session()
    repo = SqlTokenRepository(session)
    assert isinstance(repo, ITokenRepository)


# --------------------------------------------------------------------------- #
# get_tokens                                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_get_tokens_returns_none_when_no_row():
    repo = SqlTokenRepository(_mock_session(scalar_result=None))
    result = await repo.get_tokens()
    assert result is None


@pytest.mark.asyncio
async def test_get_tokens_returns_dict_when_row_exists():
    row = _orm_row()
    repo = SqlTokenRepository(_mock_session(scalar_result=row))
    result = await repo.get_tokens()
    assert result is not None
    assert result["access_token"] == "acc"
    assert result["refresh_token"] == "ref"
    assert result["expires_at"] == _expires()


# --------------------------------------------------------------------------- #
# save_tokens — insert path                                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_save_tokens_adds_new_row_when_none_exists():
    session = _mock_session(scalar_result=None)
    repo = SqlTokenRepository(session)
    await repo.save_tokens("new-acc", "new-ref", _expires())
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


# --------------------------------------------------------------------------- #
# save_tokens — update path                                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_save_tokens_updates_existing_row():
    row = _orm_row()
    session = _mock_session(scalar_result=row)
    repo = SqlTokenRepository(session)
    new_expires = datetime(2026, 6, 1, tzinfo=timezone.utc)
    await repo.save_tokens("updated-acc", "updated-ref", new_expires)

    assert row.access_token == "updated-acc"
    assert row.refresh_token == "updated-ref"
    assert row.expires_at == new_expires
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


# --------------------------------------------------------------------------- #
# clear_tokens                                                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_clear_tokens_deletes_existing_row():
    row = _orm_row()
    session = _mock_session(scalar_result=row)
    repo = SqlTokenRepository(session)
    await repo.clear_tokens()
    session.delete.assert_awaited_once_with(row)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_tokens_noop_when_no_row():
    session = _mock_session(scalar_result=None)
    repo = SqlTokenRepository(session)
    await repo.clear_tokens()
    session.delete.assert_not_called()
    session.commit.assert_not_awaited()


# --------------------------------------------------------------------------- #
# provider parameter                                                            #
# --------------------------------------------------------------------------- #

def test_default_provider_is_schwab():
    session = _mock_session()
    repo = SqlTokenRepository(session)
    assert repo._provider == "schwab"


def test_custom_provider_is_stored():
    session = _mock_session()
    repo = SqlTokenRepository(session, provider="tdameritrade")
    assert repo._provider == "tdameritrade"
