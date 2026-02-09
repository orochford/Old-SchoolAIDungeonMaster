"""Loot sub-agent that enforces proper inventory management.

When the player picks up, takes, or receives items, this agent ensures
add_item is called so items actually reach the inventory.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session

logger = logging.getLogger(__name__)


@dataclass
class LootAction:
    """Parsed loot/pickup action."""
    is_loot_action: bool
    items: List[Dict[str, Any]]  # List of {name, quantity, value_gp}
    confidence: float = 0.0


class LootAgent:
    """Sub-agent that handles item pickup with enforced tool usage."""

    # Verbs that indicate taking/picking up items
    LOOT_VERBS = [
        "take", "grab", "pick up", "pickup", "collect", "gather",
        "pocket", "loot", "snatch", "claim", "acquire", "get",
        "retrieve", "recover", "salvage", "scoop up",
    ]

    # Verbs that indicate receiving items (from NPCs, rewards, etc.)
    RECEIVE_VERBS = [
        "accept", "receive", "take", "keep",
    ]

    # Keywords that indicate NOT taking (examining, etc.)
    EXCLUDE_KEYWORDS = [
        "look at", "examine", "inspect", "check", "search for",
        "don't take", "leave", "drop", "put down", "give away",
    ]

    # Common treasure/item words (currency handled separately via gold_patterns)
    TREASURE_WORDS = [
        "gem", "gems", "jewel", "jewels", "jewelry", "ring", "rings",
        "necklace", "bracelet", "amulet", "pendant", "crown", "tiara",
        "goblet", "chalice", "idol", "statuette", "figurine",
    ]

    WEAPON_WORDS = [
        "sword", "dagger", "axe", "mace", "hammer", "spear", "bow",
        "crossbow", "staff", "club", "flail", "halberd", "pike",
        "longsword", "shortsword", "greatsword", "battleaxe",
        "warhammer", "morningstar", "scimitar", "rapier",
    ]

    ARMOR_WORDS = [
        "armor", "armour", "shield", "helmet", "helm", "gauntlets",
        "boots", "chainmail", "plate", "leather", "scale",
    ]

    ITEM_WORDS = [
        "potion", "scroll", "wand", "rod", "staff", "book", "tome",
        "key", "keys", "rope", "torch", "lantern", "flask", "bottle",
        "bag", "sack", "chest", "box", "container", "pack",
        "food", "rations", "water", "wine", "ale",
        "map", "letter", "note", "document", "paper",
    ]

    def __init__(self, tool_handler: ToolHandler, db_session: AsyncSession):
        self.tool_handler = tool_handler
        self.db = db_session

    def parse_loot_action(self, player_input: str) -> LootAction:
        """Parse player input to detect loot/pickup intent.

        Args:
            player_input: The player's action text

        Returns:
            LootAction with parsed item details
        """
        input_lower = player_input.lower().strip()

        # Check for exclusion keywords first
        for exclude in self.EXCLUDE_KEYWORDS:
            if exclude in input_lower:
                return LootAction(is_loot_action=False, items=[], confidence=0.8)

        # Check for loot verbs
        has_loot_verb = any(
            re.search(rf'\b{verb}\b', input_lower)
            for verb in self.LOOT_VERBS
        )

        if not has_loot_verb:
            # Check for receive verbs (might be accepting a reward)
            has_receive_verb = any(
                re.search(rf'\b{verb}\b', input_lower)
                for verb in self.RECEIVE_VERBS
            )
            if not has_receive_verb:
                return LootAction(is_loot_action=False, items=[], confidence=0.7)

        # Extract items from the input
        items = self._extract_items(input_lower)

        if not items:
            # Has loot verb but no identifiable items
            # This might be "take everything" or similar
            if any(word in input_lower for word in ["everything", "all", "it all", "the lot"]):
                return LootAction(
                    is_loot_action=True,
                    items=[{"name": "all items", "quantity": 1}],
                    confidence=0.6,
                )
            return LootAction(is_loot_action=False, items=[], confidence=0.4)

        return LootAction(
            is_loot_action=True,
            items=items,
            confidence=0.9 if len(items) > 0 else 0.5,
        )

    def _extract_items(self, input_lower: str) -> List[Dict[str, Any]]:
        """Extract item names and quantities from input text."""
        items = []

        # Pattern for gold/coins with amounts: "50 gold", "100 gp", "the gold pieces"
        gold_patterns = [
            r'(\d+)\s*(?:gold|gp|gold pieces|gold coins)',
            r'(\d+)\s*(?:silver|sp|silver pieces)',
            r'(\d+)\s*(?:copper|cp|copper pieces)',
            r'(\d+)\s*(?:platinum|pp)',
            r'(\d+)\s*(?:electrum|ep)',
            r'(?:the\s+)?gold(?:\s+pieces)?',  # "the gold" without amount
        ]

        for pattern in gold_patterns:
            match = re.search(pattern, input_lower)
            if match:
                if match.groups() and match.group(1):
                    amount = int(match.group(1))
                    if 'silver' in pattern or 'sp' in pattern:
                        items.append({"name": "Silver Pieces", "quantity": amount, "value_gp": amount / 10})
                    elif 'copper' in pattern or 'cp' in pattern:
                        items.append({"name": "Copper Pieces", "quantity": amount, "value_gp": amount / 100})
                    elif 'platinum' in pattern or 'pp' in pattern:
                        items.append({"name": "Platinum Pieces", "quantity": amount, "value_gp": amount * 5})
                    elif 'electrum' in pattern or 'ep' in pattern:
                        items.append({"name": "Electrum Pieces", "quantity": amount, "value_gp": amount / 2})
                    else:
                        items.append({"name": "Gold Pieces", "quantity": amount, "value_gp": amount})
                else:
                    # "the gold" without specific amount - will need DM context
                    items.append({"name": "Gold Pieces", "quantity": None})
                break  # Only match one gold pattern

        # Pattern for items with quantities: "3 potions", "a sword", "the dagger"
        quantity_patterns = [
            (r'(\d+)\s+(\w+(?:\s+\w+)?)', lambda m: (int(m.group(1)), m.group(2))),
            (r'(?:a|an|the)\s+(\w+(?:\s+\w+)?)', lambda m: (1, m.group(1))),
        ]

        # Check for specific item types
        all_item_words = self.WEAPON_WORDS + self.ARMOR_WORDS + self.ITEM_WORDS + self.TREASURE_WORDS

        # Skip currency words - they're handled by gold_patterns above
        currency_words = ['gold', 'gp', 'silver', 'sp', 'copper', 'cp', 'platinum', 'pp',
                          'electrum', 'ep', 'coins', 'coin', 'pieces', 'money', 'wealth']

        for word in all_item_words:
            if word in input_lower and word not in currency_words:
                # Found an item word, try to get quantity
                quantity_match = re.search(rf'(\d+)\s+{word}', input_lower)
                if quantity_match:
                    quantity = int(quantity_match.group(1))
                else:
                    quantity = 1

                # Capitalize the item name
                item_name = word.title()

                # Check if already in items list
                if not any(item.get("name", "").lower() == word for item in items):
                    items.append({"name": item_name, "quantity": quantity})

        return items

    async def handle_loot(
        self,
        player_input: str,
        character: Character,
        session: Session,
        dm_context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Handle a potential loot/pickup action.

        If loot action is detected and items can be identified,
        forces add_item tool calls for each item.

        Args:
            player_input: Player's action text
            character: Player character
            session: Game session
            dm_context: Optional context about available loot

        Returns:
            List of tool result dicts for items added
        """
        action = self.parse_loot_action(player_input)

        if not action.is_loot_action:
            logger.debug(f"[LOOT] No loot action detected in: {player_input[:50]}...")
            return []

        if action.confidence < 0.5:
            logger.debug(f"[LOOT] Low confidence loot action: {action.confidence}")
            return []

        if not action.items:
            logger.debug("[LOOT] Loot action detected but no specific items identified")
            return []

        logger.info(f"[LOOT] Loot action detected: {len(action.items)} items, confidence={action.confidence}")

        results = []
        for item in action.items:
            item_name = item.get("name", "Unknown Item")
            quantity = item.get("quantity", 1)
            value_gp = item.get("value_gp")

            # Skip items without specific quantities (need DM to clarify)
            if quantity is None:
                logger.info(f"[LOOT] Skipping {item_name} - quantity unknown, DM should specify")
                continue

            logger.info(f"[LOOT] Auto-adding item: {item_name} x{quantity}")

            # Build tool input
            tool_input = {
                "item_name": item_name,
                "quantity": quantity,
            }
            if value_gp is not None:
                tool_input["value_gp"] = value_gp

            # Force the add_item call
            result = await self.tool_handler.execute(
                tool_name="add_item",
                tool_input=tool_input,
                character=character,
                session=session,
            )

            if not result.get("error"):
                results.append({
                    "type": "tool_result",
                    "tool_name": "add_item",
                    "result": result,
                })

        return results

    def format_loot_context(self, items_added: List[Dict[str, Any]]) -> str:
        """Format loot additions for DM context.

        Args:
            items_added: List of add_item results

        Returns:
            Formatted context string for DM
        """
        if not items_added:
            return ""

        lines = ["## ITEMS ADDED TO INVENTORY"]
        lines.append("The following items have been added to the character's inventory:")

        for item_result in items_added:
            result = item_result.get("result", {})
            item = result.get("item", {})
            name = item.get("name", "Unknown")
            quantity = item.get("quantity", 1)
            lines.append(f"- {name} x{quantity}")

        lines.append("")
        lines.append("Acknowledge these items in your narrative. Do NOT call add_item again for these.")

        return "\n".join(lines)
