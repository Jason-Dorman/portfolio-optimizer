"""Current holdings domain models.

A HoldingsSnapshot is an aggregate root containing a set of HoldingsPositions.
The weights across all positions must sum to 1.0 (enforced on construction).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HoldingsPosition(BaseModel):
    """A single asset position within a holdings snapshot.

    weight is the normalised allocation in [0, 1].
    market_value is optional; stored only when the user provided dollar values
    at ingest time (before normalisation to weights).
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: UUID
    asset_id: UUID
    weight: float = Field(ge=0.0, le=1.0)
    market_value: float | None = None


class HoldingsSnapshot(BaseModel):
    """A dated snapshot of a user's portfolio holdings.

    positions weights must sum to 1.0 (within floating-point tolerance).
    Use from_market_values() when the user provides dollar values instead
    of weights — that factory normalises automatically.
    """

    snapshot_id: UUID = Field(default_factory=uuid4)
    label: str
    snapshot_date: date
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    positions: list[HoldingsPosition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> HoldingsSnapshot:
        if not self.positions:
            return self
        total = sum(p.weight for p in self.positions)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Position weights must sum to 1.0, got {total:.8f}. "
                "Use from_market_values() to normalise market values automatically."
            )
        return self

    @classmethod
    def from_market_values(
        cls,
        label: str,
        snapshot_date: date,
        positions: list[tuple[UUID, float]],  # (asset_id, market_value)
    ) -> HoldingsSnapshot:
        """Construct a snapshot from raw market values.

        Normalises each position's market value to a weight by dividing by
        the total portfolio value. The original market_value is preserved on
        each position for reference.

        Raises ValueError if total market value is zero or negative.
        """
        total = sum(mv for _, mv in positions)
        if total <= 0:
            raise ValueError(f"Total market value must be positive, got {total}")

        snapshot_id = uuid4()
        normalised = [
            HoldingsPosition(
                snapshot_id=snapshot_id,
                asset_id=asset_id,
                weight=mv / total,
                market_value=mv,
            )
            for asset_id, mv in positions
        ]
        return cls(
            snapshot_id=snapshot_id,
            label=label,
            snapshot_date=snapshot_date,
            positions=normalised,
        )
