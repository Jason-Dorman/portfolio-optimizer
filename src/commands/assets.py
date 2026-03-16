"""Asset command: CreateAssetCommand + CreateAssetHandler."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import HTTPException

from src.domain.models.assets import Asset
from src.domain.models.enums import AssetClass, Geography
from src.domain.repositories.assets import AssetRepository


class CreateAssetCommand(BaseModel):
    ticker: str
    name: str
    asset_class: AssetClass
    sub_class: str
    geography: Geography
    currency: str
    is_etf: bool = True
    sector: str | None = None


class CreateAssetHandler:
    """Persist a new investable asset.

    Raises 409 when a ticker already exists (case-insensitive check).
    Normalises ticker to uppercase and currency to uppercase before creation.
    """

    def __init__(self, asset_repo: AssetRepository) -> None:
        self._asset_repo = asset_repo

    async def handle(self, command: CreateAssetCommand) -> Asset:
        ticker = command.ticker.upper()
        existing = await self._asset_repo.get_by_ticker(ticker)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Asset with ticker '{ticker}' already exists.",
            )
        asset = Asset.create(
            ticker=ticker,
            name=command.name,
            asset_class=command.asset_class,
            sub_class=command.sub_class,
            geography=command.geography,
            currency=command.currency.upper(),
            is_etf=command.is_etf,
            sector=command.sector,
        )
        return await self._asset_repo.create(asset)
