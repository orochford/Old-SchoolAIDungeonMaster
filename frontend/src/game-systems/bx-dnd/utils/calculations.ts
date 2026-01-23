/**
 * Calculate B/X D&D ability modifier.
 * 3: -3, 4-5: -2, 6-8: -1, 9-12: 0, 13-15: +1, 16-17: +2, 18: +3
 */
export function calculateBXModifier(score: number): number {
  if (score <= 3) return -3
  if (score <= 5) return -2
  if (score <= 8) return -1
  if (score <= 12) return 0
  if (score <= 15) return 1
  if (score <= 17) return 2
  return 3
}

/**
 * Calculate if an attack hits using THAC0.
 * Hit if: roll + modifiers >= THAC0 - targetAC
 */
export function calculateTHAC0Hit(
  thac0: number,
  targetAC: number,
  roll: number,
  modifiers: number = 0
): boolean {
  // Natural 20 always hits, natural 1 always misses
  if (roll === 20) return true
  if (roll === 1) return false

  const targetNumber = thac0 - targetAC
  return roll + modifiers >= targetNumber
}

/**
 * Calculate the target number needed to hit on a d20.
 */
export function getTargetToHit(thac0: number, targetAC: number): number {
  return Math.max(2, Math.min(20, thac0 - targetAC))
}

/**
 * Calculate prime requisite XP bonus.
 * 3-5: -20%, 6-8: -10%, 9-12: 0%, 13-15: +5%, 16+: +10%
 */
export function calculatePrimeRequisiteBonus(score: number): number {
  if (score <= 5) return -20
  if (score <= 8) return -10
  if (score <= 12) return 0
  if (score <= 15) return 5
  return 10
}

/**
 * Calculate XP with prime requisite bonus.
 */
export function applyXPBonus(baseXP: number, bonusPercent: number): number {
  return Math.floor(baseXP * (1 + bonusPercent / 100))
}

/**
 * Roll dice notation (e.g., "3d6", "1d8+2").
 */
export function rollDice(notation: string): { rolls: number[]; modifier: number; total: number } {
  const match = notation.match(/(\d+)d(\d+)([+-]\d+)?/)
  if (!match) {
    return { rolls: [], modifier: 0, total: 0 }
  }

  const numDice = parseInt(match[1], 10)
  const dieSize = parseInt(match[2], 10)
  const modifier = match[3] ? parseInt(match[3], 10) : 0

  const rolls = Array.from({ length: numDice }, () => Math.floor(Math.random() * dieSize) + 1)
  const total = rolls.reduce((a, b) => a + b, 0) + modifier

  return { rolls, modifier, total }
}

/**
 * Roll 4d6 drop lowest for ability score generation.
 */
export function roll4d6DropLowest(): number {
  const rolls = Array.from({ length: 4 }, () => Math.floor(Math.random() * 6) + 1)
  rolls.sort((a, b) => b - a)
  return rolls[0] + rolls[1] + rolls[2]
}

/**
 * Roll 3d6 in order for classic ability score generation.
 */
export function roll3d6(): number {
  return Array.from({ length: 3 }, () => Math.floor(Math.random() * 6) + 1).reduce((a, b) => a + b, 0)
}

/**
 * Calculate reaction roll result (2d6).
 */
export function interpretReactionRoll(roll: number): {
  reaction: string
  description: string
} {
  if (roll <= 2) return { reaction: 'hostile', description: 'Attacks immediately' }
  if (roll <= 5) return { reaction: 'unfriendly', description: 'Hostile, may attack' }
  if (roll <= 8) return { reaction: 'neutral', description: 'Uncertain, considers offers' }
  if (roll <= 11) return { reaction: 'friendly', description: 'No attack, may be helpful' }
  return { reaction: 'enthusiastic', description: 'Eager to help, potential ally' }
}

/**
 * Check morale (2d6 <= morale score to pass).
 */
export function checkMorale(roll: number, moraleScore: number): boolean {
  return roll <= moraleScore
}

/**
 * Calculate XP for defeating monsters.
 */
export function calculateMonsterXP(hitDice: number, specialAbilities: number = 0): number {
  const baseXP: Record<number, number> = {
    1: 10, 2: 20, 3: 35, 4: 75, 5: 175, 6: 275, 7: 450, 8: 650, 9: 900,
  }

  const bonusXP: Record<number, number> = {
    1: 3, 2: 5, 3: 15, 4: 25, 5: 50, 6: 50, 7: 75, 8: 125, 9: 300,
  }

  const hd = Math.min(hitDice, 9)
  return (baseXP[hd] || 900) + (bonusXP[hd] || 300) * specialAbilities
}

/**
 * Equipment item with tracking data
 */
export interface EquippedItem {
  id: string
  name: string
  category: 'weapon' | 'armor' | 'gear' | 'ammo'
  equipped: boolean
  damage?: string
  ac?: number
  acBonus?: number
  weight: number
  quantity?: number
}

/**
 * Calculate AC from equipped armor and shield.
 * Base AC is 9 (unarmored).
 */
export function calculateArmorClass(equipment: EquippedItem[], dexModifier: number = 0): number {
  let baseAC = 9 // Unarmored
  let shieldBonus = 0

  for (const item of equipment) {
    if (!item.equipped) continue

    if (item.category === 'armor') {
      if (item.ac !== undefined && item.ac < baseAC) {
        // Lower AC is better in B/X
        baseAC = item.ac
      }
      if (item.acBonus !== undefined) {
        shieldBonus += item.acBonus
      }
    }
  }

  // Apply DEX modifier (lower is better, so subtract)
  // Apply shield bonus (also subtract since lower is better)
  return baseAC - dexModifier - shieldBonus
}

/**
 * Get the best equipped weapon
 */
export function getEquippedWeapon(equipment: EquippedItem[]): EquippedItem | undefined {
  return equipment.find((item) => item.category === 'weapon' && item.equipped)
}

/**
 * Calculate total encumbrance from all carried items
 */
export function calculateTotalEncumbrance(equipment: EquippedItem[]): number {
  return equipment.reduce((total, item) => {
    const qty = item.quantity || 1
    return total + (item.weight * qty)
  }, 0)
}

/**
 * Get movement rates based on encumbrance
 */
export function getMovementFromEncumbrance(encumbrance: number): {
  dungeon: number
  wilderness: number
  combat: number
  description: string
} {
  if (encumbrance <= 400) {
    return { dungeon: 120, wilderness: 24, combat: 40, description: 'Unencumbered' }
  }
  if (encumbrance <= 600) {
    return { dungeon: 90, wilderness: 18, combat: 30, description: 'Lightly Encumbered' }
  }
  if (encumbrance <= 800) {
    return { dungeon: 60, wilderness: 12, combat: 20, description: 'Heavily Encumbered' }
  }
  if (encumbrance <= 1600) {
    return { dungeon: 30, wilderness: 6, combat: 10, description: 'Severely Encumbered' }
  }
  return { dungeon: 0, wilderness: 0, combat: 0, description: 'Over-encumbered!' }
}
