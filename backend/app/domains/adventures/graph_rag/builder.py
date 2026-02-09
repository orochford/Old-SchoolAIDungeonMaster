"""Graph builder for constructing knowledge graphs from parsed adventure modules.

Builds graph from database tables populated by MultiPassParser - NO LLM extraction needed.
"""

import logging
import re
import uuid as uuid_module
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domains.adventures.graph_rag.schema import (
    ModuleGraph,
    LocationNode,
    SubAreaNode,
    ItemNode,
    CreatureNode,
    NPCNode,
    TriggerNode,
    FeatureNode,
    ContainerNode,
    BodyNode,
    ConnectionEdge,
    InternalPathEdge,
    ContainsEdge,
    LocatedAtEdge,
    HasTriggerEdge,
    HasFeatureEdge,
    TriggerType,
    FeatureType,
    DispositionType,
    GraphValidationReport,
)
from app.domains.adventures.models import (
    AdventureModule,
    AdventureLocation,
    AdventureNPC,
    AdventureEncounter,
    AdventureItem,
)

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds a knowledge graph from parsed adventure module data.

    Uses data already extracted by MultiPassParser into database tables.
    No LLM calls - just transforms structured DB data into graph format.
    """

    @staticmethod
    def _safe_int(value, default):
        """Convert value to int, treating non-numeric strings like 'N/A' as default."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def __init__(self, db: AsyncSession):
        self.db = db
        # Use a unique suffix per builder instance to prevent ID collisions
        self._instance_id = uuid_module.uuid4().hex[:8]
        self._item_counter = 0
        self._trigger_counter = 0
        self._feature_counter = 0
        self._creature_counter = 0
        self._body_counter = 0
        # Track trap name -> trigger ID mapping for sub-area linking
        self._trap_name_to_trigger_id: Dict[str, str] = {}
        # Track location name -> key mapping for exit normalization
        self._location_name_to_key: Dict[str, str] = {}

    def _generate_id(self, prefix: str) -> str:
        """Generate a globally unique ID.

        Uses instance UUID + counter to prevent collisions across
        multiple builder instances or module re-parses.
        """
        if prefix == "item":
            self._item_counter += 1
            return f"item_{self._instance_id}_{self._item_counter}"
        elif prefix == "trigger":
            self._trigger_counter += 1
            return f"trigger_{self._instance_id}_{self._trigger_counter}"
        elif prefix == "feature":
            self._feature_counter += 1
            return f"feature_{self._instance_id}_{self._feature_counter}"
        elif prefix == "creature":
            self._creature_counter += 1
            return f"creature_{self._instance_id}_{self._creature_counter}"
        elif prefix == "body":
            self._body_counter += 1
            return f"body_{self._instance_id}_{self._body_counter}"
        return f"{prefix}_{self._instance_id}_{uuid_module.uuid4().hex[:8]}"

    async def build_graph(self, module_id: UUID) -> ModuleGraph:
        """Build a knowledge graph from parsed module data.

        Args:
            module_id: UUID of the parsed adventure module

        Returns:
            ModuleGraph with all entities and relationships
        """
        # Get module with all related data
        result = await self.db.execute(
            select(AdventureModule)
            .where(AdventureModule.id == module_id)
            .options(
                selectinload(AdventureModule.locations),
                selectinload(AdventureModule.npcs),
                selectinload(AdventureModule.encounters),
                selectinload(AdventureModule.items),
            )
        )
        module = result.scalar_one_or_none()

        if not module:
            raise ValueError(f"Module not found: {module_id}")

        graph = ModuleGraph(
            module_id=str(module_id),
            module_title=module.title,
            module_code=module.code,
        )

        # Build location index for linking
        location_map: Dict[UUID, str] = {}  # location.id -> location_key

        # Build location name -> key map for exit normalization
        for location in module.locations:
            location_map[location.id] = location.location_key
            # Map both the name and variations for exit resolution
            self._location_name_to_key[location.name.lower()] = location.location_key
            # Also map without "the " prefix
            name_lower = location.name.lower()
            if name_lower.startswith("the "):
                self._location_name_to_key[name_lower[4:]] = location.location_key

        # Process locations
        for location in module.locations:
            self._add_location(graph, location)

        # Process NPCs
        for npc in module.npcs:
            location_key = location_map.get(npc.location_id) if npc.location_id else None
            self._add_npc(graph, npc, location_key)

        # Process encounters (creatures)
        for encounter in module.encounters:
            location_key = location_map.get(encounter.location_id) if encounter.location_id else None
            self._add_encounter(graph, encounter, location_key)

        # Process items
        for item in module.items:
            location_key = location_map.get(item.location_id) if item.location_id else None
            self._add_item(graph, item, location_key)

        logger.info(
            f"Built graph for {module.title}: "
            f"{len(graph.locations)} locations, "
            f"{len(graph.creatures)} creatures, "
            f"{len(graph.npcs)} NPCs, "
            f"{len(graph.items)} items"
        )

        # Validate and fix exit consistency
        self._validate_exits(graph)

        # Resolve orphan locations before final validation
        await self._resolve_orphans(graph, module)

        # Validate graph completeness (dangling exits, orphan locations)
        self._validate_graph_completeness(graph)

        return graph

    def _validate_exits(self, graph: ModuleGraph) -> None:
        """Validate exit directions are consistent and fix issues.

        If A→north→B, then B should have south→A.
        Logs warnings and attempts fixes for inconsistencies.
        """
        opposite_dirs = {
            'north': 'south', 'south': 'north',
            'east': 'west', 'west': 'east',
            'northeast': 'southwest', 'southwest': 'northeast',
            'northwest': 'southeast', 'southeast': 'northwest',
            'up': 'down', 'down': 'up',
        }

        # Build reverse index: for each location, what exits lead TO it?
        incoming: Dict[str, List[Tuple[str, str]]] = {}  # dest -> [(source, direction)]
        for conn in graph.connections:
            if conn.to_id not in incoming:
                incoming[conn.to_id] = []
            incoming[conn.to_id].append((conn.from_id, conn.direction))

        # Build outgoing index
        outgoing: Dict[str, Dict[str, str]] = {}  # source -> {direction: dest}
        for conn in graph.connections:
            if conn.from_id not in outgoing:
                outgoing[conn.from_id] = {}
            outgoing[conn.from_id][conn.direction] = conn.to_id

        fixes_needed = []

        for conn in graph.connections:
            # Skip secret connections - may be intentionally one-way
            if conn.is_secret or conn.is_one_way:
                continue

            base_dir = conn.direction.lower().replace('_door', '').replace('secret_', '')
            opposite = opposite_dirs.get(base_dir)

            if not opposite:
                continue

            # Check if destination has a return path to source
            dest_exits = outgoing.get(conn.to_id, {})
            has_return = False
            return_dir = None

            for exit_dir, exit_dest in dest_exits.items():
                if exit_dest == conn.from_id:
                    has_return = True
                    return_dir = exit_dir
                    break

            if not has_return:
                # Missing return path
                from_name = graph.locations.get(conn.from_id, {})
                to_name = graph.locations.get(conn.to_id, {})
                from_name = from_name.name if hasattr(from_name, 'name') else conn.from_id
                to_name = to_name.name if hasattr(to_name, 'name') else conn.to_id

                logger.warning(
                    f"Exit inconsistency: {from_name} ({conn.from_id}) → {conn.direction} → "
                    f"{to_name} ({conn.to_id}) but no return path exists"
                )
                fixes_needed.append((conn.to_id, opposite, conn.from_id))

            elif return_dir and return_dir.lower().replace('_door', '').replace('secret_', '') != opposite:
                # Return path exists but wrong direction
                from_name = graph.locations.get(conn.from_id, {})
                to_name = graph.locations.get(conn.to_id, {})
                from_name = from_name.name if hasattr(from_name, 'name') else conn.from_id
                to_name = to_name.name if hasattr(to_name, 'name') else conn.to_id

                logger.warning(
                    f"Exit direction mismatch: {from_name} → {conn.direction} → {to_name}, "
                    f"but {to_name} → {return_dir} → {from_name} (expected {opposite})"
                )

        # Apply fixes - add missing return connections
        for dest_id, direction, source_id in fixes_needed:
            # Check we're not creating a duplicate
            already_exists = False
            for conn in graph.connections:
                if conn.from_id == dest_id and conn.to_id == source_id:
                    already_exists = True
                    break

            if not already_exists:
                graph.add_connection(ConnectionEdge(
                    from_id=dest_id,
                    to_id=source_id,
                    direction=direction,
                    is_secret=False,
                    is_one_way=False,
                ))
                logger.info(f"Added missing return connection: {dest_id} → {direction} → {source_id}")

        if fixes_needed:
            logger.info(f"Exit validation complete: added {len(fixes_needed)} missing connections")

    def _validate_graph_completeness(self, graph: ModuleGraph) -> None:
        """Validate graph completeness and store report on the graph.

        Checks for:
        - Dangling exits: connections pointing to locations not in the graph
        - Orphan locations: locations with no connections at all
        """
        location_ids = set(graph.locations.keys())
        dangling_exits = []
        connected_ids: set = set()

        for conn in graph.connections:
            connected_ids.add(conn.from_id)
            connected_ids.add(conn.to_id)

            if conn.to_id not in location_ids:
                from_loc = graph.locations.get(conn.from_id)
                dangling_exits.append({
                    "from_id": conn.from_id,
                    "from_name": from_loc.name if from_loc else conn.from_id,
                    "direction": conn.direction,
                    "missing_target": conn.to_id,
                })

        # Orphan locations: in graph but never referenced by any connection
        orphan_locations = []
        for loc_id, loc in graph.locations.items():
            if loc_id not in connected_ids:
                orphan_locations.append({
                    "id": loc_id,
                    "name": loc.name,
                })

        report = GraphValidationReport(
            dangling_exits=dangling_exits,
            orphan_locations=orphan_locations,
            total_locations=len(graph.locations),
            total_connections=len(graph.connections),
        )
        graph.validation_report = report

        if dangling_exits:
            logger.warning(
                f"Graph completeness: {len(dangling_exits)} dangling exit(s) pointing to missing locations"
            )
            for de in dangling_exits[:5]:
                logger.warning(f"  {de['from_name']} -> {de['direction']} -> {de['missing_target']} (missing)")
        if orphan_locations:
            logger.info(f"Graph completeness: {len(orphan_locations)} orphan location(s) with no connections")

    async def _resolve_orphans(
        self,
        graph: ModuleGraph,
        module: AdventureModule,
    ) -> None:
        """Resolve orphan locations by finding connections from source text and maps.

        An orphan is a location with zero connections (no exits out, no exits in).
        Strategies (applied in order, stopping when connected):
        1. Parse the orphan's source text for room number references
        2. Scan all other rooms' source text for references to the orphan
        3. Use map vision AI to discover corridor connections
        4. Fall back to connecting to the nearest numbered room on the same level
        """
        # Build connected set
        connected_ids: set = set()
        for conn in graph.connections:
            connected_ids.add(conn.from_id)
            connected_ids.add(conn.to_id)

        orphan_keys = [
            loc_id for loc_id in graph.locations
            if loc_id not in connected_ids
        ]

        if not orphan_keys:
            return

        logger.info(f"Resolving {len(orphan_keys)} orphan location(s)...")

        # Build location lookup: key -> AdventureLocation
        loc_by_key: Dict[str, AdventureLocation] = {}
        for loc in module.locations:
            loc_by_key[loc.location_key] = loc

        all_location_keys = set(graph.locations.keys())
        resolved = 0
        still_orphaned = []

        for orphan_key in orphan_keys:
            db_loc = loc_by_key.get(orphan_key)
            if not db_loc:
                continue

            connections_added = 0

            # Strategy 1: Parse orphan's own source text for room references
            source = db_loc.source_text or db_loc.dm_description or ""
            if source:
                refs = self._extract_room_references(source, orphan_key, all_location_keys)
                for ref_key, direction in refs:
                    if not self._connection_exists(graph, orphan_key, ref_key):
                        graph.add_connection(ConnectionEdge(
                            from_id=orphan_key,
                            to_id=ref_key,
                            direction=direction,
                        ))
                        connections_added += 1
                    # Add return path
                    opposite = self._opposite_direction(direction)
                    if opposite and not self._connection_exists(graph, ref_key, orphan_key):
                        graph.add_connection(ConnectionEdge(
                            from_id=ref_key,
                            to_id=orphan_key,
                            direction=opposite,
                        ))
                        connections_added += 1

            # Strategy 2: Scan all other rooms' source text for mentions of this orphan
            if connections_added == 0:
                for other_key, other_loc in loc_by_key.items():
                    if other_key == orphan_key:
                        continue
                    other_source = other_loc.source_text or other_loc.dm_description or ""
                    if not other_source:
                        continue
                    refs = self._extract_room_references(other_source, other_key, {orphan_key})
                    for ref_key, direction in refs:
                        if ref_key == orphan_key and not self._connection_exists(graph, other_key, orphan_key):
                            graph.add_connection(ConnectionEdge(
                                from_id=other_key,
                                to_id=orphan_key,
                                direction=direction,
                            ))
                            opposite = self._opposite_direction(direction)
                            if opposite and not self._connection_exists(graph, orphan_key, other_key):
                                graph.add_connection(ConnectionEdge(
                                    from_id=orphan_key,
                                    to_id=other_key,
                                    direction=opposite,
                                ))
                            connections_added += 1
                            break
                    if connections_added > 0:
                        break

            if connections_added > 0:
                resolved += 1
                logger.info(f"  Resolved orphan {orphan_key} via text: {connections_added} connection(s)")
            else:
                still_orphaned.append(orphan_key)

        # Strategy 3: Use map vision AI for remaining orphans
        if still_orphaned:
            logger.info(f"  {len(still_orphaned)} orphan(s) remain after text scan, trying map analysis...")
            map_resolved = await self._resolve_orphans_via_map(
                graph, module, still_orphaned, loc_by_key, all_location_keys
            )
            resolved += map_resolved
            # Update still_orphaned list
            connected_ids_after_map: set = set()
            for conn in graph.connections:
                connected_ids_after_map.add(conn.from_id)
                connected_ids_after_map.add(conn.to_id)
            still_orphaned = [k for k in still_orphaned if k not in connected_ids_after_map]

        # Strategy 4: Fallback — connect to nearest room on same level
        for orphan_key in still_orphaned:
            db_loc = loc_by_key.get(orphan_key)
            if not db_loc:
                continue
            neighbor = self._find_nearest_neighbor(
                orphan_key, db_loc.dungeon_level or 1, loc_by_key, all_location_keys, graph
            )
            if neighbor:
                graph.add_connection(ConnectionEdge(
                    from_id=orphan_key,
                    to_id=neighbor,
                    direction="passage",
                ))
                graph.add_connection(ConnectionEdge(
                    from_id=neighbor,
                    to_id=orphan_key,
                    direction="passage",
                ))
                resolved += 1
                logger.info(f"  Resolved orphan {orphan_key}: fallback to adjacent room {neighbor}")
            else:
                logger.warning(f"  Could not resolve orphan {orphan_key}")

        logger.info(f"Orphan resolution: resolved {resolved}/{len(orphan_keys)}")

    async def _resolve_orphans_via_map(
        self,
        graph: ModuleGraph,
        module: AdventureModule,
        orphan_keys: List[str],
        loc_by_key: Dict[str, AdventureLocation],
        all_location_keys: set,
    ) -> int:
        """Use map vision AI to find connections for orphaned rooms."""
        try:
            from app.domains.adventures.map_corridor_discovery import (
                discover_corridors_from_maps,
            )

            # Build rooms dict for corridor discovery (all rooms, not just orphans)
            rooms_dict = {
                loc.location_key: loc for loc in module.locations
            }

            result = await discover_corridors_from_maps(
                self.db, module.pdf_document_id, rooms_dict
            )

            if not result.connections:
                logger.info("  Map analysis found no corridor connections")
                return 0

            # Apply only connections that involve orphan rooms
            orphan_set = set(orphan_keys)
            resolved = 0

            for conn in result.connections:
                involves_orphan = conn.from_room in orphan_set or conn.to_room in orphan_set
                both_exist = conn.from_room in all_location_keys and conn.to_room in all_location_keys

                if involves_orphan and both_exist and conn.confidence >= 0.6:
                    if not self._connection_exists(graph, conn.from_room, conn.to_room):
                        graph.add_connection(ConnectionEdge(
                            from_id=conn.from_room,
                            to_id=conn.to_room,
                            direction=conn.direction,
                            is_secret=conn.connection_type == "secret_door",
                        ))

                    # Add return path
                    opposite = self._opposite_direction(conn.direction)
                    if opposite and not self._connection_exists(graph, conn.to_room, conn.from_room):
                        graph.add_connection(ConnectionEdge(
                            from_id=conn.to_room,
                            to_id=conn.from_room,
                            direction=opposite,
                            is_secret=conn.connection_type == "secret_door",
                        ))

                    if conn.from_room in orphan_set:
                        orphan_set.discard(conn.from_room)
                        resolved += 1
                        logger.info(f"  Resolved orphan {conn.from_room} via map: {conn.direction} -> {conn.to_room}")
                    if conn.to_room in orphan_set:
                        orphan_set.discard(conn.to_room)
                        resolved += 1
                        logger.info(f"  Resolved orphan {conn.to_room} via map: connected from {conn.from_room}")

            return resolved

        except Exception as e:
            logger.warning(f"  Map-based orphan resolution failed: {e}")
            return 0

    def _extract_room_references(
        self,
        text: str,
        source_key: str,
        target_keys: set,
    ) -> List[Tuple[str, str]]:
        """Extract room number references from text with directional context.

        Returns list of (target_key, direction) tuples.
        """
        results = []
        text_lower = text.lower()

        # Patterns: "north to room 5", "passage leads east to 12", "south to area 3"
        dir_patterns = [
            (r'(north|south|east|west|northeast|northwest|southeast|southwest)\s+'
             r'(?:to\s+)?(?:room|area|location)?\s*(\d+[a-z]?)', 1, 2),
            # "room 5 to the north", "area 3 lies to the south"
            (r'(?:room|area|location)\s*(\d+[a-z]?)\s+(?:to the|lies?\s+(?:to the)?)\s+'
             r'(north|south|east|west|northeast|northwest|southeast|southwest)', 2, 1),
            # "leads to room 5", "connects to area 3" (no direction — use "passage")
            (r'(?:leads?|connects?|opens?|passage)\s+(?:to|into)\s+(?:room|area)?\s*(\d+[a-z]?)', None, 1),
        ]

        for pattern, dir_group, key_group in dir_patterns:
            for match in re.finditer(pattern, text_lower):
                if dir_group is not None:
                    direction = match.group(dir_group)
                    ref_key = match.group(key_group)
                else:
                    direction = "passage"
                    ref_key = match.group(key_group)

                if ref_key != source_key and ref_key in target_keys:
                    # Avoid duplicates
                    if not any(r[0] == ref_key for r in results):
                        results.append((ref_key, direction))

        # Simpler fallback: just find "room N" or standalone numbers that match known keys
        if not results:
            for match in re.finditer(r'(?:room|area)\s+(\d+[a-z]?)', text_lower):
                ref_key = match.group(1)
                if ref_key != source_key and ref_key in target_keys:
                    if not any(r[0] == ref_key for r in results):
                        results.append((ref_key, "passage"))

        return results

    def _find_nearest_neighbor(
        self,
        orphan_key: str,
        dungeon_level: int,
        loc_by_key: Dict[str, AdventureLocation],
        all_keys: set,
        graph: ModuleGraph,
    ) -> Optional[str]:
        """Find the nearest numerically adjacent room on the same dungeon level."""
        try:
            orphan_num = int(re.match(r'(\d+)', orphan_key).group(1))
        except (AttributeError, ValueError):
            return None

        # Search outward from orphan's number: ±1, ±2, ±3...
        for offset in range(1, 10):
            for candidate_num in [orphan_num - offset, orphan_num + offset]:
                candidate_key = str(candidate_num)
                if candidate_key in all_keys and candidate_key in loc_by_key:
                    candidate_loc = loc_by_key[candidate_key]
                    if (candidate_loc.dungeon_level or 1) == dungeon_level:
                        return candidate_key
        return None

    def _connection_exists(self, graph: ModuleGraph, from_id: str, to_id: str) -> bool:
        """Check if a connection already exists between two locations."""
        for conn in graph.connections:
            if conn.from_id == from_id and conn.to_id == to_id:
                return True
        return False

    @staticmethod
    def _opposite_direction(direction: str) -> Optional[str]:
        """Get the opposite cardinal direction."""
        opposites = {
            'north': 'south', 'south': 'north',
            'east': 'west', 'west': 'east',
            'northeast': 'southwest', 'southwest': 'northeast',
            'northwest': 'southeast', 'southeast': 'northwest',
            'up': 'down', 'down': 'up',
            'passage': 'passage',
        }
        return opposites.get(direction.lower())

    def _add_location(self, graph: ModuleGraph, location: AdventureLocation) -> None:
        """Add a location and its contents to the graph."""
        location_key = location.location_key

        # Determine if empty - must have empty-sounding description AND no actual content
        # A room with "empty" in description but traps/secrets is NOT truly empty
        has_content = bool(
            location.traps or
            location.secrets or
            location.treasure or
            (location.features and len(location.features) > 0)
        )
        is_empty = self._detect_empty_room(location.dm_description or "") and not has_content

        # Create location node
        loc_node = LocationNode(
            id=location_key,
            key=location_key,
            name=location.name,
            description=location.source_text or location.dm_description or "",
            read_aloud=location.read_aloud_text,
            is_empty=is_empty,
        )
        graph.add_location(loc_node)

        # Extract and add sub-areas for complex locations
        sub_areas = self._extract_sub_areas(
            location_key,
            location.dm_description or "",
            location.traps or [],
        )
        for sub_area in sub_areas:
            graph.add_subarea(sub_area)

        # Create internal paths between sub-areas
        for i in range(len(sub_areas) - 1):
            graph.add_internal_path(InternalPathEdge(
                from_subarea=sub_areas[i].id,
                to_subarea=sub_areas[i + 1].id,
                description=None,
            ))

        # Extract bodies from location description
        body_text = location.source_text or location.dm_description or ""
        bodies = self._extract_bodies(location_key, body_text)
        for body in bodies:
            graph.add_body(body)
            graph.add_located_at(LocatedAtEdge(
                entity_id=body.id,
                location_id=location_key,
            ))

        # Process exits
        if location.exits:
            for direction, destination in location.exits.items():
                dest_key = self._normalize_destination(destination)
                is_secret = "secret" in direction.lower() or "secret" in str(destination).lower()

                edge = ConnectionEdge(
                    from_id=location_key,
                    to_id=dest_key,
                    direction=direction.lower().replace("secret_", "").replace("_door", ""),
                    description=destination if isinstance(destination, str) else None,
                    is_secret=is_secret,
                )
                graph.add_connection(edge)

        # Process traps as triggers
        if location.traps:
            for trap in location.traps:
                trigger_id = self._generate_id("trigger")
                trap_name = trap.get("name", "Trap")
                trigger = TriggerNode(
                    id=trigger_id,
                    trigger_type=TriggerType.TRAP,
                    name=trap_name,
                    condition=trap.get("trigger", "Unknown trigger"),
                    effect=trap.get("effect", ""),
                    damage=trap.get("damage"),
                    save=trap.get("save") or trap.get("detection"),
                )
                graph.add_trigger(trigger)
                graph.add_trigger_link(HasTriggerEdge(
                    location_id=location_key,
                    trigger_id=trigger.id,
                ))
                # Store mapping for sub-area linking
                self._trap_name_to_trigger_id[trap_name.lower()] = trigger_id

        # Process features
        if location.features:
            for feat in location.features:
                feature = FeatureNode(
                    id=self._generate_id("feature"),
                    feature_type=self._map_feature_type(feat.get("feature", "")),
                    name=feat.get("feature", "Feature"),
                    description=feat.get("details", ""),
                    is_secret=False,
                )
                graph.add_feature(feature)
                graph.add_feature_link(HasFeatureEdge(
                    location_id=location_key,
                    feature_id=feature.id,
                ))

        # Process secrets (secret doors, hidden things)
        if location.secrets:
            for secret in location.secrets:
                secret_type = secret.get("type", "secret")
                if "door" in secret_type.lower():
                    feature = FeatureNode(
                        id=self._generate_id("feature"),
                        feature_type=FeatureType.SECRET_DOOR,
                        name="Secret Door",
                        description=secret.get("description", ""),
                        is_secret=True,
                        detection_method=secret.get("detection"),
                    )
                    graph.add_feature(feature)
                    graph.add_feature_link(HasFeatureEdge(
                        location_id=location_key,
                        feature_id=feature.id,
                    ))
                else:
                    # Hidden item or compartment
                    feature = FeatureNode(
                        id=self._generate_id("feature"),
                        feature_type=FeatureType.HIDDEN_COMPARTMENT,
                        name=secret.get("type", "Hidden"),
                        description=secret.get("description", ""),
                        is_secret=True,
                        detection_method=secret.get("detection"),
                    )
                    graph.add_feature(feature)
                    graph.add_feature_link(HasFeatureEdge(
                        location_id=location_key,
                        feature_id=feature.id,
                    ))

        # Process location treasure
        if location.treasure:
            for treasure in location.treasure:
                item = ItemNode(
                    id=self._generate_id("item"),
                    name=treasure.get("item", "Treasure"),
                    quantity=self._parse_quantity(treasure.get("value", "1")),
                    unit=self._parse_unit(treasure.get("value", "")),
                    description=treasure.get("location", ""),
                    is_hidden="hidden" in str(treasure.get("location", "")).lower(),
                )
                graph.add_item(item)
                graph.add_containment(ContainsEdge(
                    container_id=location_key,
                    item_id=item.id,
                    is_hidden=item.is_hidden,
                ))

    def _add_npc(
        self,
        graph: ModuleGraph,
        npc: AdventureNPC,
        location_key: Optional[str],
    ) -> None:
        """Add an NPC to the graph."""
        # Map disposition
        disposition_map = {
            "hostile": DispositionType.HOSTILE,
            "unfriendly": DispositionType.UNFRIENDLY,
            "neutral": DispositionType.NEUTRAL,
            "friendly": DispositionType.FRIENDLY,
            "helpful": DispositionType.HELPFUL,
        }
        disposition = disposition_map.get(
            (npc.initial_disposition or "neutral").lower(),
            DispositionType.NEUTRAL,
        )

        # Extract combat stats from npc.stats dict if present
        stats = npc.stats or {}
        npc_hd = stats.get("hd") if isinstance(stats, dict) else None
        npc_hp = stats.get("hp") if isinstance(stats, dict) else None
        npc_ac = stats.get("ac") if isinstance(stats, dict) else None

        # Convert hp to int if needed
        if npc_hp is not None:
            try:
                npc_hp = int(npc_hp) if not isinstance(npc_hp, int) else npc_hp
            except (ValueError, TypeError):
                npc_hp = None

        # Convert ac to int if needed
        if npc_ac is not None:
            try:
                npc_ac = int(npc_ac) if not isinstance(npc_ac, int) else npc_ac
            except (ValueError, TypeError):
                npc_ac = None

        npc_node = NPCNode(
            id=str(npc.id),
            name=npc.name,
            title=npc.title,
            description=npc.description or "",
            personality=npc.personality,
            motivation=npc.motivation,
            disposition=disposition,
            dialogue_hooks=npc.dialogue_hooks or [],
            hd=str(npc_hd) if npc_hd else None,
            hp=npc_hp,
            ac=npc_ac,
        )
        graph.add_npc(npc_node)

        if location_key:
            graph.add_located_at(LocatedAtEdge(
                entity_id=npc_node.id,
                location_id=location_key,
            ))

    def _add_encounter(
        self,
        graph: ModuleGraph,
        encounter: AdventureEncounter,
        location_key: Optional[str],
    ) -> None:
        """Add encounter creatures to the graph."""
        if not encounter.creatures:
            return

        for creature_data in encounter.creatures:
            try:
                # Parse creature stats
                count = creature_data.get("count", 1)
                if isinstance(count, str):
                    # Handle "1d6" style counts or ranges like "3-5"
                    original_count = count
                    range_match = re.search(r'(\d+)\s*[-–—]\s*(\d+)', count)
                    dice_match = re.search(r'(\d+)d\d+', count.lower())
                    if range_match:
                        count = int(range_match.group(1))  # Use minimum
                        logger.debug(f"Creature count range '{original_count}' -> {count} (min)")
                    elif dice_match:
                        count = int(dice_match.group(1))  # Use dice count as minimum
                        logger.debug(f"Creature count dice '{original_count}' -> {count}")
                    else:
                        # Try to extract any number
                        num_match = re.search(r'(\d+)', count)
                        count = int(num_match.group(1)) if num_match else 1
                        if count != 1:
                            logger.debug(f"Creature count '{original_count}' -> {count}")

                # Parse HP - might be individual HPs, a single value, or comma-separated
                hp_list = []
                hp_val = creature_data.get("hp")
                if hp_val:
                    if isinstance(hp_val, list):
                        hp_list = [int(h) for h in hp_val if h is not None]
                    elif isinstance(hp_val, str):
                        # Handle comma-separated HP values like "6,5,5,4,4,3,3,2,"
                        if "," in hp_val:
                            parts = [p.strip() for p in hp_val.split(",") if p.strip()]
                            hp_list = [int(p) for p in parts if p.isdigit()]
                        else:
                            # Single string value
                            try:
                                hp_list = [int(hp_val)] * count
                            except ValueError:
                                hp_list = []
                    elif isinstance(hp_val, int):
                        hp_list = [hp_val] * count

                creature = CreatureNode(
                    id=self._generate_id("creature"),
                    name=creature_data.get("name", "Unknown"),
                    count=count,
                    hd=str(creature_data.get("hd") or "1"),
                    hp=hp_list,
                    ac=self._safe_int(creature_data.get("ac"), 9),
                    thac0=self._safe_int(creature_data.get("thac0"), 19),
                    attacks=self._format_attacks(creature_data.get("attacks", [])),
                    damage=self._format_damage(creature_data.get("damage", [])),
                    morale=self._safe_int(creature_data.get("morale"), 7),
                    special=", ".join(creature_data.get("special", [])) if creature_data.get("special") else None,
                    behavior=encounter.tactics,
                )
                graph.add_creature(creature)

                if location_key:
                    graph.add_located_at(LocatedAtEdge(
                        entity_id=creature.id,
                        location_id=location_key,
                    ))
            except Exception as e:
                logger.warning(f"Failed to add creature {creature_data.get('name', 'Unknown')}: {e}")

        # Add encounter treasure
        if encounter.treasure and location_key:
            for treasure in encounter.treasure:
                if isinstance(treasure, dict):
                    item = ItemNode(
                        id=self._generate_id("item"),
                        name=treasure.get("item", "Treasure"),
                        quantity=self._parse_quantity(str(treasure.get("value", "1"))),
                        unit=self._parse_unit(str(treasure.get("value", ""))),
                    )
                elif isinstance(treasure, str):
                    item = ItemNode(
                        id=self._generate_id("item"),
                        name=treasure,
                        quantity=self._parse_quantity(treasure),
                        unit=self._parse_unit(treasure),
                    )
                else:
                    continue

                graph.add_item(item)
                graph.add_containment(ContainsEdge(
                    container_id=location_key,
                    item_id=item.id,
                ))

    def _add_item(
        self,
        graph: ModuleGraph,
        item: AdventureItem,
        location_key: Optional[str],
    ) -> None:
        """Add an item to the graph."""
        item_node = ItemNode(
            id=str(item.id),
            name=item.name,
            quantity=self._parse_quantity(item.value or "1"),
            unit=self._parse_unit(item.value or ""),
            value_gp=self._parse_gp_value(item.value),
            description=item.description,
            is_magical=item.is_magical or False,
            magical_properties=item.magical_properties,
        )
        graph.add_item(item_node)

        if location_key:
            graph.add_containment(ContainsEdge(
                container_id=location_key,
                item_id=item_node.id,
            ))

    def _detect_empty_room(self, description: str) -> bool:
        """Detect if a room is described as empty."""
        empty_phrases = [
            "empty",
            "barren",
            "nothing of interest",
            "nothing here",
            "vacant",
            "abandoned and empty",
            "completely empty",
        ]
        desc_lower = description.lower()
        return any(phrase in desc_lower for phrase in empty_phrases)

    def _normalize_destination(self, dest: str) -> str:
        """Normalize destination string to a location key.

        Handles various formats:
        - "Room 2", "2", "Area 2 (through secret door)" -> "2"
        - "The Treasury", "Treasury" -> looks up in location name map
        - Falls back to slugified name if no match found
        """
        if not dest:
            return "unknown"

        dest_str = str(dest).strip()

        # First, try to extract a number (most common case)
        match = re.search(r'(\d+[a-z]?)', dest_str)
        if match:
            return match.group(1)

        # Try to look up by location name
        dest_lower = dest_str.lower()

        # Remove common prefixes and suffixes for matching
        for prefix in ["room ", "area ", "the ", "to ", "to the "]:
            if dest_lower.startswith(prefix):
                dest_lower = dest_lower[len(prefix):]

        # Remove parenthetical notes like "(through secret door)"
        paren_match = re.match(r'^([^(]+)', dest_lower)
        if paren_match:
            dest_lower = paren_match.group(1).strip()

        # Look up in our location name map
        if dest_lower in self._location_name_to_key:
            return self._location_name_to_key[dest_lower]

        # Log warning for unresolved destinations
        logger.warning(f"Could not resolve exit destination '{dest}' to a location key")

        # Fall back to slugified name
        return dest_lower.replace(" ", "_")[:20]

    def _format_attacks(self, attacks: Any) -> str:
        """Format attacks list to string."""
        if isinstance(attacks, list):
            return ", ".join(str(a) for a in attacks)
        return str(attacks) if attacks else "1"

    def _format_damage(self, damage: Any) -> str:
        """Format damage list to string."""
        if isinstance(damage, list):
            return ", ".join(str(d) for d in damage)
        return str(damage) if damage else "1d6"

    def _parse_quantity(self, value: str) -> int:
        """Parse quantity from value string like '500 gp', '3', or '3-5'.

        For ranges like '3-5', returns the first number (minimum).
        For dice notation like '1d6', returns 1.
        Logs a warning when range information is lost.
        """
        if not value:
            return 1

        value_str = str(value).strip()

        # Check for range notation (e.g., "3-5", "100-200")
        range_match = re.search(r'(\d+)\s*[-–—]\s*(\d+)', value_str)
        if range_match:
            min_val = int(range_match.group(1))
            max_val = int(range_match.group(2))
            logger.debug(f"Quantity range '{value_str}' parsed as minimum: {min_val} (max was {max_val})")
            return min_val

        # Check for dice notation (e.g., "1d6", "2d4+1")
        dice_match = re.search(r'(\d+)d\d+', value_str.lower())
        if dice_match:
            logger.debug(f"Dice quantity '{value_str}' parsed as {dice_match.group(1)}")
            return int(dice_match.group(1))

        # Standard number extraction
        match = re.search(r'(\d+)', value_str)
        return int(match.group(1)) if match else 1

    def _parse_unit(self, value: str) -> Optional[str]:
        """Parse unit from value string like '500 gp'."""
        if not value:
            return None
        value_str = str(value).lower()
        if "gp" in value_str:
            return "gp"
        elif "sp" in value_str:
            return "sp"
        elif "cp" in value_str:
            return "cp"
        elif "pp" in value_str:
            return "pp"
        elif "ep" in value_str:
            return "ep"
        return None

    def _parse_gp_value(self, value: Optional[str]) -> Optional[int]:
        """Parse gold piece value."""
        if not value:
            return None
        value_str = str(value).lower()
        if "gp" in value_str:
            match = re.search(r'(\d+)', value_str)
            if match:
                return int(match.group(1))
        return None

    def _map_feature_type(self, feature_str: str) -> FeatureType:
        """Map feature string to FeatureType enum."""
        feature_lower = feature_str.lower()
        if "secret" in feature_lower and "door" in feature_lower:
            return FeatureType.SECRET_DOOR
        elif "stair" in feature_lower:
            return FeatureType.STAIRS
        elif "pit" in feature_lower:
            return FeatureType.PIT
        elif "lever" in feature_lower:
            return FeatureType.LEVER
        elif "statue" in feature_lower:
            return FeatureType.STATUE
        elif "fountain" in feature_lower:
            return FeatureType.FOUNTAIN
        elif "hidden" in feature_lower:
            return FeatureType.HIDDEN_COMPARTMENT
        return FeatureType.OTHER

    def _extract_sub_areas(
        self,
        location_key: str,
        description: str,
        traps: List[Dict[str, Any]],
    ) -> List[SubAreaNode]:
        """Extract sub-areas from a location description.

        Parses the description for structural markers that indicate
        distinct areas within the location (e.g., alcoves, steps, intersection).
        """
        if not description or len(description) < 200:
            # Short descriptions likely don't have meaningful sub-areas
            return []

        sub_areas = []
        desc_lower = description.lower()

        # Patterns that indicate sub-areas with their approximate position
        # Format: (pattern, area_name, keywords_to_find_section)
        # NOTE: Patterns use word boundaries (\b) to avoid false matches like "area of effect"
        area_patterns = [
            # Entrance/entry areas
            (r'\b(?:entrance|entry point|opening)\b', 'Entrance', ['entrance', 'entry']),
            # Alcoves - detect "pairs of alcoves" or "alcoves"
            (r'\b(?:first|1st)\s+(?:pair of\s+)?alcoves?\b', 'First Alcoves', ['first', 'alcove']),
            (r'\b(?:second|2nd)\s+(?:pair of\s+)?alcoves?\b', 'Second Alcoves', ['second', 'alcove']),
            (r'\b(?:third|3rd)\s+(?:pair of\s+)?alcoves?\b', 'Third Alcoves', ['third', 'alcove']),
            # Steps/stairs
            (r'\b(?:two\s+)?steps?\s+up\b|\bstairs?\s+(?:up|leading)\b', 'Steps', ['step', 'stair']),
            (r'\bsteps?\s+down\b|\bstairs?\s+(?:down|descending)\b', 'Steps Down', ['step', 'stair', 'down']),
            # Intersections/corridors
            (r'\b(?:intersection|corridors?\s+meet|passage\s+(?:meets|joins))\b', 'Intersection', ['intersection', 'corridors meet']),
            # Battle scenes
            (r'\bremains of.*battle\b|\bgrisly sight\b|\bcombatants?\s+died\b', 'Battle Scene', ['battle', 'grisly', 'combatant']),
            # Other structural features
            (r'\b(?:far end|opposite end|north(?:ern)? end|south(?:ern)? end)\b', 'Far End', ['end']),
            (r'\b(?:center of the room|middle of the)\b', 'Center', ['center', 'middle']),
        ]

        # Find which patterns match and where
        found_areas = []
        for pattern, area_name, keywords in area_patterns:
            match = re.search(pattern, desc_lower)
            if match:
                # Find the position in the original description
                pos = match.start()
                found_areas.append((pos, area_name, keywords))

        if not found_areas:
            return []

        # Sort by position in description (order of traversal)
        found_areas.sort(key=lambda x: x[0])

        # Merge sub-areas that are very close together (within 100 chars)
        # This handles cases like "intersection... grisly sight" being the same place
        merged_areas = []
        for pos, area_name, keywords in found_areas:
            if merged_areas and pos - merged_areas[-1][0] < 100:
                # Merge with previous - combine names and keywords
                prev_pos, prev_name, prev_keywords = merged_areas[-1]
                combined_name = f"{prev_name} / {area_name}"
                combined_keywords = prev_keywords + keywords
                merged_areas[-1] = (prev_pos, combined_name, combined_keywords)
            else:
                merged_areas.append((pos, area_name, keywords))

        found_areas = merged_areas

        # Create sub-area nodes
        for i, (pos, area_name, keywords) in enumerate(found_areas):
            # Extract the relevant portion of description for this area
            # Find the text from this position to the next area (or end)
            start = pos
            end = found_areas[i + 1][0] if i + 1 < len(found_areas) else len(description)
            area_desc = description[start:end].strip()
            # Limit description length (2000 chars to capture detailed content like body descriptions)
            if len(area_desc) > 2000:
                area_desc = area_desc[:2000] + "..."

            # Find triggers that apply to this sub-area
            trigger_ids = []
            for trap in traps:
                trigger_condition = (trap.get("trigger", "") or "").lower()
                if any(kw in trigger_condition for kw in keywords):
                    # This trigger fires in this sub-area - use ID not name
                    trap_name = trap.get("name", "")
                    trap_name_lower = trap_name.lower()
                    if trap_name_lower in self._trap_name_to_trigger_id:
                        trigger_ids.append(self._trap_name_to_trigger_id[trap_name_lower])
                    else:
                        # Fallback to name if ID mapping not found (shouldn't happen)
                        logger.warning(f"Trap '{trap_name}' not found in trigger ID map")
                        trigger_ids.append(trap_name)

            # Clean up area name for ID (handle merged names with '/')
            area_id_part = area_name.lower().replace(' / ', '_').replace(' ', '_').replace('/', '_')
            sub_area = SubAreaNode(
                id=f"{location_key}_{area_id_part}",
                location_id=location_key,
                name=area_name,
                sequence=i,
                description=area_desc,
                triggers=trigger_ids,
                features=[],
                is_entry=(i == 0),
                is_exit=(i == len(found_areas) - 1),
            )
            sub_areas.append(sub_area)

        if sub_areas:
            logger.info(f"Extracted {len(sub_areas)} sub-areas for location {location_key}: "
                       f"{[a.name for a in sub_areas]}")

        return sub_areas

    def _extract_bodies(
        self,
        location_key: str,
        text: str,
    ) -> List[BodyNode]:
        """Extract body/corpse descriptions from location text.

        Parses patterns like:
        - "Body #1—A human fighter..." (B1 format)
        - "corpse of a warrior", "dead body of an elf"
        - "remains of a dwarf", "skeleton of a thief"
        """
        if not text or len(text) < 50:
            return []

        bodies: List[BodyNode] = []

        # Pattern 1: B1 numbered body format
        # "Body #1—A human fighter..." or "Body #2 — An elf magic-user..."
        # Use a non-greedy match that stops at the next Body # or end of text
        numbered_body_pattern = re.compile(
            r'Body\s*#?\s*(\d+)\s*[—–\-:]\s*(.+?)(?=Body\s*#?\s*\d+|$)',
            re.DOTALL | re.IGNORECASE,
        )

        for match in numbered_body_pattern.finditer(text):
            body_num = match.group(1)
            body_desc = match.group(2).strip()
            # Clean up: limit to reasonable length, strip trailing whitespace/periods
            body_desc = body_desc[:500].strip().rstrip('.')

            # Try to detect creature type from description
            creature_type = self._detect_creature_type(body_desc)

            body = BodyNode(
                id=f"{location_key}_body_{body_num}",
                description=body_desc,
                creature_type=creature_type,
                cause_of_death=None,
                state=None,
            )
            bodies.append(body)

        # Pattern 2: Generic corpse/remains patterns (only if no numbered bodies found)
        if not bodies:
            generic_patterns = [
                (r'(?:corpse|dead body)\s+of\s+(?:a|an)\s+(.+?)(?:\.|,|;|\n)', 'corpse'),
                (r'(?:remains|skeleton)\s+of\s+(?:a|an)\s+(.+?)(?:\.|,|;|\n)', 'remains'),
                (r'(?:slain|dead|fallen)\s+(\w+(?:\s+\w+)?)\s+(?:lies?|laying?|slumped)', 'slain'),
            ]

            body_counter = 0
            for pattern, state in generic_patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    body_counter += 1
                    desc = match.group(0).strip().rstrip('.')
                    creature_type = self._detect_creature_type(match.group(1))

                    body = BodyNode(
                        id=self._generate_id("body"),
                        description=desc,
                        creature_type=creature_type,
                        cause_of_death=None,
                        state=state,
                    )
                    bodies.append(body)

        if bodies:
            logger.info(
                f"Extracted {len(bodies)} bodies for location {location_key}: "
                f"{[b.id for b in bodies]}"
            )

        return bodies

    @staticmethod
    def _detect_creature_type(text: str) -> Optional[str]:
        """Detect creature race/class from body description text."""
        text_lower = text.lower()

        # Races
        races = ["human", "elf", "dwarf", "halfling", "gnome", "half-elf", "half-orc", "orc", "goblin"]
        # Classes
        classes = ["fighter", "magic-user", "cleric", "thief", "wizard", "mage", "priest", "rogue", "ranger", "paladin"]

        found_race = None
        found_class = None

        for race in races:
            if race in text_lower:
                found_race = race.title()
                break

        for cls in classes:
            if cls in text_lower:
                found_class = cls.title()
                break

        if found_race and found_class:
            return f"{found_race} {found_class}"
        return found_race or found_class


async def build_graph_from_module(
    db: AsyncSession,
    module_id: UUID,
) -> ModuleGraph:
    """Build a knowledge graph from a parsed adventure module.

    This uses the already-extracted data from MultiPassParser.
    No LLM calls - just transforms DB data to graph format.

    Args:
        db: Database session
        module_id: UUID of the adventure module

    Returns:
        ModuleGraph with all entities and relationships
    """
    builder = GraphBuilder(db)
    return await builder.build_graph(module_id)
