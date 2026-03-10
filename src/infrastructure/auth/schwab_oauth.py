"""Schwab OAuth 2.0 authorization-code flow service.

Responsibilities:
  - Build the authorization URL the user visits to connect their account
  - Exchange the callback code for access + refresh tokens
  - Auto-refresh the access token before it expires
  - Report connection status
  - Disconnect (clear stored tokens)

Token persistence is delegated to ITokenRepository (Dependency Inversion).
This service never touches the database directly.
"""

from __future__ import annotations

import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from src.infrastructure.auth.token_repository import ITokenRepository

logger = logging.getLogger(__name__)

# Schwab access tokens expire in 30 minutes; refresh 60 s before expiry.
_REFRESH_BUFFER_SECONDS = 60
# Refresh tokens expire after 7 days of inactivity.
_REFRESH_TOKEN_TTL_DAYS = 7


class SchwabOAuthService:
    """Manages the Schwab OAuth 2.0 authorization-code flow.

    Typical usage:
        1. state = svc.generate_state()          # store in session
        2. url   = svc.get_authorization_url(state)
        3. redirect user → user authorises → Schwab calls back
        4. await svc.handle_callback(code)
        5. token = await svc.get_valid_access_token()
    """

    _AUTH_BASE = "https://api.schwabapi.com/v1/oauth"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        callback_url: str,
        token_repository: ITokenRepository,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._callback_url = callback_url
        self._tokens = token_repository
        self._client = httpx.AsyncClient()

    # ------------------------------------------------------------------ #
    # Authorization URL                                                    #
    # ------------------------------------------------------------------ #

    def generate_state(self) -> str:
        """Return a cryptographically random CSRF state token."""
        return secrets.token_urlsafe(32)

    def get_authorization_url(self, state: str) -> str:
        """Build the Schwab authorization URL the user must visit."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._callback_url,
            "response_type": "code",
            "state": state,
        }
        return f"{self._AUTH_BASE}/authorize?{urlencode(params)}"

    # ------------------------------------------------------------------ #
    # OAuth flow                                                           #
    # ------------------------------------------------------------------ #

    async def handle_callback(self, code: str) -> bool:
        """Exchange the authorization code for tokens.

        Returns True on success, False if the exchange fails (logs the error).
        """
        try:
            response = await self._client.post(
                f"{self._AUTH_BASE}/token",
                headers=self._basic_auth_headers(),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._callback_url,
                },
            )
            response.raise_for_status()
            await self._persist_token_response(response.json())
            return True
        except Exception:
            logger.exception("Schwab OAuth callback failed")
            return False

    async def refresh_access_token(self) -> bool:
        """Refresh the access token using the stored refresh token.

        Returns True on success, False if re-authentication is required.
        """
        tokens = await self._tokens.get_tokens()
        if not tokens or not tokens.get("refresh_token"):
            return False

        try:
            response = await self._client.post(
                f"{self._AUTH_BASE}/token",
                headers=self._basic_auth_headers(),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                },
            )
            response.raise_for_status()
            # Schwab may or may not issue a new refresh token; keep the old one
            # if the response omits it.
            await self._persist_token_response(
                response.json(), fallback_refresh=tokens["refresh_token"]
            )
            return True
        except Exception:
            logger.exception("Schwab token refresh failed")
            return False

    async def get_valid_access_token(self) -> str | None:
        """Return a valid access token, refreshing proactively if near expiry.

        Returns None when no tokens are stored or refresh fails (caller should
        surface an AuthenticationRequired error to the user).
        """
        tokens = await self._tokens.get_tokens()
        if not tokens:
            return None

        expires_at = tokens.get("expires_at")
        if expires_at and self._is_near_expiry(expires_at):
            if not await self.refresh_access_token():
                return None
            tokens = await self._tokens.get_tokens()

        return tokens.get("access_token") if tokens else None

    # ------------------------------------------------------------------ #
    # Status / lifecycle                                                   #
    # ------------------------------------------------------------------ #

    async def get_connection_status(self) -> dict:
        """Return connection state for display in the Settings UI."""
        tokens = await self._tokens.get_tokens()
        if not tokens:
            return {"connected": False, "needs_reauth": False, "expires_at": None}

        expires_at = tokens.get("expires_at")
        now = datetime.now(timezone.utc)
        # Heuristic: if the access token expired more than 7 days ago the
        # refresh token has also likely expired (Schwab: 7-day rolling TTL).
        needs_reauth = bool(
            expires_at and now > expires_at + timedelta(days=_REFRESH_TOKEN_TTL_DAYS)
        )
        return {
            "connected": True,
            "needs_reauth": needs_reauth,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

    async def disconnect(self) -> None:
        """Clear stored tokens, disconnecting the Schwab integration."""
        await self._tokens.clear_tokens()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _basic_auth_headers(self) -> dict[str, str]:
        creds = f"{self._client_id}:{self._client_secret}"
        encoded = base64.b64encode(creds.encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _is_near_expiry(self, expires_at: datetime) -> bool:
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            # Treat naive datetimes as UTC (legacy rows stored before tz migration)
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return now >= expires_at - timedelta(seconds=_REFRESH_BUFFER_SECONDS)

    async def _persist_token_response(
        self,
        data: dict,
        fallback_refresh: str | None = None,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        await self._tokens.save_tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or fallback_refresh or "",
            expires_at=expires_at,
        )
