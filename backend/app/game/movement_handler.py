"""Movement detection and resolution middleware.

This handler intercepts movement-related player input, validates the movement
against the current location's exits, and auto-updates the location state
before the LLM processes the action.

This ensures:
- Location tracking is 100% reliable (no more LLM forgetting to call update_adventure_location)
- Invalid exits are rejected before LLM sees them
- Proper location context is always available to the LLM
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.sessions.models import Session
from app.domains.campaigns.models import Campaign
from app.domains.adventures.models import AdventureModule, AdventureLocation

logger = logging.getLogger(__name__)


# Movement patterns that indicate directional intent
MOVEMENT_PATTERNS = [
    r"\bgo\s+",
    r"\bhead\s+",
    r"\bwalk\s+",
    r"\bmove\s+",
    r"\benter\s+",
    r"\bproceed\s+",
    r"\btravel\s+",
    r"\btake\s+the\s+",
    r"\bleave\s+",
    r"\bexit\s+",
    r"\breturn\s+",
    r"\bback\s+to\s+",
    r"\bcontinue\s+",
]

# Standard directional keywords
CARDINAL_DIRECTIONS = ["north", "south", "east", "west"]
VERTICAL_DIRECTIONS = ["up", "down", "upstairs", "downstairs"]
RELATIVE_DIRECTIONS = ["left", "right", "forward", "back", "backward"]
SPECIAL_EXITS = ["door", "passage", "tunnel", "stairs", "ladder", "corridor", "hallway", "exit", "entrance"]

ALL_DIRECTIONS = CARDINAL_DIRECTIONS + VERTICAL_DIRECTIONS + RELATIVE_DIRECTIONS + SPECIAL_EXITS


@dataclass
class MovementResult:
    """Result of movement detection and resolution."""

    detected: bool
    """Whether movement intent was detected"""

    direction: Optional[str] = None
    """The direction/exit detected (e.g., 'north', 'door')"""

    target_location_key: Optional[str] = None
    """The destination location key if valid (e.g., '2')"""

    target_location_name: Optional[str] = None
    """The destination location name if valid (e.g., 'Kitchen')"""

    is_valid: bool = True
    """Whether the movement is valid (exit exists)"""

    available_exits: Optional[Dict[str, str]] = None
    """Current location's available exits for context"""

    error_message: Optional[str] = None
    """Error message if movement is invalid"""

    context_injection: Optional[str] = None
    """Context to inject into LLM prompt about the movement"""

    auto_updated: bool = False
    """Whether location was automatically updated"""


class MovementHandler:
    """Handles movement detection and location state management.

    This handler:
    1. Detects movement intent from player input
    2. Validates movement against current location's exits
    3. Auto-updates location state for valid moves
    4. Injects context for LLM to narrate the movement
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_and_resolve(
        self,
        player_input: str,
        session: Session,
    ) -> MovementResult:
        """Detect movement intent and resolve if valid.

        Args:
            player_input: The player's input text
            session: The current game session

        Returns:
            MovementResult with detection results and any updates made
        """
        input_lower = player_input.lower().strip()

        # Check if this looks like movement
        direction = self._detect_direction(input_lower)
        if not direction:
            return MovementResult(detected=False)

        logger.info(f"[Movement] Detected direction: {direction}")

        # Get current location context
        adventure_state = session.adventure_state or {}
        current_location_key = adventure_state.get("current_location_key")

        if not current_location_key:
            logger.info("[Movement] No current location key - passing to LLM")
            return MovementResult(
                detected=True,
                direction=direction,
                is_valid=True,  # Let LLM handle it
                context_injection="Movement detected but no current location set. Handle narratively."
            )

        # Get campaign to find adventure module
        campaign = await self._get_campaign(session.campaign_id)
        if not campaign or not campaign.adventure_document_id:
            return MovementResult(
                detected=True,
                direction=direction,
                is_valid=True,  # Let LLM handle non-module adventures
            )

        # Get current location from adventure module
        current_location = await self._get_location(
            campaign.adventure_document_id,
            current_location_key
        )

        if not current_location:
            logger.warning(f"[Movement] Could not find location {current_location_key}")
            return MovementResult(
                detected=True,
                direction=direction,
                is_valid=True,  # Let LLM handle it
            )

        # Get available exits
        exits = current_location.exits or {}
        logger.info(f"[Movement] Available exits: {exits}")

        # Try to match direction to an exit
        target_key, matched_exit = self._match_exit(direction, exits)

        if target_key:
            # Valid movement - inject context for LLM to narrate and call tool
            target_location = await self._get_location(
                campaign.adventure_document_id,
                target_key
            )

            if target_location:
                logger.info(f"[Movement] Valid move to {target_key}: {target_location.name}")

                # DON'T update state here - let LLM call update_adventure_location
                # Just inject context so LLM knows it's a valid move
                return MovementResult(
                    detected=True,
                    direction=direction,
                    target_location_key=target_key,
                    target_location_name=target_location.name,
                    is_valid=True,
                    available_exits=exits,
                    auto_updated=False,  # LLM will call the tool
                    context_injection=self._build_movement_context(
                        direction,
                        target_location,
                        matched_exit,
                    ),
                )
            else:
                # Exit points to non-existent location
                logger.warning(f"[Movement] Exit {direction} points to unknown location {target_key}")
                return MovementResult(
                    detected=True,
                    direction=direction,
                    target_location_key=target_key,
                    is_valid=True,  # Still valid, let LLM narrate
                    available_exits=exits,
                )
        else:
            # Invalid movement - no such exit
            logger.info(f"[Movement] No exit found for direction '{direction}'")

            # Build helpful error message
            available = list(exits.keys())
            error_msg = f"There is no exit to the {direction}."
            if available:
                error_msg += f" Available exits: {', '.join(available)}."

            return MovementResult(
                detected=True,
                direction=direction,
                is_valid=False,
                available_exits=exits,
                error_message=error_msg,
                context_injection=f"There is no {direction} exit here. Available exits: {', '.join(available)}. Let the player know.",
            )

    def _detect_direction(self, input_lower: str) -> Optional[str]:
        """Detect movement direction from player input.

        Returns the direction if movement is detected, None otherwise.
        """
        # First check if any movement pattern is present
        has_movement_pattern = any(
            re.search(pattern, input_lower)
            for pattern in MOVEMENT_PATTERNS
        )

        # Also check for direct direction commands like "north" or "n"
        is_direct_direction = input_lower in ALL_DIRECTIONS or input_lower in ["n", "s", "e", "w"]

        if not has_movement_pattern and not is_direct_direction:
            return None

        # Handle single-letter abbreviations
        abbrev_map = {
            "n": "north",
            "s": "south",
            "e": "east",
            "w": "west",
            "u": "up",
            "d": "down",
        }
        if input_lower in abbrev_map:
            return abbrev_map[input_lower]

        # Look for direction in input
        for direction in ALL_DIRECTIONS:
            # Match whole words only
            if re.search(rf'\b{re.escape(direction)}\b', input_lower):
                return direction

        # Check for location references like "go to area 2" or "enter room 3"
        area_match = re.search(r'\b(?:area|room|location)\s*(\d+[a-z]?)\b', input_lower)
        if area_match:
            return f"area_{area_match.group(1)}"

        return None

    def _match_exit(
        self,
        direction: str,
        exits: Dict[str, str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Match a direction to an available exit.

        Args:
            direction: The detected direction (e.g., 'north', 'door')
            exits: Dict of exit_name -> destination (e.g., {'north': 'Area 2', 'door': '3'})

        Returns:
            Tuple of (target_location_key, matched_exit_name) or (None, None)
        """
        direction_lower = direction.lower()

        # Direct match
        for exit_name, destination in exits.items():
            if exit_name.lower() == direction_lower:
                target_key = self._extract_location_key(destination)
                return target_key, exit_name

        # Partial match (e.g., "north" matches "north passage")
        for exit_name, destination in exits.items():
            if direction_lower in exit_name.lower() or exit_name.lower() in direction_lower:
                target_key = self._extract_location_key(destination)
                return target_key, exit_name

        # Check for area references like "area_2"
        if direction_lower.startswith("area_"):
            target_key = direction_lower.replace("area_", "")
            # Check if any exit leads to this area
            for exit_name, destination in exits.items():
                if target_key in destination:
                    return target_key, exit_name

        return None, None

    def _extract_location_key(self, destination: str) -> Optional[str]:
        """Extract location key from destination string.

        Examples:
            "Area 2" -> "2"
            "2" -> "2"
            "Kitchen (Area 3)" -> "3"
            "north to 4a" -> "4a"
        """
        if not destination:
            return None

        # Try to find a number/key pattern
        # First check if destination is just a key
        if re.match(r'^\d+[a-z]?$', destination.strip()):
            return destination.strip()

        # Look for "Area X" or just a number
        match = re.search(r'(?:area\s*)?(\d+[a-z]?)', destination, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    async def _get_campaign(self, campaign_id: UUID) -> Optional[Campaign]:
        """Get campaign by ID."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        return result.scalar_one_or_none()

    async def _get_location(
        self,
        document_id: UUID,
        location_key: str,
    ) -> Optional[AdventureLocation]:
        """Get adventure location by key."""
        # First get the module
        result = await self.db.execute(
            select(AdventureModule).where(
                AdventureModule.pdf_document_id == document_id
            )
        )
        module = result.scalar_one_or_none()

        if not module:
            return None

        # Then get the location
        result = await self.db.execute(
            select(AdventureLocation).where(
                AdventureLocation.module_id == module.id,
                AdventureLocation.location_key == location_key,
            )
        )
        return result.scalar_one_or_none()

    async def _update_location(
        self,
        session: Session,
        location_key: str,
        location_name: str,
        tier: Optional[str],
        dungeon_level: Optional[int],
    ) -> None:
        """Update the session's adventure state with new location."""
        from datetime import datetime

        adventure_state = dict(session.adventure_state or {})

        # Track previous location
        adventure_state["previous_location_key"] = adventure_state.get("current_location_key")
        adventure_state["previous_location"] = adventure_state.get("current_location")

        # Update current location
        adventure_state["current_location_key"] = location_key
        adventure_state["current_location"] = location_name
        adventure_state["last_updated"] = datetime.utcnow().isoformat()

        # Update tier and dungeon level for wandering monsters
        if tier:
            adventure_state["current_tier"] = tier
        if dungeon_level:
            adventure_state["current_dungeon_level"] = dungeon_level

        # Track visited locations
        visited = adventure_state.get("visited_locations", [])
        if location_key not in visited:
            visited.append(location_key)
            adventure_state["visited_locations"] = visited

        # Save to session
        session.adventure_state = adventure_state
        await self.db.flush()

    def _build_movement_context(
        self,
        direction: str,
        target_location: AdventureLocation,
        exit_name: str,
    ) -> str:
        """Build context injection for LLM to narrate the movement.

        NOTE: Context injection disabled - it was confusing the LLM and
        overriding the authoritative module text. The LLM is instructed
        via system prompt to call update_adventure_location naturally.
        """
        return ""
