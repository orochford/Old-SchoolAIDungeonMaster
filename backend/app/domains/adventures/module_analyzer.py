"""Module analyzer for pre-session analysis and B1-style blank room population."""

import logging
import os
import re
import json
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.adventures.models import AdventureModule, AdventureLocation, ParsingStatus
from app.domains.adventures.retriever import AdventureDataRetriever
from app.llm.client import ClaudeClient

logger = logging.getLogger(__name__)


class ModuleAnalyzer:
    """Analyzes adventure modules before gameplay for better LLM understanding.

    This class handles:
    - Pre-session module analysis
    - B1-style blank room population
    - Creating DM briefings
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.retriever = AdventureDataRetriever(db)
        self.client = ClaudeClient()

    async def analyze_module(self, module_id: UUID) -> Dict[str, Any]:
        """Create comprehensive module analysis for DM context.

        This creates a condensed "DM briefing" that includes:
        - Room connection graph
        - Key features and encounters
        - Plot points and triggers
        - For B1-style modules: populated blank rooms

        Args:
            module_id: The adventure module UUID

        Returns:
            Analysis dictionary to store in adventure_state
        """
        logger.info(f"[ModuleAnalyzer] Starting analysis for module {module_id}")

        # Get module data
        result = await self.db.execute(
            select(AdventureModule).where(AdventureModule.id == module_id)
        )
        module = result.scalar_one_or_none()

        if not module:
            logger.warning(f"[ModuleAnalyzer] Module {module_id} not found")
            return {}

        analysis = {
            "module_id": str(module_id),
            "module_title": module.title,
            "module_code": module.code,
            "analyzed": True,
        }

        # Build room connection graph
        connection_graph = await self._build_connection_graph(module_id)
        analysis["connection_graph"] = connection_graph

        # Get all locations for analysis
        locations = await self.retriever.get_all_locations(module_id)
        analysis["location_count"] = len(locations)

        # Check if this is a B1-style module with blank rooms
        blank_rooms = await self._identify_blank_rooms(module_id)
        if blank_rooms:
            logger.info(f"[ModuleAnalyzer] Found {len(blank_rooms)} blank rooms")
            analysis["has_blank_rooms"] = True
            analysis["blank_room_keys"] = [r["key"] for r in blank_rooms]

            # Extract monster and treasure lists if available
            monster_list = await self._extract_monster_list(module)
            treasure_list = await self._extract_treasure_list(module)

            if monster_list or treasure_list:
                analysis["monster_list"] = monster_list
                analysis["treasure_list"] = treasure_list

                # Populate blank rooms using LLM
                populated = await self.populate_blank_rooms(
                    module_id=module_id,
                    blank_rooms=blank_rooms,
                    monster_list=monster_list,
                    treasure_list=treasure_list,
                )
                analysis["populated_rooms"] = populated
        else:
            analysis["has_blank_rooms"] = False

        # Create DM briefing summary
        briefing = await self._create_dm_briefing(module, locations)
        analysis["dm_briefing"] = briefing

        logger.info(f"[ModuleAnalyzer] Analysis complete for {module.title}")
        return analysis

    async def _build_connection_graph(self, module_id: UUID) -> Dict[str, List[str]]:
        """Build a graph of room connections.

        Returns:
            Dict mapping location_key -> list of connected location_keys
        """
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
        )
        locations = list(result.scalars().all())

        graph = {}
        for loc in locations:
            connections = []
            exits = loc.exits if isinstance(loc.exits, dict) else {}

            for direction, dest_info in exits.items():
                # Extract location key from destination
                key_match = re.search(r'\b(\d+[a-z]?)\b', str(dest_info))
                if key_match:
                    connections.append(key_match.group(1))

            graph[loc.location_key] = connections

        return graph

    async def _identify_blank_rooms(self, module_id: UUID) -> List[Dict[str, Any]]:
        """Identify rooms that are blank/empty and need population.

        B1-style modules have rooms marked as blank or with minimal description,
        intended for the DM to populate using provided monster/treasure lists.

        Returns:
            List of blank room info dicts
        """
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
        )
        locations = list(result.scalars().all())

        blank_rooms = []
        blank_indicators = [
            "empty",
            "blank",
            "dm's choice",
            "dm choice",
            "to be stocked",
            "unstocked",
            "no encounter",
            "nothing of interest",
        ]

        for loc in locations:
            description = (loc.dm_description or "").lower()
            is_blank = False

            # Check for blank indicators in description
            for indicator in blank_indicators:
                if indicator in description:
                    is_blank = True
                    break

            # Also check if description is very short (< 50 chars often means blank)
            if len(description.strip()) < 50:
                is_blank = True

            # Check if no encounters, NPCs, or treasure
            if not loc.traps and not loc.secrets and not loc.treasure:
                # Could be a candidate for population
                pass

            if is_blank:
                blank_rooms.append({
                    "key": loc.location_key,
                    "name": loc.name,
                    "description": loc.dm_description,
                    "dungeon_level": loc.dungeon_level,
                    "tier": loc.tier,
                })

        return blank_rooms

    async def _extract_monster_list(self, module: AdventureModule) -> List[Dict[str, Any]]:
        """Extract the monster list from a B1-style module.

        B1 includes a "MONSTER LIST" section with creatures to distribute.
        """
        if not module.full_markdown_path or not os.path.exists(module.full_markdown_path):
            return []

        try:
            with open(module.full_markdown_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
        except Exception as e:
            logger.error(f"[ModuleAnalyzer] Failed to read module markdown: {e}")
            return []

        # Look for MONSTER LIST section
        patterns = [
            r'(?:MONSTER LIST|MONSTERS?\s+TO\s+(?:BE\s+)?(?:PLACED|USED))[\s:]*\n(.*?)(?=\n(?:TREASURE|[A-Z]{2,}\s+LIST)|$)',
            r'(?:^|\n)#+\s*Monster(?:s)?\s*(?:List)?[\s:]*\n(.*?)(?=\n#+|$)',
        ]

        monster_text = ""
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if match:
                monster_text = match.group(1)
                break

        if not monster_text:
            return []

        # Parse monster entries
        # Format varies but typically: "1. Orcs (3) - HD 1, HP 4, 3, 5"
        monsters = []
        lines = monster_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Try to parse monster entry
            # Common patterns: "1. Monster Name (count)" or "Monster Name: HD X, HP Y"
            entry_match = re.match(
                r'(?:\d+\.\s*)?([A-Za-z][A-Za-z\s]+?)(?:\s*\((\d+)\))?[\s:-]*(?:HD\s*(\d+))?',
                line
            )
            if entry_match:
                name = entry_match.group(1).strip()
                count = int(entry_match.group(2)) if entry_match.group(2) else 1
                hd = int(entry_match.group(3)) if entry_match.group(3) else 1

                monsters.append({
                    "name": name,
                    "count": count,
                    "hd": hd,
                    "raw_text": line,
                })

        logger.info(f"[ModuleAnalyzer] Extracted {len(monsters)} monsters from list")
        return monsters

    async def _extract_treasure_list(self, module: AdventureModule) -> List[Dict[str, Any]]:
        """Extract the treasure list from a B1-style module.

        B1 includes a "TREASURE LIST" section with items to distribute.
        """
        if not module.full_markdown_path or not os.path.exists(module.full_markdown_path):
            return []

        try:
            with open(module.full_markdown_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
        except Exception as e:
            logger.error(f"[ModuleAnalyzer] Failed to read module markdown: {e}")
            return []

        # Look for TREASURE LIST section
        patterns = [
            r'(?:TREASURE LIST|TREASURES?\s+TO\s+(?:BE\s+)?(?:PLACED|USED))[\s:]*\n(.*?)(?=\n(?:MONSTER|[A-Z]{2,}\s+LIST)|$)',
            r'(?:^|\n)#+\s*Treasure(?:s)?\s*(?:List)?[\s:]*\n(.*?)(?=\n#+|$)',
        ]

        treasure_text = ""
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if match:
                treasure_text = match.group(1)
                break

        if not treasure_text:
            return []

        # Parse treasure entries
        treasures = []
        lines = treasure_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Try to parse treasure entry
            # Common patterns: "1. 500 gp" or "Potion of Healing" or "100 gp in chest"
            treasures.append({
                "description": line,
                "raw_text": line,
            })

        logger.info(f"[ModuleAnalyzer] Extracted {len(treasures)} treasures from list")
        return treasures

    async def populate_blank_rooms(
        self,
        module_id: UUID,
        blank_rooms: List[Dict[str, Any]],
        monster_list: List[Dict[str, Any]],
        treasure_list: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Use LLM to distribute monsters and treasures to blank rooms.

        This follows B1's guidelines:
        - Not every room needs content
        - Harder monsters in deeper areas
        - Treasure should be guarded or hidden
        - Some rooms should remain empty for pacing

        Args:
            module_id: The module UUID
            blank_rooms: List of blank room info
            monster_list: Extracted monster list
            treasure_list: Extracted treasure list

        Returns:
            Dict mapping room_key -> populated content
        """
        if not blank_rooms:
            return {}

        if not monster_list and not treasure_list:
            logger.info("[ModuleAnalyzer] No monster/treasure lists - skipping population")
            return {}

        # Build prompt for LLM
        prompt = self._build_population_prompt(blank_rooms, monster_list, treasure_list)

        try:
            response = await self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.7,
            )

            # Extract JSON from response
            response_text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    response_text += block.get("text", "")

            # Parse JSON from response
            populated = self._parse_population_response(response_text)
            logger.info(f"[ModuleAnalyzer] Populated {len(populated)} rooms")
            return populated

        except Exception as e:
            logger.error(f"[ModuleAnalyzer] Failed to populate rooms: {e}")
            return {}

    def _build_population_prompt(
        self,
        blank_rooms: List[Dict[str, Any]],
        monster_list: List[Dict[str, Any]],
        treasure_list: List[Dict[str, Any]],
    ) -> str:
        """Build the prompt for room population."""
        rooms_text = "\n".join([
            f"- Room {r['key']}: {r['name']} (Level {r.get('dungeon_level', 1)})"
            for r in blank_rooms
        ])

        monsters_text = "\n".join([
            f"- {m['name']} (Count: {m['count']}, HD: {m['hd']})"
            for m in monster_list
        ]) if monster_list else "No monster list provided"

        treasures_text = "\n".join([
            f"- {t['description']}"
            for t in treasure_list
        ]) if treasure_list else "No treasure list provided"

        return f"""You are helping set up a B/X D&D adventure module for play.

The module has blank rooms that need to be populated with monsters and treasures.
Follow classic dungeon design principles:

GUIDELINES:
- Not every room needs content (30-40% should be empty for pacing)
- Place harder monsters (higher HD) on deeper dungeon levels
- Treasure should usually be guarded by monsters or hidden
- Some treasure can be unguarded but harder to find
- Create logical monster lairs (groups together, near water/food)
- Leave some monsters as patrols or wanderers

BLANK ROOMS TO POPULATE:
{rooms_text}

AVAILABLE MONSTERS:
{monsters_text}

AVAILABLE TREASURES:
{treasures_text}

Distribute the monsters and treasures appropriately. Return your assignments as JSON:

```json
{{
  "room_key": {{
    "monsters": [
      {{"name": "Orc", "count": 3, "hp": [4, 3, 5], "behavior": "guarding treasure"}}
    ],
    "treasure": [
      {{"item": "100 gp", "location": "in iron chest"}}
    ],
    "notes": "Orc lair with stolen gold"
  }},
  "another_room_key": {{
    "monsters": null,
    "treasure": null,
    "notes": "Left empty for pacing"
  }}
}}
```

Only include rooms that you're populating or explicitly leaving empty.
Be creative but follow the guidelines above."""

    def _parse_population_response(self, response_text: str) -> Dict[str, Dict[str, Any]]:
        """Parse the LLM's population response."""
        # Extract JSON from response
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_text = json_match.group(0)
            else:
                logger.warning("[ModuleAnalyzer] Could not find JSON in population response")
                return {}

        try:
            populated = json.loads(json_text)
            return populated
        except json.JSONDecodeError as e:
            logger.error(f"[ModuleAnalyzer] Failed to parse population JSON: {e}")
            return {}

    async def _create_dm_briefing(
        self,
        module: AdventureModule,
        locations: List[Dict[str, Any]],
    ) -> str:
        """Create a condensed DM briefing for the module.

        This summarizes key information the DM needs to run the adventure.
        """
        parts = []

        parts.append(f"# DM BRIEFING: {module.title}")
        if module.code:
            parts.append(f"Module: {module.code}")

        if module.dm_overview:
            parts.append(f"\n## Overview\n{module.dm_overview[:1000]}")

        if module.adventure_flow:
            parts.append(f"\n## Adventure Flow\n{module.adventure_flow[:1000]}")

        # Key locations summary
        parts.append(f"\n## Key Locations ({len(locations)} total)")
        # Highlight important locations (first 5 and any with special features)
        key_locs = locations[:5]
        for loc in key_locs:
            parts.append(f"- {loc['key']}: {loc['name']}")

        # Critical path if available
        if module.critical_path:
            parts.append(f"\n## Critical Path")
            for step in module.critical_path[:5]:
                parts.append(f"- {step}")

        return "\n".join(parts)

    async def get_populated_room_content(
        self,
        adventure_state: Dict[str, Any],
        room_key: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the populated content for a specific room.

        Args:
            adventure_state: Session adventure_state containing populated_rooms
            room_key: The room key to look up

        Returns:
            Dict with monsters, treasure, notes or None if not populated
        """
        populated = adventure_state.get("populated_rooms", {})
        return populated.get(room_key)
