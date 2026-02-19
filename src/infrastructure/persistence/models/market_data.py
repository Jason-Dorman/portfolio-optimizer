"""Market data layer ORM models: price_bars, return_series, risk_free_series."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, Double, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class PriceBar(Base):
    """OHLCV price bar for an asset from a specific vendor.

    Composite PK: (asset_id, vendor_id, bar_date, frequency).
    pulled_at records when the row was fetched — supports audit.
    """

    __tablename__ = "price_bars"
    __table_args__ = (
        Index("ix_price_bars_asset_date", "asset_id", "bar_date"),
        Index("ix_price_bars_freq_date", "frequency", "bar_date"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_vendors.vendor_id"), primary_key=True
    )
    bar_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    frequency: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)  # daily/weekly/monthly
    adj_close: Mapped[float] = mapped_column(Double, nullable=False)
    close: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    pulled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    asset: Mapped["Asset"] = relationship(back_populates="price_bars")
    vendor: Mapped["DataVendor"] = relationship(back_populates="price_bars")


class ReturnSeries(Base):
    """Pre-computed asset return at a given date / frequency / type.

    Composite PK: (asset_id, bar_date, frequency, return_type).
    Derived from price_bars by the estimation service.
    """

    __tablename__ = "return_series"
    __table_args__ = (Index("ix_return_series_asset_date", "asset_id", "bar_date"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True
    )
    bar_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    frequency: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    return_type: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)  # simple / log
    ret: Mapped[float] = mapped_column(Double, nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="return_series_rows")


class RiskFreeSeries(Base):
    """Risk-free rate observations (e.g. FRED T-bill series DTB3)."""

    __tablename__ = "risk_free_series"
    __table_args__ = (Index("ix_risk_free_series_obs_date", "obs_date"),)

    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)       # e.g. FRED
    series_code: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. DTB3
    obs_date: Mapped[date] = mapped_column(Date, nullable=False)
    rf_annual: Mapped[float] = mapped_column(Double, nullable=False)
