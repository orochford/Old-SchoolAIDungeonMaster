# GraphRAG for D&D Module Understanding

## Problem
The LLM hallucinates details even with verbatim module text in context:
- Changes "5 gold pieces" to "15 gold pieces"
- Invents atmosphere for "empty and barren" rooms
- Skips triggered events like magic mouths
- Gets exit directions wrong

## Solution: Knowledge Graph + Structured Retrieval

Instead of giving the LLM prose to interpret, we:
1. **Extract** module content into a knowledge graph with exact values
2. **Query** the graph for precise facts about the current location
3. **Inject** structured data that the LLM must use verbatim

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INDEXING PIPELINE                        │
├─────────────────────────────────────────────────────────────┤
│  PDF → Markdown → Entity Extraction → Knowledge Graph       │
│                                                             │
│  Entities: Location, Item, NPC, Creature, Event, Feature    │
│  Relations: CONNECTS_TO, CONTAINS, TRIGGERS, HAS_PROPERTY   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH                          │
├─────────────────────────────────────────────────────────────┤
│  [Room 1: Alcoves]                                          │
│    ├── CONNECTS_TO {dir: "north"} → [Intersection]          │
│    ├── HAS_FEATURE → [Secret Doors] {detectable: false}     │
│    ├── HAS_TRIGGER → [Magic Mouth] {                        │
│    │     condition: "reach third alcoves",                  │
│    │     dialogue: ["WHO DARES...", ...],                   │
│    │   }                                                    │
│    └── PROPERTY: description = "empty and barren"           │
│                                                             │
│  [Body #1]                                                  │
│    ├── LOCATED_AT → [Intersection]                          │
│    ├── CONTAINS → [Belt Pouch]                              │
│    │     └── CONTAINS → [Gold] {amount: 5, unit: "gp"}      │
│    └── PROPERTY: state = "slumped against wall"             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    QUERY SYSTEM                             │
├─────────────────────────────────────────────────────────────┤
│  Input: current_location = "1" (Alcoves)                    │
│                                                             │
│  Queries:                                                   │
│    - Get all properties of location "1"                     │
│    - Get all items/features CONTAINED in location "1"       │
│    - Get all CONNECTIONS from location "1"                  │
│    - Get all TRIGGERS for location "1"                      │
│                                                             │
│  Output: Structured facts (not prose)                       │
│    {                                                        │
│      "description": "empty and barren, no markings",        │
│      "exits": {"north": "intersection"},                    │
│      "triggers": [{                                         │
│        "type": "magic_mouth",                               │
│        "dialogue": ["WHO DARES...", "ONLY A GROUP...", ...] │
│      }],                                                    │
│      "contents": []  // empty room                          │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM CONTEXT                              │
├─────────────────────────────────────────────────────────────┤
│  ## CURRENT LOCATION FACTS (AUTHORITATIVE - USE EXACTLY)   │
│                                                             │
│  Location: Alcoves (1)                                      │
│  Description: "empty and barren, no markings"               │
│                                                             │
│  EXITS:                                                     │
│  - NORTH → Intersection                                     │
│                                                             │
│  CONTENTS: None (room is empty)                             │
│                                                             │
│  MANDATORY TRIGGER:                                         │
│  Type: magic_mouth                                          │
│  When: Player reaches third alcoves                         │
│  Execute EXACTLY:                                           │
│    1. East mouth: "WHO DARES ENTER THIS PLACE..."           │
│    2. West mouth: "ONLY A GROUP OF FOOLHARDY..."            │
│    3. Both in unison: "WOE TO ANY WHO PASS..."              │
│    4. [Laughter fades]                                      │
│                                                             │
│  Your response MUST use these exact facts.                  │
│  Do NOT embellish "empty and barren" with atmosphere.       │
└─────────────────────────────────────────────────────────────┘
```

## Graph Schema

### Node Types

```
Location {
  key: string (required)      # "1", "2", "31"
  name: string (required)     # "Alcoves", "Kitchen"
  description: string         # Verbatim module text
  dungeon_level: int
  is_empty: bool              # Explicit flag for empty rooms
}

Item {
  id: string (required)
  name: string (required)     # "Gold Pieces", "Broken Sword"
  quantity: int               # EXACT number
  unit: string                # "gp", "pieces", etc.
  properties: dict            # Additional attributes
}

Creature {
  id: string (required)
  name: string (required)     # "Orc", "Guard"
  count: int                  # EXACT number
  hd: string                  # "1", "2+1"
  hp: list[int]               # Individual HP values
  ac: int
  thac0: int
  attacks: string
  damage: string
  morale: int
  special: string
}

NPC {
  id: string (required)
  name: string (required)
  title: string
  description: string
  personality: string
  motivation: string
}

Trigger {
  id: string (required)
  type: string                # "magic_mouth", "trap", "event"
  condition: string           # When it fires
  effect: string              # What happens
  dialogue: list[string]      # Exact words (if applicable)
  repeatable: bool
}

Feature {
  id: string (required)
  name: string                # "Secret Door", "Stairs"
  description: string
  detectable: bool
  detection_method: string
}

Container {
  id: string (required)
  name: string                # "Belt Pouch", "Iron Chest"
  description: string
}

Body {
  id: string (required)
  description: string         # "Human fighter, slumped against wall"
  cause_of_death: string
}
```

### Relationship Types

```
CONNECTS_TO {
  direction: string           # "north", "east", "secret_east"
  description: string         # "wooden door", "narrow passage"
  requirements: string        # "key", "strength check"
  one_way: bool
}

CONTAINS
  # Location CONTAINS Item/Creature/NPC/Feature/Trigger
  # Container CONTAINS Item
  # Body CONTAINS Item

LOCATED_AT
  # Body/NPC/Creature LOCATED_AT Location

HAS_TRIGGER
  # Location HAS_TRIGGER Trigger

HAS_FEATURE
  # Location HAS_FEATURE Feature
```

## Implementation Plan

### Phase 1: Graph Infrastructure
- Add Neo4j or use NetworkX for in-memory graph
- Create graph models matching schema above
- Build graph persistence layer

### Phase 2: Entity Extraction
- Create LLM-based entity extractor using structured output
- Extract: Locations, Items, Creatures, NPCs, Triggers, Features
- Preserve EXACT values (numbers, dialogue)

### Phase 3: Relationship Extraction
- Extract connections between entities
- Build bidirectional navigation (Room 1 ↔ Room 2)
- Link items to containers, containers to locations

### Phase 4: Query System
- Implement graph queries for gameplay:
  - get_location_facts(location_key) → all facts about a location
  - get_exits(location_key) → connected locations with directions
  - get_triggers(location_key) → events that fire here
  - get_contents(location_key) → items, creatures, NPCs present

### Phase 5: DM Integration
- Replace prose context with structured facts
- Generate deterministic context from graph queries
- LLM only adds flavor, cannot change facts

## Key Principle

**The graph is the source of truth.**
- Numbers come from the graph (5 gp, not LLM interpretation)
- Exits come from the graph (north → Room 2, not LLM guess)
- Triggers come from the graph (exact dialogue, not paraphrase)
- The LLM's job is to present these facts engagingly, not to invent them.
