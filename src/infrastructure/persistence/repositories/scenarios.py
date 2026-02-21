"""SQLAlchemy implementation of ScenarioRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.scenarios import (
    ScenarioDefinition as DomainScenarioDef,
    ScenarioResult as DomainScenarioResult,
)
from src.domain.repositories.scenarios import ScenarioRepository
from src.infrastructure.persistence.models.risk import (
    ScenarioDefinition as OrmScenarioDef,
    ScenarioResult as OrmScenarioResult,
)


class SqlScenarioRepository(ScenarioRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _def_to_domain(row: OrmScenarioDef) -> DomainScenarioDef:
        return DomainScenarioDef(
            scenario_id=row.scenario_id,
            name=row.name,
            shocks=row.shocks,
            created_at=row.created_at,
        )

    @staticmethod
    def _result_to_domain(row: OrmScenarioResult) -> DomainScenarioResult:
        return DomainScenarioResult(
            result_id=row.result_id,
            run_id=row.run_id,
            scenario_id=row.scenario_id,
            shocked_return=row.shocked_return,
            shocked_vol=row.shocked_vol,
            created_at=row.created_at,
        )

    async def get_by_id(self, scenario_id: UUID) -> DomainScenarioDef | None:
        stmt = select(OrmScenarioDef).where(OrmScenarioDef.scenario_id == scenario_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._def_to_domain(row) if row else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[DomainScenarioDef]:
        stmt = (
            select(OrmScenarioDef)
            .order_by(OrmScenarioDef.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._def_to_domain(row) for row in result.scalars()]

    async def create_definition(self, scenario: DomainScenarioDef) -> DomainScenarioDef:
        row = OrmScenarioDef(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            shocks=scenario.shocks,
            created_at=scenario.created_at,
        )
        self._session.add(row)
        return scenario

    async def create_result(self, result: DomainScenarioResult) -> DomainScenarioResult:
        row = OrmScenarioResult(
            result_id=result.result_id,
            run_id=result.run_id,
            scenario_id=result.scenario_id,
            shocked_return=result.shocked_return,
            shocked_vol=result.shocked_vol,
            created_at=result.created_at,
        )
        self._session.add(row)
        return result

    async def get_result(self, result_id: UUID) -> DomainScenarioResult | None:
        stmt = select(OrmScenarioResult).where(OrmScenarioResult.result_id == result_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._result_to_domain(row) if row else None

    async def create(self, entity: DomainScenarioDef) -> DomainScenarioDef:
        raise NotImplementedError("Use create_definition() for ScenarioDefinition")

    async def update(self, entity: DomainScenarioDef) -> DomainScenarioDef:
        raise NotImplementedError("ScenarioDefinitions are immutable")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("ScenarioDefinitions are immutable")
