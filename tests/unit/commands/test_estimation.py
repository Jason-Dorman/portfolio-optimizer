"""Unit tests for src/commands/estimation.py."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from src.commands.estimation import (
    ComputeReturnsCommand,
    ComputeReturnsHandler,
    CreateAssumptionSetCommand,
    CreateAssumptionSetHandler,
)
from src.domain.models.assets import Universe
from src.domain.models.assumptions import AssumptionSet, AssetStats, CovarianceEntry, CovarianceMatrix
from src.domain.models.enums import (
    AssetClass,
    CovMethod,
    Estimator,
    Frequency,
    Geography,
    ReturnType,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _universe() -> Universe:
    return Universe.create_active(name="Test", description="")


def _returns_cmd(**overrides):
    defaults = dict(
        universe_id=uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
    )
    defaults.update(overrides)
    return ComputeReturnsCommand(**defaults)


def _assumption_cmd(universe_id=None, **overrides):
    defaults = dict(
        universe_id=universe_id or uuid4(),
        lookback_start=date(2023, 1, 1),
        lookback_end=date(2023, 12, 31),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        rf_annual=0.04,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )
    defaults.update(overrides)
    return CreateAssumptionSetCommand(**defaults)


_SENTINEL = object()

def _make_universe_repo(universe=_SENTINEL, asset_ids=_SENTINEL):
    repo = AsyncMock()
    repo.get_by_id.return_value = _universe() if universe is _SENTINEL else universe
    repo.get_asset_ids.return_value = [uuid4(), uuid4()] if asset_ids is _SENTINEL else asset_ids
    return repo


def _make_returns_repo(return_points=None):
    repo = AsyncMock()
    repo.get_returns.return_value = return_points or []
    repo.bulk_insert.return_value = 5
    return repo


def _make_price_repo(bars=None):
    from types import SimpleNamespace
    repo = AsyncMock()
    bar1 = SimpleNamespace(bar_date=date(2023, 1, 3), adj_close=100.0)
    bar2 = SimpleNamespace(bar_date=date(2023, 1, 4), adj_close=101.0)
    repo.get_prices.return_value = bars if bars is not None else [bar1, bar2]
    return repo


def _make_estimation_service(mu=None, sigma=None, psd_ok=True):
    svc = MagicMock()
    idx = pd.to_datetime([date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)])
    returns_df = pd.DataFrame({"asset": [0.01, 0.02, -0.01]}, index=idx)
    svc.compute_returns.return_value = returns_df
    svc.compute_mu.return_value = mu if mu is not None else np.array([0.08, 0.06])
    svc.compute_sigma.return_value = sigma if sigma is not None else np.array([[0.04, 0.01], [0.01, 0.03]])
    svc.validate_psd.return_value = (psd_ok, None)
    svc.repair_psd.return_value = (np.array([[0.04, 0.01], [0.01, 0.03]]), "repaired")
    return svc


# ── ComputeReturnsHandler ───────────────────────────────────────────────────


async def test_compute_returns_raises_404_when_universe_not_found():
    universe_repo = _make_universe_repo(universe=None)
    universe_repo.get_by_id.return_value = None
    handler = ComputeReturnsHandler(
        universe_repo=universe_repo,
        price_repo=_make_price_repo(),
        return_repo=_make_returns_repo(),
        estimation_service=_make_estimation_service(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_returns_cmd())
    assert exc_info.value.status_code == 404


async def test_compute_returns_raises_422_when_no_assets():
    universe_repo = _make_universe_repo(asset_ids=[])  # explicitly empty
    handler = ComputeReturnsHandler(
        universe_repo=universe_repo,
        price_repo=_make_price_repo(),
        return_repo=_make_returns_repo(),
        estimation_service=_make_estimation_service(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_returns_cmd())
    assert exc_info.value.status_code == 422


async def test_compute_returns_skips_asset_with_fewer_than_2_bars():
    from types import SimpleNamespace
    single_bar = [SimpleNamespace(bar_date=date(2023, 1, 2), adj_close=100.0)]
    handler = ComputeReturnsHandler(
        universe_repo=_make_universe_repo(asset_ids=[uuid4()]),
        price_repo=_make_price_repo(bars=single_bar),
        return_repo=_make_returns_repo(),
        estimation_service=_make_estimation_service(),
    )
    result = await handler.handle(_returns_cmd())
    assert len(result.errors) == 1
    assert result.returns_inserted == 0


async def test_compute_returns_happy_path_returns_inserted():
    asset_id = uuid4()
    return_repo = _make_returns_repo()
    return_repo.bulk_insert.return_value = 3
    handler = ComputeReturnsHandler(
        universe_repo=_make_universe_repo(asset_ids=[asset_id]),
        price_repo=_make_price_repo(),
        return_repo=return_repo,
        estimation_service=_make_estimation_service(),
    )
    result = await handler.handle(_returns_cmd())
    assert result.returns_inserted == 3
    assert result.errors == []


async def test_compute_returns_assets_processed_matches_universe():
    asset_ids = [uuid4(), uuid4(), uuid4()]
    handler = ComputeReturnsHandler(
        universe_repo=_make_universe_repo(asset_ids=asset_ids),
        price_repo=_make_price_repo(),
        return_repo=_make_returns_repo(),
        estimation_service=_make_estimation_service(),
    )
    result = await handler.handle(_returns_cmd())
    assert result.assets_processed == 3


async def test_compute_returns_collects_per_asset_errors():
    """An exception during one asset's processing is captured in errors, not raised."""
    asset_ids = [uuid4(), uuid4()]
    price_repo = AsyncMock()
    price_repo.get_prices.side_effect = RuntimeError("DB error")
    handler = ComputeReturnsHandler(
        universe_repo=_make_universe_repo(asset_ids=asset_ids),
        price_repo=price_repo,
        return_repo=_make_returns_repo(),
        estimation_service=_make_estimation_service(),
    )
    result = await handler.handle(_returns_cmd())
    assert len(result.errors) == 2  # both assets fail


# ── CreateAssumptionSetHandler ──────────────────────────────────────────────


def _make_assumption_repo(assumption_set=None):
    repo = AsyncMock()
    assumption_set = assumption_set or AssumptionSet.create(
        universe_id=uuid4(),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        lookback_start=date(2023, 1, 1),
        lookback_end=date(2023, 12, 31),
        rf_annual=0.04,
        estimator=Estimator.HISTORICAL,
        cov_method=CovMethod.SAMPLE,
    )
    repo.create.return_value = assumption_set
    return repo


def _make_returns_repo_with_data(asset_ids):
    from types import SimpleNamespace
    repo = AsyncMock()

    async def get_returns(asset_id, frequency, return_type, start, end):
        return [
            SimpleNamespace(bar_date=date(2023, 1, d + 2), ret=0.01 * (d + 1))
            for d in range(30)
        ]

    repo.get_returns.side_effect = get_returns
    return repo


async def test_assumption_raises_404_when_universe_not_found():
    universe_repo = _make_universe_repo()
    universe_repo.get_by_id.return_value = None
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=_make_returns_repo(),
        assumption_repo=_make_assumption_repo(),
        estimation_service=_make_estimation_service(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_assumption_cmd())
    assert exc_info.value.status_code == 404


async def test_assumption_raises_422_when_no_assets():
    universe_repo = _make_universe_repo(asset_ids=[])
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=_make_returns_repo(),
        assumption_repo=_make_assumption_repo(),
        estimation_service=_make_estimation_service(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_assumption_cmd())
    assert exc_info.value.status_code == 422


async def test_assumption_raises_422_when_no_return_data():
    asset_ids = [uuid4(), uuid4()]
    universe_repo = _make_universe_repo(asset_ids=asset_ids)
    # No return points for either asset
    return_repo = _make_returns_repo(return_points=[])
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=return_repo,
        assumption_repo=_make_assumption_repo(),
        estimation_service=_make_estimation_service(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await handler.handle(_assumption_cmd())
    assert exc_info.value.status_code == 422


async def test_assumption_happy_path_calls_repo_create():
    asset_ids = [uuid4(), uuid4()]
    universe_repo = _make_universe_repo(asset_ids=asset_ids)
    return_repo = _make_returns_repo_with_data(asset_ids)
    assumption_repo = _make_assumption_repo()
    estimation_svc = _make_estimation_service()
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=return_repo,
        assumption_repo=assumption_repo,
        estimation_service=estimation_svc,
    )
    await handler.handle(_assumption_cmd())
    assumption_repo.create.assert_awaited_once()


async def test_assumption_no_psd_repair_when_matrix_valid():
    asset_ids = [uuid4(), uuid4()]
    universe_repo = _make_universe_repo(asset_ids=asset_ids)
    return_repo = _make_returns_repo_with_data(asset_ids)
    estimation_svc = _make_estimation_service(psd_ok=True)
    assumption_repo = _make_assumption_repo()
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=return_repo,
        assumption_repo=assumption_repo,
        estimation_service=estimation_svc,
    )
    await handler.handle(_assumption_cmd())
    estimation_svc.repair_psd.assert_not_called()


async def test_assumption_psd_repair_applied_when_invalid():
    asset_ids = [uuid4(), uuid4()]
    universe_repo = _make_universe_repo(asset_ids=asset_ids)
    return_repo = _make_returns_repo_with_data(asset_ids)
    estimation_svc = _make_estimation_service(psd_ok=False)
    assumption_repo = _make_assumption_repo()
    handler = CreateAssumptionSetHandler(
        universe_repo=universe_repo,
        return_repo=return_repo,
        assumption_repo=assumption_repo,
        estimation_service=estimation_svc,
    )
    await handler.handle(_assumption_cmd())
    estimation_svc.repair_psd.assert_called_once()
