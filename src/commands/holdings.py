"""Holdings command: CreateHoldingsSnapshotCommand + CreateHoldingsSnapshotHandler."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from src.domain.models.holdings import HoldingsPosition, HoldingsSnapshot
from src.domain.repositories.assets import AssetRepository
from src.domain.repositories.holdings import HoldingsRepository


class HoldingsPositionInput(BaseModel):
    """A single position supplied by the caller.

    Exactly one of weight or market_value must be provided — not both, not neither.
    """

    ticker: str
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    market_value: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _exactly_one_value(self) -> HoldingsPositionInput:
        has_weight = self.weight is not None
        has_mv = self.market_value is not None
        if has_weight == has_mv:  # both or neither
            raise ValueError(
                "Provide exactly one of 'weight' or 'market_value' per position."
            )
        return self


class CreateHoldingsSnapshotCommand(BaseModel):
    label: str
    snapshot_date: date
    positions: list[HoldingsPositionInput] = Field(min_length=1)


class CreateHoldingsSnapshotHandler:
    """Resolve tickers, normalise values, and persist a holdings snapshot.

    Accepts either pre-normalised weights (must sum to 1) or raw market values
    (system normalises).  Mixed weight/market_value inputs are rejected by the
    command validator before the handler runs.
    """

    def __init__(
        self,
        holdings_repo: HoldingsRepository,
        asset_repo: AssetRepository,
    ) -> None:
        self._holdings_repo = holdings_repo
        self._asset_repo = asset_repo

    async def handle(
        self, command: CreateHoldingsSnapshotCommand
    ) -> HoldingsSnapshot:
        asset_ids = await self._resolve_tickers(command.positions)

        uses_market_values = command.positions[0].market_value is not None

        if uses_market_values:
            snapshot = HoldingsSnapshot.from_market_values(
                label=command.label,
                snapshot_date=command.snapshot_date,
                positions=[
                    (asset_ids[p.ticker.upper()], p.market_value)  # type: ignore[arg-type]
                    for p in command.positions
                ],
            )
        else:
            snap_id = uuid4()
            positions = [
                HoldingsPosition(
                    snapshot_id=snap_id,
                    asset_id=asset_ids[p.ticker.upper()],
                    weight=p.weight,  # type: ignore[arg-type]
                )
                for p in command.positions
            ]
            snapshot = HoldingsSnapshot(
                snapshot_id=snap_id,
                label=command.label,
                snapshot_date=command.snapshot_date,
                positions=positions,
            )

        return await self._holdings_repo.create(snapshot)

    async def _resolve_tickers(
        self, positions: list[HoldingsPositionInput]
    ) -> dict[str, UUID]:
        """Look up each ticker and return a ticker→asset_id mapping.

        Raises 404 for any ticker not found in the database.
        """
        resolved: dict[str, UUID] = {}
        missing: list[str] = []

        for pos in positions:
            ticker = pos.ticker.upper()
            if ticker in resolved:
                continue
            asset = await self._asset_repo.get_by_ticker(ticker)
            if asset is None:
                missing.append(ticker)
            else:
                resolved[ticker] = asset.asset_id

        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Tickers not found in database: {missing}. "
                "Create the asset first via POST /commands/assets.",
            )
        return resolved
