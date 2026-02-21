"""Market data domain models.

PriceBar  — a single OHLC-style price observation for one asset at one date/frequency.
ReturnPoint — a computed return observation derived from price bars.

Both are immutable value objects (no identity beyond their natural key).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import Frequency, ReturnType


class PriceBar(BaseModel):
    """Adjusted-close price bar for one asset at one date and frequency.

    adj_close is the primary field used for return computation (split/dividend adjusted).
    close is the raw unadjusted close; retained for reference but not used in analytics.
    volume is share volume; None for assets where volume is unavailable or irrelevant.
    pulled_at records when the bar was fetched from the data vendor.
    vendor_id is the data provider UUID; required for persistence (price_bars PK includes it).
    """

    model_config = ConfigDict(frozen=True)

    asset_id: UUID
    bar_date: date
    frequency: Frequency
    adj_close: float = Field(gt=0.0)
    close: float | None = Field(default=None, gt=0.0)
    volume: int | None = Field(default=None, ge=0)
    pulled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    vendor_id: UUID | None = None  # required when persisting; populated on read


class ReturnPoint(BaseModel):
    """A computed return observation for one asset at one date.

    ret is the raw return value — either simple ((P_t / P_{t-1}) − 1) or
    log (ln(P_t / P_{t-1})) depending on return_type.

    The natural key is (asset_id, bar_date, frequency, return_type).
    """

    model_config = ConfigDict(frozen=True)

    asset_id: UUID
    bar_date: date
    frequency: Frequency
    return_type: ReturnType
    ret: float
