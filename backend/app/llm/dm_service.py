"""Dungeon Master service orchestrating LLM responses."""

from typing import AsyncGenerator, Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.llm.client import ClaudeClient, load_image_as_base64
from app.llm.prompts.dm_system import build_dm_system_prompt
from app.llm.prompts.adventure_prompt import build_adventure_context_section
from app.llm.tools.definitions import DM_TOOLS, ADVENTURE_TOOLS, JOURNAL_TOOLS, SOLO_HERO_TOOLS, CALENDAR_TOOLS, MAP_TOOLS, ENCOUNTER_TOOLS, IMAGE_TOOLS
from app.llm.tools.handlers import ToolHandler
from app.llm.combat_agent import CombatAgent
from app.llm.location_agent import LocationAgent
from app.llm.loot_agent import LootAgent
from app.llm.time_agent import TimeAgent
from app.llm.spell_agent import SpellAgent
from app.llm.subarea_agent import SubAreaAgent
from app.rag.retriever import RAGRetriever
from app.llm.adventure_planner import AdventurePlanner
from app.domains.sessions.models import Session, ConversationMessage, MessageRole
from app.domains.characters.models import Character
from app.domains.campaigns.models import Campaign
from app.domains.sourcebooks.models import PDFDocument
from app.domains.adventures.retriever import AdventureDataRetriever
from app.domains.adventures.models import AdventureModule, ParsingStatus
from app.domains.adventures.graph_rag.context_provider import GraphContextProvider
from app.domains.sourcebooks.models import PDFDocument
from app.game.damage_extractor import DamageExtractor
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
        self.combat_agent = CombatAgent(self.tool_handler, session)
        self.location_agent = LocationAgent(self.tool_handler, session)
        self.loot_agent = LootAgent(self.tool_handler, session)
        self.time_agent = TimeAgent(self.tool_handler, session)
        self.spell_agent = SpellAgent(self.tool_handler, session)
        self.subarea_agent = SubAreaAgent(self.tool_handler, session)
        self.adventure_planner = AdventurePlanner(session)
        self.damage_extractor = DamageExtractor(session)

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

    def _should_auto_start_combat(
        self,
        player_input: str,
        game_session: Session,
        adventure_state: Dict[str, Any],
        adventure_context: str,
    ) -> bool:
        """Detect if combat should automatically start based on context.

        Returns True if:
        1. Not already in combat
        2. Player action suggests initiating combat OR entering a location with enemies
        3. Current location has a fixed encounter
        """
        # Already in combat - no need to auto-start
        if game_session.active_combat_id:
            return False

        game_state = game_session.game_state or {}
        if game_state.get("in_combat"):
            return False

        player_lower = player_input.lower()

        # Combat initiation keywords
        combat_keywords = [
            "attack", "fight", "strike", "stab", "swing", "hit", "charge",
            "rush at", "rush into", "engage", "battle", "slay", "kill",
            "shoot", "fire at", "fire my", "cast at", "fireball", "magic missile",
            "draw my sword", "draw my weapon", "ready my weapon",
            "i want combat", "looking for a fight", "find enemies",
        ]

        player_initiates_combat = any(kw in player_lower for kw in combat_keywords)

        # Check if current location has creatures/enemies in context
        context_lower = adventure_context.lower() if adventure_context else ""
        has_enemies_in_context = any(term in context_lower for term in [
            "creature", "monster", "enemy", "enemies", "guard", "guards",
            "orc", "goblin", "skeleton", "zombie", "troll", "ogre",
            "attack", "hostile", "lair", "den", "lurk", "ambush",
        ])

        # Need both player combat intent AND enemies present
        if player_initiates_combat and has_enemies_in_context:
            # Check if location has a fixed encounter in the module
            location_key = adventure_state.get("current_location_key")
            if location_key:
                logger.info(f"[COMBAT] Auto-start check: player_combat={player_initiates_combat}, "
                           f"enemies_present={has_enemies_in_context}, location={location_key}")
                return True

        return False

    async def _auto_start_encounter(
        self,
        game_session: Session,
        character: Character,
        adventure_state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Automatically start an encounter from the current location.

        Returns the encounter start result, or None if it failed.
        """
        location_key = adventure_state.get("current_location_key")
        location_name = adventure_state.get("current_location", "Unknown Location")

        logger.info(f"[COMBAT] Auto-starting encounter at location {location_key}: {location_name}")

        # Call the tool handler directly
        result = await self.tool_handler.execute(
            tool_name="start_encounter",
            tool_input={
                "encounter_name": f"Combat at {location_name}",
                "source": "fixed",  # Use fixed encounter from module
            },
            character=character,
            session=game_session,
        )

        if result.get("error"):
            logger.warning(f"[COMBAT] Auto-start failed: {result.get('error')}")
            return None

        logger.info(f"[COMBAT] Auto-started encounter: {result.get('encounter_name')} - "
                   f"initiative: {result.get('initiative_order')}")
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

        module = None  # Adventure module, loaded for sub-agent use
        if campaign and campaign.adventure_document_id:
            # Get adventure-specific content
            adventure_doc = await self.adventure_planner.get_adventure_document(
                campaign.adventure_document_id
            )
            adventure_title = adventure_doc.title if adventure_doc else "Adventure"

            # Load module for sub-agents (subarea, combat auto-start, etc.)
            adventure_retriever = AdventureDataRetriever(self.db)
            module = await adventure_retriever.get_module_for_document(campaign.adventure_document_id)

            # Get parsed structured adventure data (locations, NPCs, etc.)
            # Returns (content, used_graph_rag) - when GraphRAG is used, it provides
            # authoritative location-specific data and we should skip RAG to avoid
            # cross-contamination from chunks belonging to other locations
            structured_content, used_graph_rag = await self._get_structured_adventure_context(
                campaign.adventure_document_id,
                adventure_state,
                player_input,
            )

            # Check if this is an opening scene (needs broader RAG context)
            is_opening = any(kw in player_input.lower() for kw in
                ["begin", "start", "new adventure", "opening", "first scene", "set the scene"])

            # Only fetch RAG content when:
            # 1. Opening scene (needs physical descriptions, entrance, lore)
            # 2. GraphRAG was NOT used (fallback to RAG for supplementary details)
            # When GraphRAG IS used, skip RAG to prevent hallucinating creatures/items
            # from other locations in the module
            rag_content = ""

            if is_opening:
                # For opening scenes, get multiple specific queries to ensure we capture:
                # 1. Physical description of the dungeon/location exterior
                # 2. Entrance/approach description
                # 3. Background/setting lore
                rag_parts = []

                # Use already-loaded module for targeted queries
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
            elif not used_graph_rag:
                # Only use RAG when GraphRAG is NOT available
                # When GraphRAG IS used, it provides authoritative location-specific data
                # and RAG could introduce creatures/items from OTHER locations (hallucination source)
                current_location_key = adventure_state.get("current_location_key")
                current_location = adventure_state.get("current_location", "")

                # Build location-specific query to improve relevance
                if current_location_key:
                    # Prioritize current location in query
                    query_text = f"location {current_location_key} {current_location} {player_input}"
                else:
                    query_text = f"{player_input} {current_location}".strip()

                logger.info(f"[DM] RAG query (GraphRAG unavailable): {query_text[:100]}...")

                # Get raw PDF content via RAG for full details
                # Limit to 3 chunks to reduce noise from other locations
                rag_content = await self.retriever.get_adventure_context(
                    query=query_text,
                    adventure_document_id=campaign.adventure_document_id,
                    current_location=current_location,
                    max_chunks=3,
                )
            else:
                logger.info(f"[DM] Skipping RAG - GraphRAG provided authoritative location context")

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

        # LOCATION AGENT: Detect movement and force location updates
        # This ensures proper location tracking even if LLM forgets to call update_adventure_location
        location_context = ""
        if campaign and campaign.adventure_document_id:
            previous_location = adventure_state.get("current_location")
            location_result = await self.location_agent.handle_movement(
                player_input=player_input,
                character=character,
                session=game_session,
                adventure_document_id=str(campaign.adventure_document_id),
            )

            if location_result and not location_result.get("error"):
                # Yield the location update to frontend
                yield {
                    "type": "tool_result",
                    "tool_name": "update_adventure_location",
                    "result": location_result,
                }

                # Update adventure_state with new location (for subsequent processing)
                adventure_state = game_session.adventure_state or {}
                new_location = location_result.get("location", "")
                new_location_key = location_result.get("location_key", "")

                # Add context for DM
                location_context = f"""
## LOCATION TRANSITION (auto-detected)
Player moved from: {previous_location or 'unknown'}
Player is now at: {new_location} (key: {new_location_key})

Describe this new location. Do NOT call update_adventure_location - it has already been called.
"""
                logger.info(f"[LOCATION] Auto-updated: {previous_location} -> {new_location}")

                # Auto-initialize entry sub-area if new location has sub-areas
                if new_location_key and module:
                    entry_result = await self.subarea_agent.auto_init_entry_subarea(
                        location_key=new_location_key,
                        character=character,
                        session=game_session,
                        module_id=str(module.id),
                    )
                    if entry_result and not entry_result.get("error"):
                        # Update adventure_state after sub-area init
                        adventure_state = game_session.adventure_state or {}
                        logger.info(f"[SUBAREA] Auto-initialized entry sub-area: {entry_result.get('subarea_name')}")

        # SUBAREA AGENT: Detect intra-location movement and force sub-area transitions
        # This ensures progressive reveal works even if LLM forgets to call update_subarea_position
        subarea_context = ""
        if campaign and campaign.adventure_document_id and module:
            subarea_result = await self.subarea_agent.handle_subarea_progression(
                player_input=player_input,
                character=character,
                session=game_session,
                module_id=str(module.id),
            )
            if subarea_result and not subarea_result.get("error"):
                yield {
                    "type": "tool_result",
                    "tool_name": "update_subarea_position",
                    "result": subarea_result,
                }
                # Update adventure_state after sub-area change
                adventure_state = game_session.adventure_state or {}
                subarea_context = self.subarea_agent.format_subarea_context(subarea_result)
                logger.info(f"[SUBAREA] Auto-advanced to: {subarea_result.get('subarea_name')}")

        # LOOT AGENT: Detect item pickup and force add_item calls
        loot_context = ""
        loot_results = await self.loot_agent.handle_loot(
            player_input=player_input,
            character=character,
            session=game_session,
        )
        if loot_results:
            for loot_result in loot_results:
                yield loot_result
            loot_context = self.loot_agent.format_loot_context(loot_results)
            logger.info(f"[LOOT] Auto-added {len(loot_results)} items")

        # TIME AGENT: Detect rest/travel and force advance_time calls
        time_result_context = ""
        time_result = await self.time_agent.handle_time_passage(
            player_input=player_input,
            character=character,
            session=game_session,
        )
        if time_result:
            yield {
                "type": "tool_result",
                "tool_name": "advance_time",
                "result": time_result,
            }
            # Also yield healing result separately so frontend can update HP display
            if time_result.get("healing"):
                yield {
                    "type": "tool_result",
                    "tool_name": "apply_damage_or_healing",
                    "result": {
                        "target": character.name,
                        "amount": time_result["healing"].get("healed", 0),
                        "is_healing": True,
                        "new_hp": time_result["healing"].get("new_hp"),
                        "max_hp": time_result["healing"].get("max_hp"),
                        "reason": "natural rest",
                        "visible": True,
                    },
                }
                logger.info(f"[TIME] Rest healing: +{time_result['healing'].get('healed', 0)} HP")
            time_result_context = self.time_agent.format_time_context(time_result)
            logger.info(f"[TIME] Auto-advanced time: {time_result.get('hours_passed', 0)}h {time_result.get('days_passed', 0)}d")

        # SPELL AGENT: Detect spell casting and enforce slot tracking
        spell_context = ""
        spell_result = await self.spell_agent.handle_spell_cast(
            player_input=player_input,
            character=character,
            session=game_session,
        )
        if spell_result:
            # Yield spell slot update to frontend so UI can update
            yield {
                "type": "tool_result",
                "tool_name": "use_spell_slot",
                "result": {
                    "spell_name": spell_result.get("spell_name"),
                    "spell_level": spell_result.get("spell_level"),
                    "success": spell_result.get("success"),
                    "slots_remaining": spell_result.get("slots_remaining"),
                    "slots_total": spell_result.get("slots_total"),
                    "error": spell_result.get("error"),
                    "visible": True,
                },
            }
            spell_context = self.spell_agent.format_spell_context(spell_result)
            if spell_result.get("success"):
                logger.info(f"[SPELL] Cast {spell_result.get('spell_name')} - "
                           f"{spell_result.get('slots_remaining')}/{spell_result.get('slots_total')} slots remaining")
            else:
                logger.info(f"[SPELL] Failed to cast {spell_result.get('spell_name')}: {spell_result.get('error')}")

        # AUTO-START COMBAT: Detect and automatically start encounters when needed
        # This ensures proper initiative and combat tracking even if LLM forgets to call start_encounter
        if campaign and campaign.adventure_document_id:
            if self._should_auto_start_combat(player_input, game_session, adventure_state, adventure_context):
                auto_combat_result = await self._auto_start_encounter(
                    game_session, character, adventure_state
                )
                if auto_combat_result:
                    # Yield the combat start as a tool result to the frontend
                    yield {
                        "type": "tool_result",
                        "tool_name": "start_encounter",
                        "result": auto_combat_result,
                    }
                    # Format initiative announcement for context
                    init_order = auto_combat_result.get("initiative_order", [])
                    player_init = auto_combat_result.get("player_initiative", 0)
                    is_player_first = auto_combat_result.get("is_player_turn", False)
                    enemies = auto_combat_result.get("enemies", [])

                    combat_announcement = f"""
**COMBAT INITIATED AUTOMATICALLY**
Initiative: {character.name} rolled {player_init}
Turn order: {', '.join(init_order)}
{"You act first!" if is_player_first else "The enemies act first!"}
Enemies: {', '.join(e['name'] + f" (HP: {e['hp']}, AC: {e['ac']})" for e in enemies)}

Continue the narrative describing this combat. The player {"has the first action" if is_player_first else "must react to enemy attacks first"}.
"""
                    # Add to adventure context so LLM knows combat has started
                    adventure_context += f"\n\n## COMBAT JUST STARTED\n{combat_announcement}"
                    logger.info(f"[COMBAT] Auto-started combat injected into context")

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

        # Get DM style: campaign override > global setting
        dm_style = ""
        if campaign and campaign.settings:
            dm_style = campaign.settings.get("dm_style", "")
        if not dm_style:
            from app.config import settings as app_settings
            dm_style = app_settings.dm_style or ""
        if dm_style:
            logger.info(f"[DM] Using DM style: {dm_style}")

        system_prompt = build_dm_system_prompt(
            rpg_system="bx-dnd",  # TODO: Get from character/campaign
            rules_context=rag_context,
            character=self._character_to_dict(character),
            game_state=game_session.game_state or {},
            adventure_context=adventure_context,
            journal_context=journal_context,
            time_context=time_context,
            rulebook_markdown=rulebook_markdown,
            dm_style=dm_style,
        )
        logger.info(f"[DM] System prompt built - {len(system_prompt)} chars")

        # Inject active combat context if in combat
        combat_context = await self._get_combat_context(game_session, character)
        if combat_context:
            system_prompt += f"\n\n## ACTIVE COMBAT STATE\n{combat_context}\n"
            logger.info("[DM] Injected active combat context into system prompt")

        # Build conversation history
        messages = await self._build_messages(game_session, player_input)
        logger.info(f"[DM] Built {len(messages)} messages for LLM")

        # Add map images if available (for adventure modules)
        if campaign and campaign.adventure_document_id:
            messages = await self._add_map_images_to_messages(
                messages,
                campaign.adventure_document_id,
                adventure_state,
            )

        # COMBAT AGENT: If in active combat and player takes combat action,
        # use the combat agent to enforce proper mechanics
        combat_result_context = ""
        if game_session.active_combat_id:
            combat_state = await self._load_combat_state(game_session, character)
            if combat_state and combat_state.is_active:
                # Parse player action to see if it's a combat action
                combat_action = self.combat_agent.parse_player_action(player_input, character)

                if combat_action.action_type in ("attack", "cast", "flee", "defend"):
                    logger.info(f"[COMBAT AGENT] Handling combat action: {combat_action.action_type}")

                    # Resolve combat using the agent (yields tool results)
                    combat_result = None
                    async for tool_result in self.combat_agent.resolve_combat_round(
                        combat_action, character, game_session, combat_state
                    ):
                        # Capture the final combat result
                        if isinstance(tool_result, dict):
                            if tool_result.get("type") == "combat_result":
                                combat_result = tool_result.get("result")
                            else:
                                # Yield other tool results to frontend
                                yield tool_result

                    # Get formatted results for DM to narrate
                    if combat_result:
                        combat_result_context = self.combat_agent.format_combat_result_for_dm(
                            combat_result, character
                        )
                        logger.info(f"[COMBAT AGENT] Combat resolved - hit: {combat_result.player_hit}, damage: {combat_result.player_damage}")
                    else:
                        # Fallback context
                        combat_result_context = "\n## COMBAT RESOLVED\nCombat mechanics have been processed. Narrate the results dramatically."

                    logger.info(f"[COMBAT AGENT] Adding combat results to DM context")

        # Determine which tools to use (add adventure tools if adventure is active)
        tools = list(DM_TOOLS)
        tools.extend(JOURNAL_TOOLS)  # Always include journal tools for session continuity
        tools.extend(SOLO_HERO_TOOLS)  # Solo Hero rules for single-character play
        tools.extend(CALENDAR_TOOLS)  # Calendar and time tracking tools
        tools.extend(MAP_TOOLS)  # Dungeon map tools
        tools.extend(ENCOUNTER_TOOLS)  # Persistent encounter tracking tools
        tools.extend(IMAGE_TOOLS)  # Atmospheric image display
        if campaign and campaign.adventure_document_id:
            tools.extend(ADVENTURE_TOOLS)

        # Add location transition context if movement was auto-detected
        if location_context:
            system_prompt += f"\n\n{location_context}\n"

        # Add sub-area progression context if sub-area was auto-advanced
        if subarea_context:
            system_prompt += f"\n\n{subarea_context}\n"

        # Add loot context if items were auto-added
        if loot_context:
            system_prompt += f"\n\n{loot_context}\n"

        # Add time context if time was auto-advanced
        if time_result_context:
            system_prompt += f"\n\n{time_result_context}\n"

        # Add spell context if spell was cast
        if spell_context:
            system_prompt += f"\n\n{spell_context}\n"

        # Add combat result context if combat was resolved
        if combat_result_context:
            system_prompt += f"\n\n{combat_result_context}\n"

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

                    # Block duplicate update_subarea_position calls if subarea agent already handled it
                    if tool_call["name"] == "update_subarea_position" and subarea_context:
                        logger.info(f"[DM] Blocking duplicate update_subarea_position (already handled by subarea agent)")
                        result = {"skipped": True, "reason": "Sub-area already updated by subarea agent", "visible": False}
                        tool_call["result"] = result
                        continue

                    # Block duplicate add_item calls if loot agent already handled it
                    if tool_call["name"] == "add_item" and loot_results:
                        # Check if this item was already added by loot agent
                        item_name = tool_call["input"].get("item_name", "").lower()
                        already_added = any(
                            lr.get("result", {}).get("item", {}).get("name", "").lower() == item_name
                            for lr in loot_results
                        )
                        if already_added:
                            logger.info(f"[DM] Blocking duplicate add_item for: {item_name} (already added by loot agent)")
                            result = {"skipped": True, "reason": "Item already added by loot agent", "visible": False}
                            tool_call["result"] = result
                            continue

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

                        # Ensure damage mentioned in narrative is applied
                        try:
                            damage_result = self.damage_extractor.extract(
                                full_response,
                                all_tool_calls,
                                player_name=character.name,
                            )
                            if damage_result.needs_application:
                                applied_events = await self.damage_extractor.auto_apply(
                                    damage_result, character, game_session
                                )
                                # Yield damage events so frontend can update HP display
                                for event in applied_events:
                                    yield {
                                        "type": "tool_result",
                                        "tool_name": "apply_damage_or_healing",
                                        "result": {
                                            **event,
                                            "visible": True,
                                        },
                                    }
                        except Exception as e:
                            logger.warning(f"[DM] Error applying damage: {e}")

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

    async def _add_map_images_to_messages(
        self,
        messages: List[Dict[str, Any]],
        document_id: UUID,
        adventure_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Add dungeon map images to messages for spatial context.

        Args:
            messages: Current message list
            document_id: Adventure document ID
            adventure_state: Current adventure state

        Returns:
            Updated message list with map images prepended
        """
        # Check if maps already loaded in this session (avoid reloading every turn)
        # We store a flag to avoid repeatedly loading large images
        if adventure_state.get("_maps_loaded_this_session"):
            return messages

        # Get map images for this adventure
        retriever = AdventureDataRetriever(self.db)
        maps = await retriever.get_module_maps(document_id)

        if not maps:
            logger.info("[DM] No map images found for adventure module")
            return messages

        logger.info(f"[DM] Found {len(maps)} map images for module")

        # Load the first/primary map image (usually the dungeon overview)
        # Limit to 1-2 maps to avoid context bloat
        map_content_blocks = []
        maps_to_load = maps[:2]  # Load at most 2 maps

        for map_info in maps_to_load:
            image_block = load_image_as_base64(map_info["path"])
            if image_block:
                # Add a text description before the image
                map_title = map_info.get("title", "Dungeon Map")
                map_content_blocks.append({
                    "type": "text",
                    "text": f"[DUNGEON MAP: {map_title}]\nUse this map for spatial understanding. Room numbers correspond to location keys."
                })
                map_content_blocks.append(image_block)
                logger.info(f"[DM] Loaded map image: {map_title}")

        if not map_content_blocks:
            logger.warning("[DM] Failed to load any map images")
            return messages

        # Insert map images as the first message (user role with image)
        # This ensures the LLM sees the map before any conversation
        map_message = {
            "role": "user",
            "content": map_content_blocks,
        }

        # Also need an assistant acknowledgment to maintain conversation structure
        ack_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "I can see the dungeon map. I will use it for navigation and spatial descriptions."}],
        }

        # Prepend map and acknowledgment to messages
        new_messages = [map_message, ack_message] + messages

        logger.info(f"[DM] Added map images to messages (new total: {len(new_messages)})")
        return new_messages

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

        # NOTE: Location tracking is now handled exclusively by the update_adventure_location tool.
        # Auto-detection from DM response was too error-prone (matched garbage text).
        # The LLM is instructed to call update_adventure_location when the player moves.

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

    async def _get_combat_context(
        self,
        game_session: Session,
        character: Character,
    ) -> str:
        """Get formatted combat context if an encounter is active.

        Loads CombatEncounter + participants from DB and formats
        for injection into the system prompt.
        """
        if not game_session.active_combat_id:
            return ""

        from app.domains.combat.models import (
            CombatEncounter, CombatParticipant, CombatStatus, ParticipantType,
        )
        from app.domains.combat.manager import CombatManager, CombatState, EnemyStats

        try:
            result = await self.db.execute(
                select(CombatEncounter)
                .options(selectinload(CombatEncounter.participants))
                .where(CombatEncounter.id == game_session.active_combat_id)
            )
            encounter = result.scalar_one_or_none()

            if not encounter or encounter.status != CombatStatus.ACTIVE:
                return ""

            # Reconstruct CombatState from DB records
            state = CombatState(
                round_number=encounter.current_round,
                is_active=True,
                initiative_order=[p.name for p in encounter.participants],
            )

            for p in encounter.participants:
                if p.participant_type == ParticipantType.PLAYER:
                    continue
                enemy = EnemyStats(
                    name=p.name,
                    hd=int(p.stats.get("hd", 1) or 1) if p.stats else 1,
                    hp=p.current_hp,
                    max_hp=p.max_hp,
                    ac=p.armor_class or 9,
                    thac0=p.thac0 or 19,
                    damage=str(p.stats.get("damage", "1d6") or "1d6") if p.stats else "1d6",
                    morale=p.morale or 7,
                    xp_value=int(p.stats.get("xp_value", 0) or 0) if p.stats else 0,
                )
                state.enemies[p.name] = enemy

                if p.current_hp <= 0:
                    state.defeated_enemies.append(p.name)
                elif p.morale_broken:
                    state.fled_enemies.append(p.name)

            # Determine current turn
            if encounter.current_turn_index < len(state.initiative_order):
                state.current_turn = state.initiative_order[encounter.current_turn_index]
                state.is_player_turn = state.current_turn == character.name

            # Use CombatManager's formatter
            manager = CombatManager(self.db)
            return manager.get_combat_context(state, character)

        except Exception as e:
            logger.warning(f"[DM] Failed to load combat context: {e}")
            return ""

    async def _load_combat_state(
        self,
        game_session: Session,
        character: Character,
    ) -> Optional["CombatState"]:
        """Load the current combat state from the database.

        Returns CombatState object or None if no active combat.
        """
        if not game_session.active_combat_id:
            return None

        from app.domains.combat.models import (
            CombatEncounter, CombatParticipant, CombatStatus, ParticipantType,
        )
        from app.domains.combat.manager import CombatState, EnemyStats

        try:
            result = await self.db.execute(
                select(CombatEncounter)
                .options(selectinload(CombatEncounter.participants))
                .where(CombatEncounter.id == game_session.active_combat_id)
            )
            encounter = result.scalar_one_or_none()

            if not encounter or encounter.status != CombatStatus.ACTIVE:
                return None

            # Reconstruct CombatState from DB records
            state = CombatState(
                round_number=encounter.current_round,
                is_active=True,
                initiative_order=[p.name for p in encounter.participants],
            )

            for p in encounter.participants:
                if p.participant_type == ParticipantType.PLAYER:
                    # Store player initiative
                    state.player_initiative = p.initiative or 0
                    continue

                enemy = EnemyStats(
                    name=p.name,
                    hd=int(p.stats.get("hd", 1) or 1) if p.stats else 1,
                    hp=p.current_hp,
                    max_hp=p.max_hp,
                    ac=p.armor_class or 9,
                    thac0=p.thac0 or 19,
                    damage=str(p.stats.get("damage", "1d6") or "1d6") if p.stats else "1d6",
                    morale=p.morale or 7,
                    xp_value=int(p.stats.get("xp_value", 0) or 0) if p.stats else 0,
                )
                state.enemies[p.name] = enemy

                if p.current_hp <= 0:
                    state.defeated_enemies.append(p.name)
                elif p.morale_broken:
                    state.fled_enemies.append(p.name)

            # Determine current turn
            if encounter.current_turn_index < len(state.initiative_order):
                state.current_turn = state.initiative_order[encounter.current_turn_index]
                state.is_player_turn = state.current_turn == character.name

            return state

        except Exception as e:
            logger.warning(f"[DM] Failed to load combat state: {e}")
            return None

    async def _get_rulebook_markdown(
        self,
        rpg_system_id: UUID,
        max_length: int = 50000,  # Limit to avoid huge context
    ) -> str:
        """Load rulebook markdown for the character's RPG system.

        Returns formatted markdown content from:
        1. Static rules reference for the specific RPG system (e.g., bx-dnd-rules.md)
        2. Any user-uploaded rulebooks for this system
        """
        from app.domains.campaigns.models import RPGSystem

        content_parts = []
        total_length = 0

        # Get the RPG system code to load the correct rules file
        system_code = "bx-dnd"  # Default fallback
        try:
            result = await self.db.execute(
                select(RPGSystem).where(RPGSystem.id == rpg_system_id)
            )
            rpg_system = result.scalar_one_or_none()
            if rpg_system:
                system_code = rpg_system.code
        except Exception as e:
            logger.warning(f"Failed to lookup RPG system: {e}")

        # Load the static rules file for this system
        # Files are named: {system_code}-rules.md (e.g., bx-dnd-rules.md, ose-rules.md)
        static_rules_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "rules", f"{system_code}-rules.md"
        )
        if os.path.exists(static_rules_path):
            try:
                with open(static_rules_path, 'r', encoding='utf-8') as f:
                    static_rules = f.read()
                content_parts.append(static_rules)
                total_length += len(static_rules)
                logger.info(f"Loaded static {system_code} rules reference ({len(static_rules)} chars)")
            except Exception as e:
                logger.warning(f"Failed to load static rules for {system_code}: {e}")

        # Get user-uploaded rulebooks for this system
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
            logger.warning(f"Failed to query rulebooks: {e}")
            rulebooks = []

        # Load markdown from each user-uploaded rulebook
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
    ) -> tuple[Optional[str], bool]:
        """Get structured adventure context from parsed module data.

        Returns:
            Tuple of (formatted context string or None, whether GraphRAG was used).
            When GraphRAG is used, the context is authoritative and location-specific,
            so additional RAG lookups should be skipped to avoid cross-contamination
            from other locations.
        """
        import json

        logger.info(f"[DM] Getting structured adventure context for document {document_id}")

        # Check for parsed adventure module
        retriever = AdventureDataRetriever(self.db)
        module = await retriever.get_module_for_document(document_id)
        logger.info(f"[DM] Module lookup result: {module.title if module else 'None'}")

        if not module:
            return None, False

        # Build rich context from structured data
        context_parts = []
        full_markdown_text = ""  # Store for extracting current location verbatim text
        used_graph_rag = False  # Track if GraphRAG provided authoritative location data

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
            if summary.get('recommended_party_size'):
                party_size = summary['recommended_party_size']
                context_parts.append(f"Original Party Size: {party_size} (this module was designed for a GROUP - you are adapting it for ONE solo hero)")
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
            # Try GraphRAG context first (structured facts, not prose)
            use_graph_rag = adventure_state.get("use_graph_rag", True)
            graph_context = None

            if use_graph_rag:
                try:
                    graph_provider = GraphContextProvider(self.db)
                    # Pass sub-area state for progressive reveal
                    current_subarea = adventure_state.get("current_subarea")
                    subareas_visited = adventure_state.get("subareas_visited", [])
                    triggered_content = adventure_state.get("triggered_content", [])

                    graph_context = await graph_provider.get_location_context(
                        module.id,
                        current_location_key,
                        current_subarea=current_subarea,
                        subareas_visited=subareas_visited,
                        triggered_content=triggered_content,
                    )
                    if graph_context:
                        logger.info(f"[DM] Using GraphRAG context for location {current_location_key} (subarea: {current_subarea})")
                        context_parts.append(graph_context)
                        used_graph_rag = True  # Mark that we have authoritative location data

                        # CRITICAL: Always inject source_text from DB alongside GraphRAG
                        # GraphRAG descriptions may be truncated; source_text has the FULL module text
                        location_data = await retriever.get_location_context(module.id, current_location_key)
                        if location_data:
                            loc = location_data.get("location", {})
                            source_text = loc.get("source_text")
                            if source_text and len(source_text) > 300:
                                source_text = self._transform_party_to_solo(source_text)
                                context_parts.append("\n### EXACT MODULE TEXT (AUTHORITATIVE - use for ALL details):")
                                context_parts.append(source_text)
                                context_parts.append("--- END MODULE TEXT ---")
                                logger.info(f"[DM] Injected source_text ({len(source_text)} chars) alongside GraphRAG")
                except Exception as e:
                    logger.warning(f"[DM] GraphRAG failed, falling back to prose context: {e}")
                    graph_context = None

            # Fall back to prose-based context if GraphRAG unavailable
            if not graph_context:
                location_context = await retriever.get_location_context(module.id, current_location_key)
                # Also get adjacent locations for spatial context
                adjacent_locations = await retriever.get_adjacent_locations(module.id, current_location_key)
                # Get populated room content for B1-style modules
                populated_content = adventure_state.get("populated_rooms", {}).get(current_location_key)
                if location_context:
                    # Pass full markdown so we can extract verbatim text for this location
                    context_parts.append(self._format_location_context(
                        location_context,
                        full_markdown_text,
                        adjacent_locations=adjacent_locations,
                        populated_content=populated_content,
                    ))

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

        content = "\n".join(context_parts) if context_parts else None
        return content, used_graph_rag

    def _extract_triggered_events(self, verbatim_text: str) -> List[Dict[str, Any]]:
        """Extract triggered events (magic mouths, etc.) from location text.

        These are events that MUST fire when conditions are met.
        """
        import re
        events = []

        if not verbatim_text:
            return events

        text_lower = verbatim_text.lower()

        # Check for magic mouth
        if "magic mouth" in text_lower:
            event = {
                "type": "magic_mouth",
                "trigger": "When player reaches this location",
                "dialogue": [],
                "notes": "",
            }

            # Extract quoted dialogue - look for ALL CAPS quoted text
            # B1 format: "WHO DARES ENTER THIS PLACE..."
            dialogue_pattern = r'"([A-Z][A-Z\s\-—\'!?,\.]+)"'
            matches = re.findall(dialogue_pattern, verbatim_text)
            if matches:
                event["dialogue"] = matches

            # Look for sequence notes
            if "east mouth" in text_lower and "west mouth" in text_lower:
                event["notes"] = "East mouth speaks first, then west mouth replies, then both speak in unison, then laughter fades."
            elif "in unison" in text_lower:
                event["notes"] = "Multiple voices speak in unison."

            if "laughter" in text_lower:
                if "fades" in text_lower:
                    event["dialogue"].append("[LOUD LAUGHTER that fades away]")
                else:
                    event["dialogue"].append("[LAUGHTER]")

            events.append(event)

        # Check for other triggered events
        if "triggered" in text_lower or "when" in text_lower and ("enter" in text_lower or "reach" in text_lower):
            # Generic triggered event detection
            # Look for patterns like "When X happens, Y occurs"
            pass  # Could expand this for other event types

        return events

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

    def _format_location_context(
        self,
        context: Dict[str, Any],
        full_markdown: str = "",
        adjacent_locations: Optional[Dict[str, Dict[str, Any]]] = None,
        populated_content: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format location context for the DM prompt.

        Args:
            context: Structured location data from database
            full_markdown: Full module markdown to extract verbatim text
            adjacent_locations: Map of direction -> adjacent location info
            populated_content: B1-style populated room content (monsters, treasure)
        """
        import json

        parts = []
        loc = context.get("location", {})

        if loc:
            parts.append(f"\n## CURRENT LOCATION: {loc.get('name', '')} ({loc.get('key', '')})")

            # CRITICAL: Include verbatim text for this location
            # This is the AUTHORITATIVE source - contains all details like body descriptions
            location_key = loc.get('key', '')

            # PRIORITY 1: Use source_text if available (most reliable - from parsing)
            verbatim_text = loc.get('source_text')

            # PRIORITY 2: Fall back to regex extraction if source_text is empty
            if not verbatim_text and full_markdown and location_key:
                verbatim_text = self._extract_location_from_markdown(full_markdown, location_key)

            # Process verbatim text if we have it from either source
            if verbatim_text:
                parts.append("\n### EXACT MODULE TEXT FOR THIS LOCATION (AUTHORITATIVE SOURCE):")
                parts.append("Use this text for ALL descriptions, treasure, bodies, and details.")
                parts.append("Do NOT invent details not mentioned here.\n")

                # Check if location is described as empty/barren
                text_lower = verbatim_text.lower()
                if any(word in text_lower for word in ["empty", "barren", "nothing of interest", "no markings"]):
                    parts.append("⚠️ WARNING: This location is described as EMPTY/BARREN.")
                    parts.append("DO NOT add atmosphere, hints, or 'you sense' descriptions.")
                    parts.append("Just describe empty stone walls. That's it.\n")

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

            # ADJACENT LOCATIONS (what's behind each exit)
            if adjacent_locations:
                parts.append("\n### ADJACENT AREAS (what's behind each exit):")
                parts.append("Use this to describe what the player would see/find in each direction:")
                for direction, adj_info in adjacent_locations.items():
                    adj_name = adj_info.get("name", "Unknown")
                    adj_key = adj_info.get("key", "")
                    adj_brief = adj_info.get("brief", "")
                    key_str = f" ({adj_key})" if adj_key else ""
                    parts.append(f"- {direction.upper()} → {adj_name}{key_str}")
                    if adj_brief:
                        parts.append(f"    Brief: {adj_brief}")

            # POPULATED CONTENT (for B1-style modules with blank rooms)
            if populated_content:
                parts.append("\n### POPULATED CONTENT (DM-assigned monsters/treasure)")
                parts.append("This room was blank and has been populated with the following:")

                pop_monsters = populated_content.get("monsters")
                if pop_monsters:
                    parts.append("\n**Monsters:**")
                    for monster in pop_monsters:
                        name = monster.get("name", "Unknown")
                        count = monster.get("count", 1)
                        hp = monster.get("hp", [])
                        behavior = monster.get("behavior", "")
                        hp_str = f" (HP: {', '.join(str(h) for h in hp)})" if hp else ""
                        parts.append(f"- {count}x {name}{hp_str}")
                        if behavior:
                            parts.append(f"  Behavior: {behavior}")

                pop_treasure = populated_content.get("treasure")
                if pop_treasure:
                    parts.append("\n**Treasure:**")
                    for treasure in pop_treasure:
                        item = treasure.get("item", "Unknown")
                        location = treasure.get("location", "")
                        loc_str = f" ({location})" if location else ""
                        parts.append(f"- {item}{loc_str}")

                pop_notes = populated_content.get("notes")
                if pop_notes:
                    parts.append(f"\n**DM Notes:** {pop_notes}")

            # TRIGGERED EVENTS - extract from verbatim text and mark as MANDATORY
            if verbatim_text:
                triggered_events = self._extract_triggered_events(verbatim_text)
                if triggered_events:
                    parts.append("\n### ⚠️ MANDATORY TRIGGERED EVENTS ⚠️")
                    parts.append("These events MUST occur when the player enters/explores this location:")
                    for event in triggered_events:
                        parts.append(f"\n**{event['type'].upper()}:**")
                        parts.append(f"Trigger: {event['trigger']}")
                        if event.get('dialogue'):
                            parts.append(f"EXACT DIALOGUE (use verbatim):")
                            for line in event['dialogue']:
                                parts.append(f'  "{line}"')
                        if event.get('notes'):
                            parts.append(f"Notes: {event['notes']}")
                    parts.append("\n**YOU MUST EXECUTE THESE EVENTS. DO NOT SKIP THEM.**")

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

        # Final reminder about module fidelity
        parts.append("\n---")
        parts.append("### REMINDER: USE THE MODULE TEXT ABOVE")
        parts.append("- If the module says 'empty and barren' → describe EMPTY STONE WALLS, nothing else")
        parts.append("- If there are triggered events → EXECUTE THEM with exact dialogue")
        parts.append("- Do NOT add 'you sense', 'you feel', atmosphere not in the text")
        parts.append("- The module text is AUTHORITATIVE. Your job is to present it, not embellish it.")

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
