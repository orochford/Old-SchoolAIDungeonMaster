"""Semantic chunking optimized for RPG adventure modules.

This chunker is designed to work with markdown output from pymupdf4llm,
preserving the structure of adventure modules including:
- Room/location entries
- Monster stat blocks
- Tables (wandering monsters, treasure, etc.)
- Hierarchical section context
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings


class SemanticChunker:
    """Chunk text semantically for RPG adventure modules.

    Optimized for content extracted via pymupdf4llm which outputs markdown.
    """

    # Markdown header patterns (from pymupdf4llm output)
    MARKDOWN_HEADERS = [
        (r'^(#{1})\s+(.+)$', 1),   # # Header (level 1)
        (r'^(#{2})\s+(.+)$', 2),   # ## Header (level 2)
        (r'^(#{3})\s+(.+)$', 3),   # ### Header (level 3)
        (r'^(#{4})\s+(.+)$', 4),   # #### Header (level 4)
    ]

    # Location/room patterns common in adventure modules
    LOCATION_PATTERNS = [
        r'^(\d+)\.\s+(.+)$',                    # "1. Entry Hall"
        r'^(\d+[a-z]?)\.\s+(.+)$',              # "1a. Secret Alcove"
        r'^Area\s+(\d+[a-z]?):\s*(.*)$',        # "Area 3: Guard Room"
        r'^Room\s+(\d+[a-z]?):\s*(.*)$',        # "Room 3: Guard Room"
        r'^Room\s+(\d+[a-z]?)\s*[-–—]\s*(.+)$', # "Room 3 - Guard Room"
        r'^Location\s+(\d+[a-z]?):\s*(.*)$',    # "Location 3: Tower"
        r'^(\d+)\)\s+(.+)$',                    # "1) Entry Hall"
        r'^([A-Z])\.\s+(.+)$',                  # "A. Main Entrance"
        r'^Level\s+(\d+):\s*(.*)$',             # "Level 2: Crypts"
    ]

    # Stat block indicators - if 3+ found, likely a stat block
    STAT_BLOCK_MARKERS = [
        r'AC\s*[:=]?\s*\d+',
        r'HD\s*[:=]?\s*\d+',
        r'HP\s*[:=]?\s*\d+',
        r'hp\s*[:=]?\s*\d+',
        r'Hit\s+Dice\s*[:=]?\s*\d+',
        r'Armor\s+Class\s*[:=]?\s*\d+',
        r'THAC0\s*[:=]?\s*\d+',
        r'Attacks?\s*[:=]',
        r'Damage\s*[:=]',
        r'Movement\s*[:=]',
        r'MV\s*[:=]?\s*\d+',
        r'Morale\s*[:=]?\s*\d+',
        r'ML\s*[:=]?\s*\d+',
        r'Save\s*[:=]?\s*[A-Z]',
        r'Alignment\s*[:=]',
        r'AL\s*[:=]?\s*[LCNE]',
        r'XP\s*[:=]?\s*\d+',
        r'Treasure\s+Type\s*[:=]',
        r'No\.\s+Appearing',
        r'#\s*App',
    ]

    # Table detection
    TABLE_PATTERNS = [
        r'^\|.+\|$',           # Markdown table row
        r'^[-|:]+$',           # Markdown table separator
        r'^\d+[-–]\d+\s+',     # Dice range start (wandering monster tables)
    ]

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

    def chunk(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Chunk pages into semantic units optimized for RPG content."""
        # Combine all pages into one document
        full_text = "\n\n".join(p["content"] for p in pages)
        page_map = self._build_page_map(pages)

        # Parse into hierarchical structure
        sections = self._parse_sections(full_text)

        # Convert sections to chunks with context
        chunks = []
        for section in sections:
            section_chunks = self._section_to_chunks(section, page_map)
            chunks.extend(section_chunks)

        return chunks

    def _build_page_map(self, pages: List[Dict[str, Any]]) -> Dict[int, int]:
        """Build a map of character positions to page numbers."""
        page_map = {}
        pos = 0
        for page in pages:
            page_num = page["page_number"]
            content_len = len(page["content"]) + 2  # +2 for \n\n separator
            for i in range(content_len):
                page_map[pos + i] = page_num
            pos += content_len
        return page_map

    def _get_page_for_position(self, pos: int, page_map: Dict[int, int]) -> int:
        """Get page number for a character position."""
        # Find closest position
        if pos in page_map:
            return page_map[pos]
        # Find nearest
        positions = sorted(page_map.keys())
        for p in positions:
            if p >= pos:
                return page_map[p]
        return page_map.get(positions[-1], 1) if positions else 1

    def _parse_sections(self, text: str) -> List[Dict[str, Any]]:
        """Parse text into hierarchical sections."""
        sections = []
        lines = text.split('\n')

        current_section = {
            "level": 0,
            "title": "Document",
            "content": "",
            "children": [],
            "is_location": False,
            "location_id": None,
            "is_stat_block": False,
            "is_table": False,
            "start_pos": 0,
        }

        section_stack = [current_section]
        char_pos = 0

        i = 0
        while i < len(lines):
            line = lines[i]
            line_start_pos = char_pos
            char_pos += len(line) + 1  # +1 for \n

            # Check for markdown headers
            header_match = self._match_header(line)
            if header_match:
                level, title = header_match
                new_section = {
                    "level": level,
                    "title": title,
                    "content": "",
                    "children": [],
                    "is_location": False,
                    "location_id": None,
                    "is_stat_block": False,
                    "is_table": False,
                    "start_pos": line_start_pos,
                }

                # Pop stack until we find parent
                while len(section_stack) > 1 and section_stack[-1]["level"] >= level:
                    section_stack.pop()

                section_stack[-1]["children"].append(new_section)
                section_stack.append(new_section)
                i += 1
                continue

            # Check for location entries
            location_match = self._match_location(line)
            if location_match:
                loc_id, loc_title = location_match
                new_section = {
                    "level": 10,  # High level to be child of any header
                    "title": f"{loc_id}. {loc_title}" if loc_title else f"Location {loc_id}",
                    "content": "",
                    "children": [],
                    "is_location": True,
                    "location_id": loc_id,
                    "is_stat_block": False,
                    "is_table": False,
                    "start_pos": line_start_pos,
                }

                # Locations are usually at the same level as each other
                while len(section_stack) > 1 and section_stack[-1].get("is_location"):
                    section_stack.pop()

                section_stack[-1]["children"].append(new_section)
                section_stack.append(new_section)
                i += 1
                continue

            # Check for table start
            if self._is_table_line(line):
                table_lines = [line]
                j = i + 1
                while j < len(lines) and self._is_table_line(lines[j]):
                    table_lines.append(lines[j])
                    char_pos += len(lines[j]) + 1
                    j += 1

                table_content = '\n'.join(table_lines)
                new_section = {
                    "level": 11,
                    "title": "Table",
                    "content": table_content,
                    "children": [],
                    "is_location": False,
                    "location_id": None,
                    "is_stat_block": False,
                    "is_table": True,
                    "start_pos": line_start_pos,
                }
                section_stack[-1]["children"].append(new_section)
                i = j
                continue

            # Regular content - add to current section
            if section_stack:
                section_stack[-1]["content"] += line + '\n'

            i += 1

        # Post-process to detect stat blocks
        self._detect_stat_blocks(section_stack[0])

        return [section_stack[0]]

    def _match_header(self, line: str) -> Optional[Tuple[int, str]]:
        """Match markdown header, return (level, title) or None."""
        line = line.strip()
        for pattern, level in self.MARKDOWN_HEADERS:
            match = re.match(pattern, line)
            if match:
                return (level, match.group(2).strip())

        # Also match ALL CAPS lines as level 2
        if line.isupper() and len(line) > 3 and len(line) < 50:
            return (2, line)

        return None

    def _match_location(self, line: str) -> Optional[Tuple[str, str]]:
        """Match location entry, return (id, title) or None."""
        line = line.strip()
        for pattern in self.LOCATION_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return (match.group(1), match.group(2).strip() if match.lastindex >= 2 else "")
        return None

    def _is_table_line(self, line: str) -> bool:
        """Check if line is part of a markdown table."""
        line = line.strip()
        if not line:
            return False
        for pattern in self.TABLE_PATTERNS:
            if re.match(pattern, line):
                return True
        return False

    def _detect_stat_blocks(self, section: Dict[str, Any]) -> None:
        """Recursively detect and mark stat blocks in sections."""
        content = section.get("content", "")
        markers_found = sum(1 for p in self.STAT_BLOCK_MARKERS if re.search(p, content, re.IGNORECASE))

        if markers_found >= 3:
            section["is_stat_block"] = True

        for child in section.get("children", []):
            self._detect_stat_blocks(child)

    def _section_to_chunks(
        self,
        section: Dict[str, Any],
        page_map: Dict[int, int],
        parent_context: str = "",
    ) -> List[Dict[str, Any]]:
        """Convert a section tree into chunks with hierarchical context."""
        chunks = []

        # Build context string from parent
        current_context = parent_context
        if section["title"] and section["title"] != "Document":
            if current_context:
                current_context += " > " + section["title"]
            else:
                current_context = section["title"]

        # Get page numbers
        start_page = self._get_page_for_position(section["start_pos"], page_map)

        # Handle content of this section
        content = section.get("content", "").strip()
        if content:
            # Stat blocks and tables should not be split
            if section["is_stat_block"] or section["is_table"]:
                chunk_content = content
                if current_context:
                    chunk_content = f"[{current_context}]\n\n{content}"

                chunks.append({
                    "content": chunk_content,
                    "start_page": start_page,
                    "end_page": start_page,
                    "metadata": {
                        "context": current_context,
                        "is_location": section["is_location"],
                        "location_id": section["location_id"],
                        "is_stat_block": section["is_stat_block"],
                        "is_table": section["is_table"],
                        "title": section["title"],
                    },
                })
            else:
                # Regular content - may need to split
                section_chunks = self._split_content(
                    content,
                    current_context,
                    start_page,
                    section,
                )
                chunks.extend(section_chunks)

        # Process children
        for child in section.get("children", []):
            child_chunks = self._section_to_chunks(child, page_map, current_context)
            chunks.extend(child_chunks)

        return chunks

    def _split_content(
        self,
        content: str,
        context: str,
        start_page: int,
        section: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Split content into appropriately sized chunks."""
        chunks = []

        # Calculate effective chunk size accounting for context prefix
        context_prefix = f"[{context}]\n\n" if context else ""
        effective_size = self.chunk_size - len(context_prefix)

        if len(content) <= effective_size:
            # Fits in one chunk
            chunk_content = context_prefix + content if context else content
            chunks.append({
                "content": chunk_content,
                "start_page": start_page,
                "end_page": start_page,
                "metadata": {
                    "context": context,
                    "is_location": section.get("is_location", False),
                    "location_id": section.get("location_id"),
                    "is_stat_block": section.get("is_stat_block", False),
                    "is_table": section.get("is_table", False),
                    "title": section.get("title", ""),
                },
            })
        else:
            # Split by paragraphs
            paragraphs = re.split(r'\n\s*\n', content)
            current_chunk = ""

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # Check if adding this paragraph exceeds limit
                if len(current_chunk) + len(para) + 2 > effective_size:
                    if current_chunk:
                        chunk_content = context_prefix + current_chunk if context else current_chunk
                        chunks.append({
                            "content": chunk_content,
                            "start_page": start_page,
                            "end_page": start_page,
                            "metadata": {
                                "context": context,
                                "is_location": section.get("is_location", False),
                                "location_id": section.get("location_id"),
                                "is_stat_block": False,
                                "is_table": False,
                                "title": section.get("title", ""),
                            },
                        })

                        # Start new chunk with overlap
                        overlap = self._get_overlap(current_chunk)
                        current_chunk = overlap + "\n\n" + para if overlap else para
                    else:
                        # Single paragraph too large - split by sentences
                        current_chunk = para
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + para
                    else:
                        current_chunk = para

            # Don't forget last chunk
            if current_chunk.strip():
                chunk_content = context_prefix + current_chunk if context else current_chunk
                chunks.append({
                    "content": chunk_content,
                    "start_page": start_page,
                    "end_page": start_page,
                    "metadata": {
                        "context": context,
                        "is_location": section.get("is_location", False),
                        "location_id": section.get("location_id"),
                        "is_stat_block": False,
                        "is_table": False,
                        "title": section.get("title", ""),
                    },
                })

        return chunks

    def _get_overlap(self, text: str) -> str:
        """Get overlap text from the end of a chunk."""
        if len(text) <= self.chunk_overlap:
            return text

        # Get last N characters
        overlap = text[-self.chunk_overlap:]

        # Try to break at a good point
        for sep in ['\n\n', '\n', '. ', ', ']:
            idx = overlap.find(sep)
            if idx > 0:
                return overlap[idx + len(sep):]

        return overlap
