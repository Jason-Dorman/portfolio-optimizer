"""Unit tests for OptimizationService.

All numeric assertions derive from DATA-MODEL.md §4.5–4.7 closed-form solutions
so that the tests function as an executable specification.

Closed-form references used:
  MVP (uncorrelated assets):  w_i ∝ 1/σ_i²
  Tangency (uncorrelated):    w_i ∝ (μ_i − rf) / σ_i²
  Risk decomposition identities:  Σ CRC_i = σ_p,  Σ PRC_i = 1

Test layout:
  - Fixtures
  - check_feasibility
  - optimize_mvp
  - optimize_frontier_point
  - optimize_tangency
  - compute_efficient_frontier
  - compute_risk_decomposition
  - _generate_explanation
  - Edge cases
"""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography
from src.domain.models.optimization import AssetBound, OptimizationConstraints
from src.domain.services.optimization import OptimizationService, RiskDecompositionResult


# ═══════════════════════════════════════════════════════════════════════════ #
# Helpers                                                                      #
# ═══════════════════════════════════════════════════════════════════════════ #


def _asset(ticker: str, sector: str | None = None) -> Asset:
    return Asset.create(
        ticker=ticker,
        name=f"Test {ticker}",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
        sector=sector,
    )


# ═══════════════════════════════════════════════════════════════════════════ #
# Fixtures                                                                     #
# ═══════════════════════════════════════════════════════════════════════════ #


@pytest.fixture
def svc() -> OptimizationService:
    return OptimizationService()


@pytest.fixture
def long_only() -> OptimizationConstraints:
    return OptimizationConstraints.long_only_unconstrained()


# Two-asset universe — equal variance, uncorrelated
# MVP closed-form: w* = [0.5, 0.5]
@pytest.fixture
def mu2() -> np.ndarray:
    return np.array([0.10, 0.15])


@pytest.fixture
def sigma2_equal_var() -> np.ndarray:
    """Diagonal covariance: σ₁ = σ₂ = 20% (0.04 variance each)."""
    return np.diag([0.04, 0.04])


@pytest.fixture
def sigma2_unequal_var() -> np.ndarray:
    """Diagonal covariance: σ₁ = 10% (var 0.01), σ₂ = 30% (var 0.09)."""
    return np.diag([0.01, 0.09])


# Three-asset universe — uncorrelated, used for concentration cap tests
@pytest.fixture
def mu3() -> np.ndarray:
    return np.array([0.08, 0.12, 0.16])


@pytest.fixture
def sigma3_unequal_var() -> np.ndarray:
    """σ₁ = 10%, σ₂ = 30%, σ₃ = 30% (all uncorrelated)."""
    return np.diag([0.01, 0.09, 0.09])


# ═══════════════════════════════════════════════════════════════════════════ #
# check_feasibility                                                            #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestCheckFeasibility:
    def test_returns_true_when_no_issues(
        self, svc: OptimizationService, mu2: np.ndarray, long_only: OptimizationConstraints
    ) -> None:
        ok, reason = svc.check_feasibility(mu2, target_return=None, rf=None, constraints=long_only)
        assert ok is True
        assert reason is None

    def test_tangency_infeasible_all_mu_below_rf(
        self, svc: OptimizationService, mu2: np.ndarray, long_only: OptimizationConstraints
    ) -> None:
        # rf = 0.20 > max(mu) = 0.15
        ok, reason = svc.check_feasibility(mu2, target_return=None, rf=0.20, constraints=long_only)
        assert ok is False
        assert reason is not None
        assert "tangency portfolio undefined" in reason

    def test_tangency_infeasible_all_mu_equal_rf(
        self, svc: OptimizationService, long_only: OptimizationConstraints
    ) -> None:
        mu = np.array([0.05, 0.05])
        ok, reason = svc.check_feasibility(mu, target_return=None, rf=0.05, constraints=long_only)
        assert ok is False
        assert reason is not None

    def test_frontier_infeasible_target_exceeds_max_mu_long_only(
        self, svc: OptimizationService, mu2: np.ndarray, long_only: OptimizationConstraints
    ) -> None:
        # target = 0.20 > max(mu) = 0.15
        ok, reason = svc.check_feasibility(
            mu2, target_return=0.20, rf=None, constraints=long_only
        )
        assert ok is False
        assert reason is not None
        assert "20.00%" in reason
        assert "15.00%" in reason

    def test_frontier_feasible_at_max_mu(
        self, svc: OptimizationService, mu2: np.ndarray, long_only: OptimizationConstraints
    ) -> None:
        ok, reason = svc.check_feasibility(mu2, target_return=0.15, rf=None, constraints=long_only)
        assert ok is True

    def test_frontier_feasible_short_allowed_above_max_mu(
        self, svc: OptimizationService, mu2: np.ndarray
    ) -> None:
        # Long-short portfolios can exceed max single-asset return via leverage.
        # The pre-solver check must not reject this case.
        constraints = OptimizationConstraints(long_only=False)
        ok, _ = svc.check_feasibility(mu2, target_return=0.25, rf=None, constraints=constraints)
        assert ok is True

    def test_asset_bounds_sum_exceeds_one_is_infeasible(
        self, svc: OptimizationService, mu2: np.ndarray, long_only: OptimizationConstraints
    ) -> None:
        ids = [uuid4(), uuid4()]
        constraints = OptimizationConstraints(
            long_only=True,
            asset_bounds=[
                AssetBound(asset_id=ids[0], min_weight=0.7, max_weight=1.0),
                AssetBound(asset_id=ids[1], min_weight=0.7, max_weight=1.0),
            ],
        )
        ok, reason = svc.check_feasibility(mu2, target_return=None, rf=None, constraints=constraints)
        assert ok is False
        assert reason is not None
        assert "1.4000" in reason


# ═══════════════════════════════════════════════════════════════════════════ #
# optimize_mvp                                                                 #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestOptimizeMvp:
    def test_weights_sum_to_one(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert abs(np.sum(result.weights) - 1.0) < 1e-6

    def test_equal_variance_uncorrelated_gives_equal_weights(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        # MVP closed-form: w ∝ 1/σᵢ² → equal weights when σ₁ = σ₂
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert np.allclose(result.weights, [0.5, 0.5], atol=1e-4)

    def test_unequal_variance_concentrates_in_lower_vol_asset(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_unequal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        # σ₁=10%, σ₂=30% uncorrelated → w₁ = 1/0.01 / (1/0.01 + 1/0.09) = 90%
        result = svc.optimize_mvp(mu2, sigma2_unequal_var, long_only)
        assert result.is_feasible
        assert np.allclose(result.weights, [0.9, 0.1], atol=1e-4)

    def test_long_only_all_weights_nonnegative(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert np.all(result.weights >= -1e-8)

    def test_variance_equals_stdev_squared(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert abs(result.stdev**2 - result.variance) < 1e-8

    def test_hhi_and_effective_n_consistent(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert abs(result.effective_n - 1.0 / result.hhi) < 1e-6

    def test_sharpe_is_none_for_mvp(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert result.sharpe is None

    def test_concentration_cap_respected(
        self,
        svc: OptimizationService,
        mu3: np.ndarray,
        sigma3_unequal_var: np.ndarray,
    ) -> None:
        # Unconstrained MVP puts ~82% in asset 0.  Cap at 60% forces redistribution.
        constraints = OptimizationConstraints(long_only=True, concentration_cap=0.60)
        result = svc.optimize_mvp(mu3, sigma3_unequal_var, constraints)
        assert result.is_feasible
        assert np.all(result.weights <= 0.60 + 1e-4)
        assert np.allclose(result.weights, [0.60, 0.20, 0.20], atol=1e-3)

    def test_turnover_cap_limits_deviation_from_prev(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_unequal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        # Unconstrained MVP: [0.9, 0.1].  Starting from [0.5, 0.5] with cap=0.1
        # the solver can shift at most 0.05 per asset → capped at [0.55, 0.45].
        prev = np.array([0.5, 0.5])
        constraints = OptimizationConstraints(long_only=True, turnover_cap=0.10)
        result = svc.optimize_mvp(mu2, sigma2_unequal_var, constraints, prev_weights=prev)
        assert result.is_feasible
        turnover = float(np.sum(np.abs(result.weights - prev)))
        assert turnover <= 0.10 + 1e-4

    def test_explanation_is_non_empty_string(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ═══════════════════════════════════════════════════════════════════════════ #
# optimize_frontier_point                                                      #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestOptimizeFrontierPoint:
    def test_achieves_target_return(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        target = 0.12
        result = svc.optimize_frontier_point(mu2, sigma2_equal_var, target, long_only)
        assert result.is_feasible
        assert abs(result.exp_return - target) < 1e-5

    def test_weights_sum_to_one(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_frontier_point(mu2, sigma2_equal_var, 0.12, long_only)
        assert result.is_feasible
        assert abs(np.sum(result.weights) - 1.0) < 1e-6

    def test_higher_target_yields_higher_variance(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        r_low = svc.optimize_frontier_point(mu2, sigma2_equal_var, 0.11, long_only)
        r_high = svc.optimize_frontier_point(mu2, sigma2_equal_var, 0.14, long_only)
        assert r_low.is_feasible and r_high.is_feasible
        assert r_low.variance <= r_high.variance + 1e-8

    def test_infeasible_when_target_exceeds_max_mu_long_only(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_frontier_point(mu2, sigma2_equal_var, 0.20, long_only)
        assert not result.is_feasible
        assert "20.00%" in result.infeasibility_reason
        assert "15.00%" in result.infeasibility_reason

    def test_infeasibility_reason_stored_in_explanation(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_frontier_point(mu2, sigma2_equal_var, 0.20, long_only)
        assert not result.is_feasible
        assert result.infeasibility_reason in result.explanation


# ═══════════════════════════════════════════════════════════════════════════ #
# optimize_tangency                                                            #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestOptimizeTangency:
    def test_uncorrelated_equal_variance_weights(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        # Tangency: w ∝ σ⁻¹(μ − rf) = (1/0.04)[0.05, 0.10] ∝ [1, 2] → [1/3, 2/3]
        rf = 0.05
        result = svc.optimize_tangency(mu2, sigma2_equal_var, rf, long_only)
        assert result.is_feasible
        assert np.allclose(result.weights, [1.0 / 3.0, 2.0 / 3.0], atol=1e-3)

    def test_weights_sum_to_one(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_tangency(mu2, sigma2_equal_var, 0.05, long_only)
        assert result.is_feasible
        assert abs(np.sum(result.weights) - 1.0) < 1e-6

    def test_sharpe_is_populated(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_tangency(mu2, sigma2_equal_var, 0.05, long_only)
        assert result.is_feasible
        assert result.sharpe is not None
        # Manually verify Sharpe: (μ_p − rf) / σ_p
        expected_sharpe = (result.exp_return - 0.05) / result.stdev
        assert abs(result.sharpe - expected_sharpe) < 1e-6

    def test_tangency_sharpe_exceeds_mvp_sharpe(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        rf = 0.05
        tangency = svc.optimize_tangency(mu2, sigma2_equal_var, rf, long_only)
        mvp = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert tangency.is_feasible and mvp.is_feasible

        mvp_sharpe = (mvp.exp_return - rf) / mvp.stdev
        assert tangency.sharpe >= mvp_sharpe - 1e-4

    def test_all_mu_below_rf_returns_infeasible(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_tangency(mu2, sigma2_equal_var, rf=0.20, constraints=long_only)
        assert not result.is_feasible
        assert "tangency portfolio undefined" in result.infeasibility_reason

    def test_all_mu_equal_rf_returns_infeasible(
        self,
        svc: OptimizationService,
        long_only: OptimizationConstraints,
    ) -> None:
        mu = np.array([0.05, 0.05])
        sigma = np.diag([0.04, 0.04])
        result = svc.optimize_tangency(mu, sigma, rf=0.05, constraints=long_only)
        assert not result.is_feasible


# ═══════════════════════════════════════════════════════════════════════════ #
# compute_efficient_frontier                                                   #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeEfficientFrontier:
    def test_returns_n_points(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        frontier = svc.compute_efficient_frontier(mu2, sigma2_equal_var, long_only, n_points=10)
        assert len(frontier) == 10

    def test_first_point_is_mvp(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        frontier = svc.compute_efficient_frontier(mu2, sigma2_equal_var, long_only, n_points=5)
        mvp = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert frontier[0].is_feasible
        assert abs(frontier[0].variance - mvp.variance) < 1e-6

    def test_variance_non_decreasing_along_frontier(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        frontier = svc.compute_efficient_frontier(mu2, sigma2_equal_var, long_only, n_points=8)
        feasible_variances = [p.variance for p in frontier if p.is_feasible]
        # Variance must be monotonically non-decreasing as return increases
        for i in range(1, len(feasible_variances)):
            assert feasible_variances[i] >= feasible_variances[i - 1] - 1e-6

    def test_return_monotonically_increasing(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        frontier = svc.compute_efficient_frontier(mu2, sigma2_equal_var, long_only, n_points=8)
        returns = [p.exp_return for p in frontier if p.is_feasible]
        for i in range(1, len(returns)):
            assert returns[i] >= returns[i - 1] - 1e-6

    def test_degenerate_case_returns_mvp_only(
        self,
        svc: OptimizationService,
        long_only: OptimizationConstraints,
    ) -> None:
        # All assets have the same expected return — no frontier to trace
        mu = np.array([0.10, 0.10, 0.10])
        sigma = np.diag([0.04, 0.09, 0.16])
        frontier = svc.compute_efficient_frontier(mu, sigma, long_only, n_points=10)
        assert len(frontier) == 1


# ═══════════════════════════════════════════════════════════════════════════ #
# compute_risk_decomposition                                                   #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestComputeRiskDecomposition:
    @pytest.fixture
    def two_asset_setup(
        self,
        sigma2_unequal_var: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        # MVP weights for σ = diag([0.01, 0.09])
        w = np.array([0.9, 0.1])
        return w, sigma2_unequal_var

    def test_crc_sums_to_portfolio_volatility(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        sigma_p = float(np.sqrt(w @ sigma @ w))
        assert abs(float(np.sum(decomp.crc)) - sigma_p) < 1e-8

    def test_prc_sums_to_one(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        assert abs(float(np.sum(decomp.prc)) - 1.0) < 1e-8

    def test_mcr_formula(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        # MCR_i = (Σw)_i / σ_p
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        g = sigma @ w
        sigma_p = float(np.sqrt(w @ sigma @ w))
        expected_mcr = g / sigma_p
        assert np.allclose(decomp.mcr, expected_mcr, atol=1e-10)

    def test_crc_is_weight_times_mcr(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        assert np.allclose(decomp.crc, w * decomp.mcr, atol=1e-10)

    def test_prc_is_crc_over_sigma_p(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        sigma_p = float(np.sqrt(w @ sigma @ w))
        assert np.allclose(decomp.prc, decomp.crc / sigma_p, atol=1e-10)

    def test_output_shape_matches_weights(
        self,
        svc: OptimizationService,
        two_asset_setup: tuple[np.ndarray, np.ndarray],
    ) -> None:
        w, sigma = two_asset_setup
        decomp = svc.compute_risk_decomposition(w, sigma)
        assert decomp.mcr.shape == w.shape
        assert decomp.crc.shape == w.shape
        assert decomp.prc.shape == w.shape

    def test_zero_volatility_returns_zero_arrays(
        self, svc: OptimizationService
    ) -> None:
        # Zero covariance matrix → zero portfolio volatility
        w = np.array([0.5, 0.5])
        sigma = np.zeros((2, 2))
        decomp = svc.compute_risk_decomposition(w, sigma)
        assert np.all(decomp.mcr == 0.0)
        assert np.all(decomp.crc == 0.0)
        assert np.all(decomp.prc == 0.0)

    def test_identities_hold_for_correlated_matrix(
        self, svc: OptimizationService
    ) -> None:
        # 3-asset correlated covariance
        sigma = np.array([
            [0.04, 0.010, 0.005],
            [0.010, 0.09, 0.020],
            [0.005, 0.020, 0.16],
        ])
        w = np.array([0.5, 0.3, 0.2])
        decomp = svc.compute_risk_decomposition(w, sigma)

        sigma_p = float(np.sqrt(w @ sigma @ w))
        assert abs(float(np.sum(decomp.crc)) - sigma_p) < 1e-8
        assert abs(float(np.sum(decomp.prc)) - 1.0) < 1e-8


# ═══════════════════════════════════════════════════════════════════════════ #
# _generate_explanation                                                        #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestGenerateExplanation:
    def test_includes_ticker_when_assets_provided(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        assets = [_asset("SPY"), _asset("AGG")]
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only, assets=assets)
        assert "SPY" in result.explanation
        assert "AGG" in result.explanation

    def test_fallback_to_asset_index_when_no_assets(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert result.is_feasible
        assert "Asset 0" in result.explanation or "Asset 1" in result.explanation

    def test_includes_return_and_volatility(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_mvp(mu2, sigma2_equal_var, long_only)
        assert "Expected return" in result.explanation
        assert "volatility" in result.explanation

    def test_includes_sharpe_for_tangency(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_tangency(mu2, sigma2_equal_var, rf=0.05, constraints=long_only)
        assert "Sharpe" in result.explanation

    def test_includes_constraint_description(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
    ) -> None:
        constraints = OptimizationConstraints(long_only=True, concentration_cap=0.70)
        result = svc.optimize_mvp(mu2, sigma2_equal_var, constraints)
        assert "long-only" in result.explanation
        assert "concentration" in result.explanation

    def test_infeasible_result_explanation_contains_reason(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        result = svc.optimize_tangency(mu2, sigma2_equal_var, rf=0.20, constraints=long_only)
        assert not result.is_feasible
        assert result.infeasibility_reason in result.explanation


# ═══════════════════════════════════════════════════════════════════════════ #
# Edge cases                                                                   #
# ═══════════════════════════════════════════════════════════════════════════ #


class TestEdgeCases:
    def test_single_asset_mvp_is_fully_invested(
        self, svc: OptimizationService, long_only: OptimizationConstraints
    ) -> None:
        mu = np.array([0.10])
        sigma = np.array([[0.04]])
        result = svc.optimize_mvp(mu, sigma, long_only)
        assert result.is_feasible
        assert np.allclose(result.weights, [1.0], atol=1e-6)

    def test_single_asset_tangency(
        self, svc: OptimizationService, long_only: OptimizationConstraints
    ) -> None:
        mu = np.array([0.10])
        sigma = np.array([[0.04]])
        result = svc.optimize_tangency(mu, sigma, rf=0.05, constraints=long_only)
        assert result.is_feasible
        assert np.allclose(result.weights, [1.0], atol=1e-6)

    def test_turnover_ignored_when_prev_weights_none(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_unequal_var: np.ndarray,
    ) -> None:
        # turnover_cap set but no prev_weights → constraint is skipped, no error raised
        constraints = OptimizationConstraints(long_only=True, turnover_cap=0.05)
        result = svc.optimize_mvp(mu2, sigma2_unequal_var, constraints, prev_weights=None)
        assert result.is_feasible
        assert np.allclose(result.weights, [0.9, 0.1], atol=1e-4)

    def test_frontier_with_only_two_points(
        self,
        svc: OptimizationService,
        mu2: np.ndarray,
        sigma2_equal_var: np.ndarray,
        long_only: OptimizationConstraints,
    ) -> None:
        frontier = svc.compute_efficient_frontier(mu2, sigma2_equal_var, long_only, n_points=2)
        assert len(frontier) == 2
        assert all(p.is_feasible for p in frontier)

    def test_risk_decomp_single_asset(self, svc: OptimizationService) -> None:
        w = np.array([1.0])
        sigma = np.array([[0.04]])
        decomp = svc.compute_risk_decomposition(w, sigma)
        # Single asset: CRC = σ_p = 0.2, PRC = 1.0
        assert abs(float(decomp.crc[0]) - 0.2) < 1e-6
        assert abs(float(decomp.prc[0]) - 1.0) < 1e-6
