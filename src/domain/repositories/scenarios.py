"""Scenario repository interface.

ScenarioRepository manages two distinct entity types:
  ScenarioDefinition — reusable named stress scenarios (created once, applied many times)
  ScenarioResult     — the outcome of applying a scenario to a specific optimization run

Because these are two different entities, create_definition() and create_result()
are separate methods rather than a single polymorphic create().  The repository
inherits from Repository[ScenarioDefinition] as the primary entity.
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.scenarios import ScenarioDefinition, ScenarioResult

from .base import Repository


class ScenarioRepository(Repository[ScenarioDefinition]):
    """Read/write interface for scenario definitions and their results."""

    async def get(self, id: UUID) -> ScenarioDefinition | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, scenario_id: UUID) -> ScenarioDefinition | None:
        """Return the scenario definition, or None."""

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[ScenarioDefinition]:
        """Return all scenario definitions ordered by creation time descending."""

    @abstractmethod
    async def create_definition(self, scenario: ScenarioDefinition) -> ScenarioDefinition:
        """Persist a new scenario definition."""

    @abstractmethod
    async def create_result(self, result: ScenarioResult) -> ScenarioResult:
        """Persist the outcome of applying a scenario to an optimization run."""

    @abstractmethod
    async def get_result(self, result_id: UUID) -> ScenarioResult | None:
        """Return the scenario result, or None."""
