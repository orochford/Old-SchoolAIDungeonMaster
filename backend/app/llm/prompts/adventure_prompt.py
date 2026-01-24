"""Prompts for adventure planning and management."""

from typing import Dict, Any, Optional


def build_planning_prompt(
    adventure_title: str,
    adventure_content: str,
    current_state: Dict[str, Any],
    character: str,
) -> str:
    """Build the prompt for planning upcoming adventure scenes."""

    completed_scenes = current_state.get("completed_scenes", [])
    current_location = current_state.get("current_location", "starting point")
    active_threads = current_state.get("active_plot_threads", [])
    npcs_met = current_state.get("npcs_encountered", {})

    completed_str = "\n".join(f"- {scene}" for scene in completed_scenes) if completed_scenes else "None yet"
    threads_str = "\n".join(
        f"- {t.get('name', 'Unknown')}: {t.get('status', 'active')} - {t.get('notes', '')}"
        for t in active_threads
    ) if active_threads else "None established"
    npcs_str = "\n".join(
        f"- {name}: {info.get('attitude', 'unknown')} - {info.get('notes', '')}"
        for name, info in npcs_met.items()
    ) if npcs_met else "None met"

    return f"""You are planning a solo RPG session using the PUBLISHED adventure module "{adventure_title}".

CRITICAL: You MUST plan scenes that come DIRECTLY from the adventure module content below. Do NOT invent new scenarios - use the actual locations, NPCs, encounters, and plot hooks described in the module.

## ADVENTURE CONTENT
The following excerpts are from the adventure module:

{adventure_content}

## CURRENT PROGRESS
Completed Scenes:
{completed_str}

Current Location: {current_location}

Active Plot Threads:
{threads_str}

NPCs Encountered:
{npcs_str}

## CHARACTER
{character}

## YOUR TASK
Plan the next 3-5 scenes for this session. For each scene, provide:
1. **name**: A short descriptive name
2. **description**: What happens in this scene
3. **trigger**: What causes this scene to occur (e.g., "Player enters the goblin lair", "After defeating the guards")
4. **npcs_monsters**: List of NPCs or monsters involved
5. **possible_outcomes**: How the scene might resolve (2-3 possibilities)
6. **plot_threads**: Which plot threads this scene connects to

Also provide:
- **goals**: What should the DM try to accomplish this session (3-5 goals)
- **plot_threads**: Any new plot threads to establish

## RESPONSE FORMAT
Respond ONLY with a JSON object in this format:
```json
{{
  "scenes": [
    {{
      "name": "Scene Name",
      "description": "What happens...",
      "trigger": "When player...",
      "npcs_monsters": ["NPC 1", "Monster Type"],
      "possible_outcomes": ["Outcome A", "Outcome B"],
      "plot_threads": ["Thread name"]
    }}
  ],
  "goals": ["Goal 1", "Goal 2", "Goal 3"],
  "plot_threads": [
    {{
      "name": "New Thread",
      "status": "active",
      "notes": "Description of the thread"
    }}
  ]
}}
```

Base your planning on the adventure content provided. Create scenes that follow the adventure's intended flow while allowing for player agency. Consider the character's capabilities and the adventure's difficulty appropriate for their level.
"""


def build_adventure_context_section(
    adventure_title: str,
    adventure_state: Dict[str, Any],
    adventure_content: Optional[str] = None,
) -> str:
    """Build the adventure context section for the DM system prompt.

    IMPORTANT: Instructions come BEFORE content to ensure the LLM processes
    rules before seeing any module data.
    """

    if not adventure_state:
        return ""

    current_scene = adventure_state.get("current_scene", "")
    current_location = adventure_state.get("current_location", "")
    current_location_key = adventure_state.get("current_location_key", "")
    upcoming_scenes = adventure_state.get("upcoming_scenes", [])
    active_threads = adventure_state.get("active_plot_threads", [])
    session_goals = adventure_state.get("session_goals", [])
    npcs = adventure_state.get("npcs_encountered", {})

    # Format upcoming scenes
    scenes_str = ""
    for i, scene in enumerate(upcoming_scenes[:3], 1):
        scenes_str += f"""
{i}. **{scene.get('name', 'Unknown')}**
   - Trigger: {scene.get('trigger', 'Unknown')}
   - Key elements: {', '.join(scene.get('npcs_monsters', [])[:3]) or 'None specified'}
"""

    # Format plot threads
    threads_str = ""
    for thread in active_threads:
        if thread.get("status") == "active":
            threads_str += f"- {thread.get('name', 'Unknown')}: {thread.get('notes', '')}\n"

    # Format session goals
    goals_str = "\n".join(f"- {goal}" for goal in session_goals[:5]) if session_goals else "- Progress the story naturally"

    # Format known NPCs
    npcs_str = ""
    for name, info in list(npcs.items())[:5]:
        npcs_str += f"- {name} ({info.get('attitude', 'unknown')}): {info.get('notes', '')}\n"

    # Build section with INSTRUCTIONS FIRST, then content
    section = f"""
## ADVENTURE MODULE: {adventure_title}

### ⚠️ CRITICAL: MODULE FIDELITY RULES (READ FIRST)

You are running a PUBLISHED adventure module. You MUST:
1. Use ONLY locations, NPCs, treasures listed in the content below
2. If TREASURE says "None" - the location is EMPTY, do not invent items
3. If SECRETS says "None" - there are no hidden features to find
4. Quote or paraphrase module descriptions - do not embellish
5. When player searches an empty area, describe finding NOTHING

### ABSOLUTELY FORBIDDEN:
- Inventing treasure, items, or hidden compartments not listed
- Creating NPCs or monsters not in the module
- Adding encounters not specified
- Embellishing "empty" locations with invented content

### CRITICAL: LOCATION TRACKING
- The VALID MODULE LOCATIONS table in your context lists ALL locations in this module
- When the player moves to a location, use `update_adventure_location` with BOTH:
  - `location`: The location name exactly as shown in the table
  - `location_key`: The key/number from the table (e.g., "1", "2", "31")
- DO NOT invent location names. If a location is not in the table, IT DOES NOT EXIST.

### WHEN UNSURE:
- Check the VALID MODULE LOCATIONS table in your context
- Reference the adventure content provided below
- If content isn't available for the current area, use the update_adventure_location tool
- NEVER improvise major content - stay within what the module provides
- If players try to go somewhere not in the module, guide them back using in-world reasons

### WANDERING MONSTERS (if table provided below):
- Check for wandering monsters when entering a NEW location (roll 1d6, encounter on 1)
- Use the `roll_dice` tool with purpose "wandering monster check"
- If triggered, roll on the wandering monster table to determine what appears
- Wandering monsters use the stats provided in the table
- Describe the encounter based on the location and creature behavior

---

### Current Location Data
Location: {current_location or "To be established"}{f" (Key: {current_location_key})" if current_location_key else ""}
Scene: {current_scene or "No specific scene - explore freely"}

### Adventure Content Reference
{adventure_content or "Use the adventure context provided in the rules section."}

---

### Session Planning Context

**Upcoming Planned Scenes:**
{scenes_str or "No specific scenes planned - improvise based on player actions"}

**Active Plot Threads:**
{threads_str or "None established yet"}

**Known NPCs:**
{npcs_str or "No NPCs encountered yet"}

**Session Goals:**
{goals_str}
"""

    return section
