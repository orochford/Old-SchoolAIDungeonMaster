"""Adventure data retriever for DM context building."""

from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, EncounterType, ParsingStatus,
)
from app.domains.sourcebooks.models import ExtractedImage
from app.rag.embeddings import EmbeddingService


class AdventureDataRetriever:
    """Retrieves structured adventure data for DM context."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService()

    async def get_module_for_document(self, document_id: UUID) -> Optional[AdventureModule]:
        """Get the parsed adventure module for a document."""
        result = await self.db.execute(
            select(AdventureModule)
            .where(AdventureModule.pdf_document_id == document_id)
            .where(AdventureModule.parsing_status == ParsingStatus.COMPLETED)
        )
        return result.scalar_one_or_none()

    async def get_module_maps(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Get map images for a module.

        Args:
            document_id: The PDF document ID

        Returns:
            List of map image data with paths, titles, and descriptions
        """
        result = await self.db.execute(
            select(ExtractedImage)
            .where(ExtractedImage.document_id == document_id)
            .where(ExtractedImage.image_type == "map")
            .order_by(ExtractedImage.page_number)
        )
        images = list(result.scalars().all())

        return [
            {
                "id": str(img.id),
                "path": img.image_path,
                "title": img.title or f"Map (page {img.page_number})",
                "description": img.description,
                "page_number": img.page_number,
                "width": img.width,
                "height": img.height,
            }
            for img in images
        ]

    async def get_adjacent_locations(
        self,
        module_id: UUID,
        location_key: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Get brief info about locations adjacent to the current one.

        Args:
            module_id: Adventure module UUID
            location_key: Current location key

        Returns:
            Dictionary mapping direction -> location brief info
        """
        # First get the current location to find its exits
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
            .where(AdventureLocation.location_key == location_key)
        )
        current_location = result.scalar_one_or_none()

        if not current_location or not current_location.exits:
            return {}

        adjacent = {}
        exits = current_location.exits if isinstance(current_location.exits, dict) else {}

        for direction, dest_info in exits.items():
            # Extract location key from destination info
            # dest_info might be "Room 2 (Kitchen)" or just "2" or "Kitchen"
            import re
            # Try to find a numeric key first
            key_match = re.search(r'\b(\d+[a-z]?)\b', str(dest_info))
            if key_match:
                dest_key = key_match.group(1)

                # Look up the adjacent location
                result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module_id)
                    .where(AdventureLocation.location_key == dest_key)
                )
                adj_location = result.scalar_one_or_none()

                if adj_location:
                    adjacent[direction] = {
                        "key": adj_location.location_key,
                        "name": adj_location.name,
                        "brief": adj_location.dm_description[:150] + "..." if adj_location.dm_description and len(adj_location.dm_description) > 150 else adj_location.dm_description,
                    }
                else:
                    # Couldn't find location, use the raw destination info
                    adjacent[direction] = {
                        "key": dest_key,
                        "name": dest_info,
                        "brief": None,
                    }
            else:
                # No numeric key found, just record the raw info
                adjacent[direction] = {
                    "key": None,
                    "name": dest_info,
                    "brief": None,
                }

        return adjacent

    async def get_location_context(
        self,
        module_id: UUID,
        location_key: str,
    ) -> Dict[str, Any]:
        """Get rich context for a location including NPCs, encounters, and items.

        Args:
            module_id: Adventure module UUID
            location_key: Location key (e.g., "1", "Area 1", "1a")

        Returns:
            Dictionary with location, npcs, encounters, items, and wandering_table
        """
        # Get the location
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
            .where(AdventureLocation.location_key == location_key)
        )
        location = result.scalar_one_or_none()

        if not location:
            return {}

        # Get NPCs at this location
        result = await self.db.execute(
            select(AdventureNPC).where(AdventureNPC.location_id == location.id)
        )
        npcs = list(result.scalars().all())

        # Get fixed encounters at this location
        result = await self.db.execute(
            select(AdventureEncounter)
            .where(AdventureEncounter.location_id == location.id)
            .where(AdventureEncounter.encounter_type == EncounterType.FIXED)
        )
        encounters = list(result.scalars().all())

        # Get items at this location
        result = await self.db.execute(
            select(AdventureItem).where(AdventureItem.location_id == location.id)
        )
        items = list(result.scalars().all())

        # Get wandering monster table for this tier/level
        wandering_encounters = []
        if location.tier:
            result = await self.db.execute(
                select(AdventureEncounter)
                .where(AdventureEncounter.module_id == module_id)
                .where(AdventureEncounter.encounter_type == EncounterType.WANDERING)
                .where(AdventureEncounter.wandering_table_name.ilike(f"%{location.tier}%"))
            )
            wandering_encounters = list(result.scalars().all())

        return {
            "location": self._format_location(location),
            "npcs": [self._format_npc(npc) for npc in npcs],
            "encounters": [self._format_encounter(enc) for enc in encounters],
            "items": [self._format_item(item) for item in items],
            "wandering_table": self._format_wandering_table(wandering_encounters) if wandering_encounters else None,
        }

    async def get_wandering_encounter(
        self,
        module_id: UUID,
        tier: Optional[str] = None,
        dungeon_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get the wandering monster table for an area.

        Args:
            module_id: Adventure module UUID
            tier: Optional tier name (e.g., "Upper Pyramid")
            dungeon_level: Optional dungeon level number

        Returns:
            Dictionary with wandering monster table data
        """
        base_query = (
            select(AdventureEncounter)
            .where(AdventureEncounter.module_id == module_id)
            .where(AdventureEncounter.encounter_type == EncounterType.WANDERING)
        )

        encounters = []

        # Try matching by tier name first
        if tier:
            query = base_query.where(AdventureEncounter.wandering_table_name.ilike(f"%{tier}%"))
            result = await self.db.execute(query.order_by(AdventureEncounter.roll_range))
            encounters = list(result.scalars().all())

        # If no match by tier, try matching by dungeon level
        if not encounters and dungeon_level:
            query = base_query.where(
                AdventureEncounter.wandering_table_name.ilike(f"%Level {dungeon_level}%")
            )
            result = await self.db.execute(query.order_by(AdventureEncounter.roll_range))
            encounters = list(result.scalars().all())

        # If still no match, get all wandering encounters for this module
        if not encounters:
            result = await self.db.execute(base_query.order_by(AdventureEncounter.roll_range))
            encounters = list(result.scalars().all())

        if not encounters:
            return {}

        return self._format_wandering_table(encounters)

    async def get_npc_context(
        self,
        module_id: UUID,
        npc_name: str,
    ) -> Dict[str, Any]:
        """Get full NPC data for roleplay.

        Args:
            module_id: Adventure module UUID
            npc_name: Name of the NPC

        Returns:
            Dictionary with NPC data for roleplay
        """
        result = await self.db.execute(
            select(AdventureNPC)
            .where(AdventureNPC.module_id == module_id)
            .where(AdventureNPC.name.ilike(f"%{npc_name}%"))
        )
        npc = result.scalar_one_or_none()

        if not npc:
            return {}

        return self._format_npc(npc)

    async def search_adventure(
        self,
        module_id: UUID,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search across all adventure content.

        Args:
            module_id: Adventure module UUID
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching content items
        """
        # Get query embedding
        query_embedding = await self.embedding_service.get_embedding(query)

        results = []

        # Search locations
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
            .where(AdventureLocation.embedding.isnot(None))
            .order_by(AdventureLocation.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        for loc in result.scalars():
            results.append({
                "type": "location",
                "key": loc.location_key,
                "name": loc.name,
                "content": loc.dm_description[:500],
                "data": self._format_location(loc),
            })

        # Search NPCs
        result = await self.db.execute(
            select(AdventureNPC)
            .where(AdventureNPC.module_id == module_id)
            .where(AdventureNPC.embedding.isnot(None))
            .order_by(AdventureNPC.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        for npc in result.scalars():
            results.append({
                "type": "npc",
                "name": npc.name,
                "content": npc.description[:500] if npc.description else "",
                "data": self._format_npc(npc),
            })

        # Search encounters
        result = await self.db.execute(
            select(AdventureEncounter)
            .where(AdventureEncounter.module_id == module_id)
            .where(AdventureEncounter.embedding.isnot(None))
            .order_by(AdventureEncounter.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        for enc in result.scalars():
            results.append({
                "type": "encounter",
                "name": enc.name,
                "content": enc.description[:500] if enc.description else "",
                "data": self._format_encounter(enc),
            })

        # Sort by relevance (already sorted by cosine distance within each type)
        # Just return top N overall
        return results[:limit]

    async def get_player_background(self, module_id: UUID) -> Optional[str]:
        """Get the player background text for session intro."""
        result = await self.db.execute(
            select(AdventureModule).where(AdventureModule.id == module_id)
        )
        module = result.scalar_one_or_none()
        return module.player_background if module else None

    async def get_module_summary(self, module_id: UUID) -> Dict[str, Any]:
        """Get module metadata summary."""
        result = await self.db.execute(
            select(AdventureModule).where(AdventureModule.id == module_id)
        )
        module = result.scalar_one_or_none()

        if not module:
            return {}

        return {
            "title": module.title,
            "code": module.code,
            "recommended_levels": f"{module.recommended_level_min or '?'}-{module.recommended_level_max or '?'}",
            "recommended_party_size": f"{module.recommended_party_size_min or '?'}-{module.recommended_party_size_max or '?'}",
            "summary": module.summary,
            "dm_overview": module.dm_overview,
            "adventure_flow": module.adventure_flow,
            "location_count": module.location_count,
            "npc_count": module.npc_count,
            "encounter_count": module.encounter_count,
        }

    async def get_all_locations(self, module_id: UUID) -> List[Dict[str, Any]]:
        """Get all locations in the module for DM reference.

        Returns a list of location briefs with key, name, and level info.
        """
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
            .order_by(AdventureLocation.dungeon_level, AdventureLocation.location_key)
        )
        locations = list(result.scalars().all())

        return [
            {
                "key": loc.location_key,
                "name": loc.name,
                "level": loc.dungeon_level,
                "tier": loc.tier,
            }
            for loc in locations
        ]

    def _format_location(self, location: AdventureLocation) -> Dict[str, Any]:
        """Format a location for DM context."""
        return {
            "key": location.location_key,
            "name": location.name,
            "dm_description": location.dm_description,
            "source_text": location.source_text,
            "read_aloud": location.read_aloud_text,
            "features": location.features,
            "exits": location.exits if isinstance(location.exits, dict) else {},
            "traps": location.traps,
            "secrets": location.secrets,
            "treasure": location.treasure,
            "dungeon_level": location.dungeon_level,
            "tier": location.tier,
        }

    def _format_npc(self, npc: AdventureNPC) -> Dict[str, Any]:
        """Format an NPC for DM context."""
        return {
            "name": npc.name,
            "title": npc.title,
            "description": npc.description,
            "appearance": npc.appearance,
            "personality": npc.personality,
            "motivation": npc.motivation,
            "goals": npc.goals,
            "dialogue_hooks": npc.dialogue_hooks,
            "stats": npc.stats,
            "equipment": npc.equipment,
            "treasure": npc.treasure,
            "spells": npc.spells,
            "faction": npc.faction,
            "disposition": npc.initial_disposition,
        }

    def _format_encounter(self, encounter: AdventureEncounter) -> Dict[str, Any]:
        """Format an encounter for DM context."""
        return {
            "name": encounter.name,
            "description": encounter.description,
            "creatures": encounter.creatures,
            "tactics": encounter.tactics,
            "treasure": encounter.treasure,
            "xp_value": encounter.xp_value,
            "trigger": encounter.trigger_condition,
        }

    def _format_item(self, item: AdventureItem) -> Dict[str, Any]:
        """Format an item for DM context."""
        return {
            "name": item.name,
            "type": item.item_type,
            "description": item.description,
            "value": item.value,
            "is_magical": item.is_magical,
            "magical_properties": item.magical_properties,
            "charges": item.charges,
            "is_key_item": item.is_key_item,
            "found_at": item.found_at,
        }

    def _format_wandering_table(self, encounters: List[AdventureEncounter]) -> Dict[str, Any]:
        """Format wandering monster table for DM context."""
        if not encounters:
            return {}

        first = encounters[0]
        return {
            "table_name": first.wandering_table_name,
            "die_roll": first.die_roll,
            "check_frequency": first.check_frequency,
            "entries": [
                {
                    "roll_range": enc.roll_range,
                    "name": enc.name,
                    "creatures": enc.creatures,
                    "tactics": enc.tactics,
                }
                for enc in encounters
            ],
        }
