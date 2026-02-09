"""Post-LLM damage detection and auto-application middleware.

This handler parses LLM output for damage mentions and ensures damage is
properly applied even if the LLM forgot to call apply_damage_or_healing.

This ensures:
- HP is always tracked correctly
- Damage mentioned in narrative is actually applied
- Combat state remains consistent
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.characters.models import Character
from app.domains.sessions.models import Session

logger = logging.getLogger(__name__)


# Patterns to detect damage being dealt to the player
PLAYER_DAMAGE_PATTERNS = [
    # "deals 5 damage to you"
    r"deals?\s+(\d+)\s+(?:points?\s+of\s+)?damage\s+to\s+(?:you|the\s+player|{player_name})",
    # "you take 5 damage"
    r"you\s+take\s+(\d+)\s+(?:points?\s+of\s+)?damage",
    # "hits you for 5 damage"
    r"hits?\s+(?:you|the\s+player|{player_name})\s+for\s+(\d+)\s+(?:points?\s+of\s+)?damage",
    # "strikes you for 5 damage"
    r"strikes?\s+(?:you|the\s+player|{player_name})\s+for\s+(\d+)\s+(?:points?\s+of\s+)?damage",
    # "inflicts 5 damage"
    r"inflicts?\s+(\d+)\s+(?:points?\s+of\s+)?damage\s+(?:on|to)\s+(?:you|the\s+player|{player_name})",
    # "causes 5 damage"
    r"causes?\s+(\d+)\s+(?:points?\s+of\s+)?damage\s+(?:on|to)\s+(?:you|the\s+player|{player_name})",
    # "5 damage to you"
    r"(\d+)\s+(?:points?\s+of\s+)?damage\s+to\s+(?:you|the\s+player|{player_name})",
    # "you suffer 5 damage"
    r"you\s+suffer\s+(\d+)\s+(?:points?\s+of\s+)?damage",
    # "you lose 5 hit points"
    r"you\s+lose\s+(\d+)\s+hit\s+points?",
    # "you are hit for 5"
    r"you\s+are\s+hit\s+for\s+(\d+)",
]

# Patterns to detect healing
HEALING_PATTERNS = [
    # "you heal 5 hit points"
    r"you\s+heal\s+(\d+)\s+(?:hit\s+)?points?",
    # "you regain 5 hit points"
    r"you\s+regain\s+(\d+)\s+(?:hit\s+)?points?",
    # "restores 5 hit points"
    r"restores?\s+(\d+)\s+(?:hit\s+)?points?\s+(?:to\s+)?(?:you)?",
    # "heals you for 5"
    r"heals?\s+(?:you|the\s+player|{player_name})\s+(?:for\s+)?(\d+)",
    # "you recover 5 hit points"
    r"you\s+recover\s+(\d+)\s+(?:hit\s+)?points?",
]

# Patterns to detect damage dealt by the player to monsters
# Note: These patterns must NOT match "you" or "player" as targets
MONSTER_DAMAGE_PATTERNS = [
    # "you deal 5 damage to the goblin" - exclude "you" as target
    r"you\s+deal\s+(\d+)\s+(?:points?\s+of\s+)?damage\s+to\s+(?:the\s+)?(?!you\b)(\w+)",
    # "strikes the goblin for 5 damage" - target before damage
    r"strikes?\s+(?:the\s+)?(?!you\b)(\w+)\s+for\s+(\d+)\s+(?:points?\s+of\s+)?damage",
    # "hits the goblin for 5 damage" - target before damage
    r"hits?\s+(?:the\s+)?(?!you\b)(\w+)\s+for\s+(\d+)\s+(?:points?\s+of\s+)?damage",
]


@dataclass
class DamageEvent:
    """A detected damage or healing event."""

    amount: int
    """Damage amount (positive for damage, negative for healing)"""

    target: str
    """Who receives the damage ('player' or monster name)"""

    source: str
    """Source of the damage (extracted from context)"""

    damage_type: str = "untyped"
    """Type of damage if specified"""

    applied: bool = False
    """Whether this damage was already applied via tool call"""


@dataclass
class DamageExtractionResult:
    """Result of damage extraction from LLM response."""

    events: List[DamageEvent] = field(default_factory=list)
    """All detected damage/healing events"""

    player_damage_total: int = 0
    """Total damage to apply to player"""

    player_healing_total: int = 0
    """Total healing to apply to player"""

    monster_damage: Dict[str, int] = field(default_factory=dict)
    """Damage to apply to monsters: {name: amount}"""

    needs_application: bool = False
    """Whether any damage needs to be auto-applied"""

    tool_calls_made: Set[str] = field(default_factory=set)
    """Tool calls that were made (to avoid double-applying)"""


class DamageExtractor:
    """Extracts damage events from LLM responses.

    This handler:
    1. Parses LLM narrative for damage mentions
    2. Checks if apply_damage_or_healing was called
    3. Auto-applies damage that was mentioned but not tool-called
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def extract(
        self,
        llm_response: str,
        tool_calls: List[Dict[str, Any]],
        player_name: str = "you",
    ) -> DamageExtractionResult:
        """Extract damage events from LLM response.

        Args:
            llm_response: The LLM's narrative response
            tool_calls: List of tool calls made during the response
            player_name: Player character name for pattern matching

        Returns:
            DamageExtractionResult with detected events and totals
        """
        result = DamageExtractionResult()
        response_lower = llm_response.lower()

        # Track which damage was already applied via tool calls
        applied_amounts = self._get_applied_damage(tool_calls)
        result.tool_calls_made = {tc.get("name", "") for tc in tool_calls}

        # Check if apply_damage_or_healing was called at all
        damage_tool_called = "apply_damage_or_healing" in result.tool_calls_made

        # Extract player damage
        player_damage = self._extract_player_damage(response_lower, player_name)
        for event in player_damage:
            # Check if this amount was already applied
            if event.amount in applied_amounts.get("player", []):
                event.applied = True
                applied_amounts["player"].remove(event.amount)
            result.events.append(event)

            if not event.applied:
                result.player_damage_total += event.amount
                result.needs_application = True

        # Extract player healing
        player_healing = self._extract_healing(response_lower, player_name)
        for event in player_healing:
            # Healing amounts are stored as negative in applied_amounts
            if -event.amount in applied_amounts.get("player", []):
                event.applied = True
                applied_amounts["player"].remove(-event.amount)
            result.events.append(event)

            if not event.applied:
                result.player_healing_total += event.amount
                result.needs_application = True

        # Extract monster damage
        monster_damage = self._extract_monster_damage(response_lower)
        for event in monster_damage:
            if event.amount in applied_amounts.get(event.target.lower(), []):
                event.applied = True
                applied_amounts.get(event.target.lower(), []).remove(event.amount)
            result.events.append(event)

            if not event.applied:
                result.monster_damage[event.target] = (
                    result.monster_damage.get(event.target, 0) + event.amount
                )
                result.needs_application = True

        logger.info(
            f"[Damage] Extracted: player_damage={result.player_damage_total}, "
            f"player_healing={result.player_healing_total}, "
            f"monster_damage={result.monster_damage}, "
            f"needs_application={result.needs_application}"
        )

        return result

    def _get_applied_damage(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> Dict[str, List[int]]:
        """Get damage amounts that were already applied via tool calls."""
        applied = {"player": []}

        for tc in tool_calls:
            if tc.get("name") == "apply_damage_or_healing":
                input_data = tc.get("input", {})
                target = input_data.get("target", "player").lower()
                amount = input_data.get("amount", 0)

                if target not in applied:
                    applied[target] = []
                applied[target].append(amount)

        return applied

    def _extract_player_damage(
        self,
        response_lower: str,
        player_name: str,
    ) -> List[DamageEvent]:
        """Extract damage events targeting the player."""
        events = []
        seen_positions = set()  # Track match positions to avoid duplicates

        for pattern in PLAYER_DAMAGE_PATTERNS:
            # Replace player name placeholder
            pattern_with_name = pattern.replace("{player_name}", re.escape(player_name.lower()))

            matches = re.finditer(pattern_with_name, response_lower, re.IGNORECASE)
            for match in matches:
                # Skip if we've already matched at this position
                if match.start() in seen_positions:
                    continue

                try:
                    amount = int(match.group(1))
                    if amount > 0:
                        events.append(DamageEvent(
                            amount=amount,
                            target="player",
                            source="combat",
                        ))
                        # Mark a range around this match as seen
                        for pos in range(match.start(), match.end()):
                            seen_positions.add(pos)
                except (ValueError, IndexError):
                    pass

        return events

    def _extract_healing(
        self,
        response_lower: str,
        player_name: str,
    ) -> List[DamageEvent]:
        """Extract healing events targeting the player."""
        events = []

        for pattern in HEALING_PATTERNS:
            pattern_with_name = pattern.replace("{player_name}", re.escape(player_name.lower()))

            matches = re.finditer(pattern_with_name, response_lower, re.IGNORECASE)
            for match in matches:
                try:
                    amount = int(match.group(1))
                    if amount > 0:
                        events.append(DamageEvent(
                            amount=-amount,  # Negative for healing
                            target="player",
                            source="healing",
                        ))
                except (ValueError, IndexError):
                    pass

        return events

    def _extract_monster_damage(self, response_lower: str) -> List[DamageEvent]:
        """Extract damage events targeting monsters."""
        events = []

        for pattern in MONSTER_DAMAGE_PATTERNS:
            matches = re.finditer(pattern, response_lower, re.IGNORECASE)
            for match in matches:
                try:
                    groups = match.groups()
                    # Pattern might have (damage, target) or (target, damage) order
                    if len(groups) >= 2:
                        # Determine which group is the number
                        if groups[0].isdigit():
                            amount = int(groups[0])
                            target = groups[1]
                        else:
                            amount = int(groups[1])
                            target = groups[0]

                        if amount > 0 and target:
                            events.append(DamageEvent(
                                amount=amount,
                                target=target.strip(),
                                source="player_attack",
                            ))
                except (ValueError, IndexError):
                    pass

        return events

    async def auto_apply(
        self,
        result: DamageExtractionResult,
        character: Character,
        session: Session,
    ) -> List[Dict[str, Any]]:
        """Auto-apply unapplied damage events.

        Args:
            result: The extraction result
            character: The player character
            session: The game session

        Returns:
            List of applied damage events for logging
        """
        applied_events = []

        # Apply player damage
        if result.player_damage_total > 0:
            old_hp = character.current_hp
            character.current_hp = max(0, character.current_hp - result.player_damage_total)
            await self.db.flush()

            applied_events.append({
                "type": "player_damage",
                "amount": result.player_damage_total,
                "old_hp": old_hp,
                "new_hp": character.current_hp,
                "auto_applied": True,
            })
            logger.info(
                f"[Damage] Auto-applied {result.player_damage_total} damage to player: "
                f"{old_hp} -> {character.current_hp}"
            )

        # Apply player healing
        if result.player_healing_total > 0:
            old_hp = character.current_hp
            character.current_hp = min(character.max_hp, character.current_hp + result.player_healing_total)
            await self.db.flush()

            applied_events.append({
                "type": "player_healing",
                "amount": result.player_healing_total,
                "old_hp": old_hp,
                "new_hp": character.current_hp,
                "auto_applied": True,
            })
            logger.info(
                f"[Damage] Auto-applied {result.player_healing_total} healing to player: "
                f"{old_hp} -> {character.current_hp}"
            )

        # Apply monster damage (track in game state)
        if result.monster_damage:
            game_state = session.game_state or {}
            npcs = game_state.get("npcs", {})

            for target, amount in result.monster_damage.items():
                target_key = target.lower()
                npc = npcs.get(target_key, {"hp": 10, "max_hp": 10})
                old_hp = npc.get("hp", 10)
                npc["hp"] = max(0, old_hp - amount)
                npcs[target_key] = npc

                applied_events.append({
                    "type": "monster_damage",
                    "target": target,
                    "amount": amount,
                    "old_hp": old_hp,
                    "new_hp": npc["hp"],
                    "auto_applied": True,
                })
                logger.info(
                    f"[Damage] Auto-applied {amount} damage to {target}: "
                    f"{old_hp} -> {npc['hp']}"
                )

            game_state["npcs"] = npcs
            session.game_state = game_state
            await self.db.flush()

        return applied_events
