"""Reference layer ORM models: assets, universes, universe_assets, data_vendors."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class Asset(Base):
    """Investable asset — ETF or individual security.

    asset_class and geography are structured enumerations enforced at the
    application layer. Free-text classification is not permitted.
    sector is null for non-equity assets.
    """

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("ticker", name="uq_assets_ticker"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[str] = mapped_column(Text, nullable=False)  # equity / fixed_income / …
    sub_class: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # GICS; null non-equity
    geography: Mapped[str] = mapped_column(Text, nullable=False)  # us / developed_ex_us / …
    currency: Mapped[str] = mapped_column(Text, nullable=False)  # ISO 4217
    is_etf: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    universe_memberships: Mapped[list["UniverseAsset"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="asset")
    return_series_rows: Mapped[list["ReturnSeries"]] = relationship(back_populates="asset")
    assumption_stats: Mapped[list["AssumptionAssetStat"]] = relationship(back_populates="asset")
    holdings_positions: Mapped[list["CurrentHoldingsPosition"]] = relationship(
        back_populates="asset"
    )
    screening_scores: Mapped[list["ScreeningScore"]] = relationship(back_populates="asset")
    optimization_weights: Mapped[list["OptimizationWeight"]] = relationship(
        back_populates="asset"
    )
    drift_positions: Mapped[list["DriftCheckPosition"]] = relationship(back_populates="asset")
    backtest_benchmark_roles: Mapped[list["BacktestRun"]] = relationship(
        "BacktestRun",
        foreign_keys="BacktestRun.benchmark_asset_id",
        back_populates="benchmark_asset",
    )


class Universe(Base):
    """Asset universe — active optimization universe or screening candidate pool.

    universe_type: 'active' | 'candidate_pool'
    """

    __tablename__ = "universes"
    __table_args__ = (UniqueConstraint("name", name="uq_universes_name"),)

    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    universe_type: Mapped[str] = mapped_column(Text, nullable=False)  # active / candidate_pool
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    universe_assets: Mapped[list["UniverseAsset"]] = relationship(
        back_populates="universe", cascade="all, delete-orphan"
    )
    assumption_sets: Mapped[list["AssumptionSet"]] = relationship(back_populates="universe")
    # Two distinct FK paths from ScreeningRun → Universe; disambiguated with foreign_keys.
    screening_runs_as_pool: Mapped[list["ScreeningRun"]] = relationship(
        "ScreeningRun",
        foreign_keys="ScreeningRun.candidate_pool_id",
        back_populates="candidate_pool",
    )
    screening_runs_as_seed: Mapped[list["ScreeningRun"]] = relationship(
        "ScreeningRun",
        foreign_keys="ScreeningRun.reference_universe_id",
        back_populates="reference_universe",
    )
    backtest_runs: Mapped[list["BacktestRun"]] = relationship(
        "BacktestRun",
        foreign_keys="BacktestRun.universe_id",
        back_populates="universe",
    )


class UniverseAsset(Base):
    """Association: which assets belong to which universe."""

    __tablename__ = "universe_assets"

    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universes.universe_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_benchmark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    universe: Mapped["Universe"] = relationship(back_populates="universe_assets")
    asset: Mapped["Asset"] = relationship(back_populates="universe_memberships")


class DataVendor(Base):
    """External market data provider (e.g. Polygon, Tiingo, FRED)."""

    __tablename__ = "data_vendors"
    __table_args__ = (UniqueConstraint("name", name="uq_data_vendors_name"),)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="vendor")
