"""Rules loader - retrieves appropriate rules for an RPG system."""

from typing import Optional
from .base import RPGRules
from .bx_dnd import BX_DND_RULES
from .ose import OSE_RULES
from .basic_fantasy import BASIC_FANTASY_RULES

# Registry of supported systems
RULES_REGISTRY = {
    "bx-dnd": BX_DND_RULES,
    "bx": BX_DND_RULES,  # Alias
    "b/x": BX_DND_RULES,  # Alias
    "ose": OSE_RULES,
    "old-school-essentials": OSE_RULES,  # Alias
    "basic-fantasy": BASIC_FANTASY_RULES,
    "bfrpg": BASIC_FANTASY_RULES,  # Alias
}

# List of officially supported systems (for UI)
SUPPORTED_SYSTEMS = [
    {
        "id": "bx-dnd",
        "name": "B/X D&D (1981)",
        "description": "Classic Basic/Expert D&D by Moldvay/Cook",
    },
    {
        "id": "ose",
        "name": "Old School Essentials",
        "description": "Modern restatement of B/X rules by Necrotic Gnome",
    },
    {
        "id": "basic-fantasy",
        "name": "Basic Fantasy RPG",
        "description": "Free retro-clone with ascending AC and race/class separation",
    },
]

# Default system if none specified
DEFAULT_SYSTEM = "ose"


def get_rules_for_system(rpg_system_id: Optional[str] = None) -> RPGRules:
    """
    Get the rules configuration for a given RPG system.

    Args:
        rpg_system_id: The system identifier (e.g., "ose", "basic-fantasy")

    Returns:
        RPGRules instance for the system, or default if not found
    """
    if not rpg_system_id:
        rpg_system_id = DEFAULT_SYSTEM

    # Normalize the ID (lowercase, strip whitespace)
    normalized_id = rpg_system_id.lower().strip()

    # Look up in registry
    rules = RULES_REGISTRY.get(normalized_id)

    if rules:
        return rules

    # If not found, return default and log warning
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Unknown RPG system '{rpg_system_id}', using default: {DEFAULT_SYSTEM}")

    return RULES_REGISTRY[DEFAULT_SYSTEM]


def get_combat_system(rpg_system_id: Optional[str] = None) -> str:
    """Get the combat system type for a given RPG system."""
    rules = get_rules_for_system(rpg_system_id)
    return rules.combat_system


def is_ascending_ac(rpg_system_id: Optional[str] = None) -> bool:
    """Check if the system uses ascending AC."""
    return get_combat_system(rpg_system_id) == "ascending_ac"
