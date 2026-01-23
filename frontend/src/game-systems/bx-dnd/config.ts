import type { GameSystemConfig } from '../types/base.types'
import { BXCharacterSheet } from './components/sheet/BXCharacterSheet'
import { BXCombatTracker } from './components/combat/BXCombatTracker'
import { calculateBXModifier, calculateTHAC0Hit } from './utils/calculations'
import { BX_CLASSES } from './data/classes'
import { BX_EQUIPMENT } from './data/equipment'

export const bxDndConfig: GameSystemConfig = {
  id: 'bx-dnd',
  name: 'Basic/Expert D&D (1981)',
  version: '1981',
  description: 'The classic Moldvay/Cook Basic and Expert D&D rules',

  creationSteps: [
    {
      id: 'abilities',
      title: 'Ability Scores',
      description: 'Roll 3d6 for each ability score in order',
      component: () => null, // Placeholder - implemented in CharacterCreatePage
      validate: (data) => {
        const scores = data.abilityScores as Record<string, number>
        return Object.values(scores).every((s) => s >= 3 && s <= 18)
      },
    },
    {
      id: 'class',
      title: 'Class',
      description: 'Choose your class (race and class are combined in B/X)',
      component: () => null,
      validate: (data) => BX_CLASSES.some((c) => c.id === data.characterClass),
    },
    {
      id: 'alignment',
      title: 'Alignment',
      description: 'Choose Lawful, Neutral, or Chaotic',
      component: () => null,
      validate: (data) => ['Lawful', 'Neutral', 'Chaotic'].includes(data.alignment as string),
    },
    {
      id: 'equipment',
      title: 'Equipment',
      description: 'Purchase starting equipment with your gold',
      component: () => null,
      validate: () => true,
    },
    {
      id: 'details',
      title: 'Details',
      description: 'Name your character and add final details',
      component: () => null,
      validate: (data) => typeof data.name === 'string' && data.name.length > 0,
    },
  ],

  CharacterSheet: BXCharacterSheet,
  CombatTracker: BXCombatTracker,

  calculateModifier: calculateBXModifier,
  calculateToHit: (attacker, targetAC, roll) => {
    const thac0 = (attacker.attributes as { thac0?: number })?.thac0 || 19
    return calculateTHAC0Hit(thac0, targetAC, roll, 0)
  },
}

export { BX_CLASSES, BX_EQUIPMENT }
