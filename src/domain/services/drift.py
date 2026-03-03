"""Drift detection service.

Implements DATA-MODEL.md §4.11: implied weights after price appreciation
are compared against target weights from the last optimization run.

Drift always uses simple returns for wealth compounding:
    growth_i = Π_τ (1 + r_{i,τ})

Implied weight:
    w_{i,t} = (w_i* · growth_i) / Σ_j (w_j* · growth_j)

Breach condition:
    |w_{i,t} - w_i*| > θ_drift   (default θ = 0.05)

The service returns a DriftResult dataclass (no run_id at the service layer).
The command handler wraps it into DriftCheck (with run_id) for persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pandas as pd

from src.domain.models.drift import DRIFT_THRESHOLD_DEFAULT

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────── #
# Output type                                                                  #
# ─────────────────────────────────────────────────────────────────────────── #


@dataclass(frozen=True)
class DriftResult:
    """Pure-computation output from drift detection.

    No run_id — the command handler wraps this into DriftCheck with the
    run_id when persisting to the database.

    raw_positions mirrors the format expected by DriftCheck.create():
        list of (asset_id, target_weight, current_weight, explanation | None)
        explanation is set only when the position has breached the threshold.
    """

    check_date: date
    threshold: float
    any_breach: bool
    raw_positions: list[tuple[UUID, float, float, str | None]]


# ─────────────────────────────────────────────────────────────────────────── #
# Service                                                                       #
# ─────────────────────────────────────────────────────────────────────────── #


class DriftService:
    """Pure computation service for portfolio drift detection.

    Responsibility: given target weights and subsequent prices, compute
    implied current weights and identify assets that have breached the
    drift threshold.

    Stateless — all configuration is passed per-call.
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def compute_drift(
        self,
        target_weights: dict[UUID, float],
        asset_tickers: dict[UUID, str],
        prices: pd.DataFrame,
        optimization_date: date,
        check_date: date,
        threshold: float = DRIFT_THRESHOLD_DEFAULT,
    ) -> DriftResult:
        """Compute drift from target weights using price changes.

        Always uses simple returns for wealth compounding (DATA-MODEL.md §4.11).

        Args:
            target_weights:    UUID → target weight from the optimization run.
            asset_tickers:     UUID → ticker string for plain-language alerts.
            prices:            DataFrame with UUID columns and a DatetimeIndex.
                               Must span at least [optimization_date, check_date].
            optimization_date: Date the target weights were established.
            check_date:        Date at which drift is evaluated.
            threshold:         Absolute drift threshold for breach detection.

        Returns:
            DriftResult with per-asset positions and breach summary.
        """
        growth_factors = self._compute_growth_factors(prices, optimization_date, check_date)

        common_ids = [aid for aid in target_weights if aid in growth_factors]

        if not common_ids:
            logger.warning(
                "No assets overlap between target_weights and prices DataFrame; "
                "returning empty DriftResult."
            )
            return DriftResult(
                check_date=check_date,
                threshold=threshold,
                any_breach=False,
                raw_positions=[],
            )

        active_targets = {aid: target_weights[aid] for aid in common_ids}
        active_growth = {aid: growth_factors[aid] for aid in common_ids}

        implied_weights = self._compute_implied_weights(active_targets, active_growth)

        raw_positions: list[tuple[UUID, float, float, str | None]] = []
        any_breach = False

        for asset_id in common_ids:
            target = active_targets[asset_id]
            current = implied_weights[asset_id]
            drift_abs = abs(current - target)
            breached = drift_abs > threshold

            explanation: str | None = None
            if breached:
                ticker = asset_tickers.get(asset_id, str(asset_id))
                explanation = self._generate_explanation(
                    ticker, target, current, active_growth[asset_id]
                )
                any_breach = True

            raw_positions.append((asset_id, target, current, explanation))

        return DriftResult(
            check_date=check_date,
            threshold=threshold,
            any_breach=any_breach,
            raw_positions=raw_positions,
        )

    # ------------------------------------------------------------------ #
    # Computation stages                                                   #
    # ------------------------------------------------------------------ #

    def _compute_growth_factors(
        self,
        prices: pd.DataFrame,
        start_date: date,
        end_date: date,
    ) -> dict[UUID, float]:
        """Compute multiplicative growth for each asset.

        Implements DATA-MODEL.md §4.11:
            growth_i = Π_τ (1 + r_{i,τ})

        Slices prices to the window [start_date, end_date] inclusive, where
        start_date provides the base price and end_date is the evaluation date.
        When the window has fewer than 2 rows (e.g. start_date == end_date),
        returns 1.0 for every asset — no elapsed periods means no price drift.

        Args:
            prices:     DataFrame with UUID columns and a DatetimeIndex.
            start_date: First date of the window (base price; included).
            end_date:   Last date of the window (evaluation price; included).

        Returns:
            dict[UUID, float] — growth factor per asset column.
        """
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        window = prices.loc[start_ts:end_ts]

        if len(window) < 2:
            return {col: 1.0 for col in prices.columns}

        simple_returns = window.pct_change().iloc[1:]
        growth_series = (1.0 + simple_returns).prod(axis=0)
        return {col: float(growth_series[col]) for col in prices.columns}

    def _compute_implied_weights(
        self,
        target_weights: dict[UUID, float],
        growth_factors: dict[UUID, float],
    ) -> dict[UUID, float]:
        """Compute current implied weights after price changes.

        Implements DATA-MODEL.md §4.11:
            w_{i,t} = (w_i* · growth_i) / Σ_j (w_j* · growth_j)

        If the denominator is ≤ 0 (degenerate: all assets lost all value),
        returns the original target weights unchanged and logs a warning.

        Args:
            target_weights: UUID → w_i* for each asset.
            growth_factors: UUID → Π(1 + r_t) for each asset.

        Returns:
            dict[UUID, float] — implied weights summing to 1.0.
        """
        numerators = {
            aid: target_weights[aid] * growth_factors[aid]
            for aid in target_weights
        }
        total = sum(numerators.values())

        if total <= 0.0:
            logger.warning(
                "Implied-weight denominator is ≤ 0 (all weighted growth values are "
                "zero); returning target weights unchanged."
            )
            return dict(target_weights)

        return {aid: num / total for aid, num in numerators.items()}

    # ------------------------------------------------------------------ #
    # Explanation generation                                               #
    # ------------------------------------------------------------------ #

    def _generate_explanation(
        self,
        ticker: str,
        target: float,
        current: float,
        growth: float,
    ) -> str:
        """Generate plain-language drift alert with concrete percentages.

        Implements FR13 / FR14 explainability requirement:
            "SPY has grown from 40% to 51% due to price appreciation
             since last rebalance."

        Uses concrete numbers only — no directional language without figures.

        Args:
            ticker:  Ticker symbol for the asset.
            target:  Target weight as a decimal (e.g. 0.40 for 40%).
            current: Current implied weight as a decimal.
            growth:  Total growth factor (≥1 = appreciation, <1 = decline).

        Returns:
            Plain-language sentence describing the drift.
        """
        if growth >= 1.0:
            movement, cause = "grown", "price appreciation"
        else:
            movement, cause = "fallen", "price decline"

        return (
            f"{ticker} has {movement} from {target * 100:.1f}% to {current * 100:.1f}% "
            f"due to {cause} since last rebalance."
        )
