#!/bin/bash

set -euo pipefail

echo "🧪 Setting up test environment..."

if ! command -v docker-compose >/dev/null 2>&1; then
  echo "❌ docker-compose is required to run the test environment" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "❌ psql (PostgreSQL client) is required" >&2
  exit 1
fi

cleanup() {
  echo "🧹 Cleaning up test environment..."
  docker-compose -f docker-compose.test.yml down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "🛑 Stopping existing test containers..."
docker-compose -f docker-compose.test.yml down -v >/dev/null 2>&1 || true

echo "🚀 Starting test containers..."
docker-compose -f docker-compose.test.yml up -d

echo "⏳ Waiting for services to be ready..."
sleep 5

echo "🔍 Checking test database connection..."
until docker-compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d test_origin_db >/dev/null 2>&1; do
  echo "Waiting for test database..."
  sleep 2
done

echo "🔍 Checking test Redis connection..."
until docker-compose -f docker-compose.test.yml exec -T test-redis redis-cli ping >/dev/null 2>&1; do
  echo "Waiting for test Redis..."
  sleep 2
done

echo "🧱 Ensuring local virtual environment..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

echo "🗄️ Setting up test database schema..."
PGPASSWORD=test_password psql -h localhost -p 5434 -U test_user -d test_origin_db -f scripts/setup_test_schema.sql

echo "🧹 Clearing existing test data..."
PGPASSWORD=test_password psql -h localhost -p 5434 -U test_user -d test_origin_db -c "
SET session_replication_role = replica;
TRUNCATE TABLE
  attachments,
  conversation_messages,
  conversation_threads,
  user_profiles,
  reviews,
  memories,
  messages,
  rooms
CASCADE;
SET session_replication_role = DEFAULT;
SELECT setval(pg_get_serial_sequence('rooms', 'room_id'), 1, false);
"

echo "✅ Test environment is ready!"

echo "🧪 Running tests..."
export DATABASE_URL="postgresql://test_user:test_password@localhost:5434/test_origin_db"
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5434"
export POSTGRES_USER="test_user"
export POSTGRES_PASSWORD="test_password"
export POSTGRES_DB="test_origin_db"
export REDIS_URL="redis://localhost:6380/0"
export CELERY_BROKER_URL="redis://localhost:6380/0"
export CELERY_RESULT_BACKEND="redis://localhost:6380/0"
export DB_ENCRYPTION_KEY="test-encryption-key-32-bytes-long"
export TESTING="true"
export PYTHONPATH=$PWD

pytest tests/ -v

echo "✅ Test run completed!"
