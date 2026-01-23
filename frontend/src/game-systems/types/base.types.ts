// Base types for all RPG systems

export interface AbilityScores {
  [key: string]: number
}

export interface SavingThrows {
  [key: string]: number
}

export interface CharacterClass {
  id: string
  name: string
  description: string
  hitDie: string
  primeRequisite: string | string[]
  requirements: Record<string, number>
  abilities: string[]
  restrictions: string[]
}

export interface Equipment {
  id: string
  name: string
  category: string
  costGp: number
  weight: number
  properties: Record<string, unknown>
}

export interface Spell {
  id: string
  name: string
  level: number
  range: string
  duration: string
  description: string
}

export interface Character {
  id: string
  name: string
  level: number
  experiencePoints: number
  currentHp: number
  maxHp: number
  attributes: Record<string, unknown>
}

// Creation step definition
export interface CreationStep {
  id: string
  title: string
  description: string
  component: React.ComponentType<CreationStepProps>
  validate: (data: Record<string, unknown>) => boolean
}

export interface CreationStepProps {
  data: Record<string, unknown>
  onChange: (data: Record<string, unknown>) => void
  options: SystemCreationOptions
}

export interface SystemCreationOptions {
  classes: CharacterClass[]
  equipment: Equipment[]
  spells?: Spell[]
  alignments: string[]
}

// System configuration
export interface GameSystemConfig {
  id: string
  name: string
  version: string
  description: string
  creationSteps: CreationStep[]
  // Components
  CharacterSheet: React.ComponentType<{ character: Character }>
  CombatTracker: React.ComponentType<{ combat: CombatState }>
  // Rules engine
  calculateModifier: (abilityScore: number) => number
  calculateToHit: (attacker: Character, targetAC: number, roll: number) => boolean
}

export interface CombatState {
  round: number
  currentTurnIndex: number
  participants: CombatParticipant[]
}

export interface CombatParticipant {
  id: string
  name: string
  type: 'player' | 'npc' | 'monster'
  initiative: number
  currentHp: number
  maxHp: number
  armorClass: number
  isCurrentTurn: boolean
  conditions: string[]
}
