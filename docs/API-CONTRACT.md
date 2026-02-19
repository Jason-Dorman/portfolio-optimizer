# API Contract v1

## Overview

This document defines the REST API for the Portfolio Builder & Risk Analyzer. The API follows a **CQRS-style organization**:

- **Commands** (`/commands/*`) — Write operations that mutate state
- **Queries** (`/queries/*`) — Read operations that return data without side effects

This separation enables:
- Independent scaling of read vs. write workloads
- Clear audit boundaries (all mutations flow through commands)
- Easier caching of query responses
- Alignment with SOLID principles (Single Responsibility, Interface Segregation)

---

## Design Principles

### SOLID Alignment

| Principle | Application |
|-----------|-------------|
| **Single Responsibility** | Each endpoint does one thing. Commands mutate; queries read. |
| **Open/Closed** | New endpoints extend functionality without modifying existing ones. |
| **Liskov Substitution** | All command responses follow the same envelope; all query responses are self-describing. |
| **Interface Segregation** | Clients only depend on the endpoints they use. Screening clients don't need optimization endpoints. |
| **Dependency Inversion** | Handlers depend on abstractions (repositories, services), not concrete implementations. |

### Conventions

- All requests/responses are JSON
- UUIDs for all entity IDs
- ISO 8601 for dates and timestamps
- Snake_case for field names
- Pagination via `limit` and `offset` query params (queries only)
- Errors return `{ "error": { "code": "...", "message": "...", "details": {...} } }`

---

## Quick Reference (Markdown)

### Commands — Write Operations

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|--------------|----------|
| POST | `/commands/assets` | Create asset | `CreateAssetRequest` | `Asset` |
| POST | `/commands/universes` | Create universe | `CreateUniverseRequest` | `Universe` |
| POST | `/commands/universes/{id}/assets` | Add assets to universe | `AddUniverseAssetsRequest` | `Universe` |
| DELETE | `/commands/universes/{id}/assets` | Remove assets from universe | `RemoveUniverseAssetsRequest` | `Universe` |
| POST | `/commands/holdings/snapshots` | Create holdings snapshot | `CreateHoldingsSnapshotRequest` | `HoldingsSnapshot` |
| POST | `/commands/ingest/prices` | Ingest price data | `IngestPricesRequest` | `IngestResult` |
| POST | `/commands/ingest/risk-free` | Ingest risk-free rates | `IngestRiskFreeRequest` | `IngestResult` |
| POST | `/commands/returns/compute` | Compute return series | `ComputeReturnsRequest` | `ComputeReturnsResult` |
| POST | `/commands/assumptions` | Generate assumption set | `CreateAssumptionSetRequest` | `AssumptionSet` |
| POST | `/commands/screening` | Run asset screening | `RunScreeningRequest` | `ScreeningRun` |
| POST | `/commands/optimize` | Run optimization | `RunOptimizationRequest` | `OptimizationRun` |
| POST | `/commands/drift-check` | Check portfolio drift | `RunDriftCheckRequest` | `DriftCheck` |
| POST | `/commands/backtest` | Run backtest | `RunBacktestRequest` | `BacktestRun` |
| POST | `/commands/scenarios` | Define stress scenario | `CreateScenarioRequest` | `ScenarioDefinition` |
| POST | `/commands/scenarios/{id}/apply` | Apply scenario to portfolio | `ApplyScenarioRequest` | `ScenarioResult` |

### Queries — Read Operations

| Method | Path | Description | Query Params | Response |
|--------|------|-------------|--------------|----------|
| GET | `/queries/assets` | List assets | `ticker`, `asset_class`, `limit`, `offset` | `Asset[]` |
| GET | `/queries/assets/{id}` | Get asset by ID | — | `Asset` |
| GET | `/queries/universes` | List universes | `universe_type`, `limit`, `offset` | `Universe[]` |
| GET | `/queries/universes/{id}` | Get universe with assets | — | `UniverseDetail` |
| GET | `/queries/holdings/snapshots` | List holdings snapshots | `limit`, `offset` | `HoldingsSnapshot[]` |
| GET | `/queries/holdings/snapshots/{id}` | Get snapshot with positions | — | `HoldingsSnapshotDetail` |
| GET | `/queries/holdings/latest` | Get most recent snapshot | — | `HoldingsSnapshotDetail` |
| GET | `/queries/prices` | Get price history | `asset_id`, `start`, `end`, `frequency` | `PriceBar[]` |
| GET | `/queries/returns` | Get return series | `asset_id`, `start`, `end`, `frequency`, `return_type` | `ReturnPoint[]` |
| GET | `/queries/assumptions` | List assumption sets | `universe_id`, `limit`, `offset` | `AssumptionSet[]` |
| GET | `/queries/assumptions/{id}` | Get assumption set detail | — | `AssumptionSetDetail` |
| GET | `/queries/assumptions/{id}/covariance` | Get covariance matrix | — | `CovarianceMatrix` |
| GET | `/queries/assumptions/{id}/correlation` | Get correlation matrix | — | `CorrelationMatrix` |
| GET | `/queries/screening` | List screening runs | `limit`, `offset` | `ScreeningRunSummary[]` |
| GET | `/queries/screening/{id}` | Get screening run detail | — | `ScreeningRunDetail` |
| GET | `/queries/screening/{id}/scores` | Get all candidate scores | `limit`, `offset` | `ScreeningScore[]` |
| GET | `/queries/optimization` | List optimization runs | `assumption_id`, `status`, `limit`, `offset` | `OptimizationRunSummary[]` |
| GET | `/queries/optimization/{id}` | Get optimization detail | — | `OptimizationRunDetail` |
| GET | `/queries/optimization/{id}/weights` | Get portfolio weights | — | `PortfolioWeight[]` |
| GET | `/queries/optimization/{id}/risk` | Get risk decomposition | — | `RiskDecomposition` |
| GET | `/queries/drift/{id}` | Get drift check detail | — | `DriftCheckDetail` |
| GET | `/queries/backtest` | List backtest runs | `limit`, `offset` | `BacktestRunSummary[]` |
| GET | `/queries/backtest/{id}` | Get backtest detail | — | `BacktestRunDetail` |
| GET | `/queries/backtest/{id}/series` | Get backtest time series | — | `BacktestPoint[]` |
| GET | `/queries/scenarios` | List scenario definitions | — | `ScenarioDefinition[]` |
| GET | `/queries/scenarios/results/{id}` | Get scenario result | — | `ScenarioResult` |

---

## Request/Response Schemas

### Common Types

```yaml
# Reusable types
UUID:
  type: string
  format: uuid
  example: "550e8400-e29b-41d4-a716-446655440000"

Date:
  type: string
  format: date
  example: "2024-01-15"

Timestamp:
  type: string
  format: date-time
  example: "2024-01-15T10:30:00Z"

AssetClass:
  type: string
  enum: [equity, fixed_income, commodity, real_estate, cash, crypto, other]

Geography:
  type: string
  enum: [us, developed_ex_us, emerging, global]

Frequency:
  type: string
  enum: [daily, weekly, monthly]

ReturnType:
  type: string
  enum: [simple, log]

Estimator:
  type: string
  enum: [historical, ewma, shrinkage]

CovMethod:
  type: string
  enum: [sample, ledoit_wolf, nearest_psd]

OptimizationStatus:
  type: string
  enum: [SUCCESS, INFEASIBLE, ERROR]

RunType:
  type: string
  enum: [MVP, FRONTIER_POINT, FRONTIER_SERIES, TANGENCY]

Objective:
  type: string
  enum: [MIN_VAR, MAX_SHARPE]
```

### Command Schemas

```yaml
# ===== ASSETS =====

CreateAssetRequest:
  type: object
  required: [ticker, name, asset_class, geography, currency]
  properties:
    ticker:
      type: string
      example: "VTI"
    name:
      type: string
      example: "Vanguard Total Stock Market ETF"
    asset_class:
      $ref: "#/AssetClass"
    sub_class:
      type: string
      example: "total_market_us"
    sector:
      type: string
      nullable: true
      description: "GICS sector (null for non-equity)"
    geography:
      $ref: "#/Geography"
    currency:
      type: string
      example: "USD"
    is_etf:
      type: boolean
      default: true

Asset:
  type: object
  properties:
    asset_id:
      $ref: "#/UUID"
    ticker:
      type: string
    name:
      type: string
    asset_class:
      $ref: "#/AssetClass"
    sub_class:
      type: string
    sector:
      type: string
      nullable: true
    geography:
      $ref: "#/Geography"
    currency:
      type: string
    is_etf:
      type: boolean
    created_at:
      $ref: "#/Timestamp"

# ===== UNIVERSES =====

CreateUniverseRequest:
  type: object
  required: [name, universe_type]
  properties:
    name:
      type: string
      example: "US ETF Core"
    description:
      type: string
    universe_type:
      type: string
      enum: [active, candidate_pool]
    asset_ids:
      type: array
      items:
        $ref: "#/UUID"
      description: "Optional initial assets"

AddUniverseAssetsRequest:
  type: object
  required: [asset_ids]
  properties:
    asset_ids:
      type: array
      items:
        $ref: "#/UUID"
    is_benchmark:
      type: boolean
      default: false

RemoveUniverseAssetsRequest:
  type: object
  required: [asset_ids]
  properties:
    asset_ids:
      type: array
      items:
        $ref: "#/UUID"

Universe:
  type: object
  properties:
    universe_id:
      $ref: "#/UUID"
    name:
      type: string
    description:
      type: string
    universe_type:
      type: string
    asset_count:
      type: integer
    created_at:
      $ref: "#/Timestamp"

# ===== HOLDINGS =====

CreateHoldingsSnapshotRequest:
  type: object
  required: [label, snapshot_date, positions]
  properties:
    label:
      type: string
      example: "My Brokerage Account"
    snapshot_date:
      $ref: "#/Date"
    positions:
      type: array
      items:
        $ref: "#/HoldingsPosition"
      description: "Weights OR market_values. If market_values provided, system normalizes to weights."

HoldingsPosition:
  type: object
  required: [ticker]
  properties:
    ticker:
      type: string
    weight:
      type: number
      nullable: true
      description: "Provide weight OR market_value, not both"
    market_value:
      type: number
      nullable: true

HoldingsSnapshot:
  type: object
  properties:
    snapshot_id:
      $ref: "#/UUID"
    label:
      type: string
    snapshot_date:
      $ref: "#/Date"
    position_count:
      type: integer
    created_at:
      $ref: "#/Timestamp"

# ===== INGEST =====

IngestPricesRequest:
  type: object
  required: [asset_ids, start_date, end_date, frequency]
  properties:
    asset_ids:
      type: array
      items:
        $ref: "#/UUID"
    start_date:
      $ref: "#/Date"
    end_date:
      $ref: "#/Date"
    frequency:
      $ref: "#/Frequency"
    vendor:
      type: string
      enum: [polygon, tiingo, alphavantage]
      default: "polygon"

IngestRiskFreeRequest:
  type: object
  required: [start_date, end_date]
  properties:
    start_date:
      $ref: "#/Date"
    end_date:
      $ref: "#/Date"
    series_code:
      type: string
      default: "DTB3"
      description: "FRED series code"

IngestResult:
  type: object
  properties:
    rows_inserted:
      type: integer
    rows_updated:
      type: integer
    errors:
      type: array
      items:
        type: object
        properties:
          asset_id:
            $ref: "#/UUID"
          error:
            type: string

# ===== RETURNS =====

ComputeReturnsRequest:
  type: object
  required: [asset_ids, frequency, return_type]
  properties:
    asset_ids:
      type: array
      items:
        $ref: "#/UUID"
    frequency:
      $ref: "#/Frequency"
    return_type:
      $ref: "#/ReturnType"
    start_date:
      $ref: "#/Date"
      nullable: true
    end_date:
      $ref: "#/Date"
      nullable: true

ComputeReturnsResult:
  type: object
  properties:
    assets_processed:
      type: integer
    returns_computed:
      type: integer
    date_range:
      type: object
      properties:
        start:
          $ref: "#/Date"
        end:
          $ref: "#/Date"

# ===== ASSUMPTIONS =====

CreateAssumptionSetRequest:
  type: object
  required: [universe_id, frequency, return_type, lookback_start, lookback_end]
  properties:
    universe_id:
      $ref: "#/UUID"
    frequency:
      $ref: "#/Frequency"
    return_type:
      $ref: "#/ReturnType"
    lookback_start:
      $ref: "#/Date"
    lookback_end:
      $ref: "#/Date"
    estimator:
      $ref: "#/Estimator"
      default: "historical"
    cov_method:
      $ref: "#/CovMethod"
      default: "sample"
    rf_annual:
      type: number
      description: "Override risk-free rate. If null, uses latest from FRED."
      nullable: true

AssumptionSet:
  type: object
  properties:
    assumption_id:
      $ref: "#/UUID"
    universe_id:
      $ref: "#/UUID"
    frequency:
      $ref: "#/Frequency"
    return_type:
      $ref: "#/ReturnType"
    lookback_start:
      $ref: "#/Date"
    lookback_end:
      $ref: "#/Date"
    annualization_factor:
      type: integer
    rf_annual:
      type: number
    estimator:
      $ref: "#/Estimator"
    cov_method:
      $ref: "#/CovMethod"
    psd_repair_applied:
      type: boolean
    psd_repair_note:
      type: string
      nullable: true
    asset_count:
      type: integer
    created_at:
      $ref: "#/Timestamp"

# ===== SCREENING =====

RunScreeningRequest:
  type: object
  required: [assumption_id, candidate_pool_id]
  properties:
    assumption_id:
      $ref: "#/UUID"
    candidate_pool_id:
      $ref: "#/UUID"
      description: "Universe with universe_type = candidate_pool"
    reference_snapshot_id:
      $ref: "#/UUID"
      nullable: true
      description: "Current holdings snapshot. Provide this OR reference_universe_id."
    reference_universe_id:
      $ref: "#/UUID"
      nullable: true
      description: "Seed universe for equal-weight reference. Provide this OR reference_snapshot_id."
    nominal_add_weight:
      type: number
      default: 0.05
      description: "Weight assumed when computing marginal vol reduction"
    score_weights:
      type: object
      properties:
        correlation:
          type: number
          default: 0.40
        marginal_vol:
          type: number
          default: 0.30
        sector_gap:
          type: number
          default: 0.15
        hhi:
          type: number
          default: 0.15
      description: "Must sum to 1.0"

ScreeningRun:
  type: object
  properties:
    screening_id:
      $ref: "#/UUID"
    assumption_id:
      $ref: "#/UUID"
    candidate_pool_id:
      $ref: "#/UUID"
    reference_type:
      type: string
      enum: [current_holdings, seed_universe]
    candidates_scored:
      type: integer
    top_candidates:
      type: array
      items:
        $ref: "#/ScreeningScore"
      description: "Top 10 by default"
    created_at:
      $ref: "#/Timestamp"

ScreeningScore:
  type: object
  properties:
    asset_id:
      $ref: "#/UUID"
    ticker:
      type: string
    avg_pairwise_corr:
      type: number
    marginal_vol_reduction:
      type: number
    sector_gap_score:
      type: number
    hhi_reduction:
      type: number
    composite_score:
      type: number
    rank:
      type: integer
    explanation:
      type: string

# ===== OPTIMIZATION =====

RunOptimizationRequest:
  type: object
  required: [assumption_id, run_type, objective]
  properties:
    assumption_id:
      $ref: "#/UUID"
    run_type:
      $ref: "#/RunType"
    objective:
      $ref: "#/Objective"
    target_return:
      type: number
      nullable: true
      description: "Required for FRONTIER_POINT"
    frontier_points:
      type: integer
      nullable: true
      description: "Number of points for FRONTIER_SERIES (default 20)"
    reference_snapshot_id:
      $ref: "#/UUID"
      nullable: true
      description: "Current holdings for turnover constraint"
    constraints:
      $ref: "#/OptimizationConstraints"

OptimizationConstraints:
  type: object
  properties:
    long_only:
      type: boolean
      default: true
    min_weight:
      type: number
      nullable: true
      description: "Per-asset minimum (overrides long_only if set)"
    max_weight:
      type: number
      nullable: true
      description: "Per-asset maximum"
    leverage_cap:
      type: number
      nullable: true
      description: "Sum of absolute weights cap"
    concentration_cap:
      type: number
      nullable: true
      description: "Max single position size"
    turnover_cap:
      type: number
      nullable: true
      description: "Max turnover vs reference"
    asset_bounds:
      type: object
      additionalProperties:
        type: object
        properties:
          min:
            type: number
          max:
            type: number
      description: "Per-asset overrides keyed by asset_id"

OptimizationRun:
  type: object
  properties:
    run_id:
      $ref: "#/UUID"
    assumption_id:
      $ref: "#/UUID"
    run_type:
      $ref: "#/RunType"
    objective:
      $ref: "#/Objective"
    status:
      $ref: "#/OptimizationStatus"
    infeasibility_reason:
      type: string
      nullable: true
    result:
      $ref: "#/OptimizationResult"
      nullable: true
    weights:
      type: array
      items:
        $ref: "#/PortfolioWeight"
    created_at:
      $ref: "#/Timestamp"

OptimizationResult:
  type: object
  properties:
    exp_return:
      type: number
    variance:
      type: number
    stdev:
      type: number
    sharpe:
      type: number
      nullable: true
    hhi:
      type: number
    effective_n:
      type: number
    explanation:
      type: string

PortfolioWeight:
  type: object
  properties:
    asset_id:
      $ref: "#/UUID"
    ticker:
      type: string
    weight:
      type: number
    mcr:
      type: number
      description: "Marginal contribution to risk"
    crc:
      type: number
      description: "Component contribution to risk"
    prc:
      type: number
      description: "Percent risk contribution"

# ===== DRIFT =====

RunDriftCheckRequest:
  type: object
  required: [run_id, check_date]
  properties:
    run_id:
      $ref: "#/UUID"
      description: "Optimization run to check drift against"
    check_date:
      $ref: "#/Date"
    threshold_pct:
      type: number
      default: 0.05
      description: "Breach threshold (0.05 = 5%)"

DriftCheck:
  type: object
  properties:
    drift_id:
      $ref: "#/UUID"
    run_id:
      $ref: "#/UUID"
    check_date:
      $ref: "#/Date"
    threshold_pct:
      type: number
    any_breach:
      type: boolean
    positions:
      type: array
      items:
        $ref: "#/DriftPosition"
    created_at:
      $ref: "#/Timestamp"

DriftPosition:
  type: object
  properties:
    asset_id:
      $ref: "#/UUID"
    ticker:
      type: string
    target_weight:
      type: number
    current_weight:
      type: number
    drift_abs:
      type: number
    breached:
      type: boolean
    explanation:
      type: string
      nullable: true
      description: "Present when breached = true"

# ===== BACKTEST =====

RunBacktestRequest:
  type: object
  required: [universe_id, strategy, rebal_freq, window_length, start_date, end_date]
  properties:
    universe_id:
      $ref: "#/UUID"
    benchmark_asset_id:
      $ref: "#/UUID"
      nullable: true
    strategy:
      type: string
      enum: [TANGENCY_REBAL, MVP_REBAL, EW_REBAL]
    rebal_freq:
      type: string
      enum: [monthly, quarterly, threshold]
    rebal_threshold:
      type: number
      nullable: true
      description: "Required if rebal_freq = threshold"
    window_length:
      type: integer
      description: "Lookback window in periods"
    start_date:
      $ref: "#/Date"
    end_date:
      $ref: "#/Date"
    transaction_cost_bps:
      type: number
      default: 10
    constraints:
      $ref: "#/OptimizationConstraints"

BacktestRun:
  type: object
  properties:
    backtest_id:
      $ref: "#/UUID"
    universe_id:
      $ref: "#/UUID"
    strategy:
      type: string
    rebal_freq:
      type: string
    summary:
      $ref: "#/BacktestSummary"
    survivorship_bias_note:
      type: string
    created_at:
      $ref: "#/Timestamp"

BacktestSummary:
  type: object
  properties:
    total_return:
      type: number
    annualized_return:
      type: number
    annualized_vol:
      type: number
    sharpe:
      type: number
    max_drawdown:
      type: number
    var_95:
      type: number
    cvar_95:
      type: number
    avg_turnover:
      type: number
    tracking_error:
      type: number
      nullable: true
    information_ratio:
      type: number
      nullable: true

# ===== SCENARIOS =====

CreateScenarioRequest:
  type: object
  required: [name, shocks]
  properties:
    name:
      type: string
      example: "Equity Crash -30%"
    shocks:
      type: object
      additionalProperties:
        type: number
      example:
        equity: -0.30
        duration: 2.0

ApplyScenarioRequest:
  type: object
  required: [run_id]
  properties:
    run_id:
      $ref: "#/UUID"
      description: "Optimization run to stress test"

ScenarioDefinition:
  type: object
  properties:
    scenario_id:
      $ref: "#/UUID"
    name:
      type: string
    shocks:
      type: object
    created_at:
      $ref: "#/Timestamp"

ScenarioResult:
  type: object
  properties:
    result_id:
      $ref: "#/UUID"
    run_id:
      $ref: "#/UUID"
    scenario_id:
      $ref: "#/UUID"
    scenario_name:
      type: string
    shocked_return:
      type: number
    shocked_vol:
      type: number
      nullable: true
    created_at:
      $ref: "#/Timestamp"
```

---

## Error Responses

All errors follow this structure:

```yaml
ErrorResponse:
  type: object
  properties:
    error:
      type: object
      properties:
        code:
          type: string
          description: "Machine-readable error code"
        message:
          type: string
          description: "Human-readable message"
        details:
          type: object
          nullable: true
          description: "Additional context"

# Common error codes
ErrorCodes:
  - VALIDATION_ERROR      # Request validation failed
  - NOT_FOUND            # Resource not found
  - CONFLICT             # Duplicate or conflicting resource
  - INFEASIBLE           # Optimization has no solution
  - EXTERNAL_API_ERROR   # Data vendor API failed
  - INTERNAL_ERROR       # Unexpected server error
```

### Example Error Responses

```json
// 400 Bad Request - Validation
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Screening requires either reference_snapshot_id or reference_universe_id",
    "details": {
      "field": "reference_snapshot_id",
      "constraint": "exactly_one_required"
    }
  }
}

// 404 Not Found
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Assumption set not found",
    "details": {
      "assumption_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }
}

// 200 OK but optimization infeasible
{
  "run_id": "...",
  "status": "INFEASIBLE",
  "infeasibility_reason": "Target return of 11% exceeds maximum achievable return of 8.4% under long-only constraints",
  "result": null,
  "weights": []
}
```

---

## OpenAPI Specification

The full OpenAPI 3.0 specification follows. Save as `openapi.yaml` for tooling.

```yaml
openapi: 3.0.3
info:
  title: Portfolio Builder & Risk Analyzer API
  description: |
    CQRS-style API for portfolio construction, optimization, and risk analysis.
    
    - Commands (`/commands/*`) mutate state
    - Queries (`/queries/*`) read state without side effects
  version: 1.0.0
  contact:
    name: API Support

servers:
  - url: http://localhost:8000
    description: Local development
  - url: https://api.portfolio-builder.example.com
    description: Production

tags:
  - name: Commands - Assets
    description: Asset management commands
  - name: Commands - Universes
    description: Universe management commands
  - name: Commands - Holdings
    description: Holdings snapshot commands
  - name: Commands - Ingest
    description: Data ingestion commands
  - name: Commands - Estimation
    description: Assumption set generation
  - name: Commands - Screening
    description: Asset screening commands
  - name: Commands - Optimization
    description: Portfolio optimization commands
  - name: Commands - Risk
    description: Risk analysis commands
  - name: Queries - Assets
    description: Asset queries
  - name: Queries - Universes
    description: Universe queries
  - name: Queries - Holdings
    description: Holdings queries
  - name: Queries - Market Data
    description: Price and return queries
  - name: Queries - Estimation
    description: Assumption set queries
  - name: Queries - Screening
    description: Screening result queries
  - name: Queries - Optimization
    description: Optimization result queries
  - name: Queries - Backtest
    description: Backtest result queries

paths:
  # ===== COMMANDS =====
  
  /commands/assets:
    post:
      tags: [Commands - Assets]
      summary: Create a new asset
      operationId: createAsset
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateAssetRequest'
      responses:
        '201':
          description: Asset created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Asset'
        '400':
          $ref: '#/components/responses/ValidationError'
        '409':
          $ref: '#/components/responses/ConflictError'

  /commands/universes:
    post:
      tags: [Commands - Universes]
      summary: Create a new universe
      operationId: createUniverse
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUniverseRequest'
      responses:
        '201':
          description: Universe created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Universe'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/universes/{universe_id}/assets:
    post:
      tags: [Commands - Universes]
      summary: Add assets to universe
      operationId: addUniverseAssets
      parameters:
        - $ref: '#/components/parameters/UniverseId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AddUniverseAssetsRequest'
      responses:
        '200':
          description: Assets added
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Universe'
        '404':
          $ref: '#/components/responses/NotFoundError'
    delete:
      tags: [Commands - Universes]
      summary: Remove assets from universe
      operationId: removeUniverseAssets
      parameters:
        - $ref: '#/components/parameters/UniverseId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RemoveUniverseAssetsRequest'
      responses:
        '200':
          description: Assets removed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Universe'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /commands/holdings/snapshots:
    post:
      tags: [Commands - Holdings]
      summary: Create holdings snapshot
      operationId: createHoldingsSnapshot
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateHoldingsSnapshotRequest'
      responses:
        '201':
          description: Snapshot created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HoldingsSnapshot'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/ingest/prices:
    post:
      tags: [Commands - Ingest]
      summary: Ingest price data from vendor
      operationId: ingestPrices
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/IngestPricesRequest'
      responses:
        '200':
          description: Ingest complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/IngestResult'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/ingest/risk-free:
    post:
      tags: [Commands - Ingest]
      summary: Ingest risk-free rate series from FRED
      operationId: ingestRiskFree
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/IngestRiskFreeRequest'
      responses:
        '200':
          description: Ingest complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/IngestResult'

  /commands/returns/compute:
    post:
      tags: [Commands - Estimation]
      summary: Compute return series from prices
      operationId: computeReturns
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ComputeReturnsRequest'
      responses:
        '200':
          description: Returns computed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ComputeReturnsResult'

  /commands/assumptions:
    post:
      tags: [Commands - Estimation]
      summary: Generate assumption set (μ, Σ)
      operationId: createAssumptionSet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateAssumptionSetRequest'
      responses:
        '201':
          description: Assumption set created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssumptionSet'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/screening:
    post:
      tags: [Commands - Screening]
      summary: Run asset screening
      operationId: runScreening
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RunScreeningRequest'
      responses:
        '201':
          description: Screening complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScreeningRun'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/optimize:
    post:
      tags: [Commands - Optimization]
      summary: Run portfolio optimization
      operationId: runOptimization
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RunOptimizationRequest'
      responses:
        '201':
          description: Optimization complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OptimizationRun'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/drift-check:
    post:
      tags: [Commands - Risk]
      summary: Check portfolio drift
      operationId: runDriftCheck
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RunDriftCheckRequest'
      responses:
        '201':
          description: Drift check complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DriftCheck'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /commands/backtest:
    post:
      tags: [Commands - Risk]
      summary: Run backtest simulation
      operationId: runBacktest
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RunBacktestRequest'
      responses:
        '201':
          description: Backtest complete
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BacktestRun'
        '400':
          $ref: '#/components/responses/ValidationError'

  /commands/scenarios:
    post:
      tags: [Commands - Risk]
      summary: Define stress scenario
      operationId: createScenario
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateScenarioRequest'
      responses:
        '201':
          description: Scenario created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScenarioDefinition'

  /commands/scenarios/{scenario_id}/apply:
    post:
      tags: [Commands - Risk]
      summary: Apply scenario to portfolio
      operationId: applyScenario
      parameters:
        - $ref: '#/components/parameters/ScenarioId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ApplyScenarioRequest'
      responses:
        '201':
          description: Scenario applied
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScenarioResult'
        '404':
          $ref: '#/components/responses/NotFoundError'

  # ===== QUERIES =====
  
  /queries/assets:
    get:
      tags: [Queries - Assets]
      summary: List assets
      operationId: listAssets
      parameters:
        - name: ticker
          in: query
          schema:
            type: string
        - name: asset_class
          in: query
          schema:
            $ref: '#/components/schemas/AssetClass'
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Asset list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Asset'

  /queries/assets/{asset_id}:
    get:
      tags: [Queries - Assets]
      summary: Get asset by ID
      operationId: getAsset
      parameters:
        - $ref: '#/components/parameters/AssetId'
      responses:
        '200':
          description: Asset details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Asset'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/universes:
    get:
      tags: [Queries - Universes]
      summary: List universes
      operationId: listUniverses
      parameters:
        - name: universe_type
          in: query
          schema:
            type: string
            enum: [active, candidate_pool]
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Universe list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Universe'

  /queries/universes/{universe_id}:
    get:
      tags: [Queries - Universes]
      summary: Get universe with assets
      operationId: getUniverse
      parameters:
        - $ref: '#/components/parameters/UniverseId'
      responses:
        '200':
          description: Universe details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UniverseDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/holdings/snapshots:
    get:
      tags: [Queries - Holdings]
      summary: List holdings snapshots
      operationId: listHoldingsSnapshots
      parameters:
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Snapshot list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/HoldingsSnapshot'

  /queries/holdings/snapshots/{snapshot_id}:
    get:
      tags: [Queries - Holdings]
      summary: Get snapshot with positions
      operationId: getHoldingsSnapshot
      parameters:
        - $ref: '#/components/parameters/SnapshotId'
      responses:
        '200':
          description: Snapshot details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HoldingsSnapshotDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/holdings/latest:
    get:
      tags: [Queries - Holdings]
      summary: Get most recent snapshot
      operationId: getLatestHoldingsSnapshot
      responses:
        '200':
          description: Latest snapshot
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HoldingsSnapshotDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/prices:
    get:
      tags: [Queries - Market Data]
      summary: Get price history
      operationId: getPrices
      parameters:
        - name: asset_id
          in: query
          required: true
          schema:
            type: string
            format: uuid
        - name: start
          in: query
          schema:
            type: string
            format: date
        - name: end
          in: query
          schema:
            type: string
            format: date
        - name: frequency
          in: query
          schema:
            $ref: '#/components/schemas/Frequency'
      responses:
        '200':
          description: Price bars
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/PriceBar'

  /queries/returns:
    get:
      tags: [Queries - Market Data]
      summary: Get return series
      operationId: getReturns
      parameters:
        - name: asset_id
          in: query
          required: true
          schema:
            type: string
            format: uuid
        - name: start
          in: query
          schema:
            type: string
            format: date
        - name: end
          in: query
          schema:
            type: string
            format: date
        - name: frequency
          in: query
          schema:
            $ref: '#/components/schemas/Frequency'
        - name: return_type
          in: query
          schema:
            $ref: '#/components/schemas/ReturnType'
      responses:
        '200':
          description: Return series
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ReturnPoint'

  /queries/assumptions:
    get:
      tags: [Queries - Estimation]
      summary: List assumption sets
      operationId: listAssumptionSets
      parameters:
        - name: universe_id
          in: query
          schema:
            type: string
            format: uuid
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Assumption set list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/AssumptionSet'

  /queries/assumptions/{assumption_id}:
    get:
      tags: [Queries - Estimation]
      summary: Get assumption set detail
      operationId: getAssumptionSet
      parameters:
        - $ref: '#/components/parameters/AssumptionId'
      responses:
        '200':
          description: Assumption set details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssumptionSetDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/assumptions/{assumption_id}/covariance:
    get:
      tags: [Queries - Estimation]
      summary: Get covariance matrix
      operationId: getCovarianceMatrix
      parameters:
        - $ref: '#/components/parameters/AssumptionId'
      responses:
        '200':
          description: Covariance matrix
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CovarianceMatrix'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/assumptions/{assumption_id}/correlation:
    get:
      tags: [Queries - Estimation]
      summary: Get correlation matrix
      operationId: getCorrelationMatrix
      parameters:
        - $ref: '#/components/parameters/AssumptionId'
      responses:
        '200':
          description: Correlation matrix
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CorrelationMatrix'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/screening:
    get:
      tags: [Queries - Screening]
      summary: List screening runs
      operationId: listScreeningRuns
      parameters:
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Screening run list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ScreeningRunSummary'

  /queries/screening/{screening_id}:
    get:
      tags: [Queries - Screening]
      summary: Get screening run detail
      operationId: getScreeningRun
      parameters:
        - $ref: '#/components/parameters/ScreeningId'
      responses:
        '200':
          description: Screening run details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScreeningRunDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/screening/{screening_id}/scores:
    get:
      tags: [Queries - Screening]
      summary: Get all candidate scores
      operationId: getScreeningScores
      parameters:
        - $ref: '#/components/parameters/ScreeningId'
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: All screening scores
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ScreeningScore'

  /queries/optimization:
    get:
      tags: [Queries - Optimization]
      summary: List optimization runs
      operationId: listOptimizationRuns
      parameters:
        - name: assumption_id
          in: query
          schema:
            type: string
            format: uuid
        - name: status
          in: query
          schema:
            $ref: '#/components/schemas/OptimizationStatus'
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Optimization run list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OptimizationRunSummary'

  /queries/optimization/{run_id}:
    get:
      tags: [Queries - Optimization]
      summary: Get optimization detail
      operationId: getOptimizationRun
      parameters:
        - $ref: '#/components/parameters/RunId'
      responses:
        '200':
          description: Optimization details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OptimizationRunDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/optimization/{run_id}/weights:
    get:
      tags: [Queries - Optimization]
      summary: Get portfolio weights
      operationId: getOptimizationWeights
      parameters:
        - $ref: '#/components/parameters/RunId'
      responses:
        '200':
          description: Portfolio weights
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/PortfolioWeight'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/optimization/{run_id}/risk:
    get:
      tags: [Queries - Optimization]
      summary: Get risk decomposition
      operationId: getRiskDecomposition
      parameters:
        - $ref: '#/components/parameters/RunId'
      responses:
        '200':
          description: Risk decomposition
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RiskDecomposition'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/drift/{drift_id}:
    get:
      tags: [Queries - Optimization]
      summary: Get drift check detail
      operationId: getDriftCheck
      parameters:
        - $ref: '#/components/parameters/DriftId'
      responses:
        '200':
          description: Drift check details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DriftCheckDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/backtest:
    get:
      tags: [Queries - Backtest]
      summary: List backtest runs
      operationId: listBacktestRuns
      parameters:
        - $ref: '#/components/parameters/Limit'
        - $ref: '#/components/parameters/Offset'
      responses:
        '200':
          description: Backtest run list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/BacktestRunSummary'

  /queries/backtest/{backtest_id}:
    get:
      tags: [Queries - Backtest]
      summary: Get backtest detail
      operationId: getBacktestRun
      parameters:
        - $ref: '#/components/parameters/BacktestId'
      responses:
        '200':
          description: Backtest details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BacktestRunDetail'
        '404':
          $ref: '#/components/responses/NotFoundError'

  /queries/backtest/{backtest_id}/series:
    get:
      tags: [Queries - Backtest]
      summary: Get backtest time series
      operationId: getBacktestSeries
      parameters:
        - $ref: '#/components/parameters/BacktestId'
      responses:
        '200':
          description: Time series data
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/BacktestPoint'

  /queries/scenarios:
    get:
      tags: [Queries - Backtest]
      summary: List scenario definitions
      operationId: listScenarios
      responses:
        '200':
          description: Scenario list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ScenarioDefinition'

  /queries/scenarios/results/{result_id}:
    get:
      tags: [Queries - Backtest]
      summary: Get scenario result
      operationId: getScenarioResult
      parameters:
        - $ref: '#/components/parameters/ResultId'
      responses:
        '200':
          description: Scenario result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScenarioResult'
        '404':
          $ref: '#/components/responses/NotFoundError'

components:
  parameters:
    AssetId:
      name: asset_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    UniverseId:
      name: universe_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    SnapshotId:
      name: snapshot_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    AssumptionId:
      name: assumption_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    ScreeningId:
      name: screening_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    RunId:
      name: run_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    DriftId:
      name: drift_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    BacktestId:
      name: backtest_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    ScenarioId:
      name: scenario_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    ResultId:
      name: result_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
    Limit:
      name: limit
      in: query
      schema:
        type: integer
        default: 50
        maximum: 200
    Offset:
      name: offset
      in: query
      schema:
        type: integer
        default: 0

  responses:
    ValidationError:
      description: Request validation failed
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    NotFoundError:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'
    ConflictError:
      description: Resource conflict
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorResponse'

  schemas:
    # All schemas defined above in the Request/Response Schemas section
    # would be repeated here in full OpenAPI format.
    # For brevity, key schemas are shown; full implementation would include all.
    
    AssetClass:
      type: string
      enum: [equity, fixed_income, commodity, real_estate, cash, crypto, other]
    
    Geography:
      type: string
      enum: [us, developed_ex_us, emerging, global]
    
    Frequency:
      type: string
      enum: [daily, weekly, monthly]
    
    ReturnType:
      type: string
      enum: [simple, log]
    
    Estimator:
      type: string
      enum: [historical, ewma, shrinkage]
    
    CovMethod:
      type: string
      enum: [sample, ledoit_wolf, nearest_psd]
    
    OptimizationStatus:
      type: string
      enum: [SUCCESS, INFEASIBLE, ERROR]
    
    RunType:
      type: string
      enum: [MVP, FRONTIER_POINT, FRONTIER_SERIES, TANGENCY]
    
    Objective:
      type: string
      enum: [MIN_VAR, MAX_SHARPE]
    
    ErrorResponse:
      type: object
      properties:
        error:
          type: object
          properties:
            code:
              type: string
            message:
              type: string
            details:
              type: object
    
    # Additional schemas would follow...
```

---

## Implementation Notes

### CQRS Handler Structure

```
app/
├── commands/
│   ├── __init__.py
│   ├── router.py              # FastAPI router for /commands/*
│   ├── assets.py              # CreateAssetHandler
│   ├── universes.py           # CreateUniverseHandler, AddAssetsHandler
│   ├── holdings.py            # CreateSnapshotHandler
│   ├── ingest.py              # IngestPricesHandler, IngestRiskFreeHandler
│   ├── estimation.py          # ComputeReturnsHandler, CreateAssumptionSetHandler
│   ├── screening.py           # RunScreeningHandler
│   ├── optimization.py        # RunOptimizationHandler
│   └── risk.py                # DriftCheckHandler, BacktestHandler, ScenarioHandlers
├── queries/
│   ├── __init__.py
│   ├── router.py              # FastAPI router for /queries/*
│   ├── assets.py              # ListAssetsQuery, GetAssetQuery
│   ├── universes.py           # ListUniversesQuery, GetUniverseQuery
│   ├── holdings.py            # ListSnapshotsQuery, GetSnapshotQuery
│   ├── market_data.py         # GetPricesQuery, GetReturnsQuery
│   ├── estimation.py          # ListAssumptionsQuery, GetCovarianceQuery
│   ├── screening.py           # ListScreeningQuery, GetScoresQuery
│   ├── optimization.py        # ListRunsQuery, GetWeightsQuery, GetRiskQuery
│   └── backtest.py            # ListBacktestsQuery, GetSeriesQuery
├── domain/
│   ├── models.py              # Domain entities (Asset, Universe, etc.)
│   ├── services/              # Business logic
│   │   ├── estimation.py
│   │   ├── screening.py
│   │   ├── optimization.py
│   │   └── risk.py
│   └── repositories/          # Data access abstractions
│       ├── base.py
│       ├── assets.py
│       └── ...
└── infrastructure/
    ├── database.py            # SQLAlchemy/asyncpg setup
    ├── vendors/               # External API adapters
    │   ├── polygon.py
    │   ├── tiingo.py
    │   └── fred.py
    └── persistence/           # Repository implementations
```

### Dependency Injection

Commands and queries depend on abstractions (repository interfaces), not implementations:

```python
# commands/optimization.py
class RunOptimizationHandler:
    def __init__(
        self,
        assumption_repo: AssumptionRepository,  # Abstract
        optimization_repo: OptimizationRepository,  # Abstract
        optimizer_service: OptimizerService,  # Abstract
    ):
        self._assumptions = assumption_repo
        self._optimizations = optimization_repo
        self._optimizer = optimizer_service
```

This enables:
- Unit testing with mocks
- Swapping implementations (e.g., different solvers)
- Clear boundaries between layers
