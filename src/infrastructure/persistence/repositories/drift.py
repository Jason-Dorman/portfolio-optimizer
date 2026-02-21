"""SQLAlchemy implementation of DriftRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.models.drift import (
    DriftCheck as DomainDriftCheck,
    DriftPosition as DomainDriftPosition,
)
from src.domain.repositories.drift import DriftRepository
from src.infrastructure.persistence.models.drift import (
    DriftCheck as OrmDriftCheck,
    DriftCheckPosition as OrmDriftPosition,
)


def _position_to_domain(row: OrmDriftPosition) -> DomainDriftPosition:
    return DomainDriftPosition(
        drift_id=row.drift_id,
        asset_id=row.asset_id,
        target_weight=row.target_weight,
        current_weight=row.current_weight,
        drift_abs=row.drift_abs,
        breached=row.breached,
        explanation=row.explanation,
    )


def _check_to_domain(
    row: OrmDriftCheck, positions: list[DomainDriftPosition]
) -> DomainDriftCheck:
    return DomainDriftCheck(
        drift_id=row.drift_id,
        run_id=row.run_id,
        check_date=row.check_date,
        threshold_pct=row.threshold_pct,
        any_breach=row.any_breach,
        created_at=row.created_at,
        positions=positions,
    )


class SqlDriftRepository(DriftRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, drift_id: UUID) -> DomainDriftCheck | None:
        stmt = (
            select(OrmDriftCheck)
            .options(selectinload(OrmDriftCheck.positions))
            .where(OrmDriftCheck.drift_id == drift_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        positions = [_position_to_domain(p) for p in row.positions]
        return _check_to_domain(row, positions)

    async def list(self, limit: int = 50, offset: int = 0) -> list[DomainDriftCheck]:
        # Returns header checks without positions. Use get_by_id() for full data.
        stmt = (
            select(OrmDriftCheck)
            .order_by(OrmDriftCheck.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_check_to_domain(row, []) for row in result.scalars()]

    async def create(self, entity: DomainDriftCheck) -> DomainDriftCheck:
        check_row = OrmDriftCheck(
            drift_id=entity.drift_id,
            run_id=entity.run_id,
            check_date=entity.check_date,
            threshold_pct=entity.threshold_pct,
            any_breach=entity.any_breach,
            created_at=entity.created_at,
        )
        position_rows = [
            OrmDriftPosition(
                drift_id=entity.drift_id,
                asset_id=p.asset_id,
                target_weight=p.target_weight,
                current_weight=p.current_weight,
                drift_abs=p.drift_abs,
                breached=p.breached,
                explanation=p.explanation,
            )
            for p in entity.positions
        ]
        self._session.add(check_row)
        self._session.add_all(position_rows)
        return entity

    async def update(self, entity: DomainDriftCheck) -> DomainDriftCheck:
        raise NotImplementedError("DriftChecks are append-only")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("DriftChecks are append-only")

    async def get_positions(self, drift_id: UUID) -> list[DomainDriftPosition]:
        stmt = select(OrmDriftPosition).where(OrmDriftPosition.drift_id == drift_id)
        result = await self._session.execute(stmt)
        return [_position_to_domain(row) for row in result.scalars()]