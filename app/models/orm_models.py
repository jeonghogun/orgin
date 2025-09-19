"""
SQLAlchemy ORM Models.
These models are primarily for Alembic's auto-generation capabilities
and to provide a Python-native representation of the DB schema.
The application services may use raw SQL for performance, but these
models should be kept in sync with the DDL in migrations.

LAST UPDATED: 2025-09-14 - Jules (AI) to resolve schema inconsistencies.
"""
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    func,
    BigInteger,
    Float,
    LargeBinary
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID, ARRAY
from sqlalchemy import Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# --- Core Tables from Initial Schema ---

class Room(Base):
    __tablename__ = 'rooms'
    room_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    owner_id = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    parent_id = Column(String(255), ForeignKey('rooms.room_id', ondelete='CASCADE'))
    # NOTE: The initial migration used BIGINT for timestamps. The application logic seems to handle this.
    # Using DateTime with timezone=True for better SQLAlchemy semantics.
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    message_count = Column(Integer, nullable=False, server_default='0')

    # Relationships from existing models
    parent = relationship('Room', remote_side=[room_id], back_populates='children')
    children = relationship('Room', back_populates='parent')
    conversation_threads = relationship('ConversationThread', back_populates='sub_room')
    memories = relationship('Memory', back_populates='room', cascade="all, delete-orphan")
    messages = relationship('Message', back_populates='room', cascade="all, delete-orphan")
    reviews = relationship('Review', back_populates='room', cascade="all, delete-orphan")
    conversation_contexts = relationship('ConversationContext', back_populates='room', cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = 'messages'
    message_id = Column(String(255), primary_key=True)
    room_id = Column(String(255), ForeignKey('rooms.room_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    # The 'content' column is encrypted binary data
    content = Column(LargeBinary, nullable=False)
    # The 'content_searchable' column holds the plaintext for FTS
    content_searchable = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    embedding = Column(Text, nullable=True)  # VECTOR(1536) 대신 Text 사용
    ts = Column(TSVECTOR, nullable=True)

    room = relationship('Room', back_populates='messages')


class Memory(Base):
    __tablename__ = 'memories'
    memory_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    room_id = Column(String(255), ForeignKey('rooms.room_id', ondelete='CASCADE'), nullable=False, index=True)
    key = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)  # VECTOR(1536) 대신 Text 사용
    importance = Column(Float, nullable=True, server_default='1.0')
    expires_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)

    room = relationship('Room', back_populates='memories')


class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id = Column(String(255), primary_key=True)
    role = Column(String(50), nullable=False, server_default='user')
    name = Column(LargeBinary, nullable=True)
    preferences = Column(LargeBinary, nullable=True)
    conversation_style = Column(String(255), nullable=True, server_default='casual')
    interests = Column(ARRAY(Text), nullable=False, server_default='{}')
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    auto_fact_extraction_enabled = Column(Boolean, nullable=False, server_default='true')


class ConversationContext(Base):
    __tablename__ = 'conversation_contexts'
    context_id = Column(String(255), primary_key=True)
    room_id = Column(String(255), ForeignKey('rooms.room_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    key_topics = Column(ARRAY(Text), nullable=True)
    sentiment = Column(String(50), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    room = relationship('Room', back_populates='conversation_contexts')


class Review(Base):
    __tablename__ = 'reviews'
    review_id = Column(String(255), primary_key=True)
    room_id = Column(String(255), ForeignKey('rooms.room_id', ondelete='CASCADE'), nullable=False, index=True)
    topic = Column(Text, nullable=False)
    instruction = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    total_rounds = Column(Integer, nullable=False)
    current_round = Column(Integer, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    completed_at = Column(BigInteger, nullable=True)
    final_report = Column(JSONB, nullable=True)

    room = relationship('Room', back_populates='reviews')
    events = relationship('ReviewEvent', back_populates='review', cascade="all, delete-orphan")
    metrics = relationship('ReviewMetric', uselist=False, back_populates='review', cascade="all, delete-orphan")
    panel_reports = relationship('PanelReport', back_populates='review', cascade="all, delete-orphan")
    consolidated_reports = relationship('ConsolidatedReport', back_populates='review', cascade="all, delete-orphan")


class ReviewEvent(Base):
    __tablename__ = 'review_events'
    event_id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String(255), ForeignKey('reviews.review_id', ondelete='CASCADE'), nullable=False, index=True)
    ts = Column(BigInteger, nullable=False)
    type = Column(String(50), nullable=False)
    round = Column(Integer, nullable=True)
    actor = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)

    review = relationship('Review', back_populates='events')

class ReviewMetric(Base):
    __tablename__ = 'review_metrics'
    review_id = Column(String(255), ForeignKey('reviews.review_id', ondelete='CASCADE'), primary_key=True)
    total_duration_seconds = Column(Float, nullable=False)
    total_tokens_used = Column(Integer, nullable=False)
    total_cost_usd = Column(Float, nullable=False)
    round_metrics = Column(JSONB, nullable=True)
    created_at = Column(BigInteger, nullable=False)

    review = relationship('Review', back_populates='metrics')


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False, index=True)
    admin_user_id = Column(String(255), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    details = Column(JSONB, nullable=True)
    trace_id = Column(String(255), nullable=True)


class KpiSnapshot(Base):
    __tablename__ = 'kpi_snapshots'
    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    details = Column(JSONB, nullable=True)


class ProviderConfig(Base):
    __tablename__ = 'provider_configs'
    provider_name = Column(String(100), primary_key=True)
    model = Column(String(100), nullable=False)
    timeout_ms = Column(Integer, nullable=False)
    retries = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, server_default='true')
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key = Column(String(100), primary_key=True)
    value_json = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --- Tables from Report Tables Migration ---

class PanelReport(Base):
    __tablename__ = 'panel_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String(255), ForeignKey('reviews.review_id', ondelete='CASCADE'), nullable=False)
    round_num = Column(Integer, nullable=False)
    persona = Column(String(255), nullable=False)
    report_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship('Review', back_populates='panel_reports')

class ConsolidatedReport(Base):
    __tablename__ = 'consolidated_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String(255), ForeignKey('reviews.review_id', ondelete='CASCADE'), nullable=False)
    round_num = Column(Integer, nullable=False)
    report_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship('Review', back_populates='consolidated_reports')


# --- Tables that were already correctly defined ---

class ConversationThread(Base):
    __tablename__ = 'conversation_threads'
    id = Column(String, primary_key=True)
    sub_room_id = Column(String, ForeignKey('rooms.room_id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    pinned = Column(Boolean, nullable=False, server_default='false')
    archived = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sub_room = relationship('Room', back_populates='conversation_threads')
    messages = relationship('ConversationMessage', back_populates='thread', cascade="all, delete-orphan")
    attachments = relationship('Attachment', back_populates='thread', cascade="all, delete-orphan")
    export_jobs = relationship('ExportJob', back_populates='thread', cascade="all, delete-orphan")

class ConversationMessage(Base):
    __tablename__ = 'conversation_messages'
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('conversation_threads.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default='draft')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    meta = Column(JSONB, nullable=True)
    content_tsvector = Column(TSVECTOR, nullable=True)

    # Relationships
    thread = relationship('ConversationThread', back_populates='messages')

class Attachment(Base):
    __tablename__ = 'attachments'
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('conversation_threads.id', ondelete='CASCADE'), nullable=True, index=True)
    kind = Column(String, nullable=False)
    name = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    thread = relationship('ConversationThread', back_populates='attachments')
    chunks = relationship('AttachmentChunk', back_populates='attachment', cascade="all, delete-orphan")

class AttachmentChunk(Base):
    __tablename__ = 'attachment_chunks'
    id = Column(String, primary_key=True)
    attachment_id = Column(String, ForeignKey('attachments.id', ondelete='CASCADE'), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)  # VECTOR(1536) 대신 Text 사용

    # Relationships
    attachment = relationship('Attachment', back_populates='chunks')

class ExportJob(Base):
    __tablename__ = 'export_jobs'
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('conversation_threads.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(String, nullable=False, index=True)
    format = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default='queued')
    file_url = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    thread = relationship('ConversationThread', back_populates='export_jobs')

# --- Tables added during stabilization audit to sync with migrations ---

class MessageVersion(Base):
    __tablename__ = 'message_versions'
    version_id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(255), ForeignKey('messages.message_id', ondelete='CASCADE'), nullable=False, index=True)
    content = Column(Text, nullable=False)
    role = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship('Message', back_populates='versions')

# Add the relationship to the Message model
Message.versions = relationship('MessageVersion', order_by=MessageVersion.created_at, back_populates='message', cascade="all, delete-orphan")


class UserFact(Base):
    __tablename__ = 'user_facts'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Text, nullable=False, index=True)
    kind = Column(Text, nullable=False)
    fact_type = Column(Text, nullable=False)
    value_json = Column(JSONB, nullable=False)
    normalized_value = Column(Text, nullable=False)
    source_message_id = Column(String(255), nullable=True)
    pending_review = Column(Boolean, nullable=False, server_default='false')
    latest = Column(Boolean, nullable=False, server_default='true')
    sensitivity = Column(String(50), nullable=False, server_default='low')
    confidence = Column(Float, nullable=False, server_default='1.0')
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SummaryNote(Base):
    __tablename__ = 'summary_notes'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    room_id = Column(Text, nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    text = Column(Text, nullable=False)
    tokens_saved_estimate = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
