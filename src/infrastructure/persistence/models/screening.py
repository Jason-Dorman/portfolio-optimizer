"""Screening layer ORM models: screening_runs, screening_scores."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Double, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class ScreeningRun(Base):
    """Asset screening run — scores and ranks candidates from a candidate pool.

    Conditional FK enforced by DB CHECK constraint:
      reference_type = 'current_holdings'
        → reference_snapshot_id IS NOT NULL, reference_universe_id IS NULL
      reference_type = 'seed_universe'
        → reference_universe_id IS NOT NULL, reference_snapshot_id IS NULL
    """

    __tablename__ = "screening_runs"
    __table_args__ = (
        CheckConstraint(
            "(reference_type = 'current_holdings'"
            " AND reference_snapshot_id IS NOT NULL"
            " AND reference_universe_id IS NULL)"
            " OR"
            " (reference_type = 'seed_universe'"
            " AND reference_universe_id IS NOT NULL"
            " AND reference_snapshot_id IS NULL)",
            name="ck_screening_runs_reference_consistency",
        ),
    )

    screening_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assumption_sets.assumption_id"), nullable=False
    )
    # Must reference a universe with universe_type = 'candidate_pool'
    candidate_pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universes.universe_id"), nullable=False
    )
    reference_type: Mapped[str] = mapped_column(Text, nullable=False)  # current_holdings / seed_universe
    # Populated when reference_type = 'current_holdings'; NULL otherwise
    reference_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("current_holdings_snapshots.snapshot_id"),
        nullable=True,
    )
    # Populated when reference_type = 'seed_universe'; NULL otherwise
    reference_universe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universes.universe_id"), nullable=True
    )
    # Weight assumed when computing marginal vol reduction (default 5%)
    nominal_add_weight: Mapped[float] = mapped_column(Double, nullable=False, default=0.05)
    # Minimum weight in reference portfolio for an asset class to be 'represented' (default 2%)
    sector_gap_threshold: Mapped[float] = mapped_column(Double, nullable=False, default=0.02)
    # e.g. {"correlation": 0.4, "marginal_vol": 0.3, "sector_gap": 0.15, "hhi": 0.15}
    score_weights: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    assumption_set: Mapped["AssumptionSet"] = relationship(back_populates="screening_runs")
    candidate_pool: Mapped["Universe"] = relationship(
        "Universe",
        foreign_keys=[candidate_pool_id],
        back_populates="screening_runs_as_pool",
    )
    reference_snapshot: Mapped[Optional["CurrentHoldingsSnapshot"]] = relationship(
        "CurrentHoldingsSnapshot",
        foreign_keys=[reference_snapshot_id],
        back_populates="screening_runs",
    )
    reference_universe: Mapped[Optional["Universe"]] = relationship(
        "Universe",
        foreign_keys=[reference_universe_id],
        back_populates="screening_runs_as_seed",
    )
    scores: Mapped[list["ScreeningScore"]] = relationship(
        back_populates="screening_run", cascade="all, delete-orphan"
    )


class ScreeningScore(Base):
    """Per-asset diversification scores produced by a screening run.

    rank 1 = best diversification candidate.
    composite_score is the weighted combination of the four component scores.
    Composite PK: (screening_id, asset_id).
    """

    __tablename__ = "screening_scores"

    screening_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screening_runs.screening_id", ondelete="CASCADE"),
        primary_key=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.asset_id"), primary_key=True
    )
    avg_pairwise_corr: Mapped[float] = mapped_column(Double, nullable=False)
    marginal_vol_reduction: Mapped[float] = mapped_column(Double, nullable=False)
    sector_gap_score: Mapped[float] = mapped_column(Double, nullable=False)  # 0–1
    hhi_reduction: Mapped[float] = mapped_column(Double, nullable=False)
    composite_score: Mapped[float] = mapped_column(Double, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    screening_run: Mapped["ScreeningRun"] = relationship(back_populates="scores")
    asset: Mapped["Asset"] = relationship(back_populates="screening_scores")
