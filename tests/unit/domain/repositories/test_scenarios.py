"""Tests for src/domain/repositories/scenarios.py."""

import asyncio
import pytest
from uuid import uuid4

from src.domain.repositories.scenarios import ScenarioRepository


def _concrete() -> ScenarioRepository:
    class _Impl(ScenarioRepository):
        async def get_by_id(self, scenario_id): return "definition"
        async def list(self, limit=50, offset=0): return []
        async def create(self, entity): return entity
        async def update(self, entity): return entity
        async def delete(self, id): return None
        async def create_definition(self, scenario): return scenario
        async def create_result(self, result): return result
        async def get_result(self, result_id): return "result"

    return _Impl()


def test_scenario_repository_is_abstract():
    with pytest.raises(TypeError):
        ScenarioRepository()  # type: ignore[abstract]


def test_scenario_repository_concrete_instantiates():
    assert _concrete() is not None


def test_scenario_repository_get_delegates_to_get_by_id():
    result = asyncio.run(_concrete().get(uuid4()))
    assert result == "definition"


def test_scenario_repository_get_result_returns_value():
    result = asyncio.run(_concrete().get_result(uuid4()))
    assert result == "result"
