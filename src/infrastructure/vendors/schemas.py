"""Vendor-layer DTOs: raw price data returned by adapters before domain mapping.

VendorPriceBar is what every VendorAdapter.fetch_price_history() returns.
Command handlers receive this DTO and are responsible for resolving asset_id
and vendor_id before constructing the domain PriceBar.

This keeps infrastructure concerns (vendor API shapes) out of the domain layer
and domain concerns (asset identity, vendor provenance) out of the vendor layer.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models.enums import Frequency


class VendorPriceBar(BaseModel):
    """Raw OHLC bar from a vendor API, not yet mapped to a domain PriceBar.

    All four price fields are required — vendors that omit open/high/low must
    fill them from close before constructing this object.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    bar_date: date
    frequency: Frequency
    open: float = Field(gt=0.0)
    high: float = Field(gt=0.0)
    low: float = Field(gt=0.0)
    close: float = Field(gt=0.0)
    volume: int | None = Field(default=None, ge=0)
    pulled_at: datetime
