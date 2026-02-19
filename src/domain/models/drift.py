"""Drift detection domain models.

DriftCheck is an aggregate root containing a set of DriftPositions.
Each position records how far the current implied weight has moved from
the target weight established by an optimization run.

Drift always uses simple returns for wealth compounding (DATA-MODEL.md §4.11).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DEFAULT_THRESHOLD = 0.05  # 5 percentage points


class DriftPosition(BaseModel):
    """Per-asset drift measurement for a drift check.

    target_weight  — w*  from the linked optimization run
    current_weight — wᵢ,ₜ implied by price appreciation since last rebalance
    drift_abs      — |current_weight − target_weight|
    breached       — drift_abs > threshold_pct
    explanation    — plain-language alert; REQUIRED when breached is True.
    """

    model_config = ConfigDict(frozen=True)

    drift_id: UUID
    asset_id: UUID
    target_weight: float = Field(ge=0.0, le=1.0)
    current_weight: float = Field(ge=0.0, le=1.0)
    drift_abs: float = Field(ge=0.0)
    breached: bool
    explanation: str | None = None

    @model_validator(mode="after")
    def _explanation_required_when_breached(self) -> DriftPosition:
        if self.breached and self.explanation is None:
            raise ValueError(
                f"explanation is required when breached is True "
                f"(asset_id={self.asset_id})"
            )
        return self

    @model_validator(mode="after")
    def _drift_abs_consistent(self) -> DriftPosition:
        expected = abs(self.current_weight - self.target_weight)
        if abs(self.drift_abs - expected) > 1e-8:
            raise ValueError(
                f"drift_abs ({self.drift_abs:.10f}) must equal "
                f"|current_weight − target_weight| ({expected:.10f})"
            )
        return self


class DriftCheck(BaseModel):
    """A dated drift check against the target weights of an optimization run.

    any_breach is True if at least one position's drift exceeds threshold_pct.
    Use the create() factory to build a DriftCheck from unsaved positions —
    it auto-computes drift_id, drift_abs, breached, and any_breach.
    """

    drift_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    check_date: date
    threshold_pct: float = Field(default=_DEFAULT_THRESHOLD, gt=0.0, le=1.0)
    any_breach: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    positions: list[DriftPosition] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        run_id: UUID,
        check_date: date,
        raw_positions: list[tuple[UUID, float, float, str | None]],
        # each tuple: (asset_id, target_weight, current_weight, explanation_if_breached)
        threshold_pct: float = _DEFAULT_THRESHOLD,
    ) -> DriftCheck:
        """Build a DriftCheck from raw weight pairs.

        raw_positions: list of (asset_id, target_weight, current_weight, explanation)
          explanation is required only when the position breaches the threshold;
          pass None for non-breaching positions.

        Computes drift_abs and breached automatically from the weights.
        """
        drift_id = uuid4()
        positions: list[DriftPosition] = []

        for asset_id, target, current, explanation in raw_positions:
            drift_abs = abs(current - target)
            breached = drift_abs > threshold_pct
            positions.append(
                DriftPosition(
                    drift_id=drift_id,
                    asset_id=asset_id,
                    target_weight=target,
                    current_weight=current,
                    drift_abs=drift_abs,
                    breached=breached,
                    explanation=explanation,
                )
            )

        return cls(
            drift_id=drift_id,
            run_id=run_id,
            check_date=check_date,
            threshold_pct=threshold_pct,
            any_breach=any(p.breached for p in positions),
            positions=positions,
        )
