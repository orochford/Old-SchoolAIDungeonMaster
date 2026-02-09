"""Query system for retrieving exact facts from the module knowledge graph.

This is the key component that replaces prose-based RAG with structured data.
All queries return exact values that the LLM must use verbatim.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

from app.domains.adventures.graph_rag.schema import (
    ModuleGraph,
    LocationNode,
    SubAreaNode,
    ItemNode,
    CreatureNode,
    TriggerNode,
    FeatureNode,
    BodyNode,
    ContainerNode,
    TriggerType,
)

logger = logging.getLogger(__name__)


@dataclass
class SubAreaInfo:
    """Information about a sub-area within a location."""
    id: str
    name: str
    sequence: int
    description: str
    is_entry: bool
    is_exit: bool
    triggers: List[str]  # Trigger IDs that fire at this sub-area
    features: List[str]  # Feature IDs visible at this sub-area


@dataclass
class LocationFacts:
    """Structured facts about a location - AUTHORITATIVE DATA."""
    location_key: str
    name: str
    description: str
    read_aloud: Optional[str]
    is_empty: bool
    exits: Dict[str, Dict[str, Any]]  # direction -> {to_key, to_name, description, is_secret}
    contents: List[Dict[str, Any]]  # Items directly in location
    creatures: List[Dict[str, Any]]  # Creatures present
    npcs: List[Dict[str, Any]]  # NPCs present
    bodies: List[Dict[str, Any]]  # Bodies that can be searched
    triggers: List[Dict[str, Any]]  # Events that fire here
    features: List[Dict[str, Any]]  # Notable features
    containers: List[Dict[str, Any]]  # Containers (chests, etc.)
    sub_areas: List[SubAreaInfo] = None  # Sub-areas within this location (for progressive reveal)


class GraphQueryService:
    """Service for querying the module knowledge graph.

    All methods return structured data with EXACT values.
    The LLM must use these values verbatim - no interpretation needed.
    """

    def __init__(self, graph: ModuleGraph):
        self.graph = graph
        # Build indexes for fast lookup
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build reverse indexes for efficient queries."""
        # Index: location_id -> list of exits
        self._exits_by_location: Dict[str, List[Dict]] = {}
        for conn in self.graph.connections:
            if conn.from_id not in self._exits_by_location:
                self._exits_by_location[conn.from_id] = []
            self._exits_by_location[conn.from_id].append({
                "direction": conn.direction,
                "to_id": conn.to_id,
                "description": conn.description,
                "is_secret": conn.is_secret,
                "is_one_way": conn.is_one_way,
                "requirements": conn.requirements,
            })

        # Index: container_id -> list of contained item_ids
        self._contents_by_container: Dict[str, List[str]] = {}
        for edge in self.graph.containment:
            if edge.container_id not in self._contents_by_container:
                self._contents_by_container[edge.container_id] = []
            self._contents_by_container[edge.container_id].append(edge.item_id)

        # Index: location_id -> list of entity_ids (creatures, npcs, bodies)
        self._entities_at_location: Dict[str, List[str]] = {}
        for edge in self.graph.locations_of:
            if edge.location_id not in self._entities_at_location:
                self._entities_at_location[edge.location_id] = []
            self._entities_at_location[edge.location_id].append(edge.entity_id)

        # Index: location_id -> list of trigger_ids
        self._triggers_at_location: Dict[str, List[str]] = {}
        for edge in self.graph.trigger_links:
            if edge.location_id not in self._triggers_at_location:
                self._triggers_at_location[edge.location_id] = []
            self._triggers_at_location[edge.location_id].append(edge.trigger_id)

        # Index: location_id -> list of feature_ids
        self._features_at_location: Dict[str, List[str]] = {}
        for edge in self.graph.feature_links:
            if edge.location_id not in self._features_at_location:
                self._features_at_location[edge.location_id] = []
            self._features_at_location[edge.location_id].append(edge.feature_id)

    def get_location(self, location_key: str) -> Optional[LocationNode]:
        """Get a location by its key."""
        return self.graph.locations.get(location_key)

    def get_location_facts(self, location_key: str) -> Optional[LocationFacts]:
        """Get all facts about a location.

        This is the primary query method for gameplay. Returns everything
        the DM needs to know about the current location.
        """
        location = self.graph.locations.get(location_key)
        if not location:
            logger.warning(f"Location not found: {location_key}")
            return None

        # Get exits
        exits = {}
        for exit_info in self._exits_by_location.get(location_key, []):
            to_loc = self.graph.locations.get(exit_info["to_id"])
            exits[exit_info["direction"]] = {
                "to_key": exit_info["to_id"],
                "to_name": to_loc.name if to_loc else "Unknown",
                "description": exit_info["description"],
                "is_secret": exit_info["is_secret"],
                "requirements": exit_info["requirements"],
            }

        # Get direct contents (items in this location, not in containers)
        contents = []
        for item_id in self._contents_by_container.get(location_key, []):
            item = self.graph.items.get(item_id)
            if item:
                contents.append({
                    "id": item.id,
                    "name": item.display_name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "description": item.description,
                    "is_hidden": item.is_hidden,
                    "is_magical": item.is_magical,
                })

        # Get entities at this location
        creatures = []
        npcs = []
        bodies = []
        containers_here = []

        for entity_id in self._entities_at_location.get(location_key, []):
            # Check each entity type
            if entity_id in self.graph.creatures:
                creature = self.graph.creatures[entity_id]
                creatures.append({
                    "id": creature.id,
                    "name": creature.name,
                    "count": creature.count,
                    "hd": creature.hd,
                    "hp": creature.hp,
                    "ac": creature.ac,
                    "thac0": creature.thac0,
                    "attacks": creature.attacks,
                    "damage": creature.damage,
                    "morale": creature.morale,
                    "special": creature.special,
                    "behavior": creature.behavior,
                })
            elif entity_id in self.graph.npcs:
                npc = self.graph.npcs[entity_id]
                npcs.append({
                    "id": npc.id,
                    "name": npc.name,
                    "title": npc.title,
                    "description": npc.description,
                    "personality": npc.personality,
                    "disposition": npc.disposition.value,
                })
            elif entity_id in self.graph.bodies:
                body = self.graph.bodies[entity_id]
                # Also get items contained in this body
                body_items = self._get_container_contents(entity_id)
                bodies.append({
                    "id": body.id,
                    "description": body.description,
                    "creature_type": body.creature_type,
                    "cause_of_death": body.cause_of_death,
                    "state": body.state,
                    "contains": body_items,
                })
            elif entity_id in self.graph.containers:
                container = self.graph.containers[entity_id]
                container_items = self._get_container_contents(entity_id)
                containers_here.append({
                    "id": container.id,
                    "name": container.name,
                    "description": container.description,
                    "is_locked": container.is_locked,
                    "is_trapped": container.is_trapped,
                    "contains": container_items,
                })
            else:
                # Entity ID not found in any category - log warning
                logger.warning(
                    f"Entity '{entity_id}' at location '{location_key}' not found in any category "
                    f"(creatures, npcs, bodies, containers)"
                )

        # Get triggers
        triggers = []
        for trigger_id in self._triggers_at_location.get(location_key, []):
            trigger = self.graph.triggers.get(trigger_id)
            if trigger:
                triggers.append({
                    "id": trigger.id,
                    "type": trigger.trigger_type.value,
                    "name": trigger.name,
                    "condition": trigger.condition,
                    "effect": trigger.effect,
                    "dialogue": trigger.dialogue,  # EXACT dialogue
                    "damage": trigger.damage,
                    "save": trigger.save,
                    "repeatable": trigger.repeatable,
                })

        # Get features
        features = []
        for feature_id in self._features_at_location.get(location_key, []):
            feature = self.graph.features.get(feature_id)
            if feature:
                features.append({
                    "id": feature.id,
                    "type": feature.feature_type.value,
                    "name": feature.name,
                    "description": feature.description,
                    "is_secret": feature.is_secret,
                    "is_detectable": feature.is_detectable,
                    "detection_method": feature.detection_method,
                })

        # Get sub-areas for this location (for progressive reveal)
        sub_areas = self._get_sub_areas(location_key)

        return LocationFacts(
            location_key=location.key,
            name=location.name,
            description=location.description,
            read_aloud=location.read_aloud,
            is_empty=location.is_empty,
            exits=exits,
            contents=contents,
            creatures=creatures,
            npcs=npcs,
            bodies=bodies,
            triggers=triggers,
            features=features,
            containers=containers_here,
            sub_areas=sub_areas,
        )

    def _get_container_contents(
        self,
        container_id: str,
        _visited: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Get items contained in a container/body.

        Includes cycle detection to prevent infinite loops in case
        of malformed containment relationships.
        """
        # Initialize visited set for cycle detection
        if _visited is None:
            _visited = set()

        # Check for cycle
        if container_id in _visited:
            logger.warning(f"Containment cycle detected at '{container_id}', breaking loop")
            return []

        _visited.add(container_id)

        items = []
        for item_id in self._contents_by_container.get(container_id, []):
            item = self.graph.items.get(item_id)
            if item:
                items.append({
                    "name": item.display_name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "value_gp": item.value_gp,
                    "is_hidden": item.is_hidden,
                })
        return items

    def _get_sub_areas(self, location_key: str) -> List[SubAreaInfo]:
        """Get sub-areas for a location, sorted by sequence.

        Sub-areas enable progressive reveal - the DM only describes
        content the player has actually reached within a larger location.
        """
        sub_areas = []
        location = self.graph.locations.get(location_key)
        if not location or not location.sub_areas:
            return sub_areas

        for subarea_id in location.sub_areas:
            subarea = self.graph.sub_areas.get(subarea_id)
            if subarea:
                sub_areas.append(SubAreaInfo(
                    id=subarea.id,
                    name=subarea.name,
                    sequence=subarea.sequence,
                    description=subarea.description,
                    is_entry=subarea.is_entry,
                    is_exit=subarea.is_exit,
                    triggers=subarea.triggers,
                    features=subarea.features,
                ))

        # Sort by sequence
        sub_areas.sort(key=lambda x: x.sequence)
        return sub_areas

    def get_exits(self, location_key: str) -> Dict[str, Dict[str, Any]]:
        """Get exits from a location.

        Returns: {direction: {to_key, to_name, description, is_secret}}
        """
        exits = {}
        for exit_info in self._exits_by_location.get(location_key, []):
            to_loc = self.graph.locations.get(exit_info["to_id"])
            exits[exit_info["direction"]] = {
                "to_key": exit_info["to_id"],
                "to_name": to_loc.name if to_loc else "Unknown",
                "description": exit_info["description"],
                "is_secret": exit_info["is_secret"],
            }
        return exits

    def get_triggers(self, location_key: str) -> List[Dict[str, Any]]:
        """Get triggers for a location.

        Returns list of triggers with EXACT dialogue.
        """
        triggers = []
        for trigger_id in self._triggers_at_location.get(location_key, []):
            trigger = self.graph.triggers.get(trigger_id)
            if trigger:
                triggers.append({
                    "type": trigger.trigger_type.value,
                    "condition": trigger.condition,
                    "dialogue": trigger.dialogue,
                    "effect": trigger.effect,
                })
        return triggers

    def get_adjacent_locations(self, location_key: str) -> Dict[str, Dict[str, Any]]:
        """Get info about adjacent locations.

        Returns brief info about what's in each direction.
        """
        adjacent = {}
        for exit_info in self._exits_by_location.get(location_key, []):
            to_loc = self.graph.locations.get(exit_info["to_id"])
            if to_loc:
                adjacent[exit_info["direction"]] = {
                    "key": to_loc.key,
                    "name": to_loc.name,
                    "is_empty": to_loc.is_empty,
                    "brief": to_loc.description[:100] + "..." if len(to_loc.description) > 100 else to_loc.description,
                }
        return adjacent

    def search_body(self, body_id: str) -> Dict[str, Any]:
        """Get contents of a body when searched.

        Returns EXACT items with EXACT quantities.
        """
        body = self.graph.bodies.get(body_id)
        if not body:
            return {"found": False, "message": "No such body"}

        items = self._get_container_contents(body_id)
        return {
            "found": True,
            "body_description": body.description,
            "items": items,
        }

    def format_for_llm(self, facts: LocationFacts) -> str:
        """Format location facts for LLM context.

        This produces the structured context that replaces prose-based RAG.
        The LLM MUST use these exact values.
        """
        lines = []

        lines.append("## CURRENT LOCATION FACTS (AUTHORITATIVE - USE EXACTLY)")
        lines.append("")
        lines.append(f"**Location:** {facts.name} ({facts.location_key})")

        if facts.is_empty:
            lines.append("**⚠️ THIS LOCATION IS EMPTY** - Do not add atmosphere or details")

        lines.append("")
        lines.append(f"**Description:** {facts.description}")

        if facts.read_aloud:
            lines.append("")
            lines.append(f"**Read Aloud:** \"{facts.read_aloud}\"")

        # Exits
        lines.append("")
        lines.append("### EXITS (use these EXACT directions)")
        if facts.exits:
            for direction, exit_info in facts.exits.items():
                secret_marker = " [SECRET]" if exit_info.get("is_secret") else ""
                desc = f" - {exit_info['description']}" if exit_info.get("description") else ""
                lines.append(f"- **{direction.upper()}** → {exit_info['to_name']} ({exit_info['to_key']}){secret_marker}{desc}")
        else:
            lines.append("- No exits")

        # Triggers - MANDATORY
        if facts.triggers:
            lines.append("")
            lines.append("### ⚠️ MANDATORY TRIGGERS (MUST EXECUTE)")
            for trigger in facts.triggers:
                lines.append(f"**Type:** {trigger['type']}")
                lines.append(f"**When:** {trigger['condition']}")
                if trigger.get("dialogue"):
                    lines.append("**EXACT Dialogue (use verbatim, in order):**")
                    for i, line in enumerate(trigger["dialogue"], 1):
                        lines.append(f"  {i}. \"{line}\"")
                if trigger.get("effect"):
                    lines.append(f"**Effect:** {trigger['effect']}")
                lines.append("")

        # Creatures - EXPLICIT about presence or absence
        lines.append("")
        if facts.creatures:
            lines.append("### CREATURES PRESENT")
            for creature in facts.creatures:
                hp_str = f", HP: {', '.join(str(h) for h in creature['hp'])}" if creature.get("hp") else ""
                lines.append(f"- **{creature['count']}x {creature['name']}** (HD {creature['hd']}, AC {creature['ac']}, THAC0 {creature['thac0']}{hp_str})")
                lines.append(f"  Attacks: {creature['attacks']}, Damage: {creature['damage']}, Morale: {creature['morale']}")
                if creature.get("behavior"):
                    lines.append(f"  Behavior: {creature['behavior']}")
        else:
            lines.append("### ⚠️ NO CREATURES IN THIS LOCATION")
            lines.append("**DO NOT invent or add any monsters, creatures, or enemies.** This room has no hostile encounters unless a wandering monster check indicates one.")

        # Bodies
        if facts.bodies:
            lines.append("")
            lines.append("### BODIES (can be searched)")
            for body in facts.bodies:
                lines.append(f"- **{body['id']}:** {body['description']}")
                if body.get("contains"):
                    lines.append("  Contains (EXACT - do not change quantities):")
                    for item in body["contains"]:
                        lines.append(f"    - {item['name']}")

        # Contents
        if facts.contents:
            lines.append("")
            lines.append("### ITEMS IN LOCATION (EXACT quantities)")
            for item in facts.contents:
                hidden = " [HIDDEN]" if item.get("is_hidden") else ""
                lines.append(f"- {item['name']}{hidden}")

        # Containers
        if facts.containers:
            lines.append("")
            lines.append("### CONTAINERS")
            for container in facts.containers:
                status = []
                if container.get("is_locked"):
                    status.append("LOCKED")
                if container.get("is_trapped"):
                    status.append("TRAPPED")
                status_str = f" [{', '.join(status)}]" if status else ""
                lines.append(f"- **{container['name']}**{status_str}")
                if container.get("contains"):
                    lines.append("  Contains (EXACT):")
                    for item in container["contains"]:
                        lines.append(f"    - {item['name']}")

        # Features
        if facts.features:
            lines.append("")
            lines.append("### FEATURES")
            for feature in facts.features:
                secret = " [SECRET]" if feature.get("is_secret") else ""
                lines.append(f"- **{feature['name']}**{secret}: {feature['description']}")
                if feature.get("detection_method"):
                    lines.append(f"  Detection: {feature['detection_method']}")

        # Sub-areas (for progressive reveal)
        if facts.sub_areas:
            lines.append("")
            lines.append("### ⚠️ SUB-AREAS (PROGRESSIVE REVEAL)")
            lines.append("**CRITICAL:** This location has multiple distinct areas. Reveal content PROGRESSIVELY as the player moves through each sub-area. Do NOT describe later sub-areas until the player reaches them.")
            lines.append("")
            for sub in facts.sub_areas:
                entry_marker = " [ENTRY POINT]" if sub.is_entry else ""
                exit_marker = " [EXIT TO OTHER LOCATIONS]" if sub.is_exit else ""
                lines.append(f"**{sub.sequence}. {sub.name}**{entry_marker}{exit_marker}")
                if sub.description:
                    lines.append(f"   {sub.description}")
                if sub.triggers:
                    lines.append(f"   ⚠️ TRIGGERS HERE: {', '.join(sub.triggers)}")
                if sub.features:
                    lines.append(f"   Features visible: {', '.join(sub.features)}")
            lines.append("")
            lines.append("**When entering this location:** Start at sub-area 0. Call `update_subarea_position` as player progresses. Only fire triggers when player reaches the correct sub-area.")

        # Final reminder
        lines.append("")
        lines.append("---")
        lines.append("**RULES:** Use the EXACT values above. Do not change numbers, directions, or dialogue.")
        if facts.is_empty:
            lines.append("**This room is EMPTY.** Do not add atmosphere, hints, or 'you sense' descriptions.")

        return "\n".join(lines)

    def format_for_llm_with_state(
        self,
        facts: LocationFacts,
        current_subarea: Optional[str] = None,
        subareas_visited: Optional[List[str]] = None,
        triggered_content: Optional[List[str]] = None,
    ) -> str:
        """Format location facts with awareness of player's current position.

        This enables progressive reveal - only showing content for sub-areas
        the player has actually reached.

        Args:
            facts: The location facts
            current_subarea: ID of the sub-area the player is currently in
            subareas_visited: List of sub-area IDs already visited in this location
            triggered_content: List of trigger/feature IDs already triggered
        """
        if subareas_visited is None:
            subareas_visited = []
        if triggered_content is None:
            triggered_content = []

        lines = []

        lines.append("## CURRENT LOCATION FACTS (AUTHORITATIVE - USE EXACTLY)")
        lines.append("")
        lines.append(f"**Location:** {facts.name} ({facts.location_key})")

        if current_subarea:
            # Find the current sub-area's name
            subarea_name = current_subarea
            if facts.sub_areas:
                for sub in facts.sub_areas:
                    if sub.id == current_subarea:
                        subarea_name = sub.name
                        break
            lines.append(f"**Current Position:** {subarea_name}")
            lines.append(f"**Areas Visited:** {len(subareas_visited)} of {len(facts.sub_areas or [])}")

        if facts.is_empty:
            lines.append("**⚠️ THIS LOCATION IS EMPTY** - Do not add atmosphere or details")

        lines.append("")
        lines.append(f"**Description:** {facts.description}")

        if facts.read_aloud:
            lines.append("")
            lines.append(f"**Read Aloud:** \"{facts.read_aloud}\"")

        # Exits
        lines.append("")
        lines.append("### EXITS (use these EXACT directions)")
        if facts.exits:
            for direction, exit_info in facts.exits.items():
                secret_marker = " [SECRET]" if exit_info.get("is_secret") else ""
                desc = f" - {exit_info['description']}" if exit_info.get("description") else ""
                lines.append(f"- **{direction.upper()}** → {exit_info['to_name']} ({exit_info['to_key']}){secret_marker}{desc}")
        else:
            lines.append("- No exits")

        # Sub-areas with state-aware formatting
        if facts.sub_areas:
            lines.append("")
            lines.append("### ⚠️ SUB-AREAS (PROGRESSIVE REVEAL - STATE TRACKED)")
            lines.append("")

            for sub in facts.sub_areas:
                visited = sub.id in subareas_visited
                is_current = sub.id == current_subarea
                status = "[CURRENT]" if is_current else "[VISITED]" if visited else "[NOT REACHED]"

                lines.append(f"**{sub.sequence}. {sub.name}** {status}")

                # Only show details for visited or current sub-areas
                if visited or is_current:
                    if sub.description:
                        lines.append(f"   {sub.description}")

                    # Show triggers for this sub-area
                    if sub.triggers:
                        for trigger_id in sub.triggers:
                            already_fired = trigger_id in triggered_content
                            fire_status = " [ALREADY FIRED]" if already_fired else " [FIRES NOW!]" if is_current else ""
                            lines.append(f"   ⚠️ TRIGGER: {trigger_id}{fire_status}")

                            # Get trigger details
                            trigger = self.graph.triggers.get(trigger_id)
                            if trigger and (is_current and not already_fired):
                                lines.append(f"      Type: {trigger.trigger_type.value}")
                                lines.append(f"      When: {trigger.condition}")
                                if trigger.dialogue:
                                    lines.append("      **EXACT Dialogue (use verbatim, in order):**")
                                    for i, line in enumerate(trigger.dialogue, 1):
                                        lines.append(f"        {i}. \"{line}\"")
                                if trigger.effect:
                                    lines.append(f"      Effect: {trigger.effect}")

                    if sub.features:
                        lines.append(f"   Features visible: {', '.join(sub.features)}")
                else:
                    lines.append(f"   [Content hidden - player has not reached this area]")

            # Instruction for next sub-area
            if current_subarea:
                current_idx = None
                for i, sub in enumerate(facts.sub_areas):
                    if sub.id == current_subarea:
                        current_idx = i
                        break
                if current_idx is not None and current_idx < len(facts.sub_areas) - 1:
                    next_sub = facts.sub_areas[current_idx + 1]
                    lines.append(f"")
                    lines.append(f"**NEXT AREA:** When player continues forward, call `update_subarea_position` with `{next_sub.id}` ({next_sub.name})")

        # Triggers not tied to specific sub-areas (or if no sub-areas)
        general_triggers = []
        if facts.triggers and not facts.sub_areas:
            general_triggers = facts.triggers
        elif facts.triggers:
            # Show triggers not linked to any sub-area
            subarea_triggers = set()
            for sub in facts.sub_areas or []:
                subarea_triggers.update(sub.triggers)
            general_triggers = [t for t in facts.triggers if t['id'] not in subarea_triggers]

        if general_triggers:
            lines.append("")
            lines.append("### ⚠️ MANDATORY TRIGGERS (MUST EXECUTE)")
            for trigger in general_triggers:
                already_fired = trigger['id'] in triggered_content
                status = " [ALREADY FIRED]" if already_fired else ""
                lines.append(f"**Type:** {trigger['type']}{status}")
                lines.append(f"**When:** {trigger['condition']}")
                if trigger.get("dialogue") and not already_fired:
                    lines.append("**EXACT Dialogue (use verbatim, in order):**")
                    for i, line in enumerate(trigger["dialogue"], 1):
                        lines.append(f"  {i}. \"{line}\"")
                if trigger.get("effect"):
                    lines.append(f"**Effect:** {trigger['effect']}")
                lines.append("")

        # Creatures - EXPLICIT about presence or absence
        lines.append("")
        if facts.creatures:
            lines.append("### CREATURES PRESENT")
            for creature in facts.creatures:
                hp_str = f", HP: {', '.join(str(h) for h in creature['hp'])}" if creature.get("hp") else ""
                lines.append(f"- **{creature['count']}x {creature['name']}** (HD {creature['hd']}, AC {creature['ac']}, THAC0 {creature['thac0']}{hp_str})")
                lines.append(f"  Attacks: {creature['attacks']}, Damage: {creature['damage']}, Morale: {creature['morale']}")
                if creature.get("behavior"):
                    lines.append(f"  Behavior: {creature['behavior']}")
        else:
            lines.append("### ⚠️ NO CREATURES IN THIS LOCATION")
            lines.append("**DO NOT invent or add any monsters, creatures, or enemies.** This room has no hostile encounters unless a wandering monster check indicates one.")

        # Bodies
        if facts.bodies:
            lines.append("")
            lines.append("### BODIES (can be searched)")
            for body in facts.bodies:
                lines.append(f"- **{body['id']}:** {body['description']}")
                if body.get("contains"):
                    lines.append("  Contains (EXACT - do not change quantities):")
                    for item in body["contains"]:
                        lines.append(f"    - {item['name']}")

        # Contents
        if facts.contents:
            lines.append("")
            lines.append("### ITEMS IN LOCATION (EXACT quantities)")
            for item in facts.contents:
                hidden = " [HIDDEN]" if item.get("is_hidden") else ""
                lines.append(f"- {item['name']}{hidden}")

        # Containers
        if facts.containers:
            lines.append("")
            lines.append("### CONTAINERS")
            for container in facts.containers:
                status = []
                if container.get("is_locked"):
                    status.append("LOCKED")
                if container.get("is_trapped"):
                    status.append("TRAPPED")
                status_str = f" [{', '.join(status)}]" if status else ""
                lines.append(f"- **{container['name']}**{status_str}")
                if container.get("contains"):
                    lines.append("  Contains (EXACT):")
                    for item in container["contains"]:
                        lines.append(f"    - {item['name']}")

        # Features
        if facts.features:
            lines.append("")
            lines.append("### FEATURES")
            for feature in facts.features:
                secret = " [SECRET]" if feature.get("is_secret") else ""
                lines.append(f"- **{feature['name']}**{secret}: {feature['description']}")
                if feature.get("detection_method"):
                    lines.append(f"  Detection: {feature['detection_method']}")

        # Final reminder
        lines.append("")
        lines.append("---")
        lines.append("**RULES:** Use the EXACT values above. Do not change numbers, directions, or dialogue.")
        if facts.is_empty:
            lines.append("**This room is EMPTY.** Do not add atmosphere, hints, or 'you sense' descriptions.")
        if facts.sub_areas:
            lines.append("**PROGRESSIVE REVEAL:** Only describe content for sub-areas the player has visited. Call `update_subarea_position` as player moves through the location.")

        return "\n".join(lines)
