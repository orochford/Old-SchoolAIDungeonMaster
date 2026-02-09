"""SubArea sub-agent that enforces progressive reveal within locations.

When a player progresses through a complex location (e.g., a corridor with
alcoves, steps, and an intersection), this agent detects intra-location
movement and forces update_subarea_position calls so the DM only reveals
content the player has actually reached.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.domains.adventures.graph_rag.context_provider import GraphContextProvider
from app.domains.adventures.graph_rag.schema import SubAreaNode

logger = logging.getLogger(__name__)


@dataclass
class SubAreaIntent:
    """Parsed intra-location movement intent."""
    is_subarea_movement: bool
    target_subarea_id: Optional[str] = None
    target_subarea_name: Optional[str] = None
    is_forward_progression: bool = False
    confidence: float = 0.0


class SubAreaAgent:
    """Sub-agent that handles intra-location progression with enforced tool usage."""

    # Patterns indicating forward/continued movement within a location
    FORWARD_PATTERNS = [
        "continue", "press on", "move forward", "go ahead", "keep going",
        "walk forward", "proceed", "advance", "push on", "carry on",
        "go further", "move on", "head on", "on to", "past the",
        "go deeper", "press forward", "move ahead", "keep moving",
        "walk on", "step forward", "forge ahead",
    ]

    # Patterns that indicate examining/staying in current sub-area (not movement)
    STAY_PATTERNS = [
        "search", "examine", "look at", "inspect", "check",
        "investigate", "study", "read", "open", "touch",
        "listen", "smell", "taste",
    ]

    def __init__(self, tool_handler: ToolHandler, db_session: AsyncSession):
        self.tool_handler = tool_handler
        self.db = db_session

    def parse_subarea_intent(
        self,
        player_input: str,
        current_subarea: Optional[str],
        sub_areas: List[SubAreaNode],
    ) -> SubAreaIntent:
        """Detect intra-location movement from player input.

        Args:
            player_input: The player's action text
            current_subarea: ID of the current sub-area (None if not initialized)
            sub_areas: List of sub-areas for the current location

        Returns:
            SubAreaIntent with parsed movement details
        """
        input_lower = player_input.lower().strip()

        if not sub_areas:
            return SubAreaIntent(is_subarea_movement=False, confidence=0.9)

        # Check for stay-in-place actions first
        for stay_pattern in self.STAY_PATTERNS:
            if stay_pattern in input_lower:
                # Unless they also have forward movement
                if not any(fwd in input_lower for fwd in self.FORWARD_PATTERNS):
                    return SubAreaIntent(is_subarea_movement=False, confidence=0.8)

        # Check for specific sub-area targeting by name
        for sa in sub_areas:
            sa_name_lower = sa.name.lower()
            # Handle merged names like "Steps / Intersection / Battle Scene"
            name_parts = [p.strip().lower() for p in sa_name_lower.split("/")]

            for name_part in name_parts:
                if len(name_part) < 3:
                    continue
                # "go to the intersection", "check the alcoves", "head to the steps"
                if name_part in input_lower:
                    return SubAreaIntent(
                        is_subarea_movement=True,
                        target_subarea_id=sa.id,
                        target_subarea_name=sa.name,
                        is_forward_progression=False,
                        confidence=0.9,
                    )

            # Also check individual keywords from the name
            for word in sa_name_lower.split():
                if len(word) < 4:
                    continue
                # Match significant words like "alcoves", "intersection", "steps"
                if word in ("entrance", "first", "second", "third", "far"):
                    continue  # Too generic on their own
                if re.search(rf'\b{re.escape(word)}\b', input_lower):
                    # Matched a keyword - check context suggests going there
                    movement_context = any(
                        mv in input_lower for mv in
                        ["go", "head", "move", "walk", "to the", "toward", "towards", "on to"]
                    )
                    if movement_context:
                        return SubAreaIntent(
                            is_subarea_movement=True,
                            target_subarea_id=sa.id,
                            target_subarea_name=sa.name,
                            is_forward_progression=False,
                            confidence=0.7,
                        )

        # Check for forward progression patterns
        has_forward = any(
            fwd in input_lower for fwd in self.FORWARD_PATTERNS
        )
        if has_forward:
            return SubAreaIntent(
                is_subarea_movement=True,
                target_subarea_id=None,  # Will be resolved to next in sequence
                target_subarea_name=None,
                is_forward_progression=True,
                confidence=0.8,
            )

        return SubAreaIntent(is_subarea_movement=False, confidence=0.7)

    def _resolve_next_subarea(
        self,
        current_subarea: Optional[str],
        sub_areas: List[SubAreaNode],
    ) -> Optional[SubAreaNode]:
        """Get the next sub-area in sequence after the current one.

        Args:
            current_subarea: ID of current sub-area
            sub_areas: All sub-areas for this location, sorted by sequence

        Returns:
            Next SubAreaNode, or None if already at the end
        """
        if not sub_areas:
            return None

        sorted_areas = sorted(sub_areas, key=lambda sa: sa.sequence)

        if current_subarea is None:
            # Not initialized - return entry sub-area
            return sorted_areas[0]

        # Find current position and return next
        for i, sa in enumerate(sorted_areas):
            if sa.id == current_subarea:
                if i + 1 < len(sorted_areas):
                    return sorted_areas[i + 1]
                return None  # Already at the end

        # Current subarea not found in list - return first
        return sorted_areas[0]

    def _get_entry_subarea(self, sub_areas: List[SubAreaNode]) -> Optional[SubAreaNode]:
        """Get the entry sub-area for a location."""
        if not sub_areas:
            return None

        # Prefer explicitly marked entry
        for sa in sub_areas:
            if sa.is_entry:
                return sa

        # Fall back to lowest sequence
        sorted_areas = sorted(sub_areas, key=lambda sa: sa.sequence)
        return sorted_areas[0] if sorted_areas else None

    async def handle_subarea_progression(
        self,
        player_input: str,
        character: Character,
        session: Session,
        module_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle intra-location progression.

        Detects movement within a location and forces update_subarea_position.

        Args:
            player_input: Player's action text
            character: Player character
            session: Game session
            module_id: Adventure module ID (UUID string)

        Returns:
            Tool result dict if sub-area was updated, None otherwise
        """
        if not module_id:
            return None

        adventure_state = session.adventure_state or {}
        current_location_key = adventure_state.get("current_location_key")

        if not current_location_key:
            return None

        # Get graph and sub-areas for current location
        try:
            from uuid import UUID
            graph_provider = GraphContextProvider(self.db)
            graph = await graph_provider.get_graph(UUID(str(module_id)))

            if not graph:
                return None

            # Get sub-areas for current location
            location_node = graph.locations.get(current_location_key)
            if not location_node or not location_node.sub_areas:
                return None

            sub_area_nodes = [
                graph.sub_areas[sa_id]
                for sa_id in location_node.sub_areas
                if sa_id in graph.sub_areas
            ]

            if not sub_area_nodes:
                return None

        except Exception as e:
            logger.warning(f"[SUBAREA] Failed to load graph/sub-areas: {e}")
            return None

        current_subarea = adventure_state.get("current_subarea")

        # Parse player intent
        intent = self.parse_subarea_intent(
            player_input, current_subarea, sub_area_nodes
        )

        if not intent.is_subarea_movement:
            logger.debug(f"[SUBAREA] No sub-area movement detected in: {player_input[:50]}...")
            return None

        if intent.confidence < 0.5:
            logger.debug(f"[SUBAREA] Low confidence sub-area movement: {intent.confidence}")
            return None

        # Determine target sub-area
        target = None
        if intent.target_subarea_id:
            # Specific sub-area targeted
            target = next(
                (sa for sa in sub_area_nodes if sa.id == intent.target_subarea_id),
                None,
            )
        elif intent.is_forward_progression:
            # Move to next in sequence
            target = self._resolve_next_subarea(current_subarea, sub_area_nodes)

        if not target:
            logger.debug(f"[SUBAREA] Could not determine target sub-area")
            return None

        # Don't update if already at this sub-area
        if target.id == current_subarea:
            logger.debug(f"[SUBAREA] Already at sub-area {current_subarea}")
            return None

        logger.info(
            f"[SUBAREA] Advancing: {current_subarea} -> {target.id} ({target.name})"
        )

        # Force the sub-area update
        result = await self.tool_handler.execute(
            tool_name="update_subarea_position",
            tool_input={
                "subarea_id": target.id,
                "subarea_name": target.name,
                "triggered_content": target.triggers or [],
            },
            character=character,
            session=session,
        )

        if result and not result.get("error"):
            # Attach sub-area description for context
            result["subarea_description"] = target.description
            result["subarea_triggers"] = target.triggers
            result["subarea_is_entry"] = target.is_entry
            result["subarea_is_exit"] = target.is_exit

        return result

    async def auto_init_entry_subarea(
        self,
        location_key: str,
        character: Character,
        session: Session,
        module_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Auto-initialize the entry sub-area when entering a new location.

        Called after location_agent moves the player to a new room.
        Sets current_subarea to the entry point so progressive reveal activates.

        Args:
            location_key: The new location's key
            character: Player character
            session: Game session
            module_id: Adventure module ID (UUID string)

        Returns:
            Tool result dict if entry sub-area was set, None otherwise
        """
        try:
            from uuid import UUID
            graph_provider = GraphContextProvider(self.db)
            graph = await graph_provider.get_graph(UUID(str(module_id)))

            if not graph:
                return None

            location_node = graph.locations.get(location_key)
            if not location_node or not location_node.sub_areas:
                return None

            sub_area_nodes = [
                graph.sub_areas[sa_id]
                for sa_id in location_node.sub_areas
                if sa_id in graph.sub_areas
            ]

            if not sub_area_nodes:
                return None

            entry = self._get_entry_subarea(sub_area_nodes)
            if not entry:
                return None

            logger.info(
                f"[SUBAREA] Auto-initializing entry sub-area for location {location_key}: "
                f"{entry.id} ({entry.name})"
            )

            result = await self.tool_handler.execute(
                tool_name="update_subarea_position",
                tool_input={
                    "subarea_id": entry.id,
                    "subarea_name": entry.name,
                    "triggered_content": entry.triggers or [],
                },
                character=character,
                session=session,
            )

            if result and not result.get("error"):
                result["subarea_description"] = entry.description
                result["subarea_triggers"] = entry.triggers
                result["subarea_is_entry"] = entry.is_entry
                result["subarea_is_exit"] = entry.is_exit

            return result

        except Exception as e:
            logger.warning(f"[SUBAREA] Failed to auto-init entry sub-area: {e}")
            return None

    def format_subarea_context(self, result: Dict[str, Any]) -> str:
        """Format sub-area transition for DM context.

        Args:
            result: Tool result from update_subarea_position

        Returns:
            Formatted context string for DM
        """
        lines = ["## SUB-AREA PROGRESSION (auto-detected)"]

        subarea_name = result.get("subarea_name", "Unknown")
        previous = result.get("previous_subarea")

        if previous:
            lines.append(f"Player advanced from sub-area: {previous}")
        lines.append(f"Player is now at: **{subarea_name}** (id: {result.get('subarea_id', '')})")

        # Include the sub-area's description
        description = result.get("subarea_description", "")
        if description:
            lines.append(f"\n### What the player sees in this sub-area:")
            lines.append(description)

        # Note any triggers that fire
        triggers = result.get("subarea_triggers", [])
        if triggers:
            lines.append(f"\n### TRIGGERS THAT FIRE HERE: {', '.join(triggers)}")
            lines.append("You MUST include these triggered events in your narration.")

        # Instructions for the DM
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.append("- Describe ONLY what is visible in this sub-area")
        lines.append("- Do NOT skip ahead to describe areas the player hasn't reached")
        lines.append("- Do NOT call update_subarea_position - it has already been called")

        if result.get("subarea_is_entry"):
            lines.append("- This is the ENTRY point - describe the initial view of the location")
        if result.get("subarea_is_exit"):
            lines.append("- This is the final area - include exits to other locations")

        return "\n".join(lines)
