"""Tests for src/domain/models/screening.py."""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.screening import (
    ScoreWeights,
    ScreeningConfig,
    ScreeningRun,
    ScreeningScore,
)
from src.domain.models.enums import ReferenceType


# --- ScoreWeights ---

def test_score_weights_defaults_sum_to_one():
    sw = ScoreWeights()
    total = sw.correlation + sw.marginal_vol + sw.sector_gap + sw.hhi
    assert abs(total - 1.0) < 1e-9


def test_score_weights_default_correlation():
    assert ScoreWeights().correlation == 0.40


def test_score_weights_default_marginal_vol():
    assert ScoreWeights().marginal_vol == 0.30


def test_score_weights_custom_valid():
    sw = ScoreWeights(correlation=0.25, marginal_vol=0.25, sector_gap=0.25, hhi=0.25)
    assert sw.sector_gap == 0.25


def test_score_weights_not_sum_to_one_raises():
    with pytest.raises(ValidationError):
        ScoreWeights(correlation=0.40, marginal_vol=0.30, sector_gap=0.15, hhi=0.20)


def test_score_weights_individual_above_one_raises():
    with pytest.raises(ValidationError):
        ScoreWeights(correlation=1.1, marginal_vol=0.0, sector_gap=0.0, hhi=0.0)


# --- ScreeningConfig ---

def test_screening_config_default_nominal_add_weight():
    assert ScreeningConfig().nominal_add_weight == 0.05


def test_screening_config_default_sector_gap_threshold():
    assert ScreeningConfig().sector_gap_threshold == 0.02


def test_screening_config_default_factory():
    cfg = ScreeningConfig.default()
    assert cfg.nominal_add_weight == 0.05


def test_screening_config_custom_nominal_weight():
    cfg = ScreeningConfig(nominal_add_weight=0.10)
    assert cfg.nominal_add_weight == 0.10


def test_screening_config_nominal_weight_zero_raises():
    with pytest.raises(ValidationError):
        ScreeningConfig(nominal_add_weight=0.0)


def test_screening_config_nominal_weight_one_raises():
    with pytest.raises(ValidationError):
        ScreeningConfig(nominal_add_weight=1.0)


# --- ScreeningScore ---

def test_screening_score_construction():
    score = ScreeningScore(
        screening_id=uuid4(),
        asset_id=uuid4(),
        avg_pairwise_corr=0.45,
        marginal_vol_reduction=0.012,
        sector_gap_score=1.0,
        hhi_reduction=0.05,
        composite_score=0.72,
        rank=1,
        explanation="Fills an absent asset class and reduces average correlation.",
    )
    assert score.rank == 1


def test_screening_score_composite_above_one_raises():
    with pytest.raises(ValidationError):
        ScreeningScore(
            screening_id=uuid4(),
            asset_id=uuid4(),
            avg_pairwise_corr=0.3,
            marginal_vol_reduction=0.01,
            sector_gap_score=0.5,
            hhi_reduction=0.02,
            composite_score=1.1,
            rank=1,
            explanation="Test",
        )


def test_screening_score_rank_below_one_raises():
    with pytest.raises(ValidationError):
        ScreeningScore(
            screening_id=uuid4(),
            asset_id=uuid4(),
            avg_pairwise_corr=0.3,
            marginal_vol_reduction=0.01,
            sector_gap_score=0.5,
            hhi_reduction=0.02,
            composite_score=0.7,
            rank=0,
            explanation="Test",
        )


# --- ScreeningRun ---

def test_screening_run_for_holdings_reference_type():
    run = ScreeningRun.for_holdings(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=uuid4(),
    )
    assert run.reference_type == ReferenceType.CURRENT_HOLDINGS


def test_screening_run_for_holdings_universe_id_is_none():
    run = ScreeningRun.for_holdings(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=uuid4(),
    )
    assert run.reference_universe_id is None


def test_screening_run_for_universe_reference_type():
    run = ScreeningRun.for_universe(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    assert run.reference_type == ReferenceType.SEED_UNIVERSE


def test_screening_run_for_universe_snapshot_id_is_none():
    run = ScreeningRun.for_universe(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    assert run.reference_snapshot_id is None


def test_screening_run_current_holdings_missing_snapshot_raises():
    with pytest.raises(ValidationError):
        ScreeningRun(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
            reference_type=ReferenceType.CURRENT_HOLDINGS,
            reference_snapshot_id=None,
        )


def test_screening_run_current_holdings_has_universe_raises():
    with pytest.raises(ValidationError):
        ScreeningRun(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
            reference_type=ReferenceType.CURRENT_HOLDINGS,
            reference_snapshot_id=uuid4(),
            reference_universe_id=uuid4(),
        )


def test_screening_run_seed_universe_missing_universe_raises():
    with pytest.raises(ValidationError):
        ScreeningRun(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
            reference_type=ReferenceType.SEED_UNIVERSE,
            reference_universe_id=None,
        )


def test_screening_run_seed_universe_has_snapshot_raises():
    with pytest.raises(ValidationError):
        ScreeningRun(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
            reference_type=ReferenceType.SEED_UNIVERSE,
            reference_universe_id=uuid4(),
            reference_snapshot_id=uuid4(),
        )


def test_screening_run_default_config():
    run = ScreeningRun.for_universe(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    assert run.config.nominal_add_weight == 0.05


def test_screening_run_custom_config():
    cfg = ScreeningConfig(nominal_add_weight=0.10)
    run = ScreeningRun.for_universe(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
        config=cfg,
    )
    assert run.config.nominal_add_weight == 0.10


def test_screening_run_scores_empty_by_default():
    run = ScreeningRun.for_holdings(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=uuid4(),
    )
    assert run.scores == []


def test_screening_run_id_auto_generated():
    run = ScreeningRun.for_holdings(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=uuid4(),
    )
    assert run.screening_id is not None
