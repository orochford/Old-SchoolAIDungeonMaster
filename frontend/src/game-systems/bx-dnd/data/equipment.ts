export interface BXEquipment {
  id: string
  name: string
  category: 'weapon' | 'armor' | 'gear' | 'ammo'
  costGp: number
  weight: number // in coins (10 coins = 1 lb)
  damage?: string
  ac?: number
  acBonus?: number
  properties: Record<string, unknown>
}

export const BX_EQUIPMENT: BXEquipment[] = [
  // Weapons
  { id: 'dagger', name: 'Dagger', category: 'weapon', costGp: 3, weight: 10, damage: '1d4', properties: { melee: true, thrown: true, range: '10/20/30' } },
  { id: 'short_sword', name: 'Short Sword', category: 'weapon', costGp: 7, weight: 30, damage: '1d6', properties: { melee: true } },
  { id: 'sword', name: 'Sword', category: 'weapon', costGp: 10, weight: 60, damage: '1d8', properties: { melee: true } },
  { id: 'two_handed_sword', name: 'Two-Handed Sword', category: 'weapon', costGp: 15, weight: 150, damage: '1d10', properties: { melee: true, twoHanded: true } },
  { id: 'battle_axe', name: 'Battle Axe', category: 'weapon', costGp: 7, weight: 50, damage: '1d8', properties: { melee: true } },
  { id: 'hand_axe', name: 'Hand Axe', category: 'weapon', costGp: 4, weight: 30, damage: '1d6', properties: { melee: true, thrown: true, range: '10/20/30' } },
  { id: 'mace', name: 'Mace', category: 'weapon', costGp: 5, weight: 30, damage: '1d6', properties: { melee: true, blunt: true } },
  { id: 'war_hammer', name: 'War Hammer', category: 'weapon', costGp: 5, weight: 30, damage: '1d6', properties: { melee: true, blunt: true } },
  { id: 'club', name: 'Club', category: 'weapon', costGp: 3, weight: 50, damage: '1d4', properties: { melee: true, blunt: true } },
  { id: 'staff', name: 'Staff', category: 'weapon', costGp: 2, weight: 40, damage: '1d4', properties: { melee: true, blunt: true, twoHanded: true } },
  { id: 'spear', name: 'Spear', category: 'weapon', costGp: 3, weight: 30, damage: '1d6', properties: { melee: true, thrown: true, range: '20/40/60' } },
  { id: 'pole_arm', name: 'Pole Arm', category: 'weapon', costGp: 7, weight: 150, damage: '1d10', properties: { melee: true, twoHanded: true } },
  { id: 'short_bow', name: 'Short Bow', category: 'weapon', costGp: 25, weight: 30, damage: '1d6', properties: { ranged: true, twoHanded: true, range: '50/100/150' } },
  { id: 'long_bow', name: 'Long Bow', category: 'weapon', costGp: 40, weight: 30, damage: '1d6', properties: { ranged: true, twoHanded: true, range: '70/140/210' } },
  { id: 'crossbow', name: 'Crossbow', category: 'weapon', costGp: 30, weight: 50, damage: '1d6', properties: { ranged: true, twoHanded: true, range: '80/160/240', slow: true } },
  { id: 'sling', name: 'Sling', category: 'weapon', costGp: 2, weight: 20, damage: '1d4', properties: { ranged: true, range: '40/80/160' } },
  { id: 'silver_dagger', name: 'Silver Dagger', category: 'weapon', costGp: 30, weight: 10, damage: '1d4', properties: { melee: true, thrown: true, silver: true } },

  // Ammo
  { id: 'arrows_20', name: 'Arrows (20)', category: 'ammo', costGp: 5, weight: 20, properties: {} },
  { id: 'crossbow_bolts_30', name: 'Crossbow Bolts (30)', category: 'ammo', costGp: 10, weight: 30, properties: {} },
  { id: 'sling_stones_30', name: 'Sling Stones (30)', category: 'ammo', costGp: 0, weight: 30, properties: {} },

  // Armor
  { id: 'leather_armor', name: 'Leather Armor', category: 'armor', costGp: 20, weight: 200, ac: 7, properties: {} },
  { id: 'chain_mail', name: 'Chain Mail', category: 'armor', costGp: 40, weight: 400, ac: 5, properties: {} },
  { id: 'plate_mail', name: 'Plate Mail', category: 'armor', costGp: 60, weight: 500, ac: 3, properties: {} },
  { id: 'shield', name: 'Shield', category: 'armor', costGp: 10, weight: 100, acBonus: 1, properties: {} },

  // Adventuring Gear
  { id: 'backpack', name: 'Backpack', category: 'gear', costGp: 5, weight: 20, properties: { capacity: 400 } },
  { id: 'rope_50ft', name: 'Rope (50\')', category: 'gear', costGp: 1, weight: 50, properties: {} },
  { id: 'torches_6', name: 'Torches (6)', category: 'gear', costGp: 1, weight: 60, properties: { light: '30\'', duration: '1 hour each' } },
  { id: 'lantern', name: 'Lantern', category: 'gear', costGp: 10, weight: 30, properties: { light: '30\'' } },
  { id: 'oil_flask', name: 'Oil Flask', category: 'gear', costGp: 2, weight: 10, properties: { duration: '4 hours' } },
  { id: 'tinderbox', name: 'Tinderbox', category: 'gear', costGp: 3, weight: 5, properties: {} },
  { id: 'iron_spikes_12', name: 'Iron Spikes (12)', category: 'gear', costGp: 1, weight: 60, properties: {} },
  { id: 'hammer', name: 'Small Hammer', category: 'gear', costGp: 2, weight: 10, properties: {} },
  { id: 'holy_symbol', name: 'Holy Symbol', category: 'gear', costGp: 25, weight: 5, properties: {} },
  { id: 'holy_water', name: 'Holy Water (vial)', category: 'gear', costGp: 25, weight: 5, properties: { damage: '1d8 vs undead' } },
  { id: 'thieves_tools', name: 'Thieves\' Tools', category: 'gear', costGp: 25, weight: 10, properties: {} },
  { id: 'mirror', name: 'Mirror (hand-sized)', category: 'gear', costGp: 5, weight: 5, properties: {} },
  { id: 'rations_iron_1week', name: 'Iron Rations (1 week)', category: 'gear', costGp: 15, weight: 70, properties: {} },
  { id: 'rations_standard_1week', name: 'Standard Rations (1 week)', category: 'gear', costGp: 5, weight: 200, properties: {} },
  { id: 'waterskin', name: 'Waterskin', category: 'gear', costGp: 1, weight: 50, properties: {} },
  { id: 'wooden_pole', name: 'Wooden Pole (10\')', category: 'gear', costGp: 1, weight: 80, properties: {} },
  { id: 'garlic', name: 'Garlic', category: 'gear', costGp: 5, weight: 1, properties: {} },
  { id: 'wolfsbane', name: 'Wolfsbane', category: 'gear', costGp: 10, weight: 1, properties: {} },
]

export function getEquipmentById(id: string): BXEquipment | undefined {
  return BX_EQUIPMENT.find((e) => e.id === id)
}

/**
 * Get display name for an item. Looks up from equipment list first,
 * then falls back to formatting the ID nicely.
 * e.g., "rope_50ft" -> "Rope (50')" or "unknown_item" -> "Unknown Item"
 */
export function getItemDisplayName(itemNameOrId: string): string {
  // First try to find in equipment list
  const equipment = getEquipmentById(itemNameOrId)
  if (equipment) {
    return equipment.name
  }

  // Check if this is already a display name (contains spaces or parentheses)
  if (itemNameOrId.includes(' ') || itemNameOrId.includes('(')) {
    return itemNameOrId
  }

  // Format the ID: replace underscores, handle common patterns
  let name = itemNameOrId
    .replace(/_(\d+)(ft|lb|gp)?$/i, (_, num, unit) => {
      // Handle patterns like "rope_50ft" -> "Rope (50')"
      if (unit?.toLowerCase() === 'ft') return ` (${num}')`
      if (unit?.toLowerCase() === 'lb') return ` (${num} lb)`
      if (unit?.toLowerCase() === 'gp') return ` (${num} gp)`
      return ` (${num})`
    })
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase()) // Title case

  return name
}

export function getEquipmentByCategory(category: BXEquipment['category']): BXEquipment[] {
  return BX_EQUIPMENT.filter((e) => e.category === category)
}

export function calculateEncumbrance(equipmentIds: string[]): number {
  return equipmentIds.reduce((total, id) => {
    const item = getEquipmentById(id)
    return total + (item?.weight || 0)
  }, 0)
}

export function getMovementRate(encumbrance: number): { dungeon: number; combat: number } {
  if (encumbrance <= 400) return { dungeon: 120, combat: 40 }
  if (encumbrance <= 600) return { dungeon: 90, combat: 30 }
  if (encumbrance <= 800) return { dungeon: 60, combat: 20 }
  if (encumbrance <= 1600) return { dungeon: 30, combat: 10 }
  return { dungeon: 0, combat: 0 } // Over-encumbered
}
