"""Drift detection ORM models: drift_checks, drift_check_positions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Double, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class DriftCheck(Base):
    """Point-in-time drift check against an optimization run's target weights."""

    __tablename__ = "drift_checks"

    drift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("optimization_runs.run_id"), nullable=False
    )
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_pct: Mapped[float] = mapped_column(Double, nullable=False, default=0.05)  # default 5%
    any_breach: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["OptimizationRun"] = relationship(back_populates="drift_checks")
    positions: Mapped[list["DriftCheckPosition"]] = relationship(
        back_populates="drift_check", cascade="all, delete-orphan"
    )


class DriftCheckPosition(Base):
    """Per-asset drift measurement within a drift check.

    explanation is required (NOT NULL) when breached = True. This invariant
    is enforced at the application layer in the command handler before insert.
    Composite PK: (drift_id, asset_id).
    """

    __tablename__ = "drift_check_positions"

    drift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drift_checks.drift_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    target_weight: Mapped[float] = mapped_column(Double, nullable=False)
    current_weight: Mapped[float] = mapped_column(Double, nullable=False)
    drift_abs: Mapped[float] = mapped_column(Double, nullable=False)
    breached: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # required when breached

    drift_check: Mapped["DriftCheck"] = relationship(back_populates="positions")
    asset: Mapped["Asset"] = relationship(back_populates="drift_positions")
