"""Asset and universe domain models.

These are pure domain objects — no ORM or persistence concerns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import AssetClass, Geography, UniverseType


class Asset(BaseModel):
    """An investable asset (ETF or individual security).

    asset_class and geography are constrained enumerations; free-text
    values are not permitted (enforced at construction time by Pydantic).
    sector is the GICS sector string — null for non-equity assets.
    currency is an ISO 4217 code (e.g. "USD").
    """

    model_config = ConfigDict(frozen=True)

    asset_id: UUID = Field(default_factory=uuid4)
    ticker: str
    name: str
    asset_class: AssetClass
    sub_class: str
    sector: str | None = None  # GICS sector; None for non-equity
    geography: Geography
    currency: str  # ISO 4217
    is_etf: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        ticker: str,
        name: str,
        asset_class: AssetClass,
        sub_class: str,
        geography: Geography,
        currency: str,
        is_etf: bool,
        sector: str | None = None,
    ) -> Asset:
        """Named constructor — explicit about the caller's intent."""
        return cls(
            ticker=ticker,
            name=name,
            asset_class=asset_class,
            sub_class=sub_class,
            geography=geography,
            currency=currency,
            is_etf=is_etf,
            sector=sector,
        )


class Universe(BaseModel):
    """A named collection of assets.

    universe_type distinguishes active optimization universes
    (universe_type=ACTIVE) from screening candidate pools
    (universe_type=CANDIDATE_POOL).
    """

    model_config = ConfigDict(frozen=True)

    universe_id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    universe_type: UniverseType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create_active(cls, name: str, description: str) -> Universe:
        return cls(name=name, description=description, universe_type=UniverseType.ACTIVE)

    @classmethod
    def create_candidate_pool(cls, name: str, description: str) -> Universe:
        return cls(name=name, description=description, universe_type=UniverseType.CANDIDATE_POOL)


class UniverseAsset(BaseModel):
    """Membership record — maps an asset into a universe.

    is_benchmark marks the asset as the benchmark for backtest comparisons
    (e.g. SPY inside a candidate pool universe).
    """

    model_config = ConfigDict(frozen=True)

    universe_id: UUID
    asset_id: UUID
    is_benchmark: bool = False
