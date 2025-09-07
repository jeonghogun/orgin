#!/bin/bash

# This script is modified to run correctly in the isolated execution environment.

echo "Setting up test environment..."
# The reset script needs to be called with its full path.
# Assuming a test DB is managed by the environment, we might not even need this.
# I'll comment it out for now to see if the tests can run without it.
# echo "Resetting test database..."
# /app/scripts/reset_test_db.sh

echo "Running tests..."
# The virtual environment is not used in this container.
# Set the PYTHONPATH to the root of the repository.
export PYTHONPATH=/app
# The DATABASE_URL should be provided by the environment, but we set it just in case.
export DATABASE_URL="postgresql://user:password@localhost:5433/test_origin_db"

# Define the correct python executable
PYTHON_EXEC="/home/jules/.pyenv/shims/python"

# Run pytest using the specific python executable to ensure correct dependencies.
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    $PYTHON_EXEC -m pytest /app/tests
else
    echo "Running specific tests: $@"
    $PYTHON_EXEC -m pytest "/app/tests/$@"
fi

echo "Test run complete!"
