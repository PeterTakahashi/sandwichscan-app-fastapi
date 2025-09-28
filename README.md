# SandwichScan React frontend

Provide a visualization tool for sandwich attacks

## Goal

Build a simple, trustworthy, and open visualization tool that lets anyone:

- Inspect total and per-attacker metrics (revenues, profits, number of attacks).
- Inspect total harm to victims.
- Search and filter attacks by victim or attacker address.
- Sort results by timestamp, revenue, profit, or harm.
- See interactive charts of attacker revenue/profit vs victim harm.
- Access public API docs and call the API (historic window: from 2020).
- Source: swap & transaction logs from Ethereum via GCP BigQuery (only Uniswap V2, Sushiswap V2, PancakeSwap V2 are used for detection).

## Links

sandwichscan app  
https://app.sandwichscan.baltoon.jp

sandwichscan api docs  
https://api.sandwichscan.baltoon.jp/app/v1/scalar

docs repository  
https://github.com/PeterTakahashi/sandwich-scan-docs

fastapi backend api repository  
https://github.com/PeterTakahashi/sandwichscan-app-fastapi

react frontend repository  
https://github.com/PeterTakahashi/sandwichscan-app-react

## Definition / detection rule

A sandwich attack is detected when:

1. There is a _victim swap_.
2. Within one block before or after the victim’s swap, there are swaps from the _attacker_.
3. The attacker’s front-run swap is in the **same direction** as the victim’s swap.

## Data source & scope

- Source: Raw swaps + transactions in **Ethereum** collected by GCP BigQuery.
- Pools scanned: Uniswap v2, Sushiswap v2, PancakeSwap v2.
- Time range: since 2020.
- Only swaps on the Ethereum chain are considered.

## get start

```
docker exec -it sandwichscan-web bash
source .venv/bin/activate
alembic upgrade head
ENV=test alembic upgrade head # For test environment
exit # Exit the container
```

## Local Development

### Docker Commands

- **Access the backend web container:**
  ```bash
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  ```
- **Stop and remove all services, including volumes (for a clean slate):**
  ```bash
  docker compose down -v
  ```

### Database Management

- **Reset Database (clean slate):**
  ```bash
  docker compose down -v
  docker compose up -d
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  alembic revision --autogenerate -m "init" # Only if starting from scratch or major schema change
  alembic upgrade head
  ENV=test alembic upgrade head # For test environment
  python -m app.db.seed
  exit
  ```
- **Create new database migration file:**
  ```bash
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  alembic revision --autogenerate -m "Your migration message here"
  alembic upgrade head
  ```
- **Apply database migrations:**
  ```bash
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  alembic upgrade head
  ENV=test alembic upgrade head # For test environment
  ```
- **Generate schema and repository files:**

  ```bash
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  python -m scripts.create_schema
  ```

- **Create repository files from model files automatically:**

```bash
  docker exec -it sandwichscan-web bash
  source .venv/bin/activate
  python scripts/generate_repositories_from_models.py
  python scripts/generate_repository_dependencies.py
  python scripts/generate_repository_fixtures.py
```

### Code Quality

- **Run tests and generate coverage report:**
  ```bash
  docker exec -it service-base-web bash
  source .venv/bin/activate
  pytest --cov=app --cov-report=term-missing --cov-report=html
  open htmlcov/index.html # Open coverage report in browser (if on macOS)
  ```
- **Format code with Black and Ruff:**
  ```bash
  black .
  ruff check . --fix
  ```
- **Check code with Ruff and MyPy:**
  ```bash
  ruff check .
  mypy --config-file mypy.ini .
  ```

### insert blockchain data from bigquery

```sh
python -m app.db.services.backfill_from_bigquery
```

```sh
python -m app.db.services.backfill_transactions_uniswap_from_bigquery
```

### sql dump

```sh
docker exec -t sandwichscan-db pg_dump -U postgres -d sandwichscan_dev > dump.sql
```
