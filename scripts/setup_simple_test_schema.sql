-- Simple Test Database Schema Setup
-- This script creates all necessary tables for testing without vector extensions

-- Enable required extensions (skip vector for now)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create rooms table
CREATE TABLE IF NOT EXISTS rooms (
    room_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_id VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    parent_id VARCHAR(255) REFERENCES rooms(room_id),
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
);

-- Create messages table (without vector for now)
CREATE TABLE IF NOT EXISTS messages (
    message_id VARCHAR(255) PRIMARY KEY,
    room_id VARCHAR(255) NOT NULL REFERENCES rooms(room_id),
    user_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    timestamp BIGINT NOT NULL,
    content BYTEA NOT NULL,
    content_searchable TEXT NOT NULL,
    ts TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(content_searchable, ''))) STORED
);

-- Create memories table (without vector for now)
CREATE TABLE IF NOT EXISTS memories (
    memory_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    room_id VARCHAR(255) NOT NULL REFERENCES rooms(room_id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    importance DOUBLE PRECISION DEFAULT 1.0,
    expires_at BIGINT,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id VARCHAR(255) PRIMARY KEY,
    room_id VARCHAR(255) NOT NULL REFERENCES rooms(room_id),
    topic TEXT NOT NULL,
    instruction TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    total_rounds INTEGER NOT NULL DEFAULT 3,
    current_round INTEGER NOT NULL DEFAULT 0,
    created_at BIGINT NOT NULL,
    completed_at BIGINT,
    final_report JSONB
);

-- Create conversation_threads table
CREATE TABLE IF NOT EXISTS conversation_threads (
    id VARCHAR(255) PRIMARY KEY,
    sub_room_id VARCHAR(255) NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    title VARCHAR(500),
    pinned BOOLEAN DEFAULT FALSE,
    archived BOOLEAN DEFAULT FALSE,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

-- Create user_profiles table
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id VARCHAR(255) PRIMARY KEY,
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    name BYTEA,
    preferences BYTEA,
    conversation_style VARCHAR(255) DEFAULT 'casual',
    interests TEXT[] NOT NULL DEFAULT '{}',
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    auto_fact_extraction_enabled BOOLEAN NOT NULL DEFAULT TRUE
);

-- Create conversation_messages table (without vector for now)
CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content BYTEA NOT NULL,
    content_searchable TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    meta TEXT,
    ts TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(content_searchable, ''))) STORED
);

-- Create attachments table
CREATE TABLE IF NOT EXISTS attachments (
    attachment_id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    created_at BIGINT NOT NULL
);

-- Create export_jobs table for async export flow
CREATE TABLE IF NOT EXISTS export_jobs (
    id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    format VARCHAR(20) NOT NULL,
    status VARCHAR(50) NOT NULL,
    file_url TEXT,
    error_message TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

-- Create review_metrics table
CREATE TABLE IF NOT EXISTS review_metrics (
    review_id VARCHAR(255) PRIMARY KEY,
    total_duration_seconds DECIMAL(10,2),
    total_tokens_used INTEGER,
    total_cost_usd DECIMAL(10,6),
    round_metrics JSONB,
    created_at BIGINT NOT NULL
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_rooms_owner_id ON rooms(owner_id);
CREATE INDEX IF NOT EXISTS idx_rooms_parent_id ON rooms(parent_id);
CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_messages_room_id_timestamp ON messages(room_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages USING gin(ts);
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_room_id ON reviews(room_id);
CREATE INDEX IF NOT EXISTS idx_conversation_threads_sub_room_id ON conversation_threads(sub_room_id);
CREATE INDEX IF NOT EXISTS idx_conversation_threads_created_at ON conversation_threads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_threads_pinned_archived ON conversation_threads(pinned, archived);
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread_id ON conversation_messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_ts ON conversation_messages USING gin(ts);
CREATE INDEX IF NOT EXISTS idx_attachments_thread_id ON attachments(thread_id);
CREATE INDEX IF NOT EXISTS idx_export_jobs_thread_id ON export_jobs(thread_id);
