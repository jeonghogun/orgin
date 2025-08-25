-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Rooms Table
CREATE TABLE rooms (
    room_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    owner_id VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    parent_id VARCHAR(255),
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    message_count INT DEFAULT 0,
    -- Foreign key to parent room
    FOREIGN KEY (parent_id) REFERENCES rooms(room_id) ON DELETE CASCADE
);

-- Messages Table
CREATE TABLE messages (
    message_id VARCHAR(255) PRIMARY KEY,
    room_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    -- Embedding vector for semantic search
    embedding vector(1536), -- Assuming OpenAI's ada-002 embedding size
    FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
);

-- Reviews Table
CREATE TABLE reviews (
    review_id VARCHAR(255) PRIMARY KEY,
    room_id VARCHAR(255) NOT NULL,
    topic TEXT NOT NULL,
    instruction TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    total_rounds INT NOT NULL,
    current_round INT NOT NULL,
    created_at BIGINT NOT NULL,
    completed_at BIGINT,
    final_report JSONB,
    FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
);

-- Review Events Table
CREATE TABLE review_events (
    event_id SERIAL PRIMARY KEY,
    review_id VARCHAR(255) NOT NULL,
    ts BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    round INT,
    actor VARCHAR(255),
    content TEXT,
    FOREIGN KEY (review_id) REFERENCES reviews(review_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_rooms_owner_id ON rooms(owner_id);
CREATE INDEX idx_messages_room_id ON messages(room_id);
CREATE INDEX idx_reviews_room_id ON reviews(room_id);
CREATE INDEX idx_review_events_review_id ON review_events(review_id);
-- IVFFlat index for vector search on messages
CREATE INDEX idx_messages_embedding ON messages USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
