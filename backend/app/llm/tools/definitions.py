"""Tool definitions for the LLM DM."""

DM_TOOLS = [
    {
        "name": "roll_dice",
        "description": "Roll dice using standard notation. Use for ALL random rolls: attacks, damage, saves, ability checks, morale, reaction rolls, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "notation": {
                    "type": "string",
                    "description": "Dice notation (e.g., '1d20', '2d6', '3d8+5', '1d20+4')",
                },
                "purpose": {
                    "type": "string",
                    "description": "What this roll is for (e.g., 'attack roll', 'damage', 'saving throw vs poison')",
                },
            },
            "required": ["notation", "purpose"],
        },
    },
    {
        "name": "lookup_rule",
        "description": "Query the rulebook for specific rules or mechanics. Use when uncertain about rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The rule or mechanic to look up (e.g., 'elf saving throws level 3', 'sleep spell effect')",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_character",
        "description": "Get detailed information about the player character.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aspect": {
                    "type": "string",
                    "enum": ["stats", "inventory", "spells", "abilities", "conditions", "all"],
                    "description": "Which aspect of the character to query",
                },
            },
            "required": ["aspect"],
        },
    },
    {
        "name": "update_game_state",
        "description": "Update the current game state (location, conditions, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "New location name",
                },
                "add_condition": {
                    "type": "string",
                    "description": "Condition to add to the character",
                },
                "remove_condition": {
                    "type": "string",
                    "description": "Condition to remove from the character",
                },
                "flags": {
                    "type": "object",
                    "description": "Game flags to set (e.g., {'door_unlocked': true})",
                },
            },
        },
    },
    {
        "name": "apply_damage_or_healing",
        "description": "Apply damage or healing to a character or creature.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Who receives the damage/healing ('player' or NPC/monster name)",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount of damage (positive) or healing (negative)",
                },
                "damage_type": {
                    "type": "string",
                    "description": "Type of damage (e.g., 'slashing', 'fire', 'poison')",
                },
                "source": {
                    "type": "string",
                    "description": "What caused the damage/healing",
                },
            },
            "required": ["target", "amount"],
        },
    },
    {
        "name": "roll_morale",
        "description": "Make a morale check for monsters/NPCs (B/X specific). Roll 2d6 vs morale score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "creature_name": {
                    "type": "string",
                    "description": "Name of the creature making the morale check",
                },
                "morale_score": {
                    "type": "integer",
                    "description": "The creature's morale score (2-12)",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the morale check is being made (e.g., 'first casualty', 'half casualties')",
                },
            },
            "required": ["creature_name", "morale_score", "reason"],
        },
    },
    {
        "name": "roll_reaction",
        "description": "Make a reaction roll for NPC encounters (B/X specific). Roll 2d6, modified by CHA.",
        "input_schema": {
            "type": "object",
            "properties": {
                "npc_name": {
                    "type": "string",
                    "description": "Name or type of the NPC/creature",
                },
                "cha_modifier": {
                    "type": "integer",
                    "description": "Charisma modifier to apply to the roll",
                },
                "context": {
                    "type": "string",
                    "description": "Context for the encounter",
                },
            },
            "required": ["npc_name"],
        },
    },
    {
        "name": "calculate_thac0",
        "description": "Calculate if an attack hits using THAC0 vs AC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "attacker_thac0": {
                    "type": "integer",
                    "description": "Attacker's THAC0 value",
                },
                "target_ac": {
                    "type": "integer",
                    "description": "Target's Armor Class (descending, 9 to -3)",
                },
                "attack_roll": {
                    "type": "integer",
                    "description": "The d20 roll result",
                },
                "modifiers": {
                    "type": "integer",
                    "description": "Any modifiers to the attack roll",
                    "default": 0,
                },
            },
            "required": ["attacker_thac0", "target_ac", "attack_roll"],
        },
    },
    {
        "name": "award_xp",
        "description": "Award experience points to the player character.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Amount of XP to award",
                },
                "source": {
                    "type": "string",
                    "description": "Source of XP (e.g., 'gold from treasure', 'defeating 3 goblins')",
                },
            },
            "required": ["amount", "source"],
        },
    },
    {
        "name": "oracle_query",
        "description": "Ask the Mythic GME oracle a yes/no question. Use when NPC behavior is uncertain, or to determine unknown world state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The yes/no question to ask the oracle",
                },
                "odds": {
                    "type": "string",
                    "enum": ["impossible", "no_way", "very_unlikely", "unlikely", "fifty_fifty", "somewhat_likely", "likely", "very_likely", "near_sure_thing", "sure_thing", "has_to_be"],
                    "description": "How likely is 'yes' given the circumstances",
                },
                "chaos_factor": {
                    "type": "integer",
                    "description": "Current chaos factor (1-9, default 5)",
                    "default": 5,
                },
            },
            "required": ["question", "odds"],
        },
    },
    {
        "name": "random_event",
        "description": "Generate a random event using Mythic GME tables. Use when doubles are rolled on oracle, or to add unexpected twists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Current scene context to help interpret the event",
                },
            },
            "required": ["context"],
        },
    },
]

# Solo Hero tools (for running classic modules with a single character)
SOLO_HERO_TOOLS = [
    {
        "name": "convert_damage_to_harm",
        "description": "Convert a hero's damage roll to 'harm' for killing foes. In Solo Hero rules, heroes deal harm instead of damage to foes. Use this EVERY time the hero attacks and deals damage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "damage_rolled": {
                    "type": "integer",
                    "description": "The total damage rolled by the hero",
                },
                "target_hd": {
                    "type": "integer",
                    "description": "Total HD of the target(s) being attacked",
                },
                "target_description": {
                    "type": "string",
                    "description": "Description of target(s) (e.g., '2 goblins', 'an ogre')",
                },
            },
            "required": ["damage_rolled", "target_hd", "target_description"],
        },
    },
    {
        "name": "roll_fray_die",
        "description": "Roll the hero's Fray Die (1d8) at the end of their combat turn. This automatically damages any foe of 1 HD or less within melee range, representing the hero's superior combat prowess.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_description": {
                    "type": "string",
                    "description": "Description of weak foes in melee range (e.g., 'the remaining goblins')",
                },
            },
            "required": ["target_description"],
        },
    },
    {
        "name": "defy_death",
        "description": "Roll when the hero is reduced to 0 HP. This determines if they die, are knocked out, or get a second wind. Roll 1d20 + CON modifier + level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "con_modifier": {
                    "type": "integer",
                    "description": "Hero's Constitution modifier",
                },
                "level": {
                    "type": "integer",
                    "description": "Hero's character level",
                },
            },
            "required": ["con_modifier", "level"],
        },
    },
    {
        "name": "roll_trait_check",
        "description": "Make a trait check (2d8 + modifier) for non-combat challenges in Solo Hero rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trait": {
                    "type": "string",
                    "description": "The trait being tested (e.g., 'Strength', 'Dexterity', 'Intelligence')",
                },
                "modifier": {
                    "type": "integer",
                    "description": "Modifier to apply (usually ability modifier)",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["easy", "normal", "hard", "very_hard", "heroic"],
                    "description": "Difficulty of the check",
                },
                "task_description": {
                    "type": "string",
                    "description": "What the hero is attempting",
                },
            },
            "required": ["trait", "modifier", "difficulty", "task_description"],
        },
    },
]

# Adventure-specific tools (only available when campaign has adventure module)
ADVENTURE_TOOLS = [
    {
        "name": "advance_scene",
        "description": "Mark the current scene as complete and transition to the next scene. Use when a planned scene concludes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scene_completed": {
                    "type": "string",
                    "description": "Name of the scene that was completed",
                },
                "outcome": {
                    "type": "string",
                    "description": "How the scene resolved (e.g., 'players negotiated peace', 'defeated the goblins')",
                },
                "next_scene": {
                    "type": "string",
                    "description": "Name of the next planned scene to activate, or 'continue' for free exploration",
                },
            },
            "required": ["scene_completed", "outcome"],
        },
    },
    {
        "name": "update_plot_thread",
        "description": "Update the status of an active plot thread in the adventure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_name": {
                    "type": "string",
                    "description": "Name of the plot thread",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "resolved", "escalated"],
                    "description": "New status for the plot thread",
                },
                "notes": {
                    "type": "string",
                    "description": "What changed or happened with this thread",
                },
            },
            "required": ["thread_name", "status", "notes"],
        },
    },
    {
        "name": "record_npc_encounter",
        "description": "Record meeting an NPC from the adventure module.",
        "input_schema": {
            "type": "object",
            "properties": {
                "npc_name": {
                    "type": "string",
                    "description": "Name of the NPC encountered",
                },
                "attitude": {
                    "type": "string",
                    "enum": ["friendly", "neutral", "hostile"],
                    "description": "NPC's current attitude toward the player",
                },
                "notes": {
                    "type": "string",
                    "description": "Key information exchanged or notable events",
                },
            },
            "required": ["npc_name", "attitude"],
        },
    },
    {
        "name": "update_adventure_location",
        "description": "Update the current location within the adventure module. IMPORTANT: When using a parsed adventure module, you MUST provide the location_key from the module's location list (e.g., '1', '2', '33a'). This ensures you have access to the correct location details, encounters, and treasure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location name as it appears in the adventure (e.g., 'Alcoves', 'Kitchen', 'Room of Pools')",
                },
                "location_key": {
                    "type": "string",
                    "description": "The location key/number from the adventure module (e.g., '1', '2', '31'). CRITICAL: Use this when moving to a parsed module location to get full context.",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "add_item",
        "description": "Add an item to the character's inventory. Use when player picks up, receives, or acquires items. For gold/coins, this adds to the character's gold total. For other items, adds to equipment list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "Name of the item (e.g., 'Longsword', 'Healing Potion', 'Gold Pieces')",
                },
                "quantity": {
                    "type": "integer",
                    "description": "How many of the item to add (default 1)",
                    "default": 1,
                },
                "value_gp": {
                    "type": "number",
                    "description": "Value in gold pieces (for treasure). For gold/coins, this is the amount to add.",
                },
            },
            "required": ["item_name"],
        },
    },
    {
        "name": "update_subarea_position",
        "description": "Update the player's position WITHIN a location. Use this for internal movement (progressing through a corridor, reaching a new area within a room). CRITICAL: Many locations have sub-areas (alcoves, steps, intersections, etc.) with different features and triggers. Track the player's progression through these sub-areas to reveal content in the correct order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subarea_id": {
                    "type": "string",
                    "description": "ID of the sub-area the player has reached (e.g., '1_alcoves_1', '1_intersection')",
                },
                "subarea_name": {
                    "type": "string",
                    "description": "Human-readable name of the sub-area (e.g., 'First Alcoves', 'Top of Steps')",
                },
                "triggered_content": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of triggers or features that activate upon reaching this sub-area",
                },
            },
            "required": ["subarea_id", "subarea_name"],
        },
    },
]

# Journal tools for session continuity and world tracking
JOURNAL_TOOLS = [
    {
        "name": "query_journal",
        "description": "Query past journal entries, session summaries, and adventure history. Use this to recall what happened in previous sessions, track NPCs met, locations discovered, and key events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_type": {
                    "type": "string",
                    "enum": ["auto_summary", "player_note", "key_event", "location", "npc", "combat", "loot", "all"],
                    "description": "Type of entries to retrieve. Use 'all' to get mixed types.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return (default 5)",
                    "default": 5,
                },
            },
        },
    },
    {
        "name": "record_discovery",
        "description": "Record a significant discovery or event to the journal - new locations, key events, important loot, NPC encounters. Use this to ensure important moments are preserved for future sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_type": {
                    "type": "string",
                    "enum": ["key_event", "location", "npc", "combat", "loot"],
                    "description": "Type of discovery being recorded",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the entry (e.g., 'Met the Innkeeper', 'Discovered the Hidden Cave')",
                },
                "content": {
                    "type": "string",
                    "description": "Description of what was discovered or happened",
                },
            },
            "required": ["entry_type", "title", "content"],
        },
    },
    {
        "name": "query_world_state",
        "description": "Query the current world state - active consequences from player actions, discovered locations, and world changes. Use this to maintain consistency with past events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_consequences": {
                    "type": "boolean",
                    "description": "Include active world consequences from player actions",
                    "default": True,
                },
                "include_locations": {
                    "type": "boolean",
                    "description": "Include discovered locations",
                    "default": True,
                },
            },
        },
    },
]

# Calendar and time tracking tools
CALENDAR_TOOLS = [
    {
        "name": "advance_time",
        "description": "Advance in-game time by hours or days. Use when the party rests, travels, or time passes. This updates moon phases, triggers scheduled events, and changes weather.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Number of hours to advance (0-24)",
                    "default": 0,
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to advance",
                    "default": 0,
                },
                "reason": {
                    "type": "string",
                    "description": "Why time is passing (e.g., 'resting at the inn', 'traveling to the castle')",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Get the current in-game date, time of day, moon phase, season, and weather. Use this to describe atmospheric conditions and track time.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "schedule_event",
        "description": "Schedule a future event in the calendar. Use for festivals, NPC appointments, or timed plot events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the event (e.g., 'Harvest Festival', 'Meeting with Lord Blackwood')",
                },
                "day": {
                    "type": "integer",
                    "description": "Day of the month (1-31)",
                },
                "month": {
                    "type": "integer",
                    "description": "Month number (1-12)",
                },
                "year": {
                    "type": "integer",
                    "description": "Year (optional - omit for recurring yearly events)",
                },
                "recurring": {
                    "type": "boolean",
                    "description": "Whether this event repeats yearly",
                    "default": False,
                },
                "description": {
                    "type": "string",
                    "description": "Details about the event",
                },
            },
            "required": ["name", "day", "month"],
        },
    },
    {
        "name": "check_upcoming_events",
        "description": "Check for scheduled events in the near future. Use to remind players of upcoming deadlines or appointments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to check (default 30)",
                    "default": 30,
                },
            },
        },
    },
]

# Map and dungeon exploration tools
# Encounter management tools (persistent combat state)
ENCOUNTER_TOOLS = [
    {
        "name": "start_encounter",
        "description": "Start a tracked combat encounter. MANDATORY before ANY combat begins. If fighting creatures from the current module location, you can omit enemies to auto-populate from the module's encounter data. For wandering monsters or ad-hoc fights, provide the enemies list. This creates persistent DB records for all combatants.",
        "input_schema": {
            "type": "object",
            "properties": {
                "encounter_name": {
                    "type": "string",
                    "description": "Name for this encounter (e.g., 'Goblin Ambush', 'Wandering Skeleton Patrol')",
                },
                "source": {
                    "type": "string",
                    "enum": ["fixed", "wandering", "custom"],
                    "description": "Source of enemies: 'fixed' = auto-populate from current location's fixed encounter, 'wandering' = auto-populate from wandering monster table (provide wandering_roll), 'custom' = use provided enemies list. Default: 'fixed' if no enemies provided, 'custom' if enemies provided.",
                },
                "wandering_roll": {
                    "type": "integer",
                    "description": "The die roll result for wandering monster table lookup (only used when source='wandering')",
                },
                "enemies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Enemy name (e.g., 'Orc 1', 'Goblin Leader')",
                            },
                            "hd": {
                                "type": "integer",
                                "description": "Hit Dice",
                            },
                            "hp": {
                                "type": "integer",
                                "description": "Hit points (auto-rolled from HD if omitted)",
                            },
                            "ac": {
                                "type": "integer",
                                "description": "Armor Class (descending, B/X style)",
                            },
                            "thac0": {
                                "type": "integer",
                                "description": "To Hit Armor Class 0",
                            },
                            "damage": {
                                "type": "string",
                                "description": "Damage notation (e.g., '1d6', '1d8+1')",
                            },
                            "morale": {
                                "type": "integer",
                                "description": "Morale score (2-12)",
                            },
                            "xp_value": {
                                "type": "integer",
                                "description": "XP awarded for defeating this enemy",
                            },
                        },
                        "required": ["name"],
                    },
                    "description": "List of enemies. Omit to auto-populate from module encounter data.",
                },
            },
        },
    },
    {
        "name": "end_encounter",
        "description": "End the current combat encounter. MANDATORY when combat concludes for any reason. Records outcome and awards XP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": ["victory", "defeat", "fled"],
                    "description": "How combat ended: victory (enemies defeated/fled), defeat (hero fell), fled (hero retreated)",
                },
            },
            "required": ["outcome"],
        },
    },
]

MAP_TOOLS = [
    {
        "name": "display_map",
        "description": "Display the current dungeon map to the player, showing explored areas and fog of war. Use when the player asks to see the map or when entering a new mapped area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_markers": {
                    "type": "boolean",
                    "description": "Whether to show map markers (treasure, danger, etc.)",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "update_map_position",
        "description": "Move the player to a new position on the map and reveal nearby areas. Use when the player moves through mapped locations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate on the map",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate on the map",
                },
                "reveal_radius": {
                    "type": "integer",
                    "description": "How many cells to reveal around the new position (default 2)",
                    "default": 2,
                },
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "add_map_marker",
        "description": "Add a marker to the map for treasure, danger, secrets, or points of interest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate for the marker",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate for the marker",
                },
                "symbol": {
                    "type": "string",
                    "description": "Single character symbol (e.g., '$' for treasure, '!' for danger, '?' for secret)",
                },
                "label": {
                    "type": "string",
                    "description": "Description of what the marker represents",
                },
                "marker_type": {
                    "type": "string",
                    "enum": ["treasure", "danger", "secret", "npc", "entrance", "exit", "generic"],
                    "description": "Type of marker for styling",
                    "default": "generic",
                },
            },
            "required": ["x", "y", "symbol", "label"],
        },
    },
    {
        "name": "create_map",
        "description": "Create a new ASCII dungeon map for the current location. Use when entering a dungeon, cave, or building that should be mapped. The map will use fog of war - only explored areas are visible to the player.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the map (e.g., 'Goblin Caves Level 1', 'The Old Mill')",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this map represents",
                },
                "map_type": {
                    "type": "string",
                    "enum": ["dungeon", "cave", "building", "outdoor", "custom"],
                    "description": "Type of map to generate",
                    "default": "dungeon",
                },
                "size": {
                    "type": "string",
                    "enum": ["small", "medium", "large"],
                    "description": "Size of the map: small (15x15), medium (25x25), large (40x40)",
                    "default": "medium",
                },
                "custom_ascii": {
                    "type": "string",
                    "description": "Optional: Provide your own ASCII map. Use '#' for walls, '.' for floor, '+' for doors, '~' for water, etc.",
                },
                "entrance_x": {
                    "type": "integer",
                    "description": "X coordinate of the entrance (where player starts)",
                },
                "entrance_y": {
                    "type": "integer",
                    "description": "Y coordinate of the entrance (where player starts)",
                },
            },
            "required": ["name"],
        },
    },
]

# Tools for displaying atmospheric images to the player
IMAGE_TOOLS = [
    {
        "name": "show_illustration",
        "description": "Display an illustration or atmospheric image to the player. Use this to enhance key moments: entering a dramatic location, encountering a notable NPC or monster, discovering treasure, or setting a scene. Only use for significant moments - don't overuse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_type": {
                    "type": "string",
                    "enum": ["location", "monster", "npc", "treasure", "scene", "map"],
                    "description": "What type of image to show",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the image should depict (e.g., 'the ancient stone archway', 'the goblin chief'). Used to find matching extracted images or generate new ones.",
                },
                "mood": {
                    "type": "string",
                    "enum": ["dramatic", "mysterious", "peaceful", "dangerous", "wondrous", "dark"],
                    "description": "The mood/atmosphere of the scene",
                    "default": "dramatic",
                },
            },
            "required": ["image_type", "description"],
        },
    },
]
