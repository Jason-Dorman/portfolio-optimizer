"""Estimation service: returns, expected-return vector, and covariance matrix.

All formulas implement DATA-MODEL.md sections 4.1–4.5.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from src.domain.models.enums import CovMethod, Estimator, ReturnType


class EstimationService:
    """Pure computation service for return series and parameter estimation.

    Responsibilities (single, focused):
    - Convert price series to return series (simple or log).
    - Estimate annualized expected-return vectors (μ).
    - Estimate annualized covariance matrices (Σ).
    - Validate and repair positive semi-definite (PSD) matrices.
    - Convert covariance to correlation matrices.

    The class is stateless; all configuration is passed per-call.
    """

    def compute_returns(
        self,
        prices: pd.DataFrame,
        return_type: ReturnType,
    ) -> pd.DataFrame:
        """Compute simple or log returns from a price DataFrame.

        Implements DATA-MODEL.md §4.1:
          Simple: r_{i,t} = P_{i,t} / P_{i,t-1} - 1
          Log:    r_{i,t} = ln(P_{i,t} / P_{i,t-1})

        The first row is always dropped because there is no prior period.

        Args:
            prices: DataFrame with assets as columns and dates as index.
            return_type: ReturnType.SIMPLE or ReturnType.LOG.

        Returns:
            DataFrame of returns with the same columns; first row removed.
        """
        if return_type == ReturnType.SIMPLE:
            returns = prices / prices.shift(1) - 1
        elif return_type == ReturnType.LOG:
            returns = np.log(prices / prices.shift(1))
        else:
            raise ValueError(f"Unsupported return type: {return_type!r}")
        return returns.dropna()

    def compute_mu(
        self,
        returns: pd.DataFrame,
        annualization_factor: int,
        estimator: Estimator = Estimator.HISTORICAL,
        ewma_halflife: int = 63,
    ) -> np.ndarray:
        """Compute the annualized expected-return vector μ.

        Implements DATA-MODEL.md §4.2: μ_i = m · r̄_i

        Methods:
          HISTORICAL — arithmetic mean of all periods, scaled by m.
          EWMA       — exponentially weighted mean at the last period, scaled by m.
                       ewma_halflife controls the decay in number of periods.
          SHRINKAGE  — not yet implemented (raises NotImplementedError).

        Args:
            returns: DataFrame of periodic returns (assets as columns).
            annualization_factor: m — periods per year (e.g. 252 daily, 12 monthly).
            estimator: Which estimation method to use.
            ewma_halflife: Decay halflife in periods (EWMA only; default 63).

        Returns:
            1-D numpy array of shape (n_assets,) with annualized expected returns.
        """
        if estimator == Estimator.HISTORICAL:
            mu_periodic = returns.mean()
        elif estimator == Estimator.EWMA:
            mu_periodic = returns.ewm(halflife=ewma_halflife).mean().iloc[-1]
        else:
            raise NotImplementedError(
                f"Estimator.{estimator.value.upper()} for expected returns is not yet implemented."
            )
        return (mu_periodic * annualization_factor).to_numpy()

    def compute_sigma(
        self,
        returns: pd.DataFrame,
        annualization_factor: int,
        method: CovMethod = CovMethod.SAMPLE,
    ) -> np.ndarray:
        """Compute the annualized covariance matrix Σ.

        Implements DATA-MODEL.md §4.2: Σ = m · Cov(r)

        Methods:
          SAMPLE      — standard sample covariance, normalized by N-1 (pandas default).
          LEDOIT_WOLF — Oracle Approximating Shrinkage via sklearn.covariance.LedoitWolf.

        To apply PSD repair after estimation, call repair_psd() separately.

        Args:
            returns: DataFrame of periodic returns (assets as columns).
            annualization_factor: m — periods per year.
            method: Which covariance estimation method to use.

        Returns:
            2-D numpy array of shape (n_assets, n_assets), annualized, symmetric.

        Raises:
            ValueError: If method is not a recognized estimation method.
        """
        if method == CovMethod.SAMPLE:
            cov_periodic = returns.cov().to_numpy()
        elif method == CovMethod.LEDOIT_WOLF:
            lw = LedoitWolf()
            lw.fit(returns.to_numpy())
            cov_periodic = lw.covariance_
        else:
            raise ValueError(
                f"Unknown covariance method: {method!r}. "
                "Use CovMethod.SAMPLE or CovMethod.LEDOIT_WOLF."
            )
        return cov_periodic * annualization_factor

    def validate_psd(
        self,
        matrix: np.ndarray,
    ) -> tuple[bool, str | None]:
        """Check whether a matrix is positive semi-definite.

        Uses numpy.linalg.eigvalsh (symmetric eigenvalue solver). A matrix is
        considered PSD if all eigenvalues are ≥ −1e-8 (tolerance for floating-point
        rounding errors near zero).

        Args:
            matrix: Square symmetric numpy array.

        Returns:
            (True, None) if PSD; (False, reason_string) otherwise.
        """
        eigenvalues = np.linalg.eigvalsh(matrix)
        min_ev = float(eigenvalues.min())
        if min_ev < -1e-8:
            return False, (
                f"Matrix is not positive semi-definite: "
                f"minimum eigenvalue is {min_ev:.6g}."
            )
        return True, None

    def repair_psd(
        self,
        matrix: np.ndarray,
    ) -> tuple[np.ndarray, str]:
        """Project a matrix to the nearest positive semi-definite matrix.

        Uses eigendecomposition: negative eigenvalues are clipped to zero and
        the matrix is reconstructed. This produces the nearest PSD matrix in
        Frobenius norm (Higham, 1988). Symmetry is enforced after reconstruction
        to remove floating-point asymmetry introduced by the round-trip.

        Args:
            matrix: Square symmetric numpy array (need not be PSD).

        Returns:
            (repaired_matrix, explanation) where explanation is a plain-English
            string describing what was done and the original minimum eigenvalue.
        """
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        min_ev = float(eigenvalues.min())
        n_clipped = int((eigenvalues < 0).sum())
        eigenvalues_clipped = np.maximum(eigenvalues, 0.0)
        repaired = eigenvectors @ np.diag(eigenvalues_clipped) @ eigenvectors.T
        repaired = (repaired + repaired.T) / 2.0
        explanation = (
            f"Clipped {n_clipped} negative eigenvalue(s) to zero "
            f"(minimum was {min_ev:.6g}). "
            "Matrix projected to the nearest positive semi-definite matrix."
        )
        return repaired, explanation

    def compute_correlation(
        self,
        covariance: np.ndarray,
        volatilities: np.ndarray,
    ) -> np.ndarray:
        """Convert a covariance matrix to a correlation matrix.

        Implements DATA-MODEL.md §4.3:
          ρ_{ij} = Σ_{ij} / (σ_i · σ_j)

        Args:
            covariance: Square symmetric covariance matrix, shape (n, n).
            volatilities: 1-D array of per-asset volatilities (σ_i), shape (n,).

        Returns:
            Correlation matrix of shape (n, n).
        """
        outer = np.outer(volatilities, volatilities)
        return covariance / outer
