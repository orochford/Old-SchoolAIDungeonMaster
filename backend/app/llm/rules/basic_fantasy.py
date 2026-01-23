"""Basic Fantasy RPG Rules Configuration."""

from .base import RPGRules

BASIC_FANTASY_RULES = RPGRules(
    system_id="basic-fantasy",
    system_name="Basic Fantasy RPG",
    system_description="A free, open-source retro-clone combining old-school feel with modern conveniences like ascending AC and separate race/class.",

    combat_system="ascending_ac",
    initiative_type="individual",

    saving_throws=[
        "Death Ray/Poison",
        "Magic Wands",
        "Paralysis/Petrify",
        "Dragon Breath",
        "Spells",
    ],

    classes=[
        "Cleric", "Fighter", "Magic-User", "Thief",
        # Races are separate: Human, Dwarf, Elf, Halfling
    ],

    combat_rules="""
- **Ascending AC system**: Roll d20 + Attack Bonus >= target AC to hit
- AC 11 is unarmored, AC 19 is plate + shield
- Initiative: d6 + DEX bonus, individual (act in order)
- One attack per round (fighters may get multiple at high levels)
- Critical hit on natural 20: Double damage (optional)
- Fumble on natural 1: Referee determines effect (optional)
- Missile ranges: Short (no penalty), Medium (-2), Long (-5)
""",

    saving_throw_rules="""
Five categories (roll d20 >= save target):
- **Death Ray/Poison**: Instant death effects, poison
- **Magic Wands**: Wand/staff attacks
- **Paralysis/Petrify**: Paralysis, petrification, polymorph
- **Dragon Breath**: Breath weapons, area effects
- **Spells**: Spells not covered elsewhere

Saving throws improve with level. Class affects base values.
""",

    ability_check_rules="""
- Roll d20 <= ability score for ability checks
- Thief abilities use percentile dice
- Open Doors: Roll d6, 1-2 success (STR 13+ adds +1)
- Listening: Roll d6, 1 success (demihumans 1-2)
- Searching: Roll d6, 1 success per 10' searched
- Elves detect secret doors on 1-2 when passing
""",

    morale_rules="""
Morale checks (2d6 <= morale) when:
- First casualty in combat
- Half the group eliminated

Typical morale scores:
- 5: Cowardly creatures
- 7: Average creatures
- 9: Brave or trained
- 11: Elite or fanatical
- 12: Never fails (undead, constructs)

Failed morale: Creatures flee, surrender, or parley.
""",

    reaction_rules="""
Reaction roll (2d6, +CHA bonus):
- 2: Immediate attack
- 3-5: Hostile, aggressive
- 6-8: Uncertain, wait and see
- 9-11: No attack, may negotiate
- 12: Friendly, may offer aid

Use when NPC disposition is unclear.
""",

    experience_rules="""
XP Sources:
- Treasure: 1 XP per 1 GP (primary)
- Monsters: XP by HD (divided among party)
- Bonus: +5% or +10% for high prime requisite

Level advancement:
- Each class has XP thresholds
- Most level around 2,000 XP for level 2
""",

    movement_rules="""
Combat Movement:
- Base 40' per round (unencumbered)
- Running: 80' (double) but -2 AC

Exploration Movement:
- Base 120' per turn (10 minutes)
- Includes careful searching, mapping

Encumbrance:
- Light: Full movement
- Heavy: 2/3 movement
- Severe: 1/3 movement

Wilderness: 24 miles/day base, terrain modifies.
""",

    magic_rules="""
Spell Memorization:
- 8 hours rest required
- Memorize spells from spellbook (Magic-Users)
- Clerics pray for spells (no spellbook)
- Slots determined by class and level

Casting:
- 1 round to cast most spells
- No movement while casting
- Damage interrupts (spell lost)
- Clerics can wear armor; Magic-Users cannot
""",

    additional_rules="""
### Race and Class Separation
Basic Fantasy uses separate race and class:
- Choose race (Human, Dwarf, Elf, Halfling)
- Choose class (Cleric, Fighter, Magic-User, Thief)
- Some restrictions: Halflings can't be Magic-Users
- Dwarves and Halflings limited to level 6-8

### Special Abilities
- Darkvision: Dwarves and Elves see 60' in darkness
- Detect Construction: Dwarves 1-2 on d6
- Surprise Bonus: Halflings surprise on 1-3 outdoors

### Turn Undead
Clerics turn undead with 2d6 vs Turn Undead table.
Higher-level clerics may destroy undead outright.
""",
)
