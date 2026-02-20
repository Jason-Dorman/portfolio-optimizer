# Portfolio Optimizer & Rebalancer

This project is in development.

## Requirements

1. Docker

## Getting Started 

### Create the virtual environment
`python -m venv .venv`

### Activate it (Windows)
`.venv\Scripts\activate`

### Activate it (WSL/Linux)
`source .venv/bin/activate`

### Install runtime + dev dependencies
`pip install -e ".[dev]"`

## Testing

Integration and unit tests are located in the **/tests** directory. 

To run tests:

`python -m pytest`

To run tests and generate code coverage reports:

`python -m pytest --cov=. --cov-report=term-missing`
`python -m pytest --cov=. --cov-report=html`

## Database

To start the Postgres db
`docker compose up db -d`

Run the migration
`alembic upgrade head`

Then verify every table was created:
`docker compose exec db psql -U optimizer -d optimizer -c "\dt"`

You should see all 24 tables listed. To spot-check a specific table's columns and constraints:

`docker compose exec db psql -U optimizer -d optimizer -c "\d screening_runs"`

That will show the columns, types, and — importantly — confirm the `ck_screening_runs_reference_consistency` CHECK constraint is present.

To tear it back down:

`docker compose down -v  # -v removes the postgres volume too`