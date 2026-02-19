"""Optimization domain models.

OptimizationConstraints  — per-run solver constraints (long-only, bounds, caps)
PortfolioWeight          — per-asset weight with embedded risk decomposition
RiskDecomposition        — MCR / CRC / PRC value object (used standalone too)
OptimizationResult       — portfolio-level statistics for a successful run
OptimizationRun          — run configuration, status, and full results
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Objective, OptimizationStatus, RunType


class AssetBound(BaseModel):
    """Per-asset weight bounds [min_weight, max_weight].

    Both bounds are in [0, 1] for long-only portfolios.
    min_weight must not exceed max_weight.
    """

    model_config = ConfigDict(frozen=True)

    asset_id: UUID
    min_weight: float = Field(ge=0.0, le=1.0)
    max_weight: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _valid_range(self) -> AssetBound:
        if self.min_weight > self.max_weight:
            raise ValueError(
                f"min_weight ({self.min_weight}) must not exceed max_weight ({self.max_weight})"
            )
        return self


class OptimizationConstraints(BaseModel):
    """Solver constraints for one optimization run.

    long_only       — all weights ≥ 0
    asset_bounds    — per-asset [min, max] weight overrides (subset of universe)
    leverage_cap    — Σ|wᵢ| ≤ L  (L > 0); None = uncapped
    concentration_cap — max(|wᵢ|) ≤ c  (c ∈ (0,1]); None = uncapped
    turnover_cap    — Σ|wᵢ − wᵢ_prev| ≤ T; None = uncapped.
                      Requires a reference snapshot or previous run; ignored
                      automatically when neither exists (with warning).
    """

    model_config = ConfigDict(frozen=True)

    long_only: bool = True
    asset_bounds: list[AssetBound] = Field(default_factory=list)
    leverage_cap: float | None = Field(default=None, gt=0.0)
    concentration_cap: float | None = Field(default=None, gt=0.0, le=1.0)
    turnover_cap: float | None = Field(default=None, gt=0.0)

    @classmethod
    def long_only_unconstrained(cls) -> OptimizationConstraints:
        """Minimal long-only constraint set with no additional bounds."""
        return cls(long_only=True)


class RiskDecomposition(BaseModel):
    """Per-asset risk contribution metrics.

    Derived from DATA-MODEL.md §4.7:
      g        = Σw  (covariance-weighted weights vector)
      MCR_i    = g_i / σ_p
      CRC_i    = w_i × MCR_i
      PRC_i    = CRC_i / σ_p

    Σ CRC_i = σ_p  and  Σ PRC_i = 1.
    """

    model_config = ConfigDict(frozen=True)

    asset_id: UUID
    mcr: float  # marginal contribution to risk
    crc: float  # component contribution to risk
    prc: float  # percent risk contribution; sum across assets = 1.0


class PortfolioWeight(BaseModel):
    """Per-asset weight with embedded risk decomposition.

    Stores MCR / CRC / PRC alongside the weight so risk decomposition is
    retrievable from the DB without recomputing the covariance product.
    """

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    asset_id: UUID
    weight: float = Field(ge=0.0, le=1.0)
    mcr: float
    crc: float
    prc: float

    @property
    def risk_decomposition(self) -> RiskDecomposition:
        return RiskDecomposition(asset_id=self.asset_id, mcr=self.mcr, crc=self.crc, prc=self.prc)


class OptimizationResult(BaseModel):
    """Portfolio-level statistics for a successful optimization run.

    1:1 with OptimizationRun (run_id is the shared key).
    hhi = Σ wᵢ²  ∈ (0, 1];  effective_n = 1 / hhi ≥ 1.
    sharpe is None when the risk-free rate was not applicable (e.g. MVP run).
    """

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    exp_return: float
    variance: float = Field(ge=0.0)
    stdev: float = Field(ge=0.0)
    sharpe: float | None = None
    hhi: float = Field(gt=0.0, le=1.0)
    effective_n: float = Field(ge=1.0)
    explanation: str  # plain-language portfolio summary

    @model_validator(mode="after")
    def _stdev_consistent(self) -> OptimizationResult:
        if abs(self.stdev**2 - self.variance) > 1e-8:
            raise ValueError(
                f"stdev² ({self.stdev**2:.10f}) must equal variance ({self.variance:.10f})"
            )
        return self

    @model_validator(mode="after")
    def _effective_n_consistent(self) -> OptimizationResult:
        expected = 1.0 / self.hhi
        if abs(self.effective_n - expected) > 1e-6:
            raise ValueError(
                f"effective_n ({self.effective_n:.6f}) must equal 1/hhi ({expected:.6f})"
            )
        return self


class OptimizationRun(BaseModel):
    """Portfolio optimization run: configuration, status, weights, and result.

    Runs are persisted only after the solver completes; status is always one
    of SUCCESS / INFEASIBLE / ERROR at write time — there is no pending state.

    Invariants (enforced by validator):
      status = SUCCESS   → infeasibility_reason is None
      status ≠ SUCCESS   → infeasibility_reason is a non-empty string

    target_return is required for FRONTIER_POINT runs and ignored otherwise.

    Turnover constraint behaviour (when constraints.turnover_cap is set):
      reference_snapshot_id provided → snapshot is the turnover baseline
      reference_snapshot_id None     → system falls back to the previous run
                                       for the same universe; ignored if none exists
    """

    run_id: UUID = Field(default_factory=uuid4)
    assumption_id: UUID
    run_type: RunType
    objective: Objective
    constraints: OptimizationConstraints
    reference_snapshot_id: UUID | None = None
    target_return: float | None = None  # FRONTIER_POINT only
    status: OptimizationStatus
    infeasibility_reason: str | None = None
    solver_meta: dict[str, object] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    weights: list[PortfolioWeight] = Field(default_factory=list)
    result: OptimizationResult | None = None

    @model_validator(mode="after")
    def _frontier_point_requires_target(self) -> OptimizationRun:
        if self.run_type == RunType.FRONTIER_POINT and self.target_return is None:
            raise ValueError("target_return is required for FRONTIER_POINT run_type")
        return self

    @model_validator(mode="after")
    def _status_and_reason_consistent(self) -> OptimizationRun:
        if self.status == OptimizationStatus.SUCCESS:
            if self.infeasibility_reason is not None:
                raise ValueError(
                    "infeasibility_reason must be None when status is SUCCESS"
                )
        else:
            if not self.infeasibility_reason:  # None or empty string
                raise ValueError(
                    f"infeasibility_reason is required (non-empty) when status is {self.status}"
                )
        return self

    @classmethod
    def create_mvp(
        cls,
        assumption_id: UUID,
        status: OptimizationStatus,
        constraints: OptimizationConstraints | None = None,
        infeasibility_reason: str | None = None,
        result: OptimizationResult | None = None,
        weights: list[PortfolioWeight] | None = None,
        reference_snapshot_id: UUID | None = None,
        solver_meta: dict[str, object] | None = None,
    ) -> OptimizationRun:
        """Factory: minimum-variance portfolio (locks in MVP / MIN_VAR invariants)."""
        return cls(
            assumption_id=assumption_id,
            run_type=RunType.MVP,
            objective=Objective.MIN_VAR,
            constraints=constraints or OptimizationConstraints.long_only_unconstrained(),
            status=status,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights or [],
            reference_snapshot_id=reference_snapshot_id,
            solver_meta=solver_meta,
        )

    @classmethod
    def create_tangency(
        cls,
        assumption_id: UUID,
        status: OptimizationStatus,
        constraints: OptimizationConstraints | None = None,
        infeasibility_reason: str | None = None,
        result: OptimizationResult | None = None,
        weights: list[PortfolioWeight] | None = None,
        reference_snapshot_id: UUID | None = None,
        solver_meta: dict[str, object] | None = None,
    ) -> OptimizationRun:
        """Factory: tangency portfolio (locks in TANGENCY / MAX_SHARPE invariants)."""
        return cls(
            assumption_id=assumption_id,
            run_type=RunType.TANGENCY,
            objective=Objective.MAX_SHARPE,
            constraints=constraints or OptimizationConstraints.long_only_unconstrained(),
            status=status,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights or [],
            reference_snapshot_id=reference_snapshot_id,
            solver_meta=solver_meta,
        )

    @classmethod
    def create_frontier_point(
        cls,
        assumption_id: UUID,
        target_return: float,
        status: OptimizationStatus,
        constraints: OptimizationConstraints | None = None,
        infeasibility_reason: str | None = None,
        result: OptimizationResult | None = None,
        weights: list[PortfolioWeight] | None = None,
        reference_snapshot_id: UUID | None = None,
        solver_meta: dict[str, object] | None = None,
    ) -> OptimizationRun:
        """Factory: efficient-frontier point (locks in FRONTIER_POINT / MIN_VAR invariants)."""
        return cls(
            assumption_id=assumption_id,
            run_type=RunType.FRONTIER_POINT,
            objective=Objective.MIN_VAR,
            target_return=target_return,
            constraints=constraints or OptimizationConstraints.long_only_unconstrained(),
            status=status,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights or [],
            reference_snapshot_id=reference_snapshot_id,
            solver_meta=solver_meta,
        )
