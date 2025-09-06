"""
SQLAlchemy ORM Models.
These models are primarily for Alembic's auto-generation capabilities
and to provide a Python-native representation of the DB schema.
The application services may use raw SQL for performance, but these
models should be kept in sync with the DDL in migrations.
"""
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, VECTOR, TSVECTOR
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Room(Base):
    __tablename__ = 'rooms'
    room_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey('rooms.room_id', ondelete='CASCADE'))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    message_count = Column(Integer, default=0)

    # Relationships
    parent = relationship('Room', remote_side=[room_id], back_populates='children')
    children = relationship('Room', back_populates='parent')
    conversation_threads = relationship('ConversationThread', back_populates='sub_room')

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

class ConversationMessage(Base):
    __tablename__ = 'conversation_messages'
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('conversation_threads.id', ondelete='CASCADE'), nullable=False, index=True)
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
    kind = Column(String, nullable=False)
    name = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    chunks = relationship('AttachmentChunk', back_populates='attachment', cascade="all, delete-orphan")

class AttachmentChunk(Base):
    __tablename__ = 'attachment_chunks'
    id = Column(String, primary_key=True)
    attachment_id = Column(String, ForeignKey('attachments.id', ondelete='CASCADE'), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(VECTOR(1536), nullable=True)

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
