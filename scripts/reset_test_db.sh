#!/bin/bash

# Reset test database to clean state
echo "Resetting test database..."

# Connect to test database and truncate all tables
docker exec orgin-test-db-1 psql -U user -d test_origin_db -c "
SET session_replication_role = replica;
TRUNCATE TABLE conversation_contexts, review_events, reviews, messages, memories, user_facts, rooms, user_profiles RESTART IDENTITY CASCADE;
SET session_replication_role = DEFAULT;
"

echo "Test database reset complete!"
