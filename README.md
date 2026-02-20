# Portfolio Optimizer & Risk Analyzer

A portfolio construction, optimization, and risk analysis engine. Implements mean-variance optimization, asset screening, drift detection, backtesting, and scenario analysis behind a CQRS REST API with a Streamlit front-end.

> **Status:** In active development. Domain layer complete. Infrastructure and API layers in progress.

---

## Prerequisites

- Python 3.11+
- Docker (for Postgres)

---

## Environment Setup

Before running anything, copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# Postgres — must match the values in docker-compose.yml
DB_USER=optimizer
DB_PASSWORD=optimizer
DB_NAME=optimizer

# Full async connection string used by the application
DATABASE_URL=postgresql+asyncpg://optimizer:optimizer@localhost:5433/optimizer

# Data vendor API keys (required when data ingestion is implemented)
POLYGON_API_KEY=
TIINGO_API_KEY=
FRED_API_KEY=
```

> **Note:** `.env` is gitignored and must never be committed. The Postgres defaults in `docker-compose.yml` are `optimizer / optimizer / optimizer` on port `5433`.

---

## Local Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # WSL / Linux / macOS
# .venv\Scripts\activate         # Windows

# Install runtime + dev dependencies
pip install -e ".[dev]"
```

---

## Database

```bash
# Start Postgres
docker compose up db -d

# Apply all migrations
alembic upgrade head

# Verify all 24 tables were created
docker compose exec db psql -U optimizer -d optimizer -c "\dt"

# Spot-check a specific table's columns and constraints
docker compose exec db psql -U optimizer -d optimizer -c "\d screening_runs"

# Tear down (removes the Postgres volume too)
docker compose down -v
```

---

## Testing

Tests live in `/tests` and are split into `unit/` and `integration/`.

```bash
# Run all tests
python -m pytest

# With coverage report in terminal
python -m pytest --cov=src --cov-report=term-missing

# With HTML coverage report
python -m pytest --cov=src --cov-report=html
```

---

## What's Built

### Domain Layer — `src/domain/`

**Models** (`src/domain/models/`) — Pure Pydantic domain objects with no ORM dependencies.

| Module | Types |
|---|---|
| `enums.py` | `AssetClass`, `Geography`, `UniverseType`, `Frequency`, `ReturnType`, `Estimator`, `CovMethod`, `OptimizationStatus`, `RunType`, `Objective`, `ReferenceType`, `BacktestStrategy`, `RebalFrequency` |
| `assets.py` | `Asset`, `Universe`, `UniverseAsset` |
| `market_data.py` | `PriceBar`, `ReturnPoint` |
| `holdings.py` | `HoldingsSnapshot`, `HoldingsPosition` |
| `assumptions.py` | `AssumptionSet`, `AssetStats`, `CovarianceEntry`, `CovarianceMatrix`, `CorrelationEntry`, `CorrelationMatrix` |
| `screening.py` | `ScreeningRun`, `ScreeningScore`, `ScreeningConfig`, `ScoreWeights` |
| `optimization.py` | `OptimizationRun`, `OptimizationResult`, `OptimizationConstraints`, `PortfolioWeight`, `RiskDecomposition`, `AssetBound` |
| `drift.py` | `DriftCheck`, `DriftPosition` |
| `backtest.py` | `BacktestRun`, `BacktestConfig`, `BacktestPoint`, `BacktestSummary` |
| `scenarios.py` | `ScenarioDefinition`, `ScenarioResult` |

**Repository Interfaces** (`src/domain/repositories/`) — Abstract data-access contracts (`ABC` + `@abstractmethod`). Return domain models, not ORM objects. Concrete implementations go in `src/infrastructure/persistence/`.

| Interface | Key methods |
|---|---|
| `AssetRepository` | `get_by_id`, `get_by_ticker`, `list`, `create` |
| `UniverseRepository` | `get_by_id`, `list`, `create`, `add_assets`, `remove_assets` |
| `HoldingsRepository` | `get_by_id`, `get_latest`, `list`, `create` |
| `PriceRepository` | `get_prices`, `get_latest_date`, `bulk_insert` |
| `ReturnRepository` | `get_returns`, `bulk_insert` |
| `AssumptionRepository` | `get_by_id`, `list`, `create`, `get_covariance_matrix`, `get_correlation_matrix` |
| `ScreeningRepository` | `get_by_id`, `list`, `create`, `get_scores` |
| `OptimizationRepository` | `get_by_id`, `list`, `create`, `get_weights`, `get_latest_for_universe` |
| `DriftRepository` | `get_by_id`, `create`, `get_positions` |
| `BacktestRepository` | `get_by_id`, `list`, `create`, `get_points`, `get_summary` |
| `ScenarioRepository` | `get_by_id`, `list`, `create_definition`, `create_result`, `get_result` |

### Database Schema — `alembic/`

24-table Postgres schema covering all five data layers: reference, market data, estimation, portfolio, and simulation. See `docs/DB-SCHEMA.md` and `docs/ER-DIAGRAM.md` for full detail.

---

## Project Structure

```
src/
├── domain/
│   ├── models/          # Entities and value objects (Pydantic, frozen)
│   └── repositories/    # Abstract data-access interfaces (ABC)
├── infrastructure/
│   ├── persistence/     # SQLAlchemy repository implementations (in progress)
│   └── vendors/         # External API adapters: Polygon, Tiingo, FRED (in progress)
└── main.py              # FastAPI application entry point (in progress)

ui/                      # Streamlit front-end (in progress)
tests/
├── unit/
│   └── domain/          # Domain model and repository interface tests
└── integration/         # DB-backed integration tests (in progress)
docs/                    # Specifications: requirements, schema, API contract, UI spec
alembic/                 # Database migrations
```

---

## Key Design Decisions

- **CQRS** — Commands (`/commands/*`) mutate state; Queries (`/queries/*`) are read-only.
- **Repository pattern** — All data access goes through abstract interfaces injected at the application boundary. Handlers never touch SQLAlchemy directly.
- **Immutable domain models** — All domain objects are frozen Pydantic models. No in-place mutation.
- **Async throughout** — `asyncpg` + SQLAlchemy async for non-blocking database access.
- **Covariance storage** — Upper triangle only (`asset_id_i ≤ asset_id_j`). Symmetry reconstructed at read time.
