"""Domain model package.

All domain objects are pure Python / Pydantic models with no ORM or
infrastructure dependencies.  Import from this package to avoid coupling
application code to individual module paths.
"""

from .assets import Asset, Universe, UniverseAsset
from .assumptions import (
    AssetStats,
    AssumptionSet,
    CorrelationEntry,
    CorrelationMatrix,
    CovarianceEntry,
    CovarianceMatrix,
)
from .backtest import BacktestConfig, BacktestPoint, BacktestRun, BacktestSummary
from .drift import DriftCheck, DriftPosition
from .enums import (
    AssetClass,
    BacktestStrategy,
    CovMethod,
    CovRepair,
    Estimator,
    Frequency,
    Geography,
    Objective,
    OptimizationStatus,
    RebalFrequency,
    ReferenceType,
    ReturnType,
    RunType,
    UniverseType,
)
from .holdings import HoldingsPosition, HoldingsSnapshot
from .market_data import PriceBar, ReturnPoint
from .optimization import (
    AssetBound,
    OptimizationConstraints,
    OptimizationResult,
    OptimizationRun,
    PortfolioWeight,
    RiskDecomposition,
)
from .scenarios import ScenarioDefinition, ScenarioResult
from .screening import ScreeningConfig, ScreeningRun, ScreeningScore, ScoreWeights

__all__ = [
    # enums
    "AssetClass",
    "BacktestStrategy",
    "CovMethod",
    "CovRepair",
    "Estimator",
    "Frequency",
    "Geography",
    "Objective",
    "OptimizationStatus",
    "RebalFrequency",
    "ReferenceType",
    "ReturnType",
    "RunType",
    "UniverseType",
    # assets
    "Asset",
    "Universe",
    "UniverseAsset",
    # holdings
    "HoldingsPosition",
    "HoldingsSnapshot",
    # market data
    "PriceBar",
    "ReturnPoint",
    # assumptions
    "AssetStats",
    "AssumptionSet",
    "CovarianceEntry",
    "CovarianceMatrix",
    "CorrelationEntry",
    "CorrelationMatrix",
    # screening
    "ScoreWeights",
    "ScreeningConfig",
    "ScreeningScore",
    "ScreeningRun",
    # optimization
    "AssetBound",
    "OptimizationConstraints",
    "RiskDecomposition",
    "PortfolioWeight",
    "OptimizationResult",
    "OptimizationRun",
    # drift
    "DriftPosition",
    "DriftCheck",
    # backtest
    "BacktestConfig",
    "BacktestPoint",
    "BacktestSummary",
    "BacktestRun",
    # scenarios
    "ScenarioDefinition",
    "ScenarioResult",
]
