"""Service for generating campaign framing for new adventures."""

import logging
import re
from typing import Dict, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.campaigns.models import Campaign
from app.domains.characters.models import Character
from app.domains.adventures.retriever import AdventureDataRetriever
from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.journal.models import JournalEntry

logger = logging.getLogger(__name__)


class CampaignFramingService:
    """Generate 'Adventure Awaits...' framing for new campaigns."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _transform_party_to_solo(self, text: str) -> str:
        """Transform party-oriented language to solo player language.

        Published adventure modules are written for groups, so they use phrases like
        "the party", "the adventurers", etc. This transforms those to "you" for solo play.
        """
        if not text:
            return text

        # Order matters - do more specific phrases first to avoid partial replacements
        replacements = [
            # Phrases with "party"
            (r"\beach member of (?:the |his |her |their )?party\b", "you"),
            (r"\bparty members\b", "you"),
            (r"\bthe party's\b", "your"),
            (r"\btheir party\b", "you"),
            (r"\bhis party\b", "you"),
            (r"\bher party\b", "you"),
            (r"\bthe party\b", "you"),
            (r"\ba party\b", "you"),
            # Phrases with "adventurers"
            (r"\bthe adventurers'\b", "your"),
            (r"\bthe adventurers\b", "you"),
            (r"\badventurers\b", "you"),
            # Phrases with "players" (game context, not character)
            (r"\bthe players'\b", "your"),
            (r"\bthe players\b", "you"),
            (r"\bplayers\b", "you"),
            # Phrases with "characters" (game context)
            (r"\bthe characters'\b", "your"),
            (r"\bthe characters\b", "you"),
            (r"\bplayer characters\b", "you"),
            (r"\bPCs\b", "you"),
            # Group references
            (r"\bthe group's\b", "your"),
            (r"\bthe group\b", "you"),
        ]

        result = text
        for pattern, replacement in replacements:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result

    async def generate_framing(
        self,
        campaign_id: UUID,
        character: Character,
        adventure_document_id: Optional[UUID],
        session_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate campaign framing data for a new adventure.

        Args:
            campaign_id: Campaign UUID
            character: Character model
            adventure_document_id: Adventure document UUID (optional)
            session_id: Session UUID for journal entry (optional)

        Returns:
            Dictionary with framing data, or None if no adventure module.
            - adventure_title: Module name
            - premise: Brief adventure hook
            - what_you_know: Player background from module (transformed to solo)
            - starting_situation: Where/why character is here
            - rumored_dangers: Known threats/warnings (optional)
        """
        if not adventure_document_id:
            return None

        # Get the adventure module
        retriever = AdventureDataRetriever(self.db)
        module = await retriever.get_module_for_document(adventure_document_id)

        if not module:
            logger.info(f"No parsed module found for document {adventure_document_id}")
            return None

        # Get module summary
        summary = await retriever.get_module_summary(module.id)

        # Get player background and transform to solo
        # Note: player_background should be populated during adventure parsing
        # via the preprocessor's find_player_background_section()
        raw_background = await retriever.get_player_background(module.id)
        player_background = self._transform_party_to_solo(raw_background) if raw_background else None

        # Get rumors table from module if available
        rumors = await self._get_rumors(module.id)

        # Get starting location info
        starting_location = await self._get_starting_location(module.id)

        # Build framing data
        framing = {
            "adventure_title": summary.get("title", "Unknown Adventure"),
            "adventure_code": summary.get("code"),
            "recommended_levels": summary.get("recommended_levels"),
            "premise": self._extract_premise(summary.get("summary", ""), player_background),
            "what_you_know": player_background,
            "starting_situation": self._build_starting_situation(
                character, starting_location, summary
            ),
            "character_name": character.name,
        }

        # Extract rumored dangers from background if present
        rumored_dangers = self._extract_dangers(player_background)
        if rumored_dangers:
            framing["rumored_dangers"] = rumored_dangers

        # Add rumors/legends if available (true ones only, for player knowledge)
        if rumors:
            framing["rumors"] = rumors

        # Save framing to journal for LLM context
        await self._save_framing_to_journal(
            campaign_id=campaign_id,
            character_id=character.id,
            session_id=session_id,
            framing=framing,
        )

        logger.info(f"Generated framing for campaign {campaign_id}: {framing.get('adventure_title')}")
        return framing

    async def _save_framing_to_journal(
        self,
        campaign_id: UUID,
        character_id: UUID,
        session_id: Optional[UUID],
        framing: Dict[str, Any],
    ) -> None:
        """Save campaign framing as a journal entry for LLM context."""
        # Build narrative content for the journal
        content_parts = []

        if framing.get("premise"):
            content_parts.append(framing["premise"])

        if framing.get("what_you_know"):
            content_parts.append(f"\nWhat you know:\n{framing['what_you_know']}")

        if framing.get("rumored_dangers"):
            dangers_text = "\n".join(f"- {d}" for d in framing["rumored_dangers"])
            content_parts.append(f"\nRumored dangers:\n{dangers_text}")

        content_parts.append(f"\n{framing.get('starting_situation', '')}")

        # Create journal entry
        journal_entry = JournalEntry(
            session_id=session_id,
            campaign_id=campaign_id,
            character_id=character_id,
            entry_type="key_event",
            title=f"Adventure Begins: {framing.get('adventure_title', 'Unknown')}",
            content="\n".join(content_parts),
            sequence=0,  # First entry
            entry_metadata={
                "event_type": "campaign_start",
                "adventure_title": framing.get("adventure_title"),
                "adventure_code": framing.get("adventure_code"),
                "recommended_levels": framing.get("recommended_levels"),
                "character_name": framing.get("character_name"),
                "rumored_dangers": framing.get("rumored_dangers"),
            },
        )

        self.db.add(journal_entry)
        await self.db.flush()
        logger.info(f"Saved campaign framing to journal for campaign {campaign_id}")

    async def _get_starting_location(self, module_id: UUID) -> Optional[Dict[str, Any]]:
        """Get the starting location for the adventure."""
        # Get first location (usually the entrance/start)
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
            .order_by(AdventureLocation.dungeon_level, AdventureLocation.location_key)
            .limit(1)
        )
        location = result.scalar_one_or_none()

        if not location:
            return None

        return {
            "key": location.location_key,
            "name": location.name,
            "description": location.dm_description[:200] if location.dm_description else None,
        }

    def _extract_premise(self, summary: str, background: Optional[str]) -> str:
        """Extract a brief premise/hook from the module data."""
        # Prefer the first 1-2 sentences from the summary
        if summary:
            # Split on sentence boundaries
            sentences = re.split(r'(?<=[.!?])\s+', summary)
            premise = " ".join(sentences[:2])
            if len(premise) > 300:
                premise = premise[:297] + "..."
            return premise

        # Fall back to first part of background
        if background:
            sentences = re.split(r'(?<=[.!?])\s+', background)
            premise = " ".join(sentences[:2])
            if len(premise) > 300:
                premise = premise[:297] + "..."
            return premise

        return "A mysterious adventure awaits..."

    def _build_starting_situation(
        self,
        character: Character,
        starting_location: Optional[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> str:
        """Build a description of the starting situation."""
        char_class = character.attributes.get("character_class", "adventurer")

        if starting_location:
            location_name = starting_location.get("name", "the adventure's entrance")
            return f"{character.name}, a level {character.level} {char_class}, stands ready at {location_name}."

        title = summary.get("title", "this adventure")
        return f"{character.name}, a level {character.level} {char_class}, has arrived to explore {title}."

    def _extract_dangers(self, background: Optional[str]) -> Optional[list]:
        """Extract mentioned dangers/threats from the background text."""
        if not background:
            return None

        dangers = []

        # Look for danger-related keywords
        danger_patterns = [
            r"(?:beware|danger|threat|warning|rumor[s]? speak of|legend tells of|tales of)[:\s]+([^.!?]+[.!?])",
            r"(?:monsters?|creatures?|beasts?|undead)[^.!?]*(?:lurk|haunt|dwell|infest)[^.!?]+[.!?]",
            r"(?:cursed?|haunted?|deadly|treacherous)[^.!?]+[.!?]",
        ]

        for pattern in danger_patterns:
            matches = re.findall(pattern, background, re.IGNORECASE)
            for match in matches:
                # Clean up the match
                danger = match.strip()
                if len(danger) > 20 and danger not in dangers:
                    dangers.append(danger)
                    if len(dangers) >= 3:
                        return dangers

        return dangers if dangers else None

    async def _get_rumors(self, module_id: UUID) -> Optional[List[Dict[str, Any]]]:
        """Get rumors/legends table from the module."""
        result = await self.db.execute(
            select(AdventureModule).where(AdventureModule.id == module_id)
        )
        module = result.scalar_one_or_none()

        if not module or not module.rumors_table:
            return None

        # Filter to true rumors only (things the player could legitimately know)
        # and transform to player-friendly format
        player_rumors = []
        for rumor in module.rumors_table:
            if rumor.get("is_true", True):  # Include true rumors
                player_rumors.append({
                    "text": self._transform_party_to_solo(rumor.get("rumor", "")),
                })

        return player_rumors if player_rumors else None
