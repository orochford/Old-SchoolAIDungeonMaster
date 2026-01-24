"""Regex-based preprocessing for B/X adventure module parsing.

Pre-processes adventure markdown to identify document sections before LLM extraction.
This dramatically improves extraction accuracy by:
1. Identifying document structure (rooms vs monster lists vs treasure)
2. Extracting rooms via regex patterns
3. Extracting wandering monster tables directly
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger(__name__)


class AdventurePreprocessor:
    """Pre-process adventure markdown to identify sections before LLM extraction."""

    # Section header patterns for B/X modules
    # Match both markdown headers (#### **TEXT**) and bold-only (**TEXT**)
    ENCOUNTER_AREAS_PATTERN = re.compile(
        r'(?:^|\n)(?:#*\s*)?\*?\*?(?:ENCOUNTER AREAS|KEY TO (?:THE )?(?:UPPER|LOWER|FIRST|SECOND|THIRD) LEVEL|'
        r'KEYED LOCATIONS|DUNGEON KEY|ROOM DESCRIPTIONS)\*?\*?',
        re.IGNORECASE | re.MULTILINE
    )

    WANDERING_HEADER_PATTERN = re.compile(
        r'(?:^|\n)(?:#*\s*)?\*?\*?WANDERING MONSTERS?\*?\*?',
        re.IGNORECASE | re.MULTILINE
    )

    MONSTER_LIST_PATTERN = re.compile(
        r'(?:^|\n)#+\s*\*?\*?(?:MONSTERS?|DM\'?S? MONSTERS?|MONSTER (?:LIST|PLACEMENT))\*?\*?',
        re.IGNORECASE | re.MULTILINE
    )

    TREASURE_LIST_PATTERN = re.compile(
        r'(?:^|\n)#+\s*\*?\*?(?:TREASURE|DM\'?S? TREASURE|TREASURE (?:LIST|PLACEMENT))\*?\*?',
        re.IGNORECASE | re.MULTILINE
    )

    # Room entry patterns - multiple patterns to handle different formats
    # Pattern 1: "1. ALCOVES. There are three pairs..." (classic B/X format)
    # Pattern 2: "1. **ALCOVES.** There are..." (bold markdown)
    # Pattern 3: "Area 1: The Entrance Hall" (named area format)

    # Key insight: Room names are ALL CAPS or Title Case, followed by descriptions
    # Monster stats have parenthetical counts and stat blocks (AC, HD, hp)

    ROOM_PATTERNS = [
        # Combined rooms FIRST (more specific): "15. & 16. TELEPORTATION ROOMS."
        # Must be checked before single-room patterns
        # NOTE: Use \Z instead of $ to match absolute end of string, not end of each line
        # (MULTILINE mode makes $ match at each line end, breaking non-greedy capture)
        re.compile(
            r"^(\d+)\.\s*&\s*(\d+)\.\s+([A-Z][A-Z\s']+)\.?\s+(.+?)(?=(?:^|\n)\d+\.\s+[A-Z]|\Z)",
            re.MULTILINE | re.DOTALL
        ),
        # Classic: NUMBER. ALL CAPS NAME. Description
        # Name can include apostrophe+s (WIZARD'S) and spaces
        re.compile(
            r"^(\d+)\.\s+([A-Z][A-Z\s']+(?:'[Ss])?[A-Z\s]*)\.?\s+(.+?)(?=(?:^|\n)\d+\.\s+[A-Z]|\Z)",
            re.MULTILINE | re.DOTALL
        ),
        # Bold markdown: NUMBER. **NAME.** Description
        re.compile(
            r'^\*?\*?(\d+)\.\s*\*?\*?([A-Z][A-Za-z\s\'-]+?)\*?\*?\.?\s*(.+?)(?=(?:^|\n)\*?\*?\d+\.|\Z)',
            re.MULTILINE | re.DOTALL
        ),
    ]

    # Monster stat line pattern - used to FILTER OUT false positives
    MONSTER_STAT_PATTERN = re.compile(
        r'^\d+\.\s+[A-Za-z][a-z]+.*?\([^)]*\)\s*[-—]\s*AC\s*\d',
        re.MULTILINE
    )

    # Wandering monster entry pattern with stats
    # Matches: "1. Orcs (1-4)-AC 6, HD 1, hp 4 each..."
    WANDERING_ENTRY_PATTERN = re.compile(
        r'^(\d+)\.\s+([A-Za-z][A-Za-z\s]+?)\s*\(([^)]+)\)\s*[-—]\s*'
        r'AC\s*(\d+),?\s*'
        r'HD\s*([\d/]+),?\s*'
        r'(?:hp\s*([\d\s,each]+),?\s*)?'
        r'(?:#AT\s*(\d+),?\s*)?'
        r'(?:D\s*([\d\-d+]+),?\s*)?'
        r'(?:MV\s*([\d\'()]+),?\s*)?'
        r'(?:Save\s*([A-Z]+\d*),?\s*)?'
        r'(?:ML\s*(\d+),?\s*)?'
        r'(?:AL\s*([A-Z]),?\s*)?'
        r'(?:XP\s*(\d+)\s*)?'
        r'(.+?)(?=^\d+\.|$)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    # Simpler wandering entry pattern for different formats
    WANDERING_ENTRY_SIMPLE = re.compile(
        r'^(\d+)\.\s+([A-Za-z][A-Za-z\s]+?)(?:\s*\(([^)]+)\))?\s*[-—:]?\s*(.+?)(?=^\d+\.|$)',
        re.MULTILINE | re.DOTALL
    )

    # Monster stat block pattern
    STAT_BLOCK_PATTERN = re.compile(
        r'AC\s*(\d+).*?HD\s*([\d/]+).*?(?:hp\s*([\d\s,]+))?.*?'
        r'(?:#AT\s*(\d+))?.*?(?:D\s*([\d\-d+\s]+))?.*?'
        r'(?:MV\s*([\d\'()]+))?.*?(?:Save\s*([A-Z]+\d*))?.*?'
        r'(?:ML\s*(\d+))?',
        re.IGNORECASE | re.DOTALL
    )

    # Player background section patterns - for extracting player-facing intro text
    # Note: OCR may corrupt "PLAYER'S" to "you'" etc, so patterns are flexible
    PLAYER_BACKGROUND_PATTERNS = [
        # "BACKGROUND SHEET" - B1 style (may have prefix like "PLAYER'S" or corrupted "you'")
        re.compile(r'(?:^|\n)\*?\*?(?:[A-Za-z\']+\s+)?BACKGROUND\s+SHEET\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "BACKGROUND FOR PLAYERS"
        re.compile(r'(?:^|\n)\*?\*?(?:BACKGROUND\s+FOR\s+(?:THE\s+)?PLAYERS?)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "PLAYER INTRODUCTION" / "PLAYER'S BACKGROUND"
        re.compile(r'(?:^|\n)\*?\*?(?:PLAYER(?:\'?S?)?\s+(?:INTRODUCTION|BACKGROUND))\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "READ THIS TO PLAYERS" / "READ ALOUD TO PLAYERS"
        re.compile(r'(?:^|\n)\*?\*?(?:READ\s+(?:THIS\s+)?(?:TO\s+(?:THE\s+)?)?PLAYERS?|READ\s+ALOUD\s+(?:TO\s+)?PLAYERS?)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "PLAYERS' INFORMATION"
        re.compile(r'(?:^|\n)\*?\*?(?:PLAYERS?\'?\s+INFORMATION)\*?\*?', re.IGNORECASE | re.MULTILINE),
    ]

    # DM-only section patterns - match B/X module conventions
    DM_SECTION_PATTERNS = [
        # "NOTES FOR THE DUNGEON MASTER" - common in B/X modules
        re.compile(r'(?:^|\n)\*?\*?(?:NOTES?\s+FOR\s+THE\s+(?:DUNGEON\s+)?MASTER)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "DM'S NOTES" / "DM GUIDANCE" etc
        re.compile(r'(?:^|\n)(?:#*\s*)?\*?\*?(?:DM\'?S?\s+(?:NOTES?|GUIDANCE|INFORMATION|BACKGROUND))\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "FOR THE DUNGEON MASTER"
        re.compile(r'(?:^|\n)(?:#*\s*)?\*?\*?(?:FOR\s+THE\s+(?:DUNGEON\s+)?MASTER)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "RUNNING THE ADVENTURE/MODULE"
        re.compile(r'(?:^|\n)(?:#*\s*)?\*?\*?(?:RUNNING\s+(?:THE\s+)?(?:ADVENTURE|MODULE))\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "HOW TO BE AN EFFECTIVE DUNGEON MASTER" / "HOW TO USE THIS MODULE"
        re.compile(r'(?:^|\n)\*?\*?(?:HOW\s+TO\s+(?:BE\s+AN\s+EFFECTIVE\s+)?(?:DUNGEON\s+MASTER|USE\s+THIS\s+MODULE))\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "PREPARATION FOR THE USE OF THE MODULE"
        re.compile(r'(?:^|\n)\*?\*?(?:PREPARATION\s+FOR\s+(?:THE\s+)?(?:USE\s+OF\s+)?(?:THE\s+)?MODULE)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "KEYING THE DUNGEON" - DM instructions for placing monsters/treasure
        re.compile(r'(?:^|\n)\*?\*?(?:KEYING\s+THE\s+DUNGEON)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "MONSTER LIST" / "TREASURE LIST" - DM placement guides
        re.compile(r'(?:^|\n)\*?\*?(?:MONSTER\s+LIST|TREASURE\s+LIST)\*?\*?', re.IGNORECASE | re.MULTILINE),
        # "BACKGROUND" - often contains DM-only info
        re.compile(r'(?:^|\n)\*?\*?BACKGROUND\*?\*?\s*$', re.IGNORECASE | re.MULTILINE),
    ]

    def preprocess(self, markdown: str) -> Dict[str, Any]:
        """Main entry point - analyze and split document.

        Returns:
            Dict with:
                - sections: Dict mapping section names to (start, end) line ranges
                - rooms: List of extracted room dicts
                - wandering_tables: List of extracted wandering table dicts
                - outline: Document structure outline (headings hierarchy)
                - dm_sections: Identified DM-only sections
        """
        logger.info(f"Preprocessing document ({len(markdown)} chars)")

        sections = self.identify_sections(markdown)
        rooms = self.extract_rooms(markdown, sections)
        wandering_tables = self.extract_wandering_tables(markdown, sections)
        outline = self.extract_outline(markdown)
        dm_sections = self.identify_dm_sections(markdown)
        player_background = self.find_player_background_section(markdown)

        logger.info(f"Preprocessor found {len(rooms)} rooms, {len(wandering_tables)} wandering tables")
        logger.info(f"Preprocessor found {len(outline)} outline entries, {len(dm_sections)} DM sections")
        if player_background:
            logger.info(f"Preprocessor found player background section ({len(player_background)} chars)")

        return {
            'sections': sections,
            'rooms': rooms,
            'wandering_tables': wandering_tables,
            'outline': outline,
            'dm_sections': dm_sections,
            'player_background_section': player_background,
        }

    def extract_outline(self, text: str) -> List[Dict[str, Any]]:
        """Extract document structure as a heading hierarchy.

        Returns list of dicts with:
            - level: Heading level (1-6)
            - text: Heading text
            - position: Character position in document
        """
        outline = []

        # Match markdown headings (# to ######)
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+?)$', re.MULTILINE)

        for match in heading_pattern.finditer(text):
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            # Remove bold markers if present
            heading_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', heading_text)

            outline.append({
                'level': level,
                'text': heading_text,
                'position': match.start(),
            })

        # Also look for bold-only section headers (common in B/X modules)
        bold_header_pattern = re.compile(r'^(?!\s*#)\*\*([A-Z][A-Z\s]+)\*\*\s*$', re.MULTILINE)

        for match in bold_header_pattern.finditer(text):
            heading_text = match.group(1).strip()

            # Don't duplicate if already found as markdown heading
            is_duplicate = any(
                entry['text'].upper() == heading_text.upper()
                and abs(entry['position'] - match.start()) < 50
                for entry in outline
            )
            if not is_duplicate:
                outline.append({
                    'level': 2,  # Treat bold headers as level 2
                    'text': heading_text,
                    'position': match.start(),
                })

        # Sort by position
        outline.sort(key=lambda x: x['position'])

        return outline

    def identify_dm_sections(self, text: str) -> List[Dict[str, Any]]:
        """Identify sections meant only for the DM (not to be shared with players).

        Returns list of dicts with:
            - name: Section name
            - start: Start position
            - end: End position
            - type: Type of DM section (notes, guidance, background)
        """
        dm_sections = []

        for pattern in self.DM_SECTION_PATTERNS:
            for match in pattern.finditer(text):
                start = match.start()

                # Find end - next major section or ~5000 chars
                end = min(start + 5000, len(text))

                # Look for next major section header
                next_section = None
                for other_pattern in [self.ENCOUNTER_AREAS_PATTERN, self.WANDERING_HEADER_PATTERN]:
                    next_match = other_pattern.search(text, start + 50)
                    if next_match and next_match.start() < end:
                        end = next_match.start()
                        break

                # Determine section type
                section_text = match.group(0).lower()
                if 'note' in section_text:
                    section_type = 'notes'
                elif 'guidance' in section_text or 'running' in section_text:
                    section_type = 'guidance'
                else:
                    section_type = 'background'

                dm_sections.append({
                    'name': match.group(0).strip(),
                    'start': start,
                    'end': end,
                    'type': section_type,
                })

        return dm_sections

    def find_player_background_section(self, text: str) -> Optional[str]:
        """Find and extract dedicated player background sections.

        Searches for sections like "BACKGROUND SHEET", "BACKGROUND FOR PLAYERS",
        "PLAYER INTRODUCTION", etc. These are narrative text meant to be shared
        with players at adventure start.

        Returns:
            The full text of the section, or None if not found.
        """
        for pattern in self.PLAYER_BACKGROUND_PATTERNS:
            match = pattern.search(text)
            if match:
                start = match.start()

                # Find end - next major section header or ~5000 chars
                end = min(start + 5000, len(text))

                # Look for next section header to bound the extraction
                for other_pattern in [self.ENCOUNTER_AREAS_PATTERN, self.WANDERING_HEADER_PATTERN]:
                    next_match = other_pattern.search(text, start + 100)
                    if next_match and next_match.start() < end:
                        end = next_match.start()
                        break

                # Also check for DM sections that would end the player section
                for dm_pattern in self.DM_SECTION_PATTERNS:
                    next_match = dm_pattern.search(text, start + 100)
                    if next_match and next_match.start() < end:
                        end = next_match.start()
                        break

                section_text = text[start:end].strip()
                if len(section_text) > 100:  # Must be substantial
                    logger.info(f"Found player background section ({len(section_text)} chars)")
                    return section_text

        return None

    def identify_sections(self, text: str) -> Dict[str, Tuple[int, int]]:
        """Find character ranges for major sections.

        Returns dict mapping section name to (start_pos, end_pos) tuple.
        """
        sections = {}

        # Find encounter/room sections
        encounter_matches = list(self.ENCOUNTER_AREAS_PATTERN.finditer(text))
        for i, match in enumerate(encounter_matches):
            start = match.start()
            # End is either next section or end of document
            if i + 1 < len(encounter_matches):
                end = encounter_matches[i + 1].start()
            else:
                # Look for other section starts
                end = len(text)
                for pattern in [self.MONSTER_LIST_PATTERN, self.TREASURE_LIST_PATTERN]:
                    other = pattern.search(text, start + 100)
                    if other and other.start() < end:
                        end = other.start()

            section_name = f"encounter_areas_{i+1}"
            sections[section_name] = (start, end)
            logger.debug(f"Found section '{section_name}' at {start}-{end}")

        # Find wandering monster sections
        wandering_matches = list(self.WANDERING_HEADER_PATTERN.finditer(text))
        for i, match in enumerate(wandering_matches):
            start = match.start()
            # End is typically next major section or ~2000 chars
            end = min(start + 3000, len(text))

            # Look for next section header
            next_section = self.ENCOUNTER_AREAS_PATTERN.search(text, start + 50)
            if next_section and next_section.start() < end:
                end = next_section.start()

            section_name = f"wandering_{i+1}"
            sections[section_name] = (start, end)
            logger.debug(f"Found section '{section_name}' at {start}-{end}")

        # Find monster list sections (DM's monster placement)
        monster_matches = list(self.MONSTER_LIST_PATTERN.finditer(text))
        for i, match in enumerate(monster_matches):
            start = match.start()
            end = min(start + 5000, len(text))

            # Look for next section
            for pattern in [self.TREASURE_LIST_PATTERN, self.ENCOUNTER_AREAS_PATTERN]:
                next_section = pattern.search(text, start + 50)
                if next_section and next_section.start() < end:
                    end = next_section.start()

            section_name = f"monster_list_{i+1}"
            sections[section_name] = (start, end)

        # Find treasure list sections
        treasure_matches = list(self.TREASURE_LIST_PATTERN.finditer(text))
        for i, match in enumerate(treasure_matches):
            start = match.start()
            end = min(start + 5000, len(text))
            section_name = f"treasure_list_{i+1}"
            sections[section_name] = (start, end)

        return sections

    def extract_rooms(self, text: str, sections: Dict[str, Tuple[int, int]]) -> List[Dict[str, Any]]:
        """Extract room entries using regex.

        Returns list of dicts with:
            - location_key: Room number (e.g., "1", "38")
            - name: Room name (e.g., "ALCOVES", "ACCESS ROOM")
            - start_text: First ~100 chars of description
            - full_text: Complete room description text
            - is_sub_area: False (sub-areas detected by LLM)
            - parent_key: None
        """
        rooms = []
        seen_keys = set()

        # Focus on encounter area sections if found
        encounter_sections = [
            (name, start, end)
            for name, (start, end) in sections.items()
            if name.startswith('encounter_areas')
        ]

        if encounter_sections:
            # Extract from identified sections
            for section_name, start, end in encounter_sections:
                section_text = text[start:end]
                section_rooms = self._extract_rooms_from_text(section_text, seen_keys)

                # Determine dungeon level from section name/header
                level = self._determine_level_from_section(section_name, section_text)
                for room in section_rooms:
                    room['dungeon_level'] = level

                rooms.extend(section_rooms)
        else:
            # No sections identified, try full document
            logger.warning("No encounter sections found, searching full document")
            rooms = self._extract_rooms_from_text(text, seen_keys)

        # Sort by room number
        rooms.sort(key=lambda r: self._parse_room_number(r['location_key']))

        return rooms

    def _extract_rooms_from_text(self, text: str, seen_keys: set) -> List[Dict[str, Any]]:
        """Extract rooms from a text section."""
        rooms = []

        # Try each pattern until we find enough rooms
        for idx, pattern in enumerate(self.ROOM_PATTERNS):
            for match in pattern.finditer(text):
                groups = match.groups()

                # Handle combined rooms pattern (e.g., "15. & 16. NAME")
                # which has 4 groups: (num1, num2, name, desc) - now at index 0
                if idx == 0 and len(groups) == 4:
                    room_num = groups[0].strip()
                    room_num2 = groups[1].strip()
                    room_name = groups[2].strip()
                    room_desc = groups[3].strip()

                    # Skip if looks like monster stat entry
                    if self._is_monster_entry(room_name, room_desc):
                        continue

                    # Add entry for first room
                    if room_num not in seen_keys:
                        seen_keys.add(room_num)
                        rooms.append({
                            'location_key': room_num,
                            'name': room_name.title(),
                            'start_text': room_desc[:100].replace('\n', ' ').strip(),
                            'full_text': room_desc,
                            'is_sub_area': False,
                            'parent_key': None,
                            'dungeon_level': 1,
                        })

                    # Add entry for second room (linked to first)
                    if room_num2 not in seen_keys:
                        seen_keys.add(room_num2)
                        rooms.append({
                            'location_key': room_num2,
                            'name': room_name.title(),
                            'start_text': f"See room {room_num}. " + room_desc[:80].replace('\n', ' ').strip(),
                            'full_text': f"Combined with room {room_num}. {room_desc}",
                            'is_sub_area': False,
                            'parent_key': room_num,
                            'dungeon_level': 1,
                        })
                else:
                    # Standard 3-group pattern: (num, name, desc)
                    room_num = groups[0].strip()
                    room_name = groups[1].strip()
                    room_desc = groups[2].strip() if len(groups) > 2 else ""

                    # Skip if looks like monster stat entry
                    if self._is_monster_entry(room_name, room_desc):
                        continue

                    # Skip duplicates
                    if room_num in seen_keys:
                        continue
                    seen_keys.add(room_num)

                    rooms.append({
                        'location_key': room_num,
                        'name': room_name.title(),
                        'start_text': room_desc[:100].replace('\n', ' ').strip(),
                        'full_text': room_desc,
                        'is_sub_area': False,
                        'parent_key': None,
                        'dungeon_level': 1,
                    })

            # If we found a good number of rooms, stop trying patterns
            if len(rooms) >= 10:
                break

        return rooms

    def _is_monster_entry(self, name: str, desc: str) -> bool:
        """Check if entry looks like a monster stat block rather than a room."""
        combined = name + ' ' + desc[:150]
        combined_upper = combined.upper()

        # Monster entries typically have stats right at the start
        # Check for stat block indicators in first 80 chars
        stat_indicators = ['-AC ', 'AC:', 'AC ', 'HD:', 'HD ', '#AT', 'MV:', 'hp ', 'hp:']
        for indicator in stat_indicators:
            pos = combined_upper.find(indicator.upper())
            if pos != -1 and pos < 80:
                return True

        # Monster entries have parenthetical counts immediately after name: "Orcs (1-4)"
        # Rooms don't have this pattern
        if re.match(r'^[A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+)*\s*\(\d', combined):
            return True

        # Room names are typically ALL CAPS (ALCOVES, KITCHEN, WIZARD'S CHAMBER)
        # Monster names are Title Case or lowercase (Orcs, Giant Centipedes)
        # If name has lowercase letters (except after apostrophe), likely a monster
        name_clean = name.replace("'S", "").replace("'s", "")
        if name_clean and not name_clean.isupper():
            # Check if it's Title Case with lowercase - likely monster
            if re.match(r'^[A-Z][a-z]', name_clean):
                return True

        return False

    def _determine_level_from_section(self, section_name: str, section_text: str) -> int:
        """Determine dungeon level from section context."""
        text_lower = section_text[:500].lower()

        if 'upper level' in text_lower or 'first level' in text_lower:
            return 1
        elif 'lower level' in text_lower or 'second level' in text_lower:
            return 2
        elif 'third level' in text_lower:
            return 3

        # Check for room number ranges
        room_nums = [int(m.group(1)) for m in re.finditer(r'^(\d+)\.', section_text, re.MULTILINE)]
        if room_nums:
            min_room = min(room_nums)
            # Heuristic: rooms 1-37 typically level 1, 38+ level 2 in B/X
            if min_room >= 38:
                return 2

        return 1

    def _parse_room_number(self, key: str) -> tuple:
        """Parse room number for sorting (handles "1", "1a", "Area 1")."""
        # Extract numeric portion
        match = re.search(r'(\d+)([a-z])?', key, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            suffix = match.group(2) or ''
            return (num, suffix.lower())
        return (0, key)

    def extract_wandering_tables(
        self,
        text: str,
        sections: Dict[str, Tuple[int, int]]
    ) -> List[Dict[str, Any]]:
        """Extract wandering monster tables.

        Returns list of dicts with:
            - table_name: Name/tier of the table
            - die_roll: Die used (e.g., "1d6")
            - check_frequency: How often to check
            - dungeon_level: Which level this applies to
            - entries: List of monster entries with stats
        """
        tables = []

        # Find wandering monster sections
        wandering_sections = [
            (name, start, end)
            for name, (start, end) in sections.items()
            if name.startswith('wandering')
        ]

        if not wandering_sections:
            # Try to find wandering tables in full text
            wandering_matches = list(self.WANDERING_HEADER_PATTERN.finditer(text))
            for match in wandering_matches:
                start = match.start()
                end = min(start + 3000, len(text))
                wandering_sections.append((f"wandering_auto", start, end))

        for section_name, start, end in wandering_sections:
            section_text = text[start:end]
            table = self._extract_wandering_table(section_text, start)
            if table and table.get('entries'):
                tables.append(table)

        return tables

    def _extract_wandering_table(self, section_text: str, offset: int = 0) -> Optional[Dict[str, Any]]:
        """Extract a single wandering monster table from section text."""
        # Determine table name from header
        table_name = "Wandering Monsters"
        header_match = re.search(
            r'WANDERING MONSTERS?\s*[-—:]?\s*([^\n]*)',
            section_text,
            re.IGNORECASE
        )
        if header_match and header_match.group(1).strip():
            table_name = header_match.group(1).strip()

        # Determine dungeon level
        level = 1
        if 'upper' in section_text[:200].lower() or 'level 1' in section_text[:200].lower():
            level = 1
        elif 'lower' in section_text[:200].lower() or 'level 2' in section_text[:200].lower():
            level = 2

        # Find check frequency
        check_freq = None
        freq_match = re.search(
            r'(?:check|roll).*?(?:every|each)\s+(\d+)\s+turns?.*?(\d+)(?:\s*(?:in|on)[\s-]*(\d+))?',
            section_text[:500],
            re.IGNORECASE
        )
        if freq_match:
            turns = freq_match.group(1)
            chance = freq_match.group(2)
            die = freq_match.group(3) or '6'
            check_freq = f"Every {turns} turns, {chance}-in-{die} chance"

        # Determine die roll
        die_roll = "1d6"  # Default for B/X
        die_match = re.search(r'roll\s*(?:a\s*)?(\d*d\d+)', section_text[:300], re.IGNORECASE)
        if die_match:
            die_roll = die_match.group(1)

        # Extract entries
        entries = self._extract_wandering_entries(section_text)

        return {
            'table_name': table_name,
            'die_roll': die_roll,
            'check_frequency': check_freq,
            'dungeon_level': level,
            'entries': entries,
        }

    def _extract_wandering_entries(self, text: str) -> List[Dict[str, Any]]:
        """Extract individual wandering monster entries with stats."""
        entries = []

        # Try detailed pattern first
        for match in self.WANDERING_ENTRY_PATTERN.finditer(text):
            entry = self._parse_wandering_match(match)
            if entry:
                entries.append(entry)

        # If detailed pattern found few entries, try simpler pattern
        if len(entries) < 3:
            for match in self.WANDERING_ENTRY_SIMPLE.finditer(text):
                roll = match.group(1)
                name = match.group(2).strip()
                count = match.group(3) or "1"
                desc = match.group(4) or ""

                # Skip if already found
                if any(e.get('roll_range') == roll for e in entries):
                    continue

                # Try to extract stats from description
                stats = self._extract_stats_from_text(desc)

                entry = {
                    'roll_range': roll,
                    'name': name,
                    'count': count,
                    'description': desc[:500].strip(),
                    'creatures': [{
                        'name': name,
                        'count': count,
                        **stats
                    }]
                }
                entries.append(entry)

        return entries

    def _parse_wandering_match(self, match) -> Optional[Dict[str, Any]]:
        """Parse a regex match into a wandering entry dict."""
        try:
            roll = match.group(1)
            name = match.group(2).strip()
            count = match.group(3) or "1"
            ac = match.group(4)
            hd = match.group(5)
            hp = match.group(6)
            num_attacks = match.group(7)
            damage = match.group(8)
            move = match.group(9)
            save = match.group(10)
            morale = match.group(11)
            alignment = match.group(12)
            xp = match.group(13)
            extra = match.group(14) or ""

            creature = {
                'name': name,
                'count': count,
            }

            if ac:
                creature['ac'] = int(ac)
            if hd:
                creature['hd'] = hd
            if hp:
                creature['hp'] = hp.strip()
            if num_attacks:
                creature['attacks'] = [f"{num_attacks} attack{'s' if int(num_attacks) > 1 else ''}"]
            if damage:
                creature['damage'] = [damage]
            if move:
                creature['mv'] = move
            if save:
                creature['save'] = save
            if morale:
                creature['morale'] = int(morale)
            if alignment:
                creature['alignment'] = alignment
            if xp:
                creature['xp'] = int(xp)

            return {
                'roll_range': roll,
                'name': f"{name} ({count})",
                'count': count,
                'description': extra[:500].strip() if extra else None,
                'creatures': [creature]
            }
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse wandering entry: {e}")
            return None

    def _extract_stats_from_text(self, text: str) -> Dict[str, Any]:
        """Extract B/X stats from descriptive text."""
        stats = {}

        # AC
        ac_match = re.search(r'AC\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
        if ac_match:
            stats['ac'] = int(ac_match.group(1))

        # HD
        hd_match = re.search(r'HD\s*[:\s]?\s*([\d/]+)', text, re.IGNORECASE)
        if hd_match:
            stats['hd'] = hd_match.group(1)

        # HP
        hp_match = re.search(r'hp\s*[:\s]?\s*([\d,\s]+(?:each)?)', text, re.IGNORECASE)
        if hp_match:
            stats['hp'] = hp_match.group(1).strip()

        # Attacks
        at_match = re.search(r'#?AT\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
        if at_match:
            num = at_match.group(1)
            stats['attacks'] = [f"{num} attack{'s' if int(num) > 1 else ''}"]

        # Damage
        dmg_match = re.search(r'D(?:amage|MG)?\s*[:\s]?\s*([\dd\-+\s/]+)', text, re.IGNORECASE)
        if dmg_match:
            stats['damage'] = [dmg_match.group(1).strip()]

        # Movement
        mv_match = re.search(r'MV\s*[:\s]?\s*([\d\'()]+)', text, re.IGNORECASE)
        if mv_match:
            stats['mv'] = mv_match.group(1)

        # Save
        save_match = re.search(r'Save\s*[:\s]?\s*([A-Z]+\d*)', text, re.IGNORECASE)
        if save_match:
            stats['save'] = save_match.group(1)

        # Morale
        ml_match = re.search(r'ML\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
        if ml_match:
            stats['morale'] = int(ml_match.group(1))

        # XP
        xp_match = re.search(r'XP\s*[:\s]?\s*(\d+)', text, re.IGNORECASE)
        if xp_match:
            stats['xp'] = int(xp_match.group(1))

        return stats

    def get_room_text_for_llm(self, room: Dict[str, Any], context_chars: int = 500) -> str:
        """Get room text formatted for LLM extraction.

        Includes the room's full text plus some context about its structure.
        """
        text = f"Room {room['location_key']}: {room['name']}\n\n"
        text += room.get('full_text', room.get('start_text', ''))
        return text[:context_chars * 2]  # Allow some overflow

    def get_section_text(
        self,
        full_text: str,
        section_name: str,
        sections: Dict[str, Tuple[int, int]]
    ) -> Optional[str]:
        """Get text for a specific section."""
        if section_name in sections:
            start, end = sections[section_name]
            return full_text[start:end]
        return None
