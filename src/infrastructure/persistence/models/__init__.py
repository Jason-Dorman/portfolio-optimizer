"""ORM model registry — imports all layer modules so every mapper class is
registered with Base.metadata before Alembic or SQLAlchemy runs.

Import order follows the dependency graph (referenced tables first).
"""

from src.infrastructure.persistence.models.reference import (
    Asset,
    DataVendor,
    Universe,
    UniverseAsset,
)
from src.infrastructure.persistence.models.market_data import (
    PriceBar,
    ReturnSeries,
    RiskFreeSeries,
)
from src.infrastructure.persistence.models.estimation import (
    AssumptionAssetStat,
    AssumptionCov,
    AssumptionSet,
)
from src.infrastructure.persistence.models.holdings import (
    CurrentHoldingsPosition,
    CurrentHoldingsSnapshot,
)
from src.infrastructure.persistence.models.screening import (
    ScreeningRun,
    ScreeningScore,
)
from src.infrastructure.persistence.models.optimization import (
    OptimizationResult,
    OptimizationRun,
    OptimizationWeight,
)
from src.infrastructure.persistence.models.risk import (
    ScenarioDefinition,
    ScenarioResult,
)
from src.infrastructure.persistence.models.backtesting import (
    BacktestPoint,
    BacktestRun,
    BacktestSummary,
)
from src.infrastructure.persistence.models.drift import (
    DriftCheck,
    DriftCheckPosition,
)

__all__ = [
    # Reference
    "Asset",
    "DataVendor",
    "Universe",
    "UniverseAsset",
    # Market data
    "PriceBar",
    "ReturnSeries",
    "RiskFreeSeries",
    # Estimation
    "AssumptionAssetStat",
    "AssumptionCov",
    "AssumptionSet",
    # Holdings
    "CurrentHoldingsPosition",
    "CurrentHoldingsSnapshot",
    # Screening
    "ScreeningRun",
    "ScreeningScore",
    # Optimization
    "OptimizationResult",
    "OptimizationRun",
    "OptimizationWeight",
    # Risk
    "ScenarioDefinition",
    "ScenarioResult",
    # Backtesting
    "BacktestPoint",
    "BacktestRun",
    "BacktestSummary",
    # Drift
    "DriftCheck",
    "DriftCheckPosition",
]
