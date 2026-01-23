"""Adventure planning service for session preparation."""

from typing import Dict, Any, List, Optional
from uuid import UUID
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.llm.client import ClaudeClient
from app.llm.prompts.adventure_prompt import build_planning_prompt
from app.rag.retriever import RAGRetriever
from app.domains.sessions.adventure_state import (
    AdventureState,
    PlannedScene,
    create_initial_adventure_state,
)
from app.domains.characters.models import Character
from app.domains.sourcebooks.models import PDFDocument

logger = logging.getLogger(__name__)


class AdventurePlanner:
    """Plans adventure sessions using RAG content and LLM."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self.client = ClaudeClient()
        self.retriever = RAGRetriever(session)

    async def get_adventure_document(self, document_id: UUID) -> Optional[PDFDocument]:
        """Fetch the adventure document."""
        result = await self.db.execute(
            select(PDFDocument).where(PDFDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def plan_session(
        self,
        adventure_document_id: UUID,
        current_state: Optional[AdventureState],
        character: Character,
        rpg_system_id: UUID,
    ) -> AdventureState:
        """
        Plan upcoming scenes for a session.

        Reads adventure module content via RAG, considers current progress,
        and uses LLM to plan 3-5 upcoming scenes with triggers and contingencies.
        """
        # Get the adventure document
        adventure_doc = await self.get_adventure_document(adventure_document_id)
        if not adventure_doc:
            logger.error(f"Adventure document {adventure_document_id} not found")
            return current_state or {}

        adventure_title = adventure_doc.title or adventure_doc.original_filename

        # Initialize state if needed
        if not current_state or not current_state.get("adventure_document_id"):
            current_state = create_initial_adventure_state(
                adventure_document_id=str(adventure_document_id),
                adventure_title=adventure_title,
            )

        # Get adventure content from RAG
        # Query for the START section and introduction
        start_context = await self.retriever.query(
            query="START beginning players arrive entrance gate first scene opening",
            document_ids=[adventure_document_id],
            top_k=4,
        )

        # Query for overview/background
        overview_context = await self.retriever.query(
            query="BACKGROUND adventure overview introduction story hook premise",
            document_ids=[adventure_document_id],
            top_k=3,
        )

        # Query for current area if we have a location
        area_context = []
        if current_state.get("current_location"):
            area_context = await self.retriever.query(
                query=f"area room {current_state.get('current_location')} description encounters",
                document_ids=[adventure_document_id],
                top_k=3,
            )

        # Query for relevant NPCs
        npc_context = await self.retriever.query(
            query="NPC character important people villain boss",
            document_ids=[adventure_document_id],
            top_k=3,
        )

        # Build context string - prioritize START section, then overview, then NPCs
        all_chunks = start_context + overview_context + area_context + npc_context
        # Deduplicate by chunk_id
        seen_ids = set()
        unique_chunks = []
        for chunk in all_chunks:
            if chunk.get("chunk_id") not in seen_ids:
                seen_ids.add(chunk.get("chunk_id"))
                unique_chunks.append(chunk)
        adventure_content = self._format_rag_chunks(unique_chunks[:10])

        # Build planning prompt
        planning_prompt = build_planning_prompt(
            adventure_title=adventure_title,
            adventure_content=adventure_content,
            current_state=current_state,
            character=self._character_to_summary(character),
        )

        # Call LLM for planning
        response = await self.client.chat(
            messages=[{"role": "user", "content": planning_prompt}],
            system="You are an expert tabletop RPG adventure planner. Your job is to plan upcoming scenes for a solo RPG session based on the adventure module content. Always respond with valid JSON.",
        )

        # Extract text from response dict
        response_text = ""
        for block in response.get("content", []):
            if block.get("type") == "text":
                response_text += block.get("text", "")

        # Parse the response
        try:
            planned_data = self._parse_planning_response(response_text)

            # Update the adventure state with planned scenes
            from datetime import datetime

            current_state["upcoming_scenes"] = planned_data.get("scenes", [])
            current_state["session_goals"] = planned_data.get("goals", [])
            current_state["last_planned"] = datetime.utcnow().isoformat()
            current_state["last_updated"] = datetime.utcnow().isoformat()

            # Add any new plot threads from planning
            if planned_data.get("plot_threads"):
                existing_threads = {t.get("name") for t in current_state.get("active_plot_threads", [])}
                for thread in planned_data.get("plot_threads", []):
                    if thread.get("name") not in existing_threads:
                        current_state.setdefault("active_plot_threads", []).append(thread)

            logger.info(f"Planned {len(current_state.get('upcoming_scenes', []))} scenes for adventure")

        except Exception as e:
            logger.error(f"Failed to parse planning response: {e}")
            # Continue with unplanned state

        return current_state

    def _format_rag_chunks(self, chunks: List[Dict[str, Any]]) -> str:
        """Format RAG chunks for the prompt."""
        if not chunks:
            return "No adventure content available."

        parts = []
        for chunk in chunks:
            source = f"[{chunk.get('document_title', 'Adventure')}, p.{chunk.get('page_numbers', '?')}]"
            parts.append(f"{source}\n{chunk.get('content', '')}")

        return "\n\n---\n\n".join(parts)

    def _character_to_summary(self, character: Character) -> str:
        """Create a character summary for planning."""
        attrs = character.attributes or {}
        return f"""
Name: {character.name}
Class: {attrs.get('character_class', 'Unknown')}
Level: {character.level}
HP: {character.current_hp}/{character.max_hp}
Alignment: {attrs.get('alignment', 'Neutral')}
Equipment: {', '.join(attrs.get('equipment', [])) or 'Standard gear'}
"""

    def _parse_planning_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM planning response."""
        # Try to extract JSON from the response
        response = response.strip()

        # Find JSON block if wrapped in markdown
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Try to find any JSON object in the response
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                logger.warning(f"Could not parse planning response as JSON: {response[:200]}")
                return {"scenes": [], "goals": [], "plot_threads": []}

        # Normalize the response structure
        scenes = []
        for scene in data.get("scenes", data.get("upcoming_scenes", [])):
            scenes.append(PlannedScene(
                name=scene.get("name", "Unnamed Scene"),
                description=scene.get("description", ""),
                trigger=scene.get("trigger", "Player enters area"),
                npcs_monsters=scene.get("npcs_monsters", scene.get("npcs", [])),
                possible_outcomes=scene.get("possible_outcomes", scene.get("outcomes", [])),
                plot_threads=scene.get("plot_threads", []),
            ))

        return {
            "scenes": scenes,
            "goals": data.get("goals", data.get("session_goals", [])),
            "plot_threads": data.get("plot_threads", data.get("active_plot_threads", [])),
        }

    async def get_adventure_context(
        self,
        adventure_document_id: UUID,
        adventure_state: AdventureState,
        query: str,
    ) -> str:
        """
        Get relevant adventure content for a specific query.

        Used during gameplay to provide context-aware adventure information.
        """
        # Query for content related to the player's action
        chunks = await self.retriever.query(
            query=query,
            document_ids=[adventure_document_id],
            top_k=5,
        )

        # Also query for current scene/location if available
        if adventure_state.get("current_scene"):
            scene_chunks = await self.retriever.query(
                query=adventure_state["current_scene"],
                document_ids=[adventure_document_id],
                top_k=2,
            )
            chunks.extend(scene_chunks)

        if adventure_state.get("current_location"):
            location_chunks = await self.retriever.query(
                query=adventure_state["current_location"],
                document_ids=[adventure_document_id],
                top_k=2,
            )
            chunks.extend(location_chunks)

        return self._format_rag_chunks(chunks)
