"""Portfolio optimization service.

Implements DATA-MODEL.md §4.5–4.7:
  - Minimum Variance Portfolio (MVP)
  - Efficient Frontier Points (target return constraint)
  - Tangency Portfolio (max Sharpe)
  - Efficient Frontier Series
  - Risk Decomposition (MCR / CRC / PRC)

All methods are pure computation — no database access, no UUIDs.
The caller (command handler) is responsible for wrapping SolverResult
into OptimizationRun / OptimizationResult for persistence.

Solver: scipy.optimize.minimize (SLSQP).
  - Handles equality and inequality constraints natively.
  - Used for both convex (variance) and non-convex (Sharpe) objectives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from uuid import UUID

import numpy as np
from scipy.optimize import minimize

from src.domain.models.assets import Asset
from src.domain.models.optimization import AssetBound, OptimizationConstraints

logger = logging.getLogger(__name__)

_WEIGHT_TOL = 1e-8          # weights below this are treated as zero
_SOLVER_FTOL = 1e-10        # SLSQP function-value convergence tolerance
_SOLVER_MAXITER = 1000


# ─────────────────────────────────────────────────────────────────────────── #
# Output types                                                                 #
# ─────────────────────────────────────────────────────────────────────────── #


@dataclass
class SolverResult:
    """Output from a single optimization call.

    No UUIDs — this is the pure-computation layer.  The command handler wraps
    this into OptimizationRun / OptimizationResult for persistence.

    When is_feasible=False all numeric fields are None and infeasibility_reason
    carries a plain-language explanation (FR11).
    """

    weights: np.ndarray | None
    exp_return: float | None
    variance: float | None
    stdev: float | None
    sharpe: float | None          # None for MVP; set for tangency
    hhi: float | None
    effective_n: float | None
    explanation: str
    is_feasible: bool
    infeasibility_reason: str | None
    solver_meta: dict[str, object] | None


@dataclass
class RiskDecompositionResult:
    """Per-asset risk contributions — positional arrays aligned to weight vector.

    Implements DATA-MODEL.md §4.7:
        g      = Σw
        MCR_i  = g_i / σ_p            (marginal contribution to risk)
        CRC_i  = w_i · MCR_i          (component contribution to risk)
        PRC_i  = CRC_i / σ_p          (percent risk contribution)

    Identities:  Σ CRC_i = σ_p,   Σ PRC_i = 1.
    """

    mcr: np.ndarray   # shape (n,)
    crc: np.ndarray   # shape (n,)
    prc: np.ndarray   # shape (n,)


# ─────────────────────────────────────────────────────────────────────────── #
# Service                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


class OptimizationService:
    """Pure computation service for mean-variance portfolio optimization.

    Responsibilities (single, focused):
      - Solve MVP, tangency, and frontier-point optimization problems.
      - Generate the efficient frontier as a series of frontier points.
      - Compute per-asset risk decomposition (MCR / CRC / PRC).
      - Check feasibility and produce plain-language infeasibility reasons.
      - Generate plain-language explanations for successful results (FR14).

    The class is stateless; all configuration is passed per-call.

    Per-asset bounds (OptimizationConstraints.asset_bounds) require an
    asset_ids list to resolve UUID → column index.  When asset_ids is None
    the bounds are silently ignored and a warning is logged.
    """

    # ─────────────────────────────────────────────────────────────────── #
    # Public API                                                           #
    # ─────────────────────────────────────────────────────────────────── #

    def optimize_mvp(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        constraints: OptimizationConstraints,
        prev_weights: np.ndarray | None = None,
        asset_ids: list[UUID] | None = None,
        assets: list[Asset] | None = None,
    ) -> SolverResult:
        """Minimize portfolio variance subject to constraints.

        DATA-MODEL.md §4.5:  min_w  w'Σw   s.t.  1'w = 1  [+ constraints]

        Args:
            mu: Annualised expected returns, shape (n,).
            sigma: Annualised covariance matrix, shape (n, n).
            constraints: Solver constraints (FR10).
            prev_weights: Reference weights for turnover cap; ignored when None.
            asset_ids: UUID → column mapping for per-asset bounds; ignored when None.
            assets: Asset metadata for explanation generation; optional.

        Returns:
            SolverResult with is_feasible=False when the problem is infeasible.
        """
        feasible, reason = self.check_feasibility(
            mu, target_return=None, rf=None, constraints=constraints
        )
        if not feasible:
            return _infeasible_result(reason)

        cons = self._build_scipy_constraints(mu, constraints, None, prev_weights)
        bounds = self._build_bounds(len(mu), constraints, asset_ids)

        sol = minimize(
            fun=_objective_variance,
            x0=_equal_weights(len(mu)),
            args=(sigma,),
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"ftol": _SOLVER_FTOL, "maxiter": _SOLVER_MAXITER},
        )

        if not sol.success:
            return _infeasible_result(f"Solver did not converge: {sol.message}")

        return self._build_result(
            sol.x, mu, sigma,
            rf=None, constraints=constraints, assets=assets,
            solver_meta={"message": sol.message, "nit": int(sol.nit)},
        )

    def optimize_frontier_point(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        target_return: float,
        constraints: OptimizationConstraints,
        prev_weights: np.ndarray | None = None,
        asset_ids: list[UUID] | None = None,
        assets: list[Asset] | None = None,
    ) -> SolverResult:
        """Minimize variance for a specific target expected return.

        DATA-MODEL.md §4.5:  min_w  w'Σw   s.t.  w'μ = R*, 1'w = 1

        Returns INFEASIBLE when target_return > max(μ) under long-only (FR8).
        """
        feasible, reason = self.check_feasibility(
            mu, target_return=target_return, rf=None, constraints=constraints
        )
        if not feasible:
            return _infeasible_result(reason)

        cons = self._build_scipy_constraints(mu, constraints, target_return, prev_weights)
        bounds = self._build_bounds(len(mu), constraints, asset_ids)

        sol = minimize(
            fun=_objective_variance,
            x0=_equal_weights(len(mu)),
            args=(sigma,),
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"ftol": _SOLVER_FTOL, "maxiter": _SOLVER_MAXITER},
        )

        if not sol.success:
            return _infeasible_result(
                f"No feasible solution at target return {target_return * 100:.2f}%"
                f" given the active constraints: {sol.message}"
            )

        return self._build_result(
            sol.x, mu, sigma,
            rf=None, constraints=constraints, assets=assets,
            solver_meta={"message": sol.message, "nit": int(sol.nit)},
        )

    def optimize_tangency(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        rf: float,
        constraints: OptimizationConstraints,
        prev_weights: np.ndarray | None = None,
        asset_ids: list[UUID] | None = None,
        assets: list[Asset] | None = None,
    ) -> SolverResult:
        """Maximize Sharpe ratio (μ_p − rf) / σ_p.

        DATA-MODEL.md §4.5:  max_w  (w'μ − rf) / √(w'Σw)   s.t.  1'w = 1

        Returns INFEASIBLE when max(μ) ≤ rf (FR9, DATA-MODEL §4.5).
        """
        feasible, reason = self.check_feasibility(
            mu, target_return=None, rf=rf, constraints=constraints
        )
        if not feasible:
            return _infeasible_result(reason)

        cons = self._build_scipy_constraints(mu, constraints, None, prev_weights)
        bounds = self._build_bounds(len(mu), constraints, asset_ids)

        sol = minimize(
            fun=_objective_neg_sharpe,
            x0=_equal_weights(len(mu)),
            args=(mu, sigma, rf),
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"ftol": _SOLVER_FTOL, "maxiter": _SOLVER_MAXITER},
        )

        if not sol.success:
            return _infeasible_result(f"Solver did not converge: {sol.message}")

        return self._build_result(
            sol.x, mu, sigma,
            rf=rf, constraints=constraints, assets=assets,
            solver_meta={"message": sol.message, "nit": int(sol.nit)},
        )

    def compute_efficient_frontier(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        constraints: OptimizationConstraints,
        n_points: int = 20,
        prev_weights: np.ndarray | None = None,
        asset_ids: list[UUID] | None = None,
        assets: list[Asset] | None = None,
    ) -> list[SolverResult]:
        """Generate n_points frontier portfolios from MVP to max-return portfolio.

        The target-return grid spans [μ_MVP, max(μ)].  Infeasible points (e.g.
        those blocked by turnover or concentration caps) are included in the
        list with is_feasible=False so callers can identify the boundary (FR8).

        Returns a single-element list containing the MVP when the grid degenerates
        (all assets share the same expected return).
        """
        mvp = self.optimize_mvp(mu, sigma, constraints, prev_weights, asset_ids, assets)
        if not mvp.is_feasible or mvp.exp_return is None:
            return [mvp]

        lower = mvp.exp_return
        upper = float(np.max(mu))

        if upper <= lower + _WEIGHT_TOL:
            return [mvp]

        targets = np.linspace(lower, upper, n_points)
        return [
            self.optimize_frontier_point(
                mu, sigma, float(t), constraints, prev_weights, asset_ids, assets
            )
            for t in targets
        ]

    def compute_risk_decomposition(
        self,
        weights: np.ndarray,
        sigma: np.ndarray,
    ) -> RiskDecompositionResult:
        """Compute MCR, CRC, and PRC for each asset (DATA-MODEL.md §4.7).

        Returns zero arrays when portfolio volatility is effectively zero
        (e.g. a single-asset portfolio held as cash).
        """
        variance = float(weights @ sigma @ weights)
        stdev = float(np.sqrt(max(variance, 0.0)))

        if stdev < _WEIGHT_TOL:
            zeros = np.zeros(len(weights))
            return RiskDecompositionResult(mcr=zeros, crc=zeros, prc=zeros)

        g = sigma @ weights        # shape (n,): Σw
        mcr = g / stdev            # MCR_i = g_i / σ_p
        crc = weights * mcr        # CRC_i = w_i · MCR_i
        prc = crc / stdev          # PRC_i = CRC_i / σ_p

        return RiskDecompositionResult(mcr=mcr, crc=crc, prc=prc)

    def check_feasibility(
        self,
        mu: np.ndarray,
        target_return: float | None,
        rf: float | None,
        constraints: OptimizationConstraints,
    ) -> tuple[bool, str | None]:
        """Check necessary conditions for feasibility before calling the solver.

        Returns (True, None) when no obvious infeasibility is detected.
        Returns (False, plain-language reason) otherwise (FR11).

        Checks performed:
          1. Tangency: max(μ) ≤ rf  →  no asset beats the risk-free rate.
          2. Long-only frontier point: target_return > max(μ)  →  unreachable.
          3. Per-asset bounds: sum of minimums > 1.0  →  full investment impossible.
        """
        max_mu = float(np.max(mu))

        if rf is not None and max_mu <= rf:
            return False, (
                "No asset has expected return exceeding the risk-free rate; "
                "tangency portfolio undefined."
            )

        if target_return is not None and constraints.long_only:
            if target_return > max_mu + _WEIGHT_TOL:
                return False, (
                    f"Target return of {target_return * 100:.2f}% exceeds the maximum "
                    f"achievable return of {max_mu * 100:.2f}% under long-only constraints."
                )

        if constraints.asset_bounds:
            total_min = sum(b.min_weight for b in constraints.asset_bounds)
            if total_min > 1.0 + _WEIGHT_TOL:
                return False, (
                    f"Sum of minimum asset bounds ({total_min:.4f}) exceeds 1.0; "
                    "full investment constraint cannot be satisfied."
                )

        return True, None

    def _generate_explanation(
        self,
        result: SolverResult,
        weights: np.ndarray,
        assets: list[Asset] | None,
        constraints: OptimizationConstraints,
    ) -> str:
        """Plain-language explanation with concrete numbers (FR14).

        Covers: top holdings, portfolio return / volatility, Sharpe, HHI vs
        equal-weight effective N, and active constraints.
        """
        if not result.is_feasible:
            return f"Optimization infeasible: {result.infeasibility_reason}"

        n = len(weights)
        parts: list[str] = []

        # Top holdings (up to 5 by absolute weight)
        top_idx = np.argsort(np.abs(weights))[::-1][:5]
        significant = [i for i in top_idx if abs(weights[i]) > _WEIGHT_TOL]
        if significant:
            if assets and len(assets) == n:
                labels = [f"{assets[i].ticker} {weights[i] * 100:.1f}%" for i in significant]
            else:
                labels = [f"Asset {i} {weights[i] * 100:.1f}%" for i in significant]
            parts.append(f"Top holdings: {', '.join(labels)}.")

        # Portfolio return and volatility
        if result.exp_return is not None and result.stdev is not None:
            parts.append(
                f"Expected return {result.exp_return * 100:.2f}%, "
                f"volatility {result.stdev * 100:.2f}%."
            )

        # Sharpe ratio
        if result.sharpe is not None:
            parts.append(f"Sharpe ratio {result.sharpe:.3f}.")

        # Concentration vs equal-weight benchmark
        if result.hhi is not None and result.effective_n is not None:
            parts.append(
                f"HHI {result.hhi:.4f}, effective N {result.effective_n:.1f} "
                f"(equal-weight would give N = {n})."
            )

        # Active constraints
        constraint_desc = _describe_constraints(constraints)
        if constraint_desc:
            parts.append(f"Constraints applied: {constraint_desc}.")

        return " ".join(parts)

    # ─────────────────────────────────────────────────────────────────── #
    # Constraint and bounds builders                                       #
    # ─────────────────────────────────────────────────────────────────── #

    def _build_scipy_constraints(
        self,
        mu: np.ndarray,
        constraints: OptimizationConstraints,
        target_return: float | None,
        prev_weights: np.ndarray | None,
    ) -> list[dict]:
        """Translate OptimizationConstraints into scipy constraint dicts."""
        cons: list[dict] = []

        # Full investment: Σwᵢ = 1  (always required)
        cons.append({"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0})

        # Target return: w'μ = R*
        if target_return is not None:
            r_star = float(target_return)
            cons.append({"type": "eq", "fun": lambda w: float(np.dot(w, mu)) - r_star})

        # Leverage cap: Σ|wᵢ| ≤ L
        if constraints.leverage_cap is not None:
            cap = float(constraints.leverage_cap)
            cons.append({"type": "ineq", "fun": lambda w: cap - float(np.sum(np.abs(w)))})

        # Concentration cap: |wᵢ| ≤ c  for every asset i
        if constraints.concentration_cap is not None:
            c = float(constraints.concentration_cap)
            for i in range(len(mu)):
                cons.append({"type": "ineq", "fun": lambda w, i=i: c - abs(float(w[i]))})

        # Turnover cap: Σ|wᵢ − wᵢ_prev| ≤ T
        if constraints.turnover_cap is not None:
            if prev_weights is not None:
                T = float(constraints.turnover_cap)
                w_prev = prev_weights.copy()
                cons.append(
                    {"type": "ineq", "fun": lambda w: T - float(np.sum(np.abs(w - w_prev)))}
                )
            else:
                logger.warning(
                    "turnover_cap is set but prev_weights is None; "
                    "turnover constraint ignored (FR10)."
                )

        return cons

    def _build_bounds(
        self,
        n: int,
        constraints: OptimizationConstraints,
        asset_ids: list[UUID] | None = None,
    ) -> list[tuple[float, float]]:
        """Build per-asset (lower, upper) bounds for SLSQP.

        Base bounds come from long_only.  Per-asset overrides from
        constraints.asset_bounds are applied when asset_ids is provided;
        silently omitted with a warning otherwise.
        """
        base_lower = 0.0 if constraints.long_only else -1.0
        bounds: list[tuple[float, float]] = [(base_lower, 1.0)] * n

        if constraints.asset_bounds:
            if asset_ids is None:
                logger.warning(
                    "asset_bounds are set but asset_ids is None; "
                    "per-asset bounds ignored."
                )
                return bounds

            bound_map: dict[UUID, AssetBound] = {
                b.asset_id: b for b in constraints.asset_bounds
            }
            bounds = list(bounds)   # make mutable copy
            for i, aid in enumerate(asset_ids):
                if aid in bound_map:
                    ab = bound_map[aid]
                    bounds[i] = (ab.min_weight, ab.max_weight)

        return bounds

    # ─────────────────────────────────────────────────────────────────── #
    # Result assembly                                                      #
    # ─────────────────────────────────────────────────────────────────── #

    def _build_result(
        self,
        raw_weights: np.ndarray,
        mu: np.ndarray,
        sigma: np.ndarray,
        rf: float | None,
        constraints: OptimizationConstraints,
        assets: list[Asset] | None,
        solver_meta: dict[str, object] | None,
    ) -> SolverResult:
        """Compute portfolio statistics and assemble a SolverResult."""
        weights = _clean_weights(raw_weights, constraints.long_only)

        exp_return = float(np.dot(weights, mu))
        variance = float(weights @ sigma @ weights)
        stdev = float(np.sqrt(max(variance, 0.0)))
        hhi = float(np.sum(weights**2))
        effective_n = 1.0 / hhi if hhi > _WEIGHT_TOL else float("inf")
        sharpe = (
            (exp_return - rf) / stdev
            if rf is not None and stdev > _WEIGHT_TOL
            else None
        )

        # Build partial result to pass to the explanation generator,
        # then replace the empty explanation with the real one.
        partial = SolverResult(
            weights=weights,
            exp_return=exp_return,
            variance=variance,
            stdev=stdev,
            sharpe=sharpe,
            hhi=hhi,
            effective_n=effective_n,
            explanation="",
            is_feasible=True,
            infeasibility_reason=None,
            solver_meta=solver_meta,
        )
        explanation = self._generate_explanation(partial, weights, assets, constraints)
        return replace(partial, explanation=explanation)


# ─────────────────────────────────────────────────────────────────────────── #
# Module-level helpers (no self state needed)                                  #
# ─────────────────────────────────────────────────────────────────────────── #


def _infeasible_result(reason: str | None) -> SolverResult:
    """Return a fully populated infeasible SolverResult."""
    return SolverResult(
        weights=None,
        exp_return=None,
        variance=None,
        stdev=None,
        sharpe=None,
        hhi=None,
        effective_n=None,
        explanation=f"Optimization infeasible: {reason}",
        is_feasible=False,
        infeasibility_reason=reason,
        solver_meta=None,
    )


def _equal_weights(n: int) -> np.ndarray:
    """Equal-weight starting point — always feasible under full-investment."""
    return np.full(n, 1.0 / n)


def _clean_weights(raw: np.ndarray, long_only: bool) -> np.ndarray:
    """Remove sub-tolerance rounding noise and renormalise to sum = 1.

    Long-only: negative rounding artefacts (e.g. -1e-16) are zeroed.
    Short-allowed: only values strictly within ±_WEIGHT_TOL are zeroed.
    Renormalisation preserves the full-investment constraint after cleaning.
    """
    if long_only:
        cleaned = np.where(raw < _WEIGHT_TOL, 0.0, raw)
    else:
        cleaned = np.where(np.abs(raw) < _WEIGHT_TOL, 0.0, raw)

    total = float(np.sum(cleaned))
    if abs(total) > _WEIGHT_TOL:
        cleaned = cleaned / total
    return cleaned


def _describe_constraints(constraints: OptimizationConstraints) -> str:
    """Summarise active constraints as a human-readable string."""
    parts: list[str] = []
    if constraints.long_only:
        parts.append("long-only")
    if constraints.asset_bounds:
        parts.append(f"{len(constraints.asset_bounds)} per-asset bounds")
    if constraints.leverage_cap is not None:
        parts.append(f"leverage ≤ {constraints.leverage_cap:.0%}")
    if constraints.concentration_cap is not None:
        parts.append(f"concentration ≤ {constraints.concentration_cap:.0%}")
    if constraints.turnover_cap is not None:
        parts.append(f"turnover ≤ {constraints.turnover_cap:.0%}")
    return ", ".join(parts)


def _objective_variance(w: np.ndarray, sigma: np.ndarray) -> float:
    """w'Σw — portfolio variance (minimise)."""
    return float(w @ sigma @ w)


def _objective_neg_sharpe(
    w: np.ndarray, mu: np.ndarray, sigma: np.ndarray, rf: float
) -> float:
    """−(w'μ − rf) / √(w'Σw) — negative Sharpe ratio (minimise)."""
    excess = float(np.dot(w, mu)) - rf
    variance = float(w @ sigma @ w)
    stdev = float(np.sqrt(max(variance, 1e-12)))   # floor avoids divide-by-zero
    return -excess / stdev
