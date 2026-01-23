"""Extraction context for multi-pass adventure parsing.

This module defines the ExtractionContext dataclass that accumulates
information across parsing passes, allowing later passes to reference
context built up by earlier passes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from uuid import UUID


@dataclass
class LocationBrief:
    """Brief location info from Pass 1."""
    key: str
    name: str
    brief_desc: str
    dungeon_level: int = 1


@dataclass
class ModuleOverview:
    """Module overview extracted in Pass 1."""
    title: str = ""
    code: Optional[str] = None
    level_min: Optional[int] = None
    level_max: Optional[int] = None
    summary: str = ""
    main_objectives: List[str] = field(default_factory=list)
    adventure_flow: str = ""


@dataclass
class LocationDetails:
    """Full location details from Pass 2."""
    location_key: str
    name: str
    dm_description: str
    read_aloud_text: Optional[str] = None
    features: List[Dict[str, Any]] = field(default_factory=list)
    exits: Dict[str, str] = field(default_factory=dict)
    visible_items: List[str] = field(default_factory=list)
    hidden_elements: List[Dict[str, Any]] = field(default_factory=list)
    treasure: List[Dict[str, Any]] = field(default_factory=list)
    traps: List[Dict[str, Any]] = field(default_factory=list)
    secrets: List[Dict[str, Any]] = field(default_factory=list)
    dungeon_level: int = 1
    tier: Optional[str] = None
    source_page: Optional[int] = None


@dataclass
class Creature:
    """Creature stat block."""
    name: str
    count: str = "1"
    hd: Optional[str] = None
    hp: Optional[str] = None
    ac: Optional[int] = None
    thac0: Optional[int] = None
    attacks: List[str] = field(default_factory=list)
    damage: List[str] = field(default_factory=list)
    save: Optional[str] = None
    morale: Optional[int] = None
    mv: Optional[str] = None
    alignment: Optional[str] = None
    special: List[str] = field(default_factory=list)
    xp: Optional[int] = None


@dataclass
class Encounter:
    """Encounter from Pass 3."""
    location_key: Optional[str]
    name: str
    description: Optional[str] = None
    creatures: List[Creature] = field(default_factory=list)
    behavior: Optional[str] = None
    tactics: Optional[str] = None
    treasure: List[Dict[str, Any]] = field(default_factory=list)
    trigger_condition: Optional[str] = None
    xp_value: Optional[int] = None
    encounter_type: str = "fixed"  # fixed or wandering


@dataclass
class WanderingTable:
    """Wandering monster table from preprocessing or Pass 3."""
    table_name: str
    die_roll: str = "1d6"
    check_frequency: Optional[str] = None
    dungeon_level: int = 1
    entries: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class NPC:
    """NPC from Pass 3."""
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[str] = None
    motivation: Optional[str] = None
    goals: List[str] = field(default_factory=list)
    dialogue_hooks: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    equipment: List[str] = field(default_factory=list)
    treasure: List[str] = field(default_factory=list)
    spells: List[str] = field(default_factory=list)
    faction: Optional[str] = None
    initial_disposition: str = "neutral"
    is_unique: bool = True
    locations_mentioned: List[str] = field(default_factory=list)


@dataclass
class DMGuidance:
    """DM guidance for a location from Pass 4."""
    location_key: str
    how_to_run: str = ""
    common_mistakes: Optional[str] = None
    player_actions: List[Dict[str, str]] = field(default_factory=list)
    scaling_notes: Optional[str] = None
    secrets_to_reveal: List[str] = field(default_factory=list)
    foreshadowing: Optional[str] = None


@dataclass
class Secret:
    """Module-wide secret or reveal from Pass 4."""
    name: str
    description: str
    location_keys: List[str] = field(default_factory=list)
    reveal_conditions: Optional[str] = None
    player_impact: Optional[str] = None


@dataclass
class AtmosphereNote:
    """Atmosphere/mood note from Pass 5."""
    sight: Optional[str] = None
    sound: Optional[str] = None
    smell: Optional[str] = None
    touch: Optional[str] = None
    mood: Optional[str] = None
    temperature: Optional[str] = None


@dataclass
class StoryBeat:
    """Story beat from Pass 6."""
    name: str
    sequence: int
    description: str
    trigger: Optional[Dict[str, Any]] = None
    branches: List[Dict[str, Any]] = field(default_factory=list)
    related_locations: List[str] = field(default_factory=list)
    is_critical_path: bool = False


@dataclass
class LocationConnection:
    """Connection between locations from Pass 6."""
    from_location: str
    to_location: str
    connection_type: str  # door, passage, secret, trap, one_way
    description: Optional[str] = None
    requirements: Optional[str] = None  # Key needed, strength check, etc.


@dataclass
class ExtractionContext:
    """Running context document that grows with each pass.

    This accumulates information across all extraction passes,
    allowing later passes to reference context from earlier ones.
    """

    # Pass 1 outputs
    overview: ModuleOverview = field(default_factory=ModuleOverview)
    location_list: List[LocationBrief] = field(default_factory=list)
    adventure_flow: str = ""

    # Pass 2 outputs
    locations: Dict[str, LocationDetails] = field(default_factory=dict)

    # Pass 3 outputs
    encounters: Dict[str, List[Encounter]] = field(default_factory=dict)  # Keyed by location_key
    wandering_tables: List[WanderingTable] = field(default_factory=list)
    npcs: List[NPC] = field(default_factory=list)

    # Pass 4 outputs
    dm_notes: Dict[str, DMGuidance] = field(default_factory=dict)  # Per-location DM advice
    secrets: List[Secret] = field(default_factory=list)  # Module-wide secrets
    module_dm_guidance: str = ""  # Overall DM guidance

    # Pass 5 outputs
    read_aloud: Dict[str, str] = field(default_factory=dict)  # Refined per-location
    atmosphere: Dict[str, AtmosphereNote] = field(default_factory=dict)  # Per-location

    # Pass 6 outputs
    story_beats: List[StoryBeat] = field(default_factory=list)
    connections: List[LocationConnection] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)  # List of location keys
    recommended_path: List[str] = field(default_factory=list)

    # Verification metadata
    verification_issues: List[str] = field(default_factory=list)
    gaps_filled: List[str] = field(default_factory=list)

    def to_context_prompt(self, include: List[str]) -> str:
        """Generate context string for LLM prompts.

        Args:
            include: List of sections to include. Options:
                - 'overview': Module overview
                - 'locations_brief': Brief location list
                - 'locations_full': Full location details
                - 'locations_summary': Summary of all locations
                - 'encounters': Encounter information
                - 'npcs': NPC information
                - 'dm_notes': DM guidance
                - 'atmosphere': Atmosphere notes
                - 'story': Story beats and connections

        Returns:
            Formatted context string for LLM prompt injection
        """
        parts = []

        if 'overview' in include and self.overview.title:
            parts.append("## MODULE OVERVIEW")
            parts.append(f"Title: {self.overview.title}")
            if self.overview.code:
                parts.append(f"Code: {self.overview.code}")
            if self.overview.level_min and self.overview.level_max:
                parts.append(f"Levels: {self.overview.level_min}-{self.overview.level_max}")
            if self.overview.summary:
                parts.append(f"Summary: {self.overview.summary}")
            if self.overview.main_objectives:
                parts.append(f"Objectives: {', '.join(self.overview.main_objectives)}")
            if self.adventure_flow:
                parts.append(f"Flow: {self.adventure_flow}")
            parts.append("")

        if 'locations_brief' in include and self.location_list:
            parts.append("## LOCATIONS (Brief)")
            for loc in self.location_list:
                parts.append(f"- {loc.key}. {loc.name}: {loc.brief_desc}")
            parts.append("")

        if 'locations_summary' in include and self.locations:
            parts.append("## LOCATIONS SUMMARY")
            for key, loc in sorted(self.locations.items(), key=lambda x: self._sort_key(x[0])):
                # Safely handle exits (might be dict, string, or None)
                if isinstance(loc.exits, dict) and loc.exits:
                    exits_str = ", ".join(f"{d}→{t}" for d, t in loc.exits.items())
                elif loc.exits:
                    exits_str = str(loc.exits)
                else:
                    exits_str = "none listed"
                parts.append(f"- {key}. {loc.name} (Level {loc.dungeon_level}): Exits: {exits_str}")
            parts.append("")

        if 'locations_full' in include and self.locations:
            parts.append("## LOCATIONS (Full Details)")
            for key, loc in sorted(self.locations.items(), key=lambda x: self._sort_key(x[0])):
                parts.append(f"### {key}. {loc.name}")
                parts.append(f"Level: {loc.dungeon_level}")
                if loc.dm_description:
                    parts.append(f"Description: {loc.dm_description[:500]}...")
                if loc.exits:
                    parts.append(f"Exits: {loc.exits}")
                if loc.treasure:
                    parts.append(f"Treasure: {loc.treasure}")
                parts.append("")

        if 'encounters' in include:
            if self.encounters:
                parts.append("## ENCOUNTERS BY LOCATION")
                for loc_key, encs in sorted(self.encounters.items(), key=lambda x: self._sort_key(x[0])):
                    for enc in encs:
                        creatures_str = ", ".join(f"{c.count} {c.name}" for c in enc.creatures) if enc.creatures else "unknown"
                        parts.append(f"- {loc_key}: {enc.name} ({creatures_str})")
                parts.append("")

            if self.wandering_tables:
                parts.append("## WANDERING MONSTER TABLES")
                for table in self.wandering_tables:
                    parts.append(f"- {table.table_name} (Level {table.dungeon_level}): {len(table.entries)} entries")
                parts.append("")

        if 'npcs' in include and self.npcs:
            parts.append("## NPCs")
            for npc in self.npcs:
                locs = ", ".join(npc.locations_mentioned) if npc.locations_mentioned else "various"
                parts.append(f"- {npc.name}: {npc.title or 'No title'} (Found: {locs})")
            parts.append("")

        if 'dm_notes' in include and self.dm_notes:
            parts.append("## DM GUIDANCE SUMMARY")
            for loc_key, guidance in sorted(self.dm_notes.items(), key=lambda x: self._sort_key(x[0])):
                if guidance.how_to_run:
                    parts.append(f"- {loc_key}: {guidance.how_to_run[:100]}...")
            parts.append("")

        if 'atmosphere' in include and self.atmosphere:
            parts.append("## ATMOSPHERE NOTES")
            for loc_key, atm in sorted(self.atmosphere.items(), key=lambda x: self._sort_key(x[0])):
                details = []
                if atm.sight:
                    details.append(f"sight: {atm.sight}")
                if atm.sound:
                    details.append(f"sound: {atm.sound}")
                if atm.mood:
                    details.append(f"mood: {atm.mood}")
                if details:
                    parts.append(f"- {loc_key}: {'; '.join(details)}")
            parts.append("")

        if 'story' in include:
            if self.story_beats:
                parts.append("## STORY PROGRESSION")
                for beat in sorted(self.story_beats, key=lambda b: b.sequence):
                    parts.append(f"{beat.sequence}. {beat.name}: {beat.description[:100]}...")
                parts.append("")

            if self.critical_path:
                parts.append(f"Critical Path: {' → '.join(self.critical_path)}")
                parts.append("")

        return "\n".join(parts)

    def _sort_key(self, location_key: str) -> tuple:
        """Parse location key for sorting."""
        import re
        match = re.search(r'(\d+)([a-z])?', location_key, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            suffix = match.group(2) or ''
            return (num, suffix.lower())
        return (0, location_key)

    def get_locations_summary(self) -> str:
        """Get a brief summary of all locations."""
        if not self.locations:
            return "No locations extracted yet."

        lines = []
        for key, loc in sorted(self.locations.items(), key=lambda x: self._sort_key(x[0])):
            lines.append(f"{key}. {loc.name}")
        return "\n".join(lines)

    def get_location_context(self, location_key: str, include_adjacent: bool = True) -> str:
        """Get context for a specific location including adjacent rooms."""
        if location_key not in self.locations:
            return ""

        loc = self.locations[location_key]
        parts = [f"## Location {location_key}: {loc.name}"]
        parts.append(f"Level: {loc.dungeon_level}")
        parts.append(f"Exits: {loc.exits}")

        if include_adjacent:
            # Get adjacent location briefs
            adjacent_keys = set(loc.exits.values())
            if adjacent_keys:
                parts.append("\n### Adjacent Locations:")
                for adj_key in adjacent_keys:
                    if adj_key in self.locations:
                        adj = self.locations[adj_key]
                        parts.append(f"- {adj_key}. {adj.name}")

        return "\n".join(parts)

    def merge(self, updates: 'ExtractionContext') -> None:
        """Merge updates from a pass into this context."""
        # Merge overview
        if updates.overview.title:
            self.overview = updates.overview
        if updates.adventure_flow:
            self.adventure_flow = updates.adventure_flow

        # Merge location list
        if updates.location_list:
            existing_keys = {loc.key for loc in self.location_list}
            for loc in updates.location_list:
                if loc.key not in existing_keys:
                    self.location_list.append(loc)

        # Merge locations
        self.locations.update(updates.locations)

        # Merge encounters
        for key, encs in updates.encounters.items():
            if key not in self.encounters:
                self.encounters[key] = []
            self.encounters[key].extend(encs)

        # Merge wandering tables
        existing_tables = {t.table_name for t in self.wandering_tables}
        for table in updates.wandering_tables:
            if table.table_name not in existing_tables:
                self.wandering_tables.append(table)

        # Merge NPCs
        existing_npcs = {npc.name for npc in self.npcs}
        for npc in updates.npcs:
            if npc.name not in existing_npcs:
                self.npcs.append(npc)

        # Merge DM notes
        self.dm_notes.update(updates.dm_notes)
        if updates.secrets:
            self.secrets.extend(updates.secrets)
        if updates.module_dm_guidance:
            self.module_dm_guidance = updates.module_dm_guidance

        # Merge player content
        self.read_aloud.update(updates.read_aloud)
        self.atmosphere.update(updates.atmosphere)

        # Merge narrative
        if updates.story_beats:
            existing_beats = {b.name for b in self.story_beats}
            for beat in updates.story_beats:
                if beat.name not in existing_beats:
                    self.story_beats.append(beat)

        if updates.connections:
            self.connections.extend(updates.connections)

        if updates.critical_path:
            self.critical_path = updates.critical_path
        if updates.recommended_path:
            self.recommended_path = updates.recommended_path

        # Merge verification data
        self.verification_issues.extend(updates.verification_issues)
        self.gaps_filled.extend(updates.gaps_filled)
