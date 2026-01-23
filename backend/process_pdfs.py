"""Process all pending PDF documents."""

import asyncio
import sys
from sqlalchemy import select

# Import all models to ensure relationships are resolved
from app.domains.campaigns import models as campaigns_models
from app.domains.characters import models as characters_models
from app.domains.sessions import models as sessions_models
from app.domains.combat import models as combat_models
from app.domains.npcs import models as npcs_models
from app.domains.inventory import models as inventory_models
from app.domains.sourcebooks import models as sourcebooks_models

from app.core.database import AsyncSessionLocal
from app.domains.sourcebooks.models import PDFDocument, PDFChunk, ProcessingStatus
from app.rag.processor import PDFProcessor


async def process_all_pending():
    """Process all pending PDF documents."""
    processor = PDFProcessor()

    async with AsyncSessionLocal() as db:
        # Get all pending documents
        result = await db.execute(select(PDFDocument))
        all_docs = list(result.scalars().all())
        pending_docs = [d for d in all_docs if d.status == ProcessingStatus.PENDING]

        print(f"Found {len(pending_docs)} pending documents to process")

        for i, doc in enumerate(pending_docs, 1):
            print(f"\n[{i}/{len(pending_docs)}] Processing: {doc.original_filename}")
            print(f"  File: {doc.file_path}")

            try:
                # Update status to processing
                doc.status = ProcessingStatus.PROCESSING
                await db.commit()

                # Get document metadata
                meta = processor.get_document_metadata(doc.file_path)
                if meta.get("title"):
                    doc.title = meta["title"]
                if meta.get("author"):
                    doc.author = meta["author"]
                if meta.get("page_count"):
                    doc.page_count = meta["page_count"]

                print(f"  Pages: {doc.page_count or 'unknown'}")
                print(f"  Title: {doc.title or doc.original_filename}")

                # Process the PDF
                print("  Extracting text and generating embeddings...")
                chunks = await processor.process(doc.file_path)

                print(f"  Created {len(chunks)} chunks")

                # Delete existing chunks if any
                existing = await db.execute(
                    select(PDFChunk).where(PDFChunk.document_id == doc.id)
                )
                for chunk in existing.scalars().all():
                    await db.delete(chunk)

                # Store new chunks
                for idx, chunk_data in enumerate(chunks):
                    chunk = PDFChunk(
                        document_id=doc.id,
                        content=chunk_data["content"],
                        start_page=chunk_data.get("start_page"),
                        end_page=chunk_data.get("end_page"),
                        chunk_index=idx,
                        chunk_metadata=chunk_data.get("metadata", {}),
                        embedding=chunk_data.get("embedding"),
                    )
                    db.add(chunk)

                # Update document status
                doc.status = ProcessingStatus.COMPLETED
                doc.chunk_count = len(chunks)
                doc.processing_error = None

                await db.commit()
                print(f"  ✓ Completed successfully")

            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                doc.status = ProcessingStatus.FAILED
                doc.processing_error = str(e)
                await db.commit()

        print("\n" + "="*50)
        print("Processing complete!")

        # Show summary
        result = await db.execute(select(PDFDocument))
        all_docs = list(result.scalars().all())

        completed = len([d for d in all_docs if d.status == ProcessingStatus.COMPLETED])
        failed = len([d for d in all_docs if d.status == ProcessingStatus.FAILED])
        pending = len([d for d in all_docs if d.status == ProcessingStatus.PENDING])

        print(f"  Completed: {completed}")
        print(f"  Failed: {failed}")
        print(f"  Pending: {pending}")


if __name__ == "__main__":
    asyncio.run(process_all_pending())
