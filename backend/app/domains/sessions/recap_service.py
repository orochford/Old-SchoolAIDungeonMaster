"""Service for generating session start recaps."""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.domains.sessions.models import Session
from app.domains.journal.models import JournalEntry
from app.domains.campaigns.models import Campaign

logger = logging.getLogger(__name__)


class RecapService:
    """Generate "Previously on..." recaps for session starts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_recap(
        self,
        campaign_id: UUID,
        character_id: UUID,
        current_session_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a recap from session data.

        Returns None if there's no previous data to recap.
        """
        # Get the campaign for the adventure title
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        # First, check current session for a saved summary (resumed session)
        result = await self.db.execute(
            select(Session).where(Session.id == current_session_id)
        )
        current_session = result.scalar_one_or_none()

        # If current session has a summary (was paused/ended), use it
        if current_session and current_session.summary:
            session_to_recap = current_session
            summary_entry = None  # Use session.summary directly
            use_last_interaction = False
        else:
            # Check if current session has conversation history (resumed without End Session)
            from app.domains.sessions.models import ConversationMessage
            result = await self.db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.session_id == current_session_id)
                .order_by(ConversationMessage.sequence.desc())
                .limit(1)
            )
            last_message = result.scalar_one_or_none()

            if last_message and current_session:
                # Session has messages but no summary - use adventure_state for recap
                session_to_recap = current_session
                summary_entry = None
                use_last_interaction = True
            else:
                # Look for previous sessions (different session ID)
                use_last_interaction = False
                result = await self.db.execute(
                    select(Session)
                    .where(
                        and_(
                            Session.campaign_id == campaign_id,
                            Session.character_id == character_id,
                            Session.id != current_session_id,
                        )
                    )
                    .order_by(Session.created_at.desc())
                    .limit(1)
                )
                session_to_recap = result.scalar_one_or_none()

                if not session_to_recap:
                    return None  # No previous sessions to recap

                # Get the auto_summary journal entry from the previous session
                result = await self.db.execute(
                    select(JournalEntry)
                    .where(
                        and_(
                            JournalEntry.session_id == session_to_recap.id,
                            JournalEntry.entry_type == 'auto_summary',
                        )
                    )
                    .order_by(JournalEntry.created_at.desc())
                    .limit(1)
                )
                summary_entry = result.scalar_one_or_none()

        # Get active plot threads from adventure state
        adventure_state = session_to_recap.adventure_state or {}
        active_plot_threads = self._extract_active_threads(adventure_state)

        # Get recent NPCs encountered
        npcs_encountered = self._extract_npcs(adventure_state)

        # Get session goals if any
        session_goals = adventure_state.get("session_goals", [])

        # Get current location from pickup_point or adventure_state
        pickup_point = adventure_state.get("pickup_point", {})
        current_location = (
            pickup_point.get("location") or
            adventure_state.get("current_location") or
            session_to_recap.current_location or
            "Unknown"
        )

        # Build recap data
        recap = {
            "campaign_name": campaign.name,
            "previous_session_id": str(session_to_recap.id),
            "current_location": current_location,
            "active_plot_threads": active_plot_threads,
            "npcs_encountered": npcs_encountered,
            "session_goals": session_goals,
        }

        # Add summary data - prefer session.summary (from End Session), then journal entry
        if session_to_recap.summary:
            # Use the saved session summary (from End Session button)
            recap["summary"] = {
                "title": session_to_recap.title or "Last Session",
                "content": session_to_recap.summary,
                "key_events": pickup_point.get("key_events", []),
                "mood": "",
            }
        elif use_last_interaction:
            # Session has messages but no summary - fetch last few messages for recap
            from app.domains.sessions.models import ConversationMessage, MessageRole

            # Get the last few DM messages for context
            result = await self.db.execute(
                select(ConversationMessage)
                .where(
                    and_(
                        ConversationMessage.session_id == current_session_id,
                        ConversationMessage.role == MessageRole.ASSISTANT,
                    )
                )
                .order_by(ConversationMessage.sequence.desc())
                .limit(3)
            )
            recent_dm_messages = list(result.scalars().all())

            # Build summary from recent DM messages (most recent first, reverse for chronological)
            if recent_dm_messages:
                # Use the most recent message as the primary recap
                last_dm_message = recent_dm_messages[0].content
                # Truncate if too long but keep it more detailed than last_interaction
                if len(last_dm_message) > 1500:
                    last_dm_message = last_dm_message[:1500] + "..."
                dm_summary = last_dm_message
            else:
                # Fallback to last_interaction
                last_interaction = adventure_state.get("last_interaction", {})
                dm_summary = last_interaction.get("dm_response_summary", "")

            # Build a recap from current state
            recap["summary"] = {
                "title": "Continuing Session",
                "content": dm_summary if dm_summary else f"You are at {current_location}.",
                "key_events": pickup_point.get("key_events", []),
                "mood": "",
            }
        elif summary_entry:
            recap["summary"] = {
                "title": summary_entry.title,
                "content": summary_entry.content,
                "key_events": summary_entry.entry_metadata.get("key_events", []),
                "mood": summary_entry.entry_metadata.get("mood", ""),
            }
        else:
            # Generate a basic recap from the session state
            recap["summary"] = {
                "title": "Last Session",
                "content": f"You were last at {current_location}.",
                "key_events": [],
                "mood": "",
            }

        # Generate narrative "Previously on..." text
        recap["narrative"] = self._generate_narrative(recap)

        return recap

    def _extract_active_threads(
        self,
        adventure_state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Extract active plot threads from adventure state."""
        threads = []
        plot_threads = adventure_state.get("plot_threads", {})

        for thread_name, thread_data in plot_threads.items():
            if isinstance(thread_data, dict):
                status = thread_data.get("status", "active")
                if status == "active":
                    threads.append({
                        "name": thread_name,
                        "notes": thread_data.get("notes", ""),
                    })
            elif thread_data == "active":
                threads.append({
                    "name": thread_name,
                    "notes": "",
                })

        return threads

    def _extract_npcs(
        self,
        adventure_state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Extract recently encountered NPCs."""
        npcs = []
        npcs_encountered = adventure_state.get("npcs_encountered", {})

        for npc_name, npc_data in npcs_encountered.items():
            if isinstance(npc_data, dict):
                npcs.append({
                    "name": npc_name,
                    "attitude": npc_data.get("attitude", "neutral"),
                    "notes": npc_data.get("notes", ""),
                })
            else:
                npcs.append({
                    "name": npc_name,
                    "attitude": "neutral",
                    "notes": "",
                })

        # Limit to most recent 5 NPCs
        return npcs[:5]

    def _generate_narrative(self, recap: Dict[str, Any]) -> str:
        """Generate a narrative 'Previously on...' text."""
        parts = []

        campaign_name = recap.get("campaign_name", "your adventure")
        parts.append(f"Previously, in {campaign_name}...")

        # Add summary content
        summary = recap.get("summary", {})
        if summary.get("content"):
            parts.append(summary["content"])

        # Mention active plot threads
        threads = recap.get("active_plot_threads", [])
        if threads:
            thread_names = [t["name"] for t in threads[:3]]
            if len(threads) == 1:
                parts.append(f"An unfinished matter awaits: {thread_names[0]}.")
            else:
                threads_text = ", ".join(thread_names[:-1]) + f" and {thread_names[-1]}"
                parts.append(f"Unfinished matters await: {threads_text}.")

        # Mention current location
        location = recap.get("current_location")
        if location and location != "Unknown":
            parts.append(f"You find yourself at {location}.")

        return "\n\n".join(parts)


async def get_previous_session_count(
    db: AsyncSession,
    campaign_id: UUID,
    character_id: UUID,
    current_session_id: UUID,
) -> int:
    """Check if there's data to recap (previous sessions with content OR current session has summary)."""
    from sqlalchemy import func, or_

    # First check if current session has a saved summary (was paused/ended properly)
    result = await db.execute(
        select(Session).where(Session.id == current_session_id)
    )
    current_session = result.scalar_one_or_none()
    if current_session and current_session.summary and current_session.summary.strip():
        return 1  # Current session has recap data

    # Otherwise count previous sessions that have actual content (summary or completed/paused status)
    # Exclude empty sessions from failed attempts
    result = await db.execute(
        select(func.count())
        .select_from(Session)
        .where(
            and_(
                Session.campaign_id == campaign_id,
                Session.character_id == character_id,
                Session.id != current_session_id,
                or_(
                    Session.summary.isnot(None),  # Has a summary
                    Session.status.in_(["paused", "completed"]),  # Was properly ended
                )
            )
        )
    )
    return result.scalar() or 0
