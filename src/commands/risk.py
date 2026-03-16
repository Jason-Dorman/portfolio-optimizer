"""Risk commands: DriftCheck, Backtest, Scenario (Create + Apply stub)."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.domain.models.backtest import BacktestConfig, BacktestPoint, BacktestRun, BacktestSummary
from src.domain.models.drift import DRIFT_THRESHOLD_DEFAULT, DriftCheck
from src.domain.models.enums import BacktestStrategy, Frequency, RebalFrequency
from src.domain.models.optimization import OptimizationConstraints
from src.domain.models.scenarios import ScenarioDefinition, ScenarioResult
from src.domain.repositories.assets import AssetRepository
from src.domain.repositories.backtest import BacktestRepository
from src.domain.repositories.drift import DriftRepository
from src.domain.repositories.optimization import OptimizationRepository
from src.domain.repositories.prices import PriceRepository
from src.domain.repositories.scenarios import ScenarioRepository
from src.domain.repositories.universes import UniverseRepository
from src.domain.services.backtest import BacktestService
from src.domain.services.drift import DriftService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────── #
# Drift check                                                                   #
# ─────────────────────────────────────────────────────────────────────────── #


class RunDriftCheckCommand(BaseModel):
    """Compute implied weights since the last optimization and flag breaches."""

    run_id: UUID
    check_date: date
    threshold_pct: float = Field(
        default=DRIFT_THRESHOLD_DEFAULT, gt=0.0, le=1.0
    )


class RunDriftCheckHandler:
    """Load target weights and price history, run DriftService, and persist.

    Drift always uses simple returns for wealth compounding (DATA-MODEL §4.11).
    """

    def __init__(
        self,
        optimization_repo: OptimizationRepository,
        price_repo: PriceRepository,
        asset_repo: AssetRepository,
        drift_repo: DriftRepository,
        drift_service: DriftService,
    ) -> None:
        self._optimization_repo = optimization_repo
        self._price_repo = price_repo
        self._asset_repo = asset_repo
        self._drift_repo = drift_repo
        self._drift_service = drift_service

    async def handle(self, command: RunDriftCheckCommand) -> DriftCheck:
        run = await self._optimization_repo.get_by_id(command.run_id)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail=f"OptimizationRun {command.run_id} not found.",
            )

        portfolio_weights = await self._optimization_repo.get_weights(command.run_id)
        if not portfolio_weights:
            raise HTTPException(
                status_code=422,
                detail=f"Run {command.run_id} has no weights (INFEASIBLE or ERROR).",
            )

        target_weights = {w.asset_id: w.weight for w in portfolio_weights}
        optimization_date = run.created_at.date()

        prices_df, asset_tickers = await self._load_prices_df(
            list(target_weights.keys()), optimization_date, command.check_date
        )

        drift_result = self._drift_service.compute_drift(
            target_weights=target_weights,
            asset_tickers=asset_tickers,
            prices=prices_df,
            optimization_date=optimization_date,
            check_date=command.check_date,
            threshold=command.threshold_pct,
        )

        drift_check = DriftCheck.create(
            run_id=command.run_id,
            check_date=command.check_date,
            raw_positions=drift_result.raw_positions,
            threshold_pct=command.threshold_pct,
        )
        return await self._drift_repo.create(drift_check)

    async def _load_prices_df(
        self,
        asset_ids: list[UUID],
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, dict[UUID, str]]:
        """Return (prices DataFrame, ticker map) for the given assets and window."""
        data: dict[UUID, dict] = {}
        tickers: dict[UUID, str] = {}

        for asset_id in asset_ids:
            asset = await self._asset_repo.get_by_id(asset_id)
            if asset is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Asset {asset_id} referenced in optimization weights not found.",
                )
            tickers[asset_id] = asset.ticker

            bars = await self._price_repo.get_prices(
                asset_id, Frequency.DAILY, start, end
            )
            if bars:
                data[asset_id] = {
                    pd.Timestamp(bar.bar_date): bar.adj_close for bar in bars
                }

        df = pd.DataFrame(data)
        if not df.empty:
            df.index = pd.DatetimeIndex(df.index)
        return df, tickers


# ─────────────────────────────────────────────────────────────────────────── #
# Backtest                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


class RunBacktestCommand(BaseModel):
    """Configure and run a rolling backtest for a universe strategy."""

    universe_id: UUID
    strategy: BacktestStrategy
    rebal_freq: RebalFrequency
    rebal_threshold: float | None = Field(default=None, gt=0.0, le=1.0)
    window_length: int = Field(gt=0)
    transaction_cost_bps: float = Field(default=0.0, ge=0.0)
    rf: float = Field(default=0.0, ge=0.0)
    start_date: date
    end_date: date
    frequency: Frequency = Frequency.DAILY
    benchmark_ticker: str | None = None
    constraints: OptimizationConstraints = Field(
        default_factory=OptimizationConstraints.long_only_unconstrained
    )


class RunBacktestHandler:
    """Load price history, run BacktestService, and persist the full run.

    A benchmark asset is loaded separately when benchmark_ticker is provided;
    its prices drive TE/IR computation in the summary.
    """

    def __init__(
        self,
        universe_repo: UniverseRepository,
        asset_repo: AssetRepository,
        price_repo: PriceRepository,
        backtest_repo: BacktestRepository,
        backtest_service: BacktestService,
    ) -> None:
        self._universe_repo = universe_repo
        self._asset_repo = asset_repo
        self._price_repo = price_repo
        self._backtest_repo = backtest_repo
        self._backtest_service = backtest_service

    async def handle(self, command: RunBacktestCommand) -> BacktestRun:
        universe = await self._universe_repo.get_by_id(command.universe_id)
        if universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Universe {command.universe_id} not found.",
            )

        asset_ids = await self._universe_repo.get_asset_ids(command.universe_id)
        if not asset_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Universe {command.universe_id} has no assets.",
            )

        prices_df = await self._load_prices_df(
            asset_ids, command.frequency, command.start_date, command.end_date
        )
        if prices_df.empty:
            raise HTTPException(
                status_code=422,
                detail="No price data found for the specified date range.",
            )

        benchmark_prices, benchmark_asset_id = await self._load_benchmark(
            command.benchmark_ticker, command.frequency,
            command.start_date, command.end_date,
        )

        config = BacktestConfig(
            strategy=command.strategy,
            rebal_freq=command.rebal_freq,
            rebal_threshold=command.rebal_threshold,
            window_length=command.window_length,
            transaction_cost_bps=command.transaction_cost_bps,
            rf=command.rf,
            constraints=command.constraints,
        )
        annualization_factor = command.frequency.periods_per_year

        bt_result = self._backtest_service.run_backtest(
            config=config,
            prices=prices_df,
            annualization_factor=annualization_factor,
            benchmark_prices=benchmark_prices,
        )

        run = BacktestRun.create(
            universe_id=command.universe_id,
            config=config,
            benchmark_asset_id=benchmark_asset_id,
            survivorship_bias_note=bt_result.survivorship_bias_note,
        )

        points = [
            BacktestPoint(
                backtest_id=run.backtest_id,
                obs_date=p.obs_date,
                portfolio_value=p.portfolio_value,
                portfolio_ret=p.portfolio_ret,
                portfolio_ret_net=p.portfolio_ret_net,
                benchmark_ret=p.benchmark_ret,
                active_ret=p.active_ret,
                turnover=p.turnover,
                drawdown=p.drawdown,
            )
            for p in bt_result.points
        ]

        summary = BacktestSummary(
            backtest_id=run.backtest_id,
            total_return=bt_result.summary.total_return,
            annualized_return=bt_result.summary.annualized_return,
            annualized_vol=bt_result.summary.annualized_vol,
            sharpe=bt_result.summary.sharpe,
            max_drawdown=bt_result.summary.max_drawdown,
            var_95=bt_result.summary.var_95,
            cvar_95=bt_result.summary.cvar_95,
            avg_turnover=bt_result.summary.avg_turnover,
            tracking_error=bt_result.summary.tracking_error,
            information_ratio=bt_result.summary.information_ratio,
        )

        run = run.model_copy(update={"points": points, "summary": summary})
        return await self._backtest_repo.create(run)

    async def _load_prices_df(
        self,
        asset_ids: list[UUID],
        frequency: Frequency,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Build a DatetimeIndex prices DataFrame with asset_id columns."""
        data: dict[UUID, dict] = {}
        for asset_id in asset_ids:
            bars = await self._price_repo.get_prices(asset_id, frequency, start, end)
            if bars:
                data[asset_id] = {pd.Timestamp(bar.bar_date): bar.adj_close for bar in bars}

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()

    async def _load_benchmark(
        self,
        benchmark_ticker: str | None,
        frequency: Frequency,
        start: date,
        end: date,
    ) -> tuple[pd.Series | None, UUID | None]:
        if benchmark_ticker is None:
            return None, None

        asset = await self._asset_repo.get_by_ticker(benchmark_ticker.upper())
        if asset is None:
            raise HTTPException(
                status_code=404,
                detail=f"Benchmark ticker '{benchmark_ticker}' not found in assets table.",
            )
        bars = await self._price_repo.get_prices(asset.asset_id, frequency, start, end)
        if not bars:
            raise HTTPException(
                status_code=422,
                detail=f"No price data for benchmark '{benchmark_ticker}' in the date range.",
            )
        series = pd.Series(
            {pd.Timestamp(bar.bar_date): bar.adj_close for bar in bars}
        )
        series.index = pd.DatetimeIndex(series.index)
        return series.sort_index(), asset.asset_id


# ─────────────────────────────────────────────────────────────────────────── #
# Scenarios                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #


class CreateScenarioCommand(BaseModel):
    """Define a named stress scenario as a set of factor shocks."""

    name: str
    shocks: dict[str, float]


class ApplyScenarioCommand(BaseModel):
    """Apply a scenario to a specific optimization run (v1.1 placeholder)."""

    run_id: UUID


class CreateScenarioHandler:
    """Persist a new scenario definition."""

    def __init__(self, scenario_repo: ScenarioRepository) -> None:
        self._scenario_repo = scenario_repo

    async def handle(self, command: CreateScenarioCommand) -> ScenarioDefinition:
        scenario = ScenarioDefinition(
            name=command.name,
            shocks=command.shocks,
        )
        return await self._scenario_repo.create_definition(scenario)


class ApplyScenarioHandler:
    """Placeholder — scenario stress testing is planned for v1.1.

    Applying factor shocks to a portfolio requires per-asset factor sensitivities
    (equity beta, duration, inflation sensitivity) which are not part of the v1
    data model.  This handler raises 501 Not Implemented until the factor model
    is added to the asset schema.
    """

    def __init__(self, scenario_repo: ScenarioRepository) -> None:
        self._scenario_repo = scenario_repo

    async def handle(
        self, scenario_id: UUID, command: ApplyScenarioCommand
    ) -> ScenarioResult:
        raise HTTPException(
            status_code=501,
            detail=(
                "Scenario stress testing requires per-asset factor sensitivities "
                "(equity beta, duration, inflation sensitivity) which are planned "
                "for v1.1.  See DATA-MODEL.md for future scope."
            ),
        )
