# Postgres DB Schema v1

## 3.1 Reference Tables

### assets
| Column | Type | Notes |
|---|---|---|
| asset_id | uuid PK | |
| ticker | text UNIQUE | |
| name | text | |
| asset_class | text | Structured: equity / fixed_income / commodity / real_estate / cash / crypto / other |
| sub_class | text | e.g., large_cap_us / em_equity / investment_grade / govt_bond |
| sector | text | GICS sector where applicable (null for non-equity) |
| geography | text | us / developed_ex_us / emerging / global |
| currency | text | ISO 4217 |
| is_etf | bool | |
| created_at | timestamptz | |

> Note: Structured asset_class and geography fields enable sector/geography gap scoring in the screening module. Free-text classification is not permitted.

### universes
| Column | Type | Notes |
|---|---|---|
| universe_id | uuid PK | |
| name | text UNIQUE | |
| description | text | |
| universe_type | text | active / candidate_pool — distinguishes optimization universes from screening pools |
| created_at | timestamptz | |

### universe_assets
| Column | Type | Notes |
|---|---|---|
| universe_id | uuid FK | |
| asset_id | uuid FK | |
| is_benchmark | bool | default false |
| PK | (universe_id, asset_id) | |

### data_vendors
| Column | Type | Notes |
|---|---|---|
| vendor_id | uuid PK | |
| name | text UNIQUE | e.g., Polygon, Tiingo, AlphaVantage, FRED |
| notes | text | |

---

## 3.2 Current Holdings

### current_holdings_snapshots
| Column | Type | Notes |
|---|---|---|
| snapshot_id | uuid PK | |
| label | text | User-defined name, e.g., "My Brokerage Account" |
| snapshot_date | date | Date holdings were recorded |
| created_at | timestamptz | |

### current_holdings_positions
| Column | Type | Notes |
|---|---|---|
| snapshot_id | uuid FK | |
| asset_id | uuid FK | |
| weight | double precision | Normalized weight (must sum to 1 across snapshot) |
| market_value | double precision NULL | Optional dollar value |
| PK | (snapshot_id, asset_id) | |

> Screening uses the most recent snapshot by snapshot_date. If no snapshot exists, screening falls back to a seed universe specified at screening run time.

> **Normalization:** If user provides market values instead of weights, the application layer normalizes to weights at ingest time and stores the result. The sum-to-1 invariant is enforced via application-level validation before insert.

---

## 3.3 Market Data

### price_bars
| Column | Type | Notes |
|---|---|---|
| asset_id | uuid FK | |
| vendor_id | uuid FK | |
| bar_date | date | |
| frequency | text | daily / weekly / monthly |
| adj_close | double precision | |
| close | double precision NULL | Unadjusted close |
| volume | bigint NULL | |
| pulled_at | timestamptz | When this row was fetched — supports audit |
| PK | (asset_id, vendor_id, bar_date, frequency) | |

Indexes: (asset_id, bar_date DESC), (frequency, bar_date DESC)

### risk_free_series
| Column | Type | Notes |
|---|---|---|
| series_id | uuid PK | |
| source | text | e.g., FRED |
| series_code | text | e.g., DTB3 |
| obs_date | date | |
| rf_annual | double precision | Annualized rate |

Index: (obs_date DESC)

---

## 3.4 Derived Returns

### return_series
| Column | Type | Notes |
|---|---|---|
| asset_id | uuid FK | |
| bar_date | date | |
| frequency | text | |
| return_type | text | simple / log |
| ret | double precision | |
| PK | (asset_id, bar_date, frequency, return_type) | |

Index: (asset_id, bar_date DESC)

---

## 3.5 Assumption Sets

### assumption_sets
| Column | Type | Notes |
|---|---|---|
| assumption_id | uuid PK | |
| universe_id | uuid FK | |
| frequency | text | |
| return_type | text | simple / log |
| lookback_start | date | |
| lookback_end | date | |
| annualization_factor | int | e.g., 252 for daily, 12 for monthly |
| rf_annual | double precision | |
| estimator | text | historical / ewma / shrinkage — controls expected return estimation |
| cov_method | text | sample / ledoit_wolf / nearest_psd — controls covariance estimation |
| psd_repair_applied | bool | True if nearest-PSD repair was used |
| psd_repair_note | text NULL | Plain-language reason for repair |
| created_at | timestamptz | |

> **Estimator vs. cov_method:** These are independent choices. `estimator` controls how expected returns (μ) are computed. `cov_method` controls how the covariance matrix (Σ) is computed. For example, `estimator=historical` with `cov_method=ledoit_wolf` uses simple historical mean returns but shrinkage-adjusted covariance.

### assumption_asset_stats
| Column | Type | Notes |
|---|---|---|
| assumption_id | uuid FK | |
| asset_id | uuid FK | |
| mu_annual | double precision | |
| sigma_annual | double precision | |
| PK | (assumption_id, asset_id) | |

### assumption_cov
| Column | Type | Notes |
|---|---|---|
| assumption_id | uuid FK | |
| asset_id_i | uuid FK | |
| asset_id_j | uuid FK | |
| cov_annual | double precision | |
| PK | (assumption_id, asset_id_i, asset_id_j) | |

> Store i ≤ j only; reconstruct symmetry in application layer. When looking up cov(i,j), the application must check for both (i,j) and (j,i) or canonicalize the lookup to min(i,j), max(i,j).

---

## 3.6 Asset Screening

### screening_runs
| Column | Type | Notes |
|---|---|---|
| screening_id | uuid PK | |
| assumption_id | uuid FK | Covariance/return data used for scoring |
| candidate_pool_id | uuid FK | References universe where universe_type = candidate_pool |
| reference_type | text | current_holdings / seed_universe |
| reference_snapshot_id | uuid FK NULL | FK to current_holdings_snapshots if reference_type = current_holdings |
| reference_universe_id | uuid FK NULL | FK to universes if reference_type = seed_universe |
| nominal_add_weight | double precision | Weight assumed when computing marginal vol reduction (default 0.05) |
| score_weights | jsonb | e.g., {"correlation": 0.4, "marginal_vol": 0.3, "sector_gap": 0.15, "hhi": 0.15} |
| created_at | timestamptz | |

> **Constraint:** Application layer (or CHECK constraint) must enforce that exactly one of reference_snapshot_id or reference_universe_id is non-null, matching reference_type:
> - If reference_type = 'current_holdings', then reference_snapshot_id IS NOT NULL AND reference_universe_id IS NULL
> - If reference_type = 'seed_universe', then reference_universe_id IS NOT NULL AND reference_snapshot_id IS NULL

### screening_scores
| Column | Type | Notes |
|---|---|---|
| screening_id | uuid FK | |
| asset_id | uuid FK | |
| avg_pairwise_corr | double precision | Average correlation of candidate to all reference holdings |
| marginal_vol_reduction | double precision | Reduction in σp if added at nominal_add_weight |
| sector_gap_score | double precision | 0–1; 1 = fills a completely absent asset class/sector |
| hhi_reduction | double precision | Reduction in HHI if added at nominal_add_weight |
| composite_score | double precision | Weighted composite; higher = better diversifier |
| rank | int | 1 = best candidate |
| explanation | text | Plain-language explanation for this candidate's score |
| PK | (screening_id, asset_id) | |

---

## 3.7 Optimization

### optimization_runs
| Column | Type | Notes |
|---|---|---|
| run_id | uuid PK | |
| assumption_id | uuid FK | |
| run_type | text | MVP / FRONTIER_POINT / FRONTIER_SERIES / TANGENCY |
| objective | text | MIN_VAR / MAX_SHARPE |
| constraints | jsonb | long_only, bounds, leverage_cap, concentration_cap, turnover_cap, etc. |
| reference_snapshot_id | uuid FK NULL | Current holdings used for turnover constraint if provided |
| target_return | double precision NULL | For FRONTIER_POINT runs |
| status | text | SUCCESS / INFEASIBLE / ERROR |
| infeasibility_reason | text NULL | Plain-language explanation when status ≠ SUCCESS |
| solver_meta | jsonb NULL | Iterations, solver message, solve time |
| created_at | timestamptz | |

> **Turnover constraint behavior:** If constraints includes turnover_cap but reference_snapshot_id is NULL, the system checks for a previous optimization run for the same universe. If none exists, the turnover constraint is ignored and a warning is logged.

### optimization_results
| Column | Type | Notes |
|---|---|---|
| run_id | uuid PK FK | |
| exp_return | double precision | |
| variance | double precision | |
| stdev | double precision | |
| sharpe | double precision NULL | |
| hhi | double precision | |
| effective_n | double precision | |
| explanation | text | Plain-language portfolio summary |

### optimization_weights
| Column | Type | Notes |
|---|---|---|
| run_id | uuid FK | |
| asset_id | uuid FK | |
| weight | double precision | |
| mcr | double precision | Marginal contribution to risk |
| crc | double precision | Component contribution to risk |
| prc | double precision | Percent risk contribution |
| PK | (run_id, asset_id) | |

> MCR/CRC/PRC stored per-weight row so risk decomposition is always retrievable without recomputing.

---

## 3.8 Risk Analytics

### scenario_definitions
| Column | Type | Notes |
|---|---|---|
| scenario_id | uuid PK | |
| name | text | e.g., "Equity Crash -30%", "Rate Spike +200bps" |
| shocks | jsonb | e.g., {"equity": -0.30, "duration": 2.0, "inflation": 0.03} |
| created_at | timestamptz | |

### scenario_results
| Column | Type | Notes |
|---|---|---|
| result_id | uuid PK | |
| run_id | uuid FK | Optimization run this was evaluated against |
| scenario_id | uuid FK | |
| shocked_return | double precision | Estimated portfolio return under scenario |
| shocked_vol | double precision NULL | If recomputed under shocked covariance |
| created_at | timestamptz | |

---

## 3.9 Backtesting

### backtest_runs
| Column | Type | Notes |
|---|---|---|
| backtest_id | uuid PK | |
| universe_id | uuid FK | |
| benchmark_asset_id | uuid FK NULL | Asset used as benchmark (e.g., SPY) |
| strategy | text | TANGENCY_REBAL / MVP_REBAL / EW_REBAL / etc. |
| rebal_freq | text | monthly / quarterly / threshold |
| rebal_threshold | double precision NULL | Max drift before threshold rebalance triggers |
| window_length | int | Lookback in periods |
| transaction_cost_bps | double precision | Cost per unit turnover in basis points |
| constraints | jsonb | |
| survivorship_bias_note | text | Always populated: documents known limitation |
| created_at | timestamptz | |

### backtest_points
| Column | Type | Notes |
|---|---|---|
| backtest_id | uuid FK | |
| obs_date | date | |
| portfolio_value | double precision | |
| portfolio_ret | double precision | Gross period return |
| portfolio_ret_net | double precision | Net of transaction costs |
| benchmark_ret | double precision NULL | Benchmark return same period |
| active_ret | double precision NULL | portfolio_ret_net − benchmark_ret |
| turnover | double precision | Turnover on this date; 0.0 on non-rebalance dates |
| drawdown | double precision | Running drawdown at this date |
| PK | (backtest_id, obs_date) | |

> **Turnover:** Stored as 0.0 on non-rebalance dates (not NULL) to simplify aggregation queries like SUM(turnover) without requiring COALESCE.

### backtest_summary
| Column | Type | Notes |
|---|---|---|
| backtest_id | uuid PK FK | |
| total_return | double precision | |
| annualized_return | double precision | |
| annualized_vol | double precision | |
| sharpe | double precision | |
| max_drawdown | double precision | |
| var_95 | double precision | |
| cvar_95 | double precision | |
| avg_turnover | double precision | Average turnover per rebalance |
| tracking_error | double precision NULL | |
| information_ratio | double precision NULL | |

---

## 3.10 Drift Detection

### drift_checks
| Column | Type | Notes |
|---|---|---|
| drift_id | uuid PK | |
| run_id | uuid FK | Optimization run defining the target weights |
| check_date | date | Date prices were pulled to compute current implied weights |
| threshold_pct | double precision | Alert threshold (default 0.05 = 5% absolute) |
| any_breach | bool | True if any asset breached threshold |
| created_at | timestamptz | |

### drift_check_positions
| Column | Type | Notes |
|---|---|---|
| drift_id | uuid FK | |
| asset_id | uuid FK | |
| target_weight | double precision | From optimization run |
| current_weight | double precision | Implied by updated prices |
| drift_abs | double precision | |current − target| |
| breached | bool | |
| explanation | text | Plain-language alert; required (NOT NULL) when breached = true, NULL otherwise |
| PK | (drift_id, asset_id) | |

> **Explanation constraint:** Application layer must enforce that explanation IS NOT NULL when breached = true.