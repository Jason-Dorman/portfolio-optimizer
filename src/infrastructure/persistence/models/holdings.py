"""Holdings layer ORM models: current_holdings_snapshots, current_holdings_positions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Double, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class CurrentHoldingsSnapshot(Base):
    """Point-in-time snapshot of a user's portfolio holdings.

    Screening uses the most recent snapshot (by snapshot_date) when
    reference_type = 'current_holdings'. If no snapshot exists, screening
    falls back to a seed universe.

    Weights must sum to 1.0 across positions; enforced at application layer.
    """

    __tablename__ = "current_holdings_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    positions: Mapped[list["CurrentHoldingsPosition"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    # Conditional FK from ScreeningRun (reference_type = 'current_holdings')
    screening_runs: Mapped[list["ScreeningRun"]] = relationship(
        "ScreeningRun",
        foreign_keys="ScreeningRun.reference_snapshot_id",
        back_populates="reference_snapshot",
    )
    # Optional turnover reference in OptimizationRun
    optimization_runs: Mapped[list["OptimizationRun"]] = relationship(
        "OptimizationRun",
        foreign_keys="OptimizationRun.reference_snapshot_id",
        back_populates="reference_snapshot",
    )


class CurrentHoldingsPosition(Base):
    """Individual asset position within a holdings snapshot.

    market_value is optional — if provided, weights are normalized at ingest time.
    Composite PK: (snapshot_id, asset_id).
    """

    __tablename__ = "current_holdings_positions"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("current_holdings_snapshots.snapshot_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Double, nullable=False)
    market_value: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    snapshot: Mapped["CurrentHoldingsSnapshot"] = relationship(back_populates="positions")
    asset: Mapped["Asset"] = relationship(back_populates="holdings_positions")
