"""Tool execution handlers for the LLM DM."""

import random
import re
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.characters.models import Character
from app.domains.sessions.models import Session
from app.rag.retriever import RAGRetriever


class ToolHandler:
    """Handles execution of DM tools."""

    # Mythic GME Fate Chart thresholds
    FATE_CHART = {
        # odds: [CF1, CF2, CF3, CF4, CF5, CF6, CF7, CF8, CF9]
        "impossible": [-20, 0, 0, 0, 5, 5, 10, 10, 15],
        "no_way": [0, 5, 5, 10, 10, 15, 20, 25, 30],
        "very_unlikely": [5, 10, 10, 15, 20, 25, 30, 35, 45],
        "unlikely": [10, 15, 20, 25, 30, 35, 45, 50, 55],
        "fifty_fifty": [15, 25, 30, 35, 45, 50, 55, 65, 75],
        "somewhat_likely": [20, 30, 35, 45, 50, 55, 65, 75, 80],
        "likely": [25, 35, 45, 50, 55, 65, 75, 80, 85],
        "very_likely": [30, 45, 50, 55, 65, 75, 80, 85, 90],
        "near_sure_thing": [35, 50, 55, 65, 75, 80, 85, 90, 95],
        "sure_thing": [45, 55, 65, 75, 80, 85, 90, 95, 100],
        "has_to_be": [50, 65, 75, 80, 85, 90, 95, 100, 115],
    }

    EVENT_FOCUS = [
        (7, "Remote Event"),
        (28, "NPC Action"),
        (35, "Introduce New NPC"),
        (45, "Move Toward Thread"),
        (52, "Move Away from Thread"),
        (55, "Close Thread"),
        (67, "PC Negative"),
        (75, "PC Positive"),
        (83, "Ambiguous Event"),
        (92, "NPC Negative"),
        (100, "NPC Positive"),
    ]

    ACTION_WORDS = [
        "Attainment", "Starting", "Neglect", "Fight", "Recruit",
        "Triumph", "Violate", "Oppose", "Malice", "Communicate",
        "Persecute", "Increase", "Decrease", "Abandon", "Gratify",
        "Inquire", "Antagonize", "Move", "Waste", "Truce",
        "Release", "Befriend", "Judge", "Desert", "Dominate",
        "Procrastinate", "Praise", "Separate", "Take", "Break",
        "Heal", "Delay", "Stop", "Lie", "Return",
        "Imitate", "Struggle", "Inform", "Bestow", "Postpone",
        "Expose", "Haggle", "Imprison", "Release", "Celebrate",
        "Develop", "Travel", "Block", "Harm", "Debase",
    ]

    SUBJECT_WORDS = [
        "Goals", "Dreams", "Environment", "Outside", "Inside",
        "Reality", "Allies", "Enemies", "Evil", "Good",
        "Emotions", "Opposition", "War", "Peace", "The Innocent",
        "Love", "The Spiritual", "The Intellectual", "New Ideas", "Joy",
        "Messages", "Energy", "Balance", "Tension", "Friendship",
        "The Physical", "A Project", "Pleasures", "Pain", "Possessions",
        "Status Quo", "Technology", "Hope", "Magic", "Illusions",
        "Portals", "Danger", "Weapons", "Animals", "Weather",
        "Elements", "Nature", "The Public", "Leadership", "Fame",
        "Anger", "Information", "Extravagance", "A Plot", "Expectations",
    ]

    @staticmethod
    def _safe_int(value, default):
        """Convert value to int, treating non-numeric strings like 'N/A' as default."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def __init__(self, session: AsyncSession):
        self.db = session
        self.retriever = RAGRetriever(session)

    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        handlers = {
            "roll_dice": self._roll_dice,
            "lookup_rule": self._lookup_rule,
            "query_character": self._query_character,
            "update_game_state": self._update_game_state,
            "apply_damage_or_healing": self._apply_damage_or_healing,
            "roll_morale": self._roll_morale,
            "roll_reaction": self._roll_reaction,
            "calculate_thac0": self._calculate_thac0,
            "award_xp": self._award_xp,
            "oracle_query": self._oracle_query,
            "random_event": self._random_event,
            # Adventure tools
            "advance_scene": self._advance_scene,
            "update_plot_thread": self._update_plot_thread,
            "record_npc_encounter": self._record_npc_encounter,
            "update_adventure_location": self._update_adventure_location,
            "update_subarea_position": self._update_subarea_position,
            "add_item": self._add_item,
            # Journal tools
            "query_journal": self._query_journal,
            "record_discovery": self._record_discovery,
            "query_world_state": self._query_world_state,
            # Solo Hero tools
            "convert_damage_to_harm": self._convert_damage_to_harm,
            "roll_fray_die": self._roll_fray_die,
            "defy_death": self._defy_death,
            "roll_trait_check": self._roll_trait_check,
            # Calendar tools
            "advance_time": self._advance_time,
            "get_current_time": self._get_current_time,
            "schedule_event": self._schedule_event,
            "check_upcoming_events": self._check_upcoming_events,
            # Map tools
            "display_map": self._display_map,
            "update_map_position": self._update_map_position,
            "add_map_marker": self._add_map_marker,
            "create_map": self._create_map,
            # Encounter tools
            "start_encounter": self._start_encounter,
            "end_encounter": self._end_encounter,
            # Image tools
            "show_illustration": self._show_illustration,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        return await handler(tool_input, character, session)

    # Purposes that indicate DM-only rolls (not visible to players)
    DM_ONLY_PURPOSES = [
        "search", "find traps", "listen", "surprise", "secret",
        "hidden", "perception", "detect", "hear noise", "spot",
    ]

    async def _roll_dice(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Roll dice using standard notation."""
        notation = input.get("notation", "1d6")
        purpose = input.get("purpose", "unknown")

        # Parse dice notation (e.g., "2d6+3", "1d20-1", "3d8")
        match = re.match(r'(\d+)d(\d+)([+-]\d+)?', notation)
        if not match:
            return {"error": f"Invalid dice notation: {notation}"}

        num_dice = int(match.group(1))
        die_size = int(match.group(2))
        modifier = int(match.group(3) or 0)

        # Roll the dice
        rolls = [random.randint(1, die_size) for _ in range(num_dice)]
        total = sum(rolls) + modifier

        # Determine if this roll should be visible to players
        purpose_lower = purpose.lower()
        is_dm_only = any(dm_purpose in purpose_lower for dm_purpose in self.DM_ONLY_PURPOSES)

        return {
            "notation": notation,
            "purpose": purpose,
            "rolls": rolls,
            "modifier": modifier,
            "total": total,
            "natural_20": die_size == 20 and num_dice == 1 and rolls[0] == 20,
            "natural_1": die_size == 20 and num_dice == 1 and rolls[0] == 1,
            "visible": not is_dm_only,
        }

    async def _lookup_rule(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Look up a rule from the sourcebooks."""
        query = input.get("query", "")

        context = await self.retriever.get_context_for_dm(
            query=query,
            rpg_system_id=character.rpg_system_id,
            max_chunks=3,
        )

        return {
            "query": query,
            "rules_found": context,
            "visible": False,  # Internal DM reference
        }

    async def _query_character(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Get character information."""
        aspect = input.get("aspect", "all")

        result = {
            "name": character.name,
            "level": character.level,
        }

        if aspect in ["stats", "all"]:
            result["stats"] = {
                "hp": f"{character.current_hp}/{character.max_hp}",
                "xp": character.experience_points,
                **character.attributes,
            }

        if aspect in ["inventory", "all"]:
            # TODO: Fetch inventory from database instead of character.attributes
            # Currently items are stored in character.attributes["equipment"] as JSON
            # Should use a proper Inventory table for:
            # - Better querying and filtering
            # - Item weight/encumbrance tracking
            # - Item condition/charges tracking
            # - Proper foreign keys to item definitions
            result["inventory"] = character.attributes.get("equipment", [])

        if aspect in ["spells", "all"]:
            result["spells"] = character.attributes.get("spells_memorized", [])

        if aspect in ["abilities", "all"]:
            result["abilities"] = character.attributes.get("abilities", [])

        if aspect in ["conditions", "all"]:
            result["conditions"] = session.game_state.get("conditions", []) if session.game_state else []

        result["visible"] = False  # Internal DM information gathering
        return result

    async def _update_game_state(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Update the game state."""
        if not session.game_state:
            session.game_state = {}

        updates = {}

        if "location" in input:
            session.current_location = input["location"]
            session.game_state["location"] = input["location"]
            updates["location"] = input["location"]

        if "add_condition" in input:
            conditions = session.game_state.get("conditions", [])
            if input["add_condition"] not in conditions:
                conditions.append(input["add_condition"])
                session.game_state["conditions"] = conditions
                updates["added_condition"] = input["add_condition"]

        if "remove_condition" in input:
            conditions = session.game_state.get("conditions", [])
            if input["remove_condition"] in conditions:
                conditions.remove(input["remove_condition"])
                session.game_state["conditions"] = conditions
                updates["removed_condition"] = input["remove_condition"]

        if "flags" in input:
            flags = session.game_state.get("flags", {})
            flags.update(input["flags"])
            session.game_state["flags"] = flags
            updates["flags_updated"] = list(input["flags"].keys())

        await self.db.flush()

        return {
            "success": True,
            "updates": updates,
            "visible": True,  # Show game state updates in frontend
        }

    async def _apply_damage_or_healing(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Apply damage or healing."""
        target = input.get("target", "player")
        amount = input.get("amount", 0)
        damage_type = input.get("damage_type", "untyped")
        source = input.get("source", "unknown")

        if target.lower() == "player":
            old_hp = character.current_hp
            character.current_hp = max(0, min(character.max_hp, character.current_hp - amount))
            new_hp = character.current_hp

            await self.db.flush()

            result = {
                "target": character.name,
                "old_hp": old_hp,
                "new_hp": new_hp,
                "change": -amount if amount > 0 else abs(amount),
                "damage_type": damage_type,
                "source": source,
            }

            if new_hp <= 0:
                result["status"] = "unconscious_or_dead"
            elif amount > 0:
                result["status"] = "damaged"
            else:
                result["status"] = "healed"

            # Sync player CombatParticipant if encounter active
            if session.active_combat_id:
                await self._sync_participant_hp(
                    session.active_combat_id, character.name, new_hp
                )

            return result
        else:
            # NPC/monster damage - track in game state
            if not session.game_state:
                session.game_state = {}

            npcs = session.game_state.get("npcs", {})
            npc = npcs.get(target, {"hp": 10, "max_hp": 10})
            old_hp = npc.get("hp", 10)
            npc["hp"] = max(0, npc.get("hp", 10) - amount)
            npcs[target] = npc
            session.game_state["npcs"] = npcs

            await self.db.flush()

            # Sync NPC CombatParticipant if encounter active
            if session.active_combat_id:
                await self._sync_participant_hp(
                    session.active_combat_id, target, npc["hp"],
                    mark_defeated=(npc["hp"] <= 0),
                )

            return {
                "target": target,
                "old_hp": old_hp,
                "new_hp": npc["hp"],
                "change": -amount,
                "status": "dead" if npc["hp"] <= 0 else "damaged",
            }

    async def _roll_morale(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Roll a B/X morale check."""
        creature_name = input.get("creature_name", "creature")
        morale_score = input.get("morale_score", 7)
        reason = input.get("reason", "combat")

        # Roll 2d6
        roll = random.randint(1, 6) + random.randint(1, 6)
        passed = roll <= morale_score

        result = {
            "creature": creature_name,
            "morale_score": morale_score,
            "roll": roll,
            "passed": passed,
            "reason": reason,
            "result": "holds firm" if passed else "breaks and flees",
            "visible": False,  # DM mechanic - hide by default
        }

        # Sync morale_broken to CombatParticipant if encounter active
        if not passed and session.active_combat_id:
            await self._sync_participant_morale_broken(
                session.active_combat_id, creature_name
            )

        return result

    async def _roll_reaction(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Roll a B/X reaction roll."""
        npc_name = input.get("npc_name", "creature")
        cha_modifier = input.get("cha_modifier", 0)
        context = input.get("context", "")

        # Roll 2d6 + CHA modifier
        roll = random.randint(1, 6) + random.randint(1, 6)
        modified_roll = roll + cha_modifier

        # Interpret result
        if modified_roll <= 2:
            reaction = "hostile"
            description = "Attacks immediately"
        elif modified_roll <= 5:
            reaction = "unfriendly"
            description = "Hostile, may attack"
        elif modified_roll <= 8:
            reaction = "neutral"
            description = "Uncertain, will consider offers"
        elif modified_roll <= 11:
            reaction = "friendly"
            description = "No attack, may be helpful"
        else:
            reaction = "enthusiastic"
            description = "Eager to help, potential ally"

        return {
            "npc": npc_name,
            "roll": roll,
            "cha_modifier": cha_modifier,
            "modified_roll": modified_roll,
            "reaction": reaction,
            "description": description,
            "context": context,
            "visible": False,  # DM mechanic - hide by default
        }

    async def _calculate_thac0(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Calculate if an attack hits using THAC0."""
        thac0 = input.get("attacker_thac0", 19)
        target_ac = input.get("target_ac", 9)
        attack_roll = input.get("attack_roll", 10)
        modifiers = input.get("modifiers", 0)

        # To hit: roll + modifiers >= THAC0 - target_ac
        # Or equivalently: roll >= THAC0 - target_ac - modifiers
        target_number = thac0 - target_ac
        modified_roll = attack_roll + modifiers
        hit = modified_roll >= target_number

        # Natural 20 always hits, natural 1 always misses
        if attack_roll == 20:
            hit = True
        elif attack_roll == 1:
            hit = False

        return {
            "thac0": thac0,
            "target_ac": target_ac,
            "attack_roll": attack_roll,
            "modifiers": modifiers,
            "target_number": target_number,
            "modified_roll": modified_roll,
            "hit": hit,
            "natural_20": attack_roll == 20,
            "natural_1": attack_roll == 1,
        }

    async def _award_xp(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Award XP to the character."""
        amount = input.get("amount", 0)
        source = input.get("source", "adventure")

        # Apply prime requisite bonus
        pr_bonus = character.attributes.get("prime_requisite_bonus", 0)
        if pr_bonus:
            bonus_xp = int(amount * pr_bonus / 100)
            amount += bonus_xp

        old_xp = character.experience_points
        character.experience_points += amount

        await self.db.flush()

        # Check for level up (would need XP tables)
        # For now, just return the update

        return {
            "old_xp": old_xp,
            "xp_gained": amount,
            "new_xp": character.experience_points,
            "source": source,
            "prime_requisite_bonus": pr_bonus,
        }

    async def _oracle_query(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Query the Mythic GME oracle for a yes/no question."""
        question = input.get("question", "")
        odds = input.get("odds", "fifty_fifty")
        chaos_factor = input.get("chaos_factor", 5)

        # Clamp chaos factor
        chaos_factor = max(1, min(9, chaos_factor))

        # Get threshold from fate chart
        thresholds = self.FATE_CHART.get(odds, self.FATE_CHART["fifty_fifty"])
        threshold = thresholds[chaos_factor - 1]

        # Roll d100
        roll = random.randint(1, 100)

        # Determine result
        exceptional_yes_threshold = threshold // 5
        exceptional_no_threshold = 100 - exceptional_yes_threshold

        if roll <= exceptional_yes_threshold and roll <= threshold:
            result = "exceptional_yes"
            answer = "Yes, and..."
        elif roll <= threshold:
            result = "yes"
            answer = "Yes"
        elif roll > exceptional_no_threshold and roll > threshold:
            result = "exceptional_no"
            answer = "No, and..."
        else:
            result = "no"
            answer = "No"

        # Check for random event (doubles and roll <= chaos * 11)
        is_doubles = (roll % 11 == 0 and roll <= 99)  # 11, 22, 33, etc.
        random_event_triggered = is_doubles and roll <= (chaos_factor * 11)

        return {
            "question": question,
            "odds": odds,
            "chaos_factor": chaos_factor,
            "threshold": threshold,
            "roll": roll,
            "result": result,
            "answer": answer,
            "random_event_triggered": random_event_triggered,
        }

    async def _random_event(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Generate a random event using Mythic GME tables."""
        context = input.get("context", "")

        # Roll for event focus
        focus_roll = random.randint(1, 100)
        event_focus = "Unknown"
        for threshold, focus in self.EVENT_FOCUS:
            if focus_roll <= threshold:
                event_focus = focus
                break

        # Roll for event meaning (action + subject)
        action_index = random.randint(0, len(self.ACTION_WORDS) - 1)
        subject_index = random.randint(0, len(self.SUBJECT_WORDS) - 1)

        action = self.ACTION_WORDS[action_index]
        subject = self.SUBJECT_WORDS[subject_index]

        return {
            "context": context,
            "focus_roll": focus_roll,
            "event_focus": event_focus,
            "action": action,
            "subject": subject,
            "event_meaning": f"{action} + {subject}",
            "interpretation_hint": f"A '{event_focus}' involving the concept of '{action}' related to '{subject}'. Interpret creatively based on current scene.",
        }

    # Adventure-specific tool handlers

    async def _advance_scene(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Mark a scene as complete and advance to the next."""
        from datetime import datetime
        from app.domains.sessions.adventure_state import advance_scene as do_advance_scene

        scene_completed = input.get("scene_completed", "")
        outcome = input.get("outcome", "")
        next_scene = input.get("next_scene", "")

        # Get current adventure state
        adventure_state = session.adventure_state or {}

        # Update adventure state
        new_state = do_advance_scene(
            state=adventure_state,
            completed_scene=scene_completed,
            outcome=outcome,
            next_scene=next_scene if next_scene != "continue" else None,
        )

        # Save to session
        session.adventure_state = new_state
        await self.db.flush()

        return {
            "success": True,
            "scene_completed": scene_completed,
            "outcome": outcome,
            "current_scene": new_state.get("current_scene", ""),
            "completed_count": len(new_state.get("completed_scenes", [])),
            "visible": False,  # Internal DM state management
        }

    async def _update_plot_thread(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Update a plot thread in the adventure."""
        from app.domains.sessions.adventure_state import update_plot_thread as do_update_thread

        thread_name = input.get("thread_name", "")
        status = input.get("status", "active")
        notes = input.get("notes", "")

        # Get current adventure state
        adventure_state = session.adventure_state or {}

        # Update adventure state
        new_state = do_update_thread(
            state=adventure_state,
            thread_name=thread_name,
            status=status,
            notes=notes,
        )

        # Save to session
        session.adventure_state = new_state
        await self.db.flush()

        return {
            "success": True,
            "thread_name": thread_name,
            "status": status,
            "notes": notes,
            "visible": False,  # Internal DM state management
        }

    async def _record_npc_encounter(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Record an NPC encounter."""
        from app.domains.sessions.adventure_state import record_npc_encounter as do_record_npc

        npc_name = input.get("npc_name", "")
        attitude = input.get("attitude", "neutral")
        notes = input.get("notes", "")

        # Get current adventure state
        adventure_state = session.adventure_state or {}

        # Update adventure state
        new_state = do_record_npc(
            state=adventure_state,
            npc_name=npc_name,
            attitude=attitude,
            notes=notes,
        )

        # Save to session
        session.adventure_state = new_state
        await self.db.flush()

        return {
            "success": True,
            "npc_name": npc_name,
            "attitude": attitude,
            "notes": notes,
            "first_encounter": npc_name not in (adventure_state.get("npcs_encountered") or {}),
            "visible": False,  # Internal DM state management
        }

    async def _update_adventure_location(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Update the current location in the adventure."""
        from datetime import datetime
        from sqlalchemy import select
        from app.domains.journal.models import WorldLocation
        from app.domains.adventures.models import AdventureModule, AdventureLocation
        from app.domains.campaigns.models import Campaign

        location = input.get("location", "")
        location_key = input.get("location_key")

        # Get current adventure state
        adventure_state = dict(session.adventure_state or {})

        # Track previous location
        previous_location = adventure_state.get("current_location", "")
        previous_key = adventure_state.get("current_location_key", "")

        # Try to find/validate location_key from the adventure module
        matched_location = None
        if session.campaign_id:
            # Get campaign to find adventure document
            campaign_result = await self.db.execute(
                select(Campaign).where(Campaign.id == session.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()

            if campaign and campaign.adventure_document_id:
                # Get the adventure module
                module_result = await self.db.execute(
                    select(AdventureModule).where(
                        AdventureModule.pdf_document_id == campaign.adventure_document_id
                    )
                )
                module = module_result.scalar_one_or_none()

                if module:
                    # Try to find the location in the module
                    if location_key:
                        # Direct key lookup
                        loc_result = await self.db.execute(
                            select(AdventureLocation).where(
                                AdventureLocation.module_id == module.id,
                                AdventureLocation.location_key == location_key
                            )
                        )
                        matched_location = loc_result.scalar_one_or_none()

                    if not matched_location and location:
                        # Try to match by name (case-insensitive partial match)
                        loc_result = await self.db.execute(
                            select(AdventureLocation).where(
                                AdventureLocation.module_id == module.id
                            )
                        )
                        all_locations = list(loc_result.scalars().all())

                        location_lower = location.lower().strip()
                        for loc in all_locations:
                            if loc.name and loc.name.lower().strip() == location_lower:
                                matched_location = loc
                                location_key = loc.location_key
                                break

                        # If no exact match, try partial match
                        if not matched_location:
                            for loc in all_locations:
                                if loc.name and location_lower in loc.name.lower():
                                    matched_location = loc
                                    location_key = loc.location_key
                                    break

        # Update location
        adventure_state["current_location"] = location
        adventure_state["last_updated"] = datetime.utcnow().isoformat()

        # Set location_key if we have it
        if location_key:
            adventure_state["current_location_key"] = location_key
        elif matched_location:
            adventure_state["current_location_key"] = matched_location.location_key

        # Set tier and dungeon level for wandering monster tables
        if matched_location:
            if matched_location.tier:
                adventure_state["current_tier"] = matched_location.tier
            if matched_location.dungeon_level:
                adventure_state["current_dungeon_level"] = matched_location.dungeon_level

        # Track visited locations for map display
        visited = adventure_state.get("visited_locations", [])
        current_key = adventure_state.get("current_location_key")
        if current_key and current_key not in visited:
            visited.append(current_key)
            adventure_state["visited_locations"] = visited

        # Reset sub-area tracking when entering a new location
        # The DM will update current_subarea as player progresses through the location
        if current_key != adventure_state.get("previous_location_key"):
            adventure_state["previous_location_key"] = current_key
            adventure_state["current_subarea"] = None  # Will be set by DM based on entry point
            adventure_state["current_subarea_name"] = None
            adventure_state["subareas_visited"] = []  # Reset for new location
            adventure_state["triggered_content"] = []  # Reset triggered content for new location

        # Save to session
        session.adventure_state = adventure_state

        # Create or update WorldLocation for mapping
        is_new_location = False
        result = await self.db.execute(
            select(WorldLocation)
            .where(WorldLocation.campaign_id == session.campaign_id)
            .where(WorldLocation.name == location)
        )
        world_loc = result.scalar_one_or_none()

        if not world_loc:
            # New location - create it
            world_loc = WorldLocation(
                campaign_id=session.campaign_id,
                name=location,
                location_type="adventure",
                is_discovered=True,
                visit_count=1,
                first_visited_session_id=session.id,
            )
            self.db.add(world_loc)
            is_new_location = True
        else:
            # Existing location - increment visit count
            world_loc.visit_count += 1

        await self.db.flush()

        response = {
            "success": True,
            "location": location,
            "previous_location": previous_location,
            "is_new_location": is_new_location,
            "visit_count": world_loc.visit_count,
            "visible": True,  # Show location updates in frontend
        }

        # Add location_key info to response if available
        if location_key:
            response["location_key"] = location_key
        if matched_location:
            response["matched_module_location"] = True
            response["location_name"] = matched_location.name
        else:
            response["matched_module_location"] = False
            response["warning"] = "Location not found in adventure module - verify this is a valid module location"

        # Generate updated map data for frontend
        try:
            from app.domains.maps.map_service import MapService
            from app.domains.adventures.retriever import AdventureDataRetriever

            if session.campaign_id:
                campaign_result = await self.db.execute(
                    select(Campaign).where(Campaign.id == session.campaign_id)
                )
                campaign = campaign_result.scalar_one_or_none()

                if campaign and campaign.adventure_document_id:
                    retriever = AdventureDataRetriever(self.db)
                    module = await retriever.get_module_for_document(campaign.adventure_document_id)

                    if module:
                        locations = await retriever.get_all_locations(module.id)
                        if locations:
                            # Build full location data with exits
                            full_locations = []
                            for loc in locations[:20]:
                                loc_context = await retriever.get_location_context(module.id, loc['key'])
                                if loc_context and loc_context.get('location'):
                                    full_locations.append({
                                        'location_key': loc['key'],
                                        'name': loc['name'],
                                        'exits': loc_context['location'].get('exits', {}),
                                    })

                            # Get current state for map generation
                            current_key = adventure_state.get('current_location_key')
                            explored_keys = adventure_state.get('visited_locations', [])

                            # Generate updated map
                            map_service = MapService(self.db)
                            map_result = map_service.generate_connection_map(
                                locations=full_locations,
                                current_location_key=current_key,
                                explored_keys=explored_keys,
                            )

                            # Include map data in response
                            response["map_update"] = {
                                "map_id": "connection_map",
                                "map_name": f"{module.title} - Area Map",
                                "rendered_map": map_result["rendered_map"],
                                "width": map_result["width"],
                                "height": map_result["height"],
                                "player_position": map_result["player_position"],
                                "markers": map_result["markers"],
                                "exploration_progress": f"{len(explored_keys)}/{len(full_locations)} areas explored",
                            }
        except Exception as map_error:
            import logging
            logging.getLogger(__name__).warning(f"Failed to generate map update: {map_error}")

        return response

    async def _update_subarea_position(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Update the player's position within a location (sub-area tracking).

        This enables progressive reveal - the DM only describes content
        the player has actually reached within a larger location.
        """
        subarea_id = input.get("subarea_id", "")
        subarea_name = input.get("subarea_name", "")
        triggered_content = input.get("triggered_content", [])

        if not subarea_id:
            return {"error": "subarea_id is required", "visible": False}

        # Get adventure state
        adventure_state = session.adventure_state or {}
        previous_subarea = adventure_state.get("current_subarea")

        # Update current sub-area
        adventure_state["current_subarea"] = subarea_id
        adventure_state["current_subarea_name"] = subarea_name

        # Track visited sub-areas for this location
        subareas_visited = adventure_state.get("subareas_visited", [])
        if subarea_id not in subareas_visited:
            subareas_visited.append(subarea_id)
            adventure_state["subareas_visited"] = subareas_visited

        # Track triggered content (triggers, features revealed)
        triggered_this_location = adventure_state.get("triggered_content", [])
        for content_id in triggered_content:
            if content_id not in triggered_this_location:
                triggered_this_location.append(content_id)
        adventure_state["triggered_content"] = triggered_this_location

        # Save to session
        session.adventure_state = adventure_state
        await self.db.flush()

        return {
            "success": True,
            "subarea_id": subarea_id,
            "subarea_name": subarea_name,
            "previous_subarea": previous_subarea,
            "subareas_visited": subareas_visited,
            "triggered_content": triggered_content,
            "visible": False,  # Internal state tracking, not shown to player
        }

    async def _add_item(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Add an item to the character's inventory.

        TODO: Items are not automatically added when found during exploration.
        The LLM must explicitly call this tool when the player takes items.
        Consider:
        - Auto-prompting player to take discovered items
        - Tracking found-but-not-taken items in session state
        - Adding a "loot all" convenience tool
        - Validating items against module's item definitions
        """
        item_name = input.get("item_name", "")
        quantity = input.get("quantity", 1)
        value_gp = input.get("value_gp", 0)

        if not item_name:
            return {"error": "Item name is required", "visible": False}

        # Ensure attributes dict exists
        if not character.attributes:
            character.attributes = {}

        # Check if this is gold/coins - add to gold total
        item_lower = item_name.lower()
        is_gold = any(term in item_lower for term in ["gold", "gp", "coin", "coins", "gold piece", "gold pieces"])

        if is_gold:
            # Add to character's gold in attributes (not a separate column)
            # Use value_gp if provided, otherwise use quantity as the gold amount
            gold_amount = int(value_gp) if value_gp else quantity
            old_gold = character.attributes.get("gold", 0) or 0
            character.attributes["gold"] = old_gold + gold_amount
            new_gold = character.attributes["gold"]

            # Mark attributes as modified for SQLAlchemy to detect the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(character, "attributes")

            await self.db.flush()

            return {
                "success": True,
                "item_type": "gold",
                "amount_added": gold_amount,
                "old_gold": old_gold,
                "new_gold": new_gold,
                "message": f"Added {gold_amount} gold pieces. Total gold: {new_gold} gp",
                "visible": True,
            }
        else:
            # Add to equipment list in character attributes
            equipment = character.attributes.get("equipment", [])

            # Check if item already exists (for stackable items)
            existing_item = None
            for item in equipment:
                if isinstance(item, dict) and item.get("name", "").lower() == item_lower:
                    existing_item = item
                    break
                elif isinstance(item, str) and item.lower() == item_lower:
                    # Convert string item to dict format
                    idx = equipment.index(item)
                    equipment[idx] = {"name": item, "quantity": 1}
                    existing_item = equipment[idx]
                    break

            if existing_item:
                # Update quantity of existing item
                old_qty = existing_item.get("quantity", 1)
                existing_item["quantity"] = old_qty + quantity
                message = f"Added {quantity} {item_name}. Now have {existing_item['quantity']}."
            else:
                # Add new item
                new_item = {"name": item_name, "quantity": quantity}
                if value_gp:
                    new_item["value_gp"] = value_gp
                equipment.append(new_item)
                message = f"Added {item_name}" + (f" x{quantity}" if quantity > 1 else "") + " to inventory."

            character.attributes["equipment"] = equipment

            # Mark attributes as modified for SQLAlchemy to detect the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(character, "attributes")

            await self.db.flush()

            return {
                "success": True,
                "item_type": "equipment",
                "item_name": item_name,
                "quantity": quantity,
                "value_gp": value_gp,
                "message": message,
                "visible": True,
            }

    # Journal tool handlers

    async def _query_journal(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Query past journal entries for session continuity."""
        from sqlalchemy import select
        from app.domains.journal.models import JournalEntry

        entry_type = input.get("entry_type", "all")
        limit = input.get("limit", 5)

        # Build query
        query = (
            select(JournalEntry)
            .where(JournalEntry.campaign_id == session.campaign_id)
            .order_by(JournalEntry.created_at.desc())
            .limit(limit)
        )

        # Filter by entry type if specified (use string values matching database enum)
        if entry_type != "all":
            type_map = {
                "auto_summary": "auto_summary",
                "player_note": "player_note",
                "key_event": "key_event",
                "location": "location",
                "npc": "npc",
                "combat": "combat",
                "loot": "loot",
            }
            if entry_type in type_map:
                query = query.where(JournalEntry.entry_type == type_map[entry_type])

        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        # Format entries for LLM consumption
        formatted_entries = []
        for entry in entries:
            # entry_type is already a string from PostgreSQL ENUM
            entry_type_str = entry.entry_type.value if hasattr(entry.entry_type, 'value') else entry.entry_type
            formatted_entries.append({
                "type": entry_type_str,
                "title": entry.title,
                "content": entry.content,
                "date": entry.created_at.isoformat() if entry.created_at else None,
                "metadata": entry.entry_metadata or {},
            })

        return {
            "entries": formatted_entries,
            "count": len(formatted_entries),
            "entry_type_filter": entry_type,
            "visible": False,  # Internal DM reference
        }

    async def _record_discovery(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Record a significant discovery to the journal."""
        from sqlalchemy import select, func
        from app.domains.journal.models import JournalEntry

        entry_type_str = input.get("entry_type", "key_event")
        title = input.get("title", "Discovery")
        content = input.get("content", "")

        # Map to database enum string values
        type_map = {
            "key_event": "key_event",
            "location": "location",
            "npc": "npc",
            "combat": "combat",
            "loot": "loot",
        }
        entry_type = type_map.get(entry_type_str, "key_event")

        # Check for duplicate entries (same title, type, campaign, character)
        # to avoid recording the same discovery multiple times
        existing = await self.db.execute(
            select(JournalEntry)
            .where(
                JournalEntry.campaign_id == session.campaign_id,
                JournalEntry.character_id == session.character_id,
                JournalEntry.title == title,
                JournalEntry.entry_type == entry_type,
            )
            .limit(1)
        )
        if existing.scalar_one_or_none():
            return {
                "success": True,
                "entry_type": entry_type_str,
                "title": title,
                "recorded": False,
                "already_exists": True,
                "visible": False,
            }

        # Get next sequence number
        result = await self.db.execute(
            select(func.coalesce(func.max(JournalEntry.sequence), 0))
            .where(JournalEntry.campaign_id == session.campaign_id)
        )
        next_sequence = result.scalar() + 1

        # Get current in-game time for the journal entry
        game_date = None
        try:
            from app.domains.campaigns.calendar_service import CalendarService
            calendar_service = CalendarService(self.db)
            time_data = await calendar_service.get_current_time(session.campaign_id)
            if time_data and time_data.get("formatted_date"):
                game_date = f"{time_data['formatted_date']} ({time_data.get('time_of_day', '')})"
        except Exception:
            pass  # Calendar may not exist for this campaign

        # Create journal entry
        entry = JournalEntry(
            session_id=session.id,
            campaign_id=session.campaign_id,
            character_id=session.character_id,
            entry_type=entry_type,
            title=title,
            content=content,
            sequence=next_sequence,
            game_date=game_date,
        )

        self.db.add(entry)
        await self.db.flush()

        return {
            "success": True,
            "entry_type": entry_type_str,
            "title": title,
            "recorded": True,
            "visible": False,  # Internal DM action
        }

    async def _query_world_state(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Query the current world state for consistency."""
        from sqlalchemy import select
        from app.domains.journal.models import WorldConsequence, WorldLocation

        include_consequences = input.get("include_consequences", True)
        include_locations = input.get("include_locations", True)

        result_data = {}

        # Get active consequences
        if include_consequences:
            result = await self.db.execute(
                select(WorldConsequence)
                .where(WorldConsequence.campaign_id == session.campaign_id)
                .where(WorldConsequence.is_active == True)
                .order_by(WorldConsequence.created_at.desc())
                .limit(10)
            )
            consequences = list(result.scalars().all())

            result_data["consequences"] = [
                {
                    "trigger": c.trigger_action,
                    "consequence": c.consequence,
                    "scope": c.scope,
                    "is_permanent": c.is_permanent,
                    "affected_locations": c.affected_locations or [],
                    "affected_npcs": c.affected_npcs or [],
                }
                for c in consequences
            ]

        # Get discovered locations
        if include_locations:
            result = await self.db.execute(
                select(WorldLocation)
                .where(WorldLocation.campaign_id == session.campaign_id)
                .where(WorldLocation.is_discovered == True)
                .order_by(WorldLocation.visit_count.desc())
                .limit(20)
            )
            locations = list(result.scalars().all())

            result_data["locations"] = [
                {
                    "name": loc.name,
                    "type": loc.location_type,
                    "description": loc.description,
                    "is_cleared": loc.is_cleared,
                    "visit_count": loc.visit_count,
                    "notes": loc.notes,
                }
                for loc in locations
            ]

        return {
            **result_data,
            "visible": False,  # Internal DM reference
        }

    # Solo Hero tool handlers

    # Damage to Harm conversion table
    DAMAGE_TO_HARM = [
        (1, 0),   # 1 damage = 0 harm
        (5, 1),   # 2-5 damage = 1 harm
        (9, 2),   # 6-9 damage = 2 harm
        (999, 4), # 10+ damage = 4 harm
    ]

    # Trait check difficulty targets
    TRAIT_DIFFICULTY = {
        "easy": 9,
        "normal": 11,
        "hard": 13,
        "very_hard": 15,
        "heroic": 17,
    }

    async def _convert_damage_to_harm(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Convert hero damage to harm against foes using Solo Hero rules."""
        damage_rolled = input.get("damage_rolled", 0)
        target_hd = input.get("target_hd", 1)
        target_description = input.get("target_description", "the foe")

        # Convert damage to harm
        harm = 0
        for threshold, harm_value in self.DAMAGE_TO_HARM:
            if damage_rolled <= threshold:
                harm = harm_value
                break

        # Determine casualties
        hd_killed = min(harm, target_hd)
        remaining_hd = max(0, target_hd - harm)

        # Interpret result narratively
        if harm >= target_hd:
            result = "eliminated"
            narrative = f"The hero's blow deals {harm} harm, slaying {target_description}!"
        elif harm > 0:
            result = "wounded"
            narrative = f"The hero deals {harm} harm to {target_description}, reducing them to {remaining_hd} HD."
        else:
            result = "ineffective"
            narrative = f"The glancing blow deals no significant harm to {target_description}."

        # Sync kills to CombatParticipant if encounter active and harm > 0
        killed_names = []
        if harm > 0 and session.active_combat_id:
            killed_names = await self._kill_participants_by_hd(
                session.active_combat_id, harm
            )

        return {
            "damage_rolled": damage_rolled,
            "harm_dealt": harm,
            "target_hd": target_hd,
            "hd_killed": hd_killed,
            "remaining_hd": remaining_hd,
            "target": target_description,
            "result": result,
            "narrative": narrative,
            "killed_in_encounter": killed_names,
            "visible": True,  # Show combat results
        }

    async def _roll_fray_die(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Roll the hero's Fray Die (1d8) for automatic kills against weak foes."""
        target_description = input.get("target_description", "the weak foes")

        # Roll 1d8
        fray_roll = random.randint(1, 8)

        # Convert to harm using fray die table
        if fray_roll == 1:
            harm = 0
            narrative = f"The hero's attacks against {target_description} fail to connect."
        elif fray_roll <= 5:
            harm = 1
            narrative = f"The hero cuts down one of {target_description}!"
        else:  # 6-8
            harm = 2
            narrative = f"The hero strikes down two of {target_description} with deadly efficiency!"

        # Sync kills to CombatParticipant if encounter active and harm > 0
        # Fray die only kills 1HD foes
        killed_names = []
        if harm > 0 and session.active_combat_id:
            killed_names = await self._kill_participants_by_hd(
                session.active_combat_id, harm, max_hd=1
            )

        return {
            "roll": fray_roll,
            "harm": harm,
            "foes_killed": harm,  # Each harm kills one 1HD foe
            "target": target_description,
            "narrative": narrative,
            "killed_in_encounter": killed_names,
            "visible": True,  # Show Fray Die results
        }

    async def _defy_death(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Roll to defy death when the hero reaches 0 HP."""
        con_modifier = input.get("con_modifier", 0)
        level = input.get("level", 1)

        # Roll 1d20 + CON modifier + level
        roll = random.randint(1, 20)
        total = roll + con_modifier + level

        # Interpret result
        if total <= 5:
            result = "dead"
            narrative = f"The hero succumbs to their wounds and dies."
            hp_restored = 0
        elif total <= 10:
            result = "mortally_wounded"
            narrative = f"The hero is mortally wounded and will die in 1d6 rounds without aid."
            hp_restored = 0
        elif total <= 15:
            result = "knocked_out"
            narrative = f"The hero is knocked unconscious and will wake in 1d6 turns."
            hp_restored = 0
        elif total <= 20:
            result = "barely_conscious"
            narrative = f"The hero clings to consciousness, rising to 1 HP but acting at -2 to all rolls."
            hp_restored = 1
        else:  # 21+
            result = "second_wind"
            second_wind_hp = random.randint(1, 6)
            narrative = f"The hero catches a second wind and surges back with {second_wind_hp} HP!"
            hp_restored = second_wind_hp

        return {
            "roll": roll,
            "con_modifier": con_modifier,
            "level": level,
            "total": total,
            "result": result,
            "narrative": narrative,
            "hp_restored": hp_restored,
            "visible": True,  # Critical moment - show result
        }

    async def _roll_trait_check(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Make a trait check using Solo Hero rules (2d8 + modifier)."""
        trait = input.get("trait", "")
        modifier = input.get("modifier", 0)
        difficulty = input.get("difficulty", "normal")
        task_description = input.get("task_description", "the task")

        # Roll 2d8
        dice = [random.randint(1, 8), random.randint(1, 8)]
        total = sum(dice) + modifier

        # Get target number
        target = self.TRAIT_DIFFICULTY.get(difficulty, 11)

        # Determine success
        success = total >= target
        margin = total - target

        if success:
            if margin >= 4:
                result = "exceptional_success"
                narrative = f"The hero succeeds brilliantly at {task_description}!"
            else:
                result = "success"
                narrative = f"The hero succeeds at {task_description}."
        else:
            if margin <= -4:
                result = "critical_failure"
                narrative = f"The hero fails badly at {task_description}, with dire consequences."
            else:
                result = "failure"
                narrative = f"The hero fails at {task_description}."

        return {
            "trait": trait,
            "dice": dice,
            "modifier": modifier,
            "total": total,
            "difficulty": difficulty,
            "target": target,
            "success": success,
            "margin": margin,
            "result": result,
            "narrative": narrative,
            "task": task_description,
            "visible": True,  # Show trait check results
        }

    # Calendar tool handlers

    async def _advance_time(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Advance in-game time."""
        from app.domains.campaigns.calendar_service import CalendarService

        hours = input.get("hours", 0)
        days = input.get("days", 0)
        reason = input.get("reason", "")

        if hours == 0 and days == 0:
            return {
                "error": "Must specify hours or days to advance",
                "visible": False,
            }

        calendar_service = CalendarService(self.db)
        result = await calendar_service.advance_time(
            campaign_id=session.campaign_id,
            hours=hours,
            days=days,
            reason=reason,
        )

        # Build narrative response
        narrative_parts = []
        if reason:
            narrative_parts.append(f"Time passes as {reason}.")

        old_time = result.get("old_time", {})
        new_time = result.get("new_time", {})
        narrative_parts.append(f"It is now {new_time.get('formatted', '')}.")

        # Mention time of day change
        if result.get("day_changed"):
            narrative_parts.append("A new day begins.")

        # Mention weather
        if result.get("weather_change"):
            new_weather = result["weather_change"]["new"]
            narrative_parts.append(f"The weather is {new_weather}.")

        # Mention moon phase change
        if result.get("moon_phase_change"):
            new_phase = result["moon_phase_change"]["new"]
            narrative_parts.append(f"The moon is now in {new_phase}.")

        # Mention triggered events
        triggered = result.get("triggered_events", [])
        if triggered:
            for event in triggered:
                narrative_parts.append(f"Event triggered: {event.get('name', 'Unknown')}!")

        return {
            **result,
            # Add aliases for expected keys (calendar returns hours_advanced, consumers expect hours_passed)
            "hours_passed": result.get("hours_advanced", 0) if result.get("hours_advanced") else hours,
            "days_passed": days,
            "narrative": " ".join(narrative_parts),
            "visible": True,  # Show time changes to player
        }

    async def _get_current_time(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Get current in-game time."""
        from app.domains.campaigns.calendar_service import CalendarService

        calendar_service = CalendarService(self.db)
        result = await calendar_service.get_current_time(
            campaign_id=session.campaign_id
        )

        return {
            **result,
            "visible": False,  # Internal DM reference
        }

    async def _schedule_event(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Schedule a future event."""
        from app.domains.campaigns.calendar_service import CalendarService

        name = input.get("name", "")
        day = input.get("day", 1)
        month = input.get("month", 1)
        year = input.get("year")  # Can be None for recurring
        recurring = input.get("recurring", False)
        description = input.get("description", "")

        if not name:
            return {
                "error": "Event name is required",
                "visible": False,
            }

        calendar_service = CalendarService(self.db)
        result = await calendar_service.schedule_event(
            campaign_id=session.campaign_id,
            name=name,
            day=day,
            month=month,
            year=year,
            recurring=recurring,
            description=description,
        )

        return {
            **result,
            "visible": False,  # Internal DM state management
        }

    async def _check_upcoming_events(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Check for upcoming scheduled events."""
        from app.domains.campaigns.calendar_service import CalendarService

        days_ahead = input.get("days_ahead", 30)

        calendar_service = CalendarService(self.db)
        events = await calendar_service.get_upcoming_events(
            campaign_id=session.campaign_id,
            days_ahead=days_ahead,
        )

        return {
            "events": events,
            "count": len(events),
            "days_checked": days_ahead,
            "visible": False,  # Internal DM reference
        }

    # Map tool handlers

    async def _display_map(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Display the current dungeon map to the player."""
        from app.domains.maps.map_service import MapService
        from app.domains.adventures.retriever import AdventureDataRetriever

        include_markers = input.get("include_markers", True)

        map_service = MapService(self.db)
        active_map = await map_service.get_active_map(session.campaign_id)

        if not active_map:
            # Try to generate a connection-based map from adventure locations
            from app.domains.campaigns.models import Campaign
            campaign_result = await self.db.execute(
                select(Campaign).where(Campaign.id == session.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()

            if campaign and campaign.adventure_document_id:
                retriever = AdventureDataRetriever(self.db)
                module = await retriever.get_module_for_document(campaign.adventure_document_id)

                if module:
                    # Get all locations with their exits
                    locations = await retriever.get_all_locations(module.id)
                    if locations:
                        # Get full location data with exits
                        full_locations = []
                        for loc in locations:
                            loc_context = await retriever.get_location_context(module.id, loc['key'])
                            if loc_context and loc_context.get('location'):
                                full_locations.append({
                                    'location_key': loc['key'],
                                    'name': loc['name'],
                                    'exits': loc_context['location'].get('exits', {}),
                                })

                        # Get explored locations from adventure state
                        adventure_state = session.adventure_state or {}
                        explored_keys = adventure_state.get('visited_locations', [])
                        current_key = adventure_state.get('current_location_key')

                        # Generate connection map
                        map_result = map_service.generate_connection_map(
                            locations=full_locations,
                            current_location_key=current_key,
                            explored_keys=explored_keys,
                        )

                        return {
                            "map_id": "connection_map",
                            "map_name": f"{module.title} - Area Map",
                            "rendered_map": map_result["rendered_map"],
                            "width": map_result["width"],
                            "height": map_result["height"],
                            "player_position": map_result["player_position"],
                            "markers": map_result["markers"],
                            "exploration_progress": f"{len(explored_keys)}/{len(full_locations)} areas explored",
                            "visible": True,
                        }

            return {
                "error": "No map available for this campaign",
                "visible": True,
            }

        map_data = await map_service.get_map_data(
            active_map.id,
            include_fog=True,
        )

        if not map_data:
            return {
                "error": "Failed to render map",
                "visible": True,
            }

        return {
            "map_id": map_data["id"],
            "map_name": map_data["name"],
            "rendered_map": map_data["rendered_map"],
            "width": map_data["width"],
            "height": map_data["height"],
            "player_position": map_data["player_position"],
            "markers": map_data["markers"] if include_markers else [],
            "exploration_progress": f"{map_data['revealed_count']}/{map_data['total_cells']} cells explored",
            "visible": True,  # Show map to player
        }

    async def _update_map_position(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Move the player position on the map."""
        from app.domains.maps.map_service import MapService

        x = input.get("x", 0)
        y = input.get("y", 0)
        reveal_radius = input.get("reveal_radius", 2)

        map_service = MapService(self.db)
        active_map = await map_service.get_active_map(session.campaign_id)

        if not active_map:
            return {
                "error": "No active map for this campaign",
                "visible": False,
            }

        result = await map_service.update_player_position(
            map_id=active_map.id,
            x=x,
            y=y,
            reveal_radius=reveal_radius,
        )

        if "error" in result:
            return {
                **result,
                "visible": False,
            }

        # Get updated map rendering
        map_data = await map_service.get_map_data(active_map.id, include_fog=True)

        return {
            **result,
            "rendered_map": map_data["rendered_map"] if map_data else None,
            "visible": True,  # Show position update to player
        }

    async def _add_map_marker(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Add a marker to the current map."""
        from app.domains.maps.map_service import MapService

        x = input.get("x", 0)
        y = input.get("y", 0)
        symbol = input.get("symbol", "*")
        label = input.get("label", "")
        marker_type = input.get("marker_type", "generic")

        map_service = MapService(self.db)
        active_map = await map_service.get_active_map(session.campaign_id)

        if not active_map:
            return {
                "error": "No active map for this campaign",
                "visible": False,
            }

        result = await map_service.add_marker(
            map_id=active_map.id,
            x=x,
            y=y,
            symbol=symbol,
            label=label,
            marker_type=marker_type,
        )

        return {
            **result,
            "visible": True,  # Show marker addition to player
        }

    async def _create_map(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Create a new dungeon map, either procedurally or from custom ASCII."""
        from app.domains.maps.map_service import MapService

        name = input.get("name", "Unnamed Map")
        description = input.get("description", "")
        map_type = input.get("map_type", "dungeon")
        size = input.get("size", "medium")
        custom_ascii = input.get("custom_ascii")
        entrance_x = input.get("entrance_x")
        entrance_y = input.get("entrance_y")

        map_service = MapService(self.db)

        # Generate or use custom map
        if custom_ascii:
            # Use provided ASCII map
            map_data = custom_ascii.strip()
            lines = map_data.split('\n')
            height = len(lines)
            width = max(len(line) for line in lines) if lines else 0

            # Use provided entrance or find a floor tile
            if entrance_x is None or entrance_y is None:
                # Find first floor tile as entrance
                for y, line in enumerate(lines):
                    for x, char in enumerate(line):
                        if char == '.':
                            entrance_x, entrance_y = x, y
                            break
                    if entrance_x is not None:
                        break
                if entrance_x is None:
                    entrance_x, entrance_y = 1, 1
        else:
            # Generate procedural map
            map_data, width, height, gen_entrance_x, gen_entrance_y = map_service.generate_map(
                map_type=map_type,
                size=size,
            )
            # Use generated entrance if not specified
            if entrance_x is None:
                entrance_x = gen_entrance_x
            if entrance_y is None:
                entrance_y = gen_entrance_y

        # Create the map in database
        dungeon_map = await map_service.create_map(
            campaign_id=session.campaign_id,
            name=name,
            map_data=map_data,
        )

        # Set as active map for this campaign
        await map_service.set_active_map(
            campaign_id=session.campaign_id,
            map_id=dungeon_map.id,
        )

        # Place player at entrance and reveal starting area
        await map_service.update_player_position(
            map_id=dungeon_map.id,
            x=entrance_x,
            y=entrance_y,
            reveal_radius=2,
        )

        # Get the rendered map with fog
        map_data_result = await map_service.get_map_data(dungeon_map.id, include_fog=True)

        return {
            "success": True,
            "map_id": str(dungeon_map.id),
            "map_name": name,
            "description": description,
            "width": width,
            "height": height,
            "entrance": {"x": entrance_x, "y": entrance_y},
            "rendered_map": map_data_result["rendered_map"] if map_data_result else "",
            "message": f"Created map '{name}' ({width}x{height}). Player starts at ({entrance_x}, {entrance_y}).",
            "visible": True,  # Show map creation to player
        }

    # Encounter tool handlers

    async def _start_encounter(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Start a tracked combat encounter with persistent DB state."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.domains.combat.manager import CombatManager, EnemyStats
        from app.domains.combat.models import CombatEncounter, CombatStatus
        from app.domains.adventures.models import (
            AdventureModule, AdventureLocation, AdventureEncounter, EncounterType,
        )
        from app.domains.campaigns.models import Campaign

        # Guard: prevent double-start
        if session.active_combat_id:
            # Check if it's actually still active
            result = await self.db.execute(
                select(CombatEncounter).where(
                    CombatEncounter.id == session.active_combat_id
                )
            )
            existing = result.scalar_one_or_none()
            if existing and existing.status == CombatStatus.ACTIVE:
                return {
                    "error": "Combat already active. Use end_encounter first.",
                    "encounter_id": str(session.active_combat_id),
                    "visible": False,
                }
            # Stale reference - clear it
            session.active_combat_id = None

        encounter_name = input.get("encounter_name", "Combat")
        source = input.get("source")
        enemies_input = input.get("enemies")
        wandering_roll = input.get("wandering_roll")

        # Determine source automatically if not specified
        if source is None:
            source = "custom" if enemies_input else "fixed"

        enemies = []

        if source == "custom" and enemies_input:
            # Use explicitly provided enemies
            enemies = enemies_input
        elif source in ("fixed", "wandering"):
            # Auto-populate from adventure module encounters
            adventure_state = session.adventure_state or {}
            location_key = adventure_state.get("current_location_key")

            if not location_key and source == "fixed":
                return {
                    "error": "No current location_key in adventure state. Provide enemies explicitly.",
                    "visible": False,
                }

            # Look up adventure module via campaign
            campaign_result = await self.db.execute(
                select(Campaign).where(Campaign.id == session.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()

            if not campaign or not campaign.adventure_document_id:
                return {
                    "error": "No adventure module linked to campaign. Provide enemies explicitly.",
                    "visible": False,
                }

            module_result = await self.db.execute(
                select(AdventureModule).where(
                    AdventureModule.pdf_document_id == campaign.adventure_document_id
                )
            )
            module = module_result.scalar_one_or_none()

            if not module:
                return {
                    "error": "Adventure module not found. Provide enemies explicitly.",
                    "visible": False,
                }

            if source == "fixed":
                # Get fixed encounters for current location
                loc_result = await self.db.execute(
                    select(AdventureLocation).where(
                        AdventureLocation.module_id == module.id,
                        AdventureLocation.location_key == location_key,
                    )
                )
                location = loc_result.scalar_one_or_none()

                if not location:
                    return {
                        "error": f"Location '{location_key}' not found in module. Provide enemies explicitly.",
                        "visible": False,
                    }

                enc_result = await self.db.execute(
                    select(AdventureEncounter).where(
                        AdventureEncounter.location_id == location.id,
                        AdventureEncounter.encounter_type == EncounterType.FIXED,
                    )
                )
                encounter_records = list(enc_result.scalars().all())

                if not encounter_records:
                    return {
                        "error": f"No fixed encounters at location '{location_key}'. Provide enemies explicitly.",
                        "visible": False,
                    }

                # Expand creatures from all fixed encounters at this location
                for enc in encounter_records:
                    if not encounter_name or encounter_name == "Combat":
                        encounter_name = enc.name or encounter_name
                    for creature in (enc.creatures or []):
                        enemies.extend(self._expand_creature_entry(creature))

            elif source == "wandering":
                # Get wandering encounters for current tier/level
                current_tier = adventure_state.get("current_tier")
                current_level = adventure_state.get("current_dungeon_level")

                wander_query = select(AdventureEncounter).where(
                    AdventureEncounter.module_id == module.id,
                    AdventureEncounter.encounter_type == EncounterType.WANDERING,
                )
                wander_result = await self.db.execute(wander_query)
                wandering_encounters = list(wander_result.scalars().all())

                if not wandering_encounters:
                    return {
                        "error": "No wandering encounter table found. Provide enemies explicitly.",
                        "visible": False,
                    }

                # Match the wandering_roll to a specific entry
                matched_encounter = None
                if wandering_roll is not None:
                    for wenc in wandering_encounters:
                        roll_range = wenc.roll_range or ""
                        if self._roll_in_range(wandering_roll, roll_range):
                            matched_encounter = wenc
                            break

                # Fallback: pick a random one if no roll match
                if not matched_encounter:
                    import random as _rand
                    matched_encounter = _rand.choice(wandering_encounters)

                if not encounter_name or encounter_name == "Combat":
                    encounter_name = matched_encounter.name or "Wandering Encounter"

                for creature in (matched_encounter.creatures or []):
                    enemies.extend(self._expand_creature_entry(creature))

        if not enemies:
            return {
                "error": "No enemies resolved. Provide enemies list explicitly.",
                "visible": False,
            }

        # Start combat via CombatManager
        combat_manager = CombatManager(self.db)
        state = await combat_manager.start_combat(session, character, enemies)

        # Set in_combat flag in game_state
        if not session.game_state:
            session.game_state = {}
        game_state = dict(session.game_state)
        game_state["in_combat"] = True
        session.game_state = game_state
        await self.db.flush()

        # Build response
        enemy_summary = []
        for name, stats in state.enemies.items():
            enemy_summary.append({
                "name": name,
                "hd": stats.hd,
                "hp": stats.hp,
                "ac": stats.ac,
                "thac0": stats.thac0,
                "damage": stats.damage,
                "morale": stats.morale,
            })

        return {
            "success": True,
            "encounter_name": encounter_name,
            "encounter_id": str(session.active_combat_id),
            "round": state.round_number,
            "initiative_order": state.initiative_order,
            "player_initiative": state.player_initiative,
            "is_player_turn": state.is_player_turn,
            "current_turn": state.current_turn,
            "enemies": enemy_summary,
            "enemy_count": len(state.enemies),
            "source": source,
            "visible": False,  # Combat setup is internal DM mechanics
        }

    async def _end_encounter(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """End the current combat encounter."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.domains.combat.manager import CombatManager, CombatState, EnemyStats
        from app.domains.combat.models import (
            CombatEncounter, CombatParticipant, CombatStatus, ParticipantType,
        )

        # Guard: no active combat
        if not session.active_combat_id:
            return {
                "error": "No active combat encounter to end.",
                "visible": False,
            }

        outcome = input.get("outcome", "victory")

        # Load encounter with participants
        result = await self.db.execute(
            select(CombatEncounter)
            .options(selectinload(CombatEncounter.participants))
            .where(CombatEncounter.id == session.active_combat_id)
        )
        encounter = result.scalar_one_or_none()

        if not encounter:
            # Stale reference
            session.active_combat_id = None
            if not session.game_state:
                session.game_state = {}
            game_state = dict(session.game_state)
            game_state["in_combat"] = False
            session.game_state = game_state
            await self.db.flush()
            return {
                "error": "Encounter record not found. Combat state cleared.",
                "visible": False,
            }

        # Reconstruct minimal CombatState from DB records
        state = CombatState(
            round_number=encounter.current_round,
            is_active=True,
        )

        for p in encounter.participants:
            if p.participant_type == ParticipantType.PLAYER:
                continue
            enemy = EnemyStats(
                name=p.name,
                hd=int(p.stats.get("hd", 1) or 1) if p.stats else 1,
                hp=p.current_hp,
                max_hp=p.max_hp,
                ac=p.armor_class or 9,
                thac0=p.thac0 or 19,
                damage=str(p.stats.get("damage", "1d6") or "1d6") if p.stats else "1d6",
                morale=p.morale or 7,
                xp_value=int(p.stats.get("xp_value", 0) or 0) if p.stats else 0,
            )
            state.enemies[p.name] = enemy

            if p.current_hp <= 0:
                state.defeated_enemies.append(p.name)
                state.total_xp_earned += enemy.xp_value
            elif p.morale_broken:
                state.fled_enemies.append(p.name)
                state.total_xp_earned += enemy.xp_value // 2

        # End combat via CombatManager
        combat_manager = CombatManager(self.db)
        summary = await combat_manager.end_combat(session, state, outcome)

        # Clear in_combat flag
        if not session.game_state:
            session.game_state = {}
        game_state = dict(session.game_state)
        game_state["in_combat"] = False
        session.game_state = game_state
        await self.db.flush()

        return {
            "success": True,
            "outcome": outcome,
            "rounds": summary["rounds"],
            "defeated_enemies": summary["defeated_enemies"],
            "fled_enemies": summary["fled_enemies"],
            "total_xp": summary["total_xp"],
            "visible": False,  # Internal DM mechanics
        }

    async def _sync_participant_hp(
        self,
        encounter_id,
        participant_name: str,
        new_hp: int,
        mark_defeated: bool = False,
    ) -> None:
        """Sync HP (and optionally defeated status) to a CombatParticipant record."""
        from sqlalchemy import select
        from app.domains.combat.models import CombatParticipant

        result = await self.db.execute(
            select(CombatParticipant).where(
                CombatParticipant.encounter_id == encounter_id,
                CombatParticipant.name == participant_name,
            )
        )
        participant = result.scalar_one_or_none()
        if participant:
            participant.current_hp = max(0, new_hp)
            if mark_defeated and new_hp <= 0:
                participant.current_hp = 0
            await self.db.flush()

    async def _sync_participant_morale_broken(
        self,
        encounter_id,
        participant_name: str,
    ) -> None:
        """Mark a CombatParticipant as morale_broken."""
        from sqlalchemy import select
        from app.domains.combat.models import CombatParticipant

        result = await self.db.execute(
            select(CombatParticipant).where(
                CombatParticipant.encounter_id == encounter_id,
                CombatParticipant.name == participant_name,
            )
        )
        participant = result.scalar_one_or_none()
        if participant:
            participant.morale_broken = True
            await self.db.flush()

    async def _kill_participants_by_hd(
        self,
        encounter_id,
        harm: int,
        max_hd: int | None = None,
    ) -> list:
        """Kill living enemy participants by HD, lowest HP first.

        Args:
            encounter_id: Active encounter ID
            harm: Number of HD worth of kills
            max_hd: If set, only kill participants with HD <= this value (fray die = 1)

        Returns:
            List of names of killed participants
        """
        from sqlalchemy import select
        from app.domains.combat.models import CombatParticipant, ParticipantType

        result = await self.db.execute(
            select(CombatParticipant).where(
                CombatParticipant.encounter_id == encounter_id,
                CombatParticipant.current_hp > 0,
                CombatParticipant.morale_broken == False,
            ).order_by(CombatParticipant.current_hp.asc())
        )
        # Filter out player participants in Python to avoid PostgreSQL enum cast issues
        living = [
            p for p in result.scalars().all()
            if p.participant_type != ParticipantType.PLAYER
        ]

        killed = []
        remaining_harm = harm

        for p in living:
            if remaining_harm <= 0:
                break
            hd = int(p.stats.get("hd", 1) or 1) if p.stats else 1
            if max_hd is not None and hd > max_hd:
                continue
            if hd <= remaining_harm:
                p.current_hp = 0
                killed.append(p.name)
                remaining_harm -= hd

        if killed:
            await self.db.flush()

        return killed

    def _expand_creature_entry(self, creature: Dict[str, Any]) -> list:
        """Expand a creature JSONB entry into individual enemy dicts.

        Creature entries from AdventureEncounter.creatures may have:
        - count: int or dice string (e.g., "1d6", 3)
        - name, hd, hp, ac, thac0, damage, morale, xp_value, etc.
        """
        import re

        count_raw = creature.get("count", 1)
        base_name = creature.get("name", "Enemy")

        # Parse count (could be dice notation or integer)
        if isinstance(count_raw, str):
            match = re.match(r'(\d+)d(\d+)([+-]\d+)?', count_raw)
            if match:
                import random as _rand
                num = int(match.group(1))
                sides = int(match.group(2))
                mod = int(match.group(3) or 0)
                count = max(1, sum(_rand.randint(1, sides) for _ in range(num)) + mod)
            else:
                try:
                    count = int(count_raw)
                except (ValueError, TypeError):
                    count = 1
        else:
            count = int(count_raw) if count_raw else 1

        results = []
        for i in range(count):
            suffix = f" {i + 1}" if count > 1 else ""
            enemy = {
                "name": f"{base_name}{suffix}",
                "hd": self._safe_int(creature.get("hd", 1), 1),
                "ac": self._safe_int(creature.get("ac", 9), 9),
                "thac0": self._safe_int(creature.get("thac0", 19), 19),
                "damage": str(creature.get("damage", "1d6") or "1d6"),
                "morale": self._safe_int(creature.get("morale", 7), 7),
                "xp_value": self._safe_int(creature.get("xp_value", 0), 0),
            }
            # Only include hp if explicitly provided (otherwise auto-roll from HD)
            if "hp" in creature:
                enemy["hp"] = creature["hp"]
            results.append(enemy)

        return results

    def _roll_in_range(self, roll: int, roll_range: str) -> bool:
        """Check if a die roll falls within a range string like '1-2', '3', '4-6'."""
        if not roll_range:
            return False
        try:
            if "-" in roll_range:
                parts = roll_range.split("-")
                low, high = int(parts[0].strip()), int(parts[1].strip())
                return low <= roll <= high
            else:
                return roll == int(roll_range.strip())
        except (ValueError, IndexError):
            return False

    async def _show_illustration(
        self,
        input: Dict[str, Any],
        character: Character,
        session: Session,
    ) -> Dict[str, Any]:
        """Show an atmospheric illustration to the player.

        Finds a matching extracted image from the adventure module using:
        1. Keyword matching on title/description
        2. Page proximity to current location
        3. Random fallback if no good match
        """
        from sqlalchemy import select
        from app.domains.sourcebooks.models import ExtractedImage
        from app.domains.campaigns.models import Campaign
        from app.domains.adventures.models import AdventureLocation

        image_type = input.get("image_type", "scene")
        description = input.get("description", "")
        mood = input.get("mood", "dramatic")

        # Get campaign to find the adventure document
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == session.campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign or not campaign.adventure_document_id:
            return {
                "shown": False,
                "reason": "No adventure module with images",
                "generate": True,
                "prompt": f"{mood} {image_type}: {description}",
            }

        # Find all images from the module (illustrations, not maps/covers)
        result = await self.db.execute(
            select(ExtractedImage)
            .where(ExtractedImage.document_id == campaign.adventure_document_id)
            .where(ExtractedImage.image_type == "illustration")
            .order_by(ExtractedImage.page_number)
        )
        images = list(result.scalars().all())

        if not images:
            # No extracted illustrations - signal for generation
            return {
                "shown": False,
                "reason": "No illustrations extracted from module",
                "generate": True,
                "prompt": f"{mood} {image_type}: {description}",
            }

        # Score each image for relevance
        description_lower = description.lower()
        keywords = set(description_lower.split())

        # Get current location's page number for proximity matching
        current_page = None
        adventure_state = session.adventure_state or {}
        current_location_key = adventure_state.get("current_location_key")

        if current_location_key:
            # Try to get the location's page number from the module
            from app.domains.adventures.models import AdventureModule
            result = await self.db.execute(
                select(AdventureModule).where(
                    AdventureModule.pdf_document_id == campaign.adventure_document_id
                )
            )
            module = result.scalar_one_or_none()
            if module:
                result = await self.db.execute(
                    select(AdventureLocation).where(
                        AdventureLocation.module_id == module.id,
                        AdventureLocation.location_key == current_location_key
                    )
                )
                location = result.scalar_one_or_none()
                if location and location.page_start:
                    current_page = location.page_start

        scored_images = []
        for img in images:
            score = 0

            # Keyword matching on title
            if img.title:
                title_lower = img.title.lower()
                title_words = set(title_lower.split())
                matching_words = keywords & title_words
                score += len(matching_words) * 3  # Title matches worth more

                # Exact substring match in title
                if description_lower in title_lower:
                    score += 10

            # Keyword matching on description
            if img.description:
                desc_lower = img.description.lower()
                desc_words = set(desc_lower.split())
                matching_words = keywords & desc_words
                score += len(matching_words) * 2

                # Exact substring match in description
                if description_lower in desc_lower:
                    score += 5

            # Page proximity bonus (images near current location)
            if current_page and img.page_number:
                page_distance = abs(img.page_number - current_page)
                if page_distance <= 2:
                    score += 5  # Very close
                elif page_distance <= 5:
                    score += 2  # Nearby

            # Mood matching via brightness
            if mood in ["dark", "dangerous"] and img.brightness is not None:
                if img.brightness < 40:
                    score += 2  # Dark images for dark moods
            elif mood in ["peaceful", "wondrous"] and img.brightness is not None:
                if img.brightness > 60:
                    score += 2  # Bright images for light moods

            scored_images.append((score, img))

        # Sort by score (highest first)
        scored_images.sort(key=lambda x: x[0], reverse=True)

        # Pick the best match, or random if all scores are 0
        if scored_images[0][0] > 0:
            selected = scored_images[0][1]
        else:
            # No good matches - pick random
            import random
            selected = random.choice(images)

        return {
            "shown": True,
            "image_id": str(selected.id),
            "image_path": selected.image_path,
            "image_url": f"/api/v1/sourcebooks/images/{selected.id}/file",
            "title": selected.title or description,
            "description": description,
            "mood": mood,
            "match_score": scored_images[0][0] if scored_images else 0,
            "visible": True,  # This signals the frontend to display the image
        }
