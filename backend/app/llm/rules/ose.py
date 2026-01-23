"""Old School Essentials (OSE) Rules Configuration."""

from .base import RPGRules

OSE_RULES = RPGRules(
    system_id="ose",
    system_name="Old School Essentials",
    system_description="A refined presentation of classic B/X D&D rules by Necrotic Gnome. Fully compatible with B/X adventures and supplements.",

    combat_system="thac0",  # OSE also supports ascending AC as optional
    initiative_type="group",

    saving_throws=[
        "Death/Poison",
        "Wands",
        "Paralysis/Petrify",
        "Breath Attacks",
        "Spells/Rods/Staves",
    ],

    classes=[
        "Cleric", "Dwarf", "Elf", "Fighter", "Halfling", "Magic-User", "Thief"
    ],

    combat_rules="""
- THAC0 system (descending AC): Roll d20 >= THAC0 - target AC to hit
- Optional: Ascending AC - Roll d20 + attack bonus >= target AC
- AC 9 [10] unarmored, AC 2 [17] plate + shield
- Group Initiative: Each side rolls d6, higher acts first
- Individual Initiative (optional): d6 + DEX modifier
- Attacks: One attack per round (fighters get more at higher levels in Advanced rules)
- Two-handed weapons: -1 to initiative, but deal more damage
- Dual wielding: Not standard, use optional rules if desired
""",

    saving_throw_rules="""
Five categories with clear triggers:
- **Death/Poison**: Poison, death rays, instant death effects
- **Wands**: Wand attacks (damage, rays, etc.)
- **Paralysis/Petrify**: Paralysis, petrification, polymorph
- **Breath Attacks**: Dragon breath, area breath weapons
- **Spells/Rods/Staves**: Spells without other categories, rods, staves

Roll d20 >= save value. Magic items may grant bonuses.
""",

    ability_check_rules="""
- Ability checks: Roll d20 <= ability score (referee's discretion)
- Thief skills: Percentile roll <= skill value
- Hear Noise: d6, base 1-in-6 (2-in-6 for demihumans)
- Open Stuck Doors: d6, base 1-2 in 6 (STR may modify)
- Find Secret Doors: d6, base 1-in-6 (elves 2-in-6)
- Find Room Traps: d6, base 1-in-6 (dwarves 2-in-6)
""",

    morale_rules="""
Check morale (2d6 <= morale score) when:
- First death on monster's side
- Half of monsters defeated

Morale scores:
- 2: Always flees
- 6: Cowardly (goblins)
- 8: Average (orcs)
- 10: Brave (ogres)
- 12: Never checks morale (undead, fanatics)

Failed check: Monsters flee or surrender.
""",

    reaction_rules="""
Initial reaction (2d6, modified by CHA):
- 2: Hostile, attacks
- 3-5: Unfriendly, may attack if provoked
- 6-8: Neutral, uncertain, will listen
- 9-11: Indifferent, uninterested but not hostile
- 12: Friendly, helpful

Re-roll allowed after negotiation/offers.
""",

    experience_rules="""
XP Sources:
- 1 XP per 1 GP of treasure recovered (primary source)
- Monster XP based on HD (divided among party)
- Prime Requisite modifiers: -20% to +10%

Leveling: XP thresholds vary by class.
""",

    movement_rules="""
Dungeon Exploration:
- Base 120' per turn (10 minutes)
- Combat movement: 40' per round (1/3 of exploration)
- Running: Double speed, no mapping, -2 to surprise others

Encumbrance (optional):
- Track weight in coins (cn)
- Every 400cn reduces movement by 30'

Wilderness: Base 24 miles/day, modified by terrain.
""",

    magic_rules="""
Spell Memorization:
- Requires 8 hours rest + 1 hour study
- Spells are "forgotten" after casting
- Spell slots by class and level

Casting:
- Most spells: 1 round casting time
- Caster cannot move while casting
- Damage interrupts casting (spell lost)

Magic-Users: Cannot cast in armor
Clerics: Can cast in any armor
Elves: Can cast in armor (class feature)
""",

    additional_rules="""
### Hazards & Exploration
- Light: Torches 30' radius, lanterns 30' radius
- Darkness: -4 to attacks, cannot read
- Falling: 1d6 damage per 10' fallen
- Drowning: CON rounds before unconscious, death follows
- Starvation: -1 HP per day without food after 1 week

### Retainers & Hirelings
- Max retainers = CHA modifier + 4
- Retainer morale affected by treatment and payment
- Hirelings are specialists (not combatants)
""",
)
