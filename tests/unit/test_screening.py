"""Unit tests for ScreeningService.

All numeric assertions use values computed by hand from the formulas in
DATA-MODEL.md §4.9 so that the tests act as an executable specification.

Test layout:
  - Fixtures (shared assets, covariance matrix, UUIDs)
  - _normalize_scores / _scale
  - _calc_avg_correlation
  - _calc_marginal_vol_reduction
  - _calc_sector_gap_score
  - _calc_hhi_reduction
  - _sector_gap_clause
  - score_candidates (integration)
  - Edge cases
"""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography
from src.domain.models.screening import ScreeningConfig, ScoreWeights
from src.domain.services.screening import ScreeningService


# ======================================================================== #
# Helpers                                                                    #
# ======================================================================== #


def _make_asset(
    asset_class: AssetClass,
    sector: str | None = None,
    ticker: str = "TST",
    asset_id: UUID | None = None,
) -> Asset:
    """Create an Asset; when asset_id is given it is used verbatim so that
    the returned object's .asset_id matches an externally-minted UUID."""
    kwargs = dict(
        ticker=ticker,
        name=f"Test {ticker}",
        asset_class=asset_class,
        sub_class="test",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
        sector=sector,
    )
    if asset_id is not None:
        return Asset(asset_id=asset_id, **kwargs)
    return Asset.create(**kwargs)


# ======================================================================== #
# Fixtures                                                                   #
# ======================================================================== #
#
# 4-asset universe used in integration tests:
#   idx 0  ref1  — Equity / IT sector        (reference, weight 0.60)
#   idx 1  ref2  — Equity / Health Care      (reference, weight 0.40)
#   idx 2  div   — Fixed Income / no sector  (candidate, low correlation)
#   idx 3  sim   — Equity / IT sector        (candidate, high correlation)
#
# Annualised vols: 20 %, 15 %, 10 %, 25 %
# Correlation matrix:
#   ref1–ref2:  0.50
#   ref1–div:   0.10   ref2–div:  0.10
#   ref1–sim:   0.80   ref2–sim:  0.70
#   div–sim:    0.30
#
# All numbers below are exact products σ_i × ρ_{ij} × σ_j.


@pytest.fixture()
def ref1_id():
    return uuid4()


@pytest.fixture()
def ref2_id():
    return uuid4()


@pytest.fixture()
def div_id():
    return uuid4()


@pytest.fixture()
def sim_id():
    return uuid4()


@pytest.fixture()
def ref1_asset(ref1_id):
    # Use ref1_id as the asset_id so reference_weights lookups resolve correctly.
    return _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="REF1", asset_id=ref1_id)


@pytest.fixture()
def ref2_asset(ref2_id):
    return _make_asset(AssetClass.EQUITY, sector="Health Care", ticker="REF2", asset_id=ref2_id)


@pytest.fixture()
def div_asset(div_id):
    # Fixed income — fills an underrepresented asset class
    return _make_asset(AssetClass.FIXED_INCOME, sector=None, ticker="DIV", asset_id=div_id)


@pytest.fixture()
def sim_asset(sim_id):
    # Equity / IT — same class AND sector as ref1
    return _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="SIM", asset_id=sim_id)


@pytest.fixture()
def covariance_4x4():
    """Symmetric 4×4 covariance matrix built from the vols and correlations above."""
    return np.array(
        [
            # ref1    ref2     div      sim
            [0.0400,  0.0150,  0.0020,  0.0400],   # ref1 vol=20%
            [0.0150,  0.0225,  0.0015,  0.02625],  # ref2 vol=15%
            [0.0020,  0.0015,  0.0100,  0.0075],   # div  vol=10%
            [0.0400,  0.02625, 0.0075,  0.0625],   # sim  vol=25%
        ]
    )


@pytest.fixture()
def asset_index(ref1_id, ref2_id, div_id, sim_id):
    return {ref1_id: 0, ref2_id: 1, div_id: 2, sim_id: 3}


@pytest.fixture()
def reference_weights(ref1_id, ref2_id):
    return {ref1_id: 0.60, ref2_id: 0.40}


@pytest.fixture()
def reference_assets(ref1_id, ref2_id, ref1_asset, ref2_asset):
    return {ref1_id: ref1_asset, ref2_id: ref2_asset}


@pytest.fixture()
def candidate_assets(div_id, sim_id, div_asset, sim_asset):
    return {div_id: div_asset, sim_id: sim_asset}


@pytest.fixture()
def default_config():
    return ScreeningConfig.default()


@pytest.fixture()
def svc():
    return ScreeningService()


# ======================================================================== #
# _normalize_scores / _scale                                                 #
# ======================================================================== #


def test_normalize_scores_standard_ascending(svc):
    assert svc._normalize_scores([1.0, 2.0, 3.0]) == pytest.approx([0.0, 0.5, 1.0])


def test_normalize_scores_inverted(svc):
    # Lower raw → higher normalized score.
    assert svc._normalize_scores([1.0, 2.0, 3.0], invert=True) == pytest.approx(
        [1.0, 0.5, 0.0]
    )


def test_normalize_scores_degenerate_returns_zeros(svc):
    # All candidates share the same raw value — signal is uninformative.
    assert svc._normalize_scores([5.0, 5.0, 5.0]) == [0.0, 0.0, 0.0]


def test_normalize_scores_single_element_returns_zero(svc):
    # One candidate: min == max → degenerate.
    assert svc._normalize_scores([42.0]) == [0.0]


def test_normalize_scores_empty_returns_empty(svc):
    assert svc._normalize_scores([]) == []


def test_normalize_scores_preserves_order(svc):
    raw = [3.0, 1.0, 2.0]
    result = svc._normalize_scores(raw)
    assert result == pytest.approx([1.0, 0.0, 0.5])


def test_scale_standard(svc):
    result = svc._scale([0.0, 5.0, 10.0], min_val=0.0, max_val=10.0, invert=False)
    assert result == pytest.approx([0.0, 0.5, 1.0])


def test_scale_inverted(svc):
    result = svc._scale([0.0, 5.0, 10.0], min_val=0.0, max_val=10.0, invert=True)
    assert result == pytest.approx([1.0, 0.5, 0.0])


# ======================================================================== #
# _calc_avg_correlation                                                      #
# ======================================================================== #


def test_calc_avg_correlation_identity_matrix_is_zero(svc):
    """Candidate is orthogonal to all reference assets — expected correlation 0."""
    corr = np.eye(4)
    result = svc._calc_avg_correlation(candidate_idx=2, reference_indices=[0, 1], corr_matrix=corr)
    assert result == pytest.approx(0.0)


def test_calc_avg_correlation_known_values(svc):
    # Build a 3×3 correlation matrix where ρ(2,0)=0.8, ρ(2,1)=0.7.
    corr = np.array(
        [[1.0, 0.5, 0.8],
         [0.5, 1.0, 0.7],
         [0.8, 0.7, 1.0]]
    )
    result = svc._calc_avg_correlation(candidate_idx=2, reference_indices=[0, 1], corr_matrix=corr)
    assert result == pytest.approx((0.8 + 0.7) / 2)


def test_calc_avg_correlation_single_reference(svc):
    corr = np.array([[1.0, 0.6], [0.6, 1.0]])
    result = svc._calc_avg_correlation(candidate_idx=1, reference_indices=[0], corr_matrix=corr)
    assert result == pytest.approx(0.6)


def test_calc_avg_correlation_empty_reference_returns_zero(svc):
    corr = np.eye(3)
    result = svc._calc_avg_correlation(candidate_idx=2, reference_indices=[], corr_matrix=corr)
    assert result == 0.0


def test_calc_avg_correlation_uses_4x4_fixture(svc, covariance_4x4):
    """Verify against hand-computed correlations from the 4-asset fixture."""
    vols = np.sqrt(np.diag(covariance_4x4))
    corr = covariance_4x4 / np.outer(vols, vols)

    # div (idx=2): ρ(2,0)=0.10, ρ(2,1)=0.10 → avg = 0.10
    result_div = svc._calc_avg_correlation(2, [0, 1], corr)
    assert result_div == pytest.approx(0.10, abs=1e-6)

    # sim (idx=3): ρ(3,0)=0.80, ρ(3,1)=0.70 → avg = 0.75
    result_sim = svc._calc_avg_correlation(3, [0, 1], corr)
    assert result_sim == pytest.approx(0.75, abs=1e-6)


# ======================================================================== #
# _calc_marginal_vol_reduction                                               #
# ======================================================================== #


def test_calc_mvr_uncorrelated_candidate_reduces_volatility(svc):
    """Adding an independent asset at 5 % reduces portfolio vol."""
    # 3 assets: ref1=0, ref2=1, candidate=2; independent (diagonal cov).
    cov = np.diag([0.04, 0.0225, 0.01])
    ref_weights = np.array([0.60, 0.40, 0.0])

    sigma_R = np.sqrt(0.60**2 * 0.04 + 0.40**2 * 0.0225)
    pro = np.array([0.57, 0.38, 0.05])
    sigma_pro = np.sqrt(pro @ cov @ pro)
    expected_mvr = sigma_R - sigma_pro

    result = svc._calc_marginal_vol_reduction(2, ref_weights.copy(), cov, delta=0.05)
    assert result == pytest.approx(expected_mvr, rel=1e-6)
    assert result > 0.0  # adding independent asset reduces vol


def test_calc_mvr_high_corr_high_vol_increases_volatility(svc):
    """Adding a highly correlated, high-volatility asset increases portfolio vol."""
    # ref vols: 20%, 15%; candidate vol: 50%; high correlations.
    cov = np.array(
        [[0.04,   0.015,  0.090],   # ref1-cand corr = 0.90
         [0.015,  0.0225, 0.0675],  # ref2-cand corr = 0.90
         [0.090,  0.0675, 0.25]]    # candidate vol = 50%
    )
    ref_weights = np.array([0.60, 0.40, 0.0])
    result = svc._calc_marginal_vol_reduction(2, ref_weights.copy(), cov, delta=0.05)
    assert result < 0.0  # vol increases


def test_calc_mvr_uses_4x4_fixture(svc, covariance_4x4):
    """Verify hand-computed MVR values for both candidates."""
    ref_weights = np.array([0.60, 0.40, 0.0, 0.0])
    delta = 0.05

    sigma_R = np.sqrt(ref_weights @ covariance_4x4 @ ref_weights)

    # div (idx=2)
    pro_div = ref_weights * (1 - delta)
    pro_div[2] += delta
    mvr_div = sigma_R - np.sqrt(pro_div @ covariance_4x4 @ pro_div)

    result_div = svc._calc_marginal_vol_reduction(2, ref_weights.copy(), covariance_4x4, delta)
    assert result_div == pytest.approx(float(mvr_div), rel=1e-6)
    assert result_div > 0.0  # diversifier reduces vol

    # sim (idx=3)
    pro_sim = ref_weights * (1 - delta)
    pro_sim[3] += delta
    mvr_sim = sigma_R - np.sqrt(pro_sim @ covariance_4x4 @ pro_sim)

    result_sim = svc._calc_marginal_vol_reduction(3, ref_weights.copy(), covariance_4x4, delta)
    assert result_sim == pytest.approx(float(mvr_sim), rel=1e-6)
    assert result_sim < 0.0  # similar high-corr candidate increases vol


# ======================================================================== #
# _calc_sector_gap_score                                                     #
# ======================================================================== #


def _build_ref_for_gap(ref1_id, ref2_id):
    """Helper: reference with Equity(IT) at 0.6 and Equity(Healthcare) at 0.4."""
    ref1 = _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="R1")
    ref2 = _make_asset(AssetClass.EQUITY, sector="Health Care", ticker="R2")
    ref_assets = [ref1, ref2]
    ref_weights = {ref1.asset_id: 0.60, ref2.asset_id: 0.40}
    return ref_assets, ref_weights


def test_sector_gap_new_asset_class_scores_one():
    """Fixed Income is not in the reference → gap score 1.0."""
    svc = ScreeningService()
    ref1_id, ref2_id = uuid4(), uuid4()
    ref_assets, ref_weights = _build_ref_for_gap(ref1_id, ref2_id)
    candidate = _make_asset(AssetClass.FIXED_INCOME, sector=None, ticker="BND")

    result = svc._calc_sector_gap_score(candidate, ref_assets, ref_weights, threshold=0.02)
    assert result == 1.0


def test_sector_gap_same_class_new_sector_scores_half():
    """Equity is represented, but Financials sector is not → gap score 0.5."""
    svc = ScreeningService()
    ref1_id, ref2_id = uuid4(), uuid4()
    ref_assets, ref_weights = _build_ref_for_gap(ref1_id, ref2_id)
    candidate = _make_asset(AssetClass.EQUITY, sector="Financials", ticker="FIN")

    result = svc._calc_sector_gap_score(candidate, ref_assets, ref_weights, threshold=0.02)
    assert result == 0.5


def test_sector_gap_same_class_and_sector_scores_zero():
    """Equity / IT is already in the reference → gap score 0.0."""
    svc = ScreeningService()
    ref1_id, ref2_id = uuid4(), uuid4()
    ref_assets, ref_weights = _build_ref_for_gap(ref1_id, ref2_id)
    candidate = _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="TECH")

    result = svc._calc_sector_gap_score(candidate, ref_assets, ref_weights, threshold=0.02)
    assert result == 0.0


def test_sector_gap_non_equity_in_represented_class_scores_zero():
    """Non-equity candidate whose class IS represented; sector=None → 0.0."""
    svc = ScreeningService()
    fi_asset = _make_asset(AssetClass.FIXED_INCOME, sector=None, ticker="BND1")
    fi_asset2 = _make_asset(AssetClass.FIXED_INCOME, sector=None, ticker="BND2")
    ref_assets = [fi_asset]
    ref_weights = {fi_asset.asset_id: 1.0}
    # Candidate is also fixed income (class is represented), sector is None.
    candidate = fi_asset2
    result = svc._calc_sector_gap_score(candidate, ref_assets, ref_weights, threshold=0.02)
    assert result == 0.0


def test_sector_gap_class_below_threshold_counts_as_missing():
    """Asset class with weight < θ is treated as not represented → gap = 1.0."""
    svc = ScreeningService()
    fi = _make_asset(AssetClass.FIXED_INCOME, sector=None, ticker="BND")
    eq = _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="EQ")
    # Equity weight 0.005 is below threshold 0.02.
    ref_assets = [fi, eq]
    ref_weights = {fi.asset_id: 0.995, eq.asset_id: 0.005}

    candidate = _make_asset(AssetClass.EQUITY, sector="Information Technology", ticker="C")
    result = svc._calc_sector_gap_score(candidate, ref_assets, ref_weights, threshold=0.02)
    assert result == 1.0


# ======================================================================== #
# _calc_hhi_reduction                                                        #
# ======================================================================== #


def test_calc_hhi_reduction_new_candidate(svc):
    """HHI reduction for a candidate not in the reference."""
    ref_weights = np.array([0.60, 0.40, 0.0])
    delta = 0.05

    hhi_R = 0.60**2 + 0.40**2  # = 0.52
    pro = np.array([0.57, 0.38, 0.05])
    hhi_pro = float(np.sum(pro**2))  # 0.57²+0.38²+0.05² ≈ 0.4718
    expected = hhi_R - hhi_pro

    result = svc._calc_hhi_reduction(candidate_idx=2, reference_weights=ref_weights.copy(), delta=delta)
    assert result == pytest.approx(expected, abs=1e-8)
    assert result > 0.0  # adding a diversified asset lowers HHI


def test_calc_hhi_reduction_concentrated_reference(svc):
    """Highly concentrated reference → larger HHI reduction."""
    ref_weights_concentrated = np.array([0.90, 0.10, 0.0])
    ref_weights_equal = np.array([0.50, 0.50, 0.0])
    delta = 0.05

    hhi_red_conc = svc._calc_hhi_reduction(2, ref_weights_concentrated.copy(), delta)
    hhi_red_eq = svc._calc_hhi_reduction(2, ref_weights_equal.copy(), delta)

    # More concentrated reference has higher HHI, so higher reduction.
    assert hhi_red_conc > hhi_red_eq


def test_calc_hhi_reduction_candidate_already_in_reference(svc):
    """Candidate at idx=0 already has weight in reference — HHI differs."""
    # ref1 (idx=0) has weight 0.6, ref2 (idx=1) has weight 0.4.
    ref_weights = np.array([0.60, 0.40])
    delta = 0.05

    # Treating idx=0 as the candidate: pro_weights[0] = 0.6×0.95 + 0.05 = 0.62
    pro = np.array([0.60 * 0.95 + 0.05, 0.40 * 0.95])
    hhi_pro = float(np.sum(pro**2))
    hhi_R = 0.60**2 + 0.40**2
    expected = hhi_R - hhi_pro

    result = svc._calc_hhi_reduction(0, ref_weights.copy(), delta)
    assert result == pytest.approx(expected, abs=1e-8)


# ======================================================================== #
# _sector_gap_clause                                                         #
# ======================================================================== #


def test_sector_gap_clause_one(svc):
    clause = svc._sector_gap_clause(1.0)
    assert "not currently represented" in clause
    assert "1.00" in clause


def test_sector_gap_clause_half(svc):
    clause = svc._sector_gap_clause(0.5)
    assert "GICS sector is absent" in clause
    assert "0.50" in clause


def test_sector_gap_clause_zero(svc):
    clause = svc._sector_gap_clause(0.0)
    assert "already represented" in clause
    assert "0.00" in clause


# ======================================================================== #
# score_candidates — integration                                             #
# ======================================================================== #


def test_score_candidates_returns_two_scores(
    svc,
    ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    sid = uuid4()
    scores = svc.score_candidates(
        screening_id=sid,
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    assert len(scores) == 2


def test_score_candidates_div_ranks_first(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """Diversifier (low corr, new class) should rank above similar asset."""
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    rank1 = next(s for s in scores if s.rank == 1)
    assert rank1.asset_id == div_id


def test_score_candidates_ranks_are_sequential(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    ranks = sorted(s.rank for s in scores)
    assert ranks == list(range(1, len(scores) + 1))


def test_score_candidates_composite_scores_in_unit_interval(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    for score in scores:
        assert 0.0 <= score.composite_score <= 1.0


def test_score_candidates_div_composite_equals_expected(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """With default weights, div should score 0.85 (corr+mvr+gap fully normalized)."""
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    div_score = next(s for s in scores if s.asset_id == div_id)
    # λ1=0.40 (norm_corr=1.0) + λ2=0.30 (norm_mvr=1.0) + λ3=0.15 (gap=1.0) + λ4=0.15 (degenerate→0.0)
    assert div_score.composite_score == pytest.approx(0.85, abs=1e-6)


def test_score_candidates_sim_composite_equals_zero(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """sim scores 0.0 — all signals are at minimum or degenerate."""
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    sim_score = next(s for s in scores if s.asset_id == sim_id)
    assert sim_score.composite_score == pytest.approx(0.0, abs=1e-6)


def test_score_candidates_explanations_are_non_empty(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    for score in scores:
        assert len(score.explanation) > 0


def test_score_candidates_explanations_contain_concrete_numbers(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """FR14: explanations must cite concrete numbers, not just direction."""
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    div_score = next(s for s in scores if s.asset_id == div_id)
    explanation = div_score.explanation
    # Must mention rank, composite score, volatility values, and HHI.
    assert "Rank 1" in explanation
    assert "%" in explanation        # volatility expressed as percentage
    assert "HHI" in explanation


def test_score_candidates_screening_id_stamped(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    sid = uuid4()
    scores = svc.score_candidates(
        screening_id=sid,
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    assert all(s.screening_id == sid for s in scores)


def test_score_candidates_raw_signals_are_stored(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """Verify raw signal values are accessible on each ScreeningScore."""
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    div_score = next(s for s in scores if s.asset_id == div_id)
    assert div_score.avg_pairwise_corr == pytest.approx(0.10, abs=1e-6)
    assert div_score.sector_gap_score == pytest.approx(1.0)
    assert div_score.marginal_vol_reduction > 0.0
    assert div_score.hhi_reduction > 0.0


def test_score_candidates_custom_weights_change_ranking(
    svc, ref1_id, ref2_id, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index,
):
    """With sector gap weight = 1.0 (others zero), div must still rank first."""
    config = ScreeningConfig(
        score_weights=ScoreWeights(
            correlation=0.0, marginal_vol=0.0, sector_gap=1.0, hhi=0.0
        )
    )
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, sim_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=config,
    )
    rank1 = next(s for s in scores if s.rank == 1)
    assert rank1.asset_id == div_id


# ======================================================================== #
# Edge cases                                                                 #
# ======================================================================== #


def test_score_candidates_empty_candidate_list_returns_empty(
    svc, reference_weights, reference_assets, covariance_4x4, asset_index, default_config
):
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[],
        candidate_assets={},
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    assert scores == []


def test_score_candidates_candidate_not_in_asset_index_is_silently_dropped(
    svc, div_id, sim_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    """Candidates absent from the covariance index are skipped, not errored."""
    unknown_id = uuid4()
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id, unknown_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    assert len(scores) == 1
    assert scores[0].asset_id == div_id


def test_score_candidates_single_candidate_gets_rank_one(
    svc, div_id,
    reference_weights, reference_assets, candidate_assets,
    covariance_4x4, asset_index, default_config,
):
    scores = svc.score_candidates(
        screening_id=uuid4(),
        reference_weights=reference_weights,
        reference_assets=reference_assets,
        candidate_ids=[div_id],
        candidate_assets=candidate_assets,
        covariance=covariance_4x4,
        asset_index=asset_index,
        config=default_config,
    )
    assert len(scores) == 1
    assert scores[0].rank == 1
    # Single candidate: corr, MVR, and HHI signals are degenerate → 0.0.
    # Sector gap (div = Fixed Income, not represented) is 1.0 and is used
    # directly without min-max normalisation, so composite = λ3 × 1.0 = 0.15.
    assert scores[0].composite_score == pytest.approx(0.15, abs=1e-6)
