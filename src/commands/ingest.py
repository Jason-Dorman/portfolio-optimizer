"""Ingest commands: prices from a market-data vendor and risk-free rates from FRED."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from src.domain.models.enums import Frequency
from src.domain.models.market_data import PriceBar
from src.domain.repositories.assets import AssetRepository
from src.domain.repositories.prices import PriceRepository
from src.domain.repositories.risk_free import RiskFreeRepository
from src.domain.repositories.vendors import DataVendorRepository
from src.infrastructure.vendors.base import VendorAdapter
from src.infrastructure.vendors.fred import FredAdapter


# ─────────────────────────────────────────────────────────────────────────── #
# Shared response type                                                          #
# ─────────────────────────────────────────────────────────────────────────── #


class IngestResult(BaseModel):
    """Summary of a price or risk-free ingest operation.

    items_requested is the number of tickers (price ingest) or series codes
    (risk-free ingest) that were requested from the vendor.
    """

    vendor_name: str
    items_requested: int
    bars_inserted: int
    errors: list[str]


# ─────────────────────────────────────────────────────────────────────────── #
# Price ingest                                                                  #
# ─────────────────────────────────────────────────────────────────────────── #


class IngestPricesCommand(BaseModel):
    """Fetch and store OHLCV price bars for one or more tickers.

    vendor_name is used to look up (or auto-create) the data_vendors record.
    All tickers must already exist in the assets table.
    """

    tickers: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    frequency: Frequency
    vendor_name: str = "schwab"


class IngestPricesHandler:
    """Fetch price history from a vendor adapter and bulk-upsert into price_bars.

    Per-ticker errors are collected and returned in IngestResult.errors rather
    than aborting the entire batch — partial success is valid.
    """

    def __init__(
        self,
        vendor_adapter: VendorAdapter,
        vendor_repo: DataVendorRepository,
        asset_repo: AssetRepository,
        price_repo: PriceRepository,
    ) -> None:
        self._vendor = vendor_adapter
        self._vendor_repo = vendor_repo
        self._asset_repo = asset_repo
        self._price_repo = price_repo

    async def handle(self, command: IngestPricesCommand) -> IngestResult:
        vendor_id = await self._vendor_repo.get_or_create(command.vendor_name)
        errors: list[str] = []
        total_inserted = 0

        for ticker in command.tickers:
            ticker_upper = ticker.upper()
            try:
                asset = await self._asset_repo.get_by_ticker(ticker_upper)
                if asset is None:
                    errors.append(
                        f"{ticker_upper}: asset not found — "
                        "create it first via POST /commands/assets"
                    )
                    continue

                vendor_bars = await self._vendor.fetch_price_history(
                    ticker_upper,
                    command.start_date,
                    command.end_date,
                    command.frequency,
                )
                if not vendor_bars:
                    errors.append(f"{ticker_upper}: vendor returned no bars")
                    continue

                # VendorPriceBar has no adj_close; use close as the adjusted price.
                # Schwab returns split/dividend-adjusted prices in the close field.
                domain_bars = [
                    PriceBar(
                        asset_id=asset.asset_id,
                        bar_date=bar.bar_date,
                        frequency=bar.frequency,
                        adj_close=bar.close,
                        close=bar.close,
                        volume=bar.volume,
                        pulled_at=bar.pulled_at,
                        vendor_id=vendor_id,
                    )
                    for bar in vendor_bars
                ]
                n = await self._price_repo.bulk_insert(domain_bars)
                total_inserted += n

            except Exception as exc:
                logger.exception("Unexpected error ingesting prices for %s", ticker_upper)
                errors.append(f"{ticker_upper}: {exc}")

        return IngestResult(
            vendor_name=command.vendor_name,
            items_requested=len(command.tickers),
            bars_inserted=total_inserted,
            errors=errors,
        )


# ─────────────────────────────────────────────────────────────────────────── #
# Risk-free rate ingest                                                         #
# ─────────────────────────────────────────────────────────────────────────── #


class IngestRiskFreeCommand(BaseModel):
    """Fetch and store risk-free rate observations from FRED.

    series_code defaults to DTB3 (3-month T-bill, annualised).
    Rates are stored as decimals (e.g. 5.25 % → 0.0525).
    """

    start_date: date
    end_date: date
    series_code: str = "DTB3"


class IngestRiskFreeHandler:
    """Fetch risk-free rate observations from FRED and upsert into risk_free_series."""

    def __init__(
        self,
        fred_adapter: FredAdapter,
        risk_free_repo: RiskFreeRepository,
    ) -> None:
        self._fred = fred_adapter
        self._risk_free_repo = risk_free_repo

    async def handle(self, command: IngestRiskFreeCommand) -> IngestResult:
        if command.start_date > command.end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must not be after end_date.",
            )

        observations = await self._fred.fetch_risk_free_series(
            start_date=command.start_date,
            end_date=command.end_date,
            series_code=command.series_code,
        )

        n = await self._risk_free_repo.bulk_upsert(
            source="FRED",
            series_code=command.series_code,
            observations=observations,
        )

        return IngestResult(
            vendor_name=f"FRED/{command.series_code}",
            items_requested=1,
            bars_inserted=n,
            errors=[],
        )
