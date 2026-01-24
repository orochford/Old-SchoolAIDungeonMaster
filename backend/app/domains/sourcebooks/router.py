from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from uuid import UUID, uuid4
import os
import shutil

from app.core.database import get_db
from app.config import settings
from app.domains.sourcebooks.models import PDFDocument, PDFChunk, ExtractedImage, ProcessingStatus
from app.domains.sourcebooks.schemas import (
    PDFUploadResponse,
    PDFDocumentResponse,
    PDFDocumentUpdate,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGQueryResult,
    ExtractedImageResponse,
)
from app.domains.campaigns.models import RPGSystem, Campaign

router = APIRouter()


async def generate_document_description(chunks: list, title: str = None) -> str:
    """Generate a brief description using LLM based on document content.

    Uses the configured AI provider, with fallback to the other.
    """
    import anthropic
    import openai
    from app.config import settings

    # Take first few chunks for context (roughly first 10 pages worth)
    sample_text = "\n\n".join([c["content"] for c in chunks[:5]])[:4000]

    prompt = f"""Based on this excerpt from an RPG sourcebook{f' titled "{title}"' if title else ''}, write a brief 1-2 sentence description of what this book contains. Focus on the type of content (rules, adventure module, supplement) and key themes.

Use plain text only - no markdown, no asterisks, no formatting.

Excerpt:
{sample_text}

Description:"""

    # Determine provider order based on processing settings
    use_openai_primary = settings.processing_provider == "openai"

    def try_openai():
        if not settings.openai_api_key:
            return None
        try:
            model = settings.processing_openai_model or "gpt-4o-mini"
            print(f"Using OpenAI ({model}) for description generation...")
            client = openai.OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI failed: {e}")
            return None

    def try_claude():
        try:
            model = settings.processing_claude_model or "claude-haiku-4-5-20250101"
            print(f"Using Claude ({model}) for description generation...")
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            message = client.messages.create(
                model=model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except anthropic.AuthenticationError as e:
            print(f"Claude auth error: {e}")
        except anthropic.RateLimitError as e:
            print(f"Claude rate limit/credits: {e}")
        except anthropic.APIStatusError as e:
            print(f"Claude API error: {e}")
        except Exception as e:
            print(f"Claude failed: {e}")
        return None

    # Use configured provider only - no fallback
    if use_openai_primary:
        return try_openai()
    else:
        return try_claude()


async def process_pdf_background(document_id: UUID, file_path: str):
    """Background task to process a PDF document."""
    # Import here to avoid circular imports
    from app.rag.processor import PDFProcessor
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(PDFDocument).where(PDFDocument.id == document_id)
            )
            document = result.scalar_one_or_none()

            if not document:
                return

            document.status = ProcessingStatus.PROCESSING
            await db.commit()

            # Process the PDF
            processor = PDFProcessor()

            # Extract images (cover, maps, illustrations)
            extracted_images = processor.extract_images(file_path, str(document_id))

            # Save extracted images to database
            for img_data in extracted_images:
                # Convert brightness from 0-1 float to 0-100 int for storage
                brightness = img_data.get("brightness")
                if brightness is not None:
                    brightness = int(brightness * 100)

                img = ExtractedImage(
                    document_id=document_id,
                    image_path=img_data["image_path"],
                    image_type=img_data["image_type"],
                    page_number=img_data.get("page_number"),
                    title=img_data.get("title"),
                    width=img_data.get("width"),
                    height=img_data.get("height"),
                    file_size=img_data.get("file_size"),
                    # Color analysis fields
                    is_color=img_data.get("is_color"),
                    dominant_colors=img_data.get("dominant_colors"),
                    color_palette=img_data.get("color_palette"),
                    brightness=brightness,
                    is_full_page=img_data.get("is_full_page", False),
                )
                db.add(img)

                # Set cover image path on document
                if img_data["image_type"] == "cover":
                    document.cover_image_path = img_data["image_path"]

            # Process text and create chunks
            chunks = await processor.process(file_path)

            # Store chunks
            for i, chunk_data in enumerate(chunks):
                chunk = PDFChunk(
                    document_id=document_id,
                    content=chunk_data["content"],
                    start_page=chunk_data.get("start_page"),
                    end_page=chunk_data.get("end_page"),
                    chunk_index=i,
                    chunk_metadata=chunk_data.get("metadata", {}),
                    embedding=chunk_data.get("embedding"),
                )
                db.add(chunk)

            # Export full markdown for LLM context loading
            # Get RPG system code for directory structure
            system_result = await db.execute(
                select(RPGSystem).where(RPGSystem.id == document.rpg_system_id)
            )
            rpg_system = system_result.scalar_one_or_none()
            system_code = rpg_system.code if rpg_system else "unknown"

            # Create markdown output path: /markdown/{system_code}/{document_id}.md
            markdown_dir = os.path.join(settings.markdown_storage_path, system_code)
            markdown_filename = f"{document_id}.md"
            markdown_path = os.path.join(markdown_dir, markdown_filename)

            # Export markdown
            try:
                doc_title = document.title or document.original_filename.replace('.pdf', '')
                processor.export_markdown(file_path, markdown_path, title=doc_title)
                document.markdown_path = markdown_path
                print(f"Exported markdown to: {markdown_path}")
            except Exception as md_err:
                print(f"Failed to export markdown: {md_err}")

            # Generate description using LLM
            if chunks and not document.description:
                description = await generate_document_description(chunks, document.title)
                if description:
                    document.description = description

            document.status = ProcessingStatus.COMPLETED
            document.chunk_count = len(chunks)
            await db.commit()

        except Exception as e:
            document.status = ProcessingStatus.FAILED
            document.processing_error = str(e)
            await db.commit()


@router.post("/upload", response_model=PDFUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    rpg_system_id: UUID = Form(...),
    category: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF sourcebook for processing."""
    # Verify RPG system exists
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.id == rpg_system_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RPG system not found",
        )

    # Validate file
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed",
        )

    # Generate unique filename
    file_id = uuid4()
    filename = f"{file_id}.pdf"
    file_path = os.path.join(settings.pdf_storage_path, filename)

    # Ensure storage directory exists
    os.makedirs(settings.pdf_storage_path, exist_ok=True)

    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}",
        )

    # Get file size
    file_size = os.path.getsize(file_path)

    # Create document record
    document = PDFDocument(
        rpg_system_id=rpg_system_id,
        filename=filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        category=category,
        status=ProcessingStatus.PENDING,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    # Start background processing
    background_tasks.add_task(process_pdf_background, document.id, file_path)

    return PDFUploadResponse(
        id=document.id,
        filename=file.filename,
        status=ProcessingStatus.PENDING,
        message="PDF uploaded successfully. Processing started.",
    )


@router.get("", response_model=List[PDFDocumentResponse])
async def list_sourcebooks(
    rpg_system_id: UUID = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """List uploaded sourcebooks."""
    query = select(PDFDocument)

    if rpg_system_id:
        query = query.where(PDFDocument.rpg_system_id == rpg_system_id)
    if status:
        query = query.where(PDFDocument.status == status)

    query = query.order_by(PDFDocument.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=PDFDocumentResponse)
async def get_sourcebook(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a sourcebook by ID."""
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    return document


@router.get("/{document_id}/status")
async def get_indexing_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the processing status of a sourcebook."""
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    return {
        "id": document.id,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "error": document.processing_error,
    }


@router.post("/query", response_model=RAGQueryResponse)
async def query_sourcebooks(
    query_request: RAGQueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Query sourcebooks using RAG."""
    from app.rag.retriever import RAGRetriever

    retriever = RAGRetriever(db)
    results = await retriever.query(
        query=query_request.query,
        rpg_system_id=query_request.rpg_system_id,
        document_ids=query_request.document_ids,
        top_k=query_request.top_k,
    )

    return RAGQueryResponse(
        query=query_request.query,
        results=[
            RAGQueryResult(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                document_title=r.get("document_title"),
                content=r["content"],
                page_numbers=r.get("page_numbers"),
                relevance_score=r["score"],
                metadata=r.get("metadata", {}),
            )
            for r in results
        ],
        total_results=len(results),
    )


@router.patch("/{document_id}", response_model=PDFDocumentResponse)
async def update_sourcebook(
    document_id: UUID,
    update_data: PDFDocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a sourcebook's metadata."""
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(document, field, value)

    await db.flush()
    await db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sourcebook(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a sourcebook and all related records."""
    from sqlalchemy import delete as sql_delete
    from app.domains.adventures.models import (
        AdventureModule, AdventureLocation, AdventureNPC,
        AdventureEncounter, AdventureItem, AdventureStoryBeat
    )

    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    # Clear FK references in campaigns that use this document as adventure
    await db.execute(
        update(Campaign)
        .where(Campaign.adventure_document_id == document_id)
        .values(adventure_document_id=None)
    )

    # Find any adventure module linked to this document
    module_result = await db.execute(
        select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
    )
    module = module_result.scalar_one_or_none()

    if module:
        # Delete adventure module's child records
        # Order matters: delete records that reference locations BEFORE deleting locations
        await db.execute(sql_delete(AdventureNPC).where(AdventureNPC.module_id == module.id))
        await db.execute(sql_delete(AdventureEncounter).where(AdventureEncounter.module_id == module.id))
        await db.execute(sql_delete(AdventureItem).where(AdventureItem.module_id == module.id))
        await db.execute(sql_delete(AdventureStoryBeat).where(AdventureStoryBeat.module_id == module.id))
        await db.execute(sql_delete(AdventureLocation).where(AdventureLocation.module_id == module.id))
        await db.execute(sql_delete(AdventureModule).where(AdventureModule.id == module.id))

    # Delete extracted images directory
    images_dir = os.path.join(settings.pdf_storage_path, "images", str(document_id))
    if os.path.exists(images_dir):
        try:
            shutil.rmtree(images_dir)
        except OSError:
            pass

    # Delete the PDF file if it exists
    if document.file_path and os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
        except OSError:
            pass  # File may already be deleted

    # Delete document (chunks and extracted_images cascade)
    await db.delete(document)
    await db.commit()


@router.post("/{document_id}/reprocess", response_model=PDFUploadResponse)
async def reprocess_sourcebook(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Reprocess a sourcebook (re-extract and re-index)."""
    from sqlalchemy import delete as sql_delete

    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    # Check if file exists
    if not document.file_path or not os.path.exists(document.file_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF file not found. Please re-upload the document.",
        )

    # Delete existing chunks
    await db.execute(
        sql_delete(PDFChunk).where(PDFChunk.document_id == document_id)
    )

    # Reset document status
    document.status = ProcessingStatus.PENDING
    document.chunk_count = 0
    document.processing_error = None

    await db.flush()

    # Start background processing
    background_tasks.add_task(process_pdf_background, document.id, document.file_path)

    return PDFUploadResponse(
        id=document.id,
        filename=document.original_filename or document.filename,
        status=ProcessingStatus.PENDING,
        message="Reprocessing started.",
    )


@router.get("/{document_id}/images", response_model=List[ExtractedImageResponse])
async def list_document_images(
    document_id: UUID,
    image_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    """List extracted images for a document."""
    query = select(ExtractedImage).where(ExtractedImage.document_id == document_id)

    if image_type:
        query = query.where(ExtractedImage.image_type == image_type)

    query = query.order_by(ExtractedImage.page_number)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{document_id}/cover")
async def get_cover_image(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the cover image for a document."""
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    if not document.cover_image_path or not os.path.exists(document.cover_image_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover image not found",
        )

    return FileResponse(
        document.cover_image_path,
        media_type="image/png",
        filename=f"{document.original_filename}_cover.png",
    )


@router.get("/images/{image_id}/file")
async def get_image_file(
    image_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve an extracted image file."""
    result = await db.execute(
        select(ExtractedImage).where(ExtractedImage.id == image_id)
    )
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    if not os.path.exists(image.image_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found",
        )

    # Determine media type from extension
    ext = os.path.splitext(image.image_path)[1].lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/png")

    return FileResponse(
        image.image_path,
        media_type=media_type,
    )


@router.get("/{document_id}/markdown")
async def get_document_markdown(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the full markdown export of a sourcebook.

    Returns the complete markdown content for LLM context loading.
    """
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sourcebook not found",
        )

    if not document.markdown_path or not os.path.exists(document.markdown_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown export not available. Try reprocessing the document.",
        )

    with open(document.markdown_path, 'r', encoding='utf-8') as f:
        content = f.read()

    return {
        "id": document.id,
        "title": document.title or document.original_filename,
        "category": document.category,
        "markdown": content,
    }


@router.get("/system/{system_code}/rulebooks")
async def get_system_rulebooks(
    system_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all rulebook markdown for an RPG system.

    Returns list of rulebooks (category='rules') with their markdown content.
    Used for loading system rules into LLM context at session start.
    """
    # Find system by code
    system_result = await db.execute(
        select(RPGSystem).where(RPGSystem.code == system_code)
    )
    rpg_system = system_result.scalar_one_or_none()

    if not rpg_system:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RPG system '{system_code}' not found",
        )

    # Get rulebooks for this system
    # Use string value for status to avoid enum type casting issues
    result = await db.execute(
        select(PDFDocument).where(
            PDFDocument.rpg_system_id == rpg_system.id,
            PDFDocument.category == "rules",
            PDFDocument.status == "completed",
        )
    )
    rulebooks = list(result.scalars().all())

    # Load markdown for each rulebook
    rulebook_data = []
    for doc in rulebooks:
        markdown_content = None
        if doc.markdown_path and os.path.exists(doc.markdown_path):
            try:
                with open(doc.markdown_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
            except Exception:
                pass

        rulebook_data.append({
            "id": str(doc.id),
            "title": doc.title or doc.original_filename,
            "description": doc.description,
            "has_markdown": markdown_content is not None,
            "markdown": markdown_content,
        })

    return {
        "system_code": system_code,
        "system_name": rpg_system.name,
        "rulebooks": rulebook_data,
        "total": len(rulebook_data),
    }
