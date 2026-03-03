"""Unit tests for DriftService.

All numeric assertions are computed by hand from the formulas in
DATA-MODEL.md §4.11 so that the tests act as an executable specification.

Test layout:
  - Fixtures (shared UUIDs, prices DataFrame)
  - _compute_growth_factors
  - _compute_implied_weights
  - _generate_explanation
  - compute_drift (integration)
  - Edge cases
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pandas as pd
import pytest

from src.domain.services.drift import DriftResult, DriftService

# ======================================================================== #
# Fixtures                                                                   #
# ======================================================================== #

ID_A = uuid4()
ID_B = uuid4()
ID_C = uuid4()

OPT_DATE = date(2024, 1, 1)
CHECK_DATE = date(2024, 1, 3)


@pytest.fixture()
def service() -> DriftService:
    return DriftService()


@pytest.fixture()
def three_day_prices() -> pd.DataFrame:
    """Three price rows covering OPT_DATE through CHECK_DATE.

    Asset A: [100, 110, 121]  →  r = +10%, +10%  →  growth = 1.21
    Asset B: [200, 180, 162]  →  r = -10%, -10%  →  growth = 0.81
    """
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {ID_A: [100.0, 110.0, 121.0], ID_B: [200.0, 180.0, 162.0]},
        index=dates,
    )


# ======================================================================== #
# _compute_growth_factors                                                    #
# ======================================================================== #


class TestComputeGrowthFactors:
    def test_two_assets_multi_period(
        self, service: DriftService, three_day_prices: pd.DataFrame
    ) -> None:
        """Growth = Π(1 + r_t); verified by hand."""
        result = service._compute_growth_factors(three_day_prices, OPT_DATE, CHECK_DATE)

        # Asset A: (1.10)(1.10) = 1.21
        assert result[ID_A] == pytest.approx(1.21, rel=1e-9)
        # Asset B: (0.90)(0.90) = 0.81
        assert result[ID_B] == pytest.approx(0.81, rel=1e-9)

    def test_single_period(self, service: DriftService) -> None:
        """One return period: growth equals 1 + that single return."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 115.0]}, index=dates)

        result = service._compute_growth_factors(prices, date(2024, 1, 1), date(2024, 1, 2))

        assert result[ID_A] == pytest.approx(1.15, rel=1e-9)

    def test_same_start_and_end_date_returns_ones(self, service: DriftService) -> None:
        """Window of one row → no return periods → growth = 1.0 for all assets."""
        dates = pd.to_datetime(["2024-01-01"])
        prices = pd.DataFrame({ID_A: [100.0], ID_B: [200.0]}, index=dates)

        result = service._compute_growth_factors(prices, date(2024, 1, 1), date(2024, 1, 1))

        assert result[ID_A] == pytest.approx(1.0)
        assert result[ID_B] == pytest.approx(1.0)

    def test_end_date_before_start_in_index_returns_ones(self, service: DriftService) -> None:
        """When the sliced window has < 2 rows, growth defaults to 1.0."""
        dates = pd.to_datetime(["2024-06-01", "2024-06-02"])
        prices = pd.DataFrame({ID_A: [100.0, 110.0]}, index=dates)

        # Request a window before any available data
        result = service._compute_growth_factors(prices, date(2024, 1, 1), date(2024, 1, 5))

        assert result[ID_A] == pytest.approx(1.0)

    def test_all_columns_returned(
        self, service: DriftService, three_day_prices: pd.DataFrame
    ) -> None:
        """Every column in the DataFrame appears as a key in the output."""
        result = service._compute_growth_factors(three_day_prices, OPT_DATE, CHECK_DATE)

        assert set(result.keys()) == {ID_A, ID_B}

    def test_growth_is_multiplicative_not_additive(self, service: DriftService) -> None:
        """Verifies Π(1 + r) — not sum(r) — using a two-step example.

        Prices: 100 → 110 → 99
        r1 = 10%, r2 = -10%
        Additive: 1.10 + 0.90 = 2.0  (wrong)
        Multiplicative: 1.10 × 0.90 = 0.99  (correct)
        """
        dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        prices = pd.DataFrame({ID_A: [100.0, 110.0, 99.0]}, index=dates)

        result = service._compute_growth_factors(prices, date(2024, 1, 1), date(2024, 1, 3))

        assert result[ID_A] == pytest.approx(0.99, rel=1e-9)


# ======================================================================== #
# _compute_implied_weights                                                   #
# ======================================================================== #


class TestComputeImpliedWeights:
    def test_implied_weights_sum_to_one(self, service: DriftService) -> None:
        """Implied weights must sum to 1.0 by construction."""
        targets = {ID_A: 0.6, ID_B: 0.4}
        growth = {ID_A: 1.1, ID_B: 0.9}

        result = service._compute_implied_weights(targets, growth)

        assert sum(result.values()) == pytest.approx(1.0, abs=1e-12)

    def test_implied_weights_formula(self, service: DriftService) -> None:
        """Hand-verified: w_A = (0.6 × 1.1) / (0.6×1.1 + 0.4×0.9) = 0.66 / 1.02."""
        targets = {ID_A: 0.6, ID_B: 0.4}
        growth = {ID_A: 1.1, ID_B: 0.9}

        result = service._compute_implied_weights(targets, growth)

        # numerators: A=0.66, B=0.36; total=1.02
        assert result[ID_A] == pytest.approx(0.66 / 1.02, rel=1e-9)
        assert result[ID_B] == pytest.approx(0.36 / 1.02, rel=1e-9)

    def test_equal_growth_preserves_weights(self, service: DriftService) -> None:
        """When all growth factors are equal, implied weights equal target weights."""
        targets = {ID_A: 0.5, ID_B: 0.3, ID_C: 0.2}
        growth = {ID_A: 1.05, ID_B: 1.05, ID_C: 1.05}

        result = service._compute_implied_weights(targets, growth)

        assert result[ID_A] == pytest.approx(0.5, rel=1e-9)
        assert result[ID_B] == pytest.approx(0.3, rel=1e-9)
        assert result[ID_C] == pytest.approx(0.2, rel=1e-9)

    def test_higher_growth_asset_increases_weight(self, service: DriftService) -> None:
        """Asset with superior growth should have a higher implied weight than its target."""
        targets = {ID_A: 0.5, ID_B: 0.5}
        growth = {ID_A: 2.0, ID_B: 1.0}  # A doubles, B flat

        result = service._compute_implied_weights(targets, growth)

        assert result[ID_A] > targets[ID_A]
        assert result[ID_B] < targets[ID_B]

    def test_zero_denominator_returns_target_weights(
        self, service: DriftService, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Degenerate case: all assets worth zero — fall back to target weights."""
        targets = {ID_A: 0.5, ID_B: 0.5}
        growth = {ID_A: 0.0, ID_B: 0.0}

        result = service._compute_implied_weights(targets, growth)

        assert result == targets
        assert "denominator" in caplog.text.lower()


# ======================================================================== #
# _generate_explanation                                                      #
# ======================================================================== #


class TestGenerateExplanation:
    def test_appreciation_uses_grown_and_appreciation_wording(
        self, service: DriftService
    ) -> None:
        explanation = service._generate_explanation(
            ticker="SPY", target=0.40, current=0.51, growth=1.275
        )

        assert "SPY" in explanation
        assert "grown" in explanation
        assert "price appreciation" in explanation

    def test_decline_uses_fallen_and_decline_wording(
        self, service: DriftService
    ) -> None:
        explanation = service._generate_explanation(
            ticker="TLT", target=0.30, current=0.22, growth=0.73
        )

        assert "TLT" in explanation
        assert "fallen" in explanation
        assert "price decline" in explanation

    def test_explanation_contains_concrete_percentages(
        self, service: DriftService
    ) -> None:
        """FR14: must include concrete numbers, not directional language only."""
        explanation = service._generate_explanation(
            ticker="SPY", target=0.40, current=0.51, growth=1.275
        )

        assert "40.0%" in explanation
        assert "51.0%" in explanation

    def test_growth_exactly_one_treated_as_appreciation(
        self, service: DriftService
    ) -> None:
        """Boundary: growth == 1.0 → no movement; should not say 'fallen'."""
        explanation = service._generate_explanation(
            ticker="XYZ", target=0.50, current=0.50, growth=1.0
        )

        assert "fallen" not in explanation
        assert "grown" in explanation


# ======================================================================== #
# compute_drift — integration                                                #
# ======================================================================== #


class TestComputeDrift:
    def test_no_breach_returns_false_any_breach(self, service: DriftService) -> None:
        """Small price moves within threshold → any_breach is False."""
        # A: [100, 103], B: [100, 101]
        # growth A=1.03, B=1.01
        # numerators: A=0.515, B=0.505; total=1.02
        # implied: A=0.50490, B=0.49510
        # drift: both ≈ 0.0049 < 0.05
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 103.0], ID_B: [100.0, 101.0]}, index=dates)
        targets = {ID_A: 0.5, ID_B: 0.5}
        tickers = {ID_A: "AAA", ID_B: "BBB"}

        result = service.compute_drift(
            target_weights=targets,
            asset_tickers=tickers,
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        assert not result.any_breach
        assert len(result.raw_positions) == 2
        # No explanation for non-breaching positions
        for _aid, _target, _current, explanation in result.raw_positions:
            assert explanation is None

    def test_breach_sets_any_breach_and_explanation(self, service: DriftService) -> None:
        """Large price move beyond threshold → any_breach True, explanation set."""
        # A: [100, 160] → growth=1.60; B: [100, 100] → growth=1.0
        # targets: A=0.5, B=0.5
        # numerators: A=0.80, B=0.50; total=1.30
        # implied: A=0.80/1.30≈0.6154, B=0.50/1.30≈0.3846
        # drift A≈0.1154 > 0.05 → breach; drift B≈0.1154 > 0.05 → breach
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 160.0], ID_B: [100.0, 100.0]}, index=dates)
        targets = {ID_A: 0.5, ID_B: 0.5}
        tickers = {ID_A: "SPY", ID_B: "TLT"}

        result = service.compute_drift(
            target_weights=targets,
            asset_tickers=tickers,
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        assert result.any_breach
        breached = [row for row in result.raw_positions if row[3] is not None]
        assert len(breached) > 0
        # SPY grew → explanation mentions the ticker
        spy_row = next(r for r in result.raw_positions if r[0] == ID_A)
        assert spy_row[3] is not None
        assert "SPY" in spy_row[3]

    def test_implied_weights_correct_in_positions(self, service: DriftService) -> None:
        """Verify the stored current_weight values match the formula."""
        # Asset A: [100, 110] → growth=1.1; B: [100, 90] → growth=0.9
        # targets: A=0.6, B=0.4
        # numerators: A=0.66, B=0.36; total=1.02
        # implied: A=0.66/1.02, B=0.36/1.02
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 110.0], ID_B: [100.0, 90.0]}, index=dates)
        targets = {ID_A: 0.6, ID_B: 0.4}
        tickers = {ID_A: "A", ID_B: "B"}

        result = service.compute_drift(
            target_weights=targets,
            asset_tickers=tickers,
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        positions = {row[0]: row for row in result.raw_positions}
        _aid_a, _t_a, current_a, _exp_a = positions[ID_A]
        _aid_b, _t_b, current_b, _exp_b = positions[ID_B]

        assert current_a == pytest.approx(0.66 / 1.02, rel=1e-9)
        assert current_b == pytest.approx(0.36 / 1.02, rel=1e-9)

    def test_threshold_stored_in_result(self, service: DriftService) -> None:
        """Custom threshold is echoed back in DriftResult."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 101.0]}, index=dates)

        result = service.compute_drift(
            target_weights={ID_A: 1.0},
            asset_tickers={ID_A: "TST"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
            threshold=0.02,
        )

        assert result.threshold == pytest.approx(0.02)

    def test_check_date_stored_in_result(self, service: DriftService) -> None:
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 102.0]}, index=dates)

        result = service.compute_drift(
            target_weights={ID_A: 1.0},
            asset_tickers={ID_A: "TST"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        assert result.check_date == date(2024, 1, 2)

    def test_result_is_frozen_dataclass(self, service: DriftService) -> None:
        """DriftResult must be immutable (frozen=True)."""
        dates = pd.to_datetime(["2024-01-01"])
        prices = pd.DataFrame({ID_A: [100.0]}, index=dates)

        result = service.compute_drift(
            target_weights={ID_A: 1.0},
            asset_tickers={ID_A: "TST"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 1),
        )

        with pytest.raises((AttributeError, TypeError)):
            result.any_breach = True  # type: ignore[misc]


# ======================================================================== #
# Edge cases                                                                 #
# ======================================================================== #


class TestEdgeCases:
    def test_no_overlapping_assets_returns_empty(
        self, service: DriftService, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When no target_weights UUID appears in prices columns, return empty result."""
        unrelated_id = uuid4()
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({unrelated_id: [100.0, 110.0]}, index=dates)

        result = service.compute_drift(
            target_weights={ID_A: 0.5, ID_B: 0.5},
            asset_tickers={ID_A: "AAA", ID_B: "BBB"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        assert not result.any_breach
        assert result.raw_positions == []
        assert "overlap" in caplog.text.lower()

    def test_same_optimization_and_check_date_no_drift(self, service: DriftService) -> None:
        """No time elapsed → growth = 1.0 → implied weights == target weights → no drift."""
        dates = pd.to_datetime(["2024-01-01"])
        prices = pd.DataFrame({ID_A: [100.0], ID_B: [200.0]}, index=dates)
        targets = {ID_A: 0.6, ID_B: 0.4}

        result = service.compute_drift(
            target_weights=targets,
            asset_tickers={ID_A: "A", ID_B: "B"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 1),
        )

        assert not result.any_breach
        for _aid, target, current, _exp in result.raw_positions:
            assert current == pytest.approx(target, abs=1e-12)

    def test_asset_missing_from_tickers_uses_uuid_string(
        self, service: DriftService
    ) -> None:
        """When a breached asset has no ticker entry, the UUID string is used as fallback."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 200.0]}, index=dates)  # 100% gain

        result = service.compute_drift(
            target_weights={ID_A: 1.0},
            asset_tickers={},  # intentionally empty
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        # With a single asset, growth=2.0, implied=1.0, drift=0 (no breach)
        # Single asset portfolio cannot breach — implied weight is always 1.0
        assert not result.any_breach

    def test_single_asset_portfolio_never_breaches(self, service: DriftService) -> None:
        """With one asset, implied weight is always 1.0 = target, so drift is always 0."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        prices = pd.DataFrame({ID_A: [100.0, 500.0]}, index=dates)  # 400% gain

        result = service.compute_drift(
            target_weights={ID_A: 1.0},
            asset_tickers={ID_A: "TST"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        assert not result.any_breach
        _, _target, current, _exp = result.raw_positions[0]
        assert current == pytest.approx(1.0, abs=1e-12)

    def test_partial_overlap_only_common_assets_processed(
        self, service: DriftService
    ) -> None:
        """Assets in target_weights but absent from prices are silently excluded."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])
        # Only ID_A is in prices; ID_B is not
        prices = pd.DataFrame({ID_A: [100.0, 103.0]}, index=dates)
        targets = {ID_A: 0.6, ID_B: 0.4}

        result = service.compute_drift(
            target_weights=targets,
            asset_tickers={ID_A: "AAA", ID_B: "BBB"},
            prices=prices,
            optimization_date=date(2024, 1, 1),
            check_date=date(2024, 1, 2),
        )

        # Only ID_A in result
        assert len(result.raw_positions) == 1
        assert result.raw_positions[0][0] == ID_A
