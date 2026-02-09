"""Location sub-agent that enforces proper location tracking.

When the player moves to a new location, this agent ensures
update_adventure_location is called with the correct location_key,
rather than relying on the LLM to remember.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.domains.adventures.models import AdventureModule, AdventureLocation

logger = logging.getLogger(__name__)


@dataclass
class MovementIntent:
    """Parsed player movement intent."""
    is_movement: bool
    direction: Optional[str] = None  # "north", "south", "back", etc.
    target_name: Optional[str] = None  # "kitchen", "storeroom", etc.
    target_key: Optional[str] = None  # "2", "10", etc.
    confidence: float = 0.0  # 0-1 confidence in the detection


class LocationAgent:
    """Sub-agent that handles location transitions with enforced tool usage."""

    # Movement keywords that indicate the player wants to move
    MOVEMENT_VERBS = [
        "go", "walk", "head", "move", "travel", "proceed", "continue",
        "enter", "exit", "leave", "return", "step", "climb", "descend",
        "explore", "venture", "push", "advance", "retreat", "flee",
    ]

    # Directional keywords
    DIRECTIONS = [
        "north", "south", "east", "west",
        "up", "down", "upstairs", "downstairs",
        "left", "right", "forward", "backward", "back",
        "ahead", "straight", "inside", "outside",
    ]

    # Keywords that suggest staying in place (not movement)
    STAY_KEYWORDS = [
        "search", "examine", "look", "inspect", "check",
        "attack", "fight", "hit", "strike",
        "talk", "speak", "ask", "say",
        "rest", "wait", "hide",
        "pick up", "take", "grab", "open", "close",
    ]

    def __init__(self, tool_handler: ToolHandler, db_session: AsyncSession):
        self.tool_handler = tool_handler
        self.db = db_session
        self._location_cache: Dict[str, List[Dict[str, Any]]] = {}

    def parse_movement_intent(
        self,
        player_input: str,
        current_location: Optional[str] = None,
        available_exits: Optional[List[str]] = None,
    ) -> MovementIntent:
        """Parse player input to detect movement intent.

        Args:
            player_input: The player's action text
            current_location: Current location name for context
            available_exits: List of known exits from current location

        Returns:
            MovementIntent with parsed movement details
        """
        input_lower = player_input.lower().strip()

        # First check for stay-in-place actions
        for stay_kw in self.STAY_KEYWORDS:
            if stay_kw in input_lower:
                # These actions typically don't involve movement
                # But check if they also have movement ("search then go north")
                if not any(mv in input_lower for mv in self.MOVEMENT_VERBS):
                    return MovementIntent(is_movement=False, confidence=0.8)

        # Check for movement verbs
        has_movement_verb = any(
            re.search(rf'\b{verb}\b', input_lower)
            for verb in self.MOVEMENT_VERBS
        )

        if not has_movement_verb:
            return MovementIntent(is_movement=False, confidence=0.7)

        # Extract direction if present
        direction = None
        for dir_word in self.DIRECTIONS:
            if re.search(rf'\b{dir_word}\b', input_lower):
                direction = dir_word
                break

        # Try to extract target location name
        target_name = None
        target_key = None

        # Pattern: "go to the X", "enter the X", "head to X"
        location_patterns = [
            r'(?:go|head|walk|move|travel|proceed)\s+(?:to\s+)?(?:the\s+)?(.+?)(?:\.|$|,|\s+and\s+)',
            r'(?:enter|exit)\s+(?:the\s+)?(.+?)(?:\.|$|,|\s+and\s+)',
            r'(?:into|to)\s+(?:the\s+)?(.+?)(?:\.|$|,|\s+and\s+)',
        ]

        for pattern in location_patterns:
            match = re.search(pattern, input_lower)
            if match:
                potential_target = match.group(1).strip()
                # Clean up common suffixes
                potential_target = re.sub(r'\s*(room|area|chamber|hall)$', '', potential_target)
                if potential_target and len(potential_target) > 1:
                    target_name = potential_target
                    break

        # Check for location key references like "room 2", "area 10", "location 3"
        key_match = re.search(r'(?:room|area|location|#)\s*(\d+[a-z]?)', input_lower)
        if key_match:
            target_key = key_match.group(1)

        # Determine confidence
        confidence = 0.5
        if has_movement_verb:
            confidence += 0.2
        if direction:
            confidence += 0.1
        if target_name or target_key:
            confidence += 0.2

        return MovementIntent(
            is_movement=True,
            direction=direction,
            target_name=target_name,
            target_key=target_key,
            confidence=min(confidence, 1.0),
        )

    async def get_module_locations(
        self,
        adventure_document_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all locations for an adventure module.

        Returns cached results if available.
        """
        cache_key = str(adventure_document_id)
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        try:
            # Get the module
            module_result = await self.db.execute(
                select(AdventureModule).where(
                    AdventureModule.pdf_document_id == adventure_document_id
                )
            )
            module = module_result.scalar_one_or_none()

            if not module:
                return []

            # Get all locations
            loc_result = await self.db.execute(
                select(AdventureLocation).where(
                    AdventureLocation.module_id == module.id
                ).order_by(AdventureLocation.location_key)
            )
            locations = list(loc_result.scalars().all())

            # Convert to dicts
            location_list = []
            for loc in locations:
                location_list.append({
                    "key": loc.location_key,
                    "name": loc.name,
                    "exits": loc.exits or [],
                    "keywords": self._extract_keywords(loc.name, loc.dm_description),
                })

            self._location_cache[cache_key] = location_list
            return location_list

        except Exception as e:
            logger.warning(f"[LOCATION] Failed to load module locations: {e}")
            return []

    def _extract_keywords(self, name: str, description: Optional[str]) -> List[str]:
        """Extract searchable keywords from location name and description."""
        keywords = []

        if name:
            # Add name words
            keywords.extend(name.lower().split())

        if description:
            # Add key nouns from description
            desc_lower = description.lower()
            key_words = [
                "door", "doors", "corridor", "passage", "stairs", "staircase",
                "room", "chamber", "hall", "cave", "cavern", "tunnel",
                "entrance", "exit", "archway", "gate", "portal",
                "kitchen", "storeroom", "armory", "barracks", "throne",
                "library", "laboratory", "prison", "cell", "dungeon",
                "pool", "fountain", "altar", "shrine", "temple",
            ]
            for word in key_words:
                if word in desc_lower:
                    keywords.append(word)

        return list(set(keywords))

    def find_matching_location(
        self,
        intent: MovementIntent,
        locations: List[Dict[str, Any]],
        current_location_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching location for the movement intent.

        Args:
            intent: Parsed movement intent
            locations: List of available locations
            current_location_key: Current location key for connection checking

        Returns:
            Best matching location dict, or None if no match
        """
        if not locations:
            return None

        # If we have an explicit key, use it
        if intent.target_key:
            for loc in locations:
                if loc["key"].lower() == intent.target_key.lower():
                    return loc

        # If we have a target name, try to match
        if intent.target_name:
            target_lower = intent.target_name.lower()
            best_match = None
            best_score = 0

            for loc in locations:
                score = 0
                loc_name_lower = loc["name"].lower()

                # Exact name match
                if target_lower == loc_name_lower:
                    return loc  # Perfect match

                # Partial name match
                if target_lower in loc_name_lower:
                    score += 5
                elif loc_name_lower in target_lower:
                    score += 3

                # Keyword match
                for keyword in loc.get("keywords", []):
                    if keyword in target_lower:
                        score += 2

                # Word overlap
                target_words = set(target_lower.split())
                loc_words = set(loc_name_lower.split())
                overlap = len(target_words & loc_words)
                score += overlap * 2

                if score > best_score:
                    best_score = score
                    best_match = loc

            if best_match and best_score >= 2:
                return best_match

        # If we have a direction and current location, check exits
        if intent.direction and current_location_key:
            current_loc = next(
                (l for l in locations if l["key"] == current_location_key),
                None
            )
            if current_loc and current_loc.get("exits"):
                direction_lower = intent.direction.lower()
                for conn in current_loc["exits"]:
                    # Connection format might be {"direction": "north", "to": "2"}
                    # or just a string like "north to room 2"
                    if isinstance(conn, dict):
                        if conn.get("direction", "").lower() == direction_lower:
                            target_key = conn.get("to") or conn.get("target")
                            if target_key:
                                for loc in locations:
                                    if loc["key"] == target_key:
                                        return loc
                    elif isinstance(conn, str):
                        if direction_lower in conn.lower():
                            # Try to extract target key from string
                            key_match = re.search(r'(\d+[a-z]?)', conn)
                            if key_match:
                                target_key = key_match.group(1)
                                for loc in locations:
                                    if loc["key"] == target_key:
                                        return loc

        return None

    async def handle_movement(
        self,
        player_input: str,
        character: Character,
        session: Session,
        adventure_document_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle a potential movement action.

        If movement is detected and a target location can be determined,
        forces the update_adventure_location tool call.

        Args:
            player_input: Player's action text
            character: Player character
            session: Game session
            adventure_document_id: Adventure module document ID

        Returns:
            Tool result dict if location was updated, None otherwise
        """
        if not adventure_document_id:
            return None

        adventure_state = session.adventure_state or {}
        current_location = adventure_state.get("current_location")
        current_location_key = adventure_state.get("current_location_key")

        # Parse movement intent
        intent = self.parse_movement_intent(
            player_input,
            current_location=current_location,
        )

        if not intent.is_movement:
            logger.debug(f"[LOCATION] No movement detected in: {player_input[:50]}...")
            return None

        if intent.confidence < 0.5:
            logger.debug(f"[LOCATION] Low confidence movement: {intent.confidence}")
            return None

        logger.info(f"[LOCATION] Movement detected: direction={intent.direction}, "
                   f"target={intent.target_name or intent.target_key}, confidence={intent.confidence}")

        # Get module locations
        locations = await self.get_module_locations(adventure_document_id)
        if not locations:
            logger.warning("[LOCATION] No locations found in module")
            return None

        # Find matching location
        target_location = self.find_matching_location(
            intent, locations, current_location_key
        )

        if not target_location:
            logger.info(f"[LOCATION] Could not determine target location for: {intent.target_name}")
            return None

        # Don't update if already at this location
        if target_location["key"] == current_location_key:
            logger.debug(f"[LOCATION] Already at location {current_location_key}")
            return None

        logger.info(f"[LOCATION] Auto-updating location: {current_location_key} -> {target_location['key']} ({target_location['name']})")

        # Force the location update
        result = await self.tool_handler.execute(
            tool_name="update_adventure_location",
            tool_input={
                "location": target_location["name"],
                "location_key": target_location["key"],
            },
            character=character,
            session=session,
        )

        return result

    def format_location_context(
        self,
        location: Dict[str, Any],
        previous_location: Optional[str] = None,
    ) -> str:
        """Format location transition for DM context.

        Args:
            location: Target location dict
            previous_location: Name of previous location

        Returns:
            Formatted context string for DM
        """
        lines = ["## LOCATION TRANSITION"]

        if previous_location:
            lines.append(f"Player moved from: {previous_location}")

        lines.append(f"Player is now at: {location['name']} (key: {location['key']})")
        lines.append("")
        lines.append("Describe this new location using the module context provided.")
        lines.append("Do NOT call update_adventure_location - it has already been called.")

        return "\n".join(lines)
