"""SQLAlchemy implementation of AssumptionRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.assumptions import (
    AssetStats as DomainAssetStats,
    AssumptionSet as DomainAssumptionSet,
    CorrelationEntry,
    CorrelationMatrix,
    CovarianceEntry,
    CovarianceMatrix,
)
from src.domain.models.enums import CovMethod, Estimator, Frequency, ReturnType
from src.domain.repositories.assumptions import AssumptionRepository
from src.infrastructure.persistence.models.estimation import (
    AssumptionAssetStat as OrmAssetStat,
    AssumptionCov as OrmAssumptionCov,
    AssumptionSet as OrmAssumptionSet,
)


class SqlAssumptionRepository(AssumptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: OrmAssumptionSet) -> DomainAssumptionSet:
        return DomainAssumptionSet(
            assumption_id=row.assumption_id,
            universe_id=row.universe_id,
            frequency=Frequency(row.frequency),
            return_type=ReturnType(row.return_type),
            lookback_start=row.lookback_start,
            lookback_end=row.lookback_end,
            annualization_factor=row.annualization_factor,
            rf_annual=row.rf_annual,
            estimator=Estimator(row.estimator),
            cov_method=CovMethod(row.cov_method),
            psd_repair_applied=row.psd_repair_applied,
            psd_repair_note=row.psd_repair_note,
            created_at=row.created_at,
        )

    async def get_by_id(self, assumption_id: UUID) -> DomainAssumptionSet | None:
        stmt = select(OrmAssumptionSet).where(
            OrmAssumptionSet.assumption_id == assumption_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list(
        self,
        universe_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainAssumptionSet]:
        stmt = (
            select(OrmAssumptionSet)
            .order_by(OrmAssumptionSet.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if universe_id is not None:
            stmt = stmt.where(OrmAssumptionSet.universe_id == universe_id)
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars()]

    async def create(  # type: ignore[override]
        self,
        assumption_set: DomainAssumptionSet,
        stats: list[DomainAssetStats],
        covariance: CovarianceMatrix,
    ) -> DomainAssumptionSet:
        set_row = OrmAssumptionSet(
            assumption_id=assumption_set.assumption_id,
            universe_id=assumption_set.universe_id,
            frequency=assumption_set.frequency.value,
            return_type=assumption_set.return_type.value,
            lookback_start=assumption_set.lookback_start,
            lookback_end=assumption_set.lookback_end,
            annualization_factor=assumption_set.annualization_factor,
            rf_annual=assumption_set.rf_annual,
            estimator=assumption_set.estimator.value,
            cov_method=assumption_set.cov_method.value,
            psd_repair_applied=assumption_set.psd_repair_applied,
            psd_repair_note=assumption_set.psd_repair_note,
            created_at=assumption_set.created_at,
        )
        stat_rows = [
            OrmAssetStat(
                assumption_id=s.assumption_id,
                asset_id=s.asset_id,
                mu_annual=s.mu_annual,
                sigma_annual=s.sigma_annual,
            )
            for s in stats
        ]
        cov_rows = [
            OrmAssumptionCov(
                assumption_id=e.assumption_id,
                asset_id_i=e.asset_id_i,
                asset_id_j=e.asset_id_j,
                cov_annual=e.cov_annual,
            )
            for e in covariance.entries
        ]
        self._session.add(set_row)
        self._session.add_all(stat_rows)
        self._session.add_all(cov_rows)
        return assumption_set

    async def update(self, entity: DomainAssumptionSet) -> DomainAssumptionSet:
        raise NotImplementedError("AssumptionSets are immutable; create a new version")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("AssumptionSets are immutable; create a new version")

    async def get_covariance_matrix(self, assumption_id: UUID) -> CovarianceMatrix | None:
        exists_stmt = select(OrmAssumptionSet).where(
            OrmAssumptionSet.assumption_id == assumption_id
        )
        exists_result = await self._session.execute(exists_stmt)
        if exists_result.scalar_one_or_none() is None:
            return None

        stmt = select(OrmAssumptionCov).where(
            OrmAssumptionCov.assumption_id == assumption_id
        )
        result = await self._session.execute(stmt)
        entries = [
            CovarianceEntry(
                assumption_id=row.assumption_id,
                asset_id_i=row.asset_id_i,
                asset_id_j=row.asset_id_j,
                cov_annual=row.cov_annual,
            )
            for row in result.scalars()
        ]
        return CovarianceMatrix(assumption_id=assumption_id, entries=entries)

    async def get_correlation_matrix(self, assumption_id: UUID) -> CorrelationMatrix | None:
        cov = await self.get_covariance_matrix(assumption_id)
        if cov is None:
            return None

        stats_stmt = select(OrmAssetStat).where(
            OrmAssetStat.assumption_id == assumption_id
        )
        stats_result = await self._session.execute(stats_stmt)
        sigma_by_asset = {row.asset_id: row.sigma_annual for row in stats_result.scalars()}

        entries: list[CorrelationEntry] = []
        for e in cov.entries:
            sig_i = sigma_by_asset.get(e.asset_id_i)
            sig_j = sigma_by_asset.get(e.asset_id_j)
            if sig_i and sig_j:
                raw_corr = e.cov_annual / (sig_i * sig_j)
                corr = max(-1.0, min(1.0, raw_corr))  # clamp for numerical safety
                entries.append(
                    CorrelationEntry(
                        assumption_id=assumption_id,
                        asset_id_i=e.asset_id_i,
                        asset_id_j=e.asset_id_j,
                        corr=corr,
                    )
                )
        return CorrelationMatrix(assumption_id=assumption_id, entries=entries)