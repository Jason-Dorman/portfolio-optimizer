"""Tests for SqlScreeningRepository — mapping and immutability."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.models.screening import ScreeningConfig, ScoreWeights
from src.infrastructure.persistence.repositories.screening import (
    SqlScreeningRepository,
    _run_to_domain,
    _score_to_domain,
)


def _orm_score(**overrides):
    defaults = {
        "screening_id": uuid4(),
        "asset_id": uuid4(),
        "avg_pairwise_corr": 0.45,
        "marginal_vol_reduction": 0.03,
        "sector_gap_score": 0.8,
        "hhi_reduction": 0.02,
        "composite_score": 0.65,
        "rank": 1,
        "explanation": "Low correlation with existing holdings.",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _orm_run(**overrides):
    defaults = {
        "screening_id": uuid4(),
        "assumption_id": uuid4(),
        "candidate_pool_id": uuid4(),
        "reference_type": "seed_universe",
        "reference_snapshot_id": None,
        "reference_universe_id": uuid4(),
        "nominal_add_weight": 0.05,
        "sector_gap_threshold": 0.02,
        "score_weights": {"correlation": 0.4, "marginal_vol": 0.3, "sector_gap": 0.15, "hhi": 0.15},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- _score_to_domain mapping ---

def test_score_to_domain_maps_rank():
    assert _score_to_domain(_orm_score(rank=3)).rank == 3


def test_score_to_domain_maps_composite_score():
    assert _score_to_domain(_orm_score(composite_score=0.72)).composite_score == 0.72


def test_score_to_domain_maps_explanation():
    result = _score_to_domain(_orm_score(explanation="High marginal vol reduction."))
    assert result.explanation == "High marginal vol reduction."


# --- _run_to_domain mapping ---

def test_run_to_domain_deserializes_score_weights():
    result = _run_to_domain(_orm_run(), [])
    assert isinstance(result.config.score_weights, ScoreWeights)


def test_run_to_domain_maps_sector_gap_threshold():
    result = _run_to_domain(_orm_run(sector_gap_threshold=0.03), [])
    assert result.config.sector_gap_threshold == 0.03


def test_run_to_domain_embeds_provided_scores():
    scores_input = [_score_to_domain(_orm_score())]
    result = _run_to_domain(_orm_run(), scores_input)
    assert len(result.scores) == 1


# --- immutability guards ---

async def test_update_raises():
    repo = SqlScreeningRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.update(None)  # type: ignore[arg-type]


async def test_delete_raises():
    repo = SqlScreeningRepository(AsyncMock())
    with pytest.raises(NotImplementedError):
        await repo.delete(uuid4())
