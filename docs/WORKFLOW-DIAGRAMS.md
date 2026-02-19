# Workflow Sequence Diagrams

## Overview

This document provides sequence diagrams for the three core workflows in the Portfolio Builder system. These diagrams show:

1. Which components interact
2. The order of operations
3. Data flow between layers
4. Error handling paths

The diagrams follow CQRS patterns where commands mutate state and queries read state.

---

## Architecture Layers

Before diving into workflows, here's the layer structure:

```mermaid
flowchart TB
    subgraph Presentation["Presentation Layer"]
        UI[Streamlit UI]
        API[FastAPI Endpoints]
    end
    
    subgraph Application["Application Layer (CQRS)"]
        CMD[Command Handlers]
        QRY[Query Handlers]
    end
    
    subgraph Domain["Domain Layer"]
        SVC[Domain Services]
        ENT[Entities / Value Objects]
    end
    
    subgraph Infrastructure["Infrastructure Layer"]
        REPO[Repositories]
        VENDOR[Vendor Adapters]
        DB[(PostgreSQL)]
        EXT[External APIs]
    end
    
    UI --> API
    API --> CMD
    API --> QRY
    CMD --> SVC
    QRY --> REPO
    SVC --> ENT
    SVC --> REPO
    REPO --> DB
    VENDOR --> EXT
    SVC --> VENDOR
```

**SOLID Alignment:**
- **Single Responsibility:** Each layer has one reason to change
- **Dependency Inversion:** Upper layers depend on abstractions defined in Domain
- **Open/Closed:** New workflows extend existing handlers without modifying them

---

## Workflow 1: Screening → Promote → Optimize

This is the primary portfolio construction workflow. A user screens candidates, selects assets to add, then optimizes.

### High-Level Flow

```mermaid
flowchart LR
    A[Define Candidate Pool] --> B[Build Assumption Set]
    B --> C[Run Screening]
    C --> D[Review Scores]
    D --> E[Promote to Universe]
    E --> F[Run Optimization]
    F --> G[Review Weights]
```

### Detailed Sequence

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant API as FastAPI
    participant CmdH as Command Handler
    participant QryH as Query Handler
    participant ScreenSvc as ScreeningService
    participant OptSvc as OptimizationService
    participant Repo as Repositories
    participant DB as PostgreSQL

    Note over User,DB: Phase 1: Setup Candidate Pool & Assumption Set
    
    User->>API: POST /commands/universes<br/>{name, type: candidate_pool, asset_ids}
    API->>CmdH: CreateUniverseHandler
    CmdH->>Repo: universe_repo.create()
    Repo->>DB: INSERT universes, universe_assets
    DB-->>Repo: universe_id
    Repo-->>CmdH: Universe
    CmdH-->>API: 201 Created
    API-->>User: Universe response

    User->>API: POST /commands/assumptions<br/>{universe_id, lookback, estimator, cov_method}
    API->>CmdH: CreateAssumptionSetHandler
    CmdH->>Repo: return_repo.get_returns(universe_id, window)
    Repo->>DB: SELECT from return_series
    DB-->>Repo: returns[]
    CmdH->>CmdH: Compute μ, Σ
    CmdH->>CmdH: Validate PSD, repair if needed
    CmdH->>Repo: assumption_repo.save(μ, Σ)
    Repo->>DB: INSERT assumption_sets, assumption_asset_stats, assumption_cov
    DB-->>Repo: assumption_id
    Repo-->>CmdH: AssumptionSet
    CmdH-->>API: 201 Created
    API-->>User: AssumptionSet response

    Note over User,DB: Phase 2: Run Screening

    User->>API: POST /commands/screening<br/>{assumption_id, candidate_pool_id, reference_snapshot_id}
    API->>CmdH: RunScreeningHandler
    CmdH->>Repo: holdings_repo.get_snapshot(reference_snapshot_id)
    Repo->>DB: SELECT from current_holdings_positions
    DB-->>Repo: positions[]
    CmdH->>Repo: assumption_repo.get_covariance(assumption_id)
    Repo->>DB: SELECT from assumption_cov
    DB-->>Repo: Σ matrix
    
    CmdH->>ScreenSvc: score_candidates(reference, candidates, Σ)
    
    loop For each candidate
        ScreenSvc->>ScreenSvc: calc_avg_correlation()
        ScreenSvc->>ScreenSvc: calc_marginal_vol_reduction()
        ScreenSvc->>ScreenSvc: calc_sector_gap_score()
        ScreenSvc->>ScreenSvc: calc_hhi_reduction()
        ScreenSvc->>ScreenSvc: compute_composite_score()
        ScreenSvc->>ScreenSvc: generate_explanation()
    end
    
    ScreenSvc->>ScreenSvc: normalize_scores()
    ScreenSvc->>ScreenSvc: rank_candidates()
    ScreenSvc-->>CmdH: ScreeningScores[]
    
    CmdH->>Repo: screening_repo.save(run, scores)
    Repo->>DB: INSERT screening_runs, screening_scores
    DB-->>Repo: screening_id
    Repo-->>CmdH: ScreeningRun
    CmdH-->>API: 201 Created
    API-->>User: ScreeningRun with top candidates

    Note over User,DB: Phase 3: Review & Promote

    User->>API: GET /queries/screening/{id}/scores
    API->>QryH: GetScreeningScoresQuery
    QryH->>Repo: screening_repo.get_scores(id)
    Repo->>DB: SELECT from screening_scores ORDER BY rank
    DB-->>Repo: scores[]
    Repo-->>QryH: ScreeningScore[]
    QryH-->>API: 200 OK
    API-->>User: All candidate scores

    User->>User: Select top candidates to promote

    User->>API: POST /commands/universes/{active_id}/assets<br/>{asset_ids: [selected]}
    API->>CmdH: AddUniverseAssetsHandler
    CmdH->>Repo: universe_repo.add_assets()
    Repo->>DB: INSERT universe_assets
    DB-->>Repo: ok
    Repo-->>CmdH: Universe
    CmdH-->>API: 200 OK
    API-->>User: Updated universe

    Note over User,DB: Phase 4: Optimize

    User->>API: POST /commands/assumptions<br/>{universe_id: active_id, ...}
    API->>CmdH: CreateAssumptionSetHandler
    Note right of CmdH: (Same flow as Phase 1)
    CmdH-->>API: 201 Created
    API-->>User: New AssumptionSet for active universe

    User->>API: POST /commands/optimize<br/>{assumption_id, run_type: TANGENCY, constraints}
    API->>CmdH: RunOptimizationHandler
    CmdH->>Repo: assumption_repo.get_full(assumption_id)
    Repo->>DB: SELECT μ, Σ
    DB-->>Repo: assumption data
    
    CmdH->>OptSvc: optimize(μ, Σ, objective, constraints)
    
    alt Feasible
        OptSvc->>OptSvc: solve_qp()
        OptSvc->>OptSvc: compute_risk_decomposition()
        OptSvc->>OptSvc: generate_explanation()
        OptSvc-->>CmdH: OptimizationResult{weights, mcr, crc, prc}
        CmdH->>Repo: optimization_repo.save(run, result, weights)
        Repo->>DB: INSERT optimization_runs, optimization_results, optimization_weights
        DB-->>Repo: run_id
        Repo-->>CmdH: OptimizationRun
        CmdH-->>API: 201 Created {status: SUCCESS}
    else Infeasible
        OptSvc->>OptSvc: diagnose_infeasibility()
        OptSvc-->>CmdH: InfeasibilityReason
        CmdH->>Repo: optimization_repo.save_infeasible(run, reason)
        Repo->>DB: INSERT optimization_runs {status: INFEASIBLE}
        DB-->>Repo: run_id
        Repo-->>CmdH: OptimizationRun
        CmdH-->>API: 201 Created {status: INFEASIBLE}
    end
    
    API-->>User: OptimizationRun response
```

### Key Decision Points

| Step | Decision | Outcome |
|------|----------|---------|
| Screening reference | Snapshot ID or Universe ID? | Exactly one must be provided |
| PSD validation | Matrix positive semi-definite? | Repair with nearest-PSD if not |
| Optimization feasibility | Solution exists? | Return weights OR infeasibility reason |
| Tangency check | max(μᵢ) > rf? | If not, return INFEASIBLE |

---

## Workflow 2: Optimize → Drift Check → Rebalance Decision

After optimization, users periodically check if their portfolio has drifted from target weights.

### High-Level Flow

```mermaid
flowchart LR
    A[Optimization Run] --> B[Time Passes]
    B --> C[Prices Change]
    C --> D[Request Drift Check]
    D --> E{Any Breach?}
    E -->|Yes| F[Review Drifted Positions]
    E -->|No| G[No Action Needed]
    F --> H[Decide: Rebalance?]
    H -->|Yes| I[Re-optimize with Turnover Constraint]
    H -->|No| J[Accept Drift]
```

### Detailed Sequence

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant API as FastAPI
    participant CmdH as Command Handler
    participant QryH as Query Handler
    participant DriftSvc as DriftService
    participant OptSvc as OptimizationService
    participant Repo as Repositories
    participant DB as PostgreSQL

    Note over User,DB: Phase 1: Initial Optimization (already complete)
    
    User->>API: GET /queries/optimization/{run_id}
    API->>QryH: GetOptimizationRunQuery
    QryH->>Repo: optimization_repo.get(run_id)
    Repo->>DB: SELECT from optimization_runs, optimization_weights
    DB-->>Repo: run + weights
    Repo-->>QryH: OptimizationRunDetail
    QryH-->>API: 200 OK
    API-->>User: Target weights from original optimization

    Note over User,DB: Phase 2: Time Passes, User Requests Drift Check

    User->>API: POST /commands/drift-check<br/>{run_id, check_date, threshold_pct: 0.05}
    API->>CmdH: RunDriftCheckHandler
    
    CmdH->>Repo: optimization_repo.get_weights(run_id)
    Repo->>DB: SELECT from optimization_weights
    DB-->>Repo: target_weights[]
    
    CmdH->>Repo: optimization_repo.get_run(run_id)
    Repo->>DB: SELECT created_at from optimization_runs
    DB-->>Repo: optimization_date
    
    CmdH->>Repo: price_repo.get_prices(asset_ids, optimization_date, check_date)
    Repo->>DB: SELECT from price_bars WHERE bar_date BETWEEN ...
    DB-->>Repo: price_series[]
    
    CmdH->>DriftSvc: compute_drift(target_weights, prices, threshold)
    
    DriftSvc->>DriftSvc: compute_simple_returns(prices)
    Note right of DriftSvc: Always simple returns<br/>for wealth compounding
    
    loop For each asset
        DriftSvc->>DriftSvc: compound_growth = Π(1 + rᵢ)
    end
    
    DriftSvc->>DriftSvc: normalize_current_weights()
    
    loop For each asset
        DriftSvc->>DriftSvc: drift_abs = |current - target|
        DriftSvc->>DriftSvc: breached = drift_abs > threshold
        alt breached
            DriftSvc->>DriftSvc: generate_explanation()
        end
    end
    
    DriftSvc->>DriftSvc: any_breach = any(breached)
    DriftSvc-->>CmdH: DriftCheckResult
    
    CmdH->>Repo: drift_repo.save(check, positions)
    Repo->>DB: INSERT drift_checks, drift_check_positions
    DB-->>Repo: drift_id
    Repo-->>CmdH: DriftCheck
    CmdH-->>API: 201 Created
    API-->>User: DriftCheck with breach flags

    Note over User,DB: Phase 3: Review Drift Details

    User->>API: GET /queries/drift/{drift_id}
    API->>QryH: GetDriftCheckQuery
    QryH->>Repo: drift_repo.get(drift_id)
    Repo->>DB: SELECT from drift_checks, drift_check_positions
    DB-->>Repo: check + positions
    Repo-->>QryH: DriftCheckDetail
    QryH-->>API: 200 OK
    API-->>User: All positions with drift amounts and explanations

    Note over User,DB: Phase 4: Rebalance Decision

    alt User decides to rebalance
        User->>API: POST /commands/holdings/snapshots<br/>{positions: current_implied_weights}
        API->>CmdH: CreateHoldingsSnapshotHandler
        CmdH->>Repo: holdings_repo.create()
        Repo->>DB: INSERT current_holdings_snapshots, positions
        DB-->>Repo: snapshot_id
        Repo-->>CmdH: HoldingsSnapshot
        CmdH-->>API: 201 Created
        API-->>User: New snapshot representing current state

        User->>API: POST /commands/optimize<br/>{assumption_id, run_type: TANGENCY,<br/>reference_snapshot_id: new_snapshot,<br/>constraints: {turnover_cap: 0.20}}
        API->>CmdH: RunOptimizationHandler
        
        CmdH->>Repo: holdings_repo.get_snapshot(reference_snapshot_id)
        Repo->>DB: SELECT current weights
        DB-->>Repo: w_prev[]
        
        CmdH->>OptSvc: optimize(μ, Σ, constraints, w_prev)
        Note right of OptSvc: Turnover constraint:<br/>Σ|wᵢ - wᵢ_prev| ≤ 0.20
        
        OptSvc->>OptSvc: solve_qp_with_turnover()
        OptSvc->>OptSvc: compute_actual_turnover()
        OptSvc-->>CmdH: OptimizationResult
        
        CmdH->>Repo: optimization_repo.save()
        Repo->>DB: INSERT optimization_runs, results, weights
        DB-->>Repo: run_id
        Repo-->>CmdH: OptimizationRun
        CmdH-->>API: 201 Created
        API-->>User: New target weights with controlled turnover
        
    else User accepts drift
        User->>User: No action taken
        Note right of User: Portfolio remains at<br/>current drifted weights
    end
```

### Drift Detection Logic

```mermaid
flowchart TD
    A[Get Target Weights from Optimization] --> B[Get Price History Since Optimization]
    B --> C[Compute Simple Returns per Asset]
    C --> D[Compound Returns: growth_i = Π(1 + r_i,t)]
    D --> E[Compute Current Implied Weights]
    E --> F[current_i = target_i × growth_i / Σ(target_j × growth_j)]
    F --> G[Compute Drift: |current_i - target_i|]
    G --> H{drift_i > threshold?}
    H -->|Yes| I[Mark Breached + Generate Explanation]
    H -->|No| J[Mark Not Breached]
    I --> K[Aggregate: any_breach = any(breached)]
    J --> K
```

---

## Workflow 3: Backtest Run Lifecycle

Backtesting simulates a strategy over historical data with periodic rebalancing.

### High-Level Flow

```mermaid
flowchart LR
    A[Define Strategy] --> B[Set Parameters]
    B --> C[Run Backtest]
    C --> D[Rolling Window Loop]
    D --> E[Compute Metrics]
    E --> F[Store Results]
    F --> G[Review Performance]
```

### Detailed Sequence

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant API as FastAPI
    participant CmdH as Command Handler
    participant QryH as Query Handler
    participant BacktestSvc as BacktestService
    participant EstSvc as EstimationService
    participant OptSvc as OptimizationService
    participant Repo as Repositories
    participant DB as PostgreSQL

    Note over User,DB: Phase 1: Configure and Launch Backtest

    User->>API: POST /commands/backtest<br/>{universe_id, strategy: TANGENCY_REBAL,<br/>rebal_freq: monthly, window_length: 252,<br/>start_date, end_date, transaction_cost_bps: 10}
    API->>CmdH: RunBacktestHandler
    
    CmdH->>Repo: universe_repo.get(universe_id)
    Repo->>DB: SELECT assets
    DB-->>Repo: asset_ids[]
    
    CmdH->>Repo: price_repo.get_prices(asset_ids, start - window, end)
    Repo->>DB: SELECT from price_bars
    DB-->>Repo: all_prices[]
    
    CmdH->>Repo: benchmark_repo.get_prices(benchmark_id, start, end)
    Repo->>DB: SELECT from price_bars
    DB-->>Repo: benchmark_prices[]
    
    CmdH->>BacktestSvc: run_backtest(config, prices, benchmark)

    Note over User,DB: Phase 2: Rolling Window Simulation

    BacktestSvc->>BacktestSvc: initialize(portfolio_value: 1.0)
    BacktestSvc->>BacktestSvc: generate_rebalance_dates(start, end, monthly)
    
    loop For each period t from start to end
        BacktestSvc->>BacktestSvc: get_lookback_window(t - window_length, t)
        
        alt Is rebalance date
            BacktestSvc->>EstSvc: estimate(returns_window)
            EstSvc->>EstSvc: compute_mu()
            EstSvc->>EstSvc: compute_sigma()
            EstSvc->>EstSvc: validate_psd()
            EstSvc-->>BacktestSvc: μ, Σ
            
            BacktestSvc->>OptSvc: optimize(μ, Σ, TANGENCY, constraints)
            
            alt Optimization succeeds
                OptSvc-->>BacktestSvc: new_weights[]
                BacktestSvc->>BacktestSvc: compute_turnover(old_weights, new_weights)
                BacktestSvc->>BacktestSvc: apply_transaction_cost(turnover × cost_bps)
                BacktestSvc->>BacktestSvc: update_weights(new_weights)
            else Optimization fails
                BacktestSvc->>BacktestSvc: keep_previous_weights()
                BacktestSvc->>BacktestSvc: log_warning("Optimization failed at t")
            end
        end
        
        BacktestSvc->>BacktestSvc: compute_period_return(weights, asset_returns)
        BacktestSvc->>BacktestSvc: update_portfolio_value()
        BacktestSvc->>BacktestSvc: compute_drawdown()
        BacktestSvc->>BacktestSvc: record_point(t, value, return, drawdown, turnover)
    end

    Note over User,DB: Phase 3: Compute Summary Statistics

    BacktestSvc->>BacktestSvc: compute_total_return()
    BacktestSvc->>BacktestSvc: compute_annualized_return()
    BacktestSvc->>BacktestSvc: compute_annualized_vol()
    BacktestSvc->>BacktestSvc: compute_sharpe()
    BacktestSvc->>BacktestSvc: compute_max_drawdown()
    BacktestSvc->>BacktestSvc: compute_var_cvar(95%)
    BacktestSvc->>BacktestSvc: compute_avg_turnover()
    
    alt Benchmark provided
        BacktestSvc->>BacktestSvc: compute_active_returns()
        BacktestSvc->>BacktestSvc: compute_tracking_error()
        BacktestSvc->>BacktestSvc: compute_information_ratio()
    end
    
    BacktestSvc->>BacktestSvc: generate_survivorship_bias_note()
    BacktestSvc-->>CmdH: BacktestResult{points[], summary}

    Note over User,DB: Phase 4: Persist Results

    CmdH->>Repo: backtest_repo.save(run, points, summary)
    Repo->>DB: INSERT backtest_runs
    Repo->>DB: INSERT backtest_points (bulk)
    Repo->>DB: INSERT backtest_summary
    DB-->>Repo: backtest_id
    Repo-->>CmdH: BacktestRun
    CmdH-->>API: 201 Created
    API-->>User: BacktestRun with summary

    Note over User,DB: Phase 5: Query Results

    User->>API: GET /queries/backtest/{backtest_id}
    API->>QryH: GetBacktestRunQuery
    QryH->>Repo: backtest_repo.get(backtest_id)
    Repo->>DB: SELECT from backtest_runs, backtest_summary
    DB-->>Repo: run + summary
    Repo-->>QryH: BacktestRunDetail
    QryH-->>API: 200 OK
    API-->>User: Summary statistics

    User->>API: GET /queries/backtest/{backtest_id}/series
    API->>QryH: GetBacktestSeriesQuery
    QryH->>Repo: backtest_repo.get_points(backtest_id)
    Repo->>DB: SELECT from backtest_points ORDER BY obs_date
    DB-->>Repo: points[]
    Repo-->>QryH: BacktestPoint[]
    QryH-->>API: 200 OK
    API-->>User: Full time series for charting
```

### Backtest State Machine

```mermaid
stateDiagram-v2
    [*] --> Initialized: Create backtest config
    Initialized --> Running: Start simulation
    
    Running --> RebalanceCheck: Each period
    RebalanceCheck --> Estimating: Is rebalance date
    RebalanceCheck --> Updating: Not rebalance date
    
    Estimating --> Optimizing: μ, Σ computed
    Optimizing --> ApplyingWeights: Success
    Optimizing --> Updating: Failed (keep old weights)
    
    ApplyingWeights --> ComputingCosts: New weights set
    ComputingCosts --> Updating: Costs applied
    
    Updating --> Recording: Update portfolio value
    Recording --> RebalanceCheck: More periods
    Recording --> Summarizing: End of period
    
    Summarizing --> Persisting: Stats computed
    Persisting --> [*]: Results saved
```

### Metrics Computation

```mermaid
flowchart TD
    subgraph Inputs
        PTS[backtest_points]
        BM[benchmark_returns]
    end
    
    subgraph Returns["Return Metrics"]
        TR[Total Return]
        AR[Annualized Return]
    end
    
    subgraph Risk["Risk Metrics"]
        VOL[Annualized Vol]
        MDD[Max Drawdown]
        VAR[VaR 95%]
        CVAR[CVaR 95%]
    end
    
    subgraph RiskAdj["Risk-Adjusted"]
        SR[Sharpe Ratio]
    end
    
    subgraph Benchmark["vs Benchmark"]
        ACT[Active Return]
        TE[Tracking Error]
        IR[Information Ratio]
    end
    
    subgraph Costs["Cost Metrics"]
        TO[Avg Turnover]
    end
    
    PTS --> TR
    PTS --> AR
    PTS --> VOL
    PTS --> MDD
    PTS --> VAR
    PTS --> CVAR
    PTS --> TO
    
    AR --> SR
    VOL --> SR
    
    PTS --> ACT
    BM --> ACT
    ACT --> TE
    ACT --> IR
    TE --> IR
```

---

## Error Handling Patterns

All workflows follow consistent error handling:

```mermaid
flowchart TD
    A[Command/Query Received] --> B{Validate Input}
    B -->|Invalid| C[Return 400 VALIDATION_ERROR]
    B -->|Valid| D{Find Resources}
    D -->|Not Found| E[Return 404 NOT_FOUND]
    D -->|Found| F{Execute Business Logic}
    F -->|Domain Error| G[Return 200 with status/reason]
    F -->|Infrastructure Error| H[Return 500 INTERNAL_ERROR]
    F -->|Success| I[Return 200/201 with result]
    
    G --> G1[e.g., INFEASIBLE optimization]
    G --> G2[e.g., PSD repair warning]
```

### Error Categories

| Category | HTTP Status | Example |
|----------|-------------|---------|
| Validation | 400 | Missing required field |
| Not Found | 404 | Unknown assumption_id |
| Conflict | 409 | Duplicate ticker |
| Business Logic | 200 | Optimization infeasible (status in body) |
| External | 502 | Vendor API timeout |
| Internal | 500 | Unexpected exception |

---

## Cross-Cutting Concerns

### Audit Trail

Every command persists:
- Timestamp
- Input parameters
- Output identifiers
- Status/errors

```mermaid
flowchart LR
    CMD[Command] --> HANDLER[Handler]
    HANDLER --> AUDIT[Audit Log]
    HANDLER --> RESULT[Result]
    AUDIT --> DB[(audit_log table)]
```

### Idempotency

Commands that create resources use client-generated UUIDs where possible, enabling safe retries:

```mermaid
sequenceDiagram
    User->>API: POST /commands/optimize {idempotency_key: X}
    API->>DB: Check if X exists
    alt Already processed
        DB-->>API: Existing result
        API-->>User: 200 OK (cached)
    else New request
        API->>Handler: Process
        Handler->>DB: Save with key X
        DB-->>Handler: OK
        Handler-->>API: Result
        API-->>User: 201 Created
    end
```

### Transactional Boundaries

Each command executes within a single database transaction:

```python
# commands/optimization.py
async def handle(self, request: RunOptimizationRequest) -> OptimizationRun:
    async with self._db.transaction():  # Single transaction
        assumptions = await self._assumption_repo.get(request.assumption_id)
        result = self._optimizer.optimize(assumptions, request.constraints)
        run = await self._optimization_repo.save(result)
        return run
    # Commit on success, rollback on exception
```
