"""Screening command: RunScreeningCommand + RunScreeningHandler."""

from __future__ import annotations

from uuid import UUID

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel, model_validator

from src.commands._cov_utils import build_cov_array, extract_cov_asset_ids
from src.domain.models.assumptions import CovarianceMatrix
from src.domain.models.enums import ReferenceType
from src.domain.models.screening import ScreeningConfig, ScreeningRun
from src.domain.repositories.assets import AssetRepository
from src.domain.repositories.assumptions import AssumptionRepository
from src.domain.repositories.holdings import HoldingsRepository
from src.domain.repositories.screening import ScreeningRepository
from src.domain.repositories.universes import UniverseRepository
from src.domain.services.screening import ScreeningService


class RunScreeningCommand(BaseModel):
    """Score all candidates in a pool against a reference portfolio.

    Exactly one of reference_snapshot_id or reference_universe_id must be
    provided — there is no automatic fallback (FR4 constraint).
    """

    assumption_id: UUID
    candidate_pool_id: UUID
    reference_snapshot_id: UUID | None = None
    reference_universe_id: UUID | None = None
    config: ScreeningConfig | None = None

    @model_validator(mode="after")
    def _exactly_one_reference(self) -> RunScreeningCommand:
        has_snapshot = self.reference_snapshot_id is not None
        has_universe = self.reference_universe_id is not None
        if has_snapshot == has_universe:
            raise ValueError(
                "Provide exactly one of 'reference_snapshot_id' or "
                "'reference_universe_id'."
            )
        return self


class RunScreeningHandler:
    """Orchestrate the screening pipeline and persist the results.

    Steps:
      1. Load assumption set and covariance matrix.
      2. Load candidate pool asset metadata.
      3. Build reference portfolio weights (snapshot or equal-weight universe).
      4. Construct the covariance numpy array and asset_index mapping.
      5. Call ScreeningService.score_candidates().
      6. Persist ScreeningRun with all scores.
    """

    def __init__(
        self,
        assumption_repo: AssumptionRepository,
        universe_repo: UniverseRepository,
        holdings_repo: HoldingsRepository,
        asset_repo: AssetRepository,
        screening_repo: ScreeningRepository,
        screening_service: ScreeningService,
    ) -> None:
        self._assumption_repo = assumption_repo
        self._universe_repo = universe_repo
        self._holdings_repo = holdings_repo
        self._asset_repo = asset_repo
        self._screening_repo = screening_repo
        self._screening_service = screening_service

    async def handle(self, command: RunScreeningCommand) -> ScreeningRun:
        assumption = await self._assumption_repo.get_by_id(command.assumption_id)
        if assumption is None:
            raise HTTPException(
                status_code=404,
                detail=f"AssumptionSet {command.assumption_id} not found.",
            )

        covariance = await self._assumption_repo.get_covariance_matrix(
            command.assumption_id
        )
        if covariance is None:
            raise HTTPException(
                status_code=422,
                detail=f"No covariance matrix found for assumption {command.assumption_id}.",
            )

        candidate_ids = await self._universe_repo.get_asset_ids(
            command.candidate_pool_id
        )
        if not candidate_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Candidate pool {command.candidate_pool_id} has no assets.",
            )

        reference_weights, reference_asset_ids = await self._build_reference(command)

        # Gather all asset IDs that appear in the covariance matrix
        cov_asset_ids = extract_cov_asset_ids(covariance)
        asset_index = {aid: i for i, aid in enumerate(cov_asset_ids)}
        cov_array = build_cov_array(covariance, asset_index)

        # Load asset metadata for reference + candidate assets
        all_ids = set(reference_asset_ids) | set(candidate_ids)
        asset_map = {}
        for aid in all_ids:
            asset = await self._asset_repo.get_by_id(aid)
            if asset is not None:
                asset_map[aid] = asset

        reference_assets = {aid: asset_map[aid] for aid in reference_asset_ids if aid in asset_map}
        candidate_assets = {aid: asset_map[aid] for aid in candidate_ids if aid in asset_map}

        config = command.config or ScreeningConfig.default()

        if command.reference_snapshot_id is not None:
            run = ScreeningRun.for_holdings(
                assumption_id=command.assumption_id,
                candidate_pool_id=command.candidate_pool_id,
                reference_snapshot_id=command.reference_snapshot_id,
                config=config,
            )
        else:
            run = ScreeningRun.for_universe(
                assumption_id=command.assumption_id,
                candidate_pool_id=command.candidate_pool_id,
                reference_universe_id=command.reference_universe_id,  # type: ignore[arg-type]
                config=config,
            )

        scores = self._screening_service.score_candidates(
            screening_id=run.screening_id,
            reference_weights=reference_weights,
            reference_assets=reference_assets,
            candidate_ids=candidate_ids,
            candidate_assets=candidate_assets,
            covariance=cov_array,
            asset_index=asset_index,
            config=config,
        )

        run = run.model_copy(update={"scores": scores})
        return await self._screening_repo.create(run)

    async def _build_reference(
        self, command: RunScreeningCommand
    ) -> tuple[dict[UUID, float], list[UUID]]:
        """Return (weights_dict, ordered_asset_ids) for the reference portfolio."""
        if command.reference_snapshot_id is not None:
            snapshot = await self._holdings_repo.get_by_id(
                command.reference_snapshot_id
            )
            if snapshot is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"HoldingsSnapshot {command.reference_snapshot_id} not found.",
                )
            asset_ids = [p.asset_id for p in snapshot.positions]
            weights = {p.asset_id: p.weight for p in snapshot.positions}
            return weights, asset_ids

        # Equal-weight the reference universe
        ref_universe = await self._universe_repo.get_by_id(
            command.reference_universe_id  # type: ignore[arg-type]
        )
        if ref_universe is None:
            raise HTTPException(
                status_code=404,
                detail=f"Reference universe {command.reference_universe_id} not found.",
            )
        asset_ids = await self._universe_repo.get_asset_ids(
            command.reference_universe_id  # type: ignore[arg-type]
        )
        if not asset_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Reference universe {command.reference_universe_id} has no assets.",
            )
        equal_weight = 1.0 / len(asset_ids)
        weights = {aid: equal_weight for aid in asset_ids}
        return weights, asset_ids


# ─────────────────────────────────────────────────────────────────────────── #
# Module-level helpers (re-exported from _cov_utils for backward compatibility) #
# ─────────────────────────────────────────────────────────────────────────── #

_extract_cov_asset_ids = extract_cov_asset_ids
_build_cov_array = build_cov_array
