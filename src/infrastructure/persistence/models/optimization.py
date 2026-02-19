"""Optimization layer ORM models: optimization_runs, optimization_results, optimization_weights."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Double, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class OptimizationRun(Base):
    """Portfolio optimization run configuration and status.

    Turnover constraint behavior (when constraints includes turnover_cap):
      reference_snapshot_id provided → snapshot is the turnover baseline
      reference_snapshot_id NULL     → fall back to previous run, or ignore
    """

    __tablename__ = "optimization_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assumption_sets.assumption_id"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(Text, nullable=False)    # MVP / FRONTIER_POINT / FRONTIER_SERIES / TANGENCY
    objective: Mapped[str] = mapped_column(Text, nullable=False)   # MIN_VAR / MAX_SHARPE
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Optional: supplies current holdings for turnover constraint
    reference_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("current_holdings_snapshots.snapshot_id"),
        nullable=True,
    )
    target_return: Mapped[Optional[float]] = mapped_column(Double, nullable=True)  # FRONTIER_POINT only
    status: Mapped[str] = mapped_column(Text, nullable=False)              # SUCCESS / INFEASIBLE / ERROR
    infeasibility_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solver_meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    assumption_set: Mapped["AssumptionSet"] = relationship(back_populates="optimization_runs")
    reference_snapshot: Mapped[Optional["CurrentHoldingsSnapshot"]] = relationship(
        "CurrentHoldingsSnapshot",
        foreign_keys=[reference_snapshot_id],
        back_populates="optimization_runs",
    )
    result: Mapped[Optional["OptimizationResult"]] = relationship(
        back_populates="run", uselist=False, cascade="all, delete-orphan"
    )
    weights: Mapped[list["OptimizationWeight"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    drift_checks: Mapped[list["DriftCheck"]] = relationship(back_populates="run")
    scenario_results: Mapped[list["ScenarioResult"]] = relationship(back_populates="run")


class OptimizationResult(Base):
    """Portfolio-level statistics for a successful optimization run.

    1:1 with OptimizationRun — run_id serves as both PK and FK.
    """

    __tablename__ = "optimization_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    exp_return: Mapped[float] = mapped_column(Double, nullable=False)
    variance: Mapped[float] = mapped_column(Double, nullable=False)
    stdev: Mapped[float] = mapped_column(Double, nullable=False)
    sharpe: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    hhi: Mapped[float] = mapped_column(Double, nullable=False)
    effective_n: Mapped[float] = mapped_column(Double, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped["OptimizationRun"] = relationship(back_populates="result")


class OptimizationWeight(Base):
    """Per-asset weight and risk decomposition for an optimization run.

    MCR / CRC / PRC stored so risk decomposition is retrievable without
    recomputing from the covariance matrix.
    Composite PK: (run_id, asset_id).
    """

    __tablename__ = "optimization_weights"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Double, nullable=False)
    mcr: Mapped[float] = mapped_column(Double, nullable=False)  # marginal contribution to risk
    crc: Mapped[float] = mapped_column(Double, nullable=False)  # component contribution to risk
    prc: Mapped[float] = mapped_column(Double, nullable=False)  # percent risk contribution

    run: Mapped["OptimizationRun"] = relationship(back_populates="weights")
    asset: Mapped["Asset"] = relationship(back_populates="optimization_weights")
