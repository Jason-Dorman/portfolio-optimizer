"""Domain enumerations for the portfolio optimizer.

All string-valued enums use str mixin so they serialize cleanly to JSON
and remain comparable to plain strings (FastAPI / Pydantic default behaviour).
"""

from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    COMMODITY = "commodity"
    REAL_ESTATE = "real_estate"
    CASH = "cash"
    CRYPTO = "crypto"
    OTHER = "other"


class Geography(str, Enum):
    US = "us"
    DEVELOPED_EX_US = "developed_ex_us"
    EMERGING = "emerging"
    GLOBAL = "global"


class UniverseType(str, Enum):
    ACTIVE = "active"
    CANDIDATE_POOL = "candidate_pool"


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def periods_per_year(self) -> int:
        """Standard annualisation factor for this frequency."""
        return {
            Frequency.DAILY: 252,
            Frequency.WEEKLY: 52,
            Frequency.MONTHLY: 12,
        }[self]


class ReturnType(str, Enum):
    SIMPLE = "simple"
    LOG = "log"


class Estimator(str, Enum):
    """Expected-return (μ) estimation method."""

    HISTORICAL = "historical"
    EWMA = "ewma"
    SHRINKAGE = "shrinkage"


class CovMethod(str, Enum):
    """Covariance matrix (Σ) estimation method."""

    SAMPLE = "sample"
    LEDOIT_WOLF = "ledoit_wolf"


class CovRepair(str, Enum):
    """Post-estimation covariance repair method.

    Separate from CovMethod because repair is applied after estimation,
    not as an alternative estimator.
    """

    NEAREST_PSD = "nearest_psd"


class OptimizationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"


class RunType(str, Enum):
    MVP = "MVP"
    FRONTIER_POINT = "FRONTIER_POINT"
    FRONTIER_SERIES = "FRONTIER_SERIES"
    TANGENCY = "TANGENCY"


class Objective(str, Enum):
    MIN_VAR = "MIN_VAR"
    MAX_SHARPE = "MAX_SHARPE"


class ReferenceType(str, Enum):
    CURRENT_HOLDINGS = "current_holdings"
    SEED_UNIVERSE = "seed_universe"


class BacktestStrategy(str, Enum):
    TANGENCY_REBAL = "TANGENCY_REBAL"
    MVP_REBAL = "MVP_REBAL"
    EW_REBAL = "EW_REBAL"


class RebalFrequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    THRESHOLD = "threshold"
