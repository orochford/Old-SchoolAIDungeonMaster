"""Adventure state tracking for session-based adventure management."""

from typing import TypedDict, List, Optional
from datetime import datetime


class PlannedScene(TypedDict, total=False):
    """A planned scene for the adventure."""
    name: str                      # Scene name (e.g., "Entering the Dungeon")
    description: str               # What happens in this scene
    trigger: str                   # What causes this scene to occur
    npcs_monsters: List[str]       # NPCs or monsters involved
    possible_outcomes: List[str]   # How the scene might resolve
    plot_threads: List[str]        # Connected plot threads


class PlotThread(TypedDict, total=False):
    """An active plot thread in the adventure."""
    name: str                      # Thread name
    status: str                    # "active", "resolved", "escalated"
    notes: str                     # What has happened with this thread
    last_updated: str              # ISO timestamp


class NPCEncounter(TypedDict, total=False):
    """Record of an NPC encounter."""
    name: str                      # NPC name
    attitude: str                  # "friendly", "neutral", "hostile"
    notes: str                     # Key information exchanged
    first_met_scene: str           # Scene where first encountered


class KeyEvent(TypedDict, total=False):
    """A significant story event that occurred."""
    description: str               # What happened
    scene: str                     # Scene where it occurred
    timestamp: str                 # ISO timestamp
    consequences: List[str]        # Resulting effects


class AdventureState(TypedDict, total=False):
    """
    Complete adventure state tracking for a session.

    This tracks the player's progress through an adventure module,
    including planned scenes, plot threads, NPC encounters, and key events.
    """
    # Current adventure progress
    adventure_document_id: str     # UUID of the adventure PDF
    adventure_title: str           # Title of the adventure
    current_scene: str             # Name of current scene
    current_location: str          # Location within the adventure

    # Scene tracking
    completed_scenes: List[str]    # Names of completed scenes
    upcoming_scenes: List[PlannedScene]  # Planned future scenes

    # Plot management
    active_plot_threads: List[PlotThread]

    # NPC tracking
    npcs_encountered: dict         # {npc_name: NPCEncounter}

    # Event log
    key_events: List[KeyEvent]

    # Session planning
    session_goals: List[str]       # What DM plans to accomplish
    chaos_factor: int              # Mythic GME chaos factor (1-9)

    # Timestamps
    last_planned: str              # When adventure was last planned
    last_updated: str              # When state was last updated


def create_initial_adventure_state(
    adventure_document_id: str,
    adventure_title: str,
) -> AdventureState:
    """Create a fresh adventure state for a new adventure."""
    now = datetime.utcnow().isoformat()
    return AdventureState(
        adventure_document_id=adventure_document_id,
        adventure_title=adventure_title,
        current_scene="",
        current_location="",
        completed_scenes=[],
        upcoming_scenes=[],
        active_plot_threads=[],
        npcs_encountered={},
        key_events=[],
        session_goals=[],
        chaos_factor=5,
        last_planned="",
        last_updated=now,
    )


def advance_scene(
    state: AdventureState,
    completed_scene: str,
    outcome: str,
    next_scene: Optional[str] = None,
) -> AdventureState:
    """Mark a scene as complete and advance to the next."""
    from datetime import datetime

    # Add to completed scenes
    completed = list(state.get("completed_scenes", []))
    if completed_scene and completed_scene not in completed:
        completed.append(completed_scene)

    # Log the completion as a key event
    events = list(state.get("key_events", []))
    events.append(KeyEvent(
        description=f"Completed scene: {completed_scene} - {outcome}",
        scene=completed_scene,
        timestamp=datetime.utcnow().isoformat(),
        consequences=[],
    ))

    # Update current scene
    current = next_scene if next_scene else ""

    # Remove from upcoming if it was planned
    upcoming = [s for s in state.get("upcoming_scenes", []) if s.get("name") != next_scene]

    return {
        **state,
        "completed_scenes": completed,
        "current_scene": current,
        "key_events": events,
        "upcoming_scenes": upcoming,
        "last_updated": datetime.utcnow().isoformat(),
    }


def update_plot_thread(
    state: AdventureState,
    thread_name: str,
    status: str,
    notes: str,
) -> AdventureState:
    """Update or create a plot thread."""
    from datetime import datetime

    threads = list(state.get("active_plot_threads", []))

    # Find existing thread or create new
    found = False
    for i, thread in enumerate(threads):
        if thread.get("name") == thread_name:
            threads[i] = PlotThread(
                name=thread_name,
                status=status,
                notes=notes,
                last_updated=datetime.utcnow().isoformat(),
            )
            found = True
            break

    if not found:
        threads.append(PlotThread(
            name=thread_name,
            status=status,
            notes=notes,
            last_updated=datetime.utcnow().isoformat(),
        ))

    return {
        **state,
        "active_plot_threads": threads,
        "last_updated": datetime.utcnow().isoformat(),
    }


def record_npc_encounter(
    state: AdventureState,
    npc_name: str,
    attitude: str,
    notes: str,
) -> AdventureState:
    """Record meeting an NPC."""
    from datetime import datetime

    npcs = dict(state.get("npcs_encountered", {}))

    existing = npcs.get(npc_name, {})
    npcs[npc_name] = NPCEncounter(
        name=npc_name,
        attitude=attitude,
        notes=notes,
        first_met_scene=existing.get("first_met_scene") or state.get("current_scene", ""),
    )

    return {
        **state,
        "npcs_encountered": npcs,
        "last_updated": datetime.utcnow().isoformat(),
    }
