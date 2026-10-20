from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    file_size_bytes = Column(Integer, nullable=False)
    total_pages = Column(Integer, default=0)
    classification = Column(String(32), default="DIGITAL")
    source_language = Column(String(16), nullable=True)
    storage_original_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship("DocumentVersionModel", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("JobModel", back_populates="document", cascade="all, delete-orphan")


class DocumentVersionModel(Base):
    __tablename__ = "document_versions"

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    parent_version_id = Column(String(64), nullable=True)
    version_number = Column(Integer, default=1)
    
    source_language = Column(String(16), nullable=False)
    target_language = Column(String(16), nullable=False)
    
    ocr_provider = Column(String(32), nullable=True)
    ocr_policy = Column(String(32), nullable=True)
    
    translation_provider = Column(String(32), nullable=False)
    translation_model = Column(String(128), nullable=False)
    translation_policy = Column(String(32), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    
    storage_ir_path = Column(String(512), nullable=True)
    storage_pdf_path = Column(String(512), nullable=True)
    
    status = Column(String(32), default="PENDING")
    is_published = Column(Boolean, default=False)
    
    quality_score = Column(Float, nullable=True)
    extra_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("DocumentModel", back_populates="versions")


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    version_id = Column(String(64), nullable=True)
    job_type = Column(String(32), default="TRANSLATE_DOCUMENT")  # TRANSLATE_DOCUMENT, EDIT_SECTION, RENDER_ONLY
    status = Column(String(32), default="UPLOADED", index=True)
    progress_percent = Column(Float, default=0.0)
    failure_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("DocumentModel", back_populates="jobs")
    events = relationship("JobEventModel", back_populates="job", cascade="all, delete-orphan")


class JobEventModel(Base):
    __tablename__ = "job_events"

    id = Column(String(64), primary_key=True)
    job_id = Column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    message = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("JobModel", back_populates="events")


class TranslationAttemptModel(Base):
    __tablename__ = "translation_attempts"

    id = Column(String(64), primary_key=True)
    node_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    model = Column(String(128), nullable=False)
    source_language = Column(String(16), nullable=False)
    target_language = Column(String(16), nullable=False)
    prompt_version = Column(String(32), nullable=False)
    input_hash = Column(String(64), nullable=False, index=True)
    
    latency_ms = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    
    status = Column(String(32), nullable=False)  # SUCCESS, FAILED
    failure_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
