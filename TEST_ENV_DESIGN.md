# Test Environment Design and Local Execution Guide

## 1. Overview and Philosophy

This document provides the canonical guide for setting up and running the project's full test suite on a local development machine. The test suite is designed to run in a fully isolated, ephemeral environment orchestrated by Docker Compose to ensure consistency and prevent interference with development data.

**Canonical Test Script:** The single source of truth for running the entire test suite is `scripts/run_tests_with_clean_env.sh`. This script automates the entire process of starting services, running tests, and cleaning up. Manual execution of `pytest` is discouraged as it may not use the correct environment.

**Sandbox Limitations:** Due to sandbox limitations (specifically, lack of Docker daemon permissions), this script cannot be executed directly in the provided evaluation environment. This guide documents the procedure for a local developer machine.

## 2. Prerequisites

*   **Docker and Docker Compose:** You must have a recent version of Docker installed that includes Docker Compose (the `docker compose` command, not the legacy `docker-compose`).
*   **Python:** Python 3.12+ is required.
*   **Virtual Environment:** A Python virtual environment tool like `venv` is strongly recommended.
*   **psql:** The PostgreSQL command-line client must be installed and available in your system's PATH.

## 3. How to Run Tests

The recommended way to run the test suite is to use the provided shell script.

```bash
# From the project root
bash scripts/run_tests_with_clean_env.sh
```

This script will automatically:
1.  Stop and remove any old test containers using `docker-compose.test.yml`.
2.  Start the `test-db` and `test-redis` services.
3.  Wait for the services to be healthy.
4.  Apply the correct database schema for testing.
5.  Run `pytest` with the correct environment variables.
6.  Clean up and shut down all test containers.

## 4. Verifying Database Schema (Alembic Check)

After making changes to the ORM models in `app/models/orm_models.py`, you should verify that your changes are in sync with the database migrations.

### Step 1: Generate a new migration (if you made schema changes)
```bash
# Make sure your test DB is running from Step 3 above
export $(cat .env | xargs) # Load env vars for alembic
alembic revision --autogenerate -m "A descriptive message for your schema change"
```

### Step 2: Run Alembic Check
The `alembic check` command will report an error if the migrations are not in sync with the models. This command should be run against a live, migrated database.

```bash
# First, ensure your test database is up and migrated
# You can use the main docker-compose file for this, as it has a persistent DB
docker-compose up -d db

# Apply all migrations
alembic upgrade head

# Run the check
alembic check
```
If this command returns `No new upgrade operations detected`, your models and migrations are in sync.

## 5. Manual Test Execution (for Debugging)

If you need to run tests manually for debugging purposes, follow these steps. This replicates the process from `scripts/run_tests_with_clean_env.sh`.

### Step 1: Create and Activate Virtual Environment

From the project root directory:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

### Step 2: Install Dependencies

Install the necessary Python packages.

```bash
# Install application and development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 3: Start Test Services

This command starts the test database and Redis containers in the background. It uses the `docker-compose.test.yml` file, which is specifically configured for testing.

```bash
# Ensure any previous test containers are removed
docker compose -f docker-compose.test.yml down -v

# Start the test services in detached mode
docker compose -f docker-compose.test.yml up -d
```

### Step 4: Wait for Services to be Ready

Before running tests, it's crucial to ensure the database and Redis are fully initialized. The test script uses healthchecks. You can manually inspect the status.

```bash
# Check the status of the containers. Wait until 'healthy'.
docker compose -f docker-compose.test.yml ps

# Or, you can manually run the healthcheck commands:
# For PostgreSQL:
docker compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d test_origin_db
# For Redis:
docker compose -f docker-compose.test.yml exec -T test-redis redis-cli ping
```
*Wait until both commands execute successfully before proceeding.*

### Step 5: Set Up Database Schema

The test database needs its schema and tables created. The project includes a SQL script for this purpose.

```bash
# Run the schema setup script
# Note: PGPASSWORD is used to provide the password non-interactively
PGPASSWORD=test_password psql -h localhost -p 5434 -U test_user -d test_origin_db -f scripts/setup_test_schema.sql
```

### Step 6: Run the Test Suite

With the environment set up, you can now run the tests using `pytest`. The script exports several environment variables to configure the application for testing.

```bash
# Export all necessary environment variables for the test run
export DATABASE_URL="postgresql://test_user:test_password@localhost:5434/test_origin_db"
export REDIS_URL="redis://localhost:6380/0"
export CELERY_BROKER_URL="redis://localhost:6380/0"
export CELERY_RESULT_BACKEND="redis://localhost:6380/0"
export DB_ENCRYPTION_KEY="test-encryption-key-32-bytes-long" # A fixed key for reproducible tests
export TESTING="true"
export AUTH_OPTIONAL="true" # Disable authentication for testing purposes

# Set PYTHONPATH so the application modules can be found
export PYTHONPATH=$PWD

# Run pytest
pytest tests/ -v
```

### Step 7: Clean Up

After the test run is complete, shut down the test containers to free up resources.

```bash
# Stop and remove the test containers and their volumes
docker compose -f docker-compose.test.yml down -v
```

## 4. Common Issues and Solutions

*   **Error: `permission denied for docker.sock`**
    *   **Cause:** Your user is not in the `docker` group.
    *   **Solution:** Add your user to the `docker` group (`sudo usermod -aG docker $USER`) and then log out and log back in.
*   **Error: `psql: command not found`**
    *   **Cause:** The PostgreSQL client is not installed or not in your PATH.
    *   **Solution:** Install the `postgresql-client` package using your system's package manager (e.g., `sudo apt-get install postgresql-client` on Debian/Ubuntu).
*   **Tests fail with connection errors:**
    *   **Cause:** You did not wait for the services to become healthy in Step 4.
    *   **Solution:** Stop the services (`docker compose ... down`), restart them, and ensure they are healthy before running `pytest`.
*   **Tests are flaky or fail unexpectedly:**
    *   **Cause:** The database was not cleaned properly. The `TRUNCATE` commands in the original script are intended to prevent this, but if you run tests multiple times without restarting the containers, state can leak.
    *   **Solution:** Always run the full `down -v` and `up -d` cycle for a guaranteed clean environment.
