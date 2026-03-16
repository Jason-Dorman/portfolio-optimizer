"""FastAPI command router — mounts all write endpoints at /commands/*.

Dependency injection pattern:
  Each route depends on a factory function that constructs the handler with
  concrete repository/service implementations wired to the request's DB session.
  Session is provided by get_session() which wraps each request in a transaction
  (commit on success, rollback on exception).

All routes return HTTP 201 Created for new resources, 200 for updates.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.commands.assets import CreateAssetCommand, CreateAssetHandler
from src.commands.estimation import (
    ComputeReturnsCommand,
    ComputeReturnsHandler,
    ComputeReturnsResult,
    CreateAssumptionSetCommand,
    CreateAssumptionSetHandler,
)
from src.commands.holdings import CreateHoldingsSnapshotCommand, CreateHoldingsSnapshotHandler
from src.commands.ingest import (
    IngestPricesCommand,
    IngestPricesHandler,
    IngestResult,
    IngestRiskFreeCommand,
    IngestRiskFreeHandler,
)
from src.commands.optimization import RunOptimizationCommand, RunOptimizationHandler
from src.commands.risk import (
    ApplyScenarioCommand,
    ApplyScenarioHandler,
    CreateScenarioCommand,
    CreateScenarioHandler,
    RunBacktestCommand,
    RunBacktestHandler,
    RunDriftCheckCommand,
    RunDriftCheckHandler,
)
from src.commands.screening import RunScreeningCommand, RunScreeningHandler
from src.commands.universes import (
    AddUniverseAssetsCommand,
    AddUniverseAssetsHandler,
    CreateUniverseCommand,
    CreateUniverseHandler,
    RemoveUniverseAssetsCommand,
    RemoveUniverseAssetsHandler,
)
from src.config import settings
from src.domain.models.assets import Asset, Universe
from src.domain.models.assumptions import AssumptionSet
from src.domain.models.backtest import BacktestRun
from src.domain.models.drift import DriftCheck
from src.domain.models.holdings import HoldingsSnapshot
from src.domain.models.optimization import OptimizationRun
from src.domain.models.scenarios import ScenarioDefinition, ScenarioResult
from src.domain.models.screening import ScreeningRun
from src.domain.services.backtest import BacktestService
from src.domain.services.drift import DriftService
from src.domain.services.estimation import EstimationService
from src.domain.services.optimization import OptimizationService
from src.domain.services.screening import ScreeningService
from src.infrastructure.database import get_session
from src.infrastructure.persistence.repositories.assets import SqlAssetRepository
from src.infrastructure.persistence.repositories.assumptions import SqlAssumptionRepository
from src.infrastructure.persistence.repositories.backtest import SqlBacktestRepository
from src.infrastructure.persistence.repositories.drift import SqlDriftRepository
from src.infrastructure.persistence.repositories.holdings import SqlHoldingsRepository
from src.infrastructure.persistence.repositories.optimization import SqlOptimizationRepository
from src.infrastructure.persistence.repositories.prices import SqlPriceRepository
from src.infrastructure.persistence.repositories.returns import SqlReturnRepository
from src.infrastructure.persistence.repositories.risk_free import SqlRiskFreeRepository
from src.infrastructure.persistence.repositories.scenarios import SqlScenarioRepository
from src.infrastructure.persistence.repositories.screening import SqlScreeningRepository
from src.infrastructure.persistence.repositories.universes import SqlUniverseRepository
from src.infrastructure.persistence.repositories.vendors import SqlDataVendorRepository
from src.infrastructure.auth.schwab_oauth import SchwabOAuthService
from src.infrastructure.auth.token_repository import SqlTokenRepository
from src.infrastructure.vendors.fred import FredAdapter
from src.infrastructure.vendors.schwab import SchwabAdapter

router = APIRouter(prefix="/commands", tags=["commands"])


# ─────────────────────────────────────────────────────────────────────────── #
# Shared service singletons (stateless — safe to reuse across requests)        #
# ─────────────────────────────────────────────────────────────────────────── #

_estimation_service = EstimationService()
_optimization_service = OptimizationService()
_screening_service = ScreeningService()
_drift_service = DriftService()
_backtest_service = BacktestService(_estimation_service, _optimization_service)


# ─────────────────────────────────────────────────────────────────────────── #
# Assets                                                                        #
# ─────────────────────────────────────────────────────────────────────────── #


def _create_asset_handler(session: AsyncSession = Depends(get_session)) -> CreateAssetHandler:
    return CreateAssetHandler(asset_repo=SqlAssetRepository(session))


@router.post("/assets", status_code=status.HTTP_201_CREATED, response_model=Asset)
async def create_asset(
    body: CreateAssetCommand,
    handler: CreateAssetHandler = Depends(_create_asset_handler),
) -> Asset:
    """Create a new investable asset (ETF or security)."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Universes                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #


def _create_universe_handler(
    session: AsyncSession = Depends(get_session),
) -> CreateUniverseHandler:
    return CreateUniverseHandler(universe_repo=SqlUniverseRepository(session))


def _add_universe_assets_handler(
    session: AsyncSession = Depends(get_session),
) -> AddUniverseAssetsHandler:
    return AddUniverseAssetsHandler(universe_repo=SqlUniverseRepository(session))


def _remove_universe_assets_handler(
    session: AsyncSession = Depends(get_session),
) -> RemoveUniverseAssetsHandler:
    return RemoveUniverseAssetsHandler(universe_repo=SqlUniverseRepository(session))


@router.post("/universes", status_code=status.HTTP_201_CREATED, response_model=Universe)
async def create_universe(
    body: CreateUniverseCommand,
    handler: CreateUniverseHandler = Depends(_create_universe_handler),
) -> Universe:
    """Create a new universe (active or candidate pool)."""
    return await handler.handle(body)


@router.post(
    "/universes/{universe_id}/assets",
    status_code=status.HTTP_200_OK,
    response_model=Universe,
)
async def add_universe_assets(
    universe_id: UUID,
    body: AddUniverseAssetsCommand,
    handler: AddUniverseAssetsHandler = Depends(_add_universe_assets_handler),
) -> Universe:
    """Add assets to an existing universe."""
    return await handler.handle(universe_id, body)


@router.delete(
    "/universes/{universe_id}/assets",
    status_code=status.HTTP_200_OK,
    response_model=Universe,
)
async def remove_universe_assets(
    universe_id: UUID,
    body: RemoveUniverseAssetsCommand,
    handler: RemoveUniverseAssetsHandler = Depends(_remove_universe_assets_handler),
) -> Universe:
    """Remove assets from an existing universe."""
    return await handler.handle(universe_id, body)


# ─────────────────────────────────────────────────────────────────────────── #
# Holdings                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


def _create_holdings_snapshot_handler(
    session: AsyncSession = Depends(get_session),
) -> CreateHoldingsSnapshotHandler:
    return CreateHoldingsSnapshotHandler(
        holdings_repo=SqlHoldingsRepository(session),
        asset_repo=SqlAssetRepository(session),
    )


@router.post(
    "/holdings/snapshots",
    status_code=status.HTTP_201_CREATED,
    response_model=HoldingsSnapshot,
)
async def create_holdings_snapshot(
    body: CreateHoldingsSnapshotCommand,
    handler: CreateHoldingsSnapshotHandler = Depends(_create_holdings_snapshot_handler),
) -> HoldingsSnapshot:
    """Create a dated holdings snapshot from weights or market values."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Ingest                                                                        #
# ─────────────────────────────────────────────────────────────────────────── #


def _ingest_prices_handler(
    session: AsyncSession = Depends(get_session),
) -> IngestPricesHandler:
    if not settings.schwab_client_id or not settings.schwab_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Schwab credentials are not configured. Set SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET.",
        )
    oauth_service = SchwabOAuthService(
        client_id=settings.schwab_client_id,
        client_secret=settings.schwab_client_secret,
        callback_url=settings.schwab_callback_url,
        token_repository=SqlTokenRepository(session),
    )
    return IngestPricesHandler(
        vendor_adapter=SchwabAdapter(oauth_service=oauth_service),
        vendor_repo=SqlDataVendorRepository(session),
        asset_repo=SqlAssetRepository(session),
        price_repo=SqlPriceRepository(session),
    )


def _ingest_risk_free_handler(
    session: AsyncSession = Depends(get_session),
) -> IngestRiskFreeHandler:
    fred_key = settings.fred_api_key
    if not fred_key:
        raise HTTPException(
            status_code=503,
            detail="FRED API key is not configured. Set FRED_API_KEY in environment.",
        )
    return IngestRiskFreeHandler(
        fred_adapter=FredAdapter(api_key=fred_key),
        risk_free_repo=SqlRiskFreeRepository(session),
    )


@router.post("/ingest/prices", status_code=status.HTTP_200_OK, response_model=IngestResult)
async def ingest_prices(
    body: IngestPricesCommand,
    handler: IngestPricesHandler = Depends(_ingest_prices_handler),
) -> IngestResult:
    """Fetch price bars from the configured market-data vendor and upsert into price_bars."""
    return await handler.handle(body)


@router.post("/ingest/risk-free", status_code=status.HTTP_200_OK, response_model=IngestResult)
async def ingest_risk_free(
    body: IngestRiskFreeCommand,
    handler: IngestRiskFreeHandler = Depends(_ingest_risk_free_handler),
) -> IngestResult:
    """Fetch risk-free rate observations from FRED and upsert into risk_free_series."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Estimation                                                                    #
# ─────────────────────────────────────────────────────────────────────────── #


def _compute_returns_handler(
    session: AsyncSession = Depends(get_session),
) -> ComputeReturnsHandler:
    return ComputeReturnsHandler(
        universe_repo=SqlUniverseRepository(session),
        price_repo=SqlPriceRepository(session),
        return_repo=SqlReturnRepository(session),
        estimation_service=_estimation_service,
    )


def _create_assumption_set_handler(
    session: AsyncSession = Depends(get_session),
) -> CreateAssumptionSetHandler:
    return CreateAssumptionSetHandler(
        universe_repo=SqlUniverseRepository(session),
        return_repo=SqlReturnRepository(session),
        assumption_repo=SqlAssumptionRepository(session),
        estimation_service=_estimation_service,
    )


@router.post(
    "/returns/compute",
    status_code=status.HTTP_200_OK,
    response_model=ComputeReturnsResult,
)
async def compute_returns(
    body: ComputeReturnsCommand,
    handler: ComputeReturnsHandler = Depends(_compute_returns_handler),
) -> ComputeReturnsResult:
    """Compute and store return series for all assets in a universe."""
    return await handler.handle(body)


@router.post(
    "/assumptions",
    status_code=status.HTTP_201_CREATED,
    response_model=AssumptionSet,
)
async def create_assumption_set(
    body: CreateAssumptionSetCommand,
    handler: CreateAssumptionSetHandler = Depends(_create_assumption_set_handler),
) -> AssumptionSet:
    """Estimate µ and Σ for a universe and persist as a versioned assumption set."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Screening                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #


def _run_screening_handler(
    session: AsyncSession = Depends(get_session),
) -> RunScreeningHandler:
    return RunScreeningHandler(
        assumption_repo=SqlAssumptionRepository(session),
        universe_repo=SqlUniverseRepository(session),
        holdings_repo=SqlHoldingsRepository(session),
        asset_repo=SqlAssetRepository(session),
        screening_repo=SqlScreeningRepository(session),
        screening_service=_screening_service,
    )


@router.post("/screening", status_code=status.HTTP_201_CREATED, response_model=ScreeningRun)
async def run_screening(
    body: RunScreeningCommand,
    handler: RunScreeningHandler = Depends(_run_screening_handler),
) -> ScreeningRun:
    """Score and rank candidate assets against a reference portfolio."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Optimization                                                                  #
# ─────────────────────────────────────────────────────────────────────────── #


def _run_optimization_handler(
    session: AsyncSession = Depends(get_session),
) -> RunOptimizationHandler:
    return RunOptimizationHandler(
        assumption_repo=SqlAssumptionRepository(session),
        holdings_repo=SqlHoldingsRepository(session),
        optimization_repo=SqlOptimizationRepository(session),
        optimization_service=_optimization_service,
    )


@router.post("/optimize", status_code=status.HTTP_201_CREATED, response_model=OptimizationRun)
async def run_optimization(
    body: RunOptimizationCommand,
    handler: RunOptimizationHandler = Depends(_run_optimization_handler),
) -> OptimizationRun:
    """Run portfolio optimization; returns SUCCESS or INFEASIBLE (both are 201)."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Drift check                                                                   #
# ─────────────────────────────────────────────────────────────────────────── #


def _run_drift_check_handler(
    session: AsyncSession = Depends(get_session),
) -> RunDriftCheckHandler:
    return RunDriftCheckHandler(
        optimization_repo=SqlOptimizationRepository(session),
        price_repo=SqlPriceRepository(session),
        asset_repo=SqlAssetRepository(session),
        drift_repo=SqlDriftRepository(session),
        drift_service=_drift_service,
    )


@router.post("/drift-check", status_code=status.HTTP_201_CREATED, response_model=DriftCheck)
async def run_drift_check(
    body: RunDriftCheckCommand,
    handler: RunDriftCheckHandler = Depends(_run_drift_check_handler),
) -> DriftCheck:
    """Compute implied weights since last optimization and flag threshold breaches."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Backtest                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


def _run_backtest_handler(
    session: AsyncSession = Depends(get_session),
) -> RunBacktestHandler:
    return RunBacktestHandler(
        universe_repo=SqlUniverseRepository(session),
        asset_repo=SqlAssetRepository(session),
        price_repo=SqlPriceRepository(session),
        backtest_repo=SqlBacktestRepository(session),
        backtest_service=_backtest_service,
    )


@router.post("/backtest", status_code=status.HTTP_201_CREATED, response_model=BacktestRun)
async def run_backtest(
    body: RunBacktestCommand,
    handler: RunBacktestHandler = Depends(_run_backtest_handler),
) -> BacktestRun:
    """Run a rolling backtest simulation and persist the full time series."""
    return await handler.handle(body)


# ─────────────────────────────────────────────────────────────────────────── #
# Scenarios                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #


def _create_scenario_handler(
    session: AsyncSession = Depends(get_session),
) -> CreateScenarioHandler:
    return CreateScenarioHandler(scenario_repo=SqlScenarioRepository(session))


def _apply_scenario_handler(
    session: AsyncSession = Depends(get_session),
) -> ApplyScenarioHandler:
    return ApplyScenarioHandler(scenario_repo=SqlScenarioRepository(session))


@router.post(
    "/scenarios",
    status_code=status.HTTP_201_CREATED,
    response_model=ScenarioDefinition,
)
async def create_scenario(
    body: CreateScenarioCommand,
    handler: CreateScenarioHandler = Depends(_create_scenario_handler),
) -> ScenarioDefinition:
    """Define a named stress scenario (factor shocks)."""
    return await handler.handle(body)


@router.post(
    "/scenarios/{scenario_id}/apply",
    status_code=status.HTTP_201_CREATED,
    response_model=ScenarioResult,
)
async def apply_scenario(
    scenario_id: UUID,
    body: ApplyScenarioCommand,
    handler: ApplyScenarioHandler = Depends(_apply_scenario_handler),
) -> ScenarioResult:
    """Apply a scenario to an optimization run (v1.1 — currently returns 501)."""
    return await handler.handle(scenario_id, body)
