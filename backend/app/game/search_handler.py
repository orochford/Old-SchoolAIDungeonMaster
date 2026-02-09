"""Search and treasure detection middleware.

This handler intercepts search-related player input, fetches treasure and secrets
from the current location, and ensures items are properly added to inventory
when discovered.

This ensures:
- Treasure is never forgotten (LLM receives what's findable)
- Secrets are properly revealed based on module data
- add_item is automatically called for discovered treasure
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.sessions.models import Session
from app.domains.campaigns.models import Campaign
from app.domains.adventures.models import AdventureModule, AdventureLocation

logger = logging.getLogger(__name__)


# Search patterns that indicate search intent
SEARCH_PATTERNS = [
    r"\bsearch\b",
    r"\blook for\b",
    r"\bexamine\b",
    r"\bcheck\b",
    r"\binvestigate\b",
    r"\binspect\b",
    r"\blook around\b",
    r"\blook through\b",
    r"\brummage\b",
    r"\bfind\b",
    r"\bscan\b",
    r"\bscour\b",
]

# Specific search targets
TREASURE_TARGETS = [
    r"\btreasure\b",
    r"\bgold\b",
    r"\bcoins?\b",
    r"\bloot\b",
    r"\bvaluables?\b",
    r"\bitems?\b",
    r"\bchest\b",
    r"\bbox\b",
    r"\bcontainer\b",
    r"\bbag\b",
    r"\bpouch\b",
]

SECRET_TARGETS = [
    r"\bsecret\b",
    r"\bhidden\b",
    r"\btrap\b",
    r"\bdoor\b",
    r"\bpassage\b",
    r"\bcompartment\b",
    r"\bpanel\b",
    r"\bswitch\b",
    r"\blever\b",
    r"\bbutton\b",
]

BODY_TARGETS = [
    r"\bbody\b",
    r"\bbodies\b",
    r"\bcorpse\b",
    r"\bcorpses\b",
    r"\bremains\b",
    r"\bskeleton\b",
    r"\bskeletons\b",
    r"\bdead\b",
]


@dataclass
class TreasureItem:
    """A treasure item from the module."""

    name: str
    """Item name"""

    value: Optional[str] = None
    """Value (e.g., '100 gp')"""

    location: Optional[str] = None
    """Where it's found (e.g., 'behind tapestry')"""

    is_hidden: bool = False
    """Whether it requires a search to find"""


@dataclass
class SecretInfo:
    """A secret from the module."""

    secret_type: str
    """Type of secret (e.g., 'secret_door', 'hidden_compartment')"""

    description: str
    """Description of the secret"""

    detection: Optional[str] = None
    """How to detect (e.g., 'Search DC 15')"""

    trigger: Optional[str] = None
    """What reveals it"""


@dataclass
class TrapInfo:
    """A trap from the module."""

    trigger: str
    """What triggers the trap"""

    effect: str
    """What happens when triggered"""

    detection: Optional[str] = None
    """How to detect"""

    disarm: Optional[str] = None
    """How to disarm"""


@dataclass
class SearchResult:
    """Result of search detection and resolution."""

    detected: bool
    """Whether search intent was detected"""

    search_type: str = "general"
    """Type of search: 'general', 'treasure', 'secrets', 'body', 'specific'"""

    search_target: Optional[str] = None
    """Specific target being searched (e.g., 'the chest')"""

    treasure_available: List[TreasureItem] = field(default_factory=list)
    """Treasure items available to find"""

    secrets_available: List[SecretInfo] = field(default_factory=list)
    """Secrets available to find"""

    traps_present: List[TrapInfo] = field(default_factory=list)
    """Traps present in the area"""

    context_injection: Optional[str] = None
    """Context to inject into LLM prompt about findable items"""

    items_to_add: List[Dict[str, Any]] = field(default_factory=list)
    """Items that should be auto-added to inventory on success"""


class SearchHandler:
    """Handles search detection and treasure/secret resolution.

    This handler:
    1. Detects search intent from player input
    2. Fetches treasure and secrets from current location
    3. Injects context about what's findable
    4. Tracks what should be auto-added to inventory
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_and_resolve(
        self,
        player_input: str,
        session: Session,
    ) -> SearchResult:
        """Detect search intent and fetch findable items.

        Args:
            player_input: The player's input text
            session: The current game session

        Returns:
            SearchResult with detection results and findable items
        """
        input_lower = player_input.lower().strip()

        # Check if this looks like a search action
        is_search, search_type, search_target = self._detect_search(input_lower)

        if not is_search:
            return SearchResult(detected=False)

        logger.info(f"[Search] Detected search: type={search_type}, target={search_target}")

        # Get current location context
        adventure_state = session.adventure_state or {}
        current_location_key = adventure_state.get("current_location_key")

        if not current_location_key:
            logger.info("[Search] No current location key - passing to LLM")
            return SearchResult(
                detected=True,
                search_type=search_type,
                search_target=search_target,
            )

        # Get campaign to find adventure module
        campaign = await self._get_campaign(session.campaign_id)
        if not campaign or not campaign.adventure_document_id:
            return SearchResult(
                detected=True,
                search_type=search_type,
                search_target=search_target,
            )

        # Get current location from adventure module
        current_location = await self._get_location(
            campaign.adventure_document_id,
            current_location_key
        )

        if not current_location:
            logger.warning(f"[Search] Could not find location {current_location_key}")
            return SearchResult(
                detected=True,
                search_type=search_type,
                search_target=search_target,
            )

        # Extract treasure, secrets, and traps
        treasure_items = self._extract_treasure(current_location.treasure)
        secrets = self._extract_secrets(current_location.secrets)
        traps = self._extract_traps(current_location.traps)

        logger.info(f"[Search] Found: {len(treasure_items)} treasure, {len(secrets)} secrets, {len(traps)} traps")

        # Build items to auto-add (for successful treasure searches)
        items_to_add = []
        if search_type in ("treasure", "general", "body") and treasure_items:
            for item in treasure_items:
                items_to_add.append({
                    "item_name": item.name,
                    "value_gp": self._parse_gold_value(item.value),
                })

        # Build context injection
        context = self._build_search_context(
            search_type,
            search_target,
            treasure_items,
            secrets,
            traps,
            current_location.name,
        )

        return SearchResult(
            detected=True,
            search_type=search_type,
            search_target=search_target,
            treasure_available=treasure_items,
            secrets_available=secrets,
            traps_present=traps,
            context_injection=context,
            items_to_add=items_to_add,
        )

    def _detect_search(self, input_lower: str) -> tuple[bool, str, Optional[str]]:
        """Detect search intent and categorize it.

        Returns:
            Tuple of (is_search, search_type, search_target)
        """
        # Check for search pattern
        has_search_pattern = any(
            re.search(pattern, input_lower)
            for pattern in SEARCH_PATTERNS
        )

        if not has_search_pattern:
            return False, "none", None

        # Determine search type
        search_type = "general"
        search_target = None

        # Check for treasure-specific search
        if any(re.search(pattern, input_lower) for pattern in TREASURE_TARGETS):
            search_type = "treasure"
            # Try to extract specific target
            for pattern in TREASURE_TARGETS:
                match = re.search(pattern, input_lower)
                if match:
                    search_target = match.group(0)
                    break

        # Check for secret-specific search
        elif any(re.search(pattern, input_lower) for pattern in SECRET_TARGETS):
            search_type = "secrets"
            for pattern in SECRET_TARGETS:
                match = re.search(pattern, input_lower)
                if match:
                    search_target = match.group(0)
                    break

        # Check for body-specific search
        elif any(re.search(pattern, input_lower) for pattern in BODY_TARGETS):
            search_type = "body"
            for pattern in BODY_TARGETS:
                match = re.search(pattern, input_lower)
                if match:
                    search_target = match.group(0)
                    break

        # Check for specific object search (e.g., "search the desk")
        specific_match = re.search(r'(?:search|examine|check|inspect)\s+(?:the\s+)?(\w+(?:\s+\w+)?)', input_lower)
        if specific_match and not search_target:
            search_target = specific_match.group(1)
            if search_type == "general":
                search_type = "specific"

        return True, search_type, search_target

    def _extract_treasure(self, treasure_data: Optional[List[Dict[str, Any]]]) -> List[TreasureItem]:
        """Extract treasure items from location data."""
        if not treasure_data:
            return []

        items = []
        for item in treasure_data:
            if isinstance(item, dict):
                items.append(TreasureItem(
                    name=item.get("item", item.get("name", "Unknown Item")),
                    value=item.get("value", item.get("value_gp")),
                    location=item.get("location"),
                    is_hidden=item.get("hidden", item.get("is_hidden", False)),
                ))
            elif isinstance(item, str):
                items.append(TreasureItem(name=item))

        return items

    def _extract_secrets(self, secrets_data: Optional[List[Dict[str, Any]]]) -> List[SecretInfo]:
        """Extract secrets from location data."""
        if not secrets_data:
            return []

        secrets = []
        for secret in secrets_data:
            if isinstance(secret, dict):
                secrets.append(SecretInfo(
                    secret_type=secret.get("type", "unknown"),
                    description=secret.get("description", ""),
                    detection=secret.get("detection"),
                    trigger=secret.get("trigger"),
                ))

        return secrets

    def _extract_traps(self, traps_data: Optional[List[Dict[str, Any]]]) -> List[TrapInfo]:
        """Extract traps from location data."""
        if not traps_data:
            return []

        traps = []
        for trap in traps_data:
            if isinstance(trap, dict):
                traps.append(TrapInfo(
                    trigger=trap.get("trigger", "unknown"),
                    effect=trap.get("effect", ""),
                    detection=trap.get("detection"),
                    disarm=trap.get("disarm"),
                ))

        return traps

    def _parse_gold_value(self, value_str: Optional[str]) -> Optional[int]:
        """Parse gold value from string like '100 gp' or '50 gold pieces'."""
        if not value_str:
            return None

        # Try to extract numeric value
        match = re.search(r'(\d+(?:,\d{3})*)\s*(?:gp|gold)', str(value_str), re.IGNORECASE)
        if match:
            return int(match.group(1).replace(',', ''))

        # Try just a number
        match = re.search(r'(\d+)', str(value_str))
        if match:
            return int(match.group(1))

        return None

    async def _get_campaign(self, campaign_id: UUID) -> Optional[Campaign]:
        """Get campaign by ID."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        return result.scalar_one_or_none()

    async def _get_location(
        self,
        document_id: UUID,
        location_key: str,
    ) -> Optional[AdventureLocation]:
        """Get adventure location by key."""
        # First get the module
        result = await self.db.execute(
            select(AdventureModule).where(
                AdventureModule.pdf_document_id == document_id
            )
        )
        module = result.scalar_one_or_none()

        if not module:
            return None

        # Then get the location
        result = await self.db.execute(
            select(AdventureLocation).where(
                AdventureLocation.module_id == module.id,
                AdventureLocation.location_key == location_key,
            )
        )
        return result.scalar_one_or_none()

    def _build_search_context(
        self,
        search_type: str,
        search_target: Optional[str],
        treasure: List[TreasureItem],
        secrets: List[SecretInfo],
        traps: List[TrapInfo],
        location_name: str,
    ) -> str:
        """Build context injection for search actions.

        NOTE: Context injection disabled - it was confusing the LLM and
        overriding the authoritative module text. Let the module text be
        the sole source of truth for treasure, secrets, and traps.
        """
        return ""
