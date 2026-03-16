"""Universe commands: Create, AddAssets, RemoveAssets."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.domain.models.assets import Universe
from src.domain.models.enums import UniverseType
from src.domain.repositories.universes import UniverseRepository


# ─────────────────────────────────────────────────────────────────────────── #
# Commands                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


class CreateUniverseCommand(BaseModel):
    name: str
    description: str = ""
    universe_type: UniverseType
    asset_ids: list[UUID] = Field(default_factory=list)


class AddUniverseAssetsCommand(BaseModel):
    asset_ids: list[UUID]
    is_benchmark: bool = False


class RemoveUniverseAssetsCommand(BaseModel):
    asset_ids: list[UUID]


# ─────────────────────────────────────────────────────────────────────────── #
# Handlers                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #


class CreateUniverseHandler:
    """Persist a new universe, optionally seeding it with initial assets."""

    def __init__(self, universe_repo: UniverseRepository) -> None:
        self._universe_repo = universe_repo

    async def handle(self, command: CreateUniverseCommand) -> Universe:
        if command.universe_type == UniverseType.ACTIVE:
            universe = Universe.create_active(
                name=command.name, description=command.description
            )
        else:
            universe = Universe.create_candidate_pool(
                name=command.name, description=command.description
            )
        created = await self._universe_repo.create(universe)
        if command.asset_ids:
            created = await self._universe_repo.add_assets(
                created.universe_id, command.asset_ids
            )
        return created


class AddUniverseAssetsHandler:
    """Add assets to an existing universe."""

    def __init__(self, universe_repo: UniverseRepository) -> None:
        self._universe_repo = universe_repo

    async def handle(
        self, universe_id: UUID, command: AddUniverseAssetsCommand
    ) -> Universe:
        universe = await self._universe_repo.get_by_id(universe_id)
        if universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Universe {universe_id} not found.",
            )
        return await self._universe_repo.add_assets(
            universe_id, command.asset_ids, command.is_benchmark
        )


class RemoveUniverseAssetsHandler:
    """Remove assets from an existing universe."""

    def __init__(self, universe_repo: UniverseRepository) -> None:
        self._universe_repo = universe_repo

    async def handle(
        self, universe_id: UUID, command: RemoveUniverseAssetsCommand
    ) -> Universe:
        universe = await self._universe_repo.get_by_id(universe_id)
        if universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Universe {universe_id} not found.",
            )
        return await self._universe_repo.remove_assets(
            universe_id, command.asset_ids
        )
