"""Service for managing dungeon maps with fog of war."""

import logging
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.domains.journal.models import DungeonMap

logger = logging.getLogger(__name__)


class MapService:
    """Manage dungeon maps, fog of war, and player positioning."""

    # Default symbols for map rendering
    FOG_SYMBOL = '?'
    PLAYER_SYMBOL = '@'
    EMPTY_SYMBOL = '.'

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_map(
        self,
        campaign_id: UUID,
        name: str,
        map_data: str,
        location_id: Optional[UUID] = None,
    ) -> DungeonMap:
        """
        Create a new dungeon map.

        map_data should be a multi-line ASCII string representing the map.
        """
        # Calculate dimensions
        lines = map_data.strip().split('\n')
        height = len(lines)
        width = max(len(line) for line in lines) if lines else 0

        # Pad lines to consistent width
        padded_lines = [line.ljust(width) for line in lines]
        normalized_map_data = '\n'.join(padded_lines)

        dungeon_map = DungeonMap(
            campaign_id=campaign_id,
            location_id=location_id,
            name=name,
            map_data=normalized_map_data,
            width=width,
            height=height,
            revealed_cells=[],
            markers=[],
            player_x=None,
            player_y=None,
            is_active=False,
        )

        self.db.add(dungeon_map)
        await self.db.flush()
        await self.db.refresh(dungeon_map)

        return dungeon_map

    async def get_active_map(
        self,
        campaign_id: UUID
    ) -> Optional[DungeonMap]:
        """Get the currently active map for a campaign."""
        result = await self.db.execute(
            select(DungeonMap)
            .where(
                and_(
                    DungeonMap.campaign_id == campaign_id,
                    DungeonMap.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_map(
        self,
        map_id: UUID
    ) -> Optional[DungeonMap]:
        """Get a specific map by ID."""
        result = await self.db.execute(
            select(DungeonMap).where(DungeonMap.id == map_id)
        )
        return result.scalar_one_or_none()

    async def set_active_map(
        self,
        campaign_id: UUID,
        map_id: UUID
    ) -> bool:
        """Set a map as the active map for a campaign."""
        # Deactivate all other maps
        result = await self.db.execute(
            select(DungeonMap).where(DungeonMap.campaign_id == campaign_id)
        )
        maps = list(result.scalars().all())

        for m in maps:
            m.is_active = (m.id == map_id)

        await self.db.flush()
        return True

    async def update_player_position(
        self,
        map_id: UUID,
        x: int,
        y: int,
        reveal_radius: int = 2,
    ) -> Dict[str, Any]:
        """
        Move the player to a new position and reveal nearby cells.

        Returns the updated map state including newly revealed cells.
        """
        dungeon_map = await self.get_map(map_id)
        if not dungeon_map:
            return {"error": "Map not found"}

        # Validate position is within bounds
        if x < 0 or x >= dungeon_map.width or y < 0 or y >= dungeon_map.height:
            return {"error": f"Position ({x}, {y}) out of bounds"}

        old_x, old_y = dungeon_map.player_x, dungeon_map.player_y

        # Update position
        dungeon_map.player_x = x
        dungeon_map.player_y = y

        # Reveal cells within radius
        newly_revealed = await self.reveal_radius(map_id, x, y, reveal_radius)

        await self.db.flush()

        return {
            "success": True,
            "old_position": {"x": old_x, "y": old_y} if old_x is not None else None,
            "new_position": {"x": x, "y": y},
            "newly_revealed_count": len(newly_revealed),
            "total_revealed": len(dungeon_map.revealed_cells),
        }

    async def reveal_radius(
        self,
        map_id: UUID,
        center_x: int,
        center_y: int,
        radius: int = 2,
    ) -> List[List[int]]:
        """
        Reveal all cells within a radius of the given position.

        Returns list of newly revealed cells.
        """
        dungeon_map = await self.get_map(map_id)
        if not dungeon_map:
            return []

        revealed = set(tuple(cell) for cell in (dungeon_map.revealed_cells or []))
        newly_revealed = []

        # Reveal cells in a square pattern (could be changed to circular)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = center_x + dx, center_y + dy

                # Check bounds
                if 0 <= nx < dungeon_map.width and 0 <= ny < dungeon_map.height:
                    cell = (nx, ny)
                    if cell not in revealed:
                        revealed.add(cell)
                        newly_revealed.append([nx, ny])

        # Update revealed cells
        dungeon_map.revealed_cells = [list(cell) for cell in revealed]
        await self.db.flush()

        return newly_revealed

    async def add_marker(
        self,
        map_id: UUID,
        x: int,
        y: int,
        symbol: str,
        label: str,
        marker_type: str = "generic",
    ) -> Dict[str, Any]:
        """Add a marker to the map."""
        import uuid

        dungeon_map = await self.get_map(map_id)
        if not dungeon_map:
            return {"error": "Map not found"}

        marker = {
            "id": str(uuid.uuid4()),
            "x": x,
            "y": y,
            "symbol": symbol,
            "label": label,
            "type": marker_type,
        }

        markers = list(dungeon_map.markers or [])
        markers.append(marker)
        dungeon_map.markers = markers

        await self.db.flush()

        return {
            "success": True,
            "marker": marker,
        }

    async def remove_marker(
        self,
        map_id: UUID,
        marker_id: str,
    ) -> bool:
        """Remove a marker from the map."""
        dungeon_map = await self.get_map(map_id)
        if not dungeon_map:
            return False

        markers = [m for m in (dungeon_map.markers or []) if m.get("id") != marker_id]
        dungeon_map.markers = markers

        await self.db.flush()
        return True

    def render_with_fog(
        self,
        dungeon_map: DungeonMap,
        show_markers: bool = True,
    ) -> str:
        """
        Render the map with fog of war applied.

        Unrevealed cells are shown as '?'.
        Player position is shown as '@'.
        Markers overlay the base map.
        """
        if not dungeon_map.map_data:
            return ""

        lines = dungeon_map.map_data.split('\n')
        revealed = set(tuple(cell) for cell in (dungeon_map.revealed_cells or []))
        markers_dict = {}

        if show_markers:
            for marker in (dungeon_map.markers or []):
                pos = (marker.get("x", 0), marker.get("y", 0))
                # Only show markers in revealed areas
                if pos in revealed:
                    markers_dict[pos] = marker.get("symbol", "*")

        # Build rendered map
        rendered_lines = []
        for y, line in enumerate(lines):
            rendered_row = []
            for x, char in enumerate(line):
                pos = (x, y)

                # Check if this is the player position
                if (dungeon_map.player_x == x and dungeon_map.player_y == y and
                    pos in revealed):
                    rendered_row.append(self.PLAYER_SYMBOL)
                # Check for marker
                elif pos in markers_dict:
                    rendered_row.append(markers_dict[pos])
                # Check if revealed
                elif pos in revealed:
                    rendered_row.append(char)
                else:
                    rendered_row.append(self.FOG_SYMBOL)

            rendered_lines.append(''.join(rendered_row))

        return '\n'.join(rendered_lines)

    def render_full_map(
        self,
        dungeon_map: DungeonMap,
        show_markers: bool = True,
    ) -> str:
        """Render the full map without fog (for DM use)."""
        if not dungeon_map.map_data:
            return ""

        lines = dungeon_map.map_data.split('\n')
        markers_dict = {}

        if show_markers:
            for marker in (dungeon_map.markers or []):
                pos = (marker.get("x", 0), marker.get("y", 0))
                markers_dict[pos] = marker.get("symbol", "*")

        # Build rendered map
        rendered_lines = []
        for y, line in enumerate(lines):
            rendered_row = []
            for x, char in enumerate(line):
                pos = (x, y)

                # Check if this is the player position
                if dungeon_map.player_x == x and dungeon_map.player_y == y:
                    rendered_row.append(self.PLAYER_SYMBOL)
                # Check for marker
                elif pos in markers_dict:
                    rendered_row.append(markers_dict[pos])
                else:
                    rendered_row.append(char)

            rendered_lines.append(''.join(rendered_row))

        return '\n'.join(rendered_lines)

    async def get_map_data(
        self,
        map_id: UUID,
        include_fog: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Get complete map data for frontend rendering."""
        dungeon_map = await self.get_map(map_id)
        if not dungeon_map:
            return None

        if include_fog:
            rendered = self.render_with_fog(dungeon_map)
        else:
            rendered = self.render_full_map(dungeon_map)

        return {
            "id": str(dungeon_map.id),
            "name": dungeon_map.name,
            "width": dungeon_map.width,
            "height": dungeon_map.height,
            "rendered_map": rendered,
            "player_position": {
                "x": dungeon_map.player_x,
                "y": dungeon_map.player_y,
            } if dungeon_map.player_x is not None else None,
            "markers": [
                m for m in (dungeon_map.markers or [])
                if tuple([m.get("x", 0), m.get("y", 0)]) in
                   set(tuple(cell) for cell in (dungeon_map.revealed_cells or []))
            ] if include_fog else dungeon_map.markers,
            "revealed_count": len(dungeon_map.revealed_cells or []),
            "total_cells": dungeon_map.width * dungeon_map.height,
        }

    async def list_campaign_maps(
        self,
        campaign_id: UUID
    ) -> List[Dict[str, Any]]:
        """List all maps for a campaign."""
        result = await self.db.execute(
            select(DungeonMap)
            .where(DungeonMap.campaign_id == campaign_id)
            .order_by(DungeonMap.created_at.desc())
        )
        maps = list(result.scalars().all())

        return [
            {
                "id": str(m.id),
                "name": m.name,
                "width": m.width,
                "height": m.height,
                "is_active": m.is_active,
                "has_player": m.player_x is not None,
                "revealed_percentage": (
                    len(m.revealed_cells or []) / (m.width * m.height) * 100
                    if m.width and m.height else 0
                ),
            }
            for m in maps
        ]

    def generate_map(
        self,
        map_type: str = "dungeon",
        size: str = "medium",
    ) -> Tuple[str, int, int, int, int]:
        """
        Generate a procedural ASCII map.

        Returns: (map_data, width, height, entrance_x, entrance_y)
        """
        import random

        # Size configurations
        sizes = {
            "small": (15, 15),
            "medium": (25, 20),
            "large": (40, 30),
        }
        width, height = sizes.get(size, sizes["medium"])

        if map_type == "dungeon":
            return self._generate_dungeon(width, height)
        elif map_type == "cave":
            return self._generate_cave(width, height)
        elif map_type == "building":
            return self._generate_building(width, height)
        elif map_type == "outdoor":
            return self._generate_outdoor(width, height)
        else:
            return self._generate_dungeon(width, height)

    def _generate_dungeon(
        self,
        width: int,
        height: int,
    ) -> Tuple[str, int, int, int, int]:
        """Generate a classic dungeon with rooms and corridors."""
        import random

        # Initialize with walls
        grid = [['#' for _ in range(width)] for _ in range(height)]

        # Generate rooms
        rooms = []
        for _ in range(random.randint(4, 8)):
            room_w = random.randint(3, min(8, width // 3))
            room_h = random.randint(3, min(6, height // 3))
            room_x = random.randint(1, width - room_w - 2)
            room_y = random.randint(1, height - room_h - 2)

            # Check for overlap
            overlaps = False
            for rx, ry, rw, rh in rooms:
                if (room_x < rx + rw + 1 and room_x + room_w + 1 > rx and
                    room_y < ry + rh + 1 and room_y + room_h + 1 > ry):
                    overlaps = True
                    break

            if not overlaps:
                rooms.append((room_x, room_y, room_w, room_h))
                # Carve room
                for y in range(room_y, room_y + room_h):
                    for x in range(room_x, room_x + room_w):
                        grid[y][x] = '.'

        # Connect rooms with corridors
        for i in range(len(rooms) - 1):
            x1 = rooms[i][0] + rooms[i][2] // 2
            y1 = rooms[i][1] + rooms[i][3] // 2
            x2 = rooms[i + 1][0] + rooms[i + 1][2] // 2
            y2 = rooms[i + 1][1] + rooms[i + 1][3] // 2

            # Horizontal then vertical
            if random.random() < 0.5:
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    grid[y1][x] = '.'
                for y in range(min(y1, y2), max(y1, y2) + 1):
                    grid[y][x2] = '.'
            else:
                for y in range(min(y1, y2), max(y1, y2) + 1):
                    grid[y][x1] = '.'
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    grid[y2][x] = '.'

        # Add doors at room entrances (occasionally)
        for rx, ry, rw, rh in rooms:
            for y in range(ry - 1, ry + rh + 1):
                for x in range(rx - 1, rx + rw + 1):
                    if 0 <= x < width and 0 <= y < height:
                        if grid[y][x] == '.' and self._is_doorway(grid, x, y, width, height):
                            if random.random() < 0.3:
                                grid[y][x] = '+'

        # Place entrance in first room
        if rooms:
            entrance_x = rooms[0][0] + rooms[0][2] // 2
            entrance_y = rooms[0][1] + rooms[0][3] // 2
        else:
            entrance_x, entrance_y = width // 2, height // 2

        map_data = '\n'.join(''.join(row) for row in grid)
        return map_data, width, height, entrance_x, entrance_y

    def _generate_cave(
        self,
        width: int,
        height: int,
    ) -> Tuple[str, int, int, int, int]:
        """Generate a natural cave using cellular automata."""
        import random

        # Initialize randomly
        grid = [['#' if random.random() < 0.45 else '.' for _ in range(width)] for _ in range(height)]

        # Apply cellular automata rules
        for _ in range(4):
            new_grid = [row[:] for row in grid]
            for y in range(1, height - 1):
                for x in range(1, width - 1):
                    walls = sum(
                        1 for dy in range(-1, 2) for dx in range(-1, 2)
                        if grid[y + dy][x + dx] == '#'
                    )
                    new_grid[y][x] = '#' if walls >= 5 else '.'
            grid = new_grid

        # Ensure border is walls
        for x in range(width):
            grid[0][x] = '#'
            grid[height - 1][x] = '#'
        for y in range(height):
            grid[y][0] = '#'
            grid[y][width - 1] = '#'

        # Add water pools occasionally
        for _ in range(random.randint(0, 2)):
            pool_x = random.randint(3, width - 4)
            pool_y = random.randint(3, height - 4)
            if grid[pool_y][pool_x] == '.':
                grid[pool_y][pool_x] = '~'
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        if grid[pool_y + dy][pool_x + dx] == '.' and random.random() < 0.5:
                            grid[pool_y + dy][pool_x + dx] = '~'

        # Find a valid entrance (floor tile near edge)
        entrance_x, entrance_y = 2, height // 2
        for y in range(2, height - 2):
            if grid[y][2] == '.':
                entrance_x, entrance_y = 2, y
                break

        map_data = '\n'.join(''.join(row) for row in grid)
        return map_data, width, height, entrance_x, entrance_y

    def _generate_building(
        self,
        width: int,
        height: int,
    ) -> Tuple[str, int, int, int, int]:
        """Generate a building layout with rooms."""
        import random

        # Initialize with walls
        grid = [['#' for _ in range(width)] for _ in range(height)]

        # Create main area
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                grid[y][x] = '.'

        # Add internal walls to create rooms
        num_dividers = random.randint(1, 3)
        for _ in range(num_dividers):
            if random.random() < 0.5:
                # Vertical wall
                x = random.randint(3, width - 4)
                door_y = random.randint(2, height - 3)
                for y in range(1, height - 1):
                    if y != door_y:
                        grid[y][x] = '#'
                    else:
                        grid[y][x] = '+'
            else:
                # Horizontal wall
                y = random.randint(3, height - 4)
                door_x = random.randint(2, width - 3)
                for x in range(1, width - 1):
                    if x != door_x:
                        grid[y][x] = '#'
                    else:
                        grid[y][x] = '+'

        # Add entrance door at bottom
        entrance_x = width // 2
        entrance_y = height - 1
        grid[entrance_y][entrance_x] = '+'
        grid[entrance_y - 1][entrance_x] = '.'

        map_data = '\n'.join(''.join(row) for row in grid)
        return map_data, width, height, entrance_x, entrance_y - 1

    def _generate_outdoor(
        self,
        width: int,
        height: int,
    ) -> Tuple[str, int, int, int, int]:
        """Generate an outdoor area with trees and paths."""
        import random

        # Initialize with grass
        grid = [['.' for _ in range(width)] for _ in range(height)]

        # Add trees
        for _ in range(int(width * height * 0.15)):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            grid[y][x] = 'T'

        # Add a path
        path_y = height // 2
        for x in range(width):
            grid[path_y][x] = ','
            if random.random() < 0.3 and path_y > 1 and path_y < height - 2:
                path_y += random.choice([-1, 0, 0, 1])

        # Add water feature
        if random.random() < 0.5:
            water_x = random.randint(3, width - 4)
            water_y = random.randint(3, height - 4)
            for dy in range(-1, 2):
                for dx in range(-2, 3):
                    if 0 <= water_y + dy < height and 0 <= water_x + dx < width:
                        grid[water_y + dy][water_x + dx] = '~'

        entrance_x, entrance_y = 0, height // 2
        grid[entrance_y][entrance_x] = ','

        map_data = '\n'.join(''.join(row) for row in grid)
        return map_data, width, height, entrance_x, entrance_y

    def _is_doorway(
        self,
        grid: List[List[str]],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> bool:
        """Check if a position is suitable for a door (connecting corridor to room)."""
        # Check if we have walls on two opposite sides and floor on the other two
        if y <= 0 or y >= height - 1 or x <= 0 or x >= width - 1:
            return False

        h_walls = (grid[y][x - 1] == '#') + (grid[y][x + 1] == '#')
        v_walls = (grid[y - 1][x] == '#') + (grid[y + 1][x] == '#')
        h_floors = (grid[y][x - 1] == '.') + (grid[y][x + 1] == '.')
        v_floors = (grid[y - 1][x] == '.') + (grid[y + 1][x] == '.')

        return (h_walls == 2 and v_floors >= 1) or (v_walls == 2 and h_floors >= 1)

    def generate_connection_map(
        self,
        locations: List[Dict[str, Any]],
        current_location_key: Optional[str] = None,
        explored_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a simple ASCII map showing room connections.

        Args:
            locations: List of location dicts with 'location_key', 'name', and 'exits'
            current_location_key: The player's current location
            explored_keys: List of location keys the player has visited

        Returns:
            Dict with rendered_map, width, height, player_position, and markers
        """
        if not locations:
            return {
                "rendered_map": "No map data available.",
                "width": 25,
                "height": 1,
                "player_position": None,
                "markers": [],
            }

        explored = set(explored_keys or [])
        if current_location_key:
            explored.add(current_location_key)

        # Build adjacency graph
        connections: Dict[str, Dict[str, str]] = {}  # key -> {direction: target_key}
        names: Dict[str, str] = {}

        for loc in locations:
            key = str(loc.get('location_key', ''))
            names[key] = loc.get('name', f'Room {key}')[:12]  # Truncate long names
            exits = loc.get('exits', {})
            if isinstance(exits, dict):
                connections[key] = exits

        # Simple grid layout - place rooms in a rough grid based on connections
        # Start with room 1 (or first room) at center
        grid_size = 40
        cell_width = 14
        cell_height = 4

        # Calculate grid dimensions
        num_rooms = len(locations)
        cols = min(5, max(2, int(num_rooms ** 0.5) + 1))
        rows = (num_rooms + cols - 1) // cols

        # Position rooms in grid
        positions: Dict[str, Tuple[int, int]] = {}
        placed = set()

        # Try to place rooms respecting exit directions
        def place_room(key: str, row: int, col: int):
            if key in placed or row < 0 or row >= rows or col < 0 or col >= cols:
                return
            if (row, col) in [(p[0], p[1]) for p in positions.values()]:
                # Find next available spot
                for r in range(rows):
                    for c in range(cols):
                        if (r, c) not in [(p[0], p[1]) for p in positions.values()]:
                            row, col = r, c
                            break
            positions[key] = (row, col)
            placed.add(key)

        # Start with room 1 or first available
        start_key = '1' if '1' in names else list(names.keys())[0] if names else None
        if start_key:
            place_room(start_key, rows // 2, 0)

            # BFS to place connected rooms
            queue = [start_key]
            while queue:
                current = queue.pop(0)
                if current not in positions:
                    continue
                curr_row, curr_col = positions[current]

                exits = connections.get(current, {})
                for direction, target in exits.items():
                    target = str(target)
                    if target not in placed and target in names:
                        # Determine position based on direction
                        dir_lower = direction.lower()
                        if 'north' in dir_lower or 'up' in dir_lower:
                            place_room(target, curr_row - 1, curr_col)
                        elif 'south' in dir_lower or 'down' in dir_lower:
                            place_room(target, curr_row + 1, curr_col)
                        elif 'east' in dir_lower or 'right' in dir_lower:
                            place_room(target, curr_row, curr_col + 1)
                        elif 'west' in dir_lower or 'left' in dir_lower:
                            place_room(target, curr_row, curr_col - 1)
                        else:
                            # Default: place in next available
                            place_room(target, curr_row, curr_col + 1)
                        queue.append(target)

        # Place any unplaced rooms
        for key in names:
            if key not in placed:
                for r in range(rows):
                    for c in range(cols):
                        if (r, c) not in [(p[0], p[1]) for p in positions.values()]:
                            positions[key] = (r, c)
                            placed.add(key)
                            break
                    if key in placed:
                        break

        # Normalize positions to start at 0
        if positions:
            min_row = min(p[0] for p in positions.values())
            min_col = min(p[1] for p in positions.values())
            positions = {k: (r - min_row, c - min_col) for k, (r, c) in positions.items()}
            rows = max(p[0] for p in positions.values()) + 1
            cols = max(p[1] for p in positions.values()) + 1

        # Build ASCII map
        map_width = cols * cell_width + 1
        map_height = rows * cell_height + 1
        grid = [[' ' for _ in range(map_width)] for _ in range(map_height)]

        # Draw rooms
        for key, (row, col) in positions.items():
            x = col * cell_width
            y = row * cell_height

            is_current = key == current_location_key
            is_explored = key in explored
            name = names.get(key, f'Room {key}')

            if not is_explored and not is_current:
                # Unexplored room - show as ???
                box_char = '?'
                display_name = '???'
            else:
                box_char = '*' if is_current else '#'
                display_name = name

            # Draw box
            # Top border
            for i in range(cell_width - 2):
                grid[y][x + 1 + i] = '-' if is_explored or is_current else '?'
            grid[y][x] = '+' if is_explored or is_current else '?'
            grid[y][x + cell_width - 1] = '+' if is_explored or is_current else '?'

            # Sides and content
            for dy in range(1, cell_height - 1):
                grid[y + dy][x] = '|' if is_explored or is_current else '?'
                grid[y + dy][x + cell_width - 1] = '|' if is_explored or is_current else '?'

            # Room key/name
            key_str = f"[{key}]" if is_explored or is_current else "[?]"
            for i, ch in enumerate(key_str[:cell_width - 4]):
                if x + 2 + i < map_width:
                    grid[y + 1][x + 2 + i] = ch

            # Room name (truncated)
            for i, ch in enumerate(display_name[:cell_width - 4]):
                if x + 2 + i < map_width:
                    grid[y + 2][x + 2 + i] = ch

            # Current marker
            if is_current:
                grid[y + 1][x + cell_width - 3] = '@'

            # Bottom border
            for i in range(cell_width - 2):
                grid[y + cell_height - 1][x + 1 + i] = '-' if is_explored or is_current else '?'
            grid[y + cell_height - 1][x] = '+' if is_explored or is_current else '?'
            grid[y + cell_height - 1][x + cell_width - 1] = '+' if is_explored or is_current else '?'

        # Draw connections between explored rooms
        for key, exits in connections.items():
            if key not in positions or key not in explored:
                continue
            src_row, src_col = positions[key]
            src_x = src_col * cell_width + cell_width // 2
            src_y = src_row * cell_height + cell_height // 2

            for direction, target in exits.items():
                target = str(target)
                if target not in positions:
                    continue
                # Only draw if target is explored or current
                if target not in explored and target != current_location_key:
                    continue

                tgt_row, tgt_col = positions[target]
                tgt_x = tgt_col * cell_width + cell_width // 2
                tgt_y = tgt_row * cell_height + cell_height // 2

                # Draw simple line
                is_secret = 'secret' in direction.lower()
                line_char = '.' if is_secret else '-' if src_y == tgt_y else '|'

                if src_y == tgt_y:  # Horizontal
                    for x in range(min(src_x, tgt_x), max(src_x, tgt_x) + 1):
                        if grid[src_y][x] == ' ':
                            grid[src_y][x] = line_char
                elif src_x == tgt_x:  # Vertical
                    for y in range(min(src_y, tgt_y), max(src_y, tgt_y) + 1):
                        if grid[y][src_x] == ' ':
                            grid[y][src_x] = line_char

        # Build output
        lines = [''.join(row).rstrip() for row in grid]
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()

        rendered_map = '\n'.join(lines)

        # Build markers list with x,y coordinates (center of each room)
        markers = []
        player_position = None

        for key, (row, col) in positions.items():
            is_explored = key in explored or key == current_location_key
            if not is_explored:
                continue

            # Calculate center of room box
            center_x = col * cell_width + cell_width // 2
            center_y = row * cell_height + cell_height // 2

            name = names.get(key, f'Room {key}')

            marker = {
                "id": f"loc_{key}",
                "x": center_x,
                "y": center_y,
                "symbol": "@" if key == current_location_key else "*",
                "label": f"[{key}] {name}",
                "type": "current" if key == current_location_key else "location",
                "location_key": key,
                "visited": key in explored,
            }
            markers.append(marker)

            if key == current_location_key:
                player_position = {"x": center_x, "y": center_y}

        return {
            "rendered_map": rendered_map,
            "width": map_width,
            "height": map_height,
            "player_position": player_position,
            "markers": markers,
        }
