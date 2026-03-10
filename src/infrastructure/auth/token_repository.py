"""Token repository: protocol + SQLAlchemy implementation.

ITokenRepository is the abstraction SchwabOAuthService depends on (DIP).
SqlTokenRepository is the concrete implementation backed by the oauth_tokens table.

Keeping the protocol here (rather than in domain/) is intentional: token
management is an infrastructure concern with no domain meaning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class ITokenRepository(Protocol):
    """Contract for OAuth token storage.  All methods are async."""

    async def save_tokens(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
    ) -> None:
        """Persist (or overwrite) the token set for this provider."""
        ...

    async def get_tokens(self) -> dict | None:
        """Return the stored token dict or None if not connected.

        Keys: access_token, refresh_token, expires_at (datetime, tz-aware).
        """
        ...

    async def clear_tokens(self) -> None:
        """Delete stored tokens (disconnect)."""
        ...


class SqlTokenRepository:
    """Stores one OAuth token set per provider in the oauth_tokens table.

    provider defaults to "schwab" but can be overridden for future vendors,
    making this class reusable without modification (Open/Closed Principle).
    """

    def __init__(self, session: AsyncSession, provider: str = "schwab") -> None:
        self._session = session
        self._provider = provider

    async def save_tokens(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
    ) -> None:
        from src.infrastructure.persistence.models.auth import OAuthToken

        result = await self._session.execute(
            select(OAuthToken).where(OAuthToken.provider == self._provider)
        )
        row = result.scalar_one_or_none()

        if row:
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.expires_at = expires_at
        else:
            self._session.add(
                OAuthToken(
                    provider=self._provider,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )
            )

        await self._session.commit()

    async def get_tokens(self) -> dict | None:
        from src.infrastructure.persistence.models.auth import OAuthToken

        result = await self._session.execute(
            select(OAuthToken).where(OAuthToken.provider == self._provider)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        return {
            "access_token": row.access_token,
            "refresh_token": row.refresh_token,
            "expires_at": row.expires_at,
        }

    async def clear_tokens(self) -> None:
        from src.infrastructure.persistence.models.auth import OAuthToken

        result = await self._session.execute(
            select(OAuthToken).where(OAuthToken.provider == self._provider)
        )
        row = result.scalar_one_or_none()
        if row:
            await self._session.delete(row)
            await self._session.commit()
