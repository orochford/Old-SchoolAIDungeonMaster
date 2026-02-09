"""Graph schema for D&D module knowledge graphs.

Defines node types and relationship types for structured representation
of adventure module content. All values are EXACT - no approximations.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum
import json


# =============================================================================
# ENUMS
# =============================================================================

class TriggerType(str, Enum):
    MAGIC_MOUTH = "magic_mouth"
    TRAP = "trap"
    EVENT = "event"
    ENCOUNTER = "encounter"
    PUZZLE = "puzzle"


class FeatureType(str, Enum):
    SECRET_DOOR = "secret_door"
    HIDDEN_COMPARTMENT = "hidden_compartment"
    STAIRS = "stairs"
    PIT = "pit"
    LEVER = "lever"
    STATUE = "statue"
    FOUNTAIN = "fountain"
    OTHER = "other"


class DispositionType(str, Enum):
    HOSTILE = "hostile"
    UNFRIENDLY = "unfriendly"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    HELPFUL = "helpful"


# =============================================================================
# NODE TYPES
# =============================================================================

class SubAreaNode(BaseModel):
    """A distinct area within a larger location."""
    id: str = Field(..., description="Unique ID (e.g., '1_alcoves', '1_intersection')")
    location_id: str = Field(..., description="Parent location ID")
    name: str = Field(..., description="Area name (e.g., 'First Alcoves', 'Intersection')")
    sequence: int = Field(0, description="Order when traversing (0=entry, 1=next, etc.)")
    description: str = Field("", description="Description specific to this area")
    triggers: List[str] = Field(default_factory=list, description="Trigger IDs that fire here")
    features: List[str] = Field(default_factory=list, description="Feature IDs visible here")
    is_entry: bool = Field(False, description="True if this is the entry point")
    is_exit: bool = Field(False, description="True if this connects to other locations")
    node_type: Literal["subarea"] = "subarea"


class LocationNode(BaseModel):
    """A location in the dungeon/adventure."""
    id: str = Field(..., description="Unique ID, typically the location key like '1', '2', '31'")
    key: str = Field(..., description="Location key from module (e.g., '1', '2a')")
    name: str = Field(..., description="Location name (e.g., 'Alcoves', 'Kitchen')")
    description: str = Field("", description="EXACT verbatim description from module")
    read_aloud: Optional[str] = Field(None, description="Read-aloud text for players")
    dungeon_level: int = Field(1, description="Dungeon level (1, 2, etc.)")
    is_empty: bool = Field(False, description="True if explicitly described as empty/barren")
    atmosphere: Optional[str] = Field(None, description="Atmosphere notes if provided")
    sub_areas: List[str] = Field(default_factory=list, description="IDs of sub-areas in traversal order")
    node_type: Literal["location"] = "location"


class ItemNode(BaseModel):
    """An item that can be found or carried."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Item name (e.g., 'Gold Pieces', 'Longsword')")
    quantity: int = Field(1, description="EXACT quantity - never approximate")
    unit: Optional[str] = Field(None, description="Unit if applicable (e.g., 'gp', 'sp')")
    value_gp: Optional[int] = Field(None, description="Value in gold pieces if known")
    description: Optional[str] = Field(None, description="Item description")
    is_magical: bool = Field(False)
    magical_properties: Optional[str] = Field(None)
    is_hidden: bool = Field(False, description="True if item is hidden/concealed")
    node_type: Literal["item"] = "item"

    @property
    def display_name(self) -> str:
        """Format for display: '5 gold pieces' or 'Longsword'."""
        if self.quantity > 1 or self.unit:
            unit_str = f" {self.unit}" if self.unit else ""
            return f"{self.quantity}{unit_str} {self.name}"
        return self.name


class CreatureNode(BaseModel):
    """A creature or monster."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Creature name (e.g., 'Orc', 'Guard')")
    count: int = Field(1, description="EXACT number of creatures")
    hd: str = Field(..., description="Hit Dice (e.g., '1', '2+1', '3')")
    hp: List[int] = Field(default_factory=list, description="Individual HP values for each creature")
    ac: int = Field(9, description="Armor Class")
    thac0: int = Field(19, description="THAC0 value")
    attacks: str = Field("1", description="Number and type of attacks")
    damage: str = Field("1d6", description="Damage per attack")
    morale: int = Field(7, description="Morale score")
    special: Optional[str] = Field(None, description="Special abilities")
    behavior: Optional[str] = Field(None, description="How they behave (guarding, sleeping, etc.)")
    node_type: Literal["creature"] = "creature"


class NPCNode(BaseModel):
    """A named NPC."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="NPC name")
    title: Optional[str] = Field(None, description="Title or role")
    description: str = Field("", description="Physical description")
    personality: Optional[str] = Field(None)
    motivation: Optional[str] = Field(None)
    disposition: DispositionType = Field(DispositionType.NEUTRAL)
    dialogue_hooks: List[str] = Field(default_factory=list, description="Things they might say")
    # Combat stats if applicable
    hd: Optional[str] = Field(None)
    hp: Optional[int] = Field(None)
    ac: Optional[int] = Field(None)
    node_type: Literal["npc"] = "npc"


class TriggerNode(BaseModel):
    """A triggered event (magic mouth, trap, etc.)."""
    id: str = Field(..., description="Unique identifier")
    trigger_type: TriggerType = Field(..., description="Type of trigger")
    name: Optional[str] = Field(None, description="Name if applicable")
    condition: str = Field(..., description="When it triggers (e.g., 'reach third alcoves')")
    effect: str = Field(..., description="What happens")
    dialogue: List[str] = Field(default_factory=list, description="EXACT dialogue in sequence")
    damage: Optional[str] = Field(None, description="Damage if trap")
    save: Optional[str] = Field(None, description="Saving throw if applicable")
    repeatable: bool = Field(True, description="Can trigger multiple times")
    node_type: Literal["trigger"] = "trigger"


class FeatureNode(BaseModel):
    """A notable feature of a location."""
    id: str = Field(..., description="Unique identifier")
    feature_type: FeatureType = Field(..., description="Type of feature")
    name: str = Field(..., description="Feature name")
    description: str = Field("", description="Description")
    is_detectable: bool = Field(True, description="Can be detected by searching")
    detection_method: Optional[str] = Field(None, description="How to detect (e.g., '1-in-6 search')")
    is_secret: bool = Field(False, description="Is this a secret/hidden feature")
    node_type: Literal["feature"] = "feature"


class ContainerNode(BaseModel):
    """A container that holds items."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Container name (e.g., 'Belt Pouch', 'Iron Chest')")
    description: Optional[str] = Field(None)
    is_locked: bool = Field(False)
    is_trapped: bool = Field(False)
    node_type: Literal["container"] = "container"


class BodyNode(BaseModel):
    """A body/corpse that can be searched."""
    id: str = Field(..., description="Unique identifier (e.g., 'body_1')")
    description: str = Field(..., description="EXACT description from module")
    creature_type: Optional[str] = Field(None, description="What kind of creature")
    cause_of_death: Optional[str] = Field(None)
    state: Optional[str] = Field(None, description="State/position (e.g., 'slumped against wall')")
    node_type: Literal["body"] = "body"


# =============================================================================
# EDGE/RELATIONSHIP TYPES
# =============================================================================

class ConnectionEdge(BaseModel):
    """Connection between two locations."""
    from_id: str = Field(..., description="Source location ID")
    to_id: str = Field(..., description="Target location ID")
    direction: str = Field(..., description="Direction (north, east, etc.)")
    description: Optional[str] = Field(None, description="Door type, passage description")
    is_secret: bool = Field(False, description="Is this a secret passage")
    is_one_way: bool = Field(False, description="Can only go one direction")
    requirements: Optional[str] = Field(None, description="Key needed, strength check, etc.")
    edge_type: Literal["connects_to"] = "connects_to"


class ContainsEdge(BaseModel):
    """Containment relationship."""
    container_id: str = Field(..., description="ID of container (location, container, body)")
    item_id: str = Field(..., description="ID of contained item")
    is_hidden: bool = Field(False, description="Item is hidden within container")
    edge_type: Literal["contains"] = "contains"


class LocatedAtEdge(BaseModel):
    """Entity is located at a location."""
    entity_id: str = Field(..., description="ID of entity (creature, NPC, body)")
    location_id: str = Field(..., description="ID of location")
    position: Optional[str] = Field(None, description="Specific position within location")
    edge_type: Literal["located_at"] = "located_at"


class HasTriggerEdge(BaseModel):
    """Location has a trigger."""
    location_id: str
    trigger_id: str
    edge_type: Literal["has_trigger"] = "has_trigger"


class HasFeatureEdge(BaseModel):
    """Location has a feature."""
    location_id: str
    feature_id: str
    edge_type: Literal["has_feature"] = "has_feature"


class InternalPathEdge(BaseModel):
    """Path between sub-areas within a location."""
    from_subarea: str = Field(..., description="Source sub-area ID")
    to_subarea: str = Field(..., description="Target sub-area ID")
    description: Optional[str] = Field(None, description="How to traverse (e.g., 'up the steps')")
    edge_type: Literal["internal_path"] = "internal_path"


# =============================================================================
# GRAPH CONTAINER
# =============================================================================

# Union types for serialization
NodeType = LocationNode | ItemNode | CreatureNode | NPCNode | TriggerNode | FeatureNode | ContainerNode | BodyNode | SubAreaNode
EdgeType = ConnectionEdge | ContainsEdge | LocatedAtEdge | HasTriggerEdge | HasFeatureEdge | InternalPathEdge


class GraphValidationReport(BaseModel):
    """Report of graph completeness validation."""
    dangling_exits: List[Dict[str, Any]] = Field(default_factory=list, description="Exits pointing to non-existent locations")
    orphan_locations: List[Dict[str, Any]] = Field(default_factory=list, description="Locations with no connections")
    total_locations: int = 0
    total_connections: int = 0


class ModuleGraph(BaseModel):
    """Complete knowledge graph for an adventure module."""
    module_id: str = Field(..., description="UUID of the adventure module")
    module_title: str = Field(..., description="Module title")
    module_code: Optional[str] = Field(None, description="Module code (e.g., 'B1')")

    # Validation
    validation_report: Optional[GraphValidationReport] = Field(None, description="Graph completeness validation report")

    # Nodes by type for efficient lookup
    locations: Dict[str, LocationNode] = Field(default_factory=dict)
    sub_areas: Dict[str, SubAreaNode] = Field(default_factory=dict)
    items: Dict[str, ItemNode] = Field(default_factory=dict)
    creatures: Dict[str, CreatureNode] = Field(default_factory=dict)
    npcs: Dict[str, NPCNode] = Field(default_factory=dict)
    triggers: Dict[str, TriggerNode] = Field(default_factory=dict)
    features: Dict[str, FeatureNode] = Field(default_factory=dict)
    containers: Dict[str, ContainerNode] = Field(default_factory=dict)
    bodies: Dict[str, BodyNode] = Field(default_factory=dict)

    # Edges
    connections: List[ConnectionEdge] = Field(default_factory=list)
    internal_paths: List[InternalPathEdge] = Field(default_factory=list)
    containment: List[ContainsEdge] = Field(default_factory=list)
    locations_of: List[LocatedAtEdge] = Field(default_factory=list)
    trigger_links: List[HasTriggerEdge] = Field(default_factory=list)
    feature_links: List[HasFeatureEdge] = Field(default_factory=list)

    def add_location(self, node: LocationNode) -> None:
        """Add a location node."""
        self.locations[node.id] = node

    def add_subarea(self, node: SubAreaNode) -> None:
        """Add a sub-area node."""
        self.sub_areas[node.id] = node
        # Also link to parent location
        if node.location_id in self.locations:
            if node.id not in self.locations[node.location_id].sub_areas:
                self.locations[node.location_id].sub_areas.append(node.id)

    def add_internal_path(self, edge: InternalPathEdge) -> None:
        """Add an internal path between sub-areas."""
        self.internal_paths.append(edge)

    def add_item(self, node: ItemNode) -> None:
        """Add an item node."""
        self.items[node.id] = node

    def add_creature(self, node: CreatureNode) -> None:
        """Add a creature node."""
        self.creatures[node.id] = node

    def add_npc(self, node: NPCNode) -> None:
        """Add an NPC node."""
        self.npcs[node.id] = node

    def add_trigger(self, node: TriggerNode) -> None:
        """Add a trigger node."""
        self.triggers[node.id] = node

    def add_feature(self, node: FeatureNode) -> None:
        """Add a feature node."""
        self.features[node.id] = node

    def add_container(self, node: ContainerNode) -> None:
        """Add a container node."""
        self.containers[node.id] = node

    def add_body(self, node: BodyNode) -> None:
        """Add a body node."""
        self.bodies[node.id] = node

    def add_connection(self, edge: ConnectionEdge) -> None:
        """Add a connection between locations."""
        self.connections.append(edge)

    def add_containment(self, edge: ContainsEdge) -> None:
        """Add a containment relationship."""
        self.containment.append(edge)

    def add_located_at(self, edge: LocatedAtEdge) -> None:
        """Add a location relationship."""
        self.locations_of.append(edge)

    def add_trigger_link(self, edge: HasTriggerEdge) -> None:
        """Link a trigger to a location."""
        self.trigger_links.append(edge)

    def add_feature_link(self, edge: HasFeatureEdge) -> None:
        """Link a feature to a location."""
        self.feature_links.append(edge)

    def to_json(self) -> str:
        """Serialize graph to JSON."""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ModuleGraph":
        """Deserialize graph from JSON."""
        return cls.model_validate_json(json_str)

    def save(self, path: str) -> None:
        """Save graph to file."""
        with open(path, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ModuleGraph":
        """Load graph from file."""
        with open(path, 'r') as f:
            return cls.from_json(f.read())
