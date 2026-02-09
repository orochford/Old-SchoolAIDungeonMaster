"""Spell sub-agent that enforces proper spell slot usage.

When the player casts a spell, this agent ensures:
1. The spell is in the character's spell list
2. The character has available slots for that spell level
3. The slot is properly deducted
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session

logger = logging.getLogger(__name__)


@dataclass
class SpellCastAction:
    """Parsed spell casting action."""
    is_spell_cast: bool
    spell_name: str = ""
    spell_level: int = 0
    target: str = ""
    confidence: float = 0.0


@dataclass
class SpellSlotStatus:
    """Current spell slot status for a level."""
    level: int
    total: int
    used: int
    available: int


class SpellAgent:
    """Sub-agent that handles spell casting with enforced slot tracking."""

    # Spell casting keywords
    CAST_VERBS = [
        "cast", "invoke", "channel", "speak", "intone", "recite",
        "pray for", "call upon", "use", "activate",
    ]

    # Common spell names for pattern matching
    # This helps detect spells even without explicit "cast" verb
    COMMON_SPELLS = [
        # Cleric spells
        "cure light wounds", "cure serious wounds", "heal",
        "bless", "protection from evil", "detect evil", "detect magic",
        "light", "darkness", "silence", "hold person", "speak with animals",
        "remove curse", "neutralize poison", "raise dead",
        # Magic-user spells
        "magic missile", "sleep", "charm person", "detect magic",
        "read magic", "shield", "floating disc", "ventriloquism",
        "invisibility", "web", "mirror image", "levitate", "knock",
        "fireball", "lightning bolt", "fly", "haste", "dispel magic",
        "polymorph", "dimension door", "ice storm", "confusion",
    ]

    def __init__(self, tool_handler: ToolHandler, db_session: AsyncSession):
        self.tool_handler = tool_handler
        self.db = db_session

    def parse_spell_cast(self, player_input: str, character: Character) -> SpellCastAction:
        """Parse player input to detect spell casting intent.

        Args:
            player_input: The player's action text
            character: The character (to check known spells)

        Returns:
            SpellCastAction with parsed spell details
        """
        input_lower = player_input.lower().strip()

        # Check for casting verbs
        has_cast_verb = any(
            re.search(rf'\b{verb}\b', input_lower)
            for verb in self.CAST_VERBS
        )

        # Check for known spells by name
        known_spell = None
        spell_level = 0

        # Get character's spell list
        char_spells = self._get_character_spells(character)

        # First check character's known spells
        for spell in char_spells:
            spell_name = spell.get("name", "").lower()
            if spell_name and spell_name in input_lower:
                known_spell = spell.get("name")
                spell_level = spell.get("level", 1)
                break

        # Also check common spell names
        if not known_spell:
            for spell_name in self.COMMON_SPELLS:
                if spell_name in input_lower:
                    known_spell = spell_name.title()
                    # Estimate level based on spell (rough heuristic)
                    spell_level = self._estimate_spell_level(spell_name)
                    break

        # If we found a spell but no cast verb, lower confidence
        if known_spell and not has_cast_verb:
            # Might just be discussing the spell, not casting
            return SpellCastAction(
                is_spell_cast=False,
                spell_name=known_spell,
                spell_level=spell_level,
                confidence=0.3,
            )

        if has_cast_verb and known_spell:
            # Extract target if present
            target = self._extract_target(input_lower, known_spell.lower())

            return SpellCastAction(
                is_spell_cast=True,
                spell_name=known_spell,
                spell_level=spell_level,
                target=target,
                confidence=0.9,
            )

        if has_cast_verb:
            # Has cast verb but couldn't identify spell
            return SpellCastAction(
                is_spell_cast=True,
                spell_name="",
                spell_level=0,
                confidence=0.5,
            )

        return SpellCastAction(is_spell_cast=False, confidence=0.8)

    def _get_character_spells(self, character: Character) -> List[Dict[str, Any]]:
        """Get list of spells from character attributes."""
        attrs = character.attributes or {}
        spells = []

        # Check various possible spell list locations
        if "spells" in attrs:
            spell_data = attrs["spells"]
            if isinstance(spell_data, dict):
                # Format: {prepared: [...], known: [...]}
                spells.extend(spell_data.get("prepared", []))
                spells.extend(spell_data.get("known", []))
            elif isinstance(spell_data, list):
                spells.extend(spell_data)

        if "prepared_spells" in attrs:
            spells.extend(attrs["prepared_spells"])

        if "known_spells" in attrs:
            spells.extend(attrs["known_spells"])

        return spells

    def _estimate_spell_level(self, spell_name: str) -> int:
        """Estimate spell level from name (rough heuristic)."""
        spell_lower = spell_name.lower()

        # Level 1 spells
        if any(s in spell_lower for s in [
            "light", "detect", "cure light", "magic missile", "sleep",
            "charm person", "shield", "read magic", "protection from",
            "bless", "purify",
        ]):
            return 1

        # Level 2 spells
        if any(s in spell_lower for s in [
            "invisibility", "web", "mirror image", "levitate", "knock",
            "hold person", "silence", "find traps", "speak with",
        ]):
            return 2

        # Level 3 spells
        if any(s in spell_lower for s in [
            "fireball", "lightning bolt", "fly", "haste", "dispel",
            "cure serious", "remove curse",
        ]):
            return 3

        # Default to level 1
        return 1

    def _extract_target(self, input_lower: str, spell_name: str) -> str:
        """Extract the target of a spell from input."""
        # Common patterns: "cast X on Y", "cast X at Y"
        patterns = [
            rf'{spell_name}\s+(?:on|at)\s+(?:the\s+)?(\w+(?:\s+\w+)?)',
            rf'(?:on|at)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+with\s+{spell_name}',
        ]

        for pattern in patterns:
            match = re.search(pattern, input_lower)
            if match:
                return match.group(1).strip()

        return ""

    def get_spell_slots(self, character: Character) -> Dict[int, SpellSlotStatus]:
        """Get current spell slot status for character.

        Returns dict of level -> SpellSlotStatus
        """
        attrs = character.attributes or {}
        slots = {}

        # Check for spell slots in various formats
        spell_data = attrs.get("spells", {})

        if isinstance(spell_data, dict):
            slots_per_level = spell_data.get("slotsPerLevel", spell_data.get("slots_per_level", {}))

            for level_str, slot_info in slots_per_level.items():
                level = int(level_str)
                if isinstance(slot_info, dict):
                    total = slot_info.get("total", 0)
                    used = slot_info.get("used", 0)
                else:
                    total = int(slot_info)
                    used = 0

                slots[level] = SpellSlotStatus(
                    level=level,
                    total=total,
                    used=used,
                    available=total - used,
                )

        # Also check flat spell_slots attribute
        if "spell_slots" in attrs:
            slot_data = attrs["spell_slots"]
            for level_str, info in slot_data.items():
                level = int(level_str)
                if isinstance(info, dict):
                    total = info.get("total", 0)
                    used = info.get("used", 0)
                    slots[level] = SpellSlotStatus(
                        level=level, total=total, used=used, available=total - used
                    )

        return slots

    async def handle_spell_cast(
        self,
        player_input: str,
        character: Character,
        session: Session,
    ) -> Optional[Dict[str, Any]]:
        """Handle a potential spell casting action.

        If spell cast is detected and slots are available,
        deducts the slot and returns cast info.

        Args:
            player_input: Player's action text
            character: Player character
            session: Game session

        Returns:
            Dict with spell cast result, or None if not a spell cast
        """
        action = self.parse_spell_cast(player_input, character)

        if not action.is_spell_cast:
            return None

        if action.confidence < 0.5:
            logger.debug(f"[SPELL] Low confidence spell cast: {action.confidence}")
            return None

        if not action.spell_name:
            logger.debug("[SPELL] Spell cast detected but no spell name identified")
            return None

        logger.info(f"[SPELL] Spell cast detected: {action.spell_name} (level {action.spell_level})")

        # Check spell slots
        slots = self.get_spell_slots(character)
        slot_info = slots.get(action.spell_level)

        if not slot_info:
            # No slots for this level - might be wrong level or no slots defined
            logger.warning(f"[SPELL] No slot info for level {action.spell_level}")
            return {
                "spell_name": action.spell_name,
                "spell_level": action.spell_level,
                "target": action.target,
                "success": False,
                "error": f"No level {action.spell_level} spell slots defined",
                "slots_remaining": 0,
            }

        if slot_info.available <= 0:
            # No slots available
            logger.info(f"[SPELL] No slots available for level {action.spell_level}")
            return {
                "spell_name": action.spell_name,
                "spell_level": action.spell_level,
                "target": action.target,
                "success": False,
                "error": f"No level {action.spell_level} spell slots remaining",
                "slots_remaining": 0,
                "slots_total": slot_info.total,
            }

        # Deduct the slot
        new_used = slot_info.used + 1
        await self._update_spell_slots(character, action.spell_level, new_used)

        logger.info(f"[SPELL] Slot deducted: level {action.spell_level} now {slot_info.available - 1}/{slot_info.total}")

        return {
            "spell_name": action.spell_name,
            "spell_level": action.spell_level,
            "target": action.target,
            "success": True,
            "slots_remaining": slot_info.available - 1,
            "slots_total": slot_info.total,
        }

    async def _update_spell_slots(
        self,
        character: Character,
        spell_level: int,
        new_used: int,
    ) -> None:
        """Update character's spell slot usage."""
        attrs = dict(character.attributes or {})
        spell_data = attrs.get("spells", {})

        if isinstance(spell_data, dict):
            slots_key = "slotsPerLevel" if "slotsPerLevel" in spell_data else "slots_per_level"
            if slots_key not in spell_data:
                spell_data[slots_key] = {}

            level_str = str(spell_level)
            if level_str in spell_data[slots_key]:
                if isinstance(spell_data[slots_key][level_str], dict):
                    spell_data[slots_key][level_str]["used"] = new_used
                else:
                    # Convert to dict format
                    total = int(spell_data[slots_key][level_str])
                    spell_data[slots_key][level_str] = {"total": total, "used": new_used}

            attrs["spells"] = spell_data
            character.attributes = attrs
            await self.db.flush()

    def format_spell_context(self, spell_result: Dict[str, Any]) -> str:
        """Format spell cast result for DM context.

        Args:
            spell_result: Result from handle_spell_cast

        Returns:
            Formatted context string for DM
        """
        if not spell_result:
            return ""

        lines = ["## SPELL CAST"]

        spell_name = spell_result.get("spell_name", "Unknown")
        spell_level = spell_result.get("spell_level", 1)
        target = spell_result.get("target", "")
        success = spell_result.get("success", False)

        lines.append(f"Spell: {spell_name} (Level {spell_level})")
        if target:
            lines.append(f"Target: {target}")

        if success:
            remaining = spell_result.get("slots_remaining", 0)
            total = spell_result.get("slots_total", 0)
            lines.append(f"**CAST SUCCESSFUL** - Slot deducted ({remaining}/{total} level {spell_level} slots remaining)")
            lines.append("")
            lines.append("Describe the spell's effect according to its description.")
            lines.append("Do NOT call any spell slot tools - the slot has been deducted.")
        else:
            error = spell_result.get("error", "Unknown error")
            lines.append(f"**CAST FAILED** - {error}")
            lines.append("")
            lines.append("Inform the player they cannot cast this spell.")
            lines.append("The character begins the incantation but realizes they lack the magical energy.")

        return "\n".join(lines)
