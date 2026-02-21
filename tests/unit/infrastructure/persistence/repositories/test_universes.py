"""Tests for SqlUniverseRepository — mapping and session interaction."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.models.assets import Universe
from src.domain.models.enums import UniverseType
from src.infrastructure.persistence.repositories.universes import SqlUniverseRepository


def _orm_universe(**overrides):
    defaults = {
        "universe_id": uuid4(),
        "name": "Core ETFs",
        "description": "Core portfolio universe",
        "universe_type": "active",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_session(scalar_result=None):
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=scalar_result)
    )
    return session


# --- _to_domain mapping ---

def test_to_domain_maps_name():
    assert SqlUniverseRepository._to_domain(_orm_universe(name="My Universe")).name == "My Universe"


def test_to_domain_maps_universe_type_enum():
    result = SqlUniverseRepository._to_domain(_orm_universe(universe_type="candidate_pool"))
    assert result.universe_type == UniverseType.CANDIDATE_POOL


def test_to_domain_maps_description():
    result = SqlUniverseRepository._to_domain(_orm_universe(description="Test desc"))
    assert result.description == "Test desc"


# --- session interaction ---

async def test_get_by_id_returns_none_when_not_found():
    repo = SqlUniverseRepository(_mock_session(scalar_result=None))
    assert await repo.get_by_id(uuid4()) is None


async def test_update_raises_when_universe_not_found():
    repo = SqlUniverseRepository(_mock_session(scalar_result=None))
    entity = Universe(name="X", description="Y", universe_type=UniverseType.ACTIVE)
    with pytest.raises(ValueError):
        await repo.update(entity)
