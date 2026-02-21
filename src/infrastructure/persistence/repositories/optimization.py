"""SQLAlchemy implementation of OptimizationRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.models.enums import Objective, OptimizationStatus, RunType
from src.domain.models.optimization import (
    OptimizationConstraints,
    OptimizationResult as DomainOptResult,
    OptimizationRun as DomainOptRun,
    PortfolioWeight as DomainWeight,
)
from src.domain.repositories.optimization import OptimizationRepository
from src.infrastructure.persistence.models.estimation import (
    AssumptionSet as OrmAssumptionSet,
)
from src.infrastructure.persistence.models.optimization import (
    OptimizationResult as OrmOptResult,
    OptimizationRun as OrmOptRun,
    OptimizationWeight as OrmOptWeight,
)


def _weight_to_domain(row: OrmOptWeight) -> DomainWeight:
    return DomainWeight(
        run_id=row.run_id,
        asset_id=row.asset_id,
        weight=row.weight,
        mcr=row.mcr,
        crc=row.crc,
        prc=row.prc,
    )


def _result_to_domain(row: OrmOptResult) -> DomainOptResult:
    return DomainOptResult(
        run_id=row.run_id,
        exp_return=row.exp_return,
        variance=row.variance,
        stdev=row.stdev,
        sharpe=row.sharpe,
        hhi=row.hhi,
        effective_n=row.effective_n,
        explanation=row.explanation,
    )


def _run_to_domain(row: OrmOptRun) -> DomainOptRun:
    constraints = OptimizationConstraints.model_validate(row.constraints)
    result = _result_to_domain(row.result) if row.result is not None else None
    weights = [_weight_to_domain(w) for w in row.weights]
    return DomainOptRun(
        run_id=row.run_id,
        assumption_id=row.assumption_id,
        run_type=RunType(row.run_type),
        objective=Objective(row.objective),
        constraints=constraints,
        reference_snapshot_id=row.reference_snapshot_id,
        target_return=row.target_return,
        status=OptimizationStatus(row.status),
        infeasibility_reason=row.infeasibility_reason,
        solver_meta=row.solver_meta,
        created_at=row.created_at,
        weights=weights,
        result=result,
    )


def _with_relations() -> list:
    return [selectinload(OrmOptRun.weights), selectinload(OrmOptRun.result)]


class SqlOptimizationRepository(OptimizationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, run_id: UUID) -> DomainOptRun | None:
        stmt = (
            select(OrmOptRun)
            .options(*_with_relations())
            .where(OrmOptRun.run_id == run_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _run_to_domain(row) if row else None

    async def list(
        self,
        assumption_id: UUID | None = None,
        status: OptimizationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainOptRun]:
        # Returns header runs without weights for efficiency. Use get_by_id() for full data.
        stmt = (
            select(OrmOptRun)
            .options(selectinload(OrmOptRun.result))
            .order_by(OrmOptRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if assumption_id is not None:
            stmt = stmt.where(OrmOptRun.assumption_id == assumption_id)
        if status is not None:
            stmt = stmt.where(OrmOptRun.status == status.value)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        # Build domain runs with empty weights (list() is a header operation)
        domain_runs = []
        for row in rows:
            run = _run_to_domain(row)
            # Replace weights with empty list since we didn't load them
            domain_runs.append(
                run.model_copy(update={"weights": []})
            )
        return domain_runs

    async def create(self, entity: DomainOptRun) -> DomainOptRun:
        run_row = OrmOptRun(
            run_id=entity.run_id,
            assumption_id=entity.assumption_id,
            run_type=entity.run_type.value,
            objective=entity.objective.value,
            constraints=entity.constraints.model_dump(mode="json"),
            reference_snapshot_id=entity.reference_snapshot_id,
            target_return=entity.target_return,
            status=entity.status.value,
            infeasibility_reason=entity.infeasibility_reason,
            solver_meta=entity.solver_meta,
            created_at=entity.created_at,
        )
        self._session.add(run_row)

        if entity.result is not None:
            result_row = OrmOptResult(
                run_id=entity.run_id,
                exp_return=entity.result.exp_return,
                variance=entity.result.variance,
                stdev=entity.result.stdev,
                sharpe=entity.result.sharpe,
                hhi=entity.result.hhi,
                effective_n=entity.result.effective_n,
                explanation=entity.result.explanation,
            )
            self._session.add(result_row)

        weight_rows = [
            OrmOptWeight(
                run_id=entity.run_id,
                asset_id=w.asset_id,
                weight=w.weight,
                mcr=w.mcr,
                crc=w.crc,
                prc=w.prc,
            )
            for w in entity.weights
        ]
        self._session.add_all(weight_rows)
        return entity

    async def update(self, entity: DomainOptRun) -> DomainOptRun:
        raise NotImplementedError("OptimizationRuns are immutable")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("OptimizationRuns are immutable")

    async def get_weights(self, run_id: UUID) -> list[DomainWeight]:
        stmt = select(OrmOptWeight).where(OrmOptWeight.run_id == run_id)
        result = await self._session.execute(stmt)
        return [_weight_to_domain(row) for row in result.scalars()]

    async def get_latest_for_universe(self, universe_id: UUID) -> DomainOptRun | None:
        stmt = (
            select(OrmOptRun)
            .options(*_with_relations())
            .join(OrmAssumptionSet, OrmOptRun.assumption_id == OrmAssumptionSet.assumption_id)
            .where(
                OrmAssumptionSet.universe_id == universe_id,
                OrmOptRun.status == OptimizationStatus.SUCCESS.value,
            )
            .order_by(OrmOptRun.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _run_to_domain(row) if row else None