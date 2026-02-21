"""SQLAlchemy implementation of ReturnRepository."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.enums import Frequency, ReturnType
from src.domain.models.market_data import ReturnPoint as DomainReturnPoint
from src.domain.repositories.returns import ReturnRepository
from src.infrastructure.persistence.models.market_data import ReturnSeries as OrmReturnSeries


class SqlReturnRepository(ReturnRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: OrmReturnSeries) -> DomainReturnPoint:
        return DomainReturnPoint(
            asset_id=row.asset_id,
            bar_date=row.bar_date,
            frequency=Frequency(row.frequency),
            return_type=ReturnType(row.return_type),
            ret=row.ret,
        )

    async def get_returns(
        self,
        asset_id: UUID,
        frequency: Frequency,
        return_type: ReturnType,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DomainReturnPoint]:
        stmt = (
            select(OrmReturnSeries)
            .where(
                OrmReturnSeries.asset_id == asset_id,
                OrmReturnSeries.frequency == frequency.value,
                OrmReturnSeries.return_type == return_type.value,
            )
            .order_by(OrmReturnSeries.bar_date.asc())
        )
        if start is not None:
            stmt = stmt.where(OrmReturnSeries.bar_date >= start)
        if end is not None:
            stmt = stmt.where(OrmReturnSeries.bar_date <= end)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def bulk_insert(self, points: list[DomainReturnPoint]) -> int:
        if not points:
            return 0
        values = [
            {
                "asset_id": p.asset_id,
                "bar_date": p.bar_date,
                "frequency": p.frequency.value,
                "return_type": p.return_type.value,
                "ret": p.ret,
            }
            for p in points
        ]
        stmt = pg_insert(OrmReturnSeries).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["asset_id", "bar_date", "frequency", "return_type"],
            set_={"ret": stmt.excluded.ret},
        )
        result = await self._session.execute(stmt)
        return result.rowcount