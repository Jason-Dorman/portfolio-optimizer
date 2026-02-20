"""Domain repository interfaces.

All abstractions are defined here with abc.ABC and @abstractmethod.
Concrete implementations live in src/infrastructure/persistence/ and are
wired at the application boundary via dependency injection.

Import from this package rather than individual modules to avoid coupling
handlers to specific repository module paths.
"""

from .assets import AssetRepository
from .assumptions import AssumptionRepository
from .backtest import BacktestRepository
from .base import Repository
from .drift import DriftRepository
from .holdings import HoldingsRepository
from .optimization import OptimizationRepository
from .prices import PriceRepository
from .returns import ReturnRepository
from .scenarios import ScenarioRepository
from .screening import ScreeningRepository
from .universes import UniverseRepository

__all__ = [
    "Repository",
    "AssetRepository",
    "UniverseRepository",
    "HoldingsRepository",
    "PriceRepository",
    "ReturnRepository",
    "AssumptionRepository",
    "ScreeningRepository",
    "OptimizationRepository",
    "DriftRepository",
    "BacktestRepository",
    "ScenarioRepository",
]
