"""SQLAlchemy implementation of BacktestRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.models.backtest import (
    BacktestConfig,
    BacktestPoint as DomainBacktestPoint,
    BacktestRun as DomainBacktestRun,
    BacktestSummary as DomainBacktestSummary,
)
from src.domain.models.enums import BacktestStrategy, RebalFrequency
from src.domain.repositories.backtest import BacktestRepository
from src.infrastructure.persistence.models.backtesting import (
    BacktestPoint as OrmPoint,
    BacktestRun as OrmRun,
    BacktestSummary as OrmSummary,
)


def _point_to_domain(row: OrmPoint) -> DomainBacktestPoint:
    return DomainBacktestPoint(
        backtest_id=row.backtest_id,
        obs_date=row.obs_date,
        portfolio_value=row.portfolio_value,
        portfolio_ret=row.portfolio_ret,
        portfolio_ret_net=row.portfolio_ret_net,
        benchmark_ret=row.benchmark_ret,
        active_ret=row.active_ret,
        turnover=row.turnover,
        drawdown=row.drawdown,
    )


def _summary_to_domain(row: OrmSummary) -> DomainBacktestSummary:
    return DomainBacktestSummary(
        backtest_id=row.backtest_id,
        total_return=row.total_return,
        annualized_return=row.annualized_return,
        annualized_vol=row.annualized_vol,
        sharpe=row.sharpe,
        max_drawdown=row.max_drawdown,
        var_95=row.var_95,
        cvar_95=row.cvar_95,
        avg_turnover=row.avg_turnover,
        tracking_error=row.tracking_error,
        information_ratio=row.information_ratio,
    )


def _run_to_domain(
    row: OrmRun,
    points: list[DomainBacktestPoint],
    summary: DomainBacktestSummary | None,
) -> DomainBacktestRun:
    config = BacktestConfig(
        strategy=BacktestStrategy(row.strategy),
        rebal_freq=RebalFrequency(row.rebal_freq),
        rebal_threshold=row.rebal_threshold,
        window_length=row.window_length,
        transaction_cost_bps=row.transaction_cost_bps,
        constraints=row.constraints,
    )
    return DomainBacktestRun(
        backtest_id=row.backtest_id,
        universe_id=row.universe_id,
        benchmark_asset_id=row.benchmark_asset_id,
        config=config,
        survivorship_bias_note=row.survivorship_bias_note,
        created_at=row.created_at,
        points=points,
        summary=summary,
    )


class SqlBacktestRepository(BacktestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, backtest_id: UUID) -> DomainBacktestRun | None:
        stmt = (
            select(OrmRun)
            .options(selectinload(OrmRun.points), selectinload(OrmRun.summary))
            .where(OrmRun.backtest_id == backtest_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        points = [_point_to_domain(p) for p in row.points]
        summary = _summary_to_domain(row.summary) if row.summary else None
        return _run_to_domain(row, points, summary)

    async def list(self, limit: int = 50, offset: int = 0) -> list[DomainBacktestRun]:
        # Returns header runs without points/summary. Use get_by_id() for full data.
        stmt = (
            select(OrmRun)
            .order_by(OrmRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_run_to_domain(row, [], None) for row in result.scalars()]

    async def create(self, entity: DomainBacktestRun) -> DomainBacktestRun:
        run_row = OrmRun(
            backtest_id=entity.backtest_id,
            universe_id=entity.universe_id,
            benchmark_asset_id=entity.benchmark_asset_id,
            strategy=entity.config.strategy.value,
            rebal_freq=entity.config.rebal_freq.value,
            rebal_threshold=entity.config.rebal_threshold,
            window_length=entity.config.window_length,
            transaction_cost_bps=entity.config.transaction_cost_bps,
            constraints=entity.config.constraints,
            survivorship_bias_note=entity.survivorship_bias_note,
            created_at=entity.created_at,
        )
        point_rows = [
            OrmPoint(
                backtest_id=entity.backtest_id,
                obs_date=p.obs_date,
                portfolio_value=p.portfolio_value,
                portfolio_ret=p.portfolio_ret,
                portfolio_ret_net=p.portfolio_ret_net,
                benchmark_ret=p.benchmark_ret,
                active_ret=p.active_ret,
                turnover=p.turnover,
                drawdown=p.drawdown,
            )
            for p in entity.points
        ]
        self._session.add(run_row)
        self._session.add_all(point_rows)

        if entity.summary is not None:
            summary_row = OrmSummary(
                backtest_id=entity.backtest_id,
                total_return=entity.summary.total_return,
                annualized_return=entity.summary.annualized_return,
                annualized_vol=entity.summary.annualized_vol,
                sharpe=entity.summary.sharpe,
                max_drawdown=entity.summary.max_drawdown,
                var_95=entity.summary.var_95,
                cvar_95=entity.summary.cvar_95,
                avg_turnover=entity.summary.avg_turnover,
                tracking_error=entity.summary.tracking_error,
                information_ratio=entity.summary.information_ratio,
            )
            self._session.add(summary_row)

        return entity

    async def update(self, entity: DomainBacktestRun) -> DomainBacktestRun:
        raise NotImplementedError("BacktestRuns are immutable")

    async def delete(self, id: UUID) -> None:
        raise NotImplementedError("BacktestRuns are immutable")

    async def get_points(self, backtest_id: UUID) -> list[DomainBacktestPoint]:
        stmt = (
            select(OrmPoint)
            .where(OrmPoint.backtest_id == backtest_id)
            .order_by(OrmPoint.obs_date.asc())
        )
        result = await self._session.execute(stmt)
        return [_point_to_domain(row) for row in result.scalars()]

    async def get_summary(self, backtest_id: UUID) -> DomainBacktestSummary | None:
        stmt = select(OrmSummary).where(OrmSummary.backtest_id == backtest_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _summary_to_domain(row) if row else None
