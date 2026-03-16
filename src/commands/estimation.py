"""Estimation commands: ComputeReturns and CreateAssumptionSet."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.domain.models.assumptions import AssetStats, AssumptionSet, CovarianceMatrix
from src.domain.models.enums import (
    CovMethod,
    Estimator,
    Frequency,
    ReturnType,
)
from src.domain.models.market_data import ReturnPoint
from src.domain.repositories.assumptions import AssumptionRepository
from src.domain.repositories.prices import PriceRepository
from src.domain.repositories.returns import ReturnRepository
from src.domain.repositories.universes import UniverseRepository
from src.domain.services.estimation import EstimationService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────── #
# Compute returns                                                               #
# ─────────────────────────────────────────────────────────────────────────── #


class ComputeReturnsCommand(BaseModel):
    """Derive and store return series for all non-benchmark assets in a universe.

    Operates on prices already stored in price_bars for the given frequency.
    start_date and end_date are inclusive window overrides; when omitted the
    full available price history is used.
    """

    universe_id: UUID
    frequency: Frequency
    return_type: ReturnType
    start_date: date | None = None
    end_date: date | None = None


class ComputeReturnsResult(BaseModel):
    universe_id: UUID
    assets_processed: int
    returns_inserted: int
    start_date: date | None
    end_date: date | None
    errors: list[str]


class ComputeReturnsHandler:
    """Compute return series from stored prices and upsert into return_series.

    Per-asset errors are collected in ComputeReturnsResult.errors rather than
    aborting the batch — an asset with insufficient price history should not
    block other assets.
    """

    def __init__(
        self,
        universe_repo: UniverseRepository,
        price_repo: PriceRepository,
        return_repo: ReturnRepository,
        estimation_service: EstimationService,
    ) -> None:
        self._universe_repo = universe_repo
        self._price_repo = price_repo
        self._return_repo = return_repo
        self._estimation = estimation_service

    async def handle(self, command: ComputeReturnsCommand) -> ComputeReturnsResult:
        universe = await self._universe_repo.get_by_id(command.universe_id)
        if universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Universe {command.universe_id} not found.",
            )

        asset_ids = await self._universe_repo.get_asset_ids(command.universe_id)
        if not asset_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Universe {command.universe_id} has no assets.",
            )

        errors: list[str] = []
        total_inserted = 0

        for asset_id in asset_ids:
            try:
                bars = await self._price_repo.get_prices(
                    asset_id, command.frequency, command.start_date, command.end_date
                )
                if len(bars) < 2:
                    errors.append(
                        f"{asset_id}: fewer than 2 price bars available — skipped"
                    )
                    continue

                prices_series = pd.Series(
                    {bar.bar_date: bar.adj_close for bar in bars}
                )
                prices_df = pd.DataFrame({"asset": prices_series})
                returns_df = self._estimation.compute_returns(
                    prices_df, command.return_type
                )

                points = [
                    ReturnPoint(
                        asset_id=asset_id,
                        bar_date=idx.date() if hasattr(idx, "date") else idx,
                        frequency=command.frequency,
                        return_type=command.return_type,
                        ret=float(row["asset"]),
                    )
                    for idx, row in returns_df.iterrows()
                ]
                n = await self._return_repo.bulk_insert(points)
                total_inserted += n

            except Exception as exc:
                logger.exception("Unexpected error computing returns for asset %s", asset_id)
                errors.append(f"{asset_id}: {exc}")

        return ComputeReturnsResult(
            universe_id=command.universe_id,
            assets_processed=len(asset_ids),
            returns_inserted=total_inserted,
            start_date=command.start_date,
            end_date=command.end_date,
            errors=errors,
        )


# ─────────────────────────────────────────────────────────────────────────── #
# Create assumption set                                                         #
# ─────────────────────────────────────────────────────────────────────────── #


class CreateAssumptionSetCommand(BaseModel):
    """Estimate µ, Σ for a universe and persist as a versioned AssumptionSet.

    Uses pre-computed return_series rows for the lookback window.  Call
    POST /commands/returns/compute first if return series are stale.

    rf_annual is the annualised risk-free rate used for Sharpe computation
    during downstream optimisation; it is not estimated here.
    """

    universe_id: UUID
    lookback_start: date
    lookback_end: date
    frequency: Frequency
    return_type: ReturnType = ReturnType.SIMPLE
    rf_annual: float = Field(ge=0.0)
    estimator: Estimator = Estimator.HISTORICAL
    cov_method: CovMethod = CovMethod.SAMPLE


class CreateAssumptionSetHandler:
    """Load return series, estimate µ + Σ, validate PSD, and persist.

    PSD repair (nearest-PSD projection) is applied automatically when the
    estimated covariance matrix fails the positive-semi-definite check.
    The repair is recorded on the AssumptionSet (psd_repair_applied / note).
    """

    def __init__(
        self,
        universe_repo: UniverseRepository,
        return_repo: ReturnRepository,
        assumption_repo: AssumptionRepository,
        estimation_service: EstimationService,
    ) -> None:
        self._universe_repo = universe_repo
        self._return_repo = return_repo
        self._assumption_repo = assumption_repo
        self._estimation = estimation_service

    async def handle(self, command: CreateAssumptionSetCommand) -> AssumptionSet:
        universe = await self._universe_repo.get_by_id(command.universe_id)
        if universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Universe {command.universe_id} not found.",
            )

        asset_ids = await self._universe_repo.get_asset_ids(command.universe_id)
        if not asset_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Universe {command.universe_id} has no assets.",
            )

        returns_df = await self._load_returns_df(
            asset_ids, command.frequency, command.return_type,
            command.lookback_start, command.lookback_end,
        )

        if returns_df.empty or returns_df.shape[0] < 2:
            raise HTTPException(
                status_code=422,
                detail="Insufficient return observations in the lookback window. "
                "Ensure prices are ingested and returns are computed first.",
            )

        # Drop assets with no data in the window (inner join on dates)
        returns_df = returns_df.dropna(axis=1, how="all")
        active_asset_ids: list[UUID] = list(returns_df.columns)

        if len(active_asset_ids) < 2:
            raise HTTPException(
                status_code=422,
                detail="At least 2 assets with return data are required to estimate Σ.",
            )

        annualization_factor = command.frequency.periods_per_year
        mu_arr = self._estimation.compute_mu(
            returns_df, annualization_factor, command.estimator
        )
        sigma_arr = self._estimation.compute_sigma(
            returns_df, annualization_factor, command.cov_method
        )

        psd_ok, _ = self._estimation.validate_psd(sigma_arr)
        psd_repair_applied = False
        psd_repair_note: str | None = None

        if not psd_ok:
            sigma_arr, psd_repair_note = self._estimation.repair_psd(sigma_arr)
            psd_repair_applied = True
            logger.info(
                "PSD repair applied for universe %s: %s",
                command.universe_id,
                psd_repair_note,
            )

        assumption_set = AssumptionSet.create(
            universe_id=command.universe_id,
            frequency=command.frequency,
            return_type=command.return_type,
            lookback_start=command.lookback_start,
            lookback_end=command.lookback_end,
            rf_annual=command.rf_annual,
            estimator=command.estimator,
            cov_method=command.cov_method,
        )
        # Attach repair metadata (AssumptionSet is frozen; model_copy is used)
        if psd_repair_applied:
            assumption_set = assumption_set.model_copy(
                update={
                    "psd_repair_applied": True,
                    "psd_repair_note": psd_repair_note,
                }
            )

        volatilities = np.sqrt(np.diag(sigma_arr))
        stats = [
            AssetStats(
                assumption_id=assumption_set.assumption_id,
                asset_id=active_asset_ids[i],
                mu_annual=float(mu_arr[i]),
                sigma_annual=float(volatilities[i]),
            )
            for i in range(len(active_asset_ids))
        ]

        covariance = CovarianceMatrix.from_full_matrix(
            assumption_id=assumption_set.assumption_id,
            asset_ids=active_asset_ids,
            matrix=sigma_arr.tolist(),
        )

        return await self._assumption_repo.create(assumption_set, stats, covariance)

    async def _load_returns_df(
        self,
        asset_ids: list[UUID],
        frequency: Frequency,
        return_type: ReturnType,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Load returns for all assets into a DataFrame (columns = asset_id, index = date)."""
        data: dict[UUID, dict] = {}
        for asset_id in asset_ids:
            points = await self._return_repo.get_returns(
                asset_id=asset_id,
                frequency=frequency,
                return_type=return_type,
                start=start,
                end=end,
            )
            if points:
                data[asset_id] = {p.bar_date: p.ret for p in points}

        if not data:
            return pd.DataFrame()

        return pd.DataFrame(data)
