# Sandwich Scan

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
