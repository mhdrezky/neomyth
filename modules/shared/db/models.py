"""SQLAlchemy ORM models shared across Neomyth modules (Neo-Parse, Neo-Voice).

Tables use snake_case names; Python attributes stay camel/snake per SQLAlchemy
convention. Alembic autogenerate reads `Base.metadata` from this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    CONTRACT = "CONTRACT"
    RECEIPT = "RECEIPT"
    REPORT = "REPORT"
    OTHER = "OTHER"


class ParseJobStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Schema(Base):
    """Reusable JSON output schema that shapes structured extraction."""

    __tablename__ = "schemas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    parse_jobs: Mapped[list[ParseJob]] = relationship(back_populates="schema")


class Document(Base):
    """Uploaded document (PDF) metadata."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
        default=DocumentType.OTHER,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    parse_jobs: Mapped[list[ParseJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_documents_doc_type", "doc_type"),
        Index("ix_documents_created_at", "created_at"),
    )


class ParseJob(Base):
    """A single parsing run against a document."""

    __tablename__ = "parse_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schemas.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ParseJobStatus] = mapped_column(
        Enum(ParseJobStatus, name="parse_job_status"),
        nullable=False,
        default=ParseJobStatus.PENDING,
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="parse_jobs")
    schema: Mapped[Schema | None] = relationship(back_populates="parse_jobs")
    sections: Mapped[list[ParseSection]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_parse_jobs_document_id", "document_id"),
        Index("ix_parse_jobs_status", "status"),
        Index("ix_parse_jobs_created_at", "created_at"),
    )


class ParseSection(Base):
    """An extracted section with source grounding (rect on a page)."""

    __tablename__ = "parse_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parse_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    rect_top: Mapped[float] = mapped_column(Float, nullable=False)
    rect_left: Mapped[float] = mapped_column(Float, nullable=False)
    rect_width: Mapped[float] = mapped_column(Float, nullable=False)
    rect_height: Mapped[float] = mapped_column(Float, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    json_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[ParseJob] = relationship(back_populates="sections")

    __table_args__ = (
        Index("ix_parse_sections_job_id", "job_id"),
        Index("ix_parse_sections_job_page", "job_id", "page_number"),
        Index("ix_parse_sections_label", "label"),
    )


class VoiceSession(Base):
    """A saved voice conversation (one Start → Stop session)."""

    __tablename__ = "voice_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    messages: Mapped[list[VoiceMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_voice_sessions_last_activity", "last_activity_at"),)


class VoiceMessage(Base):
    """A single chat turn message inside a voice session."""

    __tablename__ = "voice_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[VoiceSession] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_voice_messages_session_order", "session_id", "sort_order"),
    )
