"""Context provider that generates LLM context from the knowledge graph.

This replaces prose-based RAG context with structured facts that
the LLM must use verbatim.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.domains.adventures.graph_rag.schema import ModuleGraph
from app.domains.adventures.graph_rag.queries import GraphQueryService, LocationFacts
from app.domains.adventures.graph_rag.builder import build_graph_from_module
from app.domains.adventures.models import AdventureModule

logger = logging.getLogger(__name__)


@dataclass
class CachedGraph:
    """Wrapper for cached graph with metadata for invalidation."""
    graph: ModuleGraph
    file_mtime: Optional[float] = None  # File modification time when loaded


class GraphContextProvider:
    """Provides structured context from the knowledge graph for LLM consumption.

    This is the main integration point with dm_service. Instead of prose-based
    RAG chunks, it provides exact facts that the LLM must use.

    Thread-safe for concurrent async operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._graph_cache: Dict[str, CachedGraph] = {}
        self._query_cache: Dict[str, GraphQueryService] = {}
        self._cache_lock = asyncio.Lock()

    async def get_graph(self, module_id: UUID) -> Optional[ModuleGraph]:
        """Get or build the knowledge graph for a module.

        Thread-safe with automatic cache invalidation when file changes.
        """
        cache_key = str(module_id)
        graph_path = self._get_graph_path(module_id)

        async with self._cache_lock:
            # Check if cached and still valid
            if cache_key in self._graph_cache:
                cached = self._graph_cache[cache_key]
                # Check if file has been modified since we cached it
                if os.path.exists(graph_path):
                    current_mtime = os.path.getmtime(graph_path)
                    if cached.file_mtime is not None and current_mtime <= cached.file_mtime:
                        return cached.graph
                    else:
                        # File was modified, invalidate cache
                        logger.info(f"Graph file modified, invalidating cache for {module_id}")
                        del self._graph_cache[cache_key]
                        if cache_key in self._query_cache:
                            del self._query_cache[cache_key]
                else:
                    # File doesn't exist but we have cached - use cached
                    return cached.graph

            # Try to load from file
            if os.path.exists(graph_path):
                try:
                    graph = ModuleGraph.load(graph_path)
                    file_mtime = os.path.getmtime(graph_path)
                    self._graph_cache[cache_key] = CachedGraph(graph=graph, file_mtime=file_mtime)
                    logger.info(f"Loaded graph from {graph_path}")
                    return graph
                except Exception as e:
                    logger.error(f"Failed to load graph from {graph_path}: {e}")

            # Build graph from module (release lock during build since it may take time)
            # Note: We release the lock here to allow other operations, but this means
            # concurrent builds could happen. That's OK - last one wins.

        # Build outside the lock
        graph = await self._build_graph(module_id)
        if graph:
            async with self._cache_lock:
                # Save for future use
                try:
                    graph.save(graph_path)
                    file_mtime = os.path.getmtime(graph_path)
                    self._graph_cache[cache_key] = CachedGraph(graph=graph, file_mtime=file_mtime)
                    logger.info(f"Saved graph to {graph_path}")
                except Exception as e:
                    logger.error(f"Failed to save graph to {graph_path}: {e}")
                    # Still cache in memory even if save failed
                    self._graph_cache[cache_key] = CachedGraph(graph=graph, file_mtime=None)

        return graph

    async def invalidate_cache(self, module_id: UUID) -> None:
        """Explicitly invalidate the cache for a module.

        Call this when a module is re-parsed.
        """
        cache_key = str(module_id)
        async with self._cache_lock:
            if cache_key in self._graph_cache:
                del self._graph_cache[cache_key]
                logger.info(f"Invalidated graph cache for {module_id}")
            if cache_key in self._query_cache:
                del self._query_cache[cache_key]
                logger.info(f"Invalidated query cache for {module_id}")

    async def _build_graph(self, module_id: UUID) -> Optional[ModuleGraph]:
        """Build the knowledge graph from parsed module data.

        Uses already-extracted database data - no LLM calls needed.
        """
        try:
            graph = await build_graph_from_module(db=self.db, module_id=module_id)
            return graph
        except ValueError as e:
            logger.error(f"Module not found: {module_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to build graph: {e}")
            return None

    def _get_graph_path(self, module_id: UUID) -> str:
        """Get the path where the graph is stored."""
        base_dir = settings.graph_storage_path
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, f"{module_id}_graph.json")

    def get_query_service(self, graph: ModuleGraph) -> GraphQueryService:
        """Get or create a query service for the graph."""
        cache_key = graph.module_id
        if cache_key not in self._query_cache:
            self._query_cache[cache_key] = GraphQueryService(graph)
        return self._query_cache[cache_key]

    async def get_location_context(
        self,
        module_id: UUID,
        location_key: str,
        current_subarea: Optional[str] = None,
        subareas_visited: Optional[list] = None,
        triggered_content: Optional[list] = None,
    ) -> Optional[str]:
        """Get structured context for a location.

        This is the main method called by dm_service. Returns formatted
        context with exact facts that the LLM must use.

        Args:
            module_id: The adventure module UUID
            location_key: The location key (e.g., '1', '2', '31')
            current_subarea: ID of the sub-area player is currently in
            subareas_visited: List of sub-area IDs already visited
            triggered_content: List of trigger IDs already fired
        """
        graph = await self.get_graph(module_id)
        if not graph:
            logger.warning(f"No graph available for module {module_id}")
            return None

        query_service = self.get_query_service(graph)
        facts = query_service.get_location_facts(location_key)

        if not facts:
            logger.warning(f"No facts for location {location_key}")
            return None

        # Use state-aware formatting if state is provided
        if current_subarea is not None or subareas_visited:
            return query_service.format_for_llm_with_state(
                facts,
                current_subarea=current_subarea,
                subareas_visited=subareas_visited or [],
                triggered_content=triggered_content or [],
            )

        # Fall back to basic formatting
        return query_service.format_for_llm(facts)

    async def get_location_facts(
        self,
        module_id: UUID,
        location_key: str,
    ) -> Optional[LocationFacts]:
        """Get raw location facts (for programmatic use)."""
        graph = await self.get_graph(module_id)
        if not graph:
            return None

        query_service = self.get_query_service(graph)
        return query_service.get_location_facts(location_key)

    async def get_exits(
        self,
        module_id: UUID,
        location_key: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Get exits from a location."""
        graph = await self.get_graph(module_id)
        if not graph:
            return {}

        query_service = self.get_query_service(graph)
        return query_service.get_exits(location_key)

    async def get_triggers(
        self,
        module_id: UUID,
        location_key: str,
    ) -> list:
        """Get triggers for a location."""
        graph = await self.get_graph(module_id)
        if not graph:
            return []

        query_service = self.get_query_service(graph)
        return query_service.get_triggers(location_key)

    async def validate_exit(
        self,
        module_id: UUID,
        from_location: str,
        direction: str,
    ) -> Optional[str]:
        """Validate an exit exists and return destination.

        Returns destination key if exit exists, None otherwise.
        """
        graph = await self.get_graph(module_id)
        if not graph:
            return None

        query_service = self.get_query_service(graph)
        exits = query_service.get_exits(from_location)

        direction_lower = direction.lower()
        if direction_lower in exits:
            return exits[direction_lower]["to_key"]

        return None


async def get_graph_context(
    db: AsyncSession,
    module_id: UUID,
    location_key: str,
) -> Optional[str]:
    """Convenience function to get graph context.

    Can be called directly from dm_service.
    """
    provider = GraphContextProvider(db)
    return await provider.get_location_context(module_id, location_key)
