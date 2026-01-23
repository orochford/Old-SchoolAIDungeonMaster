export interface BXClass {
  id: string
  name: string
  description: string
  hitDie: string
  primeRequisite: string | string[]
  requirements: Record<string, number>
  savingThrows: {
    deathRayPoison: number
    wands: number
    paralysisStone: number
    breathAttack: number
    spells: number
  }
  thac0ByLevel: Record<number, number>
  xpTable: number[]
  maxLevel: number
  abilities: string[]
  restrictions: string[]
  spellsPerLevel?: Record<number, number[]>
}

export const BX_CLASSES: BXClass[] = [
  {
    id: 'fighter',
    name: 'Fighter',
    description: 'A warrior trained in combat, skilled with all weapons and armor.',
    hitDie: 'd8',
    primeRequisite: 'strength',
    requirements: {},
    savingThrows: { deathRayPoison: 12, wands: 13, paralysisStone: 14, breathAttack: 15, spells: 16 },
    thac0ByLevel: { 1: 19, 4: 17, 7: 14, 10: 12, 13: 10 },
    xpTable: [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000, 240000],
    maxLevel: 14,
    abilities: ['Use any weapon', 'Use any armor', 'Use shields'],
    restrictions: [],
  },
  {
    id: 'cleric',
    name: 'Cleric',
    description: 'A holy warrior who can cast divine spells and turn undead.',
    hitDie: 'd6',
    primeRequisite: 'wisdom',
    requirements: {},
    savingThrows: { deathRayPoison: 11, wands: 12, paralysisStone: 14, breathAttack: 16, spells: 15 },
    thac0ByLevel: { 1: 19, 5: 17, 9: 14, 13: 12 },
    xpTable: [0, 1500, 3000, 6000, 12000, 25000, 50000, 100000, 200000],
    maxLevel: 14,
    spellsPerLevel: { 2: [1], 3: [2], 4: [2, 1], 5: [2, 2], 6: [2, 2, 1, 1] },
    abilities: ['Turn undead', 'Cast divine spells (level 2+)', 'Use blunt weapons only'],
    restrictions: ['Cannot use edged or pointed weapons'],
  },
  {
    id: 'magic_user',
    name: 'Magic-User',
    description: 'A scholar of arcane arts who casts powerful spells.',
    hitDie: 'd4',
    primeRequisite: 'intelligence',
    requirements: {},
    savingThrows: { deathRayPoison: 13, wands: 14, paralysisStone: 13, breathAttack: 16, spells: 15 },
    thac0ByLevel: { 1: 19, 6: 17, 11: 14 },
    xpTable: [0, 2500, 5000, 10000, 20000, 40000, 80000, 150000, 300000],
    maxLevel: 14,
    spellsPerLevel: { 1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1] },
    abilities: ['Cast arcane spells', 'Use spellbook'],
    restrictions: ['Cannot wear armor', 'Cannot use shields', 'Dagger only weapon'],
  },
  {
    id: 'thief',
    name: 'Thief',
    description: 'A skilled rogue who excels at stealth and trickery.',
    hitDie: 'd4',
    primeRequisite: 'dexterity',
    requirements: {},
    savingThrows: { deathRayPoison: 13, wands: 14, paralysisStone: 13, breathAttack: 16, spells: 15 },
    thac0ByLevel: { 1: 19, 5: 17, 9: 14, 13: 12 },
    xpTable: [0, 1200, 2400, 4800, 9600, 20000, 40000, 80000, 160000],
    maxLevel: 14,
    abilities: ['Backstab (x2 damage)', 'Thief skills', 'Read languages (level 4+)'],
    restrictions: ['Leather armor only', 'Cannot use shields'],
  },
  {
    id: 'elf',
    name: 'Elf',
    description: 'A graceful warrior-mage of the elder race.',
    hitDie: 'd6',
    primeRequisite: ['strength', 'intelligence'],
    requirements: { intelligence: 9 },
    savingThrows: { deathRayPoison: 12, wands: 13, paralysisStone: 13, breathAttack: 15, spells: 15 },
    thac0ByLevel: { 1: 19, 4: 17, 7: 14, 10: 12 },
    xpTable: [0, 4000, 8000, 16000, 32000, 64000, 120000, 250000, 400000],
    maxLevel: 10,
    spellsPerLevel: { 1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [2, 2, 1] },
    abilities: ['Cast arcane spells', 'Use any weapon', 'Use any armor', 'Infravision 60\'', 'Detect secret doors (1-2 on d6)', 'Immune to ghoul paralysis'],
    restrictions: [],
  },
  {
    id: 'dwarf',
    name: 'Dwarf',
    description: 'A stout warrior from the mountain halls, resistant to magic.',
    hitDie: 'd8',
    primeRequisite: 'strength',
    requirements: { constitution: 9 },
    savingThrows: { deathRayPoison: 8, wands: 9, paralysisStone: 10, breathAttack: 13, spells: 12 },
    thac0ByLevel: { 1: 19, 4: 17, 7: 14, 10: 12 },
    xpTable: [0, 2200, 4400, 8800, 17000, 35000, 70000, 140000, 270000],
    maxLevel: 12,
    abilities: ['Use any weapon', 'Use any armor', 'Infravision 60\'', 'Detect stonework traps (1-2 on d6)', '+4 to saves vs magic'],
    restrictions: ['Cannot use longbows or two-handed swords'],
  },
  {
    id: 'halfling',
    name: 'Halfling',
    description: 'A small but brave folk, excellent with ranged weapons.',
    hitDie: 'd6',
    primeRequisite: ['strength', 'dexterity'],
    requirements: { constitution: 9, dexterity: 9 },
    savingThrows: { deathRayPoison: 8, wands: 9, paralysisStone: 10, breathAttack: 13, spells: 12 },
    thac0ByLevel: { 1: 19, 4: 17, 7: 14 },
    xpTable: [0, 2000, 4000, 8000, 16000, 32000, 64000, 120000],
    maxLevel: 8,
    abilities: ['+1 to hit with ranged weapons', '-2 AC vs large creatures', 'Hide in wilderness (90%)', '+4 to saves vs magic', '+1 initiative'],
    restrictions: ['Cannot use longbows or two-handed swords', 'Must use medium or smaller weapons'],
  },
]

export function getClassById(id: string): BXClass | undefined {
  return BX_CLASSES.find((c) => c.id === id)
}

export function getTHAC0ForLevel(classId: string, level: number): number {
  const cls = getClassById(classId)
  if (!cls) return 19

  // Find the highest level threshold that's <= current level
  const thresholds = Object.keys(cls.thac0ByLevel)
    .map(Number)
    .filter((l) => l <= level)
    .sort((a, b) => b - a)

  return thresholds.length > 0 ? cls.thac0ByLevel[thresholds[0]] : 19
}

export function getSavingThrowsForLevel(classId: string, _level: number): BXClass['savingThrows'] {
  const cls = getClassById(classId)
  if (!cls) {
    return { deathRayPoison: 14, wands: 15, paralysisStone: 16, breathAttack: 17, spells: 17 }
  }

  // Base saving throws improve at certain level thresholds
  // For simplicity, using base values (level 1-3)
  // Full implementation would have level-based improvements
  return cls.savingThrows
}
