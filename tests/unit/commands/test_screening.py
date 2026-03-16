"""Unit tests for src/commands/screening.py."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.commands._cov_utils import build_cov_array, extract_cov_asset_ids
from src.commands.screening import RunScreeningCommand, RunScreeningHandler
from src.domain.models.assets import Asset, Universe
from src.domain.models.assumptions import AssumptionSet, CovarianceEntry, CovarianceMatrix
from src.domain.models.enums import (
    AssetClass,
    CovMethod,
    Estimator,
    Frequency,
    Geography,
    ReturnType,
    UniverseType,
)
from src.domain.models.screening import ScreeningRun


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_asset(ticker: str = "SPY") -> Asset:
    return Asset(
        ticker=ticker,
        name="Test ETF",
        asset_class=AssetClass.EQUITY,
        sub_class="large_cap_us",
        geography=Geography.US,
        currency="USD",
        is_etf=True,
    )


def _make_assumption(universe_id=None) -> AssumptionSet:
    from datetime import date
    return AssumptionSet.create(
        universe_id=universe_id or uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        lookback_start=date(2023, 1, 1),
        lookback_end=date(2023, 12, 31),
        rf_annual=0.04,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )


def _make_covariance(assumption_id, asset_ids) -> CovarianceMatrix:
    entries = [
        CovarianceEntry(
            assumption_id=assumption_id,
            asset_id_i=asset_ids[i],
            asset_id_j=asset_ids[j],
            cov_annual=0.04 if i == j else 0.01,
        )
        for i in range(len(asset_ids))
        for j in range(i, len(asset_ids))
    ]
    return CovarianceMatrix(assumption_id=assumption_id, entries=entries)


def _make_handler(
    assumption=None,
    covariance=None,
    candidate_ids=None,
    snapshot=None,
    ref_universe=None,
    ref_asset_ids=None,
    screening_result=None,
):
    assumption = assumption or _make_assumption()
    asset_ids = [uuid4(), uuid4()]
    candidate_ids = candidate_ids or [uuid4()]
    cov = covariance or _make_covariance(assumption.assumption_id, asset_ids + candidate_ids)

    assumption_repo = AsyncMock()
    assumption_repo.get_by_id.return_value = assumption
    assumption_repo.get_covariance_matrix.return_value = cov

    universe_repo = AsyncMock()
    universe_repo.get_asset_ids.return_value = candidate_ids
    if ref_universe is not None:
        universe_repo.get_by_id.return_value = ref_universe
    else:
        universe_repo.get_by_id.return_value = Universe.create_active(name="Ref", description="")

    if ref_asset_ids is not None:
        universe_repo.get_asset_ids.side_effect = lambda uid: (
            ref_asset_ids if uid != uid else candidate_ids
        )

    holdings_repo = AsyncMock()
    if snapshot is not None:
        holdings_repo.get_by_id.return_value = snapshot
    else:
        holdings_repo.get_by_id.return_value = None

    asset_repo = AsyncMock()
    asset_repo.get_by_id.return_value = _make_asset()

    screening_repo = AsyncMock()
    screening_repo.create.side_effect = lambda r: r

    screening_service = MagicMock()
    screening_service.score_candidates.return_value = screening_result or []

    return RunScreeningHandler(
        assumption_repo=assumption_repo,
        universe_repo=universe_repo,
        holdings_repo=holdings_repo,
        asset_repo=asset_repo,
        screening_repo=screening_repo,
        screening_service=screening_service,
    )


# ── RunScreeningCommand validators ──────────────────────────────────────────


def test_command_neither_reference_raises():
    with pytest.raises(ValidationError):
        RunScreeningCommand(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
        )


def test_command_both_references_raises():
    with pytest.raises(ValidationError):
        RunScreeningCommand(
            assumption_id=uuid4(),
            candidate_pool_id=uuid4(),
            reference_snapshot_id=uuid4(),
            reference_universe_id=uuid4(),
        )


def test_command_snapshot_reference_only_valid():
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=uuid4(),
    )
    assert cmd.reference_snapshot_id is not None
    assert cmd.reference_universe_id is None


def test_command_universe_reference_only_valid():
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    assert cmd.reference_universe_id is not None
    assert cmd.reference_snapshot_id is None


# ── RunScreeningHandler error paths ─────────────────────────────────────────


async def test_handle_raises_404_when_assumption_not_found():
    handler = _make_handler()
    handler._assumption_repo.get_by_id.return_value = None
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 404


async def test_handle_raises_422_when_no_covariance():
    handler = _make_handler()
    handler._assumption_repo.get_covariance_matrix.return_value = None
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 422


async def test_handle_raises_422_when_no_candidate_assets():
    handler = _make_handler()
    handler._universe_repo.get_asset_ids.return_value = []
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 422


async def test_handle_raises_404_when_snapshot_not_found():
    handler = _make_handler()
    handler._holdings_repo.get_by_id.return_value = None
    snap_id = uuid4()
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=snap_id,
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 404


async def test_handle_raises_404_when_ref_universe_not_found():
    handler = _make_handler()
    handler._universe_repo.get_by_id.return_value = None
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(cmd)
    assert exc_info.value.status_code == 404


# ── RunScreeningHandler happy paths ─────────────────────────────────────────


async def test_handle_with_universe_reference_calls_score_candidates():
    handler = _make_handler()
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    await handler.handle(cmd)
    handler._screening_service.score_candidates.assert_called_once()


async def test_handle_with_snapshot_reference_calls_score_candidates():
    from types import SimpleNamespace
    from src.domain.models.holdings import HoldingsPosition, HoldingsSnapshot
    from datetime import date
    aid = uuid4()
    sid = uuid4()
    snap = HoldingsSnapshot(
        snapshot_id=sid,
        label="Test",
        snapshot_date=date(2024, 1, 1),
        positions=[HoldingsPosition(snapshot_id=sid, asset_id=aid, weight=1.0)],
    )
    handler = _make_handler()
    handler._holdings_repo.get_by_id.return_value = snap
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_snapshot_id=sid,
    )
    await handler.handle(cmd)
    handler._screening_service.score_candidates.assert_called_once()


async def test_handle_persists_screening_run():
    handler = _make_handler()
    cmd = RunScreeningCommand(
        assumption_id=uuid4(),
        candidate_pool_id=uuid4(),
        reference_universe_id=uuid4(),
    )
    await handler.handle(cmd)
    handler._screening_repo.create.assert_awaited_once()


# ── Helper functions ─────────────────────────────────────────────────────────


def test_extract_cov_asset_ids_returns_unique_ids():
    assumption_id = uuid4()
    a, b = uuid4(), uuid4()
    cov = _make_covariance(assumption_id, [a, b])
    ids = extract_cov_asset_ids(cov)
    assert set(ids) == {a, b}


def test_build_cov_array_is_symmetric():
    assumption_id = uuid4()
    a, b = uuid4(), uuid4()
    cov = _make_covariance(assumption_id, [a, b])
    ids = extract_cov_asset_ids(cov)
    asset_index = {aid: i for i, aid in enumerate(ids)}
    arr = build_cov_array(cov, asset_index)
    np.testing.assert_array_equal(arr, arr.T)


def test_build_cov_array_diagonal_is_variance():
    assumption_id = uuid4()
    a, b = uuid4(), uuid4()
    cov = _make_covariance(assumption_id, [a, b])
    ids = extract_cov_asset_ids(cov)
    asset_index = {aid: i for i, aid in enumerate(ids)}
    arr = build_cov_array(cov, asset_index)
    assert arr[0, 0] == pytest.approx(0.04)
    assert arr[1, 1] == pytest.approx(0.04)
