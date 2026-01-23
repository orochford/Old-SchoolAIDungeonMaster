from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PDFDocument(Base, BaseModel):
    """Uploaded PDF metadata and processing status."""

    __tablename__ = "pdf_documents"

    rpg_system_id = Column(UUID(as_uuid=True), ForeignKey("rpg_systems.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)

    # Processing status
    status = Column(
        SQLEnum(ProcessingStatus),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    processing_error = Column(Text)

    # Document metadata
    title = Column(String(255))
    description = Column(Text)  # Brief description/summary of the sourcebook
    author = Column(String(255))
    page_count = Column(Integer)
    cover_image_path = Column(String(500))  # Path to extracted cover image

    # Processing stats
    chunk_count = Column(Integer, default=0)

    # Category (core rules, module, supplement, etc.)
    category = Column(String(50))

    # Full markdown export path (for LLM context loading)
    markdown_path = Column(String(500))

    # Relationships
    rpg_system = relationship("RPGSystem", back_populates="pdf_documents")
    chunks = relationship("PDFChunk", back_populates="document", cascade="all, delete-orphan")
    images = relationship("ExtractedImage", back_populates="document", cascade="all, delete-orphan")


class ExtractedImage(Base, BaseModel):
    """Images extracted from PDFs (covers, maps, illustrations)."""

    __tablename__ = "extracted_images"

    document_id = Column(UUID(as_uuid=True), ForeignKey("pdf_documents.id", ondelete="CASCADE"), nullable=False)
    image_path = Column(String(500), nullable=False)
    image_type = Column(String(50), nullable=False)  # 'cover', 'map', 'illustration', 'table'
    page_number = Column(Integer)
    title = Column(String(255))
    description = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    file_size = Column(Integer)

    # Color analysis fields
    is_color = Column(Boolean)  # True if color image, False if grayscale/B&W
    dominant_colors = Column(JSONB)  # List of hex color strings e.g. ["#ff0000", "#00ff00"]
    color_palette = Column(JSONB)  # List of RGB tuples e.g. [[255,0,0], [0,255,0]]
    brightness = Column(Integer)  # 0-100 scale (0=dark, 100=bright)
    is_full_page = Column(Boolean, default=False)  # True if rendered from full page (vector map)

    # Relationships
    document = relationship("PDFDocument", back_populates="images")


class PDFChunk(Base, BaseModel):
    """Chunked text with embeddings for RAG retrieval."""

    __tablename__ = "pdf_chunks"

    document_id = Column(UUID(as_uuid=True), ForeignKey("pdf_documents.id"), nullable=False)

    # Chunk content
    content = Column(Text, nullable=False)

    # Page number(s) this chunk comes from
    start_page = Column(Integer)
    end_page = Column(Integer)

    # Position within the document
    chunk_index = Column(Integer, nullable=False)

    # Chunk metadata (section headers, table of contents path, etc.)
    chunk_metadata = Column(JSONB, default={})

    # Embedding vector (1536 dimensions for text-embedding-3-small)
    embedding = Column(Vector(1536))

    # Relationships
    document = relationship("PDFDocument", back_populates="chunks")
