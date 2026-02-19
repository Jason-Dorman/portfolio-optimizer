# System Spec v1 — Portfolio Builder & Risk Analyzer

## 1.1 Purpose

A personal-use application that:

- Pulls market data from APIs and maintains a clean, auditable price history
- Estimates risk/return inputs robustly using selectable methods
- Screens candidate assets for diversification value against a reference portfolio or seed universe
- Optimizes portfolios under realistic constraints
- Explains diversification, risk drivers, and portfolio construction decisions in plain language
- Supports backtesting and rebalancing simulation
- Persists everything in Postgres for auditability and reproducibility

---

## 1.2 Core Concepts

**Assumption Set** — A versioned snapshot of: universe + lookback window + estimator choices + risk-free rate + frequency. Every optimization is tied to one.

**Current Holdings** — An optional real-world portfolio the user holds today, expressed as (ticker, weight or market value). Used as the reference point for rebalancing, turnover constraints, and screening.

**Candidate Pool** — A curated list of assets (e.g., a broad ETF universe) eligible for screening. Separate from any active universe being optimized.

**Screening Run** — A scored ranking of candidate assets evaluated against a reference point (current holdings if provided, otherwise a seed universe). Scores reflect diversification value, not return prediction.

**Optimization Run** — A single solve (MVP, frontier point, or tangency) tied to an assumption set, with constraints and full outputs persisted.

**Backtest Run** — A rolling walk-forward simulation using a strategy (e.g., monthly tangency rebalance) over a historical period.

---

## 1.3 High-Level Architecture (Modular Monolith)

### A) UI / API Layer
- **Frontend:** Streamlit (v1); React optional later
- **Backend:** FastAPI
- **Endpoints cover:** universes, current holdings, candidate pools, ingest, estimate, screen, optimize, analyze, backtest, export
- All endpoints return structured JSON; frontend renders results and explanations

### B) Data Ingestion Module
- Provider adapters: Polygon / Tiingo / AlphaVantage + FRED (risk-free rates)
- Pulls adjusted close prices; records dividend/split metadata where available
- Writes price bars to Postgres with vendor provenance
- Incremental updates: only fetches missing dates
- Handles rate limiting, retries, and vendor outage fallback
- Survivorship bias note: universe reflects assets as currently defined; historical gaps are flagged but not auto-corrected in v1

### C) Estimation Module
- Computes simple or log returns from prices at selected frequency
- Produces μ (expected return vector) and Σ (covariance matrix) using **independently selectable** estimators:
  
  **Expected return (μ) estimators** (controlled by `estimator` field):
  - Historical mean (default)
  - EWMA (exponentially weighted)
  - Shrinkage toward grand mean (optional, v1.1)
  
  **Covariance (Σ) estimators** (controlled by `cov_method` field):
  - Sample covariance (default)
  - Ledoit-Wolf shrinkage
  - Nearest-PSD (repair method, applied automatically if matrix fails PSD check)

- These choices are independent: e.g., historical mean returns with Ledoit-Wolf covariance is a valid combination
- Validates matrix properties: symmetry, diagonal = 1 for correlation, positive semi-definite
- Repairs if needed (nearest-PSD) and logs warnings with reason

### D) Asset Screening Module
- Accepts a reference point: current holdings (if provided) or seed universe (explicit fallback)
- **Reference selection behavior:**
  - If user provides a current holdings snapshot ID, that snapshot is used
  - If user provides a seed universe ID instead, that universe (with equal weights) is used
  - If neither is provided, the API returns an error requiring one to be specified
  - There is no automatic fallback; the user must explicitly choose
- Scores each asset in a candidate pool on:
  - Average pairwise correlation to reference holdings
  - Marginal volatility reduction if added at a nominal weight
  - Asset class / sector gap contribution
  - HHI reduction / effective-N improvement
- Produces a composite score and ranked list with per-signal breakdown
- Stores screening runs for reproducibility
- Returns plain-language explanation for top-ranked candidates

### E) Optimization Module
- Solves MVP, efficient frontier, and tangency portfolio
- Constraint engine: long-only, per-asset bounds, leverage cap, concentration cap, turnover cap vs. current holdings
- Returns infeasibility reason in plain language when no solution exists
- Handles edge cases:
  - Tangency undefined when all μᵢ ≤ rf (returns INFEASIBLE with explanation)
  - Frontier point beyond achievable range (returns INFEASIBLE with explanation)

### F) Risk Analytics Module
- Risk decomposition: MCR / CRC / PRC
- Concentration: HHI, effective N
- Tail risk: historical VaR / CVaR (95%, 99%)
- Drawdowns: max drawdown, drawdown time series
- Scenario shocks: equity −X%, rates +Y bps, inflation spike (simple factor shocks)
- Drift detection: flags when current holdings have drifted beyond threshold from target weights

### G) Explainability Module
- Generates plain-language summaries for:
  - Why the optimizer chose these weights ("Asset X dominates because it has the lowest variance and near-zero correlation to Asset Y")
  - Why a candidate asset scored highly in screening ("Adding QQQ would reduce average pairwise correlation from 0.72 to 0.61 and increase effective N from 3.2 to 4.1")
  - Why an optimization was infeasible ("Your target return of 11% exceeds the maximum achievable return of 8.4% under long-only constraints")
  - Portfolio drift alerts ("Your SPY position has grown from 40% to 51% target weight due to price appreciation")
- Summaries are stored alongside their parent run for auditability

### H) Backtest & Rebalancing Module
- Rolling estimation window with fixed rebalancing schedule (monthly / quarterly) or threshold drift bands
- Tracks: portfolio value, period returns, turnover, realized vol, drawdown, VaR, Sharpe
- Benchmark comparison: benchmark returns ingested and stored as a regular asset; active return, tracking error, and information ratio computed
- Optional simple transaction cost model (cost = c × turnover)

---

## 1.4 Key Workflows

### Build Assumptions
Universe → pick window / frequency / estimators / rf → generate μ, Σ

### Screen Candidates
Define candidate pool → provide current holdings snapshot ID **or** seed universe ID (one required) → run scoring → review ranked list with explanations → promote selected assets to active universe

### Optimize
Choose objective (MVP / frontier / tangency) + constraints → produce weights → read plain-language explanation

### Analyze
Risk drivers + tail risk + scenario stats + concentration + drift detection

### Validate
Backtest vs. benchmarks (SPY, 60/40, equal-weight); review turnover and net-of-cost performance

### Export
PDF / CSV / Excel report with assumptions, weights, screening rationale, and risk summary

---

## 1.5 Known Limitations (v1)

- **Survivorship bias:** Universe is defined by the user; no automatic delisting adjustment
- **Return prediction:** Screening scores are purely construction-quality metrics, not return forecasts
- **Transaction costs:** Simple proportional model only; no bid-ask spread or market impact
- **Single-period framework:** Mean-variance optimization is single-period; no multi-period optimization, liability matching, or dynamic rebalancing optimization
- **Single-user:** No authentication or multi-tenancy in v1