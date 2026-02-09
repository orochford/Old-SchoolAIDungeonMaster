"""GraphRAG module for structured knowledge graph retrieval of adventure modules."""

from app.domains.adventures.graph_rag.schema import (
    # Node types
    LocationNode,
    ItemNode,
    CreatureNode,
    NPCNode,
    TriggerNode,
    FeatureNode,
    ContainerNode,
    BodyNode,
    # Relationship types
    ConnectionEdge,
    ContainsEdge,
    LocatedAtEdge,
    # Graph container
    ModuleGraph,
)
from app.domains.adventures.graph_rag.builder import GraphBuilder, build_graph_from_module  # Now uses DB data, no LLM
from app.domains.adventures.graph_rag.queries import GraphQueryService, LocationFacts
from app.domains.adventures.graph_rag.context_provider import GraphContextProvider, get_graph_context

__all__ = [
    # Node types
    "LocationNode",
    "ItemNode",
    "CreatureNode",
    "NPCNode",
    "TriggerNode",
    "FeatureNode",
    "ContainerNode",
    "BodyNode",
    # Edge types
    "ConnectionEdge",
    "ContainsEdge",
    "LocatedAtEdge",
    # Graph container
    "ModuleGraph",
    # Builder
    "GraphBuilder",
    "build_graph_from_module",
    # Queries
    "GraphQueryService",
    "LocationFacts",
    # Context provider
    "GraphContextProvider",
    "get_graph_context",
]
