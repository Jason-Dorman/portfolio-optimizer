"""SQLAlchemy implementation of RiskFreeRepository."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.risk_free import RiskFreeRepository
from src.infrastructure.persistence.models.market_data import RiskFreeSeries as OrmRiskFree


class SqlRiskFreeRepository(RiskFreeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(
        self,
        source: str,
        series_code: str,
        observations: list[tuple[date, float]],
    ) -> int:
        if not observations:
            return 0
        values = [
            {
                "source": source,
                "series_code": series_code,
                "obs_date": obs_date,
                "rf_annual": rate,
            }
            for obs_date, rate in observations
        ]
        stmt = pg_insert(OrmRiskFree).values(values)
        stmt = stmt.on_conflict_do_update(
            # Upsert on the natural key (source, series_code, obs_date).
            # series_id is a surrogate PK; the unique constraint is on
            # (source, series_code, obs_date) which must exist in the schema.
            index_elements=["source", "series_code", "obs_date"],
            set_={"rf_annual": stmt.excluded.rf_annual},
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def get_rate_on(
        self,
        obs_date: date,
        series_code: str = "DTB3",
    ) -> float | None:
        stmt = (
            select(OrmRiskFree.rf_annual)
            .where(
                OrmRiskFree.series_code == series_code,
                OrmRiskFree.obs_date <= obs_date,
            )
            .order_by(OrmRiskFree.obs_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_rate(self, series_code: str = "DTB3") -> float | None:
        stmt = (
            select(OrmRiskFree.rf_annual)
            .where(OrmRiskFree.series_code == series_code)
            .order_by(OrmRiskFree.obs_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
