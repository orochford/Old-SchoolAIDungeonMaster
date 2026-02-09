"""Combat state machine for deterministic combat tracking.

This manager handles all combat mechanics deterministically:
- Initiative rolling and turn order
- Attack resolution using THAC0
- HP tracking for all participants
- Morale checks
- XP calculation

The LLM narrates combat, but this manager tracks the actual state.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domains.combat.models import (
    CombatEncounter,
    CombatParticipant,
    CombatStatus,
    ParticipantType,
)
from app.domains.characters.models import Character
from app.domains.sessions.models import Session

logger = logging.getLogger(__name__)


@dataclass
class EnemyStats:
    """Stats for an enemy combatant."""

    name: str
    hd: int = 1
    """Hit dice"""

    hp: Optional[int] = None
    """Current HP (auto-calculated from HD if not provided)"""

    max_hp: Optional[int] = None
    """Max HP (auto-calculated from HD if not provided)"""

    ac: int = 9
    """Armor Class (descending, B/X style)"""

    thac0: int = 19
    """To Hit Armor Class 0"""

    damage: str = "1d6"
    """Damage dice notation"""

    morale: int = 7
    """Morale score (2-12)"""

    special: Optional[str] = None
    """Special abilities"""

    xp_value: int = 0
    """XP reward for defeating"""

    @staticmethod
    def _safe_int(value, default):
        """Convert value to int, treating non-numeric strings like 'N/A' as default."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def __post_init__(self):
        # Coerce numeric fields from potential string values (JSONB)
        self.hd = self._safe_int(self.hd, 1)
        self.ac = self._safe_int(self.ac, 9)
        self.thac0 = self._safe_int(self.thac0, 19)
        self.morale = self._safe_int(self.morale, 7)
        self.xp_value = self._safe_int(self.xp_value, 0)
        if self.hp is not None:
            self.hp = self._safe_int(self.hp, None)
        if self.max_hp is not None:
            self.max_hp = self._safe_int(self.max_hp, None)
        # Auto-calculate HP from HD if not provided
        if self.hp is None:
            self.hp = sum(random.randint(1, 8) for _ in range(self.hd))
        if self.max_hp is None:
            self.max_hp = self.hp


@dataclass
class CombatState:
    """Current combat state snapshot."""

    round_number: int = 1
    """Current combat round"""

    is_active: bool = False
    """Whether combat is ongoing"""

    player_initiative: int = 0
    """Player's initiative roll"""

    initiative_order: List[str] = field(default_factory=list)
    """Turn order (names)"""

    current_turn: Optional[str] = None
    """Who's turn it is currently"""

    is_player_turn: bool = False
    """Whether it's the player's turn"""

    enemies: Dict[str, EnemyStats] = field(default_factory=dict)
    """Enemy combatants: {name: EnemyStats}"""

    defeated_enemies: List[str] = field(default_factory=list)
    """Names of defeated enemies"""

    fled_enemies: List[str] = field(default_factory=list)
    """Names of enemies that fled"""

    total_xp_earned: int = 0
    """XP earned from this combat"""

    morale_checked: bool = False
    """Whether morale has been checked this combat (first casualty)"""

    half_casualties_checked: bool = False
    """Whether morale has been checked at half casualties"""


class CombatManager:
    """Manages combat state deterministically.

    This manager:
    1. Starts combat with initiative rolls
    2. Tracks all combatant HP
    3. Resolves attacks using THAC0
    4. Handles morale checks
    5. Calculates XP on combat end

    Usage:
        manager = CombatManager(db)

        # Start combat
        state = await manager.start_combat(session, character, enemies)

        # Resolve an attack
        result = manager.resolve_attack(state, "goblin", target_ac=7, attack_roll=15)

        # Check morale
        flee = manager.check_morale(state, "goblin", 6)

        # End combat
        xp = await manager.end_combat(session, state)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_combat(
        self,
        session: Session,
        character: Character,
        enemies: List[Dict[str, Any]],
    ) -> CombatState:
        """Start a new combat encounter.

        Args:
            session: The game session
            character: The player character
            enemies: List of enemy definitions

        Returns:
            CombatState with initialized combat
        """
        state = CombatState(is_active=True)

        # Roll player initiative (1d6 in B/X)
        state.player_initiative = random.randint(1, 6)

        # Roll enemy initiative (shared for group in B/X)
        enemy_initiative = random.randint(1, 6)

        # Build initiative order
        participants = []

        # Add player
        participants.append({
            "name": character.name,
            "initiative": state.player_initiative,
            "is_player": True,
        })

        # Add enemies
        for enemy_data in enemies:
            enemy_stats = EnemyStats(
                name=enemy_data.get("name", "Enemy"),
                hd=enemy_data.get("hd", 1),
                hp=enemy_data.get("hp"),
                max_hp=enemy_data.get("max_hp"),
                ac=enemy_data.get("ac", 9),
                thac0=enemy_data.get("thac0", 19),
                damage=enemy_data.get("damage", "1d6"),
                morale=enemy_data.get("morale", 7),
                special=enemy_data.get("special"),
                xp_value=enemy_data.get("xp_value", self._calculate_xp_value(enemy_data)),
            )
            state.enemies[enemy_stats.name] = enemy_stats

            participants.append({
                "name": enemy_stats.name,
                "initiative": enemy_initiative,
                "is_player": False,
            })

        # Sort by initiative (higher goes first)
        # In case of tie, players win in B/X (house rule: could use DEX)
        participants.sort(key=lambda p: (p["initiative"], p["is_player"]), reverse=True)

        state.initiative_order = [p["name"] for p in participants]
        state.current_turn = state.initiative_order[0] if state.initiative_order else None
        state.is_player_turn = state.current_turn == character.name

        # Create database record
        encounter = CombatEncounter(
            session_id=session.id,
            name=f"Combat: {', '.join(state.enemies.keys())}",
            status=CombatStatus.ACTIVE,
            current_round=1,
            current_turn_index=0,
            combat_log=[{
                "type": "combat_start",
                "player_initiative": state.player_initiative,
                "enemy_initiative": enemy_initiative,
                "turn_order": state.initiative_order,
            }],
        )
        self.db.add(encounter)
        await self.db.flush()  # Flush to generate encounter.id for FK references

        # Add participants
        for name in state.initiative_order:
            is_player = name == character.name
            if is_player:
                participant = CombatParticipant(
                    encounter_id=encounter.id,
                    character_id=character.id,
                    name=character.name,
                    participant_type=ParticipantType.PLAYER,
                    initiative=state.player_initiative,
                    current_hp=character.current_hp,
                    max_hp=character.max_hp,
                    armor_class=character.attributes.get("armor_class", 9),
                    thac0=character.attributes.get("thac0", 19),
                    is_current_turn=(name == state.current_turn),
                )
            else:
                enemy = state.enemies[name]
                participant = CombatParticipant(
                    encounter_id=encounter.id,
                    name=name,
                    participant_type=ParticipantType.MONSTER,
                    initiative=enemy_initiative,
                    current_hp=enemy.hp,
                    max_hp=enemy.max_hp,
                    armor_class=enemy.ac,
                    thac0=enemy.thac0,
                    morale=enemy.morale,
                    is_current_turn=(name == state.current_turn),
                    stats={
                        "hd": enemy.hd,
                        "damage": enemy.damage,
                        "special": enemy.special,
                        "xp_value": enemy.xp_value,
                    },
                )
            self.db.add(participant)

        # Store combat ID in session
        session.active_combat_id = encounter.id
        await self.db.flush()

        logger.info(
            f"[Combat] Started combat: {len(state.enemies)} enemies, "
            f"player init={state.player_initiative}, turn order={state.initiative_order}"
        )

        return state

    def resolve_attack(
        self,
        attacker_thac0: int,
        target_ac: int,
        attack_roll: int,
        modifiers: int = 0,
    ) -> Dict[str, Any]:
        """Resolve an attack using THAC0.

        Args:
            attacker_thac0: Attacker's THAC0
            target_ac: Target's Armor Class
            attack_roll: The d20 roll
            modifiers: Any modifiers to the attack

        Returns:
            Dict with hit result and details
        """
        # THAC0 formula: need to roll >= (THAC0 - AC)
        target_number = attacker_thac0 - target_ac
        modified_roll = attack_roll + modifiers

        # Natural 20 always hits, natural 1 always misses
        if attack_roll == 20:
            hit = True
            critical = True
        elif attack_roll == 1:
            hit = False
            critical = False
        else:
            hit = modified_roll >= target_number
            critical = False

        return {
            "hit": hit,
            "critical": critical,
            "attack_roll": attack_roll,
            "modifiers": modifiers,
            "modified_roll": modified_roll,
            "target_number": target_number,
            "thac0": attacker_thac0,
            "target_ac": target_ac,
        }

    def roll_damage(self, damage_notation: str) -> int:
        """Roll damage dice.

        Args:
            damage_notation: Dice notation like "1d6", "2d6+2"

        Returns:
            Total damage rolled
        """
        import re

        match = re.match(r'(\d+)d(\d+)([+-]\d+)?', damage_notation)
        if not match:
            return random.randint(1, 6)  # Default fallback

        num_dice = int(match.group(1))
        die_size = int(match.group(2))
        modifier = int(match.group(3) or 0)

        total = sum(random.randint(1, die_size) for _ in range(num_dice))
        return max(0, total + modifier)

    def apply_damage(
        self,
        state: CombatState,
        target_name: str,
        damage: int,
    ) -> Dict[str, Any]:
        """Apply damage to a combatant.

        Args:
            state: Current combat state
            target_name: Name of the target
            damage: Amount of damage

        Returns:
            Dict with old/new HP and status
        """
        if target_name not in state.enemies:
            return {"error": f"Unknown target: {target_name}"}

        enemy = state.enemies[target_name]
        old_hp = enemy.hp
        enemy.hp = max(0, enemy.hp - damage)

        result = {
            "target": target_name,
            "damage": damage,
            "old_hp": old_hp,
            "new_hp": enemy.hp,
            "defeated": enemy.hp <= 0,
        }

        if enemy.hp <= 0:
            state.defeated_enemies.append(target_name)
            state.total_xp_earned += enemy.xp_value
            result["xp_earned"] = enemy.xp_value

            # Check if this was first casualty (morale check trigger)
            if not state.morale_checked and len(state.defeated_enemies) == 1:
                result["trigger_morale_check"] = "first_casualty"
                state.morale_checked = True

            # Check for half casualties
            total_enemies = len(state.enemies)
            defeated_count = len(state.defeated_enemies)
            if not state.half_casualties_checked and defeated_count >= total_enemies / 2:
                result["trigger_morale_check"] = "half_casualties"
                state.half_casualties_checked = True

        logger.info(f"[Combat] {target_name} took {damage} damage: {old_hp} -> {enemy.hp}")

        return result

    def check_morale(
        self,
        state: CombatState,
        enemy_name: str,
        morale_score: int,
    ) -> Dict[str, Any]:
        """Perform a morale check for an enemy.

        Args:
            state: Current combat state
            enemy_name: Name of the enemy
            morale_score: Morale score (2-12)

        Returns:
            Dict with roll and result
        """
        # Roll 2d6
        roll = random.randint(1, 6) + random.randint(1, 6)
        passed = roll <= morale_score

        result = {
            "enemy": enemy_name,
            "morale_score": morale_score,
            "roll": roll,
            "passed": passed,
            "result": "holds" if passed else "flees",
        }

        if not passed and enemy_name in state.enemies:
            state.fled_enemies.append(enemy_name)
            # Grant partial XP for fleeing enemies (half)
            enemy = state.enemies[enemy_name]
            partial_xp = enemy.xp_value // 2
            state.total_xp_earned += partial_xp
            result["xp_earned"] = partial_xp

        logger.info(
            f"[Combat] Morale check for {enemy_name}: "
            f"rolled {roll} vs {morale_score} - {'passed' if passed else 'failed (flees)'}"
        )

        return result

    def advance_turn(
        self,
        state: CombatState,
        character_name: str,
    ) -> Dict[str, Any]:
        """Advance to the next turn in combat.

        Args:
            state: Current combat state
            character_name: Player character name

        Returns:
            Dict with new turn info
        """
        if not state.initiative_order:
            return {"error": "No combatants in initiative order"}

        # Find current position
        try:
            current_idx = state.initiative_order.index(state.current_turn)
        except ValueError:
            current_idx = -1

        # Find next active combatant
        next_idx = (current_idx + 1) % len(state.initiative_order)
        attempts = 0

        while attempts < len(state.initiative_order):
            next_name = state.initiative_order[next_idx]

            # Skip defeated or fled enemies
            if next_name in state.defeated_enemies or next_name in state.fled_enemies:
                next_idx = (next_idx + 1) % len(state.initiative_order)
                attempts += 1
                continue

            break

        # Check if combat should end (all enemies defeated/fled)
        active_enemies = [
            name for name in state.enemies
            if name not in state.defeated_enemies and name not in state.fled_enemies
        ]

        if not active_enemies:
            state.is_active = False
            return {
                "combat_ended": True,
                "reason": "all_enemies_defeated",
                "total_xp": state.total_xp_earned,
            }

        # Check for new round
        new_round = next_idx <= current_idx
        if new_round:
            state.round_number += 1

        state.current_turn = state.initiative_order[next_idx]
        state.is_player_turn = state.current_turn == character_name

        logger.info(
            f"[Combat] Turn advanced: Round {state.round_number}, "
            f"turn: {state.current_turn} (player: {state.is_player_turn})"
        )

        return {
            "round": state.round_number,
            "new_round": new_round,
            "current_turn": state.current_turn,
            "is_player_turn": state.is_player_turn,
            "active_enemies": active_enemies,
        }

    async def end_combat(
        self,
        session: Session,
        state: CombatState,
        outcome: str = "victory",
    ) -> Dict[str, Any]:
        """End the combat encounter.

        Args:
            session: The game session
            state: Final combat state
            outcome: "victory", "defeat", or "fled"

        Returns:
            Dict with combat summary and XP
        """
        state.is_active = False

        # Update database record if exists
        if session.active_combat_id:
            result = await self.db.execute(
                select(CombatEncounter).where(
                    CombatEncounter.id == session.active_combat_id
                )
            )
            encounter = result.scalar_one_or_none()

            if encounter:
                status_map = {
                    "victory": CombatStatus.VICTORY,
                    "defeat": CombatStatus.DEFEAT,
                    "fled": CombatStatus.FLED,
                }
                encounter.status = status_map.get(outcome, CombatStatus.VICTORY)

                # Add combat end to log
                log = list(encounter.combat_log or [])
                log.append({
                    "type": "combat_end",
                    "outcome": outcome,
                    "rounds": state.round_number,
                    "defeated": state.defeated_enemies,
                    "fled": state.fled_enemies,
                    "total_xp": state.total_xp_earned,
                })
                encounter.combat_log = log

            session.active_combat_id = None
            await self.db.flush()

        logger.info(
            f"[Combat] Combat ended: {outcome}, "
            f"{len(state.defeated_enemies)} defeated, "
            f"{len(state.fled_enemies)} fled, "
            f"{state.total_xp_earned} XP earned"
        )

        return {
            "outcome": outcome,
            "rounds": state.round_number,
            "defeated_enemies": state.defeated_enemies,
            "fled_enemies": state.fled_enemies,
            "total_xp": state.total_xp_earned,
        }

    def get_combat_context(self, state: CombatState, character: Character) -> str:
        """Generate combat context for LLM prompt injection.

        Args:
            state: Current combat state
            character: Player character

        Returns:
            Formatted combat context string
        """
        if not state.is_active:
            return ""

        lines = [
            f"Combat Round {state.round_number}",
            f"Current Turn: {state.current_turn}" + (" (player)" if state.is_player_turn else ""),
            "",
            "Combatants:",
            f"  {character.name}: {character.current_hp}/{character.max_hp} HP, AC {character.attributes.get('armor_class', 9)}",
        ]

        for name, enemy in state.enemies.items():
            status = ""
            if name in state.defeated_enemies:
                status = " [defeated]"
            elif name in state.fled_enemies:
                status = " [fled]"
            lines.append(
                f"  {name}: {enemy.hp}/{enemy.max_hp} HP, AC {enemy.ac}, "
                f"THAC0 {enemy.thac0}, Morale {enemy.morale}{status}"
            )

        lines.extend([
            "",
            "Turn Order: " + " → ".join(state.initiative_order),
            "",
            "### MANDATORY COMBAT ACTIONS ###",
        ])

        if state.is_player_turn:
            # Player's turn - describe enemy attack opportunity after player acts
            lines.extend([
                "It is the PLAYER'S turn. After the player declares their action:",
                "1. If player attacks: Call `calculate_thac0` with their roll result to determine hit",
                "2. If hit: Call `roll_dice` for damage, then `apply_damage_or_healing` to the target",
                "3. At the end of their turn: Call `roll_fray_die` (automatic damage to 1HD foes)",
                "4. After player turn: Describe enemy attacks using `roll_dice` for attack and damage",
                "5. If enemy hits player: Call `apply_damage_or_healing` with target='player'",
                "6. At first casualty or 50% casualties: Call `roll_morale` for remaining enemies",
                "",
                "DO NOT ask player to roll dice themselves. YOU process the mechanics using tools.",
            ])
        else:
            # Enemy turn
            active_enemies = [name for name in state.enemies.keys()
                             if name not in state.defeated_enemies and name not in state.fled_enemies]
            if active_enemies:
                lines.extend([
                    f"It is the ENEMY turn. {', '.join(active_enemies)} will attack.",
                    "1. For each enemy: Call `roll_dice` for attack (1d20)",
                    "2. Call `calculate_thac0` to determine if attack hits",
                    "3. If hit: Call `roll_dice` for damage, then `apply_damage_or_healing` target='player'",
                    "4. After all enemy attacks: Player may then act",
                    "",
                    "YOU MUST roll attacks for enemies NOW. Do not wait for player input.",
                ])
            else:
                lines.extend([
                    "All enemies are defeated or fled. Call `end_encounter` with outcome='victory'.",
                ])

        return "\n".join(lines)

    def _calculate_xp_value(self, enemy_data: Dict[str, Any]) -> int:
        """Calculate XP value for an enemy based on HD.

        Uses B/X D&D XP table.
        """
        hd = enemy_data.get("hd", 1)

        # B/X XP table (approximate)
        xp_table = {
            0: 5,    # Less than 1 HD
            1: 10,
            2: 20,
            3: 35,
            4: 75,
            5: 175,
            6: 275,
            7: 450,
            8: 650,
            9: 900,
        }

        if hd < 1:
            return xp_table[0]
        elif hd > 9:
            return 900 + (hd - 9) * 200  # +200 per HD above 9
        else:
            return xp_table.get(hd, hd * 100)
