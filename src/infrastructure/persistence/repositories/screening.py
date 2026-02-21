"""SQLAlchemy implementation of ScreeningRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.models.enums import ReferenceType
from src.domain.models.screening import (
    ScreeningConfig,
    ScreeningRun as DomainScreeningRun,
    ScreeningScore as DomainScreeningScore,
    ScoreWeights,
)
from src.domain.repositories.screening import ScreeningRepository
from src.infrastructure.persistence.models.screening import (
    ScreeningRun as OrmScreeningRun,
    ScreeningScore as OrmScreeningScore,
)


def _score_to_domain(row: OrmScreeningScore) -> DomainScreeningScore:
    return DomainScreeningScore(
        screening_id=row.screening_id,
        asset_id=row.asset_id,
        avg_pairwise_corr=row.avg_pairwise_corr,
        marginal_vol_reduction=row.marginal_vol_reduction,
        sector_gap_score=row.sector_gap_score,
        hhi_reduction=row.hhi_reduction,
        composite_score=row.composite_score,
        rank=row.rank,
        explanation=row.explanation,
    )


def _run_to_domain(
    row: OrmScreeningRun, scores: list[DomainScreeningScore]
) -> DomainScreeningRun:
    config = ScreeningConfig(
        nominal_add_weight=row.nominal_add_weight,
        sector_gap_threshold=row.sector_gap_threshold,
        score_weights=ScoreWeights.model_validate(row.score_weights),
    )
    return DomainScreeningRun(
        screening_id=row.screening_id,
        assumption_id=row.assumption_id,
        candidate_pool_id=row.candidate_pool_id,
        reference_type=ReferenceType(row.reference_type),
        reference_snapshot_id=row.reference_snapshot_id,
        reference_universe_id=row.reference_universe_id,
        config=config,
        created_at=row.created_at,
        scores=scores,
    )


class SqlScreeningRepository(ScreeningRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, screening_id: UUID) -> DomainScreeningRun | None:
        stmt = (
            select(OrmScreeningRun)
            .options(selectinload(OrmScreeningRun.scores))
            .where(OrmScreeningRun.screening_id == screening_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        scores = [_score_to_domain(s) for s in row.scores]
        return _run_to_domain(row, scores)

    async def list(self, limit: int = 50, offset: int = 0) -> list[DomainScreeningRun]:
        # Returns header runs without scores for efficiency. Use get_by_id() for full data.
        stmt = (
            select(OrmScreeningRun)
            .order_by(OrmScreeningRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_run_to_domain(row, []) for row in result.scalars()]

    async def create(self, entity: DomainScreeningRun) -> DomainScreeningRun:
        run_row = OrmScreeningRun(
            screening_id=entity.screening_id,
            assumption_id=entity.assumption_id,
            candidate_pool_id=entity.candidate_pool_id,
            reference_type=entity.reference_type.value,
            reference_snapshot_id=entity.reference_snapshot_id,
            reference_universe_id=entity.reference_universe_id,
            nominal_add_weight=entity.config.nominal_add_weight,
            sector_gap_threshold=entity.config.sector_gap_threshold,
            score_weights=entity.config.score_weights.model_dump(),
            created_at=entity.created_at,
        )
        score_rows = [
            OrmScreeningScore(
                screening_id=entity.screening_id,
                asset_id=s.asset_id,
                avg_pairwise_corr=s.avg_pairwise_corr,
                marginal_vol_reduction=s.marginal_vol_reduction,
                sector_gap_score=s.sector_gap_score,
                hhi_reduction=s.hhi_reduction,
                composite_score=s.composite_score,
                rank=s.rank,
                explanation=s.explanation,
            )
            for s in entity.scores
        ]
        self._session.add(run_row)
        self._session.add_all(score_rows)
        return entity

    async def update(self, entity: DomainScreeningRun) -> DomainScreeningRun:
        raise NotImplementedError("ScreeningRuns are immutable")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("ScreeningRuns are immutable")

    async def get_scores(
        self,
        screening_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DomainScreeningScore]:
        stmt = (
            select(OrmScreeningScore)
            .where(OrmScreeningScore.screening_id == screening_id)
            .order_by(OrmScreeningScore.rank.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_score_to_domain(row) for row in result.scalars()]
