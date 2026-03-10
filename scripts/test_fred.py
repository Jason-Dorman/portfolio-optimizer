"""Smoke-test for FredAdapter.

Usage:
    python scripts/test_fred.py

Requires FRED_API_KEY in .env.
Fetches the last 30 days of DTB3 (3-month T-bill) and prints the result.
No database connection required.
"""

import asyncio
from datetime import date, timedelta

from src.config import settings
from src.infrastructure.vendors.fred import FredAdapter


async def main() -> None:
    if not settings.fred_api_key:
        print("ERROR: FRED_API_KEY not set in .env")
        return

    adapter = FredAdapter(api_key=settings.fred_api_key)

    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    print(f"Fetching DTB3 from {start_date} to {end_date} ...")
    results = await adapter.fetch_risk_free_series(start_date, end_date)

    if not results:
        print("No observations returned (market may have been closed, try a wider range).")
        return

    print(f"\n{'Date':<15} {'Rate (decimal)':<18} {'Rate (annualised %)'}")
    print("-" * 50)
    for obs_date, rate in results:
        print(f"{str(obs_date):<15} {rate:<18.6f} {rate * 100:.4f}%")

    print(f"\nTotal observations: {len(results)}")
    print(f"Latest rate: {results[-1][1] * 100:.4f}% annualised")
    print("\nFRED adapter OK")


if __name__ == "__main__":
    asyncio.run(main())
