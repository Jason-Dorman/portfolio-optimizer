"""Unit tests for src/commands/universes.py."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.commands.universes import (
    AddUniverseAssetsCommand,
    AddUniverseAssetsHandler,
    CreateUniverseCommand,
    CreateUniverseHandler,
    RemoveUniverseAssetsCommand,
    RemoveUniverseAssetsHandler,
)
from src.domain.models.assets import Universe
from src.domain.models.enums import UniverseType


def _make_universe(**overrides) -> Universe:
    defaults = dict(name="Core ETFs", description="", universe_type=UniverseType.ACTIVE)
    defaults.update(overrides)
    return Universe(**defaults)


def _make_repo(universe=None, created_universe=None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = universe
    repo.create.return_value = created_universe or _make_universe()
    repo.add_assets.side_effect = lambda uid, aids, is_benchmark=False: _make_universe()
    repo.remove_assets.side_effect = lambda uid, aids: _make_universe()
    return repo


# ── CreateUniverseHandler ───────────────────────────────────────────────────


async def test_create_active_universe_sets_correct_type():
    repo = _make_repo()
    created = []
    repo.create.side_effect = lambda u: (created.append(u), u)[1]
    cmd = CreateUniverseCommand(name="Core", description="", universe_type=UniverseType.ACTIVE)
    await CreateUniverseHandler(universe_repo=repo).handle(cmd)
    assert created[0].universe_type == UniverseType.ACTIVE


async def test_create_candidate_pool_sets_correct_type():
    repo = _make_repo()
    created = []
    repo.create.side_effect = lambda u: (created.append(u), u)[1]
    cmd = CreateUniverseCommand(
        name="Pool", description="", universe_type=UniverseType.CANDIDATE_POOL
    )
    await CreateUniverseHandler(universe_repo=repo).handle(cmd)
    assert created[0].universe_type == UniverseType.CANDIDATE_POOL


async def test_create_without_asset_ids_does_not_call_add_assets():
    repo = _make_repo()
    cmd = CreateUniverseCommand(name="x", description="", universe_type=UniverseType.ACTIVE)
    await CreateUniverseHandler(universe_repo=repo).handle(cmd)
    repo.add_assets.assert_not_awaited()


async def test_create_with_asset_ids_calls_add_assets():
    created_universe = _make_universe()
    repo = _make_repo(created_universe=created_universe)
    asset_ids = [uuid4(), uuid4()]
    cmd = CreateUniverseCommand(
        name="x", description="", universe_type=UniverseType.ACTIVE, asset_ids=asset_ids
    )
    await CreateUniverseHandler(universe_repo=repo).handle(cmd)
    repo.add_assets.assert_awaited_once_with(created_universe.universe_id, asset_ids)


async def test_create_returns_universe():
    expected = _make_universe()
    repo = _make_repo(created_universe=expected)
    cmd = CreateUniverseCommand(name="x", description="", universe_type=UniverseType.ACTIVE)
    result = await CreateUniverseHandler(universe_repo=repo).handle(cmd)
    assert result is expected


# ── AddUniverseAssetsHandler ────────────────────────────────────────────────


async def test_add_assets_raises_404_when_universe_not_found():
    repo = _make_repo(universe=None)
    cmd = AddUniverseAssetsCommand(asset_ids=[uuid4()])
    with pytest.raises(HTTPException) as exc_info:
        await AddUniverseAssetsHandler(universe_repo=repo).handle(uuid4(), cmd)
    assert exc_info.value.status_code == 404


async def test_add_assets_calls_add_assets_on_repo():
    universe = _make_universe()
    repo = _make_repo(universe=universe)
    asset_ids = [uuid4()]
    cmd = AddUniverseAssetsCommand(asset_ids=asset_ids, is_benchmark=False)
    await AddUniverseAssetsHandler(universe_repo=repo).handle(universe.universe_id, cmd)
    repo.add_assets.assert_awaited_once_with(universe.universe_id, asset_ids, False)


async def test_add_assets_passes_is_benchmark_flag():
    universe = _make_universe()
    repo = _make_repo(universe=universe)
    cmd = AddUniverseAssetsCommand(asset_ids=[uuid4()], is_benchmark=True)
    await AddUniverseAssetsHandler(universe_repo=repo).handle(universe.universe_id, cmd)
    _, _, is_benchmark = repo.add_assets.call_args.args
    assert is_benchmark is True


# ── RemoveUniverseAssetsHandler ─────────────────────────────────────────────


async def test_remove_assets_raises_404_when_universe_not_found():
    repo = _make_repo(universe=None)
    cmd = RemoveUniverseAssetsCommand(asset_ids=[uuid4()])
    with pytest.raises(HTTPException) as exc_info:
        await RemoveUniverseAssetsHandler(universe_repo=repo).handle(uuid4(), cmd)
    assert exc_info.value.status_code == 404


async def test_remove_assets_calls_remove_assets_on_repo():
    universe = _make_universe()
    repo = _make_repo(universe=universe)
    asset_ids = [uuid4()]
    cmd = RemoveUniverseAssetsCommand(asset_ids=asset_ids)
    await RemoveUniverseAssetsHandler(universe_repo=repo).handle(universe.universe_id, cmd)
    repo.remove_assets.assert_awaited_once_with(universe.universe_id, asset_ids)
