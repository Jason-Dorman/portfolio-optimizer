"""SQLAlchemy implementation of UniverseRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.assets import Universe as DomainUniverse
from src.domain.models.enums import UniverseType
from src.domain.repositories.universes import UniverseRepository
from src.infrastructure.persistence.models.reference import Universe as OrmUniverse
from src.infrastructure.persistence.models.reference import UniverseAsset as OrmUniverseAsset


class SqlUniverseRepository(UniverseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: OrmUniverse) -> DomainUniverse:
        return DomainUniverse(
            universe_id=row.universe_id,
            name=row.name,
            description=row.description,
            universe_type=UniverseType(row.universe_type),
            created_at=row.created_at,
        )

    async def get_by_id(self, universe_id: UUID) -> DomainUniverse | None:
        stmt = select(OrmUniverse).where(OrmUniverse.universe_id == universe_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list(
        self,
        universe_type: UniverseType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainUniverse]:
        stmt = (
            select(OrmUniverse)
            .order_by(OrmUniverse.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if universe_type is not None:
            stmt = stmt.where(OrmUniverse.universe_type == universe_type.value)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def create(self, entity: DomainUniverse) -> DomainUniverse:
        row = OrmUniverse(
            universe_id=entity.universe_id,
            name=entity.name,
            description=entity.description,
            universe_type=entity.universe_type.value,
            created_at=entity.created_at,
        )
        self._session.add(row)
        return entity

    async def update(self, entity: DomainUniverse) -> DomainUniverse:
        stmt = select(OrmUniverse).where(OrmUniverse.universe_id == entity.universe_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"Universe {entity.universe_id} not found")
        row.name = entity.name
        row.description = entity.description
        row.universe_type = entity.universe_type.value
        return entity

    async def delete(self, id: UUID) -> None:
        stmt = select(OrmUniverse).where(OrmUniverse.universe_id == id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)

    async def add_assets(
        self,
        universe_id: UUID,
        asset_ids: list[UUID],
        is_benchmark: bool = False,
    ) -> DomainUniverse:
        for asset_id in asset_ids:
            row = OrmUniverseAsset(
                universe_id=universe_id,
                asset_id=asset_id,
                is_benchmark=is_benchmark,
            )
            self._session.add(row)
        await self._session.flush()
        universe = await self.get_by_id(universe_id)
        if universe is None:
            raise ValueError(f"Universe {universe_id} not found")
        return universe

    async def remove_assets(
        self,
        universe_id: UUID,
        asset_ids: list[UUID],
    ) -> DomainUniverse:
        stmt = delete(OrmUniverseAsset).where(
            OrmUniverseAsset.universe_id == universe_id,
            OrmUniverseAsset.asset_id.in_(asset_ids),
        )
        await self._session.execute(stmt)
        universe = await self.get_by_id(universe_id)
        if universe is None:
            raise ValueError(f"Universe {universe_id} not found")
        return universe
