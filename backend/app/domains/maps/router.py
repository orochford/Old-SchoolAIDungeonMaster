"""REST API endpoints for dungeon maps."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

from app.core.database import get_db
from app.domains.maps.map_service import MapService


router = APIRouter()


class MapCreate(BaseModel):
    """Request body for creating a map."""
    campaign_id: UUID
    name: str
    map_data: str
    location_id: Optional[UUID] = None


class MarkerCreate(BaseModel):
    """Request body for adding a marker."""
    x: int
    y: int
    symbol: str
    label: str
    marker_type: str = "generic"


class PositionUpdate(BaseModel):
    """Request body for updating player position."""
    x: int
    y: int
    reveal_radius: int = 2


class MapResponse(BaseModel):
    """Response for map data."""
    id: str
    name: str
    width: int
    height: int
    rendered_map: str
    player_position: Optional[dict] = None
    markers: List[dict] = []
    revealed_count: int
    total_cells: int


class MapListItem(BaseModel):
    """Response for map list item."""
    id: str
    name: str
    width: int
    height: int
    is_active: bool
    has_player: bool
    revealed_percentage: float


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_map(
    map_data: MapCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new dungeon map."""
    map_service = MapService(db)
    dungeon_map = await map_service.create_map(
        campaign_id=map_data.campaign_id,
        name=map_data.name,
        map_data=map_data.map_data,
        location_id=map_data.location_id,
    )
    await db.commit()

    return {
        "id": str(dungeon_map.id),
        "name": dungeon_map.name,
        "width": dungeon_map.width,
        "height": dungeon_map.height,
    }


@router.get("/campaign/{campaign_id}", response_model=List[MapListItem])
async def list_campaign_maps(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all maps for a campaign."""
    map_service = MapService(db)
    return await map_service.list_campaign_maps(campaign_id)


@router.get("/campaign/{campaign_id}/active")
async def get_active_map(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the currently active map for a campaign."""
    map_service = MapService(db)
    dungeon_map = await map_service.get_active_map(campaign_id)

    if not dungeon_map:
        return None

    return await map_service.get_map_data(dungeon_map.id)


@router.get("/{map_id}")
async def get_map(
    map_id: UUID,
    include_fog: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific map with rendered content."""
    map_service = MapService(db)
    map_data = await map_service.get_map_data(map_id, include_fog=include_fog)

    if not map_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map not found",
        )

    return map_data


@router.post("/{map_id}/activate")
async def activate_map(
    map_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Set a map as the active map for its campaign."""
    map_service = MapService(db)
    dungeon_map = await map_service.get_map(map_id)

    if not dungeon_map:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map not found",
        )

    await map_service.set_active_map(dungeon_map.campaign_id, map_id)
    await db.commit()

    return {"success": True, "map_id": str(map_id)}


@router.post("/{map_id}/position")
async def update_position(
    map_id: UUID,
    position: PositionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update player position on the map."""
    map_service = MapService(db)
    result = await map_service.update_player_position(
        map_id=map_id,
        x=position.x,
        y=position.y,
        reveal_radius=position.reveal_radius,
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )

    await db.commit()
    return result


@router.post("/{map_id}/markers")
async def add_marker(
    map_id: UUID,
    marker: MarkerCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a marker to the map."""
    map_service = MapService(db)
    result = await map_service.add_marker(
        map_id=map_id,
        x=marker.x,
        y=marker.y,
        symbol=marker.symbol,
        label=marker.label,
        marker_type=marker.marker_type,
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )

    await db.commit()
    return result


@router.delete("/{map_id}/markers/{marker_id}")
async def remove_marker(
    map_id: UUID,
    marker_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a marker from the map."""
    map_service = MapService(db)
    success = await map_service.remove_marker(map_id, marker_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map or marker not found",
        )

    await db.commit()
    return {"success": True}


@router.post("/{map_id}/reveal")
async def reveal_area(
    map_id: UUID,
    x: int,
    y: int,
    radius: int = 2,
    db: AsyncSession = Depends(get_db),
):
    """Reveal an area on the map."""
    map_service = MapService(db)
    newly_revealed = await map_service.reveal_radius(
        map_id=map_id,
        center_x=x,
        center_y=y,
        radius=radius,
    )

    await db.commit()

    return {
        "newly_revealed_count": len(newly_revealed),
        "newly_revealed": newly_revealed,
    }
