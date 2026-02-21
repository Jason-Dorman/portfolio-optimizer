"""Concrete SQLAlchemy repository implementations.

Exports all SqlRepository classes and the get_repositories() factory function
for wiring at the application boundary (FastAPI dependency injection).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .assets import SqlAssetRepository
from .assumptions import SqlAssumptionRepository
from .backtest import SqlBacktestRepository
from .drift import SqlDriftRepository
from .holdings import SqlHoldingsRepository
from .optimization import SqlOptimizationRepository
from .prices import SqlPriceRepository
from .returns import SqlReturnRepository
from .scenarios import SqlScenarioRepository
from .screening import SqlScreeningRepository
from .universes import SqlUniverseRepository


@dataclass
class Repositories:
    """All repository instances bound to a single AsyncSession."""

    assets: SqlAssetRepository
    universes: SqlUniverseRepository
    holdings: SqlHoldingsRepository
    prices: SqlPriceRepository
    returns: SqlReturnRepository
    assumptions: SqlAssumptionRepository
    screening: SqlScreeningRepository
    optimization: SqlOptimizationRepository
    drift: SqlDriftRepository
    backtest: SqlBacktestRepository
    scenarios: SqlScenarioRepository


def get_repositories(session: AsyncSession) -> Repositories:
    """Construct all repositories bound to the given session.

    Intended for use as a FastAPI dependency:

        async def handler(
            session: AsyncSession = Depends(get_session),
        ) -> ...:
            repos = get_repositories(session)
            asset = await repos.assets.get_by_id(asset_id)
    """
    return Repositories(
        assets=SqlAssetRepository(session),
        universes=SqlUniverseRepository(session),
        holdings=SqlHoldingsRepository(session),
        prices=SqlPriceRepository(session),
        returns=SqlReturnRepository(session),
        assumptions=SqlAssumptionRepository(session),
        screening=SqlScreeningRepository(session),
        optimization=SqlOptimizationRepository(session),
        drift=SqlDriftRepository(session),
        backtest=SqlBacktestRepository(session),
        scenarios=SqlScenarioRepository(session),
    )


__all__ = [
    "SqlAssetRepository",
    "SqlUniverseRepository",
    "SqlHoldingsRepository",
    "SqlPriceRepository",
    "SqlReturnRepository",
    "SqlAssumptionRepository",
    "SqlScreeningRepository",
    "SqlOptimizationRepository",
    "SqlDriftRepository",
    "SqlBacktestRepository",
    "SqlScenarioRepository",
    "Repositories",
    "get_repositories",
]
