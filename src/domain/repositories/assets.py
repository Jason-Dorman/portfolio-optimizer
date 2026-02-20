"""Asset repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass

from .base import Repository


class AssetRepository(Repository[Asset]):
    """Read/write interface for Asset entities.

    get_by_id and get_by_ticker both return None when no match exists.
    list() supports optional filtering by ticker prefix and asset class.
    """

    async def get(self, id: UUID) -> Asset | None:
        """Delegate to get_by_id for a consistent base-interface contract."""
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, asset_id: UUID) -> Asset | None:
        """Return the asset with the given ID, or None."""

    @abstractmethod
    async def get_by_ticker(self, ticker: str) -> Asset | None:
        """Return the asset with the given ticker (case-insensitive), or None."""

    @abstractmethod
    async def list(
        self,
        ticker: str | None = None,
        asset_class: AssetClass | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Asset]:
        """Return a page of assets, optionally filtered by ticker prefix or asset class."""

    @abstractmethod
    async def create(self, entity: Asset) -> Asset:
        """Persist a new asset.  Raises if ticker already exists (CONFLICT)."""
