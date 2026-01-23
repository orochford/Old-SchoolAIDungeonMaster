"""RAG retrieval for rule context."""

from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sourcebooks.models import PDFChunk, PDFDocument
from app.rag.embeddings import EmbeddingService
from app.config import settings


class RAGRetriever:
    """Retrieve relevant chunks from indexed PDFs."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = EmbeddingService()
        self.top_k = settings.top_k_chunks

    async def query(
        self,
        query: str,
        rpg_system_id: Optional[UUID] = None,
        document_ids: Optional[List[UUID]] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query for relevant chunks using vector similarity."""
        top_k = top_k or self.top_k

        # Generate query embedding
        query_embedding = await self.embedding_service.embed_single(query)

        # Build the vector similarity query
        results = await self._vector_search(
            query_embedding=query_embedding,
            rpg_system_id=rpg_system_id,
            document_ids=document_ids,
            top_k=top_k,
        )

        return results

    async def _vector_search(
        self,
        query_embedding: List[float],
        rpg_system_id: Optional[UUID] = None,
        document_ids: Optional[List[UUID]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search using pgvector."""
        # Convert embedding to string format for pgvector
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Build base query
        base_query = """
            SELECT
                c.id as chunk_id,
                c.document_id,
                c.content,
                c.start_page,
                c.end_page,
                c.chunk_index,
                c.chunk_metadata,
                d.title as document_title,
                d.original_filename,
                1 - (c.embedding <=> '{embedding}'::vector) as similarity
            FROM pdf_chunks c
            JOIN pdf_documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
        """.format(embedding=embedding_str)

        # Add filters
        if rpg_system_id:
            base_query += f" AND d.rpg_system_id = '{rpg_system_id}'::uuid"

        if document_ids:
            ids_str = ",".join(f"'{d}'::uuid" for d in document_ids)
            base_query += f" AND c.document_id IN ({ids_str})"

        base_query += f"""
            ORDER BY c.embedding <=> '{embedding_str}'::vector
            LIMIT {top_k}
        """

        result = await self.session.execute(text(base_query))
        rows = result.fetchall()

        return [
            {
                "chunk_id": row.chunk_id,
                "document_id": row.document_id,
                "document_title": row.document_title or row.original_filename,
                "content": row.content,
                "page_numbers": f"{row.start_page}-{row.end_page}" if row.start_page != row.end_page else str(row.start_page),
                "score": float(row.similarity) if row.similarity else 0.0,
                "metadata": row.chunk_metadata or {},
            }
            for row in rows
        ]

    async def get_context_for_dm(
        self,
        query: str,
        rpg_system_id: UUID,
        max_chunks: int = 7,
    ) -> str:
        """Get formatted context for the DM prompt."""
        chunks = await self.query(
            query=query,
            rpg_system_id=rpg_system_id,
            top_k=max_chunks,
        )

        if not chunks:
            return "No relevant rules found in the sourcebooks."

        context_parts = []
        for chunk in chunks:
            source = f"[{chunk['document_title']}, p.{chunk['page_numbers']}]"
            context_parts.append(f"{source}\n{chunk['content']}")

        return "\n\n---\n\n".join(context_parts)

    async def keyword_search(
        self,
        keywords: List[str],
        rpg_system_id: Optional[UUID] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Fallback keyword search when embeddings aren't available."""
        # Build search pattern
        pattern = "|".join(keywords)

        query = select(PDFChunk).join(PDFDocument)

        if rpg_system_id:
            query = query.where(PDFDocument.rpg_system_id == rpg_system_id)

        # Use PostgreSQL full-text search
        query = query.where(
            PDFChunk.content.op("~*")(pattern)
        ).limit(top_k)

        result = await self.session.execute(query)
        chunks = result.scalars().all()

        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "page_numbers": f"{chunk.start_page}-{chunk.end_page}" if chunk.start_page != chunk.end_page else str(chunk.start_page or "?"),
                "score": 1.0,  # Keyword matches don't have similarity scores
                "metadata": chunk.chunk_metadata or {},
            }
            for chunk in chunks
        ]

    async def get_adventure_context(
        self,
        query: str,
        adventure_document_id: UUID,
        current_location: Optional[str] = None,
        max_chunks: int = 5,
    ) -> str:
        """Get formatted context specifically from an adventure module."""
        # Get content related to the query
        chunks = await self.query(
            query=query,
            document_ids=[adventure_document_id],
            top_k=max_chunks,
        )

        # Also get content for current location if provided
        if current_location:
            location_chunks = await self.query(
                query=f"{current_location} area room description",
                document_ids=[adventure_document_id],
                top_k=2,
            )
            # Avoid duplicates
            seen_ids = {c["chunk_id"] for c in chunks}
            for chunk in location_chunks:
                if chunk["chunk_id"] not in seen_ids:
                    chunks.append(chunk)

        if not chunks:
            return "No relevant adventure content found."

        context_parts = []
        for chunk in chunks[:max_chunks + 2]:  # Allow a bit extra for location context
            source = f"[{chunk['document_title']}, p.{chunk['page_numbers']}]"
            context_parts.append(f"{source}\n{chunk['content']}")

        return "\n\n---\n\n".join(context_parts)
