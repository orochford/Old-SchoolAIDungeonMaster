"""Pass 2.5: Map-based exit validation using vision AI."""

import math
import logging
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy import select

from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.adventures.extraction_context import (
    ExtractionContext, MapPosition, MapAnalysis
)
from app.domains.adventures.passes.base import BasePass
from app.domains.sourcebooks.models import ExtractedImage
from app.domains.adventures.map_corridor_discovery import (
    get_full_page_map_images,
    load_map_image_as_base64,
    discover_corridors_from_maps,
    merge_map_connections_into_exits,
)

logger = logging.getLogger(__name__)

MAP_ANALYSIS_PROMPT = """Analyze this dungeon map to identify room positions.

## ROOMS TO FIND
{room_list}

## TASK
For each room number you can identify on the map:
1. Report its position as x,y percentages (0-100) where 0,0 is top-left
2. Rate confidence (0.0-1.0) in the identification

## OUTPUT FORMAT (JSON only)
{{
  "rooms": [
    {{"location_key": "1", "x": 25, "y": 15, "confidence": 0.95}},
    {{"location_key": "2", "x": 25, "y": 35, "confidence": 0.85}}
  ],
  "not_found": ["3a"],
  "map_orientation": "north_up"
}}
"""


class MapValidationPass(BasePass):
    """Pass 2.5: Validate exits using map images."""

    name = "pass2_5_map_validation"
    description = "Validate exit directions against map images"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        updates = ExtractionContext()

        # Get map images for this module (shared filtering + dedup)
        maps = await get_full_page_map_images(self.db, module.pdf_document_id)
        if not maps:
            self._log("No map images found, skipping map validation")
            return updates

        self._log(f"Analyzing {len(maps)} map image(s)...")

        # Build room list from context
        room_list = "\n".join([
            f"- Room {key}: {loc.name}"
            for key, loc in context.locations.items()
        ])

        # Analyze each map
        all_positions: Dict[str, MapPosition] = {}

        for map_img in maps:
            positions = await self._analyze_map(map_img, room_list)
            # Merge, preferring higher confidence
            for key, pos in positions.items():
                if key not in all_positions or pos.confidence > all_positions[key].confidence:
                    all_positions[key] = pos

        if not all_positions:
            self._log("Could not identify any rooms on maps")
            return updates

        self._log(f"Identified {len(all_positions)} rooms on map(s)")

        # Derive spatial relationships
        adjacencies = self._derive_directions(all_positions)

        # Build map analysis result
        map_analysis = MapAnalysis(
            positions=all_positions,
            adjacencies=adjacencies,
            unmapped_rooms=[k for k in context.locations if k not in all_positions],
        )
        updates.map_analysis = map_analysis

        # Validate and correct exits
        corrections = await self._validate_and_correct_exits(module.id, context, map_analysis)
        self._log(f"Corrected {corrections} exit direction(s)")

        # --- Corridor discovery via vision AI ---
        rooms_dict = {
            key: loc for key, loc in context.locations.items()
        }
        corridor_result = await discover_corridors_from_maps(
            self.db, module.pdf_document_id, rooms_dict
        )

        if corridor_result.connections:
            self._log(
                f"Discovered {len(corridor_result.connections)} corridor connections "
                f"from {corridor_result.maps_analyzed} map(s)"
            )

            # Build existing exits dict
            existing_exits: Dict[str, Dict[str, str]] = {}
            for key, loc in context.locations.items():
                if loc.exits and isinstance(loc.exits, dict):
                    existing_exits[key] = dict(loc.exits)
                else:
                    existing_exits[key] = {}

            # Merge map connections
            merged_exits = merge_map_connections_into_exits(
                corridor_result.connections, existing_exits
            )

            # Update context and DB with merged exits
            corridors_added = 0
            for key, new_exits in merged_exits.items():
                old_exits = existing_exits.get(key, {})
                if new_exits != old_exits:
                    # Update context
                    if key in context.locations:
                        context.locations[key].exits = new_exits

                    # Update database
                    result = await self.db.execute(
                        select(AdventureLocation)
                        .where(AdventureLocation.module_id == module.id)
                        .where(AdventureLocation.location_key == key)
                    )
                    db_loc = result.scalar_one_or_none()
                    if db_loc:
                        db_loc.exits = new_exits
                        corridors_added += len(new_exits) - len(old_exits)

            await self.db.flush()
            self._log(f"Added {corridors_added} new corridor exit(s) to rooms")

            # Store in map analysis
            map_analysis.discovered_corridors = [
                {
                    "from_room": c.from_room,
                    "to_room": c.to_room,
                    "direction": c.direction,
                    "connection_type": c.connection_type,
                    "confidence": c.confidence,
                }
                for c in corridor_result.connections
            ]
        else:
            self._log("No corridor connections discovered from maps")

        if corridor_result.errors:
            for err in corridor_result.errors:
                self._log(f"  Warning: {err}")

        return updates

    async def _analyze_map(self, map_img: ExtractedImage, room_list: str) -> Dict[str, MapPosition]:
        """Analyze a single map image using vision AI."""
        from app.config import settings

        # Load image as base64 (with downscaling)
        image_data = load_map_image_as_base64(map_img.image_path)
        if not image_data:
            self._log(f"Could not load map image: {map_img.image_path}")
            return {}

        prompt = MAP_ANALYSIS_PROMPT.format(room_list=room_list)

        try:
            if settings.processing_provider == "openai":
                content = await self._analyze_map_openai(image_data, prompt, settings)
            else:
                content = await self._analyze_map_claude(image_data, prompt, settings)

            result = self._extract_json(content, "map_analysis")

            if not result:
                return {}

            positions = {}
            for room in result.get("rooms", []):
                key = str(room.get("location_key", ""))
                if key and room.get("confidence", 0) > 0.5:
                    positions[key] = MapPosition(
                        location_key=key,
                        map_page=map_img.page_number or 1,
                        x=room.get("x", 50) / 100.0,
                        y=room.get("y", 50) / 100.0,
                        confidence=room.get("confidence", 0),
                        found_on_map=True,
                    )

            return positions

        except Exception as e:
            self._log(f"Map analysis failed: {e}")
            return {}

    async def _analyze_map_openai(self, image_data: Dict, prompt: str, settings) -> str:
        """Call OpenAI vision API for map analysis."""
        import openai

        # Convert Claude image format to OpenAI format
        media_type = image_data["source"]["media_type"]
        b64_data = image_data["source"]["data"]
        data_url = f"data:{media_type};base64,{b64_data}"

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ]
            }]
        )
        return response.choices[0].message.content or ""

    async def _analyze_map_claude(self, image_data: Dict, prompt: str, settings) -> str:
        """Call Claude vision API for map analysis."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    image_data,
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        return response.content[0].text if response.content else ""

    def _derive_directions(self, positions: Dict[str, MapPosition]) -> Dict[str, Dict[str, str]]:
        """Derive cardinal directions between rooms based on positions."""
        adjacencies = {}

        for key1, pos1 in positions.items():
            if not pos1.found_on_map:
                continue
            adjacencies[key1] = {}

            for key2, pos2 in positions.items():
                if key1 == key2 or not pos2.found_on_map:
                    continue

                dx = pos2.x - pos1.x
                dy = pos2.y - pos1.y
                direction = self._vector_to_direction(dx, dy)
                adjacencies[key1][key2] = direction

        return adjacencies

    def _vector_to_direction(self, dx: float, dy: float) -> str:
        """Convert vector to cardinal direction. Map coords: y increases downward."""
        angle = math.degrees(math.atan2(-dy, dx))  # Negate dy for map coords
        if angle < 0:
            angle += 360

        # 8 directions with 45-degree sectors
        if angle >= 337.5 or angle < 22.5:
            return "east"
        elif angle < 67.5:
            return "northeast"
        elif angle < 112.5:
            return "north"
        elif angle < 157.5:
            return "northwest"
        elif angle < 202.5:
            return "west"
        elif angle < 247.5:
            return "southwest"
        elif angle < 292.5:
            return "south"
        else:
            return "southeast"

    async def _validate_and_correct_exits(
        self,
        module_id: UUID,
        context: ExtractionContext,
        map_analysis: MapAnalysis,
    ) -> int:
        """Validate and correct exits against map-derived directions."""
        corrections = 0

        for loc_key, loc_details in context.locations.items():
            if not loc_details.exits:
                continue

            # Skip rooms not on map
            if loc_key not in map_analysis.positions:
                continue

            map_directions = map_analysis.adjacencies.get(loc_key, {})
            new_exits = dict(loc_details.exits)
            changed = False

            for exit_dir, dest_key in list(loc_details.exits.items()):
                # Skip special exits
                if any(x in exit_dir.lower() for x in ['secret', 'up', 'down', 'stairs']):
                    continue

                map_dir = map_directions.get(dest_key)
                if map_dir and map_dir != exit_dir.lower():
                    self._log(f"  {loc_key}->{dest_key}: {exit_dir} -> {map_dir}")
                    del new_exits[exit_dir]
                    new_exits[map_dir] = dest_key
                    changed = True
                    corrections += 1

            if changed:
                loc_details.exits = new_exits
                # Update database
                result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module_id)
                    .where(AdventureLocation.location_key == loc_key)
                )
                db_loc = result.scalar_one_or_none()
                if db_loc:
                    db_loc.exits = new_exits

        await self.db.flush()
        return corrections
