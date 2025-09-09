#!/bin/bash

# Test Environment Setup Script
echo "🧪 Setting up test environment..."

# Stop any existing test containers
echo "🛑 Stopping existing test containers..."
docker-compose -f docker-compose.test.yml down -v

# Start test containers
echo "🚀 Starting test containers..."
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if test database is ready
echo "🔍 Checking test database connection..."
until docker-compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d test_origin_db; do
  echo "Waiting for test database..."
  sleep 2
done

# Check if test Redis is ready
echo "🔍 Checking test Redis connection..."
until docker-compose -f docker-compose.test.yml exec -T test-redis redis-cli ping; do
  echo "Waiting for test Redis..."
  sleep 2
done

# Setup test database schema
echo "🗄️ Setting up test database schema..."
PGPASSWORD=test_password psql -h localhost -p 5434 -U test_user -d test_origin_db -f scripts/setup_test_schema.sql

# Clear any existing test data
echo "🧹 Clearing existing test data..."
PGPASSWORD=test_password psql -h localhost -p 5434 -U test_user -d test_origin_db -c "
-- Disable foreign key checks temporarily
SET session_replication_role = replica;

-- Clear all tables
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

-- Re-enable foreign key checks
SET session_replication_role = DEFAULT;

-- Reset sequences if any
SELECT setval(pg_get_serial_sequence('rooms', 'room_id'), 1, false);
"

echo "✅ Test environment is ready!"

# Run tests with clean environment
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

# Activate virtual environment and run tests
source .venv/bin/activate
export PYTHONPATH=$PWD
pytest tests/ -v

# Cleanup
echo "🧹 Cleaning up test environment..."
docker-compose -f docker-compose.test.yml down -v

echo "✅ Test run completed!"
