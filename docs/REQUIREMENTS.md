# Requirements v1

## 2.1 Functional Requirements (FR)

### FR1 — Universe Management
- Create named universes of assets (tickers, asset class tags, benchmark flag)
- Distinguish between **active universes** (used in optimization) and **candidate pools** (used in screening)
- Support promoting assets from a candidate pool into an active universe

### FR2 — Current Holdings
- User can define a **current holdings** record: a set of (ticker, weight) or (ticker, market value) pairs representing their real portfolio today
- **Normalization:** If market values are provided, the system normalizes to weights at ingest time. Weights must sum to 1.0; this invariant is enforced at the application layer before database insert.
- Current holdings are versioned with a timestamp
- Used as: reference point for screening, basis for turnover constraint in optimization, and baseline for drift detection
- If no current holdings exist, screening requires a user-specified seed universe (no automatic fallback)

### FR3 — Market Data Ingest (APIs)
- Pull adjusted close prices (and corporate action metadata if available)
- Store raw bars with vendor provenance (source, pull timestamp)
- Support incremental updates: only fetch missing dates
- Handle rate limiting, retries, and vendor outage fallback gracefully
- Ingest risk-free rate series from FRED (e.g., 3-month T-bill)
- Ingest benchmark price series (e.g., SPY, AGG) as regular assets

### FR4 — Return Series Generation
- Compute simple or log returns at user-selected frequency (daily / weekly / monthly)
- Missing data handling: use common date overlap by default; document forward-fill behavior explicitly when used
- Store computed returns in DB tied to asset + frequency + return type

### FR5 — Assumption Set Generation
- Produce μ (annualized expected returns), σ (annualized volatility), correlation matrix, covariance matrix
- **Estimator independence:** Expected return estimation (`estimator`) and covariance estimation (`cov_method`) are configured independently. See SYSTEM-SPEC Section 1.3C for valid combinations.
- Validation checks: correlation values in [−1, 1], symmetry, diagonal = 1, covariance PSD
- Optional repairs: nearest-PSD adjustment; log warnings with reason when repair is applied
- Shrinkage (Ledoit-Wolf) available as optional covariance method

### FR6 — Asset Screening
- Accept a **reference point**: current holdings snapshot ID (preferred) or seed universe ID (fallback)
- **Explicit selection required:** User must provide one reference; there is no automatic fallback. API returns error if neither is specified.
- Accept a **candidate pool** to score against
- Score each candidate on four signals:
  1. Average pairwise correlation to reference holdings (lower = better)
  2. Marginal portfolio volatility reduction if added at a nominal weight (default 5%)
  3. Asset class / sector gap: whether the candidate fills an underrepresented class
  4. HHI reduction / effective-N improvement
- Compute a **composite score** as a weighted combination of normalized signals
- **Default signal weights:** λ₁ = 0.40 (correlation), λ₂ = 0.30 (marginal vol), λ₃ = 0.15 (sector gap), λ₄ = 0.15 (HHI). See DATA-MODEL Section 4.9 for formula.
- Return a ranked list with per-signal scores and a plain-language explanation for each top candidate
- Persist screening run inputs, scores, and explanations for reproducibility

### FR7 — Optimization: MVP
- Compute weights minimizing portfolio variance subject to constraints

### FR8 — Optimization: Efficient Frontier
- For a grid of target returns, solve min-variance at each point
- Mark points infeasible (especially long-only beyond max achievable return)
- Store full frontier series as a linked set of optimization runs

### FR9 — Optimization: Tangency Portfolio
- Maximize Sharpe ratio (μp − rf) / σp subject to constraints
- Handle edge case: if max(μᵢ) ≤ rf, return INFEASIBLE with explanation (see FR11)

### FR10 — Constraints
Must support all of the following:
- Sum of weights = 1
- Long-only (wᵢ ≥ 0)
- Shorting allowed (wᵢ can be negative)
- Per-asset bounds (wmin, wmax)
- Leverage cap: Σ|wᵢ| ≤ L
- Concentration cap: max(|wᵢ|) ≤ c
- Turnover cap vs. reference: Σ|wᵢ − wᵢ_prev| ≤ T

**Turnover constraint reference resolution:**
1. If `reference_snapshot_id` is provided, use that current holdings snapshot
2. Else if a previous optimization run exists for the same universe, use those weights
3. Else the turnover constraint is inapplicable; ignore it and log a warning

### FR11 — Infeasibility Explanation
- When an optimization returns INFEASIBLE or ERROR, the system must produce a plain-language reason
- Examples:
  - "Target return of 11% exceeds maximum achievable return of 8.4% under long-only constraints"
  - "No solution satisfies both the turnover cap and the target return"
  - "No asset has expected return exceeding the risk-free rate; tangency portfolio undefined"
- Reason stored in DB alongside solver status
- **Cross-reference:** This is a specific case of the broader explainability requirement (FR14)

### FR12 — Risk Analytics
Compute and store:
- Portfolio μp, σp
- MCR / CRC / PRC (marginal, component, percent risk contributions)
- HHI + effective N
- Max drawdown + drawdown time series
- Historical VaR and CVaR (95% and 99%)
- Scenario stress results (equity shock, rate shock, inflation spike)

### FR13 — Drift Detection
- After a portfolio is optimized, the system can accept updated price data and recompute current implied weights
- **Trigger:** Drift checks are on-demand in v1. User explicitly requests a drift check for a given optimization run. Scheduled/automatic drift monitoring is out of scope for v1.
- Flag when any asset's weight has drifted beyond a user-defined threshold (default: ±5% absolute) from target
- Generate a plain-language drift alert: "SPY has grown from 40% to 51% due to price appreciation since last rebalance"
- **Return type:** Drift detection always uses simple returns for wealth compounding, regardless of the return type used in estimation (see DATA-MODEL Section 4.11)

### FR14 — Explainability
- Every optimization run must generate a plain-language summary explaining:
  - Which assets dominate and why (variance, correlation, return contribution)
  - What the binding constraints were
  - How the result compares to equal-weight as a reference
- Every screening run must generate a plain-language explanation for top-ranked candidates
- Infeasibility explanations (FR11) are a subset of this requirement
- Explainability output stored in DB alongside its parent run

### FR15 — Backtesting & Rebalancing
- Rolling window estimation + rebalancing schedule (monthly / quarterly / threshold-based)
- Output: performance time series, realized vol, Sharpe, max drawdown, VaR, turnover per period
- Benchmark comparison: active return, tracking error, information ratio vs. selected benchmark
- Optional transaction cost model

### FR16 — Persistence & Audit
Every run (screening, optimization, backtest) stores:
- All inputs: assumption set ID, objective, constraints, reference portfolio
- Solver status and infeasibility reason if applicable
- Outputs: weights, scores, metrics, explanations
- Ability to exactly reproduce any past run

### FR17 — Export / Report
- Export: weights, key risk metrics, assumption set, screening rationale, benchmark comparison, plots
- Formats: CSV (weights + metrics), PDF or HTML report (full summary), Excel (optional)

---

## 2.2 Non-Functional Requirements (NFR)

**Correctness**
- Numerical stability enforced; tests for identities (w'Σw ≥ 0, weights sum to 1)
- Screening scores must be deterministic given the same inputs and assumption set

**Performance**
- Efficient frontier for up to ~50 assets within seconds to minutes depending on grid size
- Screening across a candidate pool of 500 assets within seconds

**Reliability**
- Data ingest resilient to API rate limits with exponential backoff and logging

**Security**
- API keys stored in environment variables or secrets manager; never in code or DB
- DB credentials least-privilege

**Explainability**
- Every optimization and screening run produces a user-readable summary
- Summaries use concrete numbers, not just directional language

**Transparency of Limitations**
- UI and reports must clearly state that screening scores reflect portfolio construction quality only — not return forecasts
- Survivorship bias caveat displayed on all backtest outputs