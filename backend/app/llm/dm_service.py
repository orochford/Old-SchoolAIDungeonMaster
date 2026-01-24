"""Dungeon Master service orchestrating LLM responses."""

from typing import AsyncGenerator, Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.llm.client import ClaudeClient
from app.llm.prompts.dm_system import build_dm_system_prompt
from app.llm.prompts.adventure_prompt import build_adventure_context_section
from app.llm.tools.definitions import DM_TOOLS, ADVENTURE_TOOLS, JOURNAL_TOOLS, SOLO_HERO_TOOLS, CALENDAR_TOOLS, MAP_TOOLS
from app.llm.tools.handlers import ToolHandler
from app.rag.retriever import RAGRetriever
from app.llm.adventure_planner import AdventurePlanner
from app.domains.sessions.models import Session, ConversationMessage, MessageRole
from app.domains.characters.models import Character
from app.domains.campaigns.models import Campaign
from app.domains.sourcebooks.models import PDFDocument
from app.domains.adventures.retriever import AdventureDataRetriever
from app.domains.adventures.models import AdventureModule, ParsingStatus
from app.domains.sourcebooks.models import PDFDocument
import os
import logging

logger = logging.getLogger(__name__)


class DMService:
    """Orchestrates the LLM Dungeon Master for game sessions."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self.client = ClaudeClient()
        self.retriever = RAGRetriever(session)
        self.tool_handler = ToolHandler(session)
        self.adventure_planner = AdventurePlanner(session)

    def _transform_party_to_solo(self, text: str) -> str:
        """Transform party-oriented language to solo player language.

        Published adventure modules are written for groups, so they use phrases like
        "the party", "the adventurers", etc. This transforms those to "you" for solo play.
        """
        import re

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

    async def process_player_action(
        self,
        game_session: Session,
        character: Character,
        player_input: str,
        campaign: Optional[Campaign] = None,
        is_system_prompt: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process player input and stream DM response.

        Args:
            is_system_prompt: If True, don't save the input as a user message (used for opening scenes)
        """
        import json

        logger.info(f"[DM] process_player_action called - session={game_session.id}, is_system_prompt={is_system_prompt}")
        logger.info(f"[DM] Player input preview: {player_input[:100]}...")

        # Load campaign if not provided
        if not campaign:
            result = await self.db.execute(
                select(Campaign).where(Campaign.id == game_session.campaign_id)
            )
            campaign = result.scalar_one_or_none()

        # Get RAG context for the player's action
        rag_context = await self.retriever.get_context_for_dm(
            query=player_input,
            rpg_system_id=character.rpg_system_id,
        )

        # Get adventure context if this campaign has an adventure module
        adventure_context = ""
        adventure_state = game_session.adventure_state or {}

        # Debug logging for location tracking
        logger.info(f"[DM] current_location_key={adventure_state.get('current_location_key')}, current_location={adventure_state.get('current_location')}")

        if campaign and campaign.adventure_document_id:
            # Get adventure-specific content
            adventure_doc = await self.adventure_planner.get_adventure_document(
                campaign.adventure_document_id
            )
            adventure_title = adventure_doc.title if adventure_doc else "Adventure"

            # Get parsed structured adventure data (locations, NPCs, etc.)
            structured_content = await self._get_structured_adventure_context(
                campaign.adventure_document_id,
                adventure_state,
                player_input,
            )

            # ALWAYS also get RAG content to supplement structured data
            # This ensures we capture details like traps, secrets, and full descriptions
            # that may not have been fully extracted during parsing
            is_opening = any(kw in player_input.lower() for kw in
                ["begin", "start", "new adventure", "opening", "first scene", "set the scene"])

            if is_opening:
                # For opening scenes, get multiple specific queries to ensure we capture:
                # 1. Physical description of the dungeon/location exterior
                # 2. Entrance/approach description
                # 3. Background/setting lore
                rag_parts = []

                # Get adventure module title for more targeted queries
                adventure_retriever = AdventureDataRetriever(self.db)
                module = await adventure_retriever.get_module_for_document(campaign.adventure_document_id)
                module_title = module.title if module else "dungeon"

                # Query 1: Physical description and exterior
                exterior_chunks = await self.retriever.query(
                    query=f"{module_title} exterior physical description landscape terrain hill rock",
                    document_ids=[campaign.adventure_document_id],
                    top_k=3,
                )
                for chunk in exterior_chunks:
                    rag_parts.append(f"[PHYSICAL DESCRIPTION]\n{chunk['content']}")

                # Query 2: Entrance description
                entrance_chunks = await self.retriever.query(
                    query=f"{module_title} entrance approach arrival corridor first area",
                    document_ids=[campaign.adventure_document_id],
                    top_k=3,
                )
                for chunk in entrance_chunks:
                    if chunk["chunk_id"] not in [c["chunk_id"] for c in exterior_chunks]:
                        rag_parts.append(f"[ENTRANCE AREA]\n{chunk['content']}")

                # Query 3: Area 1 / First room specifically
                area1_chunks = await self.retriever.query(
                    query="area 1 room 1 entrance alcoves corridor first location",
                    document_ids=[campaign.adventure_document_id],
                    top_k=2,
                )
                for chunk in area1_chunks:
                    chunk_ids_seen = [c["chunk_id"] for c in exterior_chunks + entrance_chunks]
                    if chunk["chunk_id"] not in chunk_ids_seen:
                        rag_parts.append(f"[FIRST LOCATION]\n{chunk['content']}")

                rag_content = "\n\n---\n\n".join(rag_parts) if rag_parts else ""
                logger.info(f"[DM] Opening scene RAG: {len(rag_parts)} chunks retrieved")
            else:
                # For non-opening scenes, filter RAG to current location to prevent
                # retrieving contradictory content from other areas
                current_location_key = adventure_state.get("current_location_key")
                current_location = adventure_state.get("current_location", "")

                # Build location-specific query to improve relevance
                if current_location_key:
                    # Prioritize current location in query
                    query_text = f"location {current_location_key} {current_location} {player_input}"
                else:
                    query_text = f"{player_input} {current_location}".strip()

                logger.info(f"[DM] RAG query: {query_text[:100]}...")

                # Get raw PDF content via RAG for full details
                # Limit to 3 chunks to reduce noise from other locations
                rag_content = await self.retriever.get_adventure_context(
                    query=query_text,
                    adventure_document_id=campaign.adventure_document_id,
                    current_location=current_location,
                    max_chunks=3,
                )

            # Combine structured and RAG content
            if structured_content and rag_content:
                adventure_content = f"{structured_content}\n\n## RAW MODULE TEXT (for full details)\n{rag_content}"
            else:
                adventure_content = structured_content or rag_content

            # Build adventure context section
            adventure_context = build_adventure_context_section(
                adventure_title=adventure_title,
                adventure_state=adventure_state,
                adventure_content=adventure_content,
            )

        # Get prior session context for continuity
        journal_context = await self._get_journal_context(
            campaign_id=game_session.campaign_id,
            character_id=game_session.character_id,
        )

        # Get time context for atmospheric descriptions
        time_context = await self._get_time_context(game_session.campaign_id)

        # Load rulebook markdown for full rules reference
        rulebook_markdown = await self._get_rulebook_markdown(
            rpg_system_id=character.rpg_system_id,
        )

        # Build system prompt
        logger.info("[DM] Building system prompt...")
        system_prompt = build_dm_system_prompt(
            rpg_system="bx-dnd",  # TODO: Get from character/campaign
            rules_context=rag_context,
            character=self._character_to_dict(character),
            game_state=game_session.game_state or {},
            adventure_context=adventure_context,
            journal_context=journal_context,
            time_context=time_context,
            rulebook_markdown=rulebook_markdown,
        )
        logger.info(f"[DM] System prompt built - {len(system_prompt)} chars")

        # Build conversation history
        messages = await self._build_messages(game_session, player_input)
        logger.info(f"[DM] Built {len(messages)} messages for LLM")

        # Determine which tools to use (add adventure tools if adventure is active)
        tools = list(DM_TOOLS)
        tools.extend(JOURNAL_TOOLS)  # Always include journal tools for session continuity
        tools.extend(SOLO_HERO_TOOLS)  # Solo Hero rules for single-character play
        tools.extend(CALENDAR_TOOLS)  # Calendar and time tracking tools
        tools.extend(MAP_TOOLS)  # Dungeon map tools
        if campaign and campaign.adventure_document_id:
            tools.extend(ADVENTURE_TOOLS)

        # Track all tool calls and responses across the conversation loop
        all_tool_calls = []
        full_response = ""
        max_iterations = 10  # Prevent infinite loops

        for iteration in range(max_iterations):
            # Current turn's tool calls and text
            current_tool_calls = []
            current_text = ""
            current_tool_input = {}

            logger.info(f"[DM] Starting LLM call iteration {iteration + 1}/{max_iterations}")
            async for event in self.client.chat_stream(
                messages=messages,
                system=system_prompt,
                tools=tools,
            ):
                if event["type"] == "text_delta":
                    current_text += event["text"]
                    full_response += event["text"]
                    yield {
                        "type": "text",
                        "content": event["text"],
                    }

                elif event["type"] == "tool_use_delta":
                    # Accumulate partial JSON for tool input
                    pass  # We'll get the full input when tool_use fires

                elif event["type"] == "tool_use":
                    tool_call = event["tool_use"]
                    current_tool_calls.append(tool_call)
                    all_tool_calls.append(tool_call)

                    # Execute tool
                    result = await self.tool_handler.execute(
                        tool_name=tool_call["name"],
                        tool_input=tool_call["input"],
                        character=character,
                        session=game_session,
                    )

                    # Store result with the tool call
                    tool_call["result"] = result

                    yield {
                        "type": "tool_result",
                        "tool_name": tool_call["name"],
                        "result": result,
                    }

                elif event["type"] == "message_complete":
                    stop_reason = event["stop_reason"]

                    # If stop reason is tool_use/tool_calls, we need to continue
                    # Note: Claude uses "tool_use", OpenAI uses "tool_calls"
                    if stop_reason in ("tool_use", "tool_calls") and current_tool_calls:
                        # Build assistant message with tool use
                        assistant_content = []
                        if current_text:
                            assistant_content.append({"type": "text", "text": current_text})

                        for tc in current_tool_calls:
                            assistant_content.append({
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": tc["input"],
                            })

                        messages.append({
                            "role": "assistant",
                            "content": assistant_content,
                        })

                        # Build tool results message
                        tool_results = []
                        for tc in current_tool_calls:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tc["id"],
                                "content": json.dumps(tc["result"]),
                            })

                        messages.append({
                            "role": "user",
                            "content": tool_results,
                        })

                        # Continue the loop
                        break
                    else:
                        # Stop reason is end_turn or other - we're done
                        await self._save_messages(
                            game_session,
                            player_input,
                            full_response,
                            all_tool_calls,
                            is_system_prompt=is_system_prompt,
                        )

                        yield {
                            "type": "complete",
                            "stop_reason": stop_reason,
                        }
                        return

    async def _build_messages(
        self,
        game_session: Session,
        current_input: str,
    ) -> List[Dict[str, Any]]:
        """Build message history for Claude."""
        messages = []

        # Get recent conversation history
        if game_session.messages:
            for msg in game_session.messages[-20:]:  # Last 20 messages
                if msg.role == MessageRole.USER:
                    messages.append({
                        "role": "user",
                        "content": msg.content,
                    })
                elif msg.role == MessageRole.ASSISTANT:
                    content = [{"type": "text", "text": msg.content}]

                    # Add any tool uses
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            content.append({
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": tc["input"],
                            })

                    messages.append({
                        "role": "assistant",
                        "content": content,
                    })

                    # Add tool results if any
                    if msg.tool_results:
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tr["tool_use_id"],
                                "content": tr["content"],
                            } for tr in msg.tool_results],
                        })

        # Add current input
        messages.append({
            "role": "user",
            "content": current_input,
        })

        return messages

    async def _save_messages(
        self,
        game_session: Session,
        player_input: str,
        dm_response: str,
        tool_calls: List[Dict[str, Any]],
        is_system_prompt: bool = False,
    ) -> None:
        """Save messages to conversation history.

        Args:
            is_system_prompt: If True, skip saving the player input (it's an internal prompt)
        """
        import json
        from datetime import datetime

        # Don't save empty DM responses - this indicates an error occurred
        if not dm_response or not dm_response.strip():
            logger.warning(f"[DM] Skipping save of empty DM response for session {game_session.id}")
            return

        # Get next sequence number
        next_seq = len(game_session.messages) + 1 if game_session.messages else 1

        # Save player message (unless it's a system prompt like opening scene)
        if not is_system_prompt:
            player_msg = ConversationMessage(
                session_id=game_session.id,
                role=MessageRole.USER,
                content=player_input,
                sequence=next_seq,
            )
            self.db.add(player_msg)
            next_seq += 1
        else:
            # Don't increment sequence for system prompts
            pass

        # Save DM response with tool calls and their results
        tool_calls_data = None
        tool_results_data = None

        if tool_calls:
            tool_calls_data = [{
                "id": tc.get("id", ""),
                "name": tc["name"],
                "input": tc.get("input", {}),
            } for tc in tool_calls]

            # Also save tool results so we can reconstruct the conversation
            tool_results_data = [{
                "tool_use_id": tc.get("id", ""),
                "content": json.dumps(tc.get("result", {})),
            } for tc in tool_calls if "result" in tc]

        dm_msg = ConversationMessage(
            session_id=game_session.id,
            role=MessageRole.ASSISTANT,
            content=dm_response,
            sequence=next_seq,  # next_seq was already incremented if player msg was saved
            tool_calls=tool_calls_data,
            tool_results=tool_results_data,
        )
        self.db.add(dm_msg)

        # Auto-update adventure state with conversation context
        # This ensures the DM has context even if state-tracking tools weren't called
        await self._update_session_context(game_session, player_input, dm_response, tool_calls)

        await self.db.flush()

    async def _update_session_context(
        self,
        game_session: Session,
        player_input: str,
        dm_response: str,
        tool_calls: List[Dict[str, Any]],
    ) -> None:
        """
        Auto-update session state to maintain context between interactions.
        This ensures the DM knows where we left off even without explicit tool calls.
        """
        from datetime import datetime

        # Initialize adventure_state if needed
        adventure_state = dict(game_session.adventure_state or {})

        # Track last interaction for context
        adventure_state["last_interaction"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "player_action_summary": player_input[:200] if player_input else "",
            "dm_response_summary": dm_response[:500] if dm_response else "",
        }

        # Track message count for continuity check
        message_count = len(game_session.messages) + 2 if game_session.messages else 2
        adventure_state["message_count"] = message_count

        # Extract and track any locations mentioned in the DM response
        # This provides backup context if update_adventure_location wasn't called
        if dm_response:
            # Try to detect location from common patterns
            import re
            location_patterns = [
                # Explicit movement patterns
                r"you (?:enter|arrive at|reach|find yourself in|stand (?:at|in|before)|are (?:now )?in) (?:the )?([A-Z][^.!?]{3,50})",
                r"welcome to (?:the )?([A-Z][^.!?]{3,50})",
                # Scenic descriptions
                r"(?:the |this )([A-Z][^.!?]{3,40}) (?:is|appears|stretches|lies|opens)",
                # Area descriptions like "The Ravine", "The Cave Entrance"
                r"entering (?:the )?([A-Z][^.!?]{3,40})",
                r"inside (?:the )?([A-Z][^.!?]{3,40})",
            ]
            for pattern in location_patterns:
                match = re.search(pattern, dm_response, re.IGNORECASE)
                if match:
                    detected_location = match.group(1).strip().rstrip('.,;:')
                    # Clean up common artifacts
                    detected_location = detected_location.split(' - ')[0].strip()
                    if len(detected_location) > 3 and len(detected_location) < 60:
                        # Save to both current_location and detected_location
                        adventure_state["current_location"] = detected_location
                        adventure_state["detected_location"] = detected_location
                        # Also update the session's current_location field
                        game_session.current_location = detected_location
                        break

        # Save updated state
        game_session.adventure_state = adventure_state

    def _character_to_dict(self, character: Character) -> Dict[str, Any]:
        """Convert character to dict for prompt."""
        return {
            "name": character.name,
            "level": character.level,
            "current_hp": character.current_hp,
            "max_hp": character.max_hp,
            "xp": character.experience_points,
            **character.attributes,
        }

    async def _get_journal_context(
        self,
        campaign_id: UUID,
        character_id: UUID,
    ) -> str:
        """Get recent journal entries for DM context."""
        from app.domains.journal.models import JournalEntry

        result = await self.db.execute(
            select(JournalEntry)
            .where(JournalEntry.campaign_id == campaign_id)
            .where(JournalEntry.entry_type == 'auto_summary')
            .order_by(JournalEntry.created_at.desc())
            .limit(3)
        )
        entries = list(result.scalars().all())

        if not entries:
            return ""

        context = "\n## PREVIOUS SESSION SUMMARIES\n"
        context += "The following are summaries of recent sessions. Use these to maintain continuity:\n"

        for entry in reversed(entries):  # Show oldest first
            context += f"\n### {entry.title}\n{entry.content}\n"

            # Include key metadata if available
            metadata = entry.entry_metadata or {}
            if metadata.get("npcs_encountered"):
                context += f"NPCs met: {', '.join(metadata['npcs_encountered'])}\n"
            if metadata.get("locations_visited"):
                context += f"Locations: {', '.join(metadata['locations_visited'])}\n"

        return context

    async def _get_time_context(
        self,
        campaign_id: UUID,
    ) -> Dict[str, Any]:
        """Get current in-game time context for the DM."""
        from app.domains.campaigns.calendar_service import CalendarService

        try:
            calendar_service = CalendarService(self.db)
            time_context = await calendar_service.get_current_time(campaign_id)
            return time_context
        except Exception:
            # If calendar doesn't exist yet, return empty context
            return {}

    async def _get_rulebook_markdown(
        self,
        rpg_system_id: UUID,
        max_length: int = 50000,  # Limit to avoid huge context
    ) -> str:
        """Load rulebook markdown for the character's RPG system.

        Returns formatted markdown content from uploaded rulebooks.
        """
        # Get rulebooks for this system
        try:
            # Query without status filter first, then filter in Python
            # This avoids enum type casting issues with PostgreSQL
            result = await self.db.execute(
                select(PDFDocument).where(
                    PDFDocument.rpg_system_id == rpg_system_id,
                    PDFDocument.category == "rules",
                )
            )
            all_rulebooks = list(result.scalars().all())
            # Filter for completed status in Python
            rulebooks = [r for r in all_rulebooks if str(r.status.value if hasattr(r.status, 'value') else r.status) == "completed"]
        except Exception as e:
            logger.warning(f"Failed to load rulebook markdown: {e}")
            return ""

        if not rulebooks:
            return ""

        # Load markdown from each rulebook
        content_parts = []
        total_length = 0

        for doc in rulebooks:
            if doc.markdown_path and os.path.exists(doc.markdown_path):
                try:
                    with open(doc.markdown_path, 'r', encoding='utf-8') as f:
                        markdown = f.read()

                    # Check if adding this would exceed limit
                    if total_length + len(markdown) > max_length:
                        # Truncate to fit
                        remaining = max_length - total_length
                        if remaining > 1000:  # Only add if meaningful content
                            markdown = markdown[:remaining] + "\n\n[Content truncated...]"
                            content_parts.append(f"## {doc.title or doc.original_filename}\n\n{markdown}")
                        break

                    content_parts.append(f"## {doc.title or doc.original_filename}\n\n{markdown}")
                    total_length += len(markdown)
                    logger.info(f"Loaded rulebook markdown: {doc.title} ({len(markdown)} chars)")
                except Exception as e:
                    logger.warning(f"Failed to load rulebook markdown {doc.markdown_path}: {e}")

        if not content_parts:
            return ""

        return "\n\n".join(content_parts)

    async def _get_structured_adventure_context(
        self,
        document_id: UUID,
        adventure_state: Dict[str, Any],
        player_input: str,
    ) -> Optional[str]:
        """Get structured adventure context from parsed module data.

        Returns formatted context string if parsed data exists, None otherwise.
        """
        import json

        logger.info(f"[DM] Getting structured adventure context for document {document_id}")

        # Check for parsed adventure module
        retriever = AdventureDataRetriever(self.db)
        module = await retriever.get_module_for_document(document_id)
        logger.info(f"[DM] Module lookup result: {module.title if module else 'None'}")

        if not module:
            return None

        # Build rich context from structured data
        context_parts = []
        full_markdown_text = ""  # Store for extracting current location verbatim text

        # Load full module markdown for extracting verbatim location text
        # NOTE: We don't dump the entire markdown into context (too large, causes "lost in middle" problem)
        # Instead, we extract just the current location's verbatim text below
        if module.full_markdown_path and os.path.exists(module.full_markdown_path):
            try:
                with open(module.full_markdown_path, 'r', encoding='utf-8') as f:
                    full_markdown_text = f.read()
                logger.info(f"[DM] Loaded full module markdown for extraction: {len(full_markdown_text)} chars")
            except Exception as e:
                logger.warning(f"[DM] Failed to load full module markdown: {e}")

        # Add module summary and overview
        summary = await retriever.get_module_summary(module.id)
        if summary:
            context_parts.append(f"## Adventure: {summary.get('title', 'Unknown')}")
            if summary.get('code'):
                context_parts.append(f"Module Code: {summary['code']}")
            if summary.get('recommended_levels'):
                context_parts.append(f"Recommended Levels: {summary['recommended_levels']}")
            if summary.get('summary'):
                context_parts.append(f"\n{summary['summary']}")

            # DM Overview - critical guidance for running the adventure
            if summary.get('dm_overview'):
                context_parts.append(f"\n### DM OVERVIEW (How to Run This Adventure)")
                context_parts.append(summary['dm_overview'])

            # Adventure Flow - the narrative structure
            if summary.get('adventure_flow'):
                context_parts.append(f"\n### ADVENTURE FLOW (Narrative Structure)")
                context_parts.append(summary['adventure_flow'])

        # CRITICAL: Include all valid locations so DM knows what exists in the module
        logger.info(f"[DM] Fetching all locations for module {module.id}")
        all_locations = await retriever.get_all_locations(module.id)
        logger.info(f"[DM] Found {len(all_locations)} locations")
        if all_locations:
            context_parts.append("\n## VALID MODULE LOCATIONS")
            context_parts.append("CRITICAL: Only use these locations. When calling update_adventure_location, use the key (e.g., '1', '2', '31') as location_key.")
            context_parts.append("| Key | Name | Level |")
            context_parts.append("|-----|------|-------|")
            for loc in all_locations:
                tier_str = f" ({loc['tier']})" if loc.get('tier') else ""
                context_parts.append(f"| {loc['key']} | {loc['name']}{tier_str} | {loc.get('level', 1)} |")

        # Note: player_background is now passed directly to start_session() instead of
        # being injected here. This avoids duplicate intro content.

        # Check if this is an opening scene
        is_opening = any(kw in player_input.lower() for kw in
            ["begin", "start", "new adventure", "opening", "first scene", "set the scene"])

        # Get current location context
        current_location_key = adventure_state.get("current_location_key")
        current_location = adventure_state.get("current_location", "")

        if current_location_key:
            location_context = await retriever.get_location_context(module.id, current_location_key)
            if location_context:
                # Pass full markdown so we can extract verbatim text for this location
                context_parts.append(self._format_location_context(location_context, full_markdown_text))

        # Get wandering monster table for current area
        current_tier = adventure_state.get("current_tier")
        current_dungeon_level = adventure_state.get("current_dungeon_level")
        # Always try to get wandering encounters if we have tier or level info
        if current_tier or current_dungeon_level:
            wandering = await retriever.get_wandering_encounter(
                module.id,
                tier=current_tier,
                dungeon_level=current_dungeon_level
            )
            if wandering:
                context_parts.append(self._format_wandering_table(wandering))

        # Semantic search for relevant content based on player input
        if player_input and not is_opening:
            search_results = await retriever.search_adventure(module.id, player_input, limit=3)
            if search_results:
                context_parts.append("\n## RELEVANT ADVENTURE CONTENT")
                for result in search_results:
                    if result["type"] == "location":
                        loc = result["data"]
                        context_parts.append(f"\n### Location: {loc.get('name', '')} ({loc.get('key', '')})")
                        context_parts.append(loc.get("dm_description", "")[:500])
                    elif result["type"] == "npc":
                        npc = result["data"]
                        context_parts.append(f"\n### NPC: {npc.get('name', '')}")
                        if npc.get("personality"):
                            context_parts.append(f"Personality: {npc['personality']}")
                        if npc.get("stats"):
                            context_parts.append(f"Stats: {json.dumps(npc['stats'])}")
                    elif result["type"] == "encounter":
                        enc = result["data"]
                        context_parts.append(f"\n### Encounter: {enc.get('name', '')}")
                        if enc.get("creatures"):
                            context_parts.append(f"Creatures: {json.dumps(enc['creatures'])}")

        return "\n".join(context_parts) if context_parts else None

    def _extract_location_from_markdown(self, full_markdown: str, location_key: str) -> Optional[str]:
        """Extract the specific location text from full markdown.

        This ensures the DM has access to the EXACT verbatim text for the current
        location, not just the extracted/summarized dm_description.
        """
        import re

        if not full_markdown or not location_key:
            return None

        # Room descriptions follow format: "1. ROOM NAME. Description..."
        # where ROOM NAME is in ALL CAPS followed by a period
        # This distinguishes from monster lists like "1. Orcs (1-4)..."

        # Build patterns to find the location section
        # Key insight: Room names are ALL CAPS followed by a period, e.g. "1. ALCOVES."
        patterns = [
            # Pattern: "1. ALCOVES." or "1. & 2. ALCOVES." - room name in ALL CAPS ending with period
            # The room name must be ALL CAPS (at least 2 chars) followed by a period
            rf'(?:^|\n)({re.escape(location_key)}\.(?:\s*&\s*\d+\.)?\s+[A-Z][A-Z\s\'-]+\.\s+.*?)(?=\n\d+\.(?:\s*&\s*\d+\.)?\s+[A-Z][A-Z\s\'-]+\.|\Z)',
            # Pattern: "## 1. Room Name" (markdown header style)
            rf'(?:^|\n)(##?\s*{re.escape(location_key)}\.?\s+[^\n]+\n.*?)(?=\n##?\s*\d+\.|\Z)',
            # Pattern: "**1.** Room Name" (bold number style)
            rf'(?:^|\n)(\*\*{re.escape(location_key)}\.\*\*\s+[^\n]+\n.*?)(?=\n\*\*\d+\.\*\*|\Z)',
        ]

        for i, pattern in enumerate(patterns):
            match = re.search(pattern, full_markdown, re.DOTALL)
            if match:
                location_text = match.group(1).strip()
                logger.info(f"[DM] Extracted location {location_key} using pattern {i+1}, {len(location_text)} chars")
                # Limit to reasonable size (first ~4000 chars of the location)
                if len(location_text) > 4000:
                    location_text = location_text[:4000] + "\n\n[...section continues...]"
                return location_text

        logger.warning(f"[DM] Could not extract location {location_key} from full markdown")
        return None

    def _format_location_context(self, context: Dict[str, Any], full_markdown: str = "") -> str:
        """Format location context for the DM prompt.

        Args:
            context: Structured location data from database
            full_markdown: Full module markdown to extract verbatim text
        """
        import json

        parts = []
        loc = context.get("location", {})

        if loc:
            parts.append(f"\n## CURRENT LOCATION: {loc.get('name', '')} ({loc.get('key', '')})")

            # CRITICAL: Include verbatim text from full markdown for this location
            # This is the AUTHORITATIVE source - contains all details like body descriptions
            location_key = loc.get('key', '')
            verbatim_text = None
            if full_markdown and location_key:
                verbatim_text = self._extract_location_from_markdown(full_markdown, location_key)
                if verbatim_text:
                    parts.append("\n### EXACT MODULE TEXT FOR THIS LOCATION (AUTHORITATIVE SOURCE):")
                    parts.append("Use this text for ALL descriptions, treasure, bodies, and details.")
                    parts.append("Do NOT invent details not mentioned here.\n")
                    # Transform party language in the verbatim text too
                    verbatim_text = self._transform_party_to_solo(verbatim_text)
                    parts.append(verbatim_text)
                    parts.append("\n--- END MODULE TEXT ---\n")

            if loc.get("read_aloud"):
                # Transform party language to solo language
                read_aloud_text = self._transform_party_to_solo(loc["read_aloud"])
                parts.append(f"\n### READ ALOUD TO PLAYER:")
                parts.append(f'"{read_aloud_text}"')

            # Only include dm_description as fallback if we didn't get verbatim text
            if not verbatim_text:
                parts.append(f"\n### DM DESCRIPTION:")
                parts.append(loc.get("dm_description", ""))

            if loc.get("features"):
                parts.append("\n### FEATURES:")
                for feat in loc["features"]:
                    parts.append(f"- {feat.get('feature', '')}: {feat.get('details', '')}")

            if loc.get("exits"):
                parts.append("\n### EXITS:")
                for direction, dest in loc["exits"].items():
                    parts.append(f"- {direction}: {dest}")

            # TRAPS section - always show, even if empty
            traps = loc.get("traps", [])
            if traps:
                parts.append("\n### TRAPS:")
                for trap in traps:
                    parts.append(f"- Trigger: {trap.get('trigger', '')}")
                    parts.append(f"  Effect: {trap.get('effect', '')}")
                    parts.append(f"  Detection: {trap.get('detection', '')}")
            else:
                parts.append("\n### TRAPS: None")

            # SECRETS section - always show, even if empty
            secrets = loc.get("secrets", [])
            if secrets:
                parts.append("\n### SECRETS:")
                for secret in secrets:
                    parts.append(f"- {secret.get('type', '')}: {secret.get('description', '')}")
                    parts.append(f"  Detection: {secret.get('detection', '')}")
            else:
                parts.append("\n### SECRETS: None - no hidden doors or secret features")

            # TREASURE section - always show, even if empty
            treasure = loc.get("treasure", [])
            if treasure:
                parts.append("\n### TREASURE:")
                for item in treasure:
                    parts.append(f"- {item.get('item', '')}: {item.get('value', '')}")
            else:
                parts.append("\n### TREASURE: None - this location contains NO treasure or hidden items")

        # NPCs present
        npcs = context.get("npcs", [])
        if npcs:
            parts.append("\n### NPCs PRESENT:")
            for npc in npcs:
                parts.append(f"\n**{npc.get('name', '')}**")
                if npc.get("title"):
                    parts.append(f"  Title: {npc['title']}")
                if npc.get("personality"):
                    parts.append(f"  Personality: {npc['personality']}")
                if npc.get("motivation"):
                    parts.append(f"  Motivation: {npc['motivation']}")
                if npc.get("stats"):
                    parts.append(f"  Stats: {json.dumps(npc['stats'])}")
                if npc.get("dialogue_hooks"):
                    parts.append(f"  Dialogue hooks: {npc['dialogue_hooks'][:2]}")

        # Encounters
        encounters = context.get("encounters", [])
        if encounters:
            parts.append("\n### ENCOUNTERS:")
            for enc in encounters:
                parts.append(f"\n**{enc.get('name', '')}**")
                if enc.get("creatures"):
                    parts.append(f"  Creatures: {json.dumps(enc['creatures'])}")
                if enc.get("tactics"):
                    parts.append(f"  Tactics: {enc['tactics']}")
                if enc.get("xp_value"):
                    parts.append(f"  XP: {enc['xp_value']}")

        # Items
        items = context.get("items", [])
        if items:
            parts.append("\n### NOTABLE ITEMS:")
            for item in items:
                parts.append(f"- {item.get('name', '')}")
                if item.get("is_magical"):
                    parts.append(f"  (Magic) {item.get('magical_properties', '')}")
                if item.get("is_key_item"):
                    parts.append(f"  [KEY ITEM]")
                if item.get("found_at"):
                    parts.append(f"  Found at: {item['found_at']}")

        return "\n".join(parts)

    def _format_wandering_table(self, table: Dict[str, Any]) -> str:
        """Format wandering monster table for DM prompt."""
        import json

        if not table:
            return ""

        parts = [f"\n## WANDERING MONSTER TABLE: {table.get('table_name', 'Default')}"]
        parts.append(f"Die Roll: {table.get('die_roll', '1d6')}")
        if table.get("check_frequency"):
            parts.append(f"Check: {table['check_frequency']}")

        parts.append("\n| Roll | Encounter |")
        parts.append("|------|-----------|")

        for entry in table.get("entries", []):
            roll_range = entry.get("roll_range", "?")
            name = entry.get("name", "Unknown")
            creatures = entry.get("creatures", [])

            creature_info = ""
            if creatures:
                creature_names = [c.get("name", "") for c in creatures[:3]]
                creature_info = f" ({', '.join(creature_names)})"

            parts.append(f"| {roll_range} | {name}{creature_info} |")

        parts.append("\n### CREATURE STATS:")
        for entry in table.get("entries", []):
            for creature in entry.get("creatures", []):
                parts.append(f"\n**{creature.get('name', 'Unknown')}**")
                parts.append(f"  HD: {creature.get('hd', '?')}, HP: {creature.get('hp', '?')}, AC: {creature.get('ac', '?')}")
                parts.append(f"  THAC0: {creature.get('thac0', '?')}, Morale: {creature.get('morale', '?')}")
                if creature.get("attacks"):
                    parts.append(f"  Attacks: {creature['attacks']}")
                if creature.get("damage"):
                    parts.append(f"  Damage: {creature['damage']}")
                if creature.get("special"):
                    parts.append(f"  Special: {creature['special']}")

        return "\n".join(parts)

    async def start_session(
        self,
        game_session: Session,
        character: Character,
        campaign: Optional[Campaign] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate an opening scene for a new session.

        Note: The router is responsible for setting the opening_generated flag
        BEFORE calling this method to prevent race conditions with multiple
        WebSocket connections.
        """
        logger.info(f"[DM] start_session called for session {game_session.id}, character {character.name}")

        # Get adventure state (flag should already be set by router)
        adventure_state = game_session.adventure_state or {}

        # Load campaign if not provided (needed to access adventure module)
        if not campaign:
            result = await self.db.execute(
                select(Campaign).where(Campaign.id == game_session.campaign_id)
            )
            campaign = result.scalar_one_or_none()

        # Re-read adventure_state after potential campaign load
        adventure_state = game_session.adventure_state or {}
        adventure_title = adventure_state.get("adventure_title", "")
        logger.info(f"[DM] Adventure state: title='{adventure_title}', has_scenes={bool(adventure_state.get('upcoming_scenes'))}")

        # Fetch player_background from the adventure module if available
        player_background_text = ""
        if campaign and campaign.adventure_document_id:
            retriever = AdventureDataRetriever(self.db)
            module = await retriever.get_module_for_document(campaign.adventure_document_id)
            if module:
                raw_background = await retriever.get_player_background(module.id)
                if raw_background:
                    # Transform party language to solo player language
                    player_background_text = self._transform_party_to_solo(raw_background)
                    logger.info(f"[DM] Loaded player_background ({len(player_background_text)} chars)")

                # Set initial location key for adventure modules (location "1" is the entrance)
                if not adventure_state.get("current_location_key"):
                    # Look up location "1" to get its name and tier
                    location_context = await retriever.get_location_context(module.id, "1")
                    if location_context and location_context.get("location"):
                        loc = location_context["location"]
                        loc_name = loc.get("name", "Entrance")
                        adventure_state["current_location_key"] = "1"
                        adventure_state["current_location"] = loc_name
                        # Initialize visited_locations with the starting location for map display
                        adventure_state["visited_locations"] = ["1"]
                        # Set tier for wandering monster tables
                        if loc.get("tier"):
                            adventure_state["current_tier"] = loc["tier"]
                        if loc.get("dungeon_level"):
                            adventure_state["current_dungeon_level"] = loc["dungeon_level"]
                        game_session.adventure_state = adventure_state
                        await self.db.flush()
                        logger.info(f"[DM] Set initial location: key='1', name='{loc_name}', tier='{loc.get('tier')}'")

        if adventure_title:
            # Adventure-specific opening prompt
            # NOTE: The player has already seen the adventure background/premise in the
            # Campaign Framing popup, so we ONLY need to generate the arrival scene.
            # However, the LLM still needs the background for CONTEXT to write a fitting scene.
            first_scene = adventure_state.get("upcoming_scenes", [{}])[0] if adventure_state.get("upcoming_scenes") else {}
            scene_name = first_scene.get("name", "")
            scene_desc = first_scene.get("description", "")

            # Build background context section for LLM reference
            background_context = ""
            if player_background_text:
                background_context = f"""
## MODULE BACKGROUND (for your reference - DO NOT repeat to player)
The following is the adventure's background lore. Use this to inform your descriptions
and ensure the arrival scene fits the module's tone and setting:

---
{player_background_text}
---
"""

            opening_prompt = f"""
            Generate the ARRIVAL SCENE for {character.name} (a level {character.level} {character.attributes.get('character_class', 'adventurer')})
            beginning the adventure "{adventure_title}".
            {background_context}
            {f'Starting scene: "{scene_name}" - {scene_desc}' if scene_name else ''}

            **STARTING LOCATION: {adventure_state.get('current_location', 'the dungeon entrance')} (Location {adventure_state.get('current_location_key', '1')})**
            Use the EXACT description from the module for this location.

            MANDATORY INSTRUCTIONS - YOU MUST FOLLOW THESE:
            1. The player has ALREADY READ the background/premise - DO NOT REPEAT backstory
            2. START with {character.name} physically AT Location {adventure_state.get('current_location_key', '1')} - the module's starting area
            3. *** CRITICAL: Your description MUST match the module's physical description ***
               - If the module says "black slate rock" - describe black slate rock
               - If the module says "wooded hill" - describe a wooded hill
               - If the module says "wind buffets" - include wind
               - DO NOT invent details that contradict the module (no towers if none mentioned,
                 no vines if the module describes bare rock, etc.)
            4. Use SENSORY details from the MODULE TEXT:
               - What does the place look like according to the module?
               - What sounds does the module mention?
               - What atmospheric conditions are described?
            5. End with the first interactive moment - the entrance beckons

            FORBIDDEN:
            - Do NOT write generic fantasy descriptions
            - Do NOT invent architectural details not in the module
            - Do NOT describe vegetation, weather, or structures that contradict the source
            - Keep it to 2-3 paragraphs focused ONLY on what the module describes
            - Use "you" for solo play, never "the party"
            """
        else:
            # Standard opening prompt for sandbox/improvised play
            opening_prompt = f"""
            Begin a NEW CAMPAIGN for {character.name}, a level {character.level} {character.attributes.get('character_class', 'adventurer')}.

            Since this is the VERY FIRST session, provide a proper CAMPAIGN INTRODUCTION:

            1. PROLOGUE (2-3 paragraphs):
               - Establish the world and setting
               - Describe what circumstances have brought {character.name} to adventure
               - Build atmosphere and set the tone for the campaign
               - Create a compelling hook that draws them into the story

            2. ARRIVAL (1-2 paragraphs):
               - Describe {character.name} arriving at the starting location
               - Use rich sensory details to paint the scene
               - Transition naturally into the first interactive moment

            Consider:
            - The character's background, class, and equipment
            - An appropriate starting location (tavern, dungeon entrance, wilderness, etc.)
            - A hook to draw them into adventure
            - Opportunities for exploration, interaction, or combat

            Make it immersive and evocative, in the style of classic B/X D&D adventures.
            Do NOT skip the introduction - make the player feel the weight of the story beginning.
            """

        logger.info(f"[DM] Opening prompt built, length={len(opening_prompt)}, using_adventure={bool(adventure_title)}")

        async for event in self.process_player_action(
            game_session=game_session,
            character=character,
            player_input=opening_prompt,
            campaign=campaign,
            is_system_prompt=True,  # Don't save internal prompt as user message
        ):
            yield event
