"""Time sub-agent that enforces proper time tracking.

When the player rests, travels, or waits, this agent ensures
advance_time is called so the calendar updates properly.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
import re
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.domains.adventures.retriever import AdventureDataRetriever

logger = logging.getLogger(__name__)


@dataclass
class WanderingEncounter:
    """Result of wandering monster check."""
    triggered: bool
    roll: int = 0
    threshold: int = 1  # Encounter on this or lower
    encounter_name: str = ""
    creatures: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.creatures is None:
            self.creatures = []


@dataclass
class TimeAction:
    """Parsed time-passing action."""
    is_time_action: bool
    hours: int = 0
    days: int = 0
    reason: str = ""
    confidence: float = 0.0
    is_rest: bool = False  # True if this is rest (vs travel/wait)


class TimeAgent:
    """Sub-agent that handles time passage with enforced tool usage."""

    # Rest-related keywords and their typical durations
    REST_PATTERNS = [
        # Full rest (8 hours)
        (r'\b(?:rest|sleep|camp)\b.*\b(?:night|overnight|full|long)\b', 8, 0, "resting overnight"),
        (r'\b(?:sleep|rest)\s+(?:for\s+)?(?:the\s+)?night\b', 8, 0, "sleeping for the night"),
        (r'\b(?:make|set up)\s+camp\b', 8, 0, "camping"),
        (r'\bspend\s+(?:the\s+)?night\b', 8, 0, "spending the night"),

        # Short rest (1 hour)
        (r'\b(?:short|brief|quick)\s+rest\b', 1, 0, "taking a short rest"),
        (r'\bcatch\s+(?:my|our)?\s*breath\b', 1, 0, "catching breath"),
        (r'\btake\s+a\s+(?:short\s+)?break\b', 1, 0, "taking a break"),

        # Specific hour amounts
        (r'\brest\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "resting"),
        (r'\bsleep\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "sleeping"),
        (r'\bwait\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "waiting"),
    ]

    # Travel patterns
    TRAVEL_PATTERNS = [
        # Day-long travel
        (r'\btravel\s+(?:for\s+)?(?:a\s+)?(?:full\s+)?day\b', 8, 0, "traveling for a day"),
        (r'\bjourney\s+(?:for\s+)?(?:a\s+)?day\b', 8, 0, "journeying for a day"),
        (r'\bmarch\s+(?:for\s+)?(?:a\s+)?day\b', 8, 0, "marching for a day"),

        # Multi-day travel
        (r'\btravel\s+(?:for\s+)?(\d+)\s*days?\b', 0, None, "traveling"),
        (r'\bjourney\s+(?:for\s+)?(\d+)\s*days?\b', 0, None, "journeying"),

        # Hour-based travel
        (r'\btravel\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "traveling"),
        (r'\bwalk\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "walking"),
        (r'\bride\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "riding"),
    ]

    # Wait patterns
    WAIT_PATTERNS = [
        (r'\bwait\s+(?:until|till)\s+(?:dawn|morning|sunrise)\b', 6, 0, "waiting until dawn"),
        (r'\bwait\s+(?:until|till)\s+(?:dusk|evening|sunset|nightfall)\b', 6, 0, "waiting until dusk"),
        (r'\bwait\s+(?:until|till)\s+(?:midnight|night)\b', 8, 0, "waiting until midnight"),
        (r'\bwait\s+(?:until|till)\s+(?:noon|midday)\b', 4, 0, "waiting until noon"),
        (r'\bwait\s+(?:for\s+)?(\d+)\s*(?:hour|hr)s?\b', None, 0, "waiting"),
        (r'\bwait\s+(?:for\s+)?(\d+)\s*(?:minute|min)s?\b', 0, 0, "waiting briefly"),  # < 1 hour
    ]

    # Keywords that indicate NOT time passing
    EXCLUDE_KEYWORDS = [
        "don't wait", "no time to", "immediately", "quickly", "hurry",
        "no rest", "can't rest", "unable to rest",
    ]

    def __init__(self, tool_handler: ToolHandler, db_session: AsyncSession):
        self.tool_handler = tool_handler
        self.db = db_session

    def parse_time_action(self, player_input: str) -> TimeAction:
        """Parse player input to detect time-passing intent.

        Args:
            player_input: The player's action text

        Returns:
            TimeAction with parsed time details
        """
        input_lower = player_input.lower().strip()

        # Check for exclusion keywords first
        for exclude in self.EXCLUDE_KEYWORDS:
            if exclude in input_lower:
                return TimeAction(is_time_action=False, confidence=0.8)

        # Check patterns by category to track if it's rest
        pattern_groups = [
            (self.REST_PATTERNS, True),   # is_rest = True
            (self.TRAVEL_PATTERNS, False),
            (self.WAIT_PATTERNS, False),
        ]

        for patterns, is_rest in pattern_groups:
            for pattern, default_hours, default_days, reason in patterns:
                match = re.search(pattern, input_lower)
                if match:
                    hours = default_hours
                    days = default_days

                    # Extract number from pattern if it captured one
                    if match.groups():
                        try:
                            num = int(match.group(1))
                            if default_hours is None:
                                hours = num
                            elif default_days is None:
                                days = num
                        except (ValueError, IndexError):
                            pass

                    # Skip if no significant time passes
                    if hours == 0 and days == 0:
                        continue

                    return TimeAction(
                        is_time_action=True,
                        hours=hours or 0,
                        days=days or 0,
                        reason=reason,
                        confidence=0.9,
                        is_rest=is_rest,
                    )

        # Check for generic rest/wait without specific duration
        if re.search(r'\b(?:rest|sleep|camp)\b', input_lower):
            # Generic rest - assume 1 hour as minimum
            return TimeAction(
                is_time_action=True,
                hours=1,
                days=0,
                reason="resting",
                confidence=0.6,
                is_rest=True,
            )

        # Generic wait (not rest)
        if re.search(r'\bwait\b', input_lower):
            return TimeAction(
                is_time_action=True,
                hours=1,
                days=0,
                reason="waiting",
                confidence=0.6,
                is_rest=False,
            )

        return TimeAction(is_time_action=False, confidence=0.7)

    async def handle_time_passage(
        self,
        player_input: str,
        character: Character,
        session: Session,
    ) -> Optional[Dict[str, Any]]:
        """Handle a potential time-passing action.

        If time passage is detected, forces the advance_time tool call.

        Args:
            player_input: Player's action text
            character: Player character
            session: Game session

        Returns:
            Tool result dict if time was advanced, None otherwise
        """
        action = self.parse_time_action(player_input)

        if not action.is_time_action:
            logger.debug(f"[TIME] No time action detected in: {player_input[:50]}...")
            return None

        if action.confidence < 0.5:
            logger.debug(f"[TIME] Low confidence time action: {action.confidence}")
            return None

        if action.hours == 0 and action.days == 0:
            logger.debug("[TIME] Time action detected but duration is zero")
            return None

        logger.info(f"[TIME] Time passage detected: {action.hours}h {action.days}d - {action.reason} (is_rest={action.is_rest})")

        # Force the advance_time call
        result = await self.tool_handler.execute(
            tool_name="advance_time",
            tool_input={
                "hours": action.hours,
                "days": action.days,
                "reason": action.reason,
            },
            character=character,
            session=session,
        )

        if result.get("error"):
            logger.warning(f"[TIME] Failed to advance time: {result.get('error')}")
            return None

        # Apply natural healing if resting and character is injured
        healing_result = None
        if action.is_rest and character.current_hp < character.max_hp:
            healing_result = await self._apply_rest_healing(
                character, session, action.hours, action.days
            )
            if healing_result:
                result["healing"] = healing_result

        # Check for wandering monsters during time passage
        wandering = await self.check_wandering_monsters(
            session, action.hours, action.days
        )
        if wandering and wandering.triggered:
            result["wandering_encounter"] = {
                "triggered": True,
                "roll": wandering.roll,
                "threshold": wandering.threshold,
                "encounter_name": wandering.encounter_name,
                "creatures": wandering.creatures,
            }

        return result

    async def _apply_rest_healing(
        self,
        character: Character,
        session: Session,
        hours: int,
        days: int,
    ) -> Optional[Dict[str, Any]]:
        """Apply natural healing from rest.

        B/X Rules: 1d3 HP per full day of complete rest.
        House rule: 1 HP per 8 hours of rest (more granular).
        """
        # Calculate healing amount based on rest duration
        # Full day of rest: 1d3 HP
        # Overnight rest (8h): 1 HP guaranteed, +1 on good roll
        total_hours = hours + (days * 24)

        if total_hours < 4:
            # Less than 4 hours - no healing
            return None

        # Calculate healing dice
        if days >= 1:
            # Full day(s) of rest: 1d3 per day
            healing = sum(random.randint(1, 3) for _ in range(days))
            # Add bonus for extra hours
            if hours >= 8:
                healing += 1
        elif total_hours >= 8:
            # Overnight rest: 1 HP + 50% chance of +1
            healing = 1
            if random.randint(1, 2) == 2:
                healing += 1
        elif total_hours >= 4:
            # Short rest (4+ hours): 50% chance of 1 HP
            healing = 1 if random.randint(1, 2) == 2 else 0
        else:
            healing = 0

        if healing <= 0:
            return None

        # Cap healing at missing HP
        missing_hp = character.max_hp - character.current_hp
        healing = min(healing, missing_hp)

        if healing <= 0:
            return None

        logger.info(f"[TIME] Rest healing: +{healing} HP for {character.name}")

        # Apply the healing
        heal_result = await self.tool_handler.execute(
            tool_name="apply_damage_or_healing",
            tool_input={
                "target": character.name,
                "amount": healing,
                "is_healing": True,
                "reason": "natural rest",
            },
            character=character,
            session=session,
        )

        if heal_result.get("error"):
            logger.warning(f"[TIME] Failed to apply rest healing: {heal_result.get('error')}")
            return None

        return {
            "healed": healing,
            "new_hp": heal_result.get("new_hp", character.current_hp + healing),
            "max_hp": character.max_hp,
        }

    def format_time_context(self, time_result: Dict[str, Any]) -> str:
        """Format time passage for DM context.

        Args:
            time_result: Result from advance_time tool

        Returns:
            Formatted context string for DM
        """
        if not time_result:
            return ""

        lines = ["## TIME ADVANCED"]

        new_time = time_result.get("new_time", {})
        if new_time:
            date = new_time.get("formatted_date", "")
            time_of_day = new_time.get("time_of_day", "")
            weather = new_time.get("weather", "")

            if date:
                lines.append(f"Date: {date}")
            if time_of_day:
                lines.append(f"Time: {time_of_day}")
            if weather:
                lines.append(f"Weather: {weather}")

        hours = time_result.get("hours_passed", 0)
        days = time_result.get("days_passed", 0)
        if hours or days:
            time_str = []
            if days:
                time_str.append(f"{days} day(s)")
            if hours:
                time_str.append(f"{hours} hour(s)")
            lines.append(f"Time passed: {' and '.join(time_str)}")

        # Include healing info if rest occurred
        healing = time_result.get("healing")
        if healing:
            healed = healing.get("healed", 0)
            new_hp = healing.get("new_hp", 0)
            max_hp = healing.get("max_hp", 0)
            lines.append(f"**REST HEALING**: Character recovered {healed} HP (now {new_hp}/{max_hp})")
            lines.append("Mention the character feeling refreshed or wounds mending.")

        events = time_result.get("events_triggered", [])
        if events:
            lines.append("Events occurred:")
            for event in events:
                lines.append(f"  - {event}")

        lines.append("")
        lines.append("Incorporate this time passage into your narrative.")
        lines.append("Do NOT call advance_time again - it has already been called.")

        # Include wandering monster encounter if triggered
        encounter = time_result.get("wandering_encounter")
        if encounter and encounter.get("triggered"):
            lines.append("")
            lines.append("## ⚠️ WANDERING MONSTER ENCOUNTER!")
            lines.append(f"Roll: {encounter.get('roll', '?')} (encounter on {encounter.get('threshold', 1)} or less)")
            lines.append(f"Encounter: {encounter.get('encounter_name', 'Unknown')}")
            if encounter.get("creatures"):
                lines.append("Creatures:")
                for creature in encounter["creatures"]:
                    name = creature.get("name", "Unknown")
                    count = creature.get("count", 1)
                    hd = creature.get("hd", "?")
                    lines.append(f"  - {count}x {name} (HD {hd})")
            lines.append("")
            lines.append("**IMPORTANT**: Roleplay this encounter! The creatures appear during the rest/travel.")
            lines.append("Roll for surprise and initiative. Consider calling start_encounter if combat begins.")

        return "\n".join(lines)

    async def check_wandering_monsters(
        self,
        session: Session,
        hours: int,
        days: int,
    ) -> Optional[WanderingEncounter]:
        """Check for wandering monster encounters during time passage.

        B/X Rules: Check once per turn (10 min) in dungeon, 1-in-6 chance.
        For resting: Check once per rest period.

        Args:
            session: Game session with adventure state
            hours: Hours of time passing
            days: Days of time passing

        Returns:
            WanderingEncounter if triggered, None otherwise
        """
        adventure_state = session.adventure_state or {}

        # Only check if in a dungeon/adventure
        if not adventure_state.get("current_location_key"):
            return None

        # Get module ID for wandering monster table
        from sqlalchemy import select
        from app.domains.campaigns.models import Campaign
        from app.domains.adventures.models import AdventureModule

        try:
            # Get campaign's adventure module
            campaign_result = await self.db.execute(
                select(Campaign).where(Campaign.id == session.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if not campaign or not campaign.adventure_document_id:
                return None

            # Get module
            retriever = AdventureDataRetriever(self.db)
            module = await retriever.get_module_for_document(campaign.adventure_document_id)
            if not module:
                return None

            # Get wandering monster table for current area
            tier = adventure_state.get("current_tier")
            dungeon_level = adventure_state.get("current_dungeon_level")

            wandering_table = await retriever.get_wandering_encounter(
                module.id,
                tier=tier,
                dungeon_level=dungeon_level
            )

            if not wandering_table:
                logger.debug("[TIME] No wandering monster table for current area")
                return None

            # Calculate number of checks based on time
            total_hours = hours + (days * 24)

            # In dungeon: check every 2 hours (12 turns)
            # While traveling: check every 4 hours
            # While resting: check once per rest period
            num_checks = max(1, total_hours // 2)

            # Roll for each check
            threshold = wandering_table.get("encounter_chance", 1)  # Default 1-in-6
            die_sides = 6  # Standard d6

            for check in range(num_checks):
                roll = random.randint(1, die_sides)
                if roll <= threshold:
                    # Encounter triggered! Pick a random entry from the table
                    entries = wandering_table.get("entries", [])
                    if not entries:
                        continue

                    # Roll on the table (or pick randomly)
                    die_roll = wandering_table.get("die_roll", "1d6")
                    if "d" in die_roll:
                        parts = die_roll.lower().split("d")
                        num_dice = int(parts[0]) if parts[0] else 1
                        die_size = int(parts[1].split("+")[0].split("-")[0])
                        table_roll = sum(random.randint(1, die_size) for _ in range(num_dice))
                    else:
                        table_roll = random.randint(1, len(entries))

                    # Find matching entry
                    selected_entry = None
                    for entry in entries:
                        roll_range = entry.get("roll_range", "")
                        if "-" in str(roll_range):
                            low, high = map(int, str(roll_range).split("-"))
                            if low <= table_roll <= high:
                                selected_entry = entry
                                break
                        elif str(roll_range) == str(table_roll):
                            selected_entry = entry
                            break

                    if not selected_entry and entries:
                        selected_entry = random.choice(entries)

                    if selected_entry:
                        logger.info(f"[TIME] Wandering monster triggered! Roll {roll}/{threshold}, entry: {selected_entry.get('name', '?')}")
                        return WanderingEncounter(
                            triggered=True,
                            roll=roll,
                            threshold=threshold,
                            encounter_name=selected_entry.get("name", "Unknown Encounter"),
                            creatures=selected_entry.get("creatures", []),
                        )

            # No encounter
            return WanderingEncounter(triggered=False, roll=0, threshold=threshold)

        except Exception as e:
            logger.warning(f"[TIME] Error checking wandering monsters: {e}")
            return None
