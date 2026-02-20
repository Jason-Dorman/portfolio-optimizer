"""Assumption set domain models.

An AssumptionSet is the versioned snapshot of all estimation choices
(universe, lookback window, frequency, estimator methods, risk-free rate)
that drives a particular optimization or screening run.

AssetStats holds the per-asset μ and σ derived from that assumption set.
CovarianceMatrix holds the full Σ, stored as upper-triangle entries only
(asset_id_i ≤ asset_id_j by UUID lexicographic ordering).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import CovMethod, Estimator, Frequency, ReturnType


class AssetStats(BaseModel):
    """Annualised expected return and volatility for a single asset.

    Both mu_annual and sigma_annual are annualised figures.
    sigma_annual must be strictly positive.
    """

    model_config = ConfigDict(frozen=True)

    assumption_id: UUID
    asset_id: UUID
    mu_annual: float
    sigma_annual: float = Field(gt=0.0)


class CovarianceEntry(BaseModel):
    """One cell of the upper-triangle covariance matrix.

    Storage invariant: asset_id_i ≤ asset_id_j (UUID lexicographic order).
    The constructor auto-canonicalises the order so callers don't need to
    pre-sort. To look up cov(i, j) use CovarianceMatrix.get_covariance().
    """

    model_config = ConfigDict(frozen=True)

    assumption_id: UUID
    asset_id_i: UUID
    asset_id_j: UUID
    cov_annual: float

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_order(cls, data: dict[str, object]) -> dict[str, object]:
        """Ensure asset_id_i ≤ asset_id_j so only the upper triangle is stored."""
        i = data.get("asset_id_i")
        j = data.get("asset_id_j")
        if i is not None and j is not None and str(i) > str(j):
            data["asset_id_i"], data["asset_id_j"] = j, i
        return data


class CovarianceMatrix(BaseModel):
    """Full covariance matrix for an assumption set.

    Entries cover the upper triangle only (i ≤ j).  Symmetry is reconstructed
    at lookup time via get_covariance(). The diagonal entries (i == j) are the
    asset variances (σ_i²).

    Use from_full_matrix() to build from a dense symmetric matrix.
    """

    assumption_id: UUID
    entries: list[CovarianceEntry]

    def get_covariance(self, asset_id_i: UUID, asset_id_j: UUID) -> float | None:
        """Return cov(i, j), checking both orderings (upper-triangle canonical)."""
        a = min(str(asset_id_i), str(asset_id_j))
        b = max(str(asset_id_i), str(asset_id_j))
        for entry in self.entries:
            if str(entry.asset_id_i) == a and str(entry.asset_id_j) == b:
                return entry.cov_annual
        return None

    @classmethod
    def from_full_matrix(
        cls,
        assumption_id: UUID,
        asset_ids: list[UUID],
        matrix: list[list[float]],
    ) -> CovarianceMatrix:
        """Build from a dense n×n symmetric matrix.

        Only the upper triangle (i ≤ j) is stored; the lower triangle is
        discarded. Callers are responsible for ensuring the matrix is
        symmetric before calling this method.

        Raises ValueError if the number of asset_ids does not match the
        matrix dimensions.
        """
        n = len(asset_ids)
        if len(matrix) != n or any(len(row) != n for row in matrix):
            raise ValueError(
                f"matrix must be {n}×{n} to match the {n} asset_ids provided"
            )
        entries = [
            CovarianceEntry(
                assumption_id=assumption_id,
                asset_id_i=asset_ids[i],
                asset_id_j=asset_ids[j],
                cov_annual=matrix[i][j],
            )
            for i in range(n)
            for j in range(i, n)
        ]
        return cls(assumption_id=assumption_id, entries=entries)


class AssumptionSet(BaseModel):
    """Versioned estimation configuration for a universe.

    estimator and cov_method are independent choices:
      estimator  — how expected returns (μ) are computed
      cov_method — how the covariance matrix (Σ) is computed

    psd_repair_applied is set True by the Estimation module if the sample
    covariance matrix failed the positive-semi-definite check and was
    repaired via nearest-PSD projection.
    """

    model_config = ConfigDict(frozen=True)

    assumption_id: UUID = Field(default_factory=uuid4)
    universe_id: UUID
    frequency: Frequency
    return_type: ReturnType
    lookback_start: date
    lookback_end: date
    annualization_factor: int = Field(gt=0)  # 252 daily | 52 weekly | 12 monthly
    rf_annual: float = Field(ge=0.0)
    estimator: Estimator
    cov_method: CovMethod
    psd_repair_applied: bool = False
    psd_repair_note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _lookback_valid(self) -> AssumptionSet:
        if self.lookback_end <= self.lookback_start:
            raise ValueError(
                f"lookback_end ({self.lookback_end}) must be after "
                f"lookback_start ({self.lookback_start})"
            )
        return self

    @classmethod
    def create(
        cls,
        universe_id: UUID,
        frequency: Frequency,
        return_type: ReturnType,
        lookback_start: date,
        lookback_end: date,
        rf_annual: float,
        estimator: Estimator,
        cov_method: CovMethod,
        annualization_factor: int | None = None,
    ) -> AssumptionSet:
        """Named constructor; derives annualization_factor from frequency when omitted."""
        factor = annualization_factor if annualization_factor is not None else frequency.periods_per_year
        return cls(
            universe_id=universe_id,
            frequency=frequency,
            return_type=return_type,
            lookback_start=lookback_start,
            lookback_end=lookback_end,
            rf_annual=rf_annual,
            estimator=estimator,
            cov_method=cov_method,
            annualization_factor=factor,
        )


class CorrelationEntry(BaseModel):
    """One cell of the upper-triangle correlation matrix.

    Storage invariant: asset_id_i ≤ asset_id_j (UUID lexicographic order).
    corr is in [−1, 1]; diagonal entries (i == j) are always 1.0.
    The constructor auto-canonicalises the order so callers don't pre-sort.
    """

    model_config = ConfigDict(frozen=True)

    assumption_id: UUID
    asset_id_i: UUID
    asset_id_j: UUID
    corr: float = Field(ge=-1.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_order(cls, data: dict[str, object]) -> dict[str, object]:
        """Ensure asset_id_i ≤ asset_id_j so only the upper triangle is stored."""
        i = data.get("asset_id_i")
        j = data.get("asset_id_j")
        if i is not None and j is not None and str(i) > str(j):
            data["asset_id_i"], data["asset_id_j"] = j, i
        return data


class CorrelationMatrix(BaseModel):
    """Full correlation matrix for an assumption set.

    Entries cover the upper triangle only (i ≤ j).  Symmetry is reconstructed
    at lookup time via get_correlation(). Diagonal entries (i == j) are 1.0.

    Derived from CovarianceMatrix: corr(i,j) = cov(i,j) / (σ_i × σ_j).
    """

    assumption_id: UUID
    entries: list[CorrelationEntry]

    def get_correlation(self, asset_id_i: UUID, asset_id_j: UUID) -> float | None:
        """Return corr(i, j), checking both orderings (upper-triangle canonical)."""
        a = min(str(asset_id_i), str(asset_id_j))
        b = max(str(asset_id_i), str(asset_id_j))
        for entry in self.entries:
            if str(entry.asset_id_i) == a and str(entry.asset_id_j) == b:
                return entry.corr
        return None
