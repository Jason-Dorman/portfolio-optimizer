"""Universe repository interface."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from src.domain.models.assets import Universe
from src.domain.models.enums import UniverseType

from .base import Repository


class UniverseRepository(Repository[Universe]):
    """Read/write interface for Universe aggregates.

    add_assets and remove_assets operate on the universe_assets join table
    and return the updated Universe (with refreshed asset_count).
    """

    async def get(self, id: UUID) -> Universe | None:
        return await self.get_by_id(id)

    @abstractmethod
    async def get_by_id(self, universe_id: UUID) -> Universe | None:
        """Return the universe with the given ID, or None."""

    @abstractmethod
    async def list(
        self,
        universe_type: UniverseType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Universe]:
        """Return a page of universes, optionally filtered by type."""

    @abstractmethod
    async def create(self, entity: Universe) -> Universe:
        """Persist a new universe.  Raises if name already exists (CONFLICT)."""

    @abstractmethod
    async def add_assets(
        self,
        universe_id: UUID,
        asset_ids: list[UUID],
        is_benchmark: bool = False,
    ) -> Universe:
        """Add assets to the universe membership table and return the updated universe."""

    @abstractmethod
    async def remove_assets(
        self,
        universe_id: UUID,
        asset_ids: list[UUID],
    ) -> Universe:
        """Remove assets from the universe membership table and return the updated universe."""
