"""Estimation layer ORM models: assumption_sets, assumption_asset_stats, assumption_cov."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Double, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class AssumptionSet(Base):
    """Versioned snapshot of return (µ) and covariance (Σ) assumptions for a universe.

    estimator and cov_method are independent:
      estimator  — controls how µ is computed (historical / ewma / shrinkage)
      cov_method — controls how Σ is computed (sample / ledoit_wolf); PSD repair
                   is tracked separately via psd_repair_applied / psd_repair_note
    """

    __tablename__ = "assumption_sets"

    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    universe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universes.universe_id"), nullable=False
    )
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    return_type: Mapped[str] = mapped_column(Text, nullable=False)       # simple / log
    lookback_start: Mapped[date] = mapped_column(Date, nullable=False)
    lookback_end: Mapped[date] = mapped_column(Date, nullable=False)
    annualization_factor: Mapped[int] = mapped_column(Integer, nullable=False)  # 252 / 12 / …
    rf_annual: Mapped[float] = mapped_column(Double, nullable=False)
    estimator: Mapped[str] = mapped_column(Text, nullable=False)          # historical / ewma / shrinkage
    cov_method: Mapped[str] = mapped_column(Text, nullable=False)         # sample / ledoit_wolf
    psd_repair_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    psd_repair_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    universe: Mapped["Universe"] = relationship(back_populates="assumption_sets")
    asset_stats: Mapped[list["AssumptionAssetStat"]] = relationship(
        back_populates="assumption_set", cascade="all, delete-orphan"
    )
    covariances: Mapped[list["AssumptionCov"]] = relationship(
        back_populates="assumption_set", cascade="all, delete-orphan"
    )
    optimization_runs: Mapped[list["OptimizationRun"]] = relationship(
        back_populates="assumption_set"
    )
    screening_runs: Mapped[list["ScreeningRun"]] = relationship(back_populates="assumption_set")


class AssumptionAssetStat(Base):
    """Per-asset annualized µ and σ for an assumption set. Composite PK: (assumption_id, asset_id)."""

    __tablename__ = "assumption_asset_stats"

    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assumption_sets.assumption_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    mu_annual: Mapped[float] = mapped_column(Double, nullable=False)
    sigma_annual: Mapped[float] = mapped_column(Double, nullable=False)

    assumption_set: Mapped["AssumptionSet"] = relationship(back_populates="asset_stats")
    asset: Mapped["Asset"] = relationship(back_populates="assumption_stats")


class AssumptionCov(Base):
    """Upper-triangle covariance matrix entry for an assumption set.

    Store i ≤ j only; application layer reconstructs symmetry.
    When looking up cov(i, j), canonicalize to (min_id, max_id) before querying.

    Two FKs reference assets (asset_id_i, asset_id_j). Direct ORM relationships
    to Asset are omitted to avoid ambiguity — query via FK columns directly.
    """

    __tablename__ = "assumption_cov"

    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assumption_sets.assumption_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id_i: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    asset_id_j: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    cov_annual: Mapped[float] = mapped_column(Double, nullable=False)

    assumption_set: Mapped["AssumptionSet"] = relationship(back_populates="covariances")
