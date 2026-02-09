"""Map-based corridor discovery using vision AI.

Analyzes dungeon map images to discover corridor connections between rooms
that are only visible on the map (not described in text). Used by both
Pass 2.5 (pipeline) and the extract-missing-rooms endpoint.
"""

import base64
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sourcebooks.models import ExtractedImage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MapConnection:
    """A corridor/passage connection discovered from a map image."""
    from_room: str
    to_room: str
    direction: str           # north, south, east, west, stairs_down, etc.
    connection_type: str     # corridor, door, secret_door, stairs
    confidence: float = 0.8


@dataclass
class CorridorDiscoveryResult:
    """Results of map-based corridor discovery."""
    connections: List[MapConnection] = field(default_factory=list)
    maps_analyzed: int = 0
    cross_level_connections: List[MapConnection] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Vision prompts
# ---------------------------------------------------------------------------

PER_LEVEL_PROMPT = """Analyze this dungeon map image to identify ALL corridor connections between rooms.

## ROOMS ON THIS LEVEL
{room_list}

## TASK
Trace every corridor, hallway, passage, doorway, and connection visible on this map.
For each connection, report:
- from_room: the room number where the connection starts
- to_room: the room number where the connection leads
- direction: the cardinal direction from from_room to to_room (north, south, east, west, northeast, northwest, southeast, southwest)
- connection_type: one of "corridor", "door", "secret_door", "stairs", "passage"
- confidence: how confident you are (0.0 to 1.0)

IMPORTANT:
- Report BOTH directions for each connection (e.g. room 1 east to room 2 AND room 2 west to room 1)
- Include connections through corridors/hallways (rooms don't need to be directly adjacent)
- Look for secret doors (usually marked with 'S' or a dotted line)
- Look for one-way doors or special passages
- Only report connections you can actually trace on the map

## OUTPUT FORMAT (JSON only)
{{
  "connections": [
    {{"from_room": "1", "to_room": "2", "direction": "east", "connection_type": "corridor", "confidence": 0.9}},
    {{"from_room": "2", "to_room": "1", "direction": "west", "connection_type": "corridor", "confidence": 0.9}}
  ]
}}
"""

CROSS_LEVEL_PROMPT = """Analyze these dungeon map images to identify connections BETWEEN levels (stairs, chutes, ladders, etc.).

## LEVEL 1 ROOMS
{level1_rooms}

## LEVEL 2 ROOMS
{level2_rooms}

## TASK
Look for inter-level connections: stairs going up/down, chutes, ladders, trapdoors, or any
passage that connects rooms on different levels.

For each connection, report:
- from_room: the room number on one level
- to_room: the room number on the other level
- direction: "stairs_down", "stairs_up", "chute_down", "ladder_up", "trapdoor_down", etc.
- connection_type: "stairs"
- confidence: how confident you are (0.0 to 1.0)

Report BOTH directions (e.g. stairs_down from room 39 to 40 AND stairs_up from room 40 to 39).

## OUTPUT FORMAT (JSON only)
{{
  "connections": [
    {{"from_room": "39", "to_room": "40", "direction": "stairs_down", "connection_type": "stairs", "confidence": 0.85}},
    {{"from_room": "40", "to_room": "39", "direction": "stairs_up", "connection_type": "stairs", "confidence": 0.85}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

async def get_full_page_map_images(
    db: AsyncSession,
    document_id: UUID,
) -> List[ExtractedImage]:
    """Get full-page map images for a document, deduplicated by page number.

    Filters to is_full_page=True only (eliminates text pages) and deduplicates
    since each page can appear twice in the DB.
    """
    result = await db.execute(
        select(ExtractedImage)
        .where(ExtractedImage.document_id == document_id)
        .where(ExtractedImage.image_type == "map")
        .where(ExtractedImage.is_full_page.is_(True))
        .order_by(ExtractedImage.page_number)
    )
    all_maps = list(result.scalars().all())

    # Deduplicate by page_number — keep first occurrence
    seen_pages: set[int] = set()
    deduped: List[ExtractedImage] = []
    for img in all_maps:
        page = img.page_number or 0
        if page not in seen_pages:
            seen_pages.add(page)
            deduped.append(img)

    return deduped


def load_map_image_as_base64(
    image_path: str,
    max_dimension: int = 2048,
) -> Optional[Dict[str, Any]]:
    """Load a map image, downscale if needed, and return a Claude API content block.

    Downscales to max_dimension using Pillow to save vision tokens (~75% savings
    vs full 2550px images).
    """
    import os

    if not image_path or not os.path.exists(image_path):
        logger.warning(f"Map image not found: {image_path}")
        return None

    ext = os.path.splitext(image_path)[1].lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "image/png")

    try:
        from PIL import Image

        img = Image.open(image_path)
        original_size = img.size

        # Downscale if either dimension exceeds max
        if max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
            logger.info(
                f"Downscaled map {original_size} -> {img.size} "
                f"(max_dimension={max_dimension})"
            )

        # Save to bytes
        buf = io.BytesIO()
        save_format = "PNG" if ext == ".png" else "JPEG"
        img.save(buf, format=save_format)
        image_data = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            }
        }

    except ImportError:
        # Pillow not available — fall back to raw load (no downscaling)
        logger.warning("Pillow not available, loading image without downscaling")
        from app.llm.client import load_image_as_base64
        return load_image_as_base64(image_path)

    except Exception as e:
        logger.error(f"Failed to load map image {image_path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Vision LLM call
# ---------------------------------------------------------------------------

async def _call_vision_llm(
    image_blocks: List[Dict[str, Any]],
    prompt: str,
) -> Optional[Dict[str, Any]]:
    """Call vision AI with map images and parse JSON response.

    Respects processing_provider setting to use either OpenAI or Claude.
    """
    from app.config import settings

    try:
        if settings.processing_provider == "openai":
            text = await _call_vision_openai(image_blocks, prompt, settings)
        else:
            text = await _call_vision_claude(image_blocks, prompt, settings)

        if not text:
            return None

        return _extract_json(text)

    except Exception as e:
        logger.error(f"Vision LLM call failed: {e}")
        return None


async def _call_vision_openai(
    image_blocks: List[Dict[str, Any]],
    prompt: str,
    settings,
) -> str:
    """Call OpenAI vision API with map images."""
    import openai

    content: List[Dict[str, Any]] = []
    for img_block in image_blocks:
        # Convert Claude image format to OpenAI format
        media_type = img_block["source"]["media_type"]
        b64_data = img_block["source"]["data"]
        data_url = f"data:{media_type};base64,{b64_data}"
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    content.append({"type": "text", "text": prompt})

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=8192,
        messages=[{"role": "user", "content": content}],
    )
    return response.choices[0].message.content or ""


async def _call_vision_claude(
    image_blocks: List[Dict[str, Any]],
    prompt: str,
    settings,
) -> str:
    """Call Claude vision API with map images."""
    import anthropic

    content: List[Dict[str, Any]] = []
    for img_block in image_blocks:
        content.append(img_block)
    content.append({"type": "text", "text": prompt})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        messages=[{"role": "user", "content": content}],
    )

    if response.content:
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text
    return ""


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response text."""
    content = content.strip()

    # Remove markdown code blocks
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Find JSON object with balanced braces
    brace_start = content.find('{')
    if brace_start != -1:
        depth = 0
        for i, c in enumerate(content[brace_start:], start=brace_start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[brace_start:i + 1])
                    except json.JSONDecodeError:
                        pass
                    break

    return None


# ---------------------------------------------------------------------------
# Corridor discovery
# ---------------------------------------------------------------------------

def _assign_rooms_to_levels(
    rooms: Dict[str, Any],
    maps: List[ExtractedImage],
) -> Dict[int, List[str]]:
    """Assign rooms to map levels based on dungeon_level or room numbering.

    Returns {level_index: [room_keys]} where level_index corresponds to
    the index in the maps list (0 = first map, 1 = second map, etc.).
    """
    levels: Dict[int, List[str]] = {}

    for key, room_data in rooms.items():
        # Determine dungeon level from room data
        dungeon_level = 1
        if isinstance(room_data, dict):
            dungeon_level = room_data.get('dungeon_level', 1)
        elif hasattr(room_data, 'dungeon_level'):
            dungeon_level = room_data.dungeon_level or 1

        # Map dungeon_level to map index (level 1 -> index 0, level 2 -> index 1)
        map_idx = min(dungeon_level - 1, len(maps) - 1)
        map_idx = max(0, map_idx)

        levels.setdefault(map_idx, []).append(key)

    return levels


def _format_room_list(rooms: Dict[str, Any], keys: List[str]) -> str:
    """Format a subset of rooms as a numbered list for the vision prompt."""
    lines = []
    for key in sorted(keys, key=lambda x: (int(re.match(r'\d+', x).group()) if re.match(r'\d+', x) else 999, x)):
        name = "Unknown"
        if isinstance(rooms[key], dict):
            name = rooms[key].get('name', 'Unknown')
        elif hasattr(rooms[key], 'name'):
            name = rooms[key].name or 'Unknown'
        lines.append(f"- Room {key}: {name}")
    return "\n".join(lines)


async def discover_corridors_from_maps(
    db: AsyncSession,
    document_id: UUID,
    rooms: Dict[str, Any],
) -> CorridorDiscoveryResult:
    """Main entry point: analyze map images to discover corridor connections.

    Args:
        db: Database session
        document_id: PDF document ID to find map images for
        rooms: Dict of room_key -> room data (AdventureLocation or dict with 'name', 'dungeon_level')

    Returns:
        CorridorDiscoveryResult with discovered connections
    """
    result = CorridorDiscoveryResult()

    # Get map images
    maps = await get_full_page_map_images(db, document_id)
    if not maps:
        logger.info("No full-page map images found for corridor discovery")
        return result

    logger.info(f"Analyzing {len(maps)} map image(s) for corridor discovery")

    # Load all map images
    loaded_images: List[Optional[Dict[str, Any]]] = []
    for map_img in maps:
        img_block = load_map_image_as_base64(map_img.image_path)
        loaded_images.append(img_block)
        if not img_block:
            result.errors.append(f"Failed to load map image: {map_img.image_path}")

    # Assign rooms to levels
    level_rooms = _assign_rooms_to_levels(rooms, maps)

    # --- Per-level analysis ---
    for level_idx, map_img in enumerate(maps):
        img_block = loaded_images[level_idx]
        if not img_block:
            continue

        room_keys = level_rooms.get(level_idx, [])
        if not room_keys:
            # If no rooms assigned to this level, try all rooms
            room_keys = list(rooms.keys())

        room_list = _format_room_list(rooms, room_keys)
        prompt = PER_LEVEL_PROMPT.format(room_list=room_list)

        logger.info(f"Analyzing level {level_idx + 1} map ({len(room_keys)} rooms)...")
        response = await _call_vision_llm([img_block], prompt)

        if response and "connections" in response:
            for conn_data in response["connections"]:
                conn = _parse_connection(conn_data)
                if conn and conn.confidence >= 0.6:
                    result.connections.append(conn)

            logger.info(
                f"Level {level_idx + 1}: found {len(response['connections'])} "
                f"connections ({len([c for c in result.connections])} above threshold)"
            )
        else:
            result.errors.append(f"No connections found for level {level_idx + 1} map")

        result.maps_analyzed += 1

    # --- Cross-level analysis (if multiple maps) ---
    if len(maps) >= 2:
        valid_images = [img for img in loaded_images if img is not None]
        if len(valid_images) >= 2:
            level1_keys = level_rooms.get(0, [])
            level2_keys = level_rooms.get(1, [])

            prompt = CROSS_LEVEL_PROMPT.format(
                level1_rooms=_format_room_list(rooms, level1_keys),
                level2_rooms=_format_room_list(rooms, level2_keys),
            )

            logger.info("Analyzing cross-level connections...")
            response = await _call_vision_llm(valid_images[:2], prompt)

            if response and "connections" in response:
                for conn_data in response["connections"]:
                    conn = _parse_connection(conn_data)
                    if conn and conn.confidence >= 0.6:
                        result.cross_level_connections.append(conn)
                        result.connections.append(conn)

                logger.info(
                    f"Cross-level: found {len(response['connections'])} connections"
                )

    # Deduplicate connections
    result.connections = _deduplicate_connections(result.connections)
    result.cross_level_connections = _deduplicate_connections(result.cross_level_connections)

    logger.info(
        f"Corridor discovery complete: {len(result.connections)} connections "
        f"from {result.maps_analyzed} maps"
    )

    return result


def _parse_connection(data: Dict[str, Any]) -> Optional[MapConnection]:
    """Parse a connection dict from LLM response into a MapConnection."""
    from_room = str(data.get("from_room", "")).strip()
    to_room = str(data.get("to_room", "")).strip()
    direction = str(data.get("direction", "")).strip().lower()
    conn_type = str(data.get("connection_type", "corridor")).strip().lower()
    confidence = float(data.get("confidence", 0.8))

    if not from_room or not to_room or not direction:
        return None

    # Normalize room keys to just numbers
    from_match = re.match(r'^(\d+[a-z]?)', from_room)
    to_match = re.match(r'^(\d+[a-z]?)', to_room)
    if not from_match or not to_match:
        return None

    return MapConnection(
        from_room=from_match.group(1),
        to_room=to_match.group(1),
        direction=direction,
        connection_type=conn_type,
        confidence=confidence,
    )


def _deduplicate_connections(connections: List[MapConnection]) -> List[MapConnection]:
    """Remove duplicate connections, keeping highest confidence."""
    seen: Dict[tuple, MapConnection] = {}
    for conn in connections:
        key = (conn.from_room, conn.to_room, conn.direction)
        if key not in seen or conn.confidence > seen[key].confidence:
            seen[key] = conn
    return list(seen.values())


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def merge_map_connections_into_exits(
    connections: List[MapConnection],
    existing_exits: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    """Merge discovered map connections into existing room exits.

    Map connections are additive only:
    - Skip if destination already reachable from that room via any direction
    - Skip if direction already occupied by a different destination
    - Never remove text-derived exits

    Args:
        connections: List of MapConnection from corridor discovery
        existing_exits: Dict of {room_key: {direction: destination_key}}

    Returns:
        Updated exits dict (new dict, does not mutate input)
    """
    merged = {k: dict(v) for k, v in existing_exits.items()}
    added_count = 0

    for conn in connections:
        if conn.confidence < 0.6:
            continue

        room_exits = merged.get(conn.from_room, {})

        # Skip if destination already reachable from this room
        if conn.to_room in room_exits.values():
            continue

        # Skip if direction already occupied by a different destination
        if conn.direction in room_exits:
            continue

        # Add the connection
        if conn.from_room not in merged:
            merged[conn.from_room] = {}
        merged[conn.from_room][conn.direction] = conn.to_room
        added_count += 1

    logger.info(f"Merge: added {added_count} map connections to exits")
    return merged
