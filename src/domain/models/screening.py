"""Asset screening domain models.

A ScreeningRun scores every asset in a candidate pool against a reference
portfolio (current holdings snapshot OR a seed universe — exactly one must
be supplied; there is no automatic fallback).

ScreeningConfig holds the tunable parameters for the scoring algorithm.
ScreeningScore holds the per-asset breakdown and composite score.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ReferenceType

# Default signal weights from DATA-MODEL.md §4.9
_DEFAULT_CORR_WEIGHT = 0.40
_DEFAULT_MVR_WEIGHT = 0.30
_DEFAULT_GAP_WEIGHT = 0.15
_DEFAULT_HHI_WEIGHT = 0.15


class ScoreWeights(BaseModel):
    """Composite-score signal weights (λ₁…λ₄); must sum to 1.0.

    correlation  — average pairwise correlation signal weight (λ₁)
    marginal_vol — marginal volatility reduction signal weight (λ₂)
    sector_gap   — sector/asset-class gap score weight (λ₃)
    hhi          — HHI reduction signal weight (λ₄)
    """

    model_config = ConfigDict(frozen=True)

    correlation: float = Field(default=_DEFAULT_CORR_WEIGHT, ge=0.0, le=1.0)
    marginal_vol: float = Field(default=_DEFAULT_MVR_WEIGHT, ge=0.0, le=1.0)
    sector_gap: float = Field(default=_DEFAULT_GAP_WEIGHT, ge=0.0, le=1.0)
    hhi: float = Field(default=_DEFAULT_HHI_WEIGHT, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> ScoreWeights:
        total = self.correlation + self.marginal_vol + self.sector_gap + self.hhi
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Score weights must sum to 1.0, got {total:.8f} "
                f"(correlation={self.correlation}, marginal_vol={self.marginal_vol}, "
                f"sector_gap={self.sector_gap}, hhi={self.hhi})"
            )
        return self


class ScreeningConfig(BaseModel):
    """Tunable parameters for a screening run.

    nominal_add_weight  — δ; assumed allocation when computing marginal
                          volatility reduction (default 5 %)
    sector_gap_threshold — θ; minimum weight in reference portfolio for an
                           asset class to be considered 'represented' (default 2 %)
    score_weights        — λ₁…λ₄ composite signal weights
    """

    model_config = ConfigDict(frozen=True)

    nominal_add_weight: float = Field(default=0.05, gt=0.0, lt=1.0)
    sector_gap_threshold: float = Field(default=0.02, gt=0.0, lt=1.0)
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)

    @classmethod
    def default(cls) -> ScreeningConfig:
        return cls()


class ScreeningScore(BaseModel):
    """Per-asset diversification scores for one screening run.

    All four raw signals are stored alongside the normalised composite.
    rank 1 = best diversification candidate.
    explanation is a plain-language summary of why this candidate scored
    as it did (always populated before persistence).
    """

    model_config = ConfigDict(frozen=True)

    screening_id: UUID
    asset_id: UUID
    avg_pairwise_corr: float
    marginal_vol_reduction: float
    sector_gap_score: float = Field(ge=0.0, le=1.0)
    hhi_reduction: float
    composite_score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)
    explanation: str


class ScreeningRun(BaseModel):
    """A screening run configuration and its associated scores.

    Exactly one of reference_snapshot_id or reference_universe_id must be
    set, consistent with reference_type — this is enforced at construction.
    There is no automatic fallback; callers must be explicit.
    """

    screening_id: UUID = Field(default_factory=uuid4)
    assumption_id: UUID
    candidate_pool_id: UUID
    reference_type: ReferenceType
    reference_snapshot_id: UUID | None = None  # set when reference_type = CURRENT_HOLDINGS
    reference_universe_id: UUID | None = None  # set when reference_type = SEED_UNIVERSE
    config: ScreeningConfig = Field(default_factory=ScreeningConfig)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scores: list[ScreeningScore] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reference_consistency(self) -> ScreeningRun:
        if self.reference_type == ReferenceType.CURRENT_HOLDINGS:
            if self.reference_snapshot_id is None:
                raise ValueError(
                    "reference_snapshot_id is required when reference_type is CURRENT_HOLDINGS"
                )
            if self.reference_universe_id is not None:
                raise ValueError(
                    "reference_universe_id must be None when reference_type is CURRENT_HOLDINGS"
                )
        elif self.reference_type == ReferenceType.SEED_UNIVERSE:
            if self.reference_universe_id is None:
                raise ValueError(
                    "reference_universe_id is required when reference_type is SEED_UNIVERSE"
                )
            if self.reference_snapshot_id is not None:
                raise ValueError(
                    "reference_snapshot_id must be None when reference_type is SEED_UNIVERSE"
                )
        return self

    @classmethod
    def for_holdings(
        cls,
        assumption_id: UUID,
        candidate_pool_id: UUID,
        reference_snapshot_id: UUID,
        config: ScreeningConfig | None = None,
    ) -> ScreeningRun:
        """Factory: screening run against a current-holdings snapshot."""
        return cls(
            assumption_id=assumption_id,
            candidate_pool_id=candidate_pool_id,
            reference_type=ReferenceType.CURRENT_HOLDINGS,
            reference_snapshot_id=reference_snapshot_id,
            config=config or ScreeningConfig(),
        )

    @classmethod
    def for_universe(
        cls,
        assumption_id: UUID,
        candidate_pool_id: UUID,
        reference_universe_id: UUID,
        config: ScreeningConfig | None = None,
    ) -> ScreeningRun:
        """Factory: screening run against a seed universe (equal weights)."""
        return cls(
            assumption_id=assumption_id,
            candidate_pool_id=candidate_pool_id,
            reference_type=ReferenceType.SEED_UNIVERSE,
            reference_universe_id=reference_universe_id,
            config=config or ScreeningConfig(),
        )
