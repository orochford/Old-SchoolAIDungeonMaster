"""Connection reconciliation pass for dungeon graphs.

Sends map image(s) + complete current state to vision AI for a definitive
answer on room connections.  Unlike the additive-only merge in
map_corridor_discovery, this pass can ADD, REMOVE, and CORRECT connections.
"""

import json
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.adventures.models import AdventureLocation, AdventureModule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExitChange:
    """A single change to a room's exits."""
    room_key: str
    change_type: str       # "added", "removed", "direction_changed"
    direction: str
    destination: str
    old_direction: str | None = None
    old_destination: str | None = None
    reason: str = ""


@dataclass
class ReconciliationResult:
    """Result of the connection reconciliation pass."""
    authoritative_exits: dict[str, dict[str, str]] = field(default_factory=dict)
    changes: list[ExitChange] = field(default_factory=list)
    confidence: str = "medium"
    confidence_notes: str = ""
    disconnected_clusters: int = 0
    rooms_processed: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Opposite direction map (for bidirectional fixes)
# ---------------------------------------------------------------------------

OPPOSITE_DIRS = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
    "up": "down", "down": "up",
    "stairs_up": "stairs_down", "stairs_down": "stairs_up",
}


# ---------------------------------------------------------------------------
# Vision prompt
# ---------------------------------------------------------------------------

RECONCILIATION_PROMPT = """You are analyzing a dungeon map to produce the AUTHORITATIVE exit list for every room.

## MAP IMAGE
The attached image is a dungeon map. Room numbers are labeled on the map.

## ROOMS ON THIS LEVEL
{room_list}

## CURRENT EXITS (may contain errors from prior automated extraction)
{current_exits}

## KNOWN ISSUES
{validation_issues}

## DISCONNECTED CLUSTERS
{cluster_info}

## ROOM DESCRIPTION SNIPPETS (mentions of doors/corridors/directions)
{room_snippets}

## YOUR TASK
1. Examine the map image carefully. Trace every corridor, door, passage, and stairway.
2. Compare what you see on the map against the CURRENT EXITS listed above.
3. Produce a COMPLETE, CORRECTED exit list for EVERY room on this level.

## RULES
- The MAP is ground truth for physical connections. If a corridor exists on the map but not in current exits, ADD it.
- If current exits list a connection that does NOT exist on the map, REMOVE it.
- If a direction is wrong (e.g. listed as "north" but should be "east"), CORRECT it.
- All connections MUST be bidirectional: if Room A -> east -> Room B, then Room B -> west -> Room A.
- Destinations must be just the room number (e.g. "2", not "Room 2" or "Area 2").
- Every room MUST appear in your output, even if it has no exits.
- For stairs/ladders between levels, use "stairs_up", "stairs_down", etc.
- For secret doors, use "secret_north", "secret_east", etc.
- You MUST resolve disconnected clusters — find the connections between them on the map.

## OUTPUT FORMAT (JSON only, no other text)
{{
  "exits": {{
    "1": {{"north": "2", "east": "3"}},
    "2": {{"south": "1"}},
    "3": {{"west": "1"}}
  }},
  "confidence": "high",
  "changes_summary": [
    "Added Room 1 -> east -> Room 3 (visible corridor on map)",
    "Removed Room 5 -> north -> Room 99 (no such corridor on map)",
    "Changed Room 4 -> north -> Room 6 to east -> Room 6 (direction was wrong)"
  ]
}}
"""

CROSS_LEVEL_RECONCILIATION_PROMPT = """You are analyzing dungeon maps from MULTIPLE LEVELS to find connections BETWEEN levels.

## LEVEL {level1_num} ROOMS
{level1_rooms}

## LEVEL {level2_num} ROOMS
{level2_rooms}

## CURRENT CROSS-LEVEL CONNECTIONS
{current_cross_level}

## TASK
Find ALL connections between these two levels: stairs, ladders, chutes, trapdoors, etc.
Compare against the current cross-level connections and correct any errors.

## RULES
- Both directions required: stairs_down from room X to room Y AND stairs_up from room Y to room X.
- Destinations are just room numbers.
- Remove connections that don't exist on the maps.

## OUTPUT FORMAT (JSON only)
{{
  "cross_level_exits": [
    {{"from_room": "39", "to_room": "40", "direction": "stairs_down"}},
    {{"from_room": "40", "to_room": "39", "direction": "stairs_up"}}
  ],
  "confidence": "high",
  "changes_summary": ["Added stairs from Room 39 down to Room 40"]
}}
"""


# ---------------------------------------------------------------------------
# BFS / cluster detection
# ---------------------------------------------------------------------------

def _find_clusters(
    room_keys: set[str],
    exits: dict[str, dict[str, str]],
) -> list[set[str]]:
    """Find disconnected clusters using BFS on the exit graph."""
    visited: set[str] = set()
    clusters: list[set[str]] = []

    # Build adjacency from exits
    adj: dict[str, set[str]] = {k: set() for k in room_keys}
    for room, room_exits in exits.items():
        if room not in room_keys:
            continue
        for dest in room_exits.values():
            if dest in room_keys:
                adj.setdefault(room, set()).add(dest)
                adj.setdefault(dest, set()).add(room)

    for start in sorted(room_keys, key=lambda x: (int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 999, x)):
        if start in visited:
            continue
        cluster: set[str] = set()
        q = deque([start])
        cluster.add(start)
        while q:
            node = q.popleft()
            for nb in adj.get(node, set()):
                if nb not in cluster:
                    cluster.add(nb)
                    q.append(nb)
        visited |= cluster
        clusters.append(cluster)

    return clusters


def _format_clusters(clusters: list[set[str]]) -> str:
    """Format cluster info for the prompt."""
    if len(clusters) <= 1:
        return "All rooms are connected in a single cluster — no disconnected groups."
    lines = [f"WARNING: There are {len(clusters)} disconnected clusters. You MUST find connections between them.\n"]
    for i, cluster in enumerate(clusters, 1):
        sorted_keys = sorted(cluster, key=lambda x: (int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 999, x))
        lines.append(f"Cluster {i}: Rooms {', '.join(sorted_keys)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _format_current_exits(exits: dict[str, dict[str, str]]) -> str:
    """Format the current exits dict for the prompt."""
    lines = []
    for key in sorted(exits.keys(), key=lambda x: (int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 999, x)):
        room_exits = exits[key]
        if room_exits:
            exit_strs = [f"{d} -> Room {dest}" for d, dest in sorted(room_exits.items())]
            lines.append(f"Room {key}: {', '.join(exit_strs)}")
        else:
            lines.append(f"Room {key}: (no exits)")
    return "\n".join(lines)


def _format_validation_issues(
    exits: dict[str, dict[str, str]],
    room_keys: set[str],
) -> str:
    """Detect and format validation issues."""
    issues = []

    # Dangling exits
    for room, room_exits in exits.items():
        for direction, dest in room_exits.items():
            if dest not in room_keys:
                issues.append(f"DANGLING: Room {room} -> {direction} -> Room {dest} (Room {dest} does not exist)")

    # Missing return paths
    for room, room_exits in exits.items():
        for direction, dest in room_exits.items():
            if dest not in exits:
                continue
            base_dir = direction.lower().replace("secret_", "")
            opposite = OPPOSITE_DIRS.get(base_dir)
            if not opposite:
                continue
            dest_exits = exits.get(dest, {})
            has_return = any(d_dest == room for d_dest in dest_exits.values())
            if not has_return:
                issues.append(f"ONE-WAY: Room {room} -> {direction} -> Room {dest}, but Room {dest} has no exit back to Room {room}")

    # Orphan rooms
    connected = set()
    for room, room_exits in exits.items():
        if room_exits:
            connected.add(room)
        for dest in room_exits.values():
            connected.add(dest)
    orphans = room_keys - connected
    for orphan in sorted(orphans):
        issues.append(f"ORPHAN: Room {orphan} has no connections at all")

    if not issues:
        return "No validation issues detected."
    return "\n".join(issues)


def _format_room_snippets(
    locations: dict[str, "AdventureLocation"],
    keys: list[str],
) -> str:
    """Extract door/corridor/direction mentions from room descriptions."""
    lines = []
    door_patterns = re.compile(
        r"(door|corridor|passage|hall|stair|ladder|chute|trapdoor|tunnel|archway|opening|north|south|east|west)",
        re.IGNORECASE,
    )
    for key in sorted(keys, key=lambda x: (int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 999, x)):
        loc = locations.get(key)
        if not loc:
            continue
        desc = loc.dm_description or loc.source_text or ""
        # Find sentences mentioning connections
        sentences = re.split(r"[.!?]+", desc)
        relevant = [s.strip() for s in sentences if door_patterns.search(s)]
        if relevant:
            snippet = " | ".join(relevant[:3])  # Max 3 sentences
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            lines.append(f"Room {key} ({loc.name}): {snippet}")
    return "\n".join(lines) if lines else "No relevant snippets found."


# ---------------------------------------------------------------------------
# Bidirectional fix
# ---------------------------------------------------------------------------

def _fix_bidirectional(exits: dict[str, dict[str, str]], room_keys: set[str]) -> dict[str, dict[str, str]]:
    """Ensure all connections are bidirectional.

    If A -> east -> B, ensure B -> west -> A (unless direction slot is taken).
    """
    result = {k: dict(v) for k, v in exits.items()}

    for room, room_exits in list(exits.items()):
        for direction, dest in room_exits.items():
            if dest not in room_keys:
                continue
            base_dir = direction.lower().replace("secret_", "")
            opposite = OPPOSITE_DIRS.get(base_dir)
            if not opposite:
                continue
            # Preserve secret_ prefix
            if direction.startswith("secret_"):
                opposite = f"secret_{opposite}"

            dest_exits = result.setdefault(dest, {})
            # Check if dest already has ANY exit back to room
            has_return = any(d == room for d in dest_exits.values())
            if not has_return and opposite not in dest_exits:
                dest_exits[opposite] = room

    return result


# ---------------------------------------------------------------------------
# Diff old vs new exits
# ---------------------------------------------------------------------------

def _diff_exits(
    old_exits: dict[str, dict[str, str]],
    new_exits: dict[str, dict[str, str]],
    changes_summary: list[str] | None = None,
) -> list[ExitChange]:
    """Compute the diff between old and new exit maps."""
    changes: list[ExitChange] = []
    all_rooms = set(old_exits.keys()) | set(new_exits.keys())

    # Index changes_summary by room for reason lookup
    reason_map: dict[str, str] = {}
    for summary in (changes_summary or []):
        reason_map[summary] = summary

    for room in all_rooms:
        old = old_exits.get(room, {})
        new = new_exits.get(room, {})

        # Removed exits
        for direction, dest in old.items():
            if direction not in new:
                # Check if dest moved to a different direction
                new_dir_for_dest = None
                for nd, ndest in new.items():
                    if ndest == dest and nd not in old:
                        new_dir_for_dest = nd
                        break
                if new_dir_for_dest:
                    changes.append(ExitChange(
                        room_key=room,
                        change_type="direction_changed",
                        direction=new_dir_for_dest,
                        destination=dest,
                        old_direction=direction,
                        reason=f"Direction corrected from {direction} to {new_dir_for_dest}",
                    ))
                else:
                    changes.append(ExitChange(
                        room_key=room,
                        change_type="removed",
                        direction=direction,
                        destination=dest,
                        reason=f"Removed: no such connection visible on map",
                    ))
            elif new[direction] != dest:
                # Same direction, different destination
                changes.append(ExitChange(
                    room_key=room,
                    change_type="direction_changed",
                    direction=direction,
                    destination=new[direction],
                    old_destination=dest,
                    reason=f"Destination changed from {dest} to {new[direction]}",
                ))

        # Added exits
        for direction, dest in new.items():
            if direction not in old:
                # Skip if this was already captured as a direction_changed
                already_captured = any(
                    c.room_key == room and c.direction == direction
                    for c in changes
                )
                if not already_captured:
                    changes.append(ExitChange(
                        room_key=room,
                        change_type="added",
                        direction=direction,
                        destination=dest,
                        reason=f"Added: connection visible on map",
                    ))

    return changes


# ---------------------------------------------------------------------------
# Batch rooms for large levels
# ---------------------------------------------------------------------------

def _batch_rooms(room_keys: list[str], batch_size: int = 25, boundary_context: int = 5) -> list[dict]:
    """Split rooms into batches for levels with 40+ rooms.

    Returns list of {"keys": [...], "context_keys": [...]} where context_keys
    are boundary rooms from adjacent batches for overlap.
    """
    # Sort numerically
    sorted_keys = sorted(
        room_keys,
        key=lambda x: (int(re.match(r"\d+", x).group()) if re.match(r"\d+", x) else 999, x),
    )

    if len(sorted_keys) <= batch_size + 10:
        # Small enough for a single batch
        return [{"keys": sorted_keys, "context_keys": []}]

    batches = []
    for i in range(0, len(sorted_keys), batch_size):
        batch_keys = sorted_keys[i : i + batch_size]
        # Add boundary context from adjacent batches
        context_start = max(0, i - boundary_context)
        context_end = min(len(sorted_keys), i + batch_size + boundary_context)
        context_keys = [
            k for k in sorted_keys[context_start:context_end]
            if k not in batch_keys
        ]
        batches.append({"keys": batch_keys, "context_keys": context_keys})

    return batches


def _merge_batch_results(
    batch_exits_list: list[dict[str, dict[str, str]]],
    batches: list[dict],
) -> dict[str, dict[str, str]]:
    """Merge exits from multiple batches, preferring later batches at boundaries."""
    merged: dict[str, dict[str, str]] = {}
    for batch_exits, batch_info in zip(batch_exits_list, batches):
        primary_keys = set(batch_info["keys"])
        for room, room_exits in batch_exits.items():
            if room in primary_keys:
                # Primary room — always use this batch's result
                merged[room] = room_exits
            elif room not in merged:
                # Context room not yet seen — use it
                merged[room] = room_exits
    return merged


# ---------------------------------------------------------------------------
# Main reconciliation function
# ---------------------------------------------------------------------------

async def reconcile_connections(
    db: AsyncSession,
    module_id: UUID,
    auto_apply: bool = False,
) -> ReconciliationResult:
    """Run the connection reconciliation pass.

    Sends map image(s) + complete current state to vision AI for a
    definitive answer, able to add, remove, and correct connections.

    Args:
        db: Database session
        module_id: Adventure module ID
        auto_apply: If True, write corrected exits to DB

    Returns:
        ReconciliationResult with authoritative exits and change list
    """
    from app.domains.adventures.map_corridor_discovery import (
        _assign_rooms_to_levels,
        _call_vision_llm,
        _format_room_list,
        get_full_page_map_images,
        load_map_image_as_base64,
    )

    result = ReconciliationResult()

    # --- Step 1: Load module + locations + map images ---
    mod_result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = mod_result.scalar_one_or_none()
    if not module:
        result.errors.append("Module not found")
        return result

    loc_result = await db.execute(
        select(AdventureLocation)
        .where(AdventureLocation.module_id == module_id)
    )
    all_locations = {loc.location_key: loc for loc in loc_result.scalars().all()}
    room_keys = set(all_locations.keys())
    result.rooms_processed = len(room_keys)

    if not all_locations:
        result.errors.append("No locations found for module")
        return result

    # Load map images
    maps = []
    if module.pdf_document_id:
        maps = await get_full_page_map_images(db, module.pdf_document_id)

    if not maps:
        result.errors.append("No map images found — cannot reconcile without maps")
        return result

    loaded_images: list[dict[str, Any] | None] = []
    for map_img in maps:
        img_block = load_map_image_as_base64(map_img.image_path)
        loaded_images.append(img_block)
        if not img_block:
            result.errors.append(f"Failed to load map image: {map_img.image_path}")

    logger.info(f"[reconcile] Loaded {len(maps)} map(s), {len(all_locations)} locations")

    # --- Step 2: Build current exits from DB ---
    old_exits: dict[str, dict[str, str]] = {}
    for key, loc in all_locations.items():
        if loc.exits and isinstance(loc.exits, dict):
            old_exits[key] = dict(loc.exits)
        else:
            old_exits[key] = {}

    # --- Step 3: Detect disconnected clusters ---
    clusters = _find_clusters(room_keys, old_exits)
    result.disconnected_clusters = len(clusters)
    cluster_info = _format_clusters(clusters)
    logger.info(f"[reconcile] Found {len(clusters)} cluster(s)")

    # --- Step 4: Assign rooms to levels ---
    rooms_dict = {
        key: {"name": loc.name, "dungeon_level": loc.dungeon_level or 1}
        for key, loc in all_locations.items()
    }
    level_rooms = _assign_rooms_to_levels(rooms_dict, maps)

    # --- Step 5: Per-level reconciliation ---
    all_new_exits: dict[str, dict[str, str]] = {}
    changes_summary_all: list[str] = []

    for level_idx, map_img in enumerate(maps):
        img_block = loaded_images[level_idx]
        if not img_block:
            logger.warning(f"[reconcile] Skipping level {level_idx + 1}: no image")
            continue

        level_keys = level_rooms.get(level_idx, list(room_keys))
        if not level_keys:
            continue

        # Check if we need batching
        batches = _batch_rooms(level_keys)
        batch_exits_list: list[dict[str, dict[str, str]]] = []

        for batch_idx, batch_info in enumerate(batches):
            batch_keys = batch_info["keys"]
            context_keys = batch_info["context_keys"]
            all_batch_keys = batch_keys + context_keys

            # Build level-specific exits
            level_exits = {k: old_exits.get(k, {}) for k in all_batch_keys}

            # Validation issues for this batch
            batch_room_keys = set(all_batch_keys)
            validation_issues = _format_validation_issues(level_exits, batch_room_keys)

            # Room snippets
            room_snippets = _format_room_snippets(all_locations, all_batch_keys)

            # Room list
            room_list = _format_room_list(rooms_dict, all_batch_keys)

            batch_label = ""
            if len(batches) > 1:
                batch_label = f" (batch {batch_idx + 1}/{len(batches)})"

            prompt = RECONCILIATION_PROMPT.format(
                room_list=room_list,
                current_exits=_format_current_exits(level_exits),
                validation_issues=validation_issues,
                cluster_info=cluster_info,
                room_snippets=room_snippets,
            )

            logger.info(
                f"[reconcile] Level {level_idx + 1}{batch_label}: "
                f"sending {len(batch_keys)} rooms (+{len(context_keys)} context) to vision AI"
            )
            response = await _call_vision_llm([img_block], prompt)

            if not response or "exits" not in response:
                result.errors.append(f"Level {level_idx + 1}{batch_label}: no valid response from vision AI")
                # Fall back to old exits for this batch
                batch_exits_list.append({k: old_exits.get(k, {}) for k in batch_keys})
                continue

            # Parse exits, filter to known rooms
            batch_exits: dict[str, dict[str, str]] = {}
            for room_key, room_exits_raw in response["exits"].items():
                # Normalize room key
                key_match = re.match(r"(\d+[a-z]?)", str(room_key))
                normalized_key = key_match.group(1) if key_match else str(room_key)

                if normalized_key not in room_keys:
                    continue

                # Filter exits to known destinations
                clean_exits: dict[str, str] = {}
                for direction, dest in room_exits_raw.items():
                    dest_str = str(dest).strip()
                    dest_match = re.match(r"(\d+[a-z]?)", dest_str)
                    if dest_match:
                        dest_key = dest_match.group(1)
                        clean_exits[direction.lower()] = dest_key
                    elif dest_str.lower() in ("none", ""):
                        continue
                    else:
                        logger.debug(f"[reconcile] Skipping non-numeric dest: Room {normalized_key} -> {direction} -> {dest_str}")

                batch_exits[normalized_key] = clean_exits

            batch_exits_list.append(batch_exits)

            # Collect changes summary
            if "changes_summary" in response:
                changes_summary_all.extend(response["changes_summary"])

            confidence = response.get("confidence", "medium")
            if result.confidence == "medium" and confidence == "high":
                result.confidence = "high"
            elif confidence == "low":
                result.confidence = "low"

        # Merge batches for this level
        if len(batches) > 1:
            level_exits_merged = _merge_batch_results(batch_exits_list, batches)
        elif batch_exits_list:
            level_exits_merged = batch_exits_list[0]
        else:
            level_exits_merged = {}

        all_new_exits.update(level_exits_merged)

    # --- Step 6: Cross-level connections (if 2+ maps) ---
    if len(maps) >= 2:
        valid_images = [img for img in loaded_images if img is not None]
        if len(valid_images) >= 2:
            level1_keys = level_rooms.get(0, [])
            level2_keys = level_rooms.get(1, [])

            # Gather current cross-level connections
            cross_current = []
            for key in level1_keys:
                for direction, dest in old_exits.get(key, {}).items():
                    if dest in set(level2_keys):
                        cross_current.append(f"Room {key} -> {direction} -> Room {dest}")
            for key in level2_keys:
                for direction, dest in old_exits.get(key, {}).items():
                    if dest in set(level1_keys):
                        cross_current.append(f"Room {key} -> {direction} -> Room {dest}")

            prompt = CROSS_LEVEL_RECONCILIATION_PROMPT.format(
                level1_num=1,
                level2_num=2,
                level1_rooms=_format_room_list(rooms_dict, level1_keys),
                level2_rooms=_format_room_list(rooms_dict, level2_keys),
                current_cross_level="\n".join(cross_current) if cross_current else "None found yet.",
            )

            logger.info("[reconcile] Analyzing cross-level connections...")
            response = await _call_vision_llm(valid_images[:2], prompt)

            if response and "cross_level_exits" in response:
                for conn in response["cross_level_exits"]:
                    from_room = str(conn.get("from_room", "")).strip()
                    to_room = str(conn.get("to_room", "")).strip()
                    direction = str(conn.get("direction", "")).strip().lower()

                    from_match = re.match(r"(\d+[a-z]?)", from_room)
                    to_match = re.match(r"(\d+[a-z]?)", to_room)
                    if not from_match or not to_match:
                        continue

                    from_key = from_match.group(1)
                    to_key = to_match.group(1)

                    if from_key not in room_keys or to_key not in room_keys:
                        continue

                    # Add cross-level connection
                    room_exits = all_new_exits.setdefault(from_key, {})
                    if direction not in room_exits:
                        room_exits[direction] = to_key

                if "changes_summary" in response:
                    changes_summary_all.extend(response["changes_summary"])

    # --- Step 7: Ensure all rooms are present in new exits ---
    for key in room_keys:
        if key not in all_new_exits:
            # Room wasn't in any vision response — keep old exits
            all_new_exits[key] = old_exits.get(key, {})

    # --- Step 8: Bidirectional fix ---
    all_new_exits = _fix_bidirectional(all_new_exits, room_keys)

    # --- Step 9: Diff against old exits ---
    result.authoritative_exits = all_new_exits
    result.changes = _diff_exits(old_exits, all_new_exits, changes_summary_all)
    result.confidence_notes = "; ".join(changes_summary_all[:10]) if changes_summary_all else ""

    # Recount clusters after reconciliation
    new_clusters = _find_clusters(room_keys, all_new_exits)
    logger.info(
        f"[reconcile] Reconciliation complete: {len(result.changes)} changes, "
        f"clusters {len(clusters)} -> {len(new_clusters)}"
    )

    # --- Step 10: Apply to DB if requested ---
    if auto_apply and result.changes:
        for key, new_exits in all_new_exits.items():
            loc = all_locations.get(key)
            if not loc:
                continue
            old = old_exits.get(key, {})
            if new_exits != old:
                loc.exits = new_exits
        await db.flush()
        logger.info(f"[reconcile] Applied {len(result.changes)} exit changes to DB")

    return result
