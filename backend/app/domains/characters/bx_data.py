"""B/X D&D (1981) character creation data and utilities."""

from app.domains.characters.schemas import SystemCreationOptions

# B/X Classes (Race-as-Class)
BX_CLASSES = [
    {
        "id": "fighter",
        "name": "Fighter",
        "description": "A warrior trained in combat, skilled with all weapons and armor.",
        "hit_die": "d8",
        "prime_requisite": "strength",
        "requirements": {},
        "saving_throws": {"death_ray_poison": 12, "wands": 13, "paralysis_stone": 14, "breath_attack": 15, "spells": 16},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 17, 5: 17, 6: 17, 7: 14, 8: 14, 9: 14, 10: 12, 11: 12, 12: 12, 13: 10, 14: 10},
        "xp_table": [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000, 360000, 480000, 600000, 720000, 840000],
        "max_level": 14,
        "abilities": ["Use any weapon", "Use any armor", "Use shields"],
        "restrictions": [],
    },
    {
        "id": "cleric",
        "name": "Cleric",
        "description": "A holy warrior who can cast divine spells and turn undead.",
        "hit_die": "d6",
        "prime_requisite": "wisdom",
        "requirements": {},
        "saving_throws": {"death_ray_poison": 11, "wands": 12, "paralysis_stone": 14, "breath_attack": 16, "spells": 15},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 19, 5: 17, 6: 17, 7: 17, 8: 17, 9: 14, 10: 14, 11: 14, 12: 14, 13: 12, 14: 12},
        "xp_table": [0, 1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000, 300000, 400000, 500000, 600000, 700000],
        "max_level": 14,
        "spells_per_level": {1: [], 2: [1], 3: [2], 4: [2, 1], 5: [2, 2], 6: [2, 2, 1, 1], 7: [2, 2, 2, 1, 1], 8: [3, 3, 2, 2, 1]},
        "abilities": ["Turn undead", "Cast divine spells (level 2+)", "Use blunt weapons only"],
        "restrictions": ["Cannot use edged or pointed weapons"],
    },
    {
        "id": "magic_user",
        "name": "Magic-User",
        "description": "A scholar of arcane arts who casts powerful spells.",
        "hit_die": "d4",
        "prime_requisite": "intelligence",
        "requirements": {},
        "saving_throws": {"death_ray_poison": 13, "wands": 14, "paralysis_stone": 13, "breath_attack": 16, "spells": 15},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 19, 5: 19, 6: 17, 7: 17, 8: 17, 9: 17, 10: 17, 11: 14, 12: 14, 13: 14, 14: 14},
        "xp_table": [0, 2500, 5000, 10000, 20000, 40000, 80000, 150000, 300000, 450000, 600000, 750000, 900000, 1050000],
        "max_level": 14,
        "spells_per_level": {1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1], 6: [2, 2, 2], 7: [3, 2, 2, 1], 8: [3, 3, 2, 2]},
        "abilities": ["Cast arcane spells", "Use spellbook"],
        "restrictions": ["Cannot wear armor", "Cannot use shields", "Dagger only weapon"],
    },
    {
        "id": "thief",
        "name": "Thief",
        "description": "A skilled rogue who excels at stealth and trickery.",
        "hit_die": "d4",
        "prime_requisite": "dexterity",
        "requirements": {},
        "saving_throws": {"death_ray_poison": 13, "wands": 14, "paralysis_stone": 13, "breath_attack": 16, "spells": 15},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 19, 5: 17, 6: 17, 7: 17, 8: 17, 9: 14, 10: 14, 11: 14, 12: 14, 13: 12, 14: 12},
        "xp_table": [0, 1200, 2400, 4800, 9600, 20000, 40000, 80000, 160000, 280000, 400000, 520000, 640000, 760000],
        "max_level": 14,
        "thief_skills": {
            1: {"open_locks": 15, "find_traps": 10, "remove_traps": 10, "climb_walls": 87, "move_silently": 20, "hide_shadows": 10, "pick_pockets": 20, "hear_noise": 2},
        },
        "abilities": ["Backstab (x2 damage)", "Thief skills", "Read languages (level 4+)"],
        "restrictions": ["Leather armor only", "Cannot use shields"],
    },
    {
        "id": "elf",
        "name": "Elf",
        "description": "A graceful warrior-mage of the elder race.",
        "hit_die": "d6",
        "prime_requisite": ["strength", "intelligence"],
        "requirements": {"intelligence": 9},
        "saving_throws": {"death_ray_poison": 12, "wands": 13, "paralysis_stone": 13, "breath_attack": 15, "spells": 15},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 17, 5: 17, 6: 17, 7: 14, 8: 14, 9: 14, 10: 12},
        "xp_table": [0, 4000, 8000, 16000, 32000, 64000, 120000, 250000, 400000, 600000],
        "max_level": 10,
        "spells_per_level": {1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1], 6: [2, 2, 2], 7: [3, 2, 2, 1], 8: [3, 3, 2, 2]},
        "abilities": ["Cast arcane spells", "Use any weapon", "Use any armor", "Infravision 60'", "Detect secret doors (1-2 on d6)", "Immune to ghoul paralysis"],
        "restrictions": [],
    },
    {
        "id": "dwarf",
        "name": "Dwarf",
        "description": "A stout warrior from the mountain halls, resistant to magic.",
        "hit_die": "d8",
        "prime_requisite": "strength",
        "requirements": {"constitution": 9},
        "saving_throws": {"death_ray_poison": 8, "wands": 9, "paralysis_stone": 10, "breath_attack": 13, "spells": 12},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 17, 5: 17, 6: 17, 7: 14, 8: 14, 9: 14, 10: 12, 11: 12, 12: 12},
        "xp_table": [0, 2200, 4400, 8800, 17000, 35000, 70000, 140000, 270000, 400000, 530000, 660000],
        "max_level": 12,
        "abilities": ["Use any weapon", "Use any armor", "Infravision 60'", "Detect stonework traps (1-2 on d6)", "+4 to saves vs magic"],
        "restrictions": ["Cannot use longbows or two-handed swords"],
    },
    {
        "id": "halfling",
        "name": "Halfling",
        "description": "A small but brave folk, excellent with ranged weapons.",
        "hit_die": "d6",
        "prime_requisite": ["strength", "dexterity"],
        "requirements": {"constitution": 9, "dexterity": 9},
        "saving_throws": {"death_ray_poison": 8, "wands": 9, "paralysis_stone": 10, "breath_attack": 13, "spells": 12},
        "thac0_by_level": {1: 19, 2: 19, 3: 19, 4: 17, 5: 17, 6: 17, 7: 14, 8: 14},
        "xp_table": [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000],
        "max_level": 8,
        "abilities": ["+1 to hit with ranged weapons", "-2 AC vs large creatures", "Hide in wilderness (90%)", "+4 to saves vs magic", "+1 initiative"],
        "restrictions": ["Cannot use longbows or two-handed swords", "Must use medium or smaller weapons"],
    },
]

# B/X Equipment
BX_EQUIPMENT = [
    # Weapons
    {"id": "dagger", "name": "Dagger", "category": "weapon", "cost_gp": 3, "weight": 10, "damage": "1d4", "properties": {"melee": True, "thrown": True, "range": "10/20/30"}},
    {"id": "short_sword", "name": "Short Sword", "category": "weapon", "cost_gp": 7, "weight": 30, "damage": "1d6", "properties": {"melee": True}},
    {"id": "sword", "name": "Sword", "category": "weapon", "cost_gp": 10, "weight": 60, "damage": "1d8", "properties": {"melee": True}},
    {"id": "two_handed_sword", "name": "Two-Handed Sword", "category": "weapon", "cost_gp": 15, "weight": 150, "damage": "1d10", "properties": {"melee": True, "two_handed": True}},
    {"id": "battle_axe", "name": "Battle Axe", "category": "weapon", "cost_gp": 7, "weight": 50, "damage": "1d8", "properties": {"melee": True}},
    {"id": "hand_axe", "name": "Hand Axe", "category": "weapon", "cost_gp": 4, "weight": 30, "damage": "1d6", "properties": {"melee": True, "thrown": True, "range": "10/20/30"}},
    {"id": "mace", "name": "Mace", "category": "weapon", "cost_gp": 5, "weight": 30, "damage": "1d6", "properties": {"melee": True, "blunt": True}},
    {"id": "war_hammer", "name": "War Hammer", "category": "weapon", "cost_gp": 5, "weight": 30, "damage": "1d6", "properties": {"melee": True, "blunt": True}},
    {"id": "club", "name": "Club", "category": "weapon", "cost_gp": 3, "weight": 50, "damage": "1d4", "properties": {"melee": True, "blunt": True}},
    {"id": "staff", "name": "Staff", "category": "weapon", "cost_gp": 2, "weight": 40, "damage": "1d4", "properties": {"melee": True, "blunt": True, "two_handed": True}},
    {"id": "spear", "name": "Spear", "category": "weapon", "cost_gp": 3, "weight": 30, "damage": "1d6", "properties": {"melee": True, "thrown": True, "range": "20/40/60"}},
    {"id": "pole_arm", "name": "Pole Arm", "category": "weapon", "cost_gp": 7, "weight": 150, "damage": "1d10", "properties": {"melee": True, "two_handed": True}},
    {"id": "short_bow", "name": "Short Bow", "category": "weapon", "cost_gp": 25, "weight": 30, "damage": "1d6", "properties": {"ranged": True, "two_handed": True, "range": "50/100/150"}},
    {"id": "long_bow", "name": "Long Bow", "category": "weapon", "cost_gp": 40, "weight": 30, "damage": "1d6", "properties": {"ranged": True, "two_handed": True, "range": "70/140/210"}},
    {"id": "crossbow", "name": "Crossbow", "category": "weapon", "cost_gp": 30, "weight": 50, "damage": "1d6", "properties": {"ranged": True, "two_handed": True, "range": "80/160/240", "slow": True}},
    {"id": "sling", "name": "Sling", "category": "weapon", "cost_gp": 2, "weight": 20, "damage": "1d4", "properties": {"ranged": True, "range": "40/80/160"}},
    {"id": "arrows_20", "name": "Arrows (20)", "category": "ammo", "cost_gp": 5, "weight": 20, "properties": {}},
    {"id": "crossbow_bolts_30", "name": "Crossbow Bolts (30)", "category": "ammo", "cost_gp": 10, "weight": 30, "properties": {}},
    {"id": "sling_stones_30", "name": "Sling Stones (30)", "category": "ammo", "cost_gp": 0, "weight": 30, "properties": {}},
    {"id": "silver_dagger", "name": "Silver Dagger", "category": "weapon", "cost_gp": 30, "weight": 10, "damage": "1d4", "properties": {"melee": True, "thrown": True, "silver": True}},

    # Armor
    {"id": "leather_armor", "name": "Leather Armor", "category": "armor", "cost_gp": 20, "weight": 200, "ac": 7, "properties": {}},
    {"id": "chain_mail", "name": "Chain Mail", "category": "armor", "cost_gp": 40, "weight": 400, "ac": 5, "properties": {}},
    {"id": "plate_mail", "name": "Plate Mail", "category": "armor", "cost_gp": 60, "weight": 500, "ac": 3, "properties": {}},
    {"id": "shield", "name": "Shield", "category": "armor", "cost_gp": 10, "weight": 100, "ac_bonus": 1, "properties": {}},

    # Adventuring Gear
    {"id": "backpack", "name": "Backpack", "category": "gear", "cost_gp": 5, "weight": 20, "properties": {"capacity": 400}},
    {"id": "rope_50ft", "name": "Rope (50')", "category": "gear", "cost_gp": 1, "weight": 50, "properties": {}},
    {"id": "torches_6", "name": "Torches (6)", "category": "gear", "cost_gp": 1, "weight": 60, "properties": {"light": "30'", "duration": "1 hour each"}},
    {"id": "lantern", "name": "Lantern", "category": "gear", "cost_gp": 10, "weight": 30, "properties": {"light": "30'"}},
    {"id": "oil_flask", "name": "Oil Flask", "category": "gear", "cost_gp": 2, "weight": 10, "properties": {"duration": "4 hours"}},
    {"id": "tinderbox", "name": "Tinderbox", "category": "gear", "cost_gp": 3, "weight": 5, "properties": {}},
    {"id": "iron_spikes_12", "name": "Iron Spikes (12)", "category": "gear", "cost_gp": 1, "weight": 60, "properties": {}},
    {"id": "hammer", "name": "Small Hammer", "category": "gear", "cost_gp": 2, "weight": 10, "properties": {}},
    {"id": "holy_symbol", "name": "Holy Symbol", "category": "gear", "cost_gp": 25, "weight": 5, "properties": {}},
    {"id": "holy_water", "name": "Holy Water (vial)", "category": "gear", "cost_gp": 25, "weight": 5, "properties": {"damage": "1d8 vs undead"}},
    {"id": "thieves_tools", "name": "Thieves' Tools", "category": "gear", "cost_gp": 25, "weight": 10, "properties": {}},
    {"id": "mirror", "name": "Mirror (hand-sized)", "category": "gear", "cost_gp": 5, "weight": 5, "properties": {}},
    {"id": "rations_iron_1week", "name": "Iron Rations (1 week)", "category": "gear", "cost_gp": 15, "weight": 70, "properties": {}},
    {"id": "rations_standard_1week", "name": "Standard Rations (1 week)", "category": "gear", "cost_gp": 5, "weight": 200, "properties": {}},
    {"id": "waterskin", "name": "Waterskin", "category": "gear", "cost_gp": 1, "weight": 50, "properties": {}},
    {"id": "wine_quart", "name": "Wine (quart)", "category": "gear", "cost_gp": 1, "weight": 30, "properties": {}},
    {"id": "garlic", "name": "Garlic", "category": "gear", "cost_gp": 5, "weight": 1, "properties": {}},
    {"id": "wolfsbane", "name": "Wolfsbane", "category": "gear", "cost_gp": 10, "weight": 1, "properties": {}},
    {"id": "wooden_pole", "name": "Wooden Pole (10')", "category": "gear", "cost_gp": 1, "weight": 80, "properties": {}},
]

# B/X Spells
BX_SPELLS = {
    "magic_user": {
        1: [
            {"id": "charm_person", "name": "Charm Person", "range": "120'", "duration": "Special", "description": "Target humanoid must save vs Spells or become charmed."},
            {"id": "detect_magic", "name": "Detect Magic", "range": "60'", "duration": "2 turns", "description": "Caster can see magical auras."},
            {"id": "floating_disc", "name": "Floating Disc", "range": "0", "duration": "6 turns", "description": "Creates a floating disc that can carry 500 lbs."},
            {"id": "hold_portal", "name": "Hold Portal", "range": "10'", "duration": "2d6 turns", "description": "Magically holds a door shut."},
            {"id": "light_mu", "name": "Light", "range": "120'", "duration": "6 turns + level", "description": "Creates light in 15' radius."},
            {"id": "magic_missile", "name": "Magic Missile", "range": "150'", "duration": "Instant", "description": "Fires 1 missile that auto-hits for 1d6+1 damage."},
            {"id": "protection_from_evil", "name": "Protection from Evil", "range": "0", "duration": "6 turns", "description": "+1 to saves, -1 to enemy attacks."},
            {"id": "read_languages", "name": "Read Languages", "range": "0", "duration": "2 turns", "description": "Caster can read any language."},
            {"id": "read_magic", "name": "Read Magic", "range": "0", "duration": "1 turn", "description": "Caster can read magical writing."},
            {"id": "shield", "name": "Shield", "range": "0", "duration": "2 turns", "description": "Grants AC 2 vs missiles, AC 4 vs melee."},
            {"id": "sleep", "name": "Sleep", "range": "240'", "duration": "4d4 turns", "description": "Puts 2d8 HD of creatures to sleep (no save)."},
            {"id": "ventriloquism", "name": "Ventriloquism", "range": "60'", "duration": "2 turns", "description": "Throw voice up to 60' away."},
        ],
        2: [
            {"id": "continual_light", "name": "Continual Light", "range": "120'", "duration": "Permanent", "description": "Creates permanent light."},
            {"id": "detect_evil", "name": "Detect Evil", "range": "60'", "duration": "2 turns", "description": "Detects evil intent within range."},
            {"id": "detect_invisible", "name": "Detect Invisible", "range": "10'/level", "duration": "6 turns", "description": "Caster can see invisible creatures."},
            {"id": "esp", "name": "ESP", "range": "60'", "duration": "12 turns", "description": "Read surface thoughts of one creature."},
            {"id": "invisibility", "name": "Invisibility", "range": "Touch", "duration": "Until dispelled", "description": "Target becomes invisible until attacking."},
            {"id": "knock", "name": "Knock", "range": "60'", "duration": "Instant", "description": "Opens locked or stuck doors."},
            {"id": "levitate", "name": "Levitate", "range": "0", "duration": "6 turns + level", "description": "Caster can move up or down at 20'/round."},
            {"id": "locate_object", "name": "Locate Object", "range": "60' + 10'/level", "duration": "2 turns", "description": "Senses direction to an object."},
            {"id": "mirror_image", "name": "Mirror Image", "range": "0", "duration": "6 turns", "description": "Creates 1d4 illusory duplicates."},
            {"id": "phantasmal_force", "name": "Phantasmal Force", "range": "240'", "duration": "Concentration", "description": "Creates illusion in 20' cube."},
            {"id": "web", "name": "Web", "range": "10'", "duration": "48 turns", "description": "Fills 10'x10'x10' with sticky webs."},
            {"id": "wizard_lock", "name": "Wizard Lock", "range": "10'", "duration": "Permanent", "description": "Magically locks a door."},
        ],
    },
    "cleric": {
        1: [
            {"id": "cure_light_wounds", "name": "Cure Light Wounds", "range": "Touch", "duration": "Instant", "description": "Heals 1d6+1 HP."},
            {"id": "detect_evil_cleric", "name": "Detect Evil", "range": "120'", "duration": "6 turns", "description": "Detects evil intent within range."},
            {"id": "detect_magic_cleric", "name": "Detect Magic", "range": "60'", "duration": "2 turns", "description": "Caster can see magical auras."},
            {"id": "light_cleric", "name": "Light", "range": "120'", "duration": "12 turns", "description": "Creates light in 15' radius."},
            {"id": "protection_from_evil_cleric", "name": "Protection from Evil", "range": "0", "duration": "12 turns", "description": "+1 to saves, -1 to enemy attacks."},
            {"id": "purify_food_water", "name": "Purify Food and Water", "range": "10'", "duration": "Instant", "description": "Makes food/water safe to consume."},
            {"id": "remove_fear", "name": "Remove Fear", "range": "Touch", "duration": "2 turns", "description": "Removes magical fear."},
            {"id": "resist_cold", "name": "Resist Cold", "range": "30'", "duration": "6 turns", "description": "Grants resistance to cold."},
        ],
        2: [
            {"id": "bless", "name": "Bless", "range": "60'", "duration": "6 turns", "description": "+1 to attacks, damage, morale, saves."},
            {"id": "find_traps", "name": "Find Traps", "range": "30'", "duration": "2 turns", "description": "Reveals traps in range."},
            {"id": "hold_person", "name": "Hold Person", "range": "180'", "duration": "9 turns", "description": "Paralyzes 1-4 humanoids."},
            {"id": "know_alignment", "name": "Know Alignment", "range": "10'", "duration": "1 round", "description": "Reveals alignment of one creature."},
            {"id": "resist_fire", "name": "Resist Fire", "range": "30'", "duration": "6 turns", "description": "Grants resistance to fire."},
            {"id": "silence", "name": "Silence 15' Radius", "range": "180'", "duration": "12 turns", "description": "Creates zone of silence."},
            {"id": "snake_charm", "name": "Snake Charm", "range": "60'", "duration": "Special", "description": "Charms snakes."},
            {"id": "speak_with_animals", "name": "Speak with Animals", "range": "0", "duration": "6 turns", "description": "Communicate with animals."},
        ],
    },
}

# Alignments
BX_ALIGNMENTS = ["Lawful", "Neutral", "Chaotic"]


def calculate_prime_requisite_bonus(attributes: dict, character_class: str) -> int:
    """Calculate XP bonus from prime requisite."""
    class_data = next((c for c in BX_CLASSES if c["id"] == character_class), None)
    if not class_data:
        return 0

    prime = class_data["prime_requisite"]

    if isinstance(prime, list):
        # Dual prime requisite (Elf, Halfling)
        scores = [attributes.get(p, 10) for p in prime]
        avg = sum(scores) / len(scores)
        if avg >= 13:
            return 5
        elif avg >= 16:
            return 10
    else:
        score = attributes.get(prime, 10)
        if score >= 16:
            return 10
        elif score >= 13:
            return 5
        elif score <= 5:
            return -20
        elif score <= 8:
            return -10

    return 0


def calculate_ability_modifier(score: int) -> int:
    """Calculate B/X ability modifier."""
    if score <= 3:
        return -3
    elif score <= 5:
        return -2
    elif score <= 8:
        return -1
    elif score <= 12:
        return 0
    elif score <= 15:
        return 1
    elif score <= 17:
        return 2
    else:
        return 3


def get_bx_creation_options() -> SystemCreationOptions:
    """Get B/X D&D character creation options."""
    return SystemCreationOptions(
        system_code="bx-dnd",
        classes=BX_CLASSES,
        equipment=BX_EQUIPMENT,
        spells=list(BX_SPELLS.get("magic_user", {}).get(1, [])) + list(BX_SPELLS.get("cleric", {}).get(1, [])),
        alignments=BX_ALIGNMENTS,
    )
