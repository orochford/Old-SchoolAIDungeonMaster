"""Spell models for tracking magic in the game."""

from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base
from app.shared.base_model import BaseModel


class Spell(Base, BaseModel):
    """Master spell data from sourcebooks."""

    __tablename__ = "spells"

    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, unique=True)  # e.g., "magic_missile"
    level = Column(Integer, nullable=False)
    spell_class = Column(String(20), nullable=False)  # "cleric" or "magic-user"

    duration = Column(String(100))  # e.g., "1 turn", "6 turns +1/level"
    range = Column(String(100))  # e.g., "150'", "Touch", "Caster"
    description = Column(Text, nullable=False)

    reversible = Column(Boolean, default=False)
    reversed_name = Column(String(100), nullable=True)  # e.g., "Cause Light Wounds"

    # Additional metadata
    save = Column(String(100), nullable=True)  # e.g., "Negates", "Half damage"
    area_of_effect = Column(String(100), nullable=True)  # e.g., "20' radius"

    # Source reference
    source_book = Column(String(100), default="OSE Basic")


# Spell slot progression tables
CLERIC_SPELL_SLOTS = {
    # level: {spell_level: slots}
    1: {},
    2: {1: 1},
    3: {1: 2},
    4: {1: 2, 2: 1},
    5: {1: 2, 2: 2},
    6: {1: 2, 2: 2, 3: 1},
    7: {1: 3, 2: 2, 3: 2},
    8: {1: 3, 2: 3, 3: 2, 4: 1},
    9: {1: 3, 2: 3, 3: 3, 4: 2},
    10: {1: 4, 2: 3, 3: 3, 4: 2, 5: 1},
    11: {1: 4, 2: 4, 3: 3, 4: 3, 5: 2},
    12: {1: 5, 2: 4, 3: 4, 4: 3, 5: 2},
    13: {1: 5, 2: 5, 3: 4, 4: 4, 5: 3},
    14: {1: 6, 2: 5, 3: 5, 4: 4, 5: 4},
}

MAGIC_USER_SPELL_SLOTS = {
    # level: {spell_level: slots}
    1: {1: 1},
    2: {1: 2},
    3: {1: 2, 2: 1},
    4: {1: 2, 2: 2},
    5: {1: 2, 2: 2, 3: 1},
    6: {1: 2, 2: 2, 3: 2},
    7: {1: 3, 2: 2, 3: 2, 4: 1},
    8: {1: 3, 2: 3, 3: 2, 4: 2},
    9: {1: 3, 2: 3, 3: 3, 4: 2, 5: 1},
    10: {1: 3, 2: 3, 3: 3, 4: 3, 5: 2},
    11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    12: {1: 4, 2: 4, 3: 3, 4: 3, 5: 3, 6: 2},
    13: {1: 4, 2: 4, 3: 4, 4: 3, 5: 3, 6: 3},
    14: {1: 4, 2: 4, 3: 4, 4: 4, 5: 3, 6: 3},
}

# Elf uses same as Magic-User
ELF_SPELL_SLOTS = MAGIC_USER_SPELL_SLOTS


def get_spell_slots(character_class: str, level: int) -> dict:
    """Get spell slots available for a class at a given level."""
    class_lower = character_class.lower()

    if class_lower == "cleric":
        return CLERIC_SPELL_SLOTS.get(level, {})
    elif class_lower in ("magic-user", "magic user", "mage", "wizard"):
        return MAGIC_USER_SPELL_SLOTS.get(level, {})
    elif class_lower == "elf":
        return ELF_SPELL_SLOTS.get(level, {})
    else:
        # Fighter, Thief, Dwarf, Halfling - no spells
        return {}
