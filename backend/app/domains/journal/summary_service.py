"""Service for auto-generating session summaries."""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.sessions.models import Session, ConversationMessage, MessageRole
from app.domains.journal.models import JournalEntry, EntryType
from app.llm.client import ClaudeClient

logger = logging.getLogger(__name__)


class SessionSummaryService:
    """Generate automatic summaries of game sessions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = ClaudeClient()

    async def generate_session_summary(
        self,
        session_id: UUID,
        save_to_journal: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a summary of a game session.

        Analyzes the conversation history to extract:
        - Key events and plot points
        - NPCs encountered
        - Locations visited
        - Combat encounters
        - Loot/XP gained
        """
        # Load session with messages
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Load messages
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.sequence)
        )
        messages = list(result.scalars().all())

        if not messages:
            return {
                "summary": "No activity in this session yet.",
                "key_events": [],
                "npcs_encountered": [],
                "locations_visited": [],
                "combat_count": 0,
            }

        # Build conversation text for analysis
        conversation_text = self._format_conversation(messages)

        # Generate summary using LLM
        summary_data = await self._generate_summary_with_llm(
            conversation_text,
            session.current_location or "Unknown",
        )

        # Save to journal if requested
        if save_to_journal:
            await self._save_summary_entry(session, summary_data)

        return summary_data

    def _format_conversation(self, messages: List[ConversationMessage]) -> str:
        """Format messages into readable conversation text."""
        parts = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                parts.append(f"PLAYER: {msg.content}")
            elif msg.role == MessageRole.ASSISTANT:
                parts.append(f"DM: {msg.content}")

            # Include tool results for context
            if msg.tool_results:
                for tr in msg.tool_results:
                    if "roll" in str(tr.get("content", "")).lower():
                        parts.append(f"[Dice roll: {tr.get('content', '')}]")

        return "\n\n".join(parts)

    async def _generate_summary_with_llm(
        self,
        conversation: str,
        current_location: str,
    ) -> Dict[str, Any]:
        """Use LLM to generate structured summary."""

        prompt = f"""Analyze this tabletop RPG session transcript and create a structured summary.

TRANSCRIPT:
{conversation[:8000]}  # Limit to avoid token issues

CURRENT LOCATION: {current_location}

Please provide a JSON response with:
{{
    "title": "A short title for this session (5-8 words)",
    "summary": "A 2-3 paragraph narrative summary of what happened",
    "key_events": ["List of 3-5 significant events that occurred"],
    "npcs_encountered": ["Names of NPCs the player interacted with"],
    "locations_visited": ["Places the player went"],
    "combat_count": number of combat encounters,
    "xp_estimate": estimated XP gained (0 if none mentioned),
    "loot_found": ["Notable items or treasure found"],
    "mood": "overall mood/tone of the session (e.g., tense, triumphant, mysterious)"
}}

Focus on what actually happened in the story. Be specific about names, places, and outcomes.
Respond with ONLY the JSON, no other text."""

        try:
            response = await self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="You are a skilled chronicler summarizing tabletop RPG sessions. Extract key information and create engaging summaries. Always respond with valid JSON only.",
                temperature=0.3,  # Lower temperature for more consistent output
            )

            # Extract text from response
            response_text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    response_text += block.get("text", "")

            # Parse JSON
            import json
            # Clean up the response
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            summary_data = json.loads(response_text.strip())

            # Ensure required fields
            return {
                "title": summary_data.get("title", "Session Summary"),
                "summary": summary_data.get("summary", ""),
                "key_events": summary_data.get("key_events", []),
                "npcs_encountered": summary_data.get("npcs_encountered", []),
                "locations_visited": summary_data.get("locations_visited", []),
                "combat_count": summary_data.get("combat_count", 0),
                "xp_estimate": summary_data.get("xp_estimate", 0),
                "loot_found": summary_data.get("loot_found", []),
                "mood": summary_data.get("mood", ""),
            }

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            # Return basic fallback
            return {
                "title": "Session Summary",
                "summary": "Unable to generate automatic summary.",
                "key_events": [],
                "npcs_encountered": [],
                "locations_visited": [],
                "combat_count": 0,
                "xp_estimate": 0,
                "loot_found": [],
                "mood": "",
            }

    async def _save_summary_entry(
        self,
        session: Session,
        summary_data: Dict[str, Any],
    ) -> JournalEntry:
        """Save the summary as a journal entry."""
        from sqlalchemy import func

        # Get next sequence number
        result = await self.db.execute(
            select(func.coalesce(func.max(JournalEntry.sequence), 0))
            .where(JournalEntry.campaign_id == session.campaign_id)
        )
        next_sequence = result.scalar() + 1

        entry = JournalEntry(
            session_id=session.id,
            campaign_id=session.campaign_id,
            character_id=session.character_id,
            entry_type='auto_summary',  # Use string value for PostgreSQL enum
            title=summary_data["title"],
            content=summary_data["summary"],
            sequence=next_sequence,
            entry_metadata={
                "key_events": summary_data["key_events"],
                "npcs_encountered": summary_data["npcs_encountered"],
                "locations_visited": summary_data["locations_visited"],
                "combat_count": summary_data["combat_count"],
                "xp_estimate": summary_data["xp_estimate"],
                "loot_found": summary_data["loot_found"],
                "mood": summary_data["mood"],
            },
        )

        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)

        logger.info(f"Saved session summary for session {session.id}")
        return entry
