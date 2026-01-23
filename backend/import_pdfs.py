"""Import existing PDFs from the rpgs directory."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domains.campaigns.models import RPGSystem
from app.domains.sourcebooks.models import PDFDocument, ProcessingStatus
from app.domains.sourcebooks.router import process_pdf_background

# Import all models to resolve relationships
from app.domains.characters import models as _
from app.domains.sessions import models as __
from app.domains.combat import models as ___
from app.domains.npcs import models as ____
from app.domains.inventory import models as _____

PDF_DIR = Path("/home/orochford/rpgs")


async def get_bx_system_id() -> str:
    """Get the B/X D&D system ID."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RPGSystem).where(RPGSystem.code == "bx-dnd")
        )
        system = result.scalar_one_or_none()
        if system:
            return str(system.id)
    return None


async def import_pdf(file_path: Path, rpg_system_id: str):
    """Import a single PDF file."""
    async with AsyncSessionLocal() as db:
        # Check if already imported
        result = await db.execute(
            select(PDFDocument).where(PDFDocument.original_filename == file_path.name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  Already imported: {file_path.name} (status: {existing.status})")
            return existing

        # Create document record
        file_size = file_path.stat().st_size
        document = PDFDocument(
            id=uuid4(),
            rpg_system_id=rpg_system_id,
            filename=file_path.name,
            original_filename=file_path.name,
            file_path=str(file_path),
            file_size=file_size,
            status=ProcessingStatus.PENDING,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        print(f"  Created document record: {file_path.name}")
        return document


async def main():
    """Import all PDFs from the directory."""
    print("=" * 60)
    print("PDF Import Script")
    print("=" * 60)

    # Get the B/X D&D system ID
    system_id = await get_bx_system_id()
    if not system_id:
        print("ERROR: B/X D&D system not found. Run seed_data.py first.")
        return

    print(f"Using RPG System ID: {system_id}")
    print(f"Scanning directory: {PDF_DIR}")
    print()

    # Find all PDFs
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")
    print()

    # Import each PDF
    documents = []
    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file.name}")
        doc = await import_pdf(pdf_file, system_id)
        if doc and doc.status == ProcessingStatus.PENDING:
            documents.append(doc)

    print()
    print(f"Imported {len(documents)} new documents")

    # Ask user if they want to start processing
    if documents:
        print()
        print("Do you want to start processing (embedding) these PDFs? (y/n)")
        print("WARNING: This will use OpenAI API credits for embeddings.")
        response = input("> ").strip().lower()

        if response == 'y':
            print()
            print("Starting background processing...")
            for doc in documents:
                print(f"  Queuing: {doc.original_filename}")
                # Process in sequence to avoid overwhelming the API
                await process_pdf_background(doc.id, doc.file_path)
                print(f"  Completed: {doc.original_filename}")
            print()
            print("All documents processed!")
        else:
            print("Skipped processing. Documents are saved but not indexed.")
            print("You can process them later via the web interface.")

    print()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
