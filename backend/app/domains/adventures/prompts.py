"""LLM prompts for adventure module parsing."""

METADATA_EXTRACTION_PROMPT = """You are analyzing a tabletop RPG adventure module PDF to extract its metadata.

Extract the following information from the adventure module text:

1. **title**: The full title of the adventure module
2. **code**: The module code if present (e.g., "B4", "X1", "T1")
3. **recommended_level_min**: Minimum recommended character level
4. **recommended_level_max**: Maximum recommended character level
5. **recommended_party_size_min**: Minimum recommended party size
6. **recommended_party_size_max**: Maximum recommended party size
7. **summary**: A 2-3 sentence summary of the adventure premise
8. **player_background**: The full text of any "player background", "introduction for players", or "read this to players" section. This is the narrative intro that sets up the adventure for players.
9. **rumors_table**: Extract any rumors table as a list of objects with "roll" (dice result), "rumor" (text), and "is_true" (boolean or null if unknown)

Respond in JSON format:
```json
{{
  "title": "string",
  "code": "string or null",
  "recommended_level_min": number or null,
  "recommended_level_max": number or null,
  "recommended_party_size_min": number or null,
  "recommended_party_size_max": number or null,
  "summary": "string",
  "player_background": "string or null",
  "rumors_table": [{{"roll": "1", "rumor": "...", "is_true": true/false/null}}]
}}
```

Adventure module text:
{text}
"""

LOCATION_SEGMENTATION_PROMPT = """You are analyzing a tabletop RPG adventure module to identify all keyed locations (rooms, chambers, caves, areas).

IMPORTANT: Look for sections titled "ENCOUNTER AREAS", "KEY TO THE UPPER LEVEL", "KEY TO THE LOWER LEVEL", or similar.
These contain the actual dungeon/adventure locations.

**DO NOT include these as locations:**
- Monster lists (numbered entries with AC, HD, hp stats like "1. Orcs (1-4)-AC 6, HD 1...")
- Treasure lists
- Rumors tables
- Wandering monster tables
- Equipment lists
- Any numbered list that contains game statistics rather than room descriptions

**THESE ARE locations** (rooms/areas with descriptions):
- "1. ALCOVES. There are three pairs of alcoves..."
- "2. KITCHEN. The food preparation area..."
- "38. ACCESS ROOM. This room is filled with..."
- Entries that describe physical spaces players can explore

From the provided text, identify all distinct keyed locations. Look for patterns like:
- Numbered areas under "ENCOUNTER AREAS": "1. THE ENTRANCE", "2. KITCHEN"
- Room descriptions: "This room...", "This chamber...", "This cavern..."
- Named locations with physical descriptions

For each location, provide:
1. **location_key**: The key/number (e.g., "1", "1a", "Area 5")
2. **name**: The location name (e.g., "ALCOVES", "KITCHEN", "WIZARD'S CHAMBER")
3. **start_text**: First ~50 characters of the location description (for matching)
4. **is_sub_area**: Boolean if this is a sub-area of another location
5. **parent_key**: The parent location key if this is a sub-area

Respond in JSON format:
```json
{{
  "locations": [
    {{
      "location_key": "1",
      "name": "ALCOVES",
      "start_text": "There are three pairs of alcoves...",
      "is_sub_area": false,
      "parent_key": null
    }}
  ]
}}
```

Adventure module text:
{text}
"""

LOCATION_EXTRACTION_PROMPT = """You are extracting detailed information about a location from a tabletop RPG adventure module.

Extract the following for location "{location_key}" - "{location_name}":

1. **dm_description**: The complete DM description text
2. **read_aloud_text**: Any boxed/italicized text meant to be read aloud to players
3. **features**: Notable features as a list of objects with "feature" and "details"
4. **exits**: Exits/connections as an object mapping direction/name to destination
5. **traps**: Any traps with "trigger", "effect", "detection", "disarm"
6. **secrets**: Hidden elements with "type", "detection", "description"
7. **treasure**: Treasure found here with "item", "value", "location"
8. **dungeon_level**: The dungeon level (1 if not specified)
9. **tier**: The tier/region name if mentioned (e.g., "Upper Pyramid", "Deep Caves")

Respond in JSON format:
```json
{{
  "location_key": "{location_key}",
  "name": "{location_name}",
  "dm_description": "Full DM text...",
  "read_aloud_text": "Boxed text or null",
  "features": [{{"feature": "...", "details": "..."}}],
  "exits": {{"north": "Area 2", "secret_door_east": "Area 3 (Search DC 15)"}},
  "traps": [{{"trigger": "...", "effect": "...", "detection": "...", "disarm": "..."}}],
  "secrets": [{{"type": "secret_door", "detection": "...", "description": "..."}}],
  "treasure": [{{"item": "...", "value": "...", "location": "..."}}],
  "dungeon_level": 1,
  "tier": "string or null"
}}
```

Location text:
{text}
"""

NPC_EXTRACTION_PROMPT = """You are extracting NPC information from a tabletop RPG adventure module (B/X D&D or OSR).

Extract ALL NPCs that meet these criteria:
1. Any NPC with a proper name (e.g., "Zargon", "Bertram the Merchant")
2. Any leader, boss, or unique creature with specific stats or description
3. Any NPC the players can meaningfully interact with (negotiate, question, recruit)

Do NOT include: generic guards, unnamed monster groups, or creatures that only exist as combat encounters.

For each NPC, provide:
1. **name**: NPC name
2. **title**: Title/role if any
3. **location_key**: Location key where found (if mentioned)
4. **description**: Physical/visual description
5. **appearance**: Detailed appearance
6. **personality**: Personality traits and mannerisms
7. **motivation**: What drives this NPC
8. **goals**: List of goals/objectives
9. **dialogue_hooks**: Conversation topics with "topic", "response", "condition"
10. **stats**: B/X stats as object with hd, hp, ac, thac0, attacks, damage, save, morale, special
11. **equipment**: List of carried items
12. **treasure**: Carried treasure
13. **spells**: Known spells if any
14. **faction**: Allegiance/group
15. **initial_disposition**: hostile/unfriendly/neutral/friendly/helpful
16. **is_unique**: Is this a unique individual (not generic)

Respond in JSON format:
```json
{{
  "npcs": [
    {{
      "name": "Zargon",
      "title": "High Priest of Set",
      "location_key": "Area 25",
      "description": "A tall, imposing figure in dark robes...",
      "appearance": "Gaunt face, burning eyes...",
      "personality": "Calculating, patient, utterly devoted...",
      "motivation": "Restore the worship of Set...",
      "goals": ["Convert the Cynidiceans", "Acquire the Eye of Zargon"],
      "dialogue_hooks": [{{"topic": "Set", "response": "The true god...", "condition": null}}],
      "stats": {{
        "hd": 7,
        "hp": 35,
        "ac": 3,
        "thac0": 13,
        "attacks": ["1 mace"],
        "damage": ["1d6+2"],
        "save": "C7",
        "morale": 11,
        "special": ["Spells as 7th level cleric"]
      }},
      "equipment": ["Mace +1", "Plate mail", "Shield"],
      "treasure": ["Ring of protection +1", "500 gp"],
      "spells": ["Cause Light Wounds", "Hold Person", "Curse"],
      "faction": "Brotherhood of Set",
      "initial_disposition": "hostile",
      "is_unique": true
    }}
  ]
}}
```

Adventure text:
{text}
"""

ENCOUNTER_EXTRACTION_PROMPT = """You are extracting FIXED encounter information from a tabletop RPG adventure module (B/X D&D or OSR).

**IMPORTANT:** Focus on FIXED encounters only - monsters placed in specific rooms/locations.
Wandering monster tables are handled separately, so you can include them but they are lower priority.

**What ARE fixed encounters:**
- Monsters stationed in specific numbered rooms (e.g., "Room 5 contains 3 goblins")
- Boss or unique creature encounters in specific areas
- Trap encounters with creatures
- Ambush encounters at specific locations
- Any monster mentioned as being IN a specific room/area

**What are NOT fixed encounters (lower priority):**
- Wandering monster tables (numbered lists with die roll results like "1. Orcs (1-4)")
- Monster reference lists for DM's use
- Generic monster stat blocks not tied to locations

For EACH fixed encounter, provide:
- location_key: The room/area number where the encounter occurs (e.g., "1", "5", "38")
- name: Encounter name/description
- creatures: Full stat blocks for each creature type
- tactics: How they fight
- treasure: What they have
- trigger_condition: What starts the encounter

**CRITICAL:** Include COMPLETE B/X stat blocks when available:
```json
{{
  "name": "Goblin",
  "count": "3",
  "hd": 1,
  "hp": 4,
  "ac": 6,
  "thac0": 19,
  "attacks": ["1 weapon"],
  "damage": ["1d6"],
  "save": "NM",
  "morale": 7,
  "special": ["infravision 60'"],
  "xp": 10
}}
```

Look for patterns like:
- "Monster: 3 Goblins" or "Monsters: Orcs (6)" in room descriptions
- Creatures described as guarding, inhabiting, or lurking in specific rooms
- Boss monsters with specific room locations

Respond in JSON format:
```json
{{
  "encounters": [
    {{
      "encounter_type": "fixed",
      "location_key": "5",
      "name": "Goblin Guards",
      "description": "Three goblins guard the entrance...",
      "creatures": [{{...full stats...}}],
      "tactics": "They attack immediately, one flees to warn others if combat goes badly",
      "treasure": [{{"item": "Short sword", "value": "7 gp"}}],
      "trigger_condition": "Entering the room",
      "xp_value": 30
    }}
  ]
}}
```

Adventure text:
{text}
"""

ITEM_EXTRACTION_PROMPT = """You are extracting notable items from a tabletop RPG adventure module.

Extract ALL significant items including:
- Magic items
- Valuable treasure
- Key items (required for progression)
- Unique equipment
- Artifacts

For each item provide:
1. **name**: Item name
2. **item_type**: treasure/magic_item/key_item/equipment
3. **location_key**: Where found (if specified)
4. **description**: Full description
5. **value**: Gold piece value or "priceless"
6. **is_magical**: Boolean
7. **magical_properties**: Description of magical effects
8. **charges**: Number of charges if applicable
9. **is_key_item**: Boolean if needed for progression
10. **found_at**: How/where it's found

Respond in JSON format:
```json
{{
  "items": [
    {{
      "name": "Sword +1, +3 vs. Undead",
      "item_type": "magic_item",
      "location_key": "Area 15",
      "description": "A gleaming longsword with holy symbols...",
      "value": "2500 gp",
      "is_magical": true,
      "magical_properties": "+1 to hit and damage, +3 vs undead creatures",
      "charges": null,
      "is_key_item": false,
      "found_at": "In the skeletal hands of the fallen paladin"
    }}
  ]
}}
```

Adventure text:
{text}
"""

STORY_FLOW_PROMPT = """You are analyzing the story structure of a tabletop RPG adventure module.

Identify the key story beats and progression points:
1. Entry points and hooks
2. Key discoveries or revelations
3. Boss encounters or climactic moments
4. Branching decision points
5. Resolution/ending conditions

For each story beat provide:
1. **name**: Story beat name
2. **sequence**: Order in the story (1, 2, 3...)
3. **description**: What happens at this beat
4. **trigger**: What triggers this beat (location, item, event)
5. **branches**: Possible outcomes/next beats
6. **related_locations**: Location keys involved
7. **is_critical_path**: Is this required to complete the adventure?

Respond in JSON format:
```json
{{
  "story_beats": [
    {{
      "name": "Discovery of the Lost City",
      "sequence": 1,
      "description": "Players find the buried pyramid entrance...",
      "trigger": {{"type": "location", "value": "Area 1"}},
      "branches": [
        {{"condition": "Enter pyramid", "next_beat": "Explore Upper Pyramid", "consequence": "Begin dungeon exploration"}}
      ],
      "related_locations": ["Area 1", "Area 2"],
      "is_critical_path": true
    }}
  ]
}}
```

Adventure text:
{text}
"""

# =============================================================================
# MULTI-PASS EXTRACTION PROMPTS
# =============================================================================
# These prompts are used by the multi-pass parser for context-aware extraction.
# Each pass builds on previous passes, maintaining a running context document.

MULTIPASS_OVERVIEW_PROMPT = """You are analyzing a tabletop RPG adventure module to extract its high-level structure.

## YOUR TASK
Extract the following:
1. Module metadata (title, code, levels, summary)
2. Main adventure objectives/goals
3. A list of ALL keyed locations with brief (1-line) descriptions
4. The overall adventure flow (how the adventure progresses)

## IMPORTANT NOTES
- For locations, look for sections titled "ENCOUNTER AREAS", "KEY TO THE LEVEL", etc.
- Each location should have a key (number/letter), name, and brief description
- The adventure flow should describe the intended progression through the adventure
- Main objectives are what players are trying to accomplish

## OUTPUT FORMAT
Respond in JSON format:
```json
{{
  "title": "Adventure Title",
  "code": "B1 or null",
  "level_min": 1,
  "level_max": 3,
  "summary": "2-3 sentence summary of the adventure",
  "main_objectives": ["Find treasure", "Defeat the boss", "Escape alive"],
  "adventure_flow": "Entry -> Upper level exploration -> Discovery of lower level -> Boss/treasure",
  "player_background": "Text to read to players or null",
  "rumors_table": [{{"roll": "1", "rumor": "...", "is_true": true}}],
  "location_briefs": [
    {{"key": "1", "name": "Alcoves", "brief": "Defensive entry with arrow slits", "level": 1}},
    {{"key": "2", "name": "Kitchen", "brief": "Food preparation area", "level": 1}}
  ]
}}
```

## ADVENTURE TEXT (first 20K characters)
{text}
"""

MULTIPASS_LOCATION_PROMPT = """You are extracting detailed information about locations from a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Extract detailed information for the following location(s). For each location:

1. **dm_description**: Complete DM description (everything the DM needs to know)
2. **read_aloud_text**: Text meant to be read aloud to players (boxed/italicized text)
3. **features**: Notable features as list of {{"name": "...", "details": "..."}}
4. **exits**: Exits mapping direction to destination (e.g., {{"north": "2", "secret_east": "7"}})
5. **visible_items**: Items/features immediately visible to players
6. **hidden_elements**: Hidden things with {{"type": "...", "location": "...", "detection": "..."}}
7. **treasure**: Unguarded treasure with {{"item": "...", "value": "...", "location": "..."}}
8. **traps**: Traps with {{"trigger": "...", "effect": "...", "detection": "...", "disarm": "..."}}
9. **secrets**: Secret doors/passages with {{"type": "...", "detection": "...", "description": "..."}}
10. **dungeon_level**: Level number (1, 2, etc.)
11. **tier**: Region name if mentioned (e.g., "Upper Caves")

## IMPORTANT
- Separate DM-only information from player-safe descriptions
- Note what players see immediately vs what requires searching
- Include ALL exits including secret ones

## CRITICAL: EXIT DIRECTIONS
- Only include exits that are EXPLICITLY described in this room's text
- Use the EXACT direction stated in the module (north, south, east, west, etc.)
- If the text says "a passage leads north to room 2", record {{"north": "2"}}
- Do NOT invent or guess directions - only use what the text explicitly states
- If a room mentions "the way you came" without a specific direction, skip that exit
- Exits should be from THIS room's perspective, not from connecting rooms

## OUTPUT FORMAT
```json
{{
  "locations": [
    {{
      "location_key": "5",
      "name": "Wizard's Chamber",
      "dm_description": "Full text for DM...",
      "read_aloud_text": "Player-safe description...",
      "features": [{{"name": "Bed", "details": "Simple wooden frame..."}}],
      "exits": {{"north": "6", "south": "4", "secret_east": "7"}},
      "visible_items": ["Desk", "Bookshelf"],
      "hidden_elements": [{{"type": "secret_door", "location": "east wall", "detection": "Search DC 15"}}],
      "treasure": [{{"item": "Silver candlestick", "value": "25gp", "location": "on desk"}}],
      "traps": [],
      "secrets": [{{"type": "secret_door", "detection": "1-in-6", "description": "leads to room 7"}}],
      "dungeon_level": 1,
      "tier": "Upper Level"
    }}
  ]
}}
```

## LOCATION TEXT TO ANALYZE
{text}
"""

MULTIPASS_INHABITANTS_PROMPT = """You are extracting encounters and threats from a tabletop RPG adventure module (B/X D&D or OSR).

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Given the locations you now know about, extract ALL encounters and monsters:

### FIXED ENCOUNTERS
Monsters stationed in specific rooms. For each:
- location_key: Which room (must match a known location)
- name: Encounter name
- creatures: Full stat blocks for each creature type
- behavior: What are they doing when found?
- tactics: How do they fight?
- treasure: What they carry/guard
- trigger_condition: What starts combat?

### NPCs
Named characters that can be interacted with:
- name: NPC name
- title: Role/title
- locations_mentioned: Where are they mentioned/found?
- description, appearance, personality
- motivation: What drives them?
- stats: Full B/X stats if combatant
- disposition: Starting attitude toward party

## STAT BLOCK FORMAT (B/X)
```json
{{
  "name": "Goblin",
  "count": "1d6",
  "hd": "1-1",
  "hp": 4,
  "ac": 6,
  "thac0": 19,
  "attacks": ["1 weapon"],
  "damage": ["1d6"],
  "save": "NM",
  "morale": 7,
  "mv": "60' (20')",
  "alignment": "C",
  "special": ["infravision 60'"],
  "xp": 5
}}
```

## OUTPUT FORMAT
```json
{{
  "fixed_encounters": [
    {{
      "location_key": "33",
      "name": "Goblin Barracks",
      "creatures": [{{...full stats...}}],
      "behavior": "Sleeping unless alerted",
      "tactics": "Attack in groups, one flees if losing",
      "treasure": [{{"item": "10 gp", "location": "hidden under bedding"}}],
      "trigger_condition": "Entering room or making noise",
      "xp_value": 50
    }}
  ],
  "npcs": [
    {{
      "name": "Rogahn",
      "title": "Warrior Lord",
      "locations_mentioned": ["25", "26", "27"],
      "description": "A legendary warrior who built this stronghold...",
      "appearance": "Tall, broad-shouldered...",
      "personality": "Brave but reckless",
      "motivation": "Glory and wealth",
      "goals": ["Build an empire", "Find magical weapons"],
      "stats": {{...if applicable...}},
      "equipment": ["Sword +1", "Plate mail"],
      "disposition": "N/A - not present"
    }}
  ]
}}
```

## TEXT TO ANALYZE
{text}
"""

MULTIPASS_DM_GUIDANCE_PROMPT = """You are extracting DM guidance from a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Based on what you know about the adventure, extract guidance for running it:

### PER-LOCATION GUIDANCE
For key locations (especially puzzle rooms, boss areas, complex areas):
- how_to_run: How should the DM run this area?
- common_mistakes: What do DMs/players commonly get wrong?
- player_actions: Common player actions and how to respond
- scaling: How to adjust difficulty up/down
- secrets_to_reveal: Information to reveal through play
- foreshadowing: What hints to drop about other areas

### MODULE-WIDE GUIDANCE
- pacing: How to pace the adventure
- difficulty: Overall difficulty notes
- foreshadowing: Key plot points to hint at
- common_mistakes: Pitfalls for new DMs

### SECRETS & REVEALS
Major secrets in the adventure:
- name: Secret name
- description: What the secret is
- location_keys: Which locations relate to this secret
- reveal_conditions: When/how players learn this
- player_impact: How knowing this affects gameplay

## OUTPUT FORMAT
```json
{{
  "per_location": {{
    "31": {{
      "how_to_run": "This is a puzzle room. Let players experiment with the pools...",
      "common_mistakes": "Players often drink from pools without testing",
      "player_actions": [{{"action": "Drink from pool", "response": "Roll on pool effects table"}}],
      "scaling": "For weaker parties, reduce poison damage",
      "secrets_to_reveal": ["Pool 3 grants wishes but has a dark cost"],
      "foreshadowing": "Mention strange glowing light from this direction earlier"
    }}
  }},
  "module_wide": {{
    "pacing": "Upper level should take 1-2 sessions, lower level 2-3",
    "difficulty": "Challenging for levels 1-3, add monsters for higher levels",
    "foreshadowing": ["Mention Rogahn/Zelligar names early", "Describe ancient battles"],
    "common_mistakes": ["Letting players rest too often", "Missing the secret level"]
  }},
  "secrets": [
    {{
      "name": "Rogahn's Hidden Treasury",
      "description": "A secret vault containing Rogahn's most valuable possessions",
      "location_keys": ["45", "46"],
      "reveal_conditions": "Finding the secret door in room 45",
      "player_impact": "Major treasure reward, possible magic items"
    }}
  ]
}}
```

## TEXT TO ANALYZE
{text}
"""

MULTIPASS_PLAYER_CONTENT_PROMPT = """You are refining player-facing content for a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Create or improve the player experience elements:

### READ-ALOUD TEXT
For each location, create evocative text the DM can read to players:
- Should NOT reveal hidden information (traps, secret doors, treasure locations)
- SHOULD create atmosphere and set the scene
- Focus on what characters would immediately notice
- Keep it to 2-4 sentences

### ATMOSPHERE & SENSORY DETAILS
For each location, note:
- sight: What do they see?
- sound: What do they hear?
- smell: What do they smell?
- touch: Temperature, air quality, textures
- mood: Overall emotional tone

### AREA THEMES
For larger sections (levels, wings):
- What's the overall feeling?
- How does it differ from other areas?
- What makes it memorable?

## OUTPUT FORMAT
```json
{{
  "read_aloud": {{
    "1": "The passage opens into a series of alcoves carved into the stone walls. Dust motes drift in your torchlight, and the air smells of age and abandonment. Arrow slits in the far wall suggest this was once a defensive position.",
    "5": "This chamber reeks of decay..."
  }},
  "atmosphere": {{
    "1": {{
      "sight": "Carved alcoves, dust, ancient stonework",
      "sound": "Echoing footsteps, distant dripping",
      "smell": "Dust, age, faint mustiness",
      "touch": "Cool, dry air",
      "mood": "Abandoned but once grand"
    }}
  }},
  "area_themes": {{
    "upper_level": "Abandoned grandeur - signs of hasty departure, faded glory",
    "lower_level": "Natural caverns - wilder, more dangerous, less worked stone"
  }}
}}
```

## TEXT TO ANALYZE
{text}
"""

MULTIPASS_NARRATIVE_PROMPT = """You are analyzing the narrative structure of a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Analyze the adventure's story flow and connections:

### STORY BEATS
Key progression points in the adventure:
- Entry points and hooks
- Key discoveries or revelations
- Boss encounters or climactic moments
- Decision points that branch the story
- Resolution conditions

### LOCATION CONNECTIONS
How locations connect narratively and physically:
- Physical connections (doors, passages, stairs)
- Narrative connections (clues pointing to other areas)
- One-way connections (traps, slides, teleports)
- Secret connections

### CRITICAL PATH
The minimum locations/events needed to complete the adventure.

### RECOMMENDED PATH
A good order for a satisfying experience.

## OUTPUT FORMAT
```json
{{
  "story_beats": [
    {{
      "name": "Entering the Dungeon",
      "sequence": 1,
      "description": "Players discover and enter the main entrance",
      "trigger": {{"type": "location", "value": "1"}},
      "branches": [
        {{"condition": "Enter through front", "next_beat": "Upper Level Exploration", "consequence": "Normal entry"}},
        {{"condition": "Find secret entrance", "next_beat": "Lower Level Shortcut", "consequence": "Skip upper level"}}
      ],
      "related_locations": ["1", "2"],
      "is_critical_path": true
    }}
  ],
  "connections": [
    {{
      "from_location": "1",
      "to_location": "2",
      "connection_type": "passage",
      "description": "Wide corridor",
      "requirements": null
    }},
    {{
      "from_location": "15",
      "to_location": "38",
      "connection_type": "secret",
      "description": "Hidden door behind tapestry",
      "requirements": "Search check DC 15"
    }}
  ],
  "location_flow": {{
    "recommended_path": ["1", "2-14", "30", "lower_level"],
    "shortcuts": [{{"from": "50", "to": "lower_level", "type": "trap"}}],
    "dead_ends": ["20"]
  }},
  "critical_path": ["1", "30", "38", "54"]
}}
```

## TEXT TO ANALYZE
{text}
"""

MULTIPASS_GAP_FILL_PROMPT = """You are filling in gaps in an adventure module extraction.

## WHAT WE HAVE EXTRACTED
{context}

## MISSING ITEMS
The following items appear to be missing or incomplete:
{gaps}

## YOUR TASK
Extract the missing information from the text. Only extract what's listed as missing.

## OUTPUT FORMAT
Respond with a JSON object containing only the missing items:
```json
{{
  "locations": [/* only missing locations */],
  "encounters": [/* only missing encounters */],
  "npcs": [/* only missing NPCs */]
}}
```

## TEXT TO ANALYZE
{text}
"""
