from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID
from datetime import datetime
import json
import logging

from app.core.database import get_db, AsyncSessionLocal
from app.domains.sessions.models import Session, ConversationMessage, MessageRole, SessionStatus
from app.domains.sessions.schemas import (
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    SessionWithMessages,
    MessageCreate,
    MessageResponse,
)
from app.domains.campaigns.models import Campaign
from app.domains.characters.models import Character
from app.llm.dm_service import DMService
from app.llm.adventure_planner import AdventurePlanner
from app.domains.sessions.recap_service import RecapService, get_previous_session_count
from app.domains.sessions.framing_service import CampaignFramingService
from app.domains.journal.summary_service import SessionSummaryService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start or resume a game session."""
    # Verify campaign exists
    result = await db.execute(
        select(Campaign).where(Campaign.id == session_data.campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Verify character exists
    result = await db.execute(
        select(Character).where(Character.id == session_data.character_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    # CRITICAL: Lock the campaign row to prevent race conditions
    # This ensures only one session can be created at a time for this campaign
    # When two requests arrive simultaneously, the second will wait until the first commits
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == session_data.campaign_id)
        .with_for_update()
    )
    result.scalar_one()  # Execute the lock

    # Now safely check for existing session (protected by the lock)
    result = await db.execute(
        select(Session)
        .where(
            Session.campaign_id == session_data.campaign_id,
            Session.character_id == session_data.character_id,
            Session.status.in_(["active", "paused"]),  # Resume both active and paused
        )
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    existing_session = result.scalar_one_or_none()

    if existing_session:
        # Reactivate paused sessions
        if existing_session.status == "paused":
            existing_session.status = "active"
            await db.flush()
            logger.info(f"Reactivating paused session {existing_session.id}")
        else:
            logger.info(f"Resuming existing session {existing_session.id}")
        await db.commit()  # Release the lock
        await db.refresh(existing_session)  # Refresh after commit to reattach
        return existing_session

    # Create new session
    session = Session(**session_data.model_dump())
    db.add(session)
    await db.flush()
    await db.commit()  # Release the lock
    await db.refresh(session)  # Refresh after commit to reattach
    logger.info(f"Created new session {session.id}")
    return session


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    campaign_id: UUID = None,
    character_id: UUID = None,
    status: str = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List sessions with optional filtering."""
    query = select(Session)

    if campaign_id:
        query = query.where(Session.campaign_id == campaign_id)
    if character_id:
        query = query.where(Session.character_id == character_id)
    if status:
        query = query.where(Session.status == status)

    query = query.order_by(Session.updated_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{session_id}", response_model=SessionWithMessages)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a session by ID with message history."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.messages))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return session


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: UUID,
    session_data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a session."""
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    update_data = session_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    await db.flush()
    await db.refresh(session)
    return session


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a session."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.sequence)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    session_id: UUID,
    message_data: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a message to a session (for manual additions)."""
    # Verify session exists
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Get next sequence number
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.sequence.desc())
        .limit(1)
    )
    last_message = result.scalar_one_or_none()
    next_sequence = (last_message.sequence + 1) if last_message else 1

    message = ConversationMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=message_data.content,
        sequence=next_sequence,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a session."""
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    await db.delete(session)
    await db.commit()


@router.websocket("/{session_id}/play")
async def play_session(websocket: WebSocket, session_id: UUID):
    """WebSocket endpoint for real-time game play with LLM DM."""
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    async with AsyncSessionLocal() as db:
        try:
            # Load session with messages
            result = await db.execute(
                select(Session)
                .options(selectinload(Session.messages))
                .where(Session.id == session_id)
            )
            game_session = result.scalar_one_or_none()

            if not game_session:
                await websocket.send_json({"type": "error", "message": "Session not found"})
                await websocket.close()
                return

            # Load character
            result = await db.execute(
                select(Character).where(Character.id == game_session.character_id)
            )
            character = result.scalar_one_or_none()

            if not character:
                await websocket.send_json({"type": "error", "message": "Character not found"})
                await websocket.close()
                return

            # Load campaign to check for adventure module
            result = await db.execute(
                select(Campaign).where(Campaign.id == game_session.campaign_id)
            )
            campaign = result.scalar_one_or_none()

            dm_service = DMService(db)
            adventure_planner = AdventurePlanner(db)

            # Plan adventure if campaign has adventure module and session has no adventure state
            adventure_title = None
            if campaign and campaign.adventure_document_id:
                try:
                    adventure_doc = await adventure_planner.get_adventure_document(
                        campaign.adventure_document_id
                    )
                    adventure_title = adventure_doc.title if adventure_doc else None

                    # Plan session if we don't have planned scenes yet
                    current_state = game_session.adventure_state or {}
                    if not current_state.get("upcoming_scenes"):
                        logger.info(f"Planning adventure for session {session_id}")
                        new_state = await adventure_planner.plan_session(
                            adventure_document_id=campaign.adventure_document_id,
                            current_state=current_state,
                            character=character,
                            rpg_system_id=character.rpg_system_id,
                        )
                        game_session.adventure_state = new_state
                        await db.flush()
                except Exception as planning_error:
                    logger.exception(f"Error during adventure planning for session {session_id}: {planning_error}")
                    # Continue without adventure planning - don't fail the whole session
                    await websocket.send_json({
                        "type": "warning",
                        "message": f"Adventure planning failed: {str(planning_error)}. Continuing without adventure context."
                    })

            # Send initial connection success with adventure info and game state
            connected_msg = {
                "type": "connected",
                "session_id": str(session_id),
                "character_name": character.name,
                "game_state": game_session.game_state,
            }
            if adventure_title:
                connected_msg["adventure_title"] = adventure_title
                connected_msg["adventure_state"] = game_session.adventure_state
            await websocket.send_json(connected_msg)

            # Check for previous sessions and send recap if available
            previous_count = await get_previous_session_count(
                db,
                campaign_id=game_session.campaign_id,
                character_id=game_session.character_id,
                current_session_id=session_id,
            )
            if previous_count > 0:
                try:
                    recap_service = RecapService(db)
                    recap = await recap_service.generate_recap(
                        campaign_id=game_session.campaign_id,
                        character_id=game_session.character_id,
                        current_session_id=session_id,
                    )
                    if recap:
                        await websocket.send_json({
                            "type": "session_recap",
                            "recap": recap,
                        })
                        logger.info(f"Sent session recap for campaign {game_session.campaign_id}")
                except Exception as recap_error:
                    logger.error(f"Failed to generate recap: {recap_error}")

            # Check for existing messages in this session
            has_valid_messages = game_session.messages and any(
                msg.content and msg.content.strip() for msg in game_session.messages
            )

            # For NEW campaigns (no previous sessions, no messages), send campaign framing
            if previous_count == 0 and not has_valid_messages and campaign and campaign.adventure_document_id:
                try:
                    framing_service = CampaignFramingService(db)
                    framing = await framing_service.generate_framing(
                        campaign_id=game_session.campaign_id,
                        character=character,
                        adventure_document_id=campaign.adventure_document_id,
                        session_id=session_id,  # For journal storage
                    )
                    if framing:
                        await websocket.send_json({
                            "type": "campaign_framing",
                            "framing": framing,
                        })
                        logger.info(f"Sent campaign framing for new campaign {game_session.campaign_id}")
                except Exception as framing_error:
                    logger.error(f"Failed to generate campaign framing: {framing_error}")

            # Send existing conversation history if reconnecting (skip empty messages)
            if game_session.messages:
                history_messages = []
                for msg in game_session.messages:
                    # Skip empty messages
                    if not msg.content or not msg.content.strip():
                        continue
                    history_messages.append({
                        "id": str(msg.id),
                        "role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                        "tool_calls": msg.tool_calls,
                        "tool_results": msg.tool_results,
                    })
                if history_messages:
                    await websocket.send_json({
                        "type": "conversation_history",
                        "messages": history_messages,
                    })
                    logger.info(f"Sent {len(history_messages)} messages for session {session_id}")

            # Send map data if available
            try:
                from app.domains.maps.map_service import MapService
                from app.domains.adventures.retriever import AdventureDataRetriever

                logger.info(f"[Map] Starting map loading for session {session_id}")
                map_service = MapService(db)
                active_map = await map_service.get_active_map(game_session.campaign_id)
                logger.info(f"[Map] Active map: {active_map}")

                if active_map:
                    # Use existing dungeon map
                    map_data = await map_service.get_map_data(active_map.id, include_fog=True)
                    if map_data:
                        await websocket.send_json({
                            "type": "tool_result",
                            "tool_name": "display_map",
                            "result": {
                                "map_id": map_data["id"],
                                "map_name": map_data["name"],
                                "rendered_map": map_data["rendered_map"],
                                "width": map_data["width"],
                                "height": map_data["height"],
                                "player_position": map_data["player_position"],
                                "markers": map_data["markers"],
                                "exploration_progress": f"{map_data['revealed_count']}/{map_data['total_cells']} cells explored",
                            },
                        })
                        logger.info(f"[Map] Sent active dungeon map for session {session_id}")
                elif campaign and campaign.adventure_document_id:
                    # Generate connection map from adventure locations
                    logger.info(f"[Map] No active map, checking adventure module for doc {campaign.adventure_document_id}")
                    retriever = AdventureDataRetriever(db)
                    module = await retriever.get_module_for_document(campaign.adventure_document_id)
                    logger.info(f"[Map] Module found: {module.title if module else 'None'}")

                    if module:
                        locations = await retriever.get_all_locations(module.id)
                        logger.info(f"[Map] Found {len(locations)} locations")

                        if locations:
                            # Get exits for each location (limit to first 20 to avoid too many queries)
                            full_locations = []
                            for loc in locations[:20]:
                                loc_context = await retriever.get_location_context(module.id, loc['key'])
                                if loc_context and loc_context.get('location'):
                                    full_locations.append({
                                        'location_key': loc['key'],
                                        'name': loc['name'],
                                        'exits': loc_context['location'].get('exits', {}),
                                    })
                            logger.info(f"[Map] Built {len(full_locations)} full locations with exits")

                            adventure_state = game_session.adventure_state or {}
                            explored_keys = adventure_state.get('visited_locations', [])
                            current_key = adventure_state.get('current_location_key')
                            logger.info(f"[Map] Current: {current_key}, Explored: {explored_keys}")

                            map_result = map_service.generate_connection_map(
                                locations=full_locations,
                                current_location_key=current_key,
                                explored_keys=explored_keys,
                            )
                            logger.info(f"[Map] Generated map: {map_result['width']}x{map_result['height']}, {len(map_result['markers'])} markers")

                            await websocket.send_json({
                                "type": "tool_result",
                                "tool_name": "display_map",
                                "result": {
                                    "map_id": "connection_map",
                                    "map_name": f"{module.title} - Area Map",
                                    "rendered_map": map_result["rendered_map"],
                                    "width": map_result["width"],
                                    "height": map_result["height"],
                                    "player_position": map_result["player_position"],
                                    "markers": map_result["markers"],
                                    "exploration_progress": f"{len(explored_keys)}/{len(full_locations)} areas explored",
                                },
                            })
                            logger.info(f"[Map] Sent connection map for session {session_id}")
                        else:
                            logger.warning(f"[Map] No locations found for module {module.id}")
                    else:
                        logger.warning(f"[Map] No parsed module found for document {campaign.adventure_document_id}")
                else:
                    logger.info(f"[Map] No map source available (no active map, no adventure_document_id)")
            except Exception as map_error:
                logger.exception(f"[Map] Failed to load map for session {session_id}: {map_error}")

            # If this is a new session with no messages (or only empty messages), generate opening scene
            # Re-check has_valid_messages (we defined it earlier for framing, recheck after history)
            has_valid_messages = game_session.messages and any(
                msg.content and msg.content.strip() for msg in game_session.messages
            )

            # Use atomic database operation to prevent race conditions with multiple connections
            # This is critical because two WebSocket connections could both load the session
            # with opening_generated=False before either one commits, causing duplicate intros
            should_generate_opening = False
            if not has_valid_messages:
                # Atomically check and set the flag using a fresh database query
                from sqlalchemy import update, and_
                from sqlalchemy.dialects.postgresql import JSONB

                # First, try to atomically set the flag only if it's not already set
                # We use a raw SQL update with a WHERE clause to ensure atomicity
                result = await db.execute(
                    select(Session)
                    .where(Session.id == session_id)
                    .with_for_update()  # Lock the row
                )
                fresh_session = result.scalar_one()

                fresh_state = dict(fresh_session.adventure_state or {})
                if not fresh_state.get("opening_generated", False):
                    # We won the race - set the flag and generate opening
                    fresh_state["opening_generated"] = True
                    fresh_session.adventure_state = fresh_state
                    await db.flush()
                    await db.commit()  # Commit immediately so other connections see it
                    should_generate_opening = True
                    logger.info(f"[Session] Won race: Set opening_generated=True for session {session_id}")

                    # Re-sync our game_session object with the fresh state
                    game_session.adventure_state = fresh_state
                else:
                    logger.info(f"[Session] Lost race: opening_generated already True for session {session_id}")

            if should_generate_opening:

                # Clean up any empty messages from failed attempts
                if game_session.messages:
                    logger.warning(f"[Session] Found {len(game_session.messages)} empty messages in session {session_id}, cleaning up")
                    for msg in list(game_session.messages):
                        if not msg.content or not msg.content.strip():
                            await db.delete(msg)
                    await db.flush()
                    game_session.messages = []
                await websocket.send_json({"type": "dm_typing"})
                try:
                    logger.info(f"[Session] Starting new session {session_id} - calling dm_service.start_session")
                    async for event in dm_service.start_session(game_session, character, campaign):
                        if event["type"] == "text":
                            await websocket.send_json({
                                "type": "dm_text",
                                "content": event["content"],
                            })
                        elif event["type"] == "tool_result":
                            # Only send tool results that are visible to players
                            if event.get("result", {}).get("visible", True):
                                await websocket.send_json({
                                    "type": "tool_result",
                                    "tool_name": event["tool_name"],
                                    "result": event["result"],
                                })
                        elif event["type"] == "complete":
                            await websocket.send_json({"type": "dm_complete"})
                            logger.info(f"[Session] DM opening scene complete for session {session_id}")
                    await db.commit()
                    # Refresh session to reload messages after opening scene
                    await db.refresh(game_session, ["messages"])
                except Exception as start_error:
                    logger.exception(f"[Session] Error during DM start_session for {session_id}: {start_error}")
                    # Roll back any partial changes
                    await db.rollback()
                    # Send error to frontend so user knows something went wrong
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Error starting session: {str(start_error)}. Please try refreshing."
                        })
                        await websocket.send_json({"type": "dm_complete"})
                    except RuntimeError:
                        # WebSocket already closed
                        pass

            # Main game loop
            while True:
                try:
                    # Receive player input
                    data = await websocket.receive_json()

                    if data.get("type") == "player_action":
                        player_input = data.get("content", "")

                        if not player_input.strip():
                            continue

                        # Signal that DM is processing
                        await websocket.send_json({"type": "dm_typing"})

                        try:
                            # Process through LLM and stream response
                            async for event in dm_service.process_player_action(
                                game_session=game_session,
                                character=character,
                                player_input=player_input,
                                campaign=campaign,
                            ):
                                if event["type"] == "text":
                                    await websocket.send_json({
                                        "type": "dm_text",
                                        "content": event["content"],
                                    })
                                elif event["type"] == "tool_result":
                                    # Only send tool results that are visible to players
                                    result = event.get("result", {})
                                    is_visible = result.get("visible", True)
                                    if is_visible:
                                        await websocket.send_json({
                                            "type": "tool_result",
                                            "tool_name": event["tool_name"],
                                            "result": event["result"],
                                        })
                                elif event["type"] == "complete":
                                    await websocket.send_json({"type": "dm_complete"})

                            await db.commit()

                            # Refresh session to reload messages and character state
                            await db.refresh(game_session, ["messages"])
                            await db.refresh(character)

                        except Exception as action_error:
                            logger.exception(f"Error processing player action: {action_error}")
                            try:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": f"Error processing action: {str(action_error)}"
                                })
                                await websocket.send_json({"type": "dm_complete"})
                            except RuntimeError:
                                # WebSocket already closed
                                break

                    elif data.get("type") == "dice_roll":
                        # Player rolled dice - store in session for DM reference
                        dice_roll = {
                            "notation": data.get("notation"),
                            "rolls": data.get("rolls"),
                            "modifier": data.get("modifier", 0),
                            "total": data.get("total"),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        # Include extra data if present (attack rolls have damage, weapon, etc.)
                        extra = data.get("extra")
                        if extra:
                            dice_roll["damage"] = extra.get("damage")
                            dice_roll["damage_rolls"] = extra.get("damageRolls")
                            dice_roll["weapon"] = extra.get("weapon")
                            dice_roll["thac0"] = extra.get("thac0")
                            dice_roll["is_attack"] = True
                        # Store in game state for DM to reference
                        game_state = game_session.game_state or {}
                        game_state["last_player_roll"] = dice_roll
                        game_session.game_state = game_state
                        await db.flush()
                        logger.info(f"Player dice roll recorded: {dice_roll}")

                    elif data.get("type") == "ping":
                        try:
                            await websocket.send_json({"type": "pong"})
                        except RuntimeError:
                            break

                    elif data.get("type") == "end_session":
                        # Player explicitly ending session - generate proper summary
                        logger.info(f"Player ending session {session_id}")

                        try:
                            await websocket.send_json({"type": "dm_typing"})

                            # Generate comprehensive session summary with pickup point
                            summary_service = SessionSummaryService(db)
                            summary_data = await summary_service.generate_session_summary(
                                session_id=session_id,
                                save_to_journal=True,
                            )

                            # Update adventure state with pickup context
                            adventure_state = dict(game_session.adventure_state or {})
                            adventure_state["last_session_summary"] = summary_data.get("summary", "")
                            adventure_state["pickup_point"] = {
                                "location": adventure_state.get("current_location", game_session.current_location or ""),
                                "scene": adventure_state.get("current_scene", ""),
                                "key_events": summary_data.get("key_events", []),
                                "active_threads": [t for t in adventure_state.get("active_plot_threads", []) if t.get("status") == "active"],
                                "npcs_active": list(adventure_state.get("npcs_encountered", {}).keys())[:5],
                            }
                            game_session.adventure_state = adventure_state

                            # Mark session as paused (not completed) so it can be resumed
                            game_session.status = "paused"
                            game_session.summary = summary_data.get("summary", "")

                            await db.commit()
                            logger.info(f"Session {session_id} ended and saved")

                            # Send summary to client
                            await websocket.send_json({
                                "type": "session_ended",
                                "summary": summary_data,
                                "message": "Session saved! You can resume from where you left off next time.",
                            })

                        except Exception as end_error:
                            logger.exception(f"Error ending session: {end_error}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Error saving session: {str(end_error)}",
                            })

                        # Close connection after ending
                        await websocket.close()
                        return

                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for session {session_id}")

                    # Auto-generate session summary on disconnect
                    try:
                        # SessionSummaryService imported at top of file
                        summary_service = SessionSummaryService(db)
                        await summary_service.generate_session_summary(
                            session_id=session_id,
                            save_to_journal=True,
                        )
                        await db.commit()
                        logger.info(f"Auto-generated summary for session {session_id}")
                    except Exception as summary_error:
                        logger.error(f"Failed to auto-generate summary: {summary_error}")

                    break

        except Exception as e:
            logger.exception(f"Error in WebSocket session {session_id}")
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
                await websocket.close()
            except RuntimeError:
                # WebSocket already closed, ignore
                pass
