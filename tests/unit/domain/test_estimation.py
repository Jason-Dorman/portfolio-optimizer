"""Unit tests for EstimationService.

Verifies all formulas against DATA-MODEL.md sections 4.1–4.5.
Each test class corresponds to one public method on EstimationService.
"""

import numpy as np
import pandas as pd
import pytest

from src.domain.models.enums import CovMethod, Estimator, ReturnType
from src.domain.services.estimation import EstimationService


@pytest.fixture
def service() -> EstimationService:
    return EstimationService()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def prices_two_assets() -> pd.DataFrame:
    """Three price observations for two assets."""
    return pd.DataFrame(
        {"A": [100.0, 110.0, 99.0], "B": [200.0, 180.0, 198.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )


@pytest.fixture
def returns_two_assets() -> pd.DataFrame:
    """Two-period return series for two assets (independent returns for non-singular cov)."""
    return pd.DataFrame(
        {"A": [0.01, 0.03], "B": [0.02, -0.01]},
        index=pd.date_range("2024-01-02", periods=2, freq="D"),
    )


# ---------------------------------------------------------------------------
# §4.1 compute_returns
# ---------------------------------------------------------------------------


class TestComputeReturns:
    def test_simple_return_formula_period_one(self, service, prices_two_assets):
        """r = P_t / P_{t-1} - 1  (DATA-MODEL.md §4.1)."""
        result = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        assert result["A"].iloc[0] == pytest.approx(110.0 / 100.0 - 1)
        assert result["B"].iloc[0] == pytest.approx(180.0 / 200.0 - 1)

    def test_simple_return_formula_period_two(self, service, prices_two_assets):
        result = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        assert result["A"].iloc[1] == pytest.approx(99.0 / 110.0 - 1)
        assert result["B"].iloc[1] == pytest.approx(198.0 / 180.0 - 1)

    def test_log_return_formula_period_one(self, service, prices_two_assets):
        """r = ln(P_t / P_{t-1})  (DATA-MODEL.md §4.1)."""
        result = service.compute_returns(prices_two_assets, ReturnType.LOG)
        assert result["A"].iloc[0] == pytest.approx(np.log(110.0 / 100.0))
        assert result["B"].iloc[0] == pytest.approx(np.log(180.0 / 200.0))

    def test_log_return_formula_period_two(self, service, prices_two_assets):
        result = service.compute_returns(prices_two_assets, ReturnType.LOG)
        assert result["A"].iloc[1] == pytest.approx(np.log(99.0 / 110.0))

    def test_first_nan_row_is_dropped(self, service, prices_two_assets):
        """Return DataFrame should have n-1 rows (first period produces NaN)."""
        result = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        assert len(result) == len(prices_two_assets) - 1

    def test_column_names_preserved(self, service, prices_two_assets):
        result = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        assert list(result.columns) == ["A", "B"]

    def test_simple_and_log_returns_differ(self, service, prices_two_assets):
        """Simple and log returns are not identical (log < simple for positive returns)."""
        simple = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        log = service.compute_returns(prices_two_assets, ReturnType.LOG)
        assert not np.allclose(simple.to_numpy(), log.to_numpy())

    def test_log_return_is_less_than_simple_for_positive_price_change(
        self, service, prices_two_assets
    ):
        """ln(1+r) < r for r > 0."""
        simple = service.compute_returns(prices_two_assets, ReturnType.SIMPLE)
        log = service.compute_returns(prices_two_assets, ReturnType.LOG)
        # Asset A: first period price rises — log return < simple return
        assert log["A"].iloc[0] < simple["A"].iloc[0]


# ---------------------------------------------------------------------------
# §4.2 compute_mu
# ---------------------------------------------------------------------------


class TestComputeMu:
    def test_historical_mu_formula(self, service, returns_two_assets):
        """μ = m · mean(r)  (DATA-MODEL.md §4.2)."""
        m = 12
        result = service.compute_mu(returns_two_assets, m, Estimator.HISTORICAL)
        expected_a = 12 * returns_two_assets["A"].mean()
        expected_b = 12 * returns_two_assets["B"].mean()
        assert result[0] == pytest.approx(expected_a)
        assert result[1] == pytest.approx(expected_b)

    def test_historical_mu_annualization_factor_scales(self, service, returns_two_assets):
        """Doubling m should double μ (DATA-MODEL.md §4.2: μ = m · r̄)."""
        mu_12 = service.compute_mu(returns_two_assets, 12, Estimator.HISTORICAL)
        mu_24 = service.compute_mu(returns_two_assets, 24, Estimator.HISTORICAL)
        assert mu_24 == pytest.approx(2 * mu_12)

    def test_historical_mu_shape(self, service, returns_two_assets):
        result = service.compute_mu(returns_two_assets, 252, Estimator.HISTORICAL)
        assert result.shape == (2,)

    def test_historical_mu_known_values(self, service):
        """Verify against manually computed μ = m · mean(r)."""
        returns = pd.DataFrame({"A": [0.01, 0.03], "B": [0.02, 0.04]})
        mu = service.compute_mu(returns, 12, Estimator.HISTORICAL)
        assert mu[0] == pytest.approx(12 * 0.02)   # mean([0.01, 0.03]) = 0.02
        assert mu[1] == pytest.approx(12 * 0.03)   # mean([0.02, 0.04]) = 0.03

    def test_ewma_mu_shape_matches_historical(self, service, returns_two_assets):
        hist = service.compute_mu(returns_two_assets, 252, Estimator.HISTORICAL)
        ewma = service.compute_mu(returns_two_assets, 252, Estimator.EWMA, ewma_halflife=1)
        assert ewma.shape == hist.shape

    def test_ewma_mu_small_halflife_weights_recent_observations_more(self, service):
        """With halflife=1 (fast decay), EWMA mu is dominated by the last observation."""
        # First three periods have ~0 return; last period spikes to 10%
        returns = pd.DataFrame(
            {"A": [0.00, 0.00, 0.00, 0.10]},
            index=pd.date_range("2024-01-01", periods=4, freq="D"),
        )
        ewma = service.compute_mu(returns, 252, Estimator.EWMA, ewma_halflife=1)
        hist = service.compute_mu(returns, 252, Estimator.HISTORICAL)
        # EWMA with fast decay should be closer to 10% than the simple mean (2.5%)
        assert ewma[0] > hist[0]

    def test_ewma_mu_annualization_factor_scales(self, service, returns_two_assets):
        """Doubling m should double EWMA μ too."""
        ewma_12 = service.compute_mu(returns_two_assets, 12, Estimator.EWMA, ewma_halflife=5)
        ewma_24 = service.compute_mu(returns_two_assets, 24, Estimator.EWMA, ewma_halflife=5)
        assert ewma_24 == pytest.approx(2 * ewma_12)

    def test_shrinkage_raises_not_implemented(self, service, returns_two_assets):
        with pytest.raises(NotImplementedError):
            service.compute_mu(returns_two_assets, 252, Estimator.SHRINKAGE)


# ---------------------------------------------------------------------------
# §4.2 compute_sigma
# ---------------------------------------------------------------------------


class TestComputeSigma:
    def test_sample_cov_formula(self, service, returns_two_assets):
        """Σ = m · Cov(r)  (DATA-MODEL.md §4.2)."""
        m = 12
        result = service.compute_sigma(returns_two_assets, m, CovMethod.SAMPLE)
        expected = m * returns_two_assets.cov().to_numpy()
        assert result == pytest.approx(expected)

    def test_sample_cov_annualization_factor_scales(self, service, returns_two_assets):
        """Doubling m should double all entries of Σ."""
        sigma_12 = service.compute_sigma(returns_two_assets, 12, CovMethod.SAMPLE)
        sigma_24 = service.compute_sigma(returns_two_assets, 24, CovMethod.SAMPLE)
        assert sigma_24 == pytest.approx(2 * sigma_12)

    def test_sample_cov_shape(self, service, returns_two_assets):
        result = service.compute_sigma(returns_two_assets, 252, CovMethod.SAMPLE)
        assert result.shape == (2, 2)

    def test_sample_cov_is_symmetric(self, service, returns_two_assets):
        result = service.compute_sigma(returns_two_assets, 252, CovMethod.SAMPLE)
        assert result == pytest.approx(result.T)

    def test_sample_cov_known_values(self, service):
        """Manually verify sample covariance formula entry by entry."""
        # returns: A=[0.01, 0.03], B=[0.02, -0.01]
        # mean_A=0.02, mean_B=0.005
        # cov(A,A) = ((0.01-0.02)^2 + (0.03-0.02)^2) / 1 = 0.0002
        # cov(A,B) = ((0.01-0.02)*(0.02-0.005) + (0.03-0.02)*(-0.01-0.005)) / 1
        #          = (-0.01*0.015 + 0.01*-0.015) = -0.0003
        # cov(B,B) = (0.015^2 + (-0.015)^2) / 1 = 0.00045
        returns = pd.DataFrame({"A": [0.01, 0.03], "B": [0.02, -0.01]})
        result = service.compute_sigma(returns, 1, CovMethod.SAMPLE)
        assert result[0, 0] == pytest.approx(0.0002)
        assert result[1, 1] == pytest.approx(0.00045)
        assert result[0, 1] == pytest.approx(-0.0003)

    def test_ledoit_wolf_shape(self, service):
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)), columns=["A", "B", "C"])
        result = service.compute_sigma(returns, 252, CovMethod.LEDOIT_WOLF)
        assert result.shape == (3, 3)

    def test_ledoit_wolf_is_symmetric(self, service):
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)), columns=["A", "B", "C"])
        result = service.compute_sigma(returns, 252, CovMethod.LEDOIT_WOLF)
        assert result == pytest.approx(result.T)

    def test_ledoit_wolf_is_psd(self, service):
        """Ledoit-Wolf always produces a PSD matrix."""
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)), columns=["A", "B", "C"])
        result = service.compute_sigma(returns, 252, CovMethod.LEDOIT_WOLF)
        eigenvalues = np.linalg.eigvalsh(result)
        assert eigenvalues.min() >= -1e-8

    def test_ledoit_wolf_annualization_factor_scales(self, service):
        rng = np.random.default_rng(42)
        returns = pd.DataFrame(rng.normal(0, 0.01, (50, 3)), columns=["A", "B", "C"])
        sigma_12 = service.compute_sigma(returns, 12, CovMethod.LEDOIT_WOLF)
        sigma_24 = service.compute_sigma(returns, 24, CovMethod.LEDOIT_WOLF)
        assert sigma_24 == pytest.approx(2 * sigma_12)


# ---------------------------------------------------------------------------
# validate_psd
# ---------------------------------------------------------------------------


class TestValidatePsd:
    def test_identity_matrix_is_psd(self, service):
        is_psd, reason = service.validate_psd(np.eye(3))
        assert is_psd is True
        assert reason is None

    def test_positive_definite_matrix_passes(self, service):
        # [[4, 2], [2, 3]] has eigenvalues > 0
        matrix = np.array([[4.0, 2.0], [2.0, 3.0]])
        is_psd, reason = service.validate_psd(matrix)
        assert is_psd is True
        assert reason is None

    def test_negative_eigenvalue_fails(self, service):
        # [[1, 0], [0, -1]] has eigenvalue -1
        matrix = np.array([[1.0, 0.0], [0.0, -1.0]])
        is_psd, reason = service.validate_psd(matrix)
        assert is_psd is False
        assert reason is not None

    def test_failure_reason_mentions_eigenvalue(self, service):
        matrix = np.array([[1.0, 0.0], [0.0, -0.5]])
        _, reason = service.validate_psd(matrix)
        assert reason is not None
        assert "-0.5" in reason

    def test_near_zero_negative_eigenvalue_within_tolerance_passes(self, service):
        """Eigenvalue of -1e-9 is within floating-point tolerance and should pass."""
        matrix = np.array([[1.0, 0.0], [0.0, -1e-9]])
        is_psd, reason = service.validate_psd(matrix)
        assert is_psd is True

    def test_eigenvalue_just_below_tolerance_fails(self, service):
        """Eigenvalue of -2e-8 should fail (below -1e-8 threshold)."""
        matrix = np.array([[1.0, 0.0], [0.0, -2e-8]])
        is_psd, reason = service.validate_psd(matrix)
        assert is_psd is False


# ---------------------------------------------------------------------------
# repair_psd
# ---------------------------------------------------------------------------


class TestRepairPsd:
    def test_repaired_matrix_is_psd(self, service):
        """After repair, all eigenvalues should be ≥ 0."""
        non_psd = np.array([[1.0, 0.0], [0.0, -0.5]])
        repaired, _ = service.repair_psd(non_psd)
        eigenvalues = np.linalg.eigvalsh(repaired)
        assert eigenvalues.min() >= -1e-10

    def test_repaired_matrix_is_symmetric(self, service):
        non_psd = np.array([[1.0, 1.5], [1.5, -0.5]])
        repaired, _ = service.repair_psd(non_psd)
        assert repaired == pytest.approx(repaired.T)

    def test_repair_returns_string_explanation(self, service):
        non_psd = np.array([[1.0, 0.0], [0.0, -0.5]])
        _, explanation = service.repair_psd(non_psd)
        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_repair_explanation_mentions_clipped_count(self, service):
        """Explanation should state how many eigenvalues were clipped."""
        non_psd = np.array([[1.0, 0.0], [0.0, -0.5]])
        _, explanation = service.repair_psd(non_psd)
        assert "1" in explanation

    def test_repair_of_already_psd_matrix_is_identity_operation(self, service):
        """Repairing a PSD matrix should leave it essentially unchanged."""
        psd = np.array([[4.0, 1.0], [1.0, 3.0]])
        repaired, _ = service.repair_psd(psd)
        assert repaired == pytest.approx(psd, abs=1e-10)

    def test_repair_with_multiple_negative_eigenvalues(self, service):
        """All negative eigenvalues are clipped, not just the smallest."""
        # Construct a matrix with two negative eigenvalues by starting from
        # a diagonal with known values
        matrix = np.diag([-0.3, -0.1, 1.0])
        repaired, explanation = service.repair_psd(matrix)
        eigenvalues = np.linalg.eigvalsh(repaired)
        assert eigenvalues.min() >= -1e-10
        assert "2" in explanation


# ---------------------------------------------------------------------------
# §4.3 compute_correlation
# ---------------------------------------------------------------------------


class TestComputeCorrelation:
    def test_correlation_formula_off_diagonal(self, service):
        """ρ_{ij} = Σ_{ij} / (σ_i · σ_j)  (DATA-MODEL.md §4.3)."""
        cov = np.array([[0.04, 0.02], [0.02, 0.09]])
        vols = np.array([0.2, 0.3])
        corr = service.compute_correlation(cov, vols)
        # ρ_01 = 0.02 / (0.2 * 0.3) = 1/3
        assert corr[0, 1] == pytest.approx(0.02 / (0.2 * 0.3))

    def test_diagonal_is_one(self, service):
        """ρ_{ii} = Σ_{ii} / σ_i² = 1  (DATA-MODEL.md §4.3)."""
        cov = np.array([[0.04, 0.02], [0.02, 0.09]])
        vols = np.array([0.2, 0.3])
        corr = service.compute_correlation(cov, vols)
        assert corr[0, 0] == pytest.approx(1.0)
        assert corr[1, 1] == pytest.approx(1.0)

    def test_correlation_is_symmetric(self, service):
        cov = np.array([[0.04, 0.02], [0.02, 0.09]])
        vols = np.array([0.2, 0.3])
        corr = service.compute_correlation(cov, vols)
        assert corr == pytest.approx(corr.T)

    def test_correlation_shape(self, service):
        cov = np.eye(3) * 0.04
        vols = np.array([0.2, 0.2, 0.2])
        corr = service.compute_correlation(cov, vols)
        assert corr.shape == (3, 3)

    def test_correlation_bounded_negative_one_to_one(self, service):
        """All entries should be in [-1, 1] for a valid covariance matrix."""
        rng = np.random.default_rng(7)
        returns = pd.DataFrame(rng.normal(0, 0.01, (100, 4)))
        service_obj = EstimationService()
        sigma = service_obj.compute_sigma(returns, 252, CovMethod.SAMPLE)
        vols = np.sqrt(np.diag(sigma))
        corr = service_obj.compute_correlation(sigma, vols)
        assert corr.min() >= -1.0 - 1e-8
        assert corr.max() <= 1.0 + 1e-8
