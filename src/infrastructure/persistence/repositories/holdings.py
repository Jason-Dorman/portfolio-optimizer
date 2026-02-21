"""SQLAlchemy implementation of HoldingsRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.models.holdings import HoldingsPosition as DomainPosition
from src.domain.models.holdings import HoldingsSnapshot as DomainSnapshot
from src.domain.repositories.holdings import HoldingsRepository
from src.infrastructure.persistence.models.holdings import (
    CurrentHoldingsPosition as OrmPosition,
)
from src.infrastructure.persistence.models.holdings import (
    CurrentHoldingsSnapshot as OrmSnapshot,
)


def _position_to_domain(pos: OrmPosition) -> DomainPosition:
    return DomainPosition(
        snapshot_id=pos.snapshot_id,
        asset_id=pos.asset_id,
        weight=pos.weight,
        market_value=pos.market_value,
    )


def _snapshot_to_domain(row: OrmSnapshot, include_positions: bool = True) -> DomainSnapshot:
    positions = [_position_to_domain(p) for p in row.positions] if include_positions else []
    return DomainSnapshot(
        snapshot_id=row.snapshot_id,
        label=row.label,
        snapshot_date=row.snapshot_date,
        created_at=row.created_at,
        positions=positions,
    )


class SqlHoldingsRepository(HoldingsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, snapshot_id: UUID) -> DomainSnapshot | None:
        stmt = (
            select(OrmSnapshot)
            .options(selectinload(OrmSnapshot.positions))
            .where(OrmSnapshot.snapshot_id == snapshot_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _snapshot_to_domain(row) if row else None

    async def get_latest(self) -> DomainSnapshot | None:
        stmt = (
            select(OrmSnapshot)
            .options(selectinload(OrmSnapshot.positions))
            .order_by(OrmSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _snapshot_to_domain(row) if row else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[DomainSnapshot]:
        # Returns header snapshots without positions for efficiency.
        # Use get_by_id() to load the full aggregate.
        stmt = (
            select(OrmSnapshot)
            .options(selectinload(OrmSnapshot.positions))
            .order_by(OrmSnapshot.snapshot_date.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_snapshot_to_domain(row, include_positions=False) for row in result.scalars()]

    async def create(self, entity: DomainSnapshot) -> DomainSnapshot:
        row = OrmSnapshot(
            snapshot_id=entity.snapshot_id,
            label=entity.label,
            snapshot_date=entity.snapshot_date,
            created_at=entity.created_at,
        )
        position_rows = [
            OrmPosition(
                snapshot_id=entity.snapshot_id,
                asset_id=p.asset_id,
                weight=p.weight,
                market_value=p.market_value,
            )
            for p in entity.positions
        ]
        self._session.add(row)
        self._session.add_all(position_rows)
        return entity

    async def update(self, entity: DomainSnapshot) -> DomainSnapshot:
        raise NotImplementedError("Holdings snapshots are append-only")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("Holdings snapshots are append-only")
