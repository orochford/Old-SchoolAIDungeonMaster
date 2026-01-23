"""PDF processing for extracting text and metadata.

Uses pymupdf4llm for high-quality markdown extraction with preserved
structure (headers, tables, lists) - optimized for LLM/RAG pipelines.
"""

import fitz  # PyMuPDF - still needed for image extraction and metadata
import pymupdf4llm
from typing import List, Dict, Any, Optional
import re
import os
from uuid import uuid4
from PIL import Image
import io

from app.rag.chunker import SemanticChunker
from app.rag.embeddings import EmbeddingService
from app.config import settings


class PDFProcessor:
    """Process PDF documents for RAG indexing.

    Uses pymupdf4llm for text extraction which provides:
    - Clean markdown output with preserved formatting
    - Better table structure preservation (stat blocks, monster stats)
    - Header hierarchy detection
    - ~0.12s processing time with high quality output
    """

    def __init__(self):
        self.chunker = SemanticChunker()
        self.embedding_service = EmbeddingService()

    async def process(self, file_path: str) -> List[Dict[str, Any]]:
        """Process a PDF file and return chunks with embeddings."""
        # Extract text from PDF using pymupdf4llm
        pages = self._extract_text(file_path)

        # Chunk the text
        chunks = self.chunker.chunk(pages)

        # Generate embeddings
        texts = [chunk["content"] for chunk in chunks]
        embeddings = await self.embedding_service.embed_batch(texts)

        # Combine chunks with embeddings
        for i, chunk in enumerate(chunks):
            chunk["embedding"] = embeddings[i] if i < len(embeddings) else None

        return chunks

    def export_markdown(self, file_path: str, output_path: str, title: str = None) -> str:
        """Export PDF as a clean markdown file for LLM context.

        Args:
            file_path: Path to source PDF
            output_path: Path to save markdown file
            title: Optional title to add at top

        Returns:
            Path to saved markdown file
        """
        # Extract full markdown using pymupdf4llm
        markdown_content = pymupdf4llm.to_markdown(
            file_path,
            page_chunks=False,  # Get full document
            write_images=False,
        )

        # Add title header if provided
        if title:
            markdown_content = f"# {title}\n\n{markdown_content}"

        # Clean up the markdown
        markdown_content = self._clean_markdown(markdown_content)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save markdown file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        return output_path

    def _extract_text(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from each page of the PDF using pymupdf4llm.

        Returns markdown-formatted text with preserved structure.
        """
        pages = []

        try:
            # Use pymupdf4llm for high-quality markdown extraction
            # page_chunks=True returns a list of dicts with 'text' and 'metadata' per page
            md_pages = pymupdf4llm.to_markdown(
                file_path,
                page_chunks=True,  # Get per-page output for chunking
                write_images=False,  # We handle images separately
            )

            # Also open with fitz for additional metadata
            doc = fitz.open(file_path)

            for page_num, md_page in enumerate(md_pages, start=1):
                # pymupdf4llm returns dicts with 'text' key when page_chunks=True
                if isinstance(md_page, dict):
                    text = md_page.get('text', '')
                else:
                    text = str(md_page)

                # Clean up the markdown text
                text = self._clean_markdown(text)

                if text.strip():
                    # Get page metadata from fitz
                    fitz_page = doc[page_num - 1] if page_num <= len(doc) else None
                    metadata = self._extract_page_metadata(fitz_page) if fitz_page else {}

                    pages.append({
                        "page_number": page_num,
                        "content": text,
                        "metadata": metadata,
                    })

            doc.close()

        except Exception as e:
            raise RuntimeError(f"Failed to extract text from PDF: {str(e)}")

        return pages

    def _clean_markdown(self, text: str) -> str:
        """Clean extracted markdown text."""
        # Remove excessive newlines (more than 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove excessive spaces
        text = re.sub(r' {3,}', '  ', text)

        # Remove standalone page numbers
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)

        # Clean up any image placeholder artifacts from pymupdf4llm
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        return text.strip()

    def _extract_page_metadata(self, page) -> Dict[str, Any]:
        """Extract metadata from a page."""
        if page is None:
            return {}

        metadata = {
            "width": page.rect.width,
            "height": page.rect.height,
        }

        # Try to detect headers/titles (larger fonts at top of page)
        try:
            blocks = page.get_text("dict")["blocks"]
            headers = []

            for block in blocks[:5]:  # Check first few blocks
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if span["size"] > 12:  # Larger font
                                headers.append(span["text"].strip())

            if headers:
                metadata["headers"] = headers
        except Exception:
            pass  # Metadata extraction is optional

        return metadata

    def get_document_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract document-level metadata from PDF."""
        try:
            doc = fitz.open(file_path)
            metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "keywords": doc.metadata.get("keywords", ""),
                "page_count": doc.page_count,
            }
            doc.close()
            return metadata
        except Exception:
            return {}

    def extract_images(self, file_path: str, document_id: str) -> List[Dict[str, Any]]:
        """Extract images from PDF (cover, maps, illustrations).

        Includes:
        - Cover image (first page at 300 DPI)
        - Embedded images from all pages
        - Full-page maps (pages with minimal text, rendered at 300 DPI)
        - Color analysis for each image

        Returns list of extracted image metadata including file paths.
        """
        extracted = []
        images_dir = os.path.join(settings.pdf_storage_path, "images", document_id)
        os.makedirs(images_dir, exist_ok=True)

        try:
            doc = fitz.open(file_path)

            # Extract cover image (first page rendered as image)
            cover_path = self._extract_cover(doc, images_dir, document_id)
            if cover_path:
                extracted.append(cover_path)

            # Extract embedded images and detect full-page maps
            for page_num, page in enumerate(doc, start=1):
                # Check if this page is primarily a map (low text, high graphics)
                if self._is_map_page(page) and page_num > 1:  # Skip first page (already cover)
                    map_img = self._render_page_as_map(page, page_num, images_dir, document_id)
                    if map_img:
                        extracted.append(map_img)
                else:
                    # Extract embedded images from this page
                    images = self._extract_page_images(page, page_num, images_dir, document_id)
                    extracted.extend(images)

            doc.close()

        except Exception as e:
            print(f"Error extracting images: {e}")

        return extracted

    def _is_map_page(self, page: fitz.Page) -> bool:
        """Detect if a page is primarily a map (low text, high graphics content).

        Maps typically have:
        - Very little text (< 100 chars)
        - Large images or vector drawings
        - Grid patterns or room layouts
        """
        try:
            # Get text content
            text = page.get_text("text").strip()
            text_length = len(text)

            # Get drawing commands (vector graphics)
            drawings = page.get_drawings()
            drawing_count = len(drawings) if drawings else 0

            # Get embedded images
            images = page.get_images(full=True)
            image_count = len(images)

            # Check for large images that cover most of the page
            has_large_image = False
            page_area = page.rect.width * page.rect.height
            for img in images:
                try:
                    xref = img[0]
                    base_image = page.parent.extract_image(xref)
                    if base_image:
                        img_area = base_image.get("width", 0) * base_image.get("height", 0)
                        # Image covers > 50% of page
                        if img_area > page_area * 0.3:
                            has_large_image = True
                            break
                except Exception:
                    continue

            # Heuristics for map detection:
            # - Very little text (< 200 chars, excluding page numbers)
            # - Many vector drawings (> 50) OR large embedded image
            is_map = (
                text_length < 200 and
                (drawing_count > 50 or has_large_image or image_count > 0)
            )

            return is_map

        except Exception as e:
            print(f"Error checking if page is map: {e}")
            return False

    def _render_page_as_map(
        self, page: fitz.Page, page_num: int, images_dir: str, document_id: str
    ) -> Optional[Dict[str, Any]]:
        """Render an entire page as a high-resolution map image."""
        try:
            # Render at 300 DPI for detailed maps
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)

            map_filename = f"{document_id}_map_p{page_num}.png"
            map_path = os.path.join(images_dir, map_filename)
            pix.save(map_path)

            # Analyze colors
            color_info = self._analyze_image_colors(map_path)

            return {
                "image_path": map_path,
                "image_type": "map",
                "page_number": page_num,
                "title": f"Map (Page {page_num})",
                "width": pix.width,
                "height": pix.height,
                "file_size": os.path.getsize(map_path),
                "is_full_page": True,
                **color_info,
            }
        except Exception as e:
            print(f"Error rendering page {page_num} as map: {e}")
            return None

    def _extract_cover(self, doc: fitz.Document, images_dir: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Render the first page as a cover image."""
        try:
            first_page = doc[0]

            # Render at high resolution (300 DPI) for quality
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = first_page.get_pixmap(matrix=mat)

            cover_filename = f"{document_id}_cover.png"
            cover_path = os.path.join(images_dir, cover_filename)
            pix.save(cover_path)

            # Analyze color
            color_info = self._analyze_image_colors(cover_path)

            return {
                "image_path": cover_path,
                "image_type": "cover",
                "page_number": 1,
                "title": "Cover",
                "width": pix.width,
                "height": pix.height,
                "file_size": os.path.getsize(cover_path),
                **color_info,
            }
        except Exception as e:
            print(f"Error extracting cover: {e}")
            return None

    def _extract_page_images(
        self, page: fitz.Page, page_num: int, images_dir: str, document_id: str
    ) -> List[Dict[str, Any]]:
        """Extract embedded images from a page with color analysis."""
        extracted = []

        try:
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                xref = img[0]

                try:
                    base_image = page.parent.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image.get("ext", "png")

                    # Skip very small images (icons, bullets, etc.)
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Only keep images that are reasonably large (likely maps or illustrations)
                    if width < 100 or height < 100:
                        continue

                    # Calculate aspect ratio to help classify
                    aspect_ratio = width / height if height > 0 else 1

                    # Classify image type based on size and aspect ratio
                    image_type = self._classify_image(width, height, aspect_ratio, page_num)

                    # Generate filename
                    img_filename = f"{document_id}_p{page_num}_{img_index}.{image_ext}"
                    img_path = os.path.join(images_dir, img_filename)

                    # Save the image
                    with open(img_path, "wb") as f:
                        f.write(image_bytes)

                    # Analyze colors
                    color_info = self._analyze_image_colors(img_path)

                    extracted.append({
                        "image_path": img_path,
                        "image_type": image_type,
                        "page_number": page_num,
                        "title": None,  # Will be set by LLM during adventure parsing
                        "width": width,
                        "height": height,
                        "file_size": len(image_bytes),
                        **color_info,
                    })

                except Exception as e:
                    print(f"Error extracting image {xref} from page {page_num}: {e}")
                    continue

        except Exception as e:
            print(f"Error getting images from page {page_num}: {e}")

        return extracted

    def _classify_image(self, width: int, height: int, aspect_ratio: float, page_num: int) -> str:
        """Classify an image as map, illustration, or table based on characteristics."""
        # Large, roughly square or wide images are often maps
        if width > 400 and height > 400:
            if 0.5 < aspect_ratio < 2.0:
                return "map"

        # Very wide images might be tables or banners
        if aspect_ratio > 3.0:
            return "table"

        # Default to illustration
        return "illustration"

    def _analyze_image_colors(self, image_path: str) -> Dict[str, Any]:
        """Analyze image colors to extract palette and determine if color/grayscale.

        Returns:
            Dict with:
            - is_color: bool - True if image has color, False if grayscale/B&W
            - dominant_colors: List of top 5 hex colors
            - color_palette: List of RGB tuples
            - brightness: float 0-1 (0=dark, 1=bright)
        """
        try:
            img = Image.open(image_path)

            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            elif img.mode == 'L':
                # Already grayscale
                return {
                    "is_color": False,
                    "dominant_colors": ["#808080"],
                    "color_palette": [(128, 128, 128)],
                    "brightness": self._calculate_brightness(img),
                }

            # Resize for faster processing
            img_small = img.copy()
            img_small.thumbnail((150, 150))

            # Check if image is grayscale (R ≈ G ≈ B for most pixels)
            is_color = self._is_color_image(img_small)

            # Extract dominant colors using quantization
            dominant_colors, color_palette = self._extract_color_palette(img_small)

            # Calculate overall brightness
            brightness = self._calculate_brightness(img_small)

            return {
                "is_color": is_color,
                "dominant_colors": dominant_colors,
                "color_palette": color_palette,
                "brightness": brightness,
            }

        except Exception as e:
            print(f"Error analyzing image colors: {e}")
            return {
                "is_color": None,
                "dominant_colors": [],
                "color_palette": [],
                "brightness": None,
            }

    def _is_color_image(self, img: Image.Image) -> bool:
        """Determine if an image has significant color or is grayscale."""
        try:
            pixels = list(img.getdata())

            # Sample pixels for performance
            sample_size = min(1000, len(pixels))
            step = max(1, len(pixels) // sample_size)
            sampled = pixels[::step]

            color_pixels = 0
            for pixel in sampled:
                if isinstance(pixel, tuple) and len(pixel) >= 3:
                    r, g, b = pixel[:3]
                    # Check if R, G, B values differ significantly (color)
                    max_diff = max(abs(r - g), abs(g - b), abs(r - b))
                    if max_diff > 20:  # Threshold for "colorful"
                        color_pixels += 1

            # If more than 10% of pixels are colorful, it's a color image
            return color_pixels / len(sampled) > 0.10

        except Exception:
            return True  # Assume color on error

    def _extract_color_palette(self, img: Image.Image, num_colors: int = 5) -> tuple:
        """Extract dominant colors from image using quantization.

        Returns:
            Tuple of (hex_colors, rgb_tuples)
        """
        try:
            # Quantize to reduce colors
            quantized = img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
            palette = quantized.getpalette()

            if not palette:
                return ([], [])

            # Extract RGB values from palette
            colors_rgb = []
            for i in range(num_colors):
                r = palette[i * 3]
                g = palette[i * 3 + 1]
                b = palette[i * 3 + 2]
                colors_rgb.append((r, g, b))

            # Convert to hex
            colors_hex = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in colors_rgb]

            return (colors_hex, colors_rgb)

        except Exception as e:
            print(f"Error extracting color palette: {e}")
            return ([], [])

    def _calculate_brightness(self, img: Image.Image) -> float:
        """Calculate overall image brightness (0=dark, 1=bright)."""
        try:
            # Convert to grayscale for brightness calculation
            gray = img.convert('L')
            pixels = list(gray.getdata())

            # Average pixel value normalized to 0-1
            avg = sum(pixels) / len(pixels)
            return round(avg / 255, 2)

        except Exception:
            return 0.5  # Default to middle brightness

    def extract_cover_only(self, file_path: str, document_id: str) -> Optional[str]:
        """Quick extraction of just the cover image. Returns the cover path."""
        images_dir = os.path.join(settings.pdf_storage_path, "images", document_id)
        os.makedirs(images_dir, exist_ok=True)

        try:
            doc = fitz.open(file_path)
            result = self._extract_cover(doc, images_dir, document_id)
            doc.close()

            if result:
                return result["image_path"]
        except Exception as e:
            print(f"Error extracting cover: {e}")

        return None
