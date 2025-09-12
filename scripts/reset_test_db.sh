#!/bin/bash

# Reset test database to clean state
echo "Resetting test database..."

# Connect to test database and truncate all tables
docker exec app-test-db-1 psql -U test_user -d test_origin_db -c "
SET session_replication_role = replica;
TRUNCATE TABLE rooms, messages, memories, reviews, conversation_threads, user_profiles, conversation_messages, attachments, export_jobs, review_metrics RESTART IDENTITY CASCADE;
SET session_replication_role = DEFAULT;
"

echo "Test database reset complete!"
