"""SQLAlchemy implementation of PriceRepository."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.enums import Frequency
from src.domain.models.market_data import PriceBar as DomainPriceBar
from src.domain.repositories.prices import PriceRepository
from src.infrastructure.persistence.models.market_data import PriceBar as OrmPriceBar


class SqlPriceRepository(PriceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: OrmPriceBar) -> DomainPriceBar:
        return DomainPriceBar(
            asset_id=row.asset_id,
            bar_date=row.bar_date,
            frequency=Frequency(row.frequency),
            adj_close=row.adj_close,
            close=row.close,
            volume=row.volume,
            pulled_at=row.pulled_at,
            vendor_id=row.vendor_id,
        )

    async def get_prices(
        self,
        asset_id: UUID,
        frequency: Frequency,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DomainPriceBar]:
        stmt = (
            select(OrmPriceBar)
            .where(
                OrmPriceBar.asset_id == asset_id,
                OrmPriceBar.frequency == frequency.value,
            )
            .order_by(OrmPriceBar.bar_date.asc())
        )
        if start is not None:
            stmt = stmt.where(OrmPriceBar.bar_date >= start)
        if end is not None:
            stmt = stmt.where(OrmPriceBar.bar_date <= end)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def get_latest_date(self, asset_id: UUID, frequency: Frequency) -> date | None:
        stmt = select(func.max(OrmPriceBar.bar_date)).where(
            OrmPriceBar.asset_id == asset_id,
            OrmPriceBar.frequency == frequency.value,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_insert(self, bars: list[DomainPriceBar]) -> int:
        if not bars:
            return 0
        missing_vendor = [b for b in bars if b.vendor_id is None]
        if missing_vendor:
            raise ValueError(
                f"{len(missing_vendor)} bar(s) have no vendor_id — "
                "vendor_id is required for persistence"
            )
        values = [
            {
                "asset_id": b.asset_id,
                "vendor_id": b.vendor_id,
                "bar_date": b.bar_date,
                "frequency": b.frequency.value,
                "adj_close": b.adj_close,
                "close": b.close,
                "volume": b.volume,
                "pulled_at": b.pulled_at,
            }
            for b in bars
        ]
        stmt = pg_insert(OrmPriceBar).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["asset_id", "vendor_id", "bar_date", "frequency"],
            set_={
                "adj_close": stmt.excluded.adj_close,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "pulled_at": stmt.excluded.pulled_at,
            },
        )
        result = await self._session.execute(stmt)
        return result.rowcount
