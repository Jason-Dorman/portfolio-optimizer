"""Persistence package.

Importing this package registers every ORM mapper with Base.metadata
(required for Alembic autogenerate and SQLAlchemy mapper configuration)
and exports all repository implementations and the DI factory.
"""

from src.infrastructure.persistence.models import *  # noqa: F401, F403
from src.infrastructure.persistence.models import __all__ as _orm_all
from src.infrastructure.persistence.repositories import (
    Repositories,
    SqlAssetRepository,
    SqlAssumptionRepository,
    SqlBacktestRepository,
    SqlDriftRepository,
    SqlHoldingsRepository,
    SqlOptimizationRepository,
    SqlPriceRepository,
    SqlReturnRepository,
    SqlScenarioRepository,
    SqlScreeningRepository,
    SqlUniverseRepository,
    get_repositories,
)

__all__ = _orm_all + [
    "Repositories",
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
    "get_repositories",
]
