"""Game middleware package for deterministic game mechanics.

This package provides middleware that handles game mechanics deterministically,
reducing reliance on LLM for mechanical operations like movement, combat, and
treasure handling.

Architecture:
- GameMiddleware: Central dispatcher that orchestrates all handlers
- MovementHandler: Detects movement intent and auto-updates location
- SearchHandler: Handles search actions and pre-populates treasure/secrets
- DamageExtractor: Post-processes LLM output to ensure damage is applied
- CombatManager: Tracks combat state (HP, initiative, morale) deterministically

Flow:
    Player Input
        ↓
    GameMiddleware.pre_process()
        ├── MovementHandler: "go north" → auto-update location
        ├── SearchHandler: "search" → fetch treasure/secrets
        └── CombatManager: track combat state
        ↓
    LLM (Narrative Only)
        ↓
    GameMiddleware.post_process()
        └── DamageExtractor: ensure damage applied
        ↓
    Game State Updated
"""

from app.game.middleware import GameMiddleware
from app.game.movement_handler import MovementHandler
from app.game.search_handler import SearchHandler
from app.game.damage_extractor import DamageExtractor

__all__ = [
    "GameMiddleware",
    "MovementHandler",
    "SearchHandler",
    "DamageExtractor",
]
