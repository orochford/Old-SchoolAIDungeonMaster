"""RPG Rules configuration system for different OSR systems."""

from .loader import get_rules_for_system, SUPPORTED_SYSTEMS
from .base import RPGRules

__all__ = ["get_rules_for_system", "SUPPORTED_SYSTEMS", "RPGRules"]
