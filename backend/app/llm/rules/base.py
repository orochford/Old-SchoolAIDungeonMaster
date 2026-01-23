"""Base classes for RPG rules configuration."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RPGRules:
    """Configuration for an RPG system's rules."""

    # System identification
    system_id: str
    system_name: str
    system_description: str

    # Combat rules
    combat_system: str  # "thac0", "ascending_ac", "target20"
    initiative_type: str  # "group", "individual", "side"

    # Core mechanics text (for system prompt)
    combat_rules: str
    saving_throw_rules: str
    ability_check_rules: str
    morale_rules: str
    reaction_rules: str
    experience_rules: str
    movement_rules: str
    magic_rules: str

    # Saving throw categories
    saving_throws: List[str] = field(default_factory=list)

    # Class-specific data
    classes: List[str] = field(default_factory=list)

    # Optional rules text
    additional_rules: str = ""

    def get_full_rules_text(self) -> str:
        """Get complete rules text for system prompt."""
        sections = [
            f"## {self.system_name} Core Mechanics\n",
            f"{self.system_description}\n",
            "### Combat",
            self.combat_rules,
            "### Saving Throws",
            self.saving_throw_rules,
            "### Ability Checks",
            self.ability_check_rules,
            "### Morale",
            self.morale_rules,
            "### Reaction Rolls",
            self.reaction_rules,
            "### Experience",
            self.experience_rules,
            "### Movement",
            self.movement_rules,
            "### Magic",
            self.magic_rules,
        ]

        if self.additional_rules:
            sections.append("### Additional Rules")
            sections.append(self.additional_rules)

        return "\n\n".join(sections)
