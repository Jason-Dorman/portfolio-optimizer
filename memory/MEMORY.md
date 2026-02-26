# Portfolio Optimizer — Session Memory

## Project Structure
- Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL
- CQRS pattern: `src/commands/`, `src/queries/`
- Domain: `src/domain/models/`, `src/domain/services/`, `src/domain/repositories/`
- Frontend: Streamlit + Plotly, dark theme only
- Tests: `.venv/bin/python -m pytest` (NOT bare `python -m pytest`)

## Completed Services
- `src/domain/services/screening.py` — ScreeningService (4 signals, composite score)
- `src/domain/services/optimization.py` — OptimizationService (MVP, frontier, tangency, risk decomp)

## Optimization Service Design Decisions (approved by PO)
- **Return type**: `SolverResult` dataclass (no UUIDs). Command handlers wrap into `OptimizationRun`.
- **Risk decomp return**: `RiskDecompositionResult` dataclass with positional arrays (mcr, crc, prc). No UUIDs.
- **Prev weights**: `prev_weights: np.ndarray | None = None` on each optimize method. Turnover constraint ignored (with warning) when None.
- **Explanation**: `_generate_explanation(result, weights, assets, constraints)` — weights param added.
- **Per-asset bounds**: Require `asset_ids: list[UUID] | None = None` to resolve UUID → column. Silently ignored with warning when None.
- **Solver**: `scipy.optimize.minimize` (SLSQP). Handles both convex (variance) and non-convex (Sharpe) objectives.

## Key Patterns
- Services are stateless pure-computation classes (no DB, no UUIDs at service layer)
- `asset_ids` param resolves UUID→numpy-column mapping (same pattern as screening's `asset_index`)
- `_clean_weights()` zeros sub-tolerance artefacts + renormalises after solving
- Module-level helper functions (no `self`) for objectives, infeasible results, etc.

## Test Conventions
- Run: `.venv/bin/python -m pytest tests/unit/test_optimization.py -v`
- Numeric assertions use closed-form solutions from DATA-MODEL.md as ground truth
- Grouped into classes by method; edge cases in separate `TestEdgeCases` class
- `atol=1e-4` for solver output, `atol=1e-8` for derived identities (CRC sum, PRC sum)

## Docs Location
All specs: `docs/` — REQUIREMENTS.md, DATA-MODEL.md, SYSTEM-SPEC.md, DB-SCHEMA.md,
API-CONTRACT.md, WORKFLOW-DIAGRAMS.md, UI-SPEC.md, ENGINEERING-PRINCIPLES.md
