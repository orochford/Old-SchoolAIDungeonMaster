"""Service for managing character spells."""

from typing import Dict, List, Optional, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.spells.models import Spell, get_spell_slots
from app.domains.characters.models import Character


class SpellService:
    """Service for spell management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_spells(self, spell_class: Optional[str] = None) -> List[Spell]:
        """Get all spells, optionally filtered by class."""
        query = select(Spell).order_by(Spell.level, Spell.name)
        if spell_class:
            query = query.where(Spell.spell_class == spell_class)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_spell_by_code(self, code: str) -> Optional[Spell]:
        """Get a spell by its code."""
        result = await self.db.execute(
            select(Spell).where(Spell.code == code)
        )
        return result.scalar_one_or_none()

    async def get_spells_for_class(self, character_class: str, max_level: int = 6) -> List[Spell]:
        """Get all spells available to a character class up to a certain level."""
        spell_class = self._get_spell_class(character_class)
        if not spell_class:
            return []

        result = await self.db.execute(
            select(Spell)
            .where(Spell.spell_class == spell_class)
            .where(Spell.level <= max_level)
            .order_by(Spell.level, Spell.name)
        )
        return list(result.scalars().all())

    def _get_spell_class(self, character_class: str) -> Optional[str]:
        """Map character class to spell class."""
        class_lower = character_class.lower()
        if class_lower == "cleric":
            return "cleric"
        elif class_lower in ("magic-user", "magic user", "mage", "wizard", "elf"):
            return "magic-user"
        return None

    def get_max_spell_level(self, character_class: str, level: int) -> int:
        """Get the maximum spell level a character can cast."""
        slots = get_spell_slots(character_class, level)
        if not slots:
            return 0
        return max(slots.keys()) if slots else 0

    def get_spell_slots_for_character(self, character: Character) -> Dict[int, int]:
        """Get available spell slots based on class and level."""
        char_class = character.attributes.get("character_class", "")
        return get_spell_slots(char_class, character.level)

    def get_spells_memorized(self, character: Character) -> Dict[str, List[str]]:
        """Get currently memorized spells from character attributes."""
        return character.attributes.get("spells_memorized", {})

    def get_slots_used(self, character: Character) -> Dict[str, int]:
        """Get spell slots used today."""
        return character.attributes.get("spell_slots_used", {})

    def get_spellbook(self, character: Character) -> List[str]:
        """Get spells in character's spellbook (for magic-users)."""
        return character.attributes.get("spellbook", [])

    async def can_memorize_spell(
        self, character: Character, spell_code: str
    ) -> tuple[bool, str]:
        """Check if a character can memorize a spell."""
        spell = await self.get_spell_by_code(spell_code)
        if not spell:
            return False, "Spell not found"

        char_class = character.attributes.get("character_class", "").lower()
        spell_class = self._get_spell_class(char_class)

        # Check class compatibility
        if spell.spell_class != spell_class:
            return False, f"This spell is not available to {char_class}s"

        # Check level
        max_level = self.get_max_spell_level(char_class, character.level)
        if spell.level > max_level:
            return False, f"Character cannot cast level {spell.level} spells yet"

        # For magic-users, check if spell is in spellbook
        if spell_class == "magic-user":
            spellbook = self.get_spellbook(character)
            if spell_code not in spellbook:
                return False, "Spell is not in your spellbook"

        # Check available slots for that level
        slots = get_spell_slots(char_class, character.level)
        max_slots = slots.get(spell.level, 0)
        memorized = self.get_spells_memorized(character)
        current_memorized = len(memorized.get(str(spell.level), []))

        if current_memorized >= max_slots:
            return False, f"No more level {spell.level} spell slots available"

        return True, "OK"

    async def memorize_spell(
        self, character: Character, spell_code: str
    ) -> tuple[bool, str]:
        """Memorize a spell for the character."""
        can_memorize, message = await self.can_memorize_spell(character, spell_code)
        if not can_memorize:
            return False, message

        spell = await self.get_spell_by_code(spell_code)

        # Update character attributes
        attrs = dict(character.attributes)
        memorized = dict(attrs.get("spells_memorized", {}))
        level_key = str(spell.level)

        if level_key not in memorized:
            memorized[level_key] = []
        memorized[level_key] = list(memorized[level_key]) + [spell_code]

        attrs["spells_memorized"] = memorized
        character.attributes = attrs

        return True, f"Memorized {spell.name}"

    async def forget_spell(
        self, character: Character, spell_code: str
    ) -> tuple[bool, str]:
        """Remove a spell from memorized spells."""
        attrs = dict(character.attributes)
        memorized = dict(attrs.get("spells_memorized", {}))

        # Find the spell level
        spell = await self.get_spell_by_code(spell_code)
        if not spell:
            return False, "Spell not found"

        level_key = str(spell.level)
        if level_key not in memorized or spell_code not in memorized[level_key]:
            return False, "Spell is not memorized"

        # Remove one instance of the spell
        spells_list = list(memorized[level_key])
        spells_list.remove(spell_code)
        memorized[level_key] = spells_list

        attrs["spells_memorized"] = memorized
        character.attributes = attrs

        return True, f"Forgot {spell.name}"

    async def cast_spell(
        self, character: Character, spell_code: str
    ) -> tuple[bool, str, Optional[Spell]]:
        """Cast a memorized spell, consuming a slot."""
        spell = await self.get_spell_by_code(spell_code)
        if not spell:
            return False, "Spell not found", None

        memorized = self.get_spells_memorized(character)
        level_key = str(spell.level)

        if level_key not in memorized or spell_code not in memorized[level_key]:
            return False, f"{spell.name} is not memorized", None

        # Remove from memorized
        attrs = dict(character.attributes)
        memorized = dict(attrs.get("spells_memorized", {}))
        spells_list = list(memorized[level_key])
        spells_list.remove(spell_code)
        memorized[level_key] = spells_list

        # Track slots used (for display purposes)
        slots_used = dict(attrs.get("spell_slots_used", {}))
        slots_used[level_key] = slots_used.get(level_key, 0) + 1

        attrs["spells_memorized"] = memorized
        attrs["spell_slots_used"] = slots_used
        character.attributes = attrs

        return True, f"Cast {spell.name}!", spell

    async def rest_and_rememorize(
        self, character: Character, spells_to_memorize: List[str]
    ) -> tuple[bool, str]:
        """Rest and memorize new spells (typically after 8 hours rest)."""
        char_class = character.attributes.get("character_class", "").lower()
        spell_class = self._get_spell_class(char_class)

        if not spell_class:
            return False, "Character cannot cast spells"

        slots = get_spell_slots(char_class, character.level)

        # Validate requested spells fit in slots
        spells_by_level: Dict[int, List[str]] = {}
        for spell_code in spells_to_memorize:
            spell = await self.get_spell_by_code(spell_code)
            if not spell:
                return False, f"Unknown spell: {spell_code}"
            if spell.spell_class != spell_class:
                return False, f"{spell.name} is not available to {char_class}s"
            if spell.level not in spells_by_level:
                spells_by_level[spell.level] = []
            spells_by_level[spell.level].append(spell_code)

        # Check slots
        for level, spells in spells_by_level.items():
            max_slots = slots.get(level, 0)
            if len(spells) > max_slots:
                return False, f"Too many level {level} spells ({len(spells)} > {max_slots})"

        # For magic-users, verify spells are in spellbook
        if spell_class == "magic-user":
            spellbook = self.get_spellbook(character)
            for spell_code in spells_to_memorize:
                if spell_code not in spellbook:
                    spell = await self.get_spell_by_code(spell_code)
                    return False, f"{spell.name if spell else spell_code} is not in your spellbook"

        # Apply the new memorized spells
        attrs = dict(character.attributes)
        new_memorized = {}
        for level, spells in spells_by_level.items():
            new_memorized[str(level)] = spells

        attrs["spells_memorized"] = new_memorized
        attrs["spell_slots_used"] = {}  # Reset slots used
        character.attributes = attrs

        return True, "Spells memorized after rest"

    async def add_spell_to_spellbook(
        self, character: Character, spell_code: str
    ) -> tuple[bool, str]:
        """Add a spell to a magic-user's spellbook."""
        char_class = character.attributes.get("character_class", "").lower()
        if char_class not in ("magic-user", "magic user", "mage", "wizard", "elf"):
            return False, "Only magic-users have spellbooks"

        spell = await self.get_spell_by_code(spell_code)
        if not spell:
            return False, "Spell not found"

        if spell.spell_class != "magic-user":
            return False, "Only magic-user spells can be added to a spellbook"

        attrs = dict(character.attributes)
        spellbook = list(attrs.get("spellbook", []))

        if spell_code in spellbook:
            return False, f"{spell.name} is already in your spellbook"

        spellbook.append(spell_code)
        attrs["spellbook"] = spellbook
        character.attributes = attrs

        return True, f"Added {spell.name} to spellbook"

    def get_spell_status(self, character: Character) -> Dict[str, Any]:
        """Get complete spell status for a character."""
        char_class = character.attributes.get("character_class", "")
        spell_class = self._get_spell_class(char_class)

        if not spell_class:
            return {"can_cast": False, "reason": "Class cannot cast spells"}

        slots = get_spell_slots(char_class, character.level)
        memorized = self.get_spells_memorized(character)

        # Calculate slots remaining
        slots_remaining = {}
        for level, max_slots in slots.items():
            used = len(memorized.get(str(level), []))
            slots_remaining[level] = max_slots - used

        return {
            "can_cast": True,
            "spell_class": spell_class,
            "max_spell_level": self.get_max_spell_level(char_class, character.level),
            "spell_slots": slots,
            "spells_memorized": memorized,
            "slots_remaining": slots_remaining,
            "spellbook": self.get_spellbook(character) if spell_class == "magic-user" else None,
        }
