"""SQLAlchemy implementation of AssetRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.assets import Asset as DomainAsset
from src.domain.models.enums import AssetClass, Geography
from src.domain.repositories.assets import AssetRepository
from src.infrastructure.persistence.models.reference import Asset as OrmAsset


class SqlAssetRepository(AssetRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: OrmAsset) -> DomainAsset:
        return DomainAsset(
            asset_id=row.asset_id,
            ticker=row.ticker,
            name=row.name,
            asset_class=AssetClass(row.asset_class),
            sub_class=row.sub_class,
            sector=row.sector,
            geography=Geography(row.geography),
            currency=row.currency,
            is_etf=row.is_etf,
            created_at=row.created_at,
        )

    async def get_by_id(self, asset_id: UUID) -> DomainAsset | None:
        stmt = select(OrmAsset).where(OrmAsset.asset_id == asset_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_ticker(self, ticker: str) -> DomainAsset | None:
        stmt = select(OrmAsset).where(func.lower(OrmAsset.ticker) == ticker.lower())
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list(
        self,
        ticker: str | None = None,
        asset_class: AssetClass | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainAsset]:
        stmt = select(OrmAsset).order_by(OrmAsset.created_at.desc()).limit(limit).offset(offset)
        if ticker is not None:
            stmt = stmt.where(func.lower(OrmAsset.ticker).startswith(ticker.lower()))
        if asset_class is not None:
            stmt = stmt.where(OrmAsset.asset_class == asset_class.value)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def create(self, entity: DomainAsset) -> DomainAsset:
        row = OrmAsset(
            asset_id=entity.asset_id,
            ticker=entity.ticker,
            name=entity.name,
            asset_class=entity.asset_class.value,
            sub_class=entity.sub_class,
            sector=entity.sector,
            geography=entity.geography.value,
            currency=entity.currency,
            is_etf=entity.is_etf,
            created_at=entity.created_at,
        )
        self._session.add(row)
        return entity

    async def update(self, entity: DomainAsset) -> DomainAsset:
        stmt = select(OrmAsset).where(OrmAsset.asset_id == entity.asset_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"Asset {entity.asset_id} not found")
        row.ticker = entity.ticker
        row.name = entity.name
        row.asset_class = entity.asset_class.value
        row.sub_class = entity.sub_class
        row.sector = entity.sector
        row.geography = entity.geography.value
        row.currency = entity.currency
        row.is_etf = entity.is_etf
        return entity

    async def delete(self, id: UUID) -> None:
        stmt = select(OrmAsset).where(OrmAsset.asset_id == id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
