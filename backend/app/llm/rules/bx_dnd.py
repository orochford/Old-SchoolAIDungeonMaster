"""B/X D&D (1981) Rules Configuration."""

from .base import RPGRules

BX_DND_RULES = RPGRules(
    system_id="bx-dnd",
    system_name="B/X D&D (1981)",
    system_description="The classic Basic/Expert Dungeons & Dragons rules by Tom Moldvay and David Cook.",

    combat_system="thac0",
    initiative_type="group",

    saving_throws=[
        "Death Ray/Poison",
        "Wands",
        "Paralysis/Turn to Stone",
        "Breath Attack",
        "Spells/Rods/Staves",
    ],

    classes=[
        "Cleric", "Dwarf", "Elf", "Fighter", "Halfling", "Magic-User", "Thief"
    ],

    combat_rules="""
- Use THAC0 (To Hit Armor Class 0) for attack rolls
- Roll d20 >= THAC0 - target AC to hit (descending AC system)
- AC 9 is unarmored, AC 2 is plate + shield, AC 0 and below is magical
- Initiative: d6 per side, higher goes first (re-roll ties)
- Damage by weapon type (e.g., sword 1d8, dagger 1d4)
- Two-handed weapons always lose initiative
- Missile combat: -1 to hit per range increment beyond first
""",

    saving_throw_rules="""
Five categories: Death Ray/Poison, Wands, Paralysis/Stone, Breath Attack, Spells
- Roll d20 >= save target to succeed
- Saving throw values vary by class and level
- Some effects allow half damage on successful save
""",

    ability_check_rules="""
- Roll d20 <= ability score to succeed (when applicable)
- Thief skills use percentile dice
- Open Doors: d6, success on 1-2 (modified by STR)
- Listen at Door: d6, success on 1 (2 for elves/halflings)
- Find Secret Door: d6, success on 1 (2 for elves when searching)
""",

    morale_rules="""
Check morale (2d6 vs morale score) when:
- First casualty on either side
- Half the group eliminated
- Roll 2d6 <= morale score to pass
- Failed morale: monsters flee or surrender
- Morale scores typically range from 6 (cowardly) to 12 (fanatic)
""",

    reaction_rules="""
2d6 + CHA modifier:
- 2: Hostile, attacks immediately
- 3-5: Unfriendly, may attack
- 6-8: Neutral, uncertain
- 9-11: No attack, may negotiate
- 12: Enthusiastic friendship, potential ally
""",

    experience_rules="""
- 1 XP per 1 GP of treasure recovered and returned to civilization
- XP for defeating monsters (varies by HD)
- Prime Requisite bonus/penalty applies (±5%, ±10%)
- XP divided equally among surviving party members
""",

    movement_rules="""
- Dungeon: 120'/turn exploring (40'/round in combat)
- Wilderness: 24 miles/day base (varies by terrain)
- Encumbrance reduces movement in 400cn increments
- Running doubles movement but prohibits mapping
""",

    magic_rules="""
- Spells must be memorized in advance after rest
- Spell slots determined by class and level
- Casting time is usually 1 round (interruption loses spell)
- Magic-Users cannot wear armor while casting
- Clerics can wear armor freely
- Scrolls can be used by appropriate classes
""",
)
