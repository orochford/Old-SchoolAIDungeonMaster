"""Central game middleware dispatcher.

This module provides the main GameMiddleware class that orchestrates all
deterministic game mechanics handlers, reducing LLM reliance from ~82%
to a target of ~30%.

Architecture:
    Player Input
        ↓
    GameMiddleware.pre_process()
        ├── MovementHandler: auto-update location
        ├── SearchHandler: fetch treasure/secrets
        └── CombatManager: track combat state
        ↓
    LLM (Narrative Only)
        ↓
    GameMiddleware.post_process()
        └── DamageExtractor: ensure damage applied
        ↓
    Game State Updated
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.game.movement_handler import MovementHandler, MovementResult
from app.game.search_handler import SearchHandler, SearchResult
from app.game.damage_extractor import DamageExtractor, DamageExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class PreProcessResult:
    """Result of pre-processing player input through middleware."""

    # Movement results
    movement: Optional[MovementResult] = None
    """Movement detection and resolution result"""

    # Search results
    search: Optional[SearchResult] = None
    """Search detection and findable items result"""

    # Context to inject into LLM prompt
    context_injections: List[str] = field(default_factory=list)
    """Additional context to inject into LLM system prompt"""

    # Whether to block LLM processing
    block_llm: bool = False
    """If True, return error directly without LLM call"""

    # Error message if blocking
    error_message: Optional[str] = None
    """Error message to return to player if blocking"""

    # State updates already made
    state_updated: bool = False
    """Whether middleware already updated game state"""

    def get_combined_context(self) -> str:
        """Get all context injections as a single string.

        NOTE: Context injection disabled - it was confusing the LLM and
        overriding the authoritative module text. Let the module text and
        system prompt be the sole source of truth.
        """
        return ""


@dataclass
class PostProcessResult:
    """Result of post-processing LLM response through middleware."""

    # Damage extraction results
    damage: Optional[DamageExtractionResult] = None
    """Damage extraction and auto-application result"""

    # Events that were auto-applied
    auto_applied_events: List[Dict[str, Any]] = field(default_factory=list)
    """List of events that middleware auto-applied"""

    # Whether any auto-application happened
    state_modified: bool = False
    """Whether middleware modified game state"""

    # Movement that needs tool call
    pending_movement: Optional[dict] = None
    """Movement that LLM should have called tool for but didn't"""


class GameMiddleware:
    """Central middleware orchestrator for deterministic game mechanics.

    This class coordinates all game middleware handlers to:
    1. Pre-process player input before LLM
    2. Auto-resolve deterministic mechanics (movement, search)
    3. Post-process LLM output to ensure consistency
    4. Auto-apply missed damage/healing

    Usage:
        middleware = GameMiddleware(db)

        # Before LLM call
        pre_result = await middleware.pre_process(player_input, session)
        if pre_result.block_llm:
            return pre_result.error_message

        # Add context to LLM prompt
        enhanced_prompt = f"{system_prompt}\n{pre_result.get_combined_context()}"

        # After LLM response
        post_result = await middleware.post_process(
            llm_response, tool_calls, character, session
        )
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.movement_handler = MovementHandler(db)
        self.search_handler = SearchHandler(db)
        self.damage_extractor = DamageExtractor(db)

    async def pre_process(
        self,
        player_input: str,
        session: Session,
    ) -> PreProcessResult:
        """Pre-process player input through all middleware handlers.

        This runs BEFORE the LLM processes the action and can:
        - Auto-update location for movement
        - Inject treasure/secret context for searches
        - Block invalid actions with error messages
        - Modify game state deterministically

        Args:
            player_input: The player's input text
            session: The current game session

        Returns:
            PreProcessResult with middleware processing results
        """
        result = PreProcessResult()

        # 1. Movement detection and resolution
        try:
            movement_result = await self.movement_handler.detect_and_resolve(
                player_input, session
            )
            result.movement = movement_result

            if movement_result.detected:
                logger.info(f"[Middleware] Movement detected: {movement_result.direction}")

                if not movement_result.is_valid:
                    # Invalid movement - inject error context for LLM
                    # Don't block completely, let LLM narrate the failure
                    logger.info(f"[Middleware] Invalid movement: {movement_result.error_message}")

                if movement_result.auto_updated:
                    result.state_updated = True
                    logger.info(f"[Middleware] Auto-updated location to {movement_result.target_location_key}")

        except Exception as e:
            logger.exception(f"[Middleware] Error in movement handler: {e}")
            # Don't fail the whole request, just skip movement middleware

        # 2. Search detection and treasure/secret resolution
        try:
            search_result = await self.search_handler.detect_and_resolve(
                player_input, session
            )
            result.search = search_result

            if search_result.detected:
                logger.info(f"[Middleware] Search detected: {search_result.search_type}")

        except Exception as e:
            logger.exception(f"[Middleware] Error in search handler: {e}")
            # Don't fail the whole request, just skip search middleware

        # 3. Combat state management (placeholder for future implementation)
        # This would detect combat start/end and track HP/initiative

        return result

    async def post_process(
        self,
        llm_response: str,
        tool_calls: List[Dict[str, Any]],
        character: Character,
        session: Session,
        pre_result: Optional[PreProcessResult] = None,
    ) -> PostProcessResult:
        """Post-process LLM response through middleware.

        This runs AFTER the LLM processes the action and can:
        - Auto-apply damage that was mentioned but not tool-called
        - Check if movement tool was called when needed
        - Validate state consistency

        Args:
            llm_response: The LLM's narrative response
            tool_calls: List of tool calls made during the response
            character: The player character
            session: The game session
            pre_result: Result from pre-processing (to check if movement was expected)

        Returns:
            PostProcessResult with any auto-applied events
        """
        result = PostProcessResult()
        tool_names_called = {tc.get("name", "") for tc in tool_calls}

        # 1. Check if movement was detected but tool wasn't called
        if pre_result and pre_result.movement and pre_result.movement.is_valid:
            movement = pre_result.movement
            if movement.target_location_key and "update_adventure_location" not in tool_names_called:
                logger.warning(
                    f"[Game] Movement to {movement.target_location_key} detected but "
                    "update_adventure_location not called - flagging for retry"
                )
                result.pending_movement = {
                    "location_key": movement.target_location_key,
                    "location_name": movement.target_location_name,
                }

        # 2. Damage extraction and auto-application
        try:
            damage_result = self.damage_extractor.extract(
                llm_response,
                tool_calls,
                player_name=character.name,
            )
            result.damage = damage_result

            if damage_result.needs_application:
                applied_events = await self.damage_extractor.auto_apply(
                    damage_result, character, session
                )
                result.auto_applied_events.extend(applied_events)
                result.state_modified = True

        except Exception as e:
            logger.exception(f"[Game] Error in damage extractor: {e}")

        return result

    async def inject_pre_process_context(
        self,
        pre_result: PreProcessResult,
        adventure_context: str,
    ) -> str:
        """Inject pre-process context into the adventure context.

        Args:
            pre_result: Result from pre_process
            adventure_context: Existing adventure context string

        Returns:
            Enhanced adventure context with middleware injections
        """
        middleware_context = pre_result.get_combined_context()

        if not middleware_context:
            return adventure_context

        # Insert middleware context at a strategic location
        # Ideally after the current location section
        if "## CURRENT LOCATION" in adventure_context:
            # Insert after the current location section
            parts = adventure_context.split("## RELEVANT ADVENTURE CONTENT", 1)
            if len(parts) == 2:
                return f"{parts[0]}{middleware_context}\n## RELEVANT ADVENTURE CONTENT{parts[1]}"

        # Fallback: append at end
        return f"{adventure_context}\n{middleware_context}"

    def should_skip_llm(self, pre_result: PreProcessResult) -> bool:
        """Check if LLM processing should be skipped.

        Currently always returns False as we want LLM to narrate.
        Could be True for simple confirmations in the future.
        """
        return pre_result.block_llm

    def get_error_response(self, pre_result: PreProcessResult) -> str:
        """Get error response if LLM is blocked."""
        return pre_result.error_message or "An error occurred."
