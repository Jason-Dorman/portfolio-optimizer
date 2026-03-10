"""Smoke-test for Schwab OAuth flow.

Usage:
    python scripts/test_schwab_auth.py

Requires SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, SCHWAB_CALLBACK_URL in .env.

Walks through the full OAuth flow interactively:
  Step 1 — Prints the authorization URL for you to open in a browser.
  Step 2 — You log in, authorize the app, and Schwab redirects to the callback URL.
           The redirect URL will look like:
               https://127.0.0.1:5000/callback?code=<AUTH_CODE>&state=<STATE>
  Step 3 — Paste the full redirect URL (or just the code= value) here.
  Step 4 — Script exchanges the code for tokens and prints connection status.
  Step 5 — Fetches a live quote for SPY to confirm the access token works.

No database connection required — tokens are held in memory only.
"""

import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from src.config import settings
from src.infrastructure.auth.schwab_oauth import SchwabOAuthService
from src.infrastructure.vendors.schwab import SchwabAdapter


class _InMemoryTokenRepo:
    """Minimal in-memory token store for this smoke test (no DB needed)."""

    def __init__(self) -> None:
        self._tokens: dict | None = None

    async def save_tokens(self, access_token: str, refresh_token: str, expires_at: datetime) -> None:
        self._tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        }

    async def get_tokens(self) -> dict | None:
        return self._tokens

    async def clear_tokens(self) -> None:
        self._tokens = None


def _extract_code(raw: str) -> str:
    """Accept either a full redirect URL or a bare authorization code."""
    raw = raw.strip()
    # Handle URLs pasted without a scheme (e.g. "127.0.0.1:5000/callback?code=...")
    if not raw.startswith("http") and ("callback?" in raw or "code=" in raw):
        raw = "https://" + raw
    if raw.startswith("http"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        if not codes:
            raise ValueError("No 'code' param found in the URL you pasted.")
        return codes[0]
    return raw


async def main() -> None:
    # ------------------------------------------------------------------ #
    # Pre-flight checks                                                    #
    # ------------------------------------------------------------------ #
    missing = [
        k for k in ("schwab_client_id", "schwab_client_secret")
        if not getattr(settings, k)
    ]
    if missing:
        print(f"ERROR: missing in .env: {', '.join(m.upper() for m in missing)}")
        return

    repo = _InMemoryTokenRepo()
    svc = SchwabOAuthService(
        client_id=settings.schwab_client_id,
        client_secret=settings.schwab_client_secret,
        callback_url=settings.schwab_callback_url,
        token_repository=repo,
    )

    # ------------------------------------------------------------------ #
    # Step 1: authorization URL                                            #
    # ------------------------------------------------------------------ #
    state = svc.generate_state()
    url = svc.get_authorization_url(state)

    print("\n=== Step 1: Open this URL in your browser ===")
    print(url)
    print(
        "\nLog in with your Schwab credentials, authorize the app, then copy "
        "the full redirect URL from your browser address bar."
    )
    print(
        f"\nExpected redirect URL format:\n"
        f"  {settings.schwab_callback_url}?code=<AUTH_CODE>&state={state}"
    )

    # ------------------------------------------------------------------ #
    # Step 2: receive the code                                             #
    # ------------------------------------------------------------------ #
    print("\n=== Step 2: Paste the redirect URL (or just the code) ===")
    raw = input(">>> ").strip()
    if not raw:
        print("Nothing entered. Exiting.")
        return

    try:
        code = _extract_code(raw)
    except ValueError as e:
        print(f"ERROR: {e}")
        return

    # ------------------------------------------------------------------ #
    # Step 3: exchange code for tokens                                     #
    # ------------------------------------------------------------------ #
    print("\nExchanging code for tokens ...")
    ok = await svc.handle_callback(code)
    if not ok:
        print("ERROR: token exchange failed. Check the code and try again.")
        return

    status = await svc.get_connection_status()
    print(f"\nConnection status: {status}")
    print("OAuth flow complete.")

    # ------------------------------------------------------------------ #
    # Step 4: live quote to confirm the token works                        #
    # ------------------------------------------------------------------ #
    print("\n=== Step 4: Fetching live quote for SPY ===")
    adapter = SchwabAdapter(oauth_service=svc)
    try:
        quotes = await adapter.get_quotes(["SPY"])
        print(f"SPY last price: ${quotes['SPY']:.2f}")
        print("\nSchwab adapter OK")
    except Exception as e:
        print(f"Quote fetch failed: {e}")
        print("(Token exchange succeeded — the quote error may be a permission or market-hours issue.)")


if __name__ == "__main__":
    asyncio.run(main())
