"""Shared covariance matrix utilities used by screening and optimization commands."""

from __future__ import annotations

from uuid import UUID

import numpy as np

from src.domain.models.assumptions import CovarianceMatrix


def extract_cov_asset_ids(covariance: CovarianceMatrix) -> list[UUID]:
    """Return a deduplicated, insertion-ordered list of asset IDs from covariance entries."""
    seen: dict[UUID, int] = {}
    for entry in covariance.entries:
        if entry.asset_id_i not in seen:
            seen[entry.asset_id_i] = len(seen)
        if entry.asset_id_j not in seen:
            seen[entry.asset_id_j] = len(seen)
    return sorted(seen, key=lambda k: seen[k])


def build_cov_array(
    covariance: CovarianceMatrix,
    asset_index: dict[UUID, int],
) -> np.ndarray:
    """Convert CovarianceMatrix upper-triangle entries to a full symmetric numpy array."""
    n = len(asset_index)
    arr = np.zeros((n, n))
    for entry in covariance.entries:
        i = asset_index.get(entry.asset_id_i)
        j = asset_index.get(entry.asset_id_j)
        if i is not None and j is not None:
            arr[i, j] = entry.cov_annual
            arr[j, i] = entry.cov_annual  # enforce symmetry
    return arr
