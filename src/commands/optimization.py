"""Optimization command: RunOptimizationCommand + RunOptimizationHandler."""

from __future__ import annotations

import logging
from uuid import UUID

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.domain.models.enums import OptimizationStatus, RunType
from src.domain.models.optimization import (
    OptimizationConstraints,
    OptimizationResult,
    OptimizationRun,
    PortfolioWeight,
)
from src.domain.repositories.assumptions import AssumptionRepository
from src.domain.repositories.holdings import HoldingsRepository
from src.domain.repositories.optimization import OptimizationRepository
from src.domain.services.optimization import OptimizationService

logger = logging.getLogger(__name__)


class RunOptimizationCommand(BaseModel):
    """Run a portfolio optimization against a stored assumption set.

    run_type controls which objective is used:
      MVP             → minimize variance (ignore rf_annual)
      TANGENCY        → maximize Sharpe (uses rf_annual from the assumption set)
      FRONTIER_POINT  → minimize variance for target_return (requires target_return)
      FRONTIER_SERIES → not supported as a single command; use the query endpoint

    reference_snapshot_id is optional:
      - When constraints.turnover_cap is set and reference_snapshot_id is provided,
        the snapshot weights become the turnover baseline.
      - When turnover_cap is set but no snapshot is given, the handler falls back to
        the latest successful run for the same universe (OptimizationRepository lookup).
    """

    assumption_id: UUID
    run_type: RunType
    constraints: OptimizationConstraints = Field(
        default_factory=OptimizationConstraints.long_only_unconstrained
    )
    reference_snapshot_id: UUID | None = None
    target_return: float | None = None  # FRONTIER_POINT only


class RunOptimizationHandler:
    """Load µ + Σ, call the solver, and persist the OptimizationRun.

    Infeasible results are persisted with status=INFEASIBLE (not raised as HTTP
    errors) so callers can inspect the reason without losing the audit trail.
    FRONTIER_SERIES is rejected — use the query-side frontier endpoint.
    """

    def __init__(
        self,
        assumption_repo: AssumptionRepository,
        holdings_repo: HoldingsRepository,
        optimization_repo: OptimizationRepository,
        optimization_service: OptimizationService,
    ) -> None:
        self._assumption_repo = assumption_repo
        self._holdings_repo = holdings_repo
        self._optimization_repo = optimization_repo
        self._optimization_service = optimization_service

    async def handle(self, command: RunOptimizationCommand) -> OptimizationRun:
        if command.run_type == RunType.FRONTIER_SERIES:
            raise HTTPException(
                status_code=400,
                detail="FRONTIER_SERIES is not supported as a command. "
                "Use the query endpoint GET /queries/optimization/frontier.",
            )

        assumption = await self._assumption_repo.get_by_id(command.assumption_id)
        if assumption is None:
            raise HTTPException(
                status_code=404,
                detail=f"AssumptionSet {command.assumption_id} not found.",
            )

        stats = await self._assumption_repo.get_asset_stats(command.assumption_id)
        if not stats:
            raise HTTPException(
                status_code=422,
                detail=f"No asset stats found for assumption {command.assumption_id}. "
                "Was CreateAssumptionSet called successfully?",
            )

        covariance = await self._assumption_repo.get_covariance_matrix(
            command.assumption_id
        )
        if covariance is None:
            raise HTTPException(
                status_code=422,
                detail=f"No covariance matrix for assumption {command.assumption_id}.",
            )

        # Build ordered asset list and numpy arrays
        asset_ids = [s.asset_id for s in stats]
        mu = np.array([s.mu_annual for s in stats])
        sigma = _build_sigma(covariance, asset_ids)

        prev_weights = await self._resolve_prev_weights(
            command, asset_ids, assumption.universe_id
        )

        solver_result = self._call_solver(command, mu, sigma, assumption.rf_annual, prev_weights, asset_ids)

        run = _build_optimization_run(command, solver_result, asset_ids)
        return await self._optimization_repo.create(run)

    def _call_solver(
        self,
        command: RunOptimizationCommand,
        mu: np.ndarray,
        sigma: np.ndarray,
        rf_annual: float,
        prev_weights: np.ndarray | None,
        asset_ids: list[UUID],
    ):
        """Dispatch to the appropriate OptimizationService method."""
        if command.run_type == RunType.MVP:
            return self._optimization_service.optimize_mvp(
                mu, sigma, command.constraints,
                prev_weights=prev_weights, asset_ids=asset_ids,
            )
        if command.run_type == RunType.TANGENCY:
            return self._optimization_service.optimize_tangency(
                mu, sigma, rf_annual, command.constraints,
                prev_weights=prev_weights, asset_ids=asset_ids,
            )
        # FRONTIER_POINT
        if command.target_return is None:
            raise HTTPException(
                status_code=400,
                detail="target_return is required for FRONTIER_POINT run_type.",
            )
        return self._optimization_service.optimize_frontier_point(
            mu, sigma, command.target_return, command.constraints,
            prev_weights=prev_weights, asset_ids=asset_ids,
        )

    async def _resolve_prev_weights(
        self,
        command: RunOptimizationCommand,
        asset_ids: list[UUID],
        universe_id: UUID,
    ) -> np.ndarray | None:
        """Return previous weights array when a turnover cap is active."""
        if command.constraints.turnover_cap is None:
            return None

        if command.reference_snapshot_id is not None:
            snapshot = await self._holdings_repo.get_by_id(
                command.reference_snapshot_id
            )
            if snapshot is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"HoldingsSnapshot {command.reference_snapshot_id} not found.",
                )
            weight_map = {p.asset_id: p.weight for p in snapshot.positions}
            return np.array([weight_map.get(aid, 0.0) for aid in asset_ids])

        # Fallback: use the most recent successful run for the same universe
        latest = await self._optimization_repo.get_latest_for_universe(universe_id)
        if latest is None:
            logger.warning(
                "turnover_cap is set but no previous run exists for universe %s; "
                "turnover constraint will be ignored by the solver.",
                universe_id,
            )
            return None

        weights = await self._optimization_repo.get_weights(latest.run_id)
        weight_map = {w.asset_id: w.weight for w in weights}
        return np.array([weight_map.get(aid, 0.0) for aid in asset_ids])


# ─────────────────────────────────────────────────────────────────────────── #
# Module-level helpers                                                          #
# ─────────────────────────────────────────────────────────────────────────── #


def _build_sigma(covariance, asset_ids: list[UUID]) -> np.ndarray:
    """Reconstruct the full covariance matrix in asset_ids order."""
    from src.commands._cov_utils import build_cov_array, extract_cov_asset_ids

    cov_ids = extract_cov_asset_ids(covariance)
    asset_index = {aid: i for i, aid in enumerate(cov_ids)}
    full = build_cov_array(covariance, asset_index)

    # Re-index to the ordered asset_ids list (stats ordering)
    idx = [asset_index[aid] for aid in asset_ids if aid in asset_index]
    return full[np.ix_(idx, idx)]


def _build_optimization_run(command, solver_result, asset_ids: list[UUID]) -> OptimizationRun:
    """Wrap a SolverResult into an OptimizationRun domain object.

    MCR/CRC/PRC are stored as 0.0 — risk decomposition requires sigma which is
    not available at this layer.  Full decomp is available via the query endpoint.
    """
    if solver_result.is_feasible and solver_result.weights is not None:
        weights_list = [
            PortfolioWeight(
                run_id=_PLACEHOLDER_UUID,  # will be replaced after run_id is set
                asset_id=asset_ids[i],
                weight=float(solver_result.weights[i]),
                mcr=0.0,
                crc=0.0,
                prc=0.0,
            )
            for i in range(len(asset_ids))
        ]
        result = OptimizationResult(
            run_id=_PLACEHOLDER_UUID,
            exp_return=solver_result.exp_return,  # type: ignore[arg-type]
            variance=solver_result.variance,  # type: ignore[arg-type]
            stdev=solver_result.stdev,  # type: ignore[arg-type]
            sharpe=solver_result.sharpe,
            hhi=solver_result.hhi,  # type: ignore[arg-type]
            effective_n=solver_result.effective_n,  # type: ignore[arg-type]
            explanation=solver_result.explanation,
        )
        status = OptimizationStatus.SUCCESS
        infeasibility_reason = None
    else:
        weights_list = []
        result = None
        status = OptimizationStatus.INFEASIBLE
        infeasibility_reason = solver_result.infeasibility_reason or "Solver infeasible"

    if command.run_type == RunType.MVP:
        run = OptimizationRun.create_mvp(
            assumption_id=command.assumption_id,
            status=status,
            constraints=command.constraints,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights_list,
            reference_snapshot_id=command.reference_snapshot_id,
            solver_meta=solver_result.solver_meta,
        )
    elif command.run_type == RunType.TANGENCY:
        run = OptimizationRun.create_tangency(
            assumption_id=command.assumption_id,
            status=status,
            constraints=command.constraints,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights_list,
            reference_snapshot_id=command.reference_snapshot_id,
            solver_meta=solver_result.solver_meta,
        )
    else:  # FRONTIER_POINT
        run = OptimizationRun.create_frontier_point(
            assumption_id=command.assumption_id,
            target_return=command.target_return,  # type: ignore[arg-type]
            status=status,
            constraints=command.constraints,
            infeasibility_reason=infeasibility_reason,
            result=result,
            weights=weights_list,
            reference_snapshot_id=command.reference_snapshot_id,
            solver_meta=solver_result.solver_meta,
        )

    # Stamp run_id on weights and result now that we have it
    if run.weights:
        stamped_weights = [w.model_copy(update={"run_id": run.run_id}) for w in run.weights]
        stamped_result = run.result.model_copy(update={"run_id": run.run_id}) if run.result else None
        run = run.model_copy(update={"weights": stamped_weights, "result": stamped_result})

    return run


# Sentinel used before run_id is known; replaced immediately in _build_optimization_run
from uuid import UUID as _UUID
_PLACEHOLDER_UUID = _UUID("00000000-0000-0000-0000-000000000000")
