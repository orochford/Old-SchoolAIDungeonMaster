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
            # TODO: Fetch inventory from database
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

        return {
            "creature": creature_name,
            "morale_score": morale_score,
            "roll": roll,
            "passed": passed,
            "reason": reason,
            "result": "holds firm" if passed else "breaks and flees",
            "visible": False,  # DM mechanic - hide by default
        }

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

        return response

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

        return {
            "damage_rolled": damage_rolled,
            "harm_dealt": harm,
            "target_hd": target_hd,
            "hd_killed": hd_killed,
            "remaining_hd": remaining_hd,
            "target": target_description,
            "result": result,
            "narrative": narrative,
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

        return {
            "roll": fray_roll,
            "harm": harm,
            "foes_killed": harm,  # Each harm kills one 1HD foe
            "target": target_description,
            "narrative": narrative,
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

        include_markers = input.get("include_markers", True)

        map_service = MapService(self.db)
        active_map = await map_service.get_active_map(session.campaign_id)

        if not active_map:
            return {
                "error": "No active map for this campaign",
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
