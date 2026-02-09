"""Combat sub-agent that enforces proper combat mechanics.

When combat is active, this agent takes over combat resolution to ensure
proper tool usage (dice rolls, THAC0 calculations, damage application, etc.)
rather than relying on the main DM LLM to voluntarily use tools.
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
import logging
import re

from app.llm.client import ClaudeClient
from app.llm.tools.handlers import ToolHandler
from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.domains.combat.manager import CombatManager, CombatState, EnemyStats

logger = logging.getLogger(__name__)


@dataclass
class CombatAction:
    """Parsed player combat action."""
    action_type: str  # "attack", "cast", "use_item", "flee", "defend", "other"
    target: Optional[str] = None
    weapon: Optional[str] = None
    spell: Optional[str] = None
    details: Optional[str] = None


@dataclass
class CombatResult:
    """Result of combat resolution."""
    player_attack_roll: Optional[int] = None
    player_hit: Optional[bool] = None
    player_damage: Optional[int] = None
    player_damage_type: Optional[str] = None
    fray_damage: Optional[int] = None
    target_hp_before: Optional[int] = None
    target_hp_after: Optional[int] = None
    target_defeated: bool = False

    enemy_attacks: List[Dict[str, Any]] = None
    player_hp_before: Optional[int] = None
    player_hp_after: Optional[int] = None
    player_hit_by: List[str] = None

    morale_checks: List[Dict[str, Any]] = None
    enemies_fled: List[str] = None
    combat_ended: bool = False
    combat_outcome: Optional[str] = None  # "victory", "defeat", "fled"
    xp_earned: int = 0

    narrative_hints: List[str] = None

    def __post_init__(self):
        if self.enemy_attacks is None:
            self.enemy_attacks = []
        if self.player_hit_by is None:
            self.player_hit_by = []
        if self.morale_checks is None:
            self.morale_checks = []
        if self.enemies_fled is None:
            self.enemies_fled = []
        if self.narrative_hints is None:
            self.narrative_hints = []


class CombatAgent:
    """Sub-agent that handles combat resolution with enforced tool usage."""

    def __init__(self, tool_handler: ToolHandler, db_session):
        self.tool_handler = tool_handler
        self.db = db_session
        self.combat_manager = CombatManager(db_session)

    def parse_player_action(self, player_input: str, character: Character) -> CombatAction:
        """Parse player input to determine combat action type."""
        input_lower = player_input.lower()

        # Check for attack actions
        attack_keywords = ["attack", "hit", "strike", "swing", "stab", "slash", "smash", "bash", "mace", "sword", "axe", "hammer"]
        if any(kw in input_lower for kw in attack_keywords):
            # Try to extract weapon
            weapon = None
            equipped = character.attributes.get('equipped_items', []) or []
            for item in equipped:
                if isinstance(item, dict):
                    item_name = item.get('name', '').lower()
                    if item.get('category') == 'weapon' and item_name in input_lower:
                        weapon = item.get('name')
                        break

            # Default to first equipped weapon if not specified
            if not weapon:
                for item in equipped:
                    if isinstance(item, dict) and item.get('category') == 'weapon':
                        weapon = item.get('name')
                        break

            # Try to extract target
            target = None
            # Common patterns: "attack the X", "hit X", "strike at X"
            target_patterns = [
                r"attack (?:the |a |an )?(\w+)",
                r"hit (?:the |a |an )?(\w+)",
                r"strike (?:at )?(?:the |a |an )?(\w+)",
                r"swing at (?:the |a |an )?(\w+)",
            ]
            for pattern in target_patterns:
                match = re.search(pattern, input_lower)
                if match:
                    target = match.group(1)
                    break

            return CombatAction(
                action_type="attack",
                target=target,
                weapon=weapon,
                details=player_input,
            )

        # Check for spell casting
        spell_keywords = ["cast", "spell", "magic missile", "fireball", "sleep", "charm"]
        if any(kw in input_lower for kw in spell_keywords):
            return CombatAction(
                action_type="cast",
                details=player_input,
            )

        # Check for fleeing
        flee_keywords = ["flee", "run", "retreat", "escape", "disengage"]
        if any(kw in input_lower for kw in flee_keywords):
            return CombatAction(
                action_type="flee",
                details=player_input,
            )

        # Check for defensive actions
        defend_keywords = ["defend", "block", "parry", "dodge", "shield"]
        if any(kw in input_lower for kw in defend_keywords):
            return CombatAction(
                action_type="defend",
                details=player_input,
            )

        # Default to "other" for non-standard actions
        return CombatAction(
            action_type="other",
            details=player_input,
        )

    async def resolve_combat_round(
        self,
        player_action: CombatAction,
        character: Character,
        session: Session,
        combat_state: CombatState,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resolve a round of combat, yielding tool results as they happen.

        This method enforces proper combat mechanics by directly calling
        the appropriate tools rather than hoping the LLM does it.

        Yields:
            Tool result dicts for frontend display
            Final yield is {"type": "combat_result", "result": CombatResult}
        """
        result = CombatResult()

        # Get active enemies
        active_enemies = {
            name: enemy for name, enemy in combat_state.enemies.items()
            if name not in combat_state.defeated_enemies
            and name not in combat_state.fled_enemies
        }

        if not active_enemies:
            # No enemies left - end combat
            result.combat_ended = True
            result.combat_outcome = "victory"
            await self._end_combat(session, "victory")
            yield {"type": "combat_ended", "outcome": "victory"}
            yield {"type": "combat_result", "result": result}
            return  # Early exit - combat is over

        # Determine turn order based on initiative
        player_first = combat_state.is_player_turn

        if player_first:
            # Player acts first
            async for tool_result in self._resolve_player_action(
                player_action, character, session, combat_state, active_enemies, result
            ):
                yield tool_result

            # Then enemies act (if player didn't flee and combat continues)
            if not result.combat_ended and player_action.action_type != "flee":
                async for tool_result in self._resolve_enemy_attacks(
                    character, session, combat_state, active_enemies, result
                ):
                    yield tool_result
        else:
            # Enemies act first
            async for tool_result in self._resolve_enemy_attacks(
                character, session, combat_state, active_enemies, result
            ):
                yield tool_result

            # Then player acts (if not defeated)
            if not result.combat_ended:
                async for tool_result in self._resolve_player_action(
                    player_action, character, session, combat_state, active_enemies, result
                ):
                    yield tool_result

        # Check for combat end conditions
        if result.player_hp_after is not None and result.player_hp_after <= 0:
            result.combat_ended = True
            result.combat_outcome = "defeat"
            await self._end_combat(session, "defeat")
            yield {"type": "combat_ended", "outcome": "defeat"}

        # Yield the final combat result
        yield {"type": "combat_result", "result": result}

    async def _resolve_player_action(
        self,
        action: CombatAction,
        character: Character,
        session: Session,
        combat_state: CombatState,
        active_enemies: Dict[str, EnemyStats],
        result: CombatResult,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resolve the player's combat action."""

        if action.action_type == "attack":
            # Determine target
            target_name = action.target
            if not target_name or target_name not in active_enemies:
                # Default to first active enemy
                target_name = list(active_enemies.keys())[0]

            target = active_enemies[target_name]
            weapon_name = action.weapon or "weapon"

            # Get character's THAC0
            thac0 = character.attributes.get('thac0', 19)

            # Roll attack
            attack_result = await self.tool_handler.execute(
                tool_name="roll_dice",
                tool_input={
                    "notation": "1d20",
                    "purpose": f"{character.name} attack roll with {weapon_name} vs {target_name}",
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "roll_dice", "result": attack_result}

            attack_roll = attack_result.get("total", 0)
            result.player_attack_roll = attack_roll

            # Calculate if hit using THAC0
            thac0_result = await self.tool_handler.execute(
                tool_name="calculate_thac0",
                tool_input={
                    "attacker_thac0": thac0,
                    "target_ac": target.ac,
                    "attack_roll": attack_roll,
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "calculate_thac0", "result": thac0_result}

            hit = thac0_result.get("hit", False)
            result.player_hit = hit

            if hit:
                # Roll damage
                damage_dice = self._get_weapon_damage(character, action.weapon)
                damage_result = await self.tool_handler.execute(
                    tool_name="roll_dice",
                    tool_input={
                        "notation": damage_dice,
                        "purpose": f"{weapon_name} damage vs {target_name}",
                    },
                    character=character,
                    session=session,
                )
                yield {"type": "tool_result", "tool_name": "roll_dice", "result": damage_result}

                damage = damage_result.get("total", 0)
                result.player_damage = damage
                result.target_hp_before = target.hp

                # Apply damage
                apply_result = await self.tool_handler.execute(
                    tool_name="apply_damage_or_healing",
                    tool_input={
                        "target": target_name,
                        "amount": damage,
                        "damage_type": "bludgeoning",
                        "source": weapon_name,
                    },
                    character=character,
                    session=session,
                )
                yield {"type": "tool_result", "tool_name": "apply_damage_or_healing", "result": apply_result}

                result.target_hp_after = apply_result.get("new_hp", target.hp - damage)

                # Check if target defeated
                if result.target_hp_after <= 0:
                    result.target_defeated = True
                    result.narrative_hints.append(f"{target_name} falls!")

                    # Check morale for remaining enemies
                    remaining = [n for n in active_enemies if n != target_name]
                    if remaining:
                        async for morale_result in self._check_morale(
                            character, session, remaining, active_enemies, result, "first casualty"
                        ):
                            yield morale_result

            # Roll fray die (automatic damage to 1HD foes)
            fray_result = await self.tool_handler.execute(
                tool_name="roll_fray_die",
                tool_input={
                    "target_description": "nearby 1HD foes",
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "roll_fray_die", "result": fray_result}
            result.fray_damage = fray_result.get("damage", 0)

        elif action.action_type == "flee":
            result.combat_ended = True
            result.combat_outcome = "fled"
            await self._end_combat(session, "fled")
            yield {"type": "combat_ended", "outcome": "fled"}

        elif action.action_type == "defend":
            result.narrative_hints.append(f"{character.name} takes a defensive stance")
            # Could add AC bonus here in future

        else:
            # Other actions - just note them
            result.narrative_hints.append(f"{character.name}: {action.details}")

    async def _resolve_enemy_attacks(
        self,
        character: Character,
        session: Session,
        combat_state: CombatState,
        active_enemies: Dict[str, EnemyStats],
        result: CombatResult,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resolve all enemy attacks against the player."""

        result.player_hp_before = character.current_hp
        player_ac = character.attributes.get('armor_class', 9)

        for enemy_name, enemy in active_enemies.items():
            if enemy_name in combat_state.defeated_enemies:
                continue
            if enemy_name in combat_state.fled_enemies:
                continue

            enemy_attack = {
                "attacker": enemy_name,
                "roll": 0,
                "hit": False,
                "damage": 0,
            }

            # Roll enemy attack
            attack_result = await self.tool_handler.execute(
                tool_name="roll_dice",
                tool_input={
                    "notation": "1d20",
                    "purpose": f"{enemy_name} attack roll vs {character.name}",
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "roll_dice", "result": attack_result}

            attack_roll = attack_result.get("total", 0)
            enemy_attack["roll"] = attack_roll

            # Calculate hit
            thac0_result = await self.tool_handler.execute(
                tool_name="calculate_thac0",
                tool_input={
                    "attacker_thac0": enemy.thac0,
                    "target_ac": player_ac,
                    "attack_roll": attack_roll,
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "calculate_thac0", "result": thac0_result}

            hit = thac0_result.get("hit", False)
            enemy_attack["hit"] = hit

            if hit:
                # Roll damage
                damage_result = await self.tool_handler.execute(
                    tool_name="roll_dice",
                    tool_input={
                        "notation": enemy.damage,
                        "purpose": f"{enemy_name} damage vs {character.name}",
                    },
                    character=character,
                    session=session,
                )
                yield {"type": "tool_result", "tool_name": "roll_dice", "result": damage_result}

                damage = damage_result.get("total", 0)
                enemy_attack["damage"] = damage

                # Apply damage to player
                apply_result = await self.tool_handler.execute(
                    tool_name="apply_damage_or_healing",
                    tool_input={
                        "target": "player",
                        "amount": damage,
                        "damage_type": "slashing",
                        "source": enemy_name,
                    },
                    character=character,
                    session=session,
                )
                yield {"type": "tool_result", "tool_name": "apply_damage_or_healing", "result": apply_result}

                result.player_hit_by.append(enemy_name)
                result.player_hp_after = apply_result.get("new_hp", character.current_hp - damage)

            result.enemy_attacks.append(enemy_attack)

        if result.player_hp_after is None:
            result.player_hp_after = character.current_hp

    async def _check_morale(
        self,
        character: Character,
        session: Session,
        enemy_names: List[str],
        active_enemies: Dict[str, EnemyStats],
        result: CombatResult,
        reason: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Check morale for specified enemies."""

        for enemy_name in enemy_names:
            if enemy_name not in active_enemies:
                continue

            enemy = active_enemies[enemy_name]

            morale_result = await self.tool_handler.execute(
                tool_name="roll_morale",
                tool_input={
                    "creature_name": enemy_name,
                    "morale_score": enemy.morale,
                    "reason": reason,
                },
                character=character,
                session=session,
            )
            yield {"type": "tool_result", "tool_name": "roll_morale", "result": morale_result}

            morale_check = {
                "enemy": enemy_name,
                "roll": morale_result.get("roll", 0),
                "morale_score": enemy.morale,
                "fled": morale_result.get("result") == "fled",
            }
            result.morale_checks.append(morale_check)

            if morale_check["fled"]:
                result.enemies_fled.append(enemy_name)
                result.narrative_hints.append(f"{enemy_name} breaks and flees!")

    async def _end_combat(self, session: Session, outcome: str) -> None:
        """End the current combat encounter."""
        await self.tool_handler.execute(
            tool_name="end_encounter",
            tool_input={"outcome": outcome},
            character=None,  # Not needed for end_encounter
            session=session,
        )

    def _get_weapon_damage(self, character: Character, weapon_name: Optional[str]) -> str:
        """Get the damage dice for a weapon."""
        equipped = character.attributes.get('equipped_items', []) or []

        if weapon_name:
            for item in equipped:
                if isinstance(item, dict):
                    if item.get('name', '').lower() == weapon_name.lower():
                        return item.get('damage', '1d6')

        # Look for any equipped weapon
        for item in equipped:
            if isinstance(item, dict) and item.get('category') == 'weapon':
                return item.get('damage', '1d6')

        # Default to unarmed
        return "1d2"

    def format_combat_result_for_dm(self, result: CombatResult, character: Character) -> str:
        """Format combat results as context for the DM to narrate."""
        lines = ["## COMBAT RESOLUTION (narrate these events)"]

        if result.player_hit is not None:
            if result.player_hit:
                lines.append(f"- {character.name} HIT with attack roll {result.player_attack_roll}")
                lines.append(f"- Dealt {result.player_damage} damage")
                if result.target_defeated:
                    lines.append(f"- Target DEFEATED (HP: {result.target_hp_before} -> {result.target_hp_after})")
                else:
                    lines.append(f"- Target wounded (HP: {result.target_hp_before} -> {result.target_hp_after})")
            else:
                lines.append(f"- {character.name} MISSED with attack roll {result.player_attack_roll}")

        if result.fray_damage:
            lines.append(f"- Fray die dealt {result.fray_damage} to nearby weak foes")

        for attack in result.enemy_attacks:
            if attack["hit"]:
                lines.append(f"- {attack['attacker']} HIT {character.name} for {attack['damage']} damage")
            else:
                lines.append(f"- {attack['attacker']} MISSED {character.name} (rolled {attack['roll']})")

        if result.player_hp_after is not None:
            lines.append(f"- {character.name} HP: {result.player_hp_before} -> {result.player_hp_after}")

        for check in result.morale_checks:
            if check["fled"]:
                lines.append(f"- {check['enemy']} FAILED morale and fled!")
            else:
                lines.append(f"- {check['enemy']} passed morale check")

        if result.combat_ended:
            lines.append(f"- COMBAT ENDED: {result.combat_outcome}")
            if result.xp_earned:
                lines.append(f"- XP earned: {result.xp_earned}")

        for hint in result.narrative_hints:
            lines.append(f"- {hint}")

        lines.append("")
        lines.append("Describe these events dramatically. Do NOT re-roll any dice.")

        return "\n".join(lines)
