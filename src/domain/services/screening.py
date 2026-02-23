"""Asset screening service.

Implements DATA-MODEL.md §4.9: four diversification signals scored against
a reference portfolio (current holdings snapshot or seed universe).

All four signals produce normalized scores in [0, 1].  A degenerate signal
(all candidates share the same raw value so min == max) returns 0.0 for
every candidate — the signal is uninformative and must not distort the
composite score.

Pipeline:
    score_candidates
        → _build_reference_context   (derive reference quantities once)
        → _compute_raw_signals       (un-normalised signals per candidate)
        → _finalize
            → _compute_composites    (normalise + weight + sort)
            → _build_ranked_scores   (rank + explain → ScreeningScore)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from src.domain.models.assets import Asset
from src.domain.models.screening import ScreeningConfig, ScreeningScore, ScoreWeights


@dataclass
class _ReferenceContext:
    """Derived quantities from the reference portfolio.

    Computed once by _build_reference_context and shared across all four
    signal calculators, avoiding repeated matrix operations per candidate.
    """

    weights_arr: np.ndarray          # dense weight vector aligned to covariance columns
    weights_dict: dict[UUID, float]  # original weights dict (required by sector-gap signal)
    asset_list: list[Asset]          # reference assets as a flat list (sector-gap signal)
    indices: list[int]               # reference asset column indices in covariance
    corr_matrix: np.ndarray          # full correlation matrix derived from covariance
    sigma_R: float                   # reference portfolio annualised volatility
    hhi_R: float                     # reference HHI concentration
    n_eff_R: float                   # effective number of assets in reference


@dataclass(frozen=True)
class _CandidateRaw:
    """Un-normalised signal values for a single candidate asset.

    Separating raw signals from normalised scores makes the normalisation
    step an explicit, independently testable transformation.
    """

    asset_id: UUID
    candidate_idx: int               # column/row index in the covariance matrix
    avg_pairwise_corr: float
    marginal_vol_reduction: float
    sector_gap_score: float
    hhi_reduction: float


class ScreeningService:
    """Pure computation service for scoring and ranking screening candidates.

    Responsibilities (single, focused):
    - Orchestrate the screening pipeline.
    - Compute four diversification signals per candidate.
    - Normalise signals and compute a weighted composite score.
    - Rank candidates by composite score (rank 1 = highest composite).
    - Generate plain-language explanations with concrete numbers.

    The class is stateless; all configuration is passed per-call.
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def score_candidates(
        self,
        screening_id: UUID,
        reference_weights: dict[UUID, float],
        reference_assets: dict[UUID, Asset],
        candidate_ids: list[UUID],
        candidate_assets: dict[UUID, Asset],
        covariance: np.ndarray,
        asset_index: dict[UUID, int],
        config: ScreeningConfig,
    ) -> list[ScreeningScore]:
        """Score all candidates and return a ranked list with explanations.

        Implements DATA-MODEL.md §4.9 composite screening score.

        Args:
            screening_id: ID of the parent ScreeningRun, stamped on each score.
            reference_weights: UUID → weight for every asset in the reference portfolio.
            reference_assets: UUID → Asset for every asset in the reference portfolio.
            candidate_ids: Ordered list of candidate asset UUIDs to score.
            candidate_assets: UUID → Asset for every candidate.
            covariance: Annualised covariance matrix (n × n) covering all assets.
            asset_index: UUID → column/row index in the covariance matrix.
            config: Tunable parameters — δ, θ, and λ₁…λ₄ composite signal weights.

        Returns:
            list[ScreeningScore] ordered by rank ascending (rank 1 = best).
        """
        valid_ids = [cid for cid in candidate_ids if cid in asset_index]
        if not valid_ids:
            return []

        ctx = self._build_reference_context(
            reference_weights, reference_assets, covariance, asset_index
        )
        raw_signals = self._compute_raw_signals(
            ctx, valid_ids, candidate_assets, covariance, asset_index, config
        )
        return self._finalize(raw_signals, ctx, config, screening_id)

    # ------------------------------------------------------------------ #
    # Pipeline stages                                                      #
    # ------------------------------------------------------------------ #

    def _build_reference_context(
        self,
        reference_weights: dict[UUID, float],
        reference_assets: dict[UUID, Asset],
        covariance: np.ndarray,
        asset_index: dict[UUID, int],
    ) -> _ReferenceContext:
        """Derive all reference-portfolio quantities needed by the four signals.

        Correlation matrix: DATA-MODEL.md §4.3 — ρ_{ij} = Σ_{ij} / (σ_i · σ_j).
        """
        n = covariance.shape[0]
        weights_arr = self._build_weight_vector(reference_weights, asset_index, n)
        indices = [asset_index[aid] for aid in reference_weights if aid in asset_index]

        volatilities = np.sqrt(np.diag(covariance))
        outer_vols = np.outer(volatilities, volatilities)
        corr_matrix = np.where(outer_vols > 0.0, covariance / outer_vols, 0.0)

        sigma_R = float(np.sqrt(weights_arr @ covariance @ weights_arr))
        hhi_R = float(np.sum(weights_arr**2))
        n_eff_R = 1.0 / hhi_R if hhi_R > 0.0 else float("inf")

        return _ReferenceContext(
            weights_arr=weights_arr,
            weights_dict=reference_weights,
            asset_list=list(reference_assets.values()),
            indices=indices,
            corr_matrix=corr_matrix,
            sigma_R=sigma_R,
            hhi_R=hhi_R,
            n_eff_R=n_eff_R,
        )

    def _compute_raw_signals(
        self,
        ctx: _ReferenceContext,
        valid_ids: list[UUID],
        candidate_assets: dict[UUID, Asset],
        covariance: np.ndarray,
        asset_index: dict[UUID, int],
        config: ScreeningConfig,
    ) -> list[_CandidateRaw]:
        """Compute un-normalised signal values for every valid candidate."""
        delta = config.nominal_add_weight
        threshold = config.sector_gap_threshold

        return [
            _CandidateRaw(
                asset_id=cid,
                candidate_idx=asset_index[cid],
                avg_pairwise_corr=self._calc_avg_correlation(
                    asset_index[cid], ctx.indices, ctx.corr_matrix
                ),
                marginal_vol_reduction=self._calc_marginal_vol_reduction(
                    asset_index[cid], ctx.weights_arr.copy(), covariance, delta
                ),
                sector_gap_score=self._calc_sector_gap_score(
                    candidate_assets[cid], ctx.asset_list, ctx.weights_dict, threshold
                ),
                hhi_reduction=self._calc_hhi_reduction(
                    asset_index[cid], ctx.weights_arr.copy(), delta
                ),
            )
            for cid in valid_ids
        ]

    def _finalize(
        self,
        raw_signals: list[_CandidateRaw],
        ctx: _ReferenceContext,
        config: ScreeningConfig,
        screening_id: UUID,
    ) -> list[ScreeningScore]:
        """Normalise, rank, and explain — delegates to the two sub-stages."""
        scored = self._compute_composites(raw_signals, config.score_weights)
        return self._build_ranked_scores(scored, ctx, config, screening_id)

    def _compute_composites(
        self,
        raw_signals: list[_CandidateRaw],
        signal_weights: ScoreWeights,
    ) -> list[tuple[_CandidateRaw, float]]:
        """Normalise all four signals, apply weights, and sort descending.

        Correlation uses inverted normalisation (lower raw → higher score).
        Sector gap requires no normalisation: values are already in {0, 0.5, 1}.
        """
        norm_corr = self._normalize_scores(
            [r.avg_pairwise_corr for r in raw_signals], invert=True
        )
        norm_mvr = self._normalize_scores(
            [r.marginal_vol_reduction for r in raw_signals]
        )
        norm_gap = [r.sector_gap_score for r in raw_signals]
        norm_hhi = self._normalize_scores([r.hhi_reduction for r in raw_signals])

        scored = [
            (
                raw,
                signal_weights.correlation * norm_corr[i]
                + signal_weights.marginal_vol * norm_mvr[i]
                + signal_weights.sector_gap * norm_gap[i]
                + signal_weights.hhi * norm_hhi[i],
            )
            for i, raw in enumerate(raw_signals)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _build_ranked_scores(
        self,
        scored: list[tuple[_CandidateRaw, float]],
        ctx: _ReferenceContext,
        config: ScreeningConfig,
        screening_id: UUID,
    ) -> list[ScreeningScore]:
        """Assign ordinal ranks and generate plain-language explanations."""
        reference_stats = {
            "sigma_R": ctx.sigma_R,
            "hhi_R": ctx.hhi_R,
            "n_eff_R": ctx.n_eff_R,
            "delta": config.nominal_add_weight,
        }

        final_scores: list[ScreeningScore] = []
        for rank, (raw, composite) in enumerate(scored, start=1):
            # ScreeningScore is frozen; build with placeholder then copy with
            # the real explanation. model_copy is supported on frozen Pydantic v2.
            score = ScreeningScore(
                screening_id=screening_id,
                asset_id=raw.asset_id,
                avg_pairwise_corr=raw.avg_pairwise_corr,
                marginal_vol_reduction=raw.marginal_vol_reduction,
                sector_gap_score=raw.sector_gap_score,
                hhi_reduction=raw.hhi_reduction,
                composite_score=composite,
                rank=rank,
                explanation="",
            )
            explanation = self._generate_explanation(score, reference_stats)
            final_scores.append(score.model_copy(update={"explanation": explanation}))

        return final_scores

    # ------------------------------------------------------------------ #
    # Signal calculators                                                   #
    # ------------------------------------------------------------------ #

    def _calc_avg_correlation(
        self,
        candidate_idx: int,
        reference_indices: list[int],
        corr_matrix: np.ndarray,
    ) -> float:
        """Average pairwise correlation of candidate against all reference assets.

        Implements DATA-MODEL.md §4.9 Signal 1:
            AvgCorr(c) = (1 / |R|) · Σ_{r ∈ R} ρ_{c,r}

        Returns 0.0 when the reference is empty.
        """
        if not reference_indices:
            return 0.0
        return float(np.mean(corr_matrix[candidate_idx, reference_indices]))

    def _calc_marginal_vol_reduction(
        self,
        candidate_idx: int,
        reference_weights: np.ndarray,
        cov_matrix: np.ndarray,
        delta: float,
    ) -> float:
        """Volatility change from adding the candidate at nominal weight δ.

        Implements DATA-MODEL.md §4.9 Signal 2:
            w_pro = (1−δ)·w_R  ∪  {δ for candidate}
            MVR(c) = σ_R − √(w_pro^T Σ w_pro)

        Positive → candidate reduces portfolio volatility.
        Negative → candidate increases portfolio volatility.
        """
        sigma_R = float(np.sqrt(reference_weights @ cov_matrix @ reference_weights))

        pro_weights = reference_weights * (1.0 - delta)
        pro_weights[candidate_idx] += delta

        variance_pro = float(pro_weights @ cov_matrix @ pro_weights)
        sigma_pro = float(np.sqrt(max(variance_pro, 0.0)))

        return sigma_R - sigma_pro

    def _calc_sector_gap_score(
        self,
        candidate: Asset,
        reference_assets: list[Asset],
        reference_weights: dict[UUID, float],
        threshold: float,
    ) -> float:
        """Sector / asset-class gap score.

        Implements DATA-MODEL.md §4.9 Signal 3:
            A_R = {a | Σ_{r ∈ R, class(r)=a} w_r ≥ θ}

            GapScore(c) = 1    if class(c) ∉ A_R
                        = 0.5  if class(c) ∈ A_R  but sector(c) ∉ sectors(R)
                        = 0    otherwise

        GICS sector is Asset.sector (None for non-equity assets).
        Non-equity candidates cannot trigger the 0.5 branch.
        """
        class_weights: dict[str, float] = {}
        for asset in reference_assets:
            key = asset.asset_class.value
            class_weights[key] = (
                class_weights.get(key, 0.0)
                + reference_weights.get(asset.asset_id, 0.0)
            )

        represented_classes = {cls for cls, w in class_weights.items() if w >= threshold}
        if candidate.asset_class.value not in represented_classes:
            return 1.0

        represented_sectors = {
            asset.sector for asset in reference_assets if asset.sector is not None
        }
        if candidate.sector is not None and candidate.sector not in represented_sectors:
            return 0.5

        return 0.0

    def _calc_hhi_reduction(
        self,
        candidate_idx: int,
        reference_weights: np.ndarray,
        delta: float,
    ) -> float:
        """HHI concentration reduction from adding the candidate at weight δ.

        Implements DATA-MODEL.md §4.9 Signal 4:
            HHI_pro(c) = Σ_i w_pro_i²
            HHIRed(c)  = HHI_R − HHI_pro(c)

        Positive → candidate lowers concentration.
        """
        hhi_R = float(np.sum(reference_weights**2))

        pro_weights = reference_weights * (1.0 - delta)
        pro_weights[candidate_idx] += delta

        hhi_pro = float(np.sum(pro_weights**2))
        return hhi_R - hhi_pro

    # ------------------------------------------------------------------ #
    # Normalisation                                                        #
    # ------------------------------------------------------------------ #

    def _normalize_scores(
        self,
        raw_scores: list[float],
        invert: bool = False,
    ) -> list[float]:
        """Min-max normalize a list of raw signal values to [0, 1].

        Degenerate case (max == min): returns 0.0 for every candidate.
        The signal is uninformative and must not influence the composite.
        """
        if not raw_scores:
            return []
        min_val, max_val = min(raw_scores), max(raw_scores)
        if abs(max_val - min_val) < 1e-10:
            return [0.0] * len(raw_scores)
        return self._scale(raw_scores, min_val, max_val, invert)

    def _scale(
        self,
        scores: list[float],
        min_val: float,
        max_val: float,
        invert: bool,
    ) -> list[float]:
        """Pure min-max arithmetic — called only after edge-case guards pass."""
        span = max_val - min_val
        if invert:
            return [(max_val - v) / span for v in scores]
        return [(v - min_val) / span for v in scores]

    # ------------------------------------------------------------------ #
    # Explanation generation                                               #
    # ------------------------------------------------------------------ #

    def _generate_explanation(
        self,
        score: ScreeningScore,
        reference_stats: dict,
    ) -> str:
        """Assemble a plain-language explanation with concrete numbers.

        Implements FR6 / FR14: explanations use concrete numbers,
        not directional language alone.
        """
        sigma_R: float = reference_stats["sigma_R"]
        hhi_R: float = reference_stats["hhi_R"]
        n_eff_R: float = reference_stats["n_eff_R"]
        delta: float = reference_stats["delta"]

        sigma_pro = sigma_R - score.marginal_vol_reduction
        hhi_pro = hhi_R - score.hhi_reduction
        n_eff_pro = 1.0 / hhi_pro if hhi_pro > 0.0 else float("inf")
        vol_direction = "reduce" if score.marginal_vol_reduction >= 0.0 else "increase"

        parts = [
            f"Rank {score.rank}, composite score {score.composite_score:.3f}.",
            (
                f"Average pairwise correlation with reference portfolio: "
                f"{score.avg_pairwise_corr:.3f}."
            ),
            (
                f"Adding at a {delta * 100:.1f}% nominal weight would {vol_direction} "
                f"portfolio volatility from {sigma_R * 100:.2f}% to "
                f"{sigma_pro * 100:.2f}% annualised."
            ),
            self._sector_gap_clause(score.sector_gap_score),
            (
                f"HHI changes from {hhi_R:.4f} to {hhi_pro:.4f} "
                f"(effective N: {n_eff_R:.1f} \u2192 {n_eff_pro:.1f})."
            ),
        ]
        return " ".join(parts)

    def _sector_gap_clause(self, gap_score: float) -> str:
        """Return the sector-gap sentence for the given gap score value."""
        if gap_score == 1.0:
            return (
                "Asset class is not currently represented in the reference portfolio "
                "(gap score: 1.00)."
            )
        if gap_score == 0.5:
            return (
                "Asset class is represented but this GICS sector is absent from "
                "the reference portfolio (gap score: 0.50)."
            )
        return (
            "Asset class and GICS sector are already represented in the reference "
            "portfolio (gap score: 0.00)."
        )

    # ------------------------------------------------------------------ #
    # Internal helper                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_weight_vector(
        weights: dict[UUID, float],
        asset_index: dict[UUID, int],
        n: int,
    ) -> np.ndarray:
        """Convert a UUID-keyed weight dict to a dense array of length n."""
        arr = np.zeros(n)
        for asset_id, w in weights.items():
            if asset_id in asset_index:
                arr[asset_index[asset_id]] = w
        return arr
