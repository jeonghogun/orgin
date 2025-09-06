#!/bin/bash

# Run tests with proper environment setup
echo "Setting up test environment..."

# Reset test database
echo "Resetting test database..."
./scripts/reset_test_db.sh

# Activate virtual environment and run tests
echo "Running tests..."
source .venv/bin/activate
export PYTHONPATH=$PWD
export DATABASE_URL="postgresql://user:password@localhost:5433/test_origin_db"

# Run the tests passed as arguments, or all tests if no arguments
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    pytest
else
    echo "Running specific tests: $@"
    pytest "$@"
fi

echo "Test run complete!"
