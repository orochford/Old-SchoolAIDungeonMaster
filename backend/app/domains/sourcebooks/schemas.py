from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PDFUploadResponse(BaseModel):
    id: UUID
    filename: str
    status: ProcessingStatus
    message: str


class PDFDocumentResponse(BaseModel):
    id: UUID
    rpg_system_id: UUID
    filename: str
    original_filename: str
    status: ProcessingStatus
    processing_error: Optional[str]
    title: Optional[str]
    description: Optional[str] = None
    author: Optional[str]
    page_count: Optional[int]
    chunk_count: int
    category: Optional[str]
    cover_image_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExtractedImageResponse(BaseModel):
    id: UUID
    document_id: UUID
    image_path: str
    image_type: str  # 'cover', 'map', 'illustration', 'table'
    page_number: Optional[int]
    title: Optional[str]
    description: Optional[str]
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class PDFDocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    rpg_system_id: Optional[UUID] = None


class PDFChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    content: str
    start_page: Optional[int]
    end_page: Optional[int]
    chunk_index: int
    chunk_metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    rpg_system_id: Optional[UUID] = None
    document_ids: Optional[List[UUID]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class RAGQueryResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: Optional[str]
    content: str
    page_numbers: Optional[str]
    relevance_score: float
    metadata: Dict[str, Any]


class RAGQueryResponse(BaseModel):
    query: str
    results: List[RAGQueryResult]
    total_results: int
