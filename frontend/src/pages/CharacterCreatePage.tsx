import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, Dice6 } from 'lucide-react'
import { api } from '@/services/api'
import { getTHAC0ForLevel, getSavingThrowsForLevel } from '@/game-systems/bx-dnd/data/classes'

interface AbilityScores {
  strength: number
  intelligence: number
  wisdom: number
  dexterity: number
  constitution: number
  charisma: number
}

interface CharacterClass {
  id: string
  name: string
  description: string
  hit_die: string
  prime_requisite: string | string[]
  requirements: Record<string, number>
  abilities: string[]
  restrictions: string[]
}

interface CreationOptions {
  classes: CharacterClass[]
  equipment: Array<{ id: string; name: string; category: string; cost_gp: number }>
  alignments: string[]
}

const CREATION_STEPS = [
  'abilities',
  'class',
  'alignment',
  'equipment',
  'details',
  'review',
]

function rollAbilityScore(): number {
  const rolls = Array.from({ length: 4 }, () => Math.floor(Math.random() * 6) + 1)
  rolls.sort((a, b) => b - a)
  return rolls[0] + rolls[1] + rolls[2]
}

export function CharacterCreatePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [character, setCharacter] = useState({
    name: '',
    abilityScores: {
      strength: 10,
      intelligence: 10,
      wisdom: 10,
      dexterity: 10,
      constitution: 10,
      charisma: 10,
    } as AbilityScores,
    characterClass: '',
    alignment: '',
    equipment: [] as string[],
    gold: 0,
    description: {
      sex: '',
      height: '',
      hair: '',
      eyes: '',
      demeanor: '',
      notes: '',
    },
  })

  // Fetch RPG systems to get the B/X D&D system ID
  const { data: systems } = useQuery({
    queryKey: ['rpg-systems'],
    queryFn: () => api.get<Array<{ id: string; code: string; name: string }>>('/campaigns/systems'),
  })

  const bxSystem = systems?.find((s) => s.code === 'bx-dnd')

  const { data: options } = useQuery({
    queryKey: ['creation-options', 'bx-dnd'],
    queryFn: () => api.get<CreationOptions>('/characters/systems/bx-dnd/options'),
  })

  const createMutation = useMutation({
    mutationFn: (data: typeof character) => {
      if (!bxSystem?.id) {
        throw new Error('RPG System not loaded')
      }
      const selectedClass = options?.classes.find((c) => c.id === data.characterClass)
      const hitDie = selectedClass?.hit_die || 'd8'
      const hitDieMax = parseInt(hitDie.replace('d', '')) || 8
      const conMod = getModifier(data.abilityScores.constitution)
      const startingHp = Math.max(1, hitDieMax + conMod)

      // Get saving throws and THAC0
      const savingThrows = getSavingThrowsForLevel(data.characterClass, 1)
      const thac0 = getTHAC0ForLevel(data.characterClass, 1)

      // Calculate armor class from equipment
      const armorClass = calculateArmorClass(
        data.equipment,
        data.abilityScores.dexterity,
        options?.equipment || []
      )

      return api.post('/characters', {
        name: data.name,
        rpg_system_id: bxSystem.id,
        level: 1,
        experience_points: 0,
        current_hp: startingHp,
        max_hp: startingHp,
        attributes: {
          character_class: data.characterClass,
          ability_scores: data.abilityScores,
          alignment: data.alignment,
          equipment: data.equipment,
          gold: data.gold,
          // Add B/X-specific combat stats
          saving_throws: {
            death_ray_poison: savingThrows.deathRayPoison,
            wands: savingThrows.wands,
            paralysis_stone: savingThrows.paralysisStone,
            breath_attack: savingThrows.breathAttack,
            spells: savingThrows.spells,
          },
          thac0: thac0,
          armor_class: armorClass,
          // Character description
          description: data.description,
        },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      navigate('/characters')
    },
  })

  const rollAllAbilities = () => {
    setCharacter({
      ...character,
      abilityScores: {
        strength: rollAbilityScore(),
        intelligence: rollAbilityScore(),
        wisdom: rollAbilityScore(),
        dexterity: rollAbilityScore(),
        constitution: rollAbilityScore(),
        charisma: rollAbilityScore(),
      },
    })
  }

  const nextStep = () => {
    if (step < CREATION_STEPS.length - 1) {
      setStep(step + 1)
    }
  }

  const prevStep = () => {
    if (step > 0) {
      setStep(step - 1)
    }
  }

  const renderStep = () => {
    switch (CREATION_STEPS[step]) {
      case 'abilities':
        return (
          <AbilityScoreStep
            scores={character.abilityScores}
            onRollAll={rollAllAbilities}
            onChange={(scores) => setCharacter({ ...character, abilityScores: scores })}
          />
        )
      case 'class':
        return (
          <ClassStep
            classes={options?.classes || []}
            selected={character.characterClass}
            abilityScores={character.abilityScores}
            onSelect={(cls) => setCharacter({ ...character, characterClass: cls })}
          />
        )
      case 'alignment':
        return (
          <AlignmentStep
            alignments={options?.alignments || ['Lawful', 'Neutral', 'Chaotic']}
            selected={character.alignment}
            onSelect={(alignment) => setCharacter({ ...character, alignment })}
          />
        )
      case 'equipment':
        return (
          <EquipmentStep
            equipment={options?.equipment || []}
            selected={character.equipment}
            gold={character.gold}
            onUpdate={(equipment, gold) => setCharacter({ ...character, equipment, gold })}
          />
        )
      case 'details':
        return (
          <DetailsStep
            name={character.name}
            description={character.description}
            onUpdate={(name, description) => setCharacter({ ...character, name, description })}
          />
        )
      case 'review':
        return <ReviewStep character={character} classes={options?.classes || []} />
      default:
        return null
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="font-display text-4xl text-parchment-100 mb-8">Create Character</h1>

      {/* Progress */}
      <div className="flex items-center mb-8">
        {CREATION_STEPS.map((s, i) => (
          <div key={s} className="flex items-center">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center ${
                i <= step ? 'bg-parchment-600 text-dungeon-900' : 'bg-dungeon-700 text-parchment-400'
              }`}
            >
              {i + 1}
            </div>
            {i < CREATION_STEPS.length - 1 && (
              <div className={`w-12 h-1 ${i < step ? 'bg-parchment-600' : 'bg-dungeon-700'}`} />
            )}
          </div>
        ))}
      </div>

      <div className="card mb-8">
        {renderStep()}
      </div>

      <div className="flex justify-between">
        <button
          onClick={prevStep}
          disabled={step === 0}
          className="btn btn-secondary flex items-center space-x-2 disabled:opacity-50"
        >
          <ChevronLeft className="w-5 h-5" />
          <span>Back</span>
        </button>

        {step < CREATION_STEPS.length - 1 ? (
          <button onClick={nextStep} className="btn btn-primary flex items-center space-x-2">
            <span>Next</span>
            <ChevronRight className="w-5 h-5" />
          </button>
        ) : (
          <button
            onClick={() => createMutation.mutate(character)}
            disabled={createMutation.isPending}
            className="btn btn-primary"
          >
            {createMutation.isPending ? 'Creating...' : 'Create Character'}
          </button>
        )}
      </div>
    </div>
  )
}

function AbilityScoreStep({
  scores,
  onRollAll,
  onChange: _onChange,
}: {
  scores: AbilityScores
  onRollAll: () => void
  onChange: (scores: AbilityScores) => void
}) {
  const abilities = [
    { key: 'strength', label: 'Strength', abbr: 'STR' },
    { key: 'intelligence', label: 'Intelligence', abbr: 'INT' },
    { key: 'wisdom', label: 'Wisdom', abbr: 'WIS' },
    { key: 'dexterity', label: 'Dexterity', abbr: 'DEX' },
    { key: 'constitution', label: 'Constitution', abbr: 'CON' },
    { key: 'charisma', label: 'Charisma', abbr: 'CHA' },
  ]

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Roll Ability Scores</h2>
      <p className="text-parchment-400 mb-6">
        Roll 4d6 and drop the lowest die for each ability score.
      </p>

      <button onClick={onRollAll} className="btn btn-primary mb-6 flex items-center space-x-2">
        <Dice6 className="w-5 h-5" />
        <span>Roll All Abilities</span>
      </button>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {abilities.map((ability) => (
          <div key={ability.key} className="bg-dungeon-700 rounded-lg p-4 text-center">
            <div className="text-parchment-400 text-sm mb-1">{ability.label}</div>
            <div className="text-3xl text-parchment-100 font-bold">
              {scores[ability.key as keyof AbilityScores]}
            </div>
            <div className="text-parchment-500 text-sm">
              {getModifierText(scores[ability.key as keyof AbilityScores])}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ClassStep({
  classes,
  selected,
  abilityScores,
  onSelect,
}: {
  classes: CharacterClass[]
  selected: string
  abilityScores: AbilityScores
  onSelect: (cls: string) => void
}) {
  const meetsRequirements = (cls: CharacterClass) => {
    if (!cls.requirements) return true
    return Object.entries(cls.requirements).every(
      ([ability, min]) => abilityScores[ability as keyof AbilityScores] >= min
    )
  }

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Choose Your Class</h2>
      <p className="text-parchment-400 mb-6">
        In B/X D&D, race and class are combined. Choose your character's class.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {classes.map((cls) => {
          const canSelect = meetsRequirements(cls)
          return (
            <div
              key={cls.id}
              onClick={() => canSelect && onSelect(cls.id)}
              className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                selected === cls.id
                  ? 'border-parchment-500 bg-dungeon-700'
                  : canSelect
                  ? 'border-dungeon-600 hover:border-parchment-600'
                  : 'border-dungeon-700 opacity-50 cursor-not-allowed'
              }`}
            >
              <h3 className="font-display text-xl text-parchment-100">{cls.name}</h3>
              <p className="text-parchment-400 text-sm mb-2">{cls.description}</p>
              <div className="text-sm">
                <span className="text-parchment-500">Hit Die: </span>
                <span className="text-parchment-200">{cls.hit_die}</span>
              </div>
              {!canSelect && (
                <p className="text-red-400 text-sm mt-2">
                  Requirements not met
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AlignmentStep({
  alignments,
  selected,
  onSelect,
}: {
  alignments: string[]
  selected: string
  onSelect: (alignment: string) => void
}) {
  const descriptions: Record<string, string> = {
    Lawful: 'Believes in order, honor, and following rules. Champions justice and civilization.',
    Neutral: 'Values balance and personal freedom. Acts based on circumstances.',
    Chaotic: 'Values individual freedom above all. May be selfish or a free spirit.',
  }

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Choose Alignment</h2>
      <p className="text-parchment-400 mb-6">
        Your alignment reflects your character's moral outlook and guides their actions.
      </p>

      <div className="space-y-4">
        {alignments.map((alignment) => (
          <div
            key={alignment}
            onClick={() => onSelect(alignment)}
            className={`p-4 rounded-lg border cursor-pointer transition-colors ${
              selected === alignment
                ? 'border-parchment-500 bg-dungeon-700'
                : 'border-dungeon-600 hover:border-parchment-600'
            }`}
          >
            <h3 className="font-display text-xl text-parchment-100">{alignment}</h3>
            <p className="text-parchment-400 text-sm">{descriptions[alignment]}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function EquipmentStep({
  equipment,
  selected,
  gold,
  onUpdate,
}: {
  equipment: Array<{ id: string; name: string; category: string; cost_gp: number; weight?: number; damage?: string; ac?: number; ac_bonus?: number }>
  selected: string[]
  gold: number
  onUpdate: (equipment: string[], gold: number) => void
}) {
  const [hasRolled, setHasRolled] = useState(false)

  const rollStartingGold = () => {
    const roll = Array.from({ length: 3 }, () => Math.floor(Math.random() * 6) + 1)
    const total = roll.reduce((a, b) => a + b, 0) * 10
    onUpdate([], total)
    setHasRolled(true)
  }

  const toggleItem = (itemId: string) => {
    const item = equipment.find(e => e.id === itemId)
    if (!item) return

    if (selected.includes(itemId)) {
      // Remove item, refund gold
      onUpdate(selected.filter(id => id !== itemId), gold + item.cost_gp)
    } else {
      // Buy item if affordable
      if (gold >= item.cost_gp) {
        onUpdate([...selected, itemId], gold - item.cost_gp)
      }
    }
  }

  const categories = ['weapon', 'armor', 'ammo', 'gear']
  const categoryLabels: Record<string, string> = {
    weapon: 'Weapons',
    armor: 'Armor & Shields',
    ammo: 'Ammunition',
    gear: 'Adventuring Gear',
  }

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Starting Equipment</h2>
      <p className="text-parchment-400 mb-6">
        Roll 3d6 x 10 for starting gold, then purchase equipment.
      </p>

      <div className="flex items-center space-x-4 mb-6">
        <button onClick={rollStartingGold} className="btn btn-primary flex items-center space-x-2">
          <Dice6 className="w-5 h-5" />
          <span>Roll Starting Gold</span>
        </button>
        <div className="text-parchment-100 text-2xl font-bold">{gold} gp</div>
      </div>

      {hasRolled && equipment.length > 0 ? (
        <div className="space-y-6 max-h-96 overflow-y-auto">
          {categories.map(category => {
            const items = equipment.filter(e => e.category === category)
            if (items.length === 0) return null

            return (
              <div key={category}>
                <h3 className="font-display text-lg text-parchment-200 mb-2 border-b border-dungeon-600 pb-1">
                  {categoryLabels[category] || category}
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {items.map(item => {
                    const isSelected = selected.includes(item.id)
                    const canAfford = gold >= item.cost_gp

                    return (
                      <div
                        key={item.id}
                        onClick={() => (isSelected || canAfford) && toggleItem(item.id)}
                        className={`p-2 rounded border cursor-pointer transition-colors text-sm ${
                          isSelected
                            ? 'border-parchment-500 bg-dungeon-600'
                            : canAfford
                            ? 'border-dungeon-600 hover:border-parchment-600'
                            : 'border-dungeon-700 opacity-50 cursor-not-allowed'
                        }`}
                      >
                        <div className="flex justify-between items-start">
                          <span className="text-parchment-100">{item.name}</span>
                          <span className="text-parchment-400">{item.cost_gp} gp</span>
                        </div>
                        {item.damage && (
                          <span className="text-parchment-500 text-xs">Dmg: {item.damage}</span>
                        )}
                        {item.ac && (
                          <span className="text-parchment-500 text-xs">AC: {item.ac}</span>
                        )}
                        {item.ac_bonus && (
                          <span className="text-parchment-500 text-xs">AC Bonus: -{item.ac_bonus}</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-parchment-400">
          Roll for starting gold to see available equipment.
        </p>
      )}

      <div className="mt-4 text-parchment-300">
        Selected: {selected.length} items
      </div>
    </div>
  )
}

interface CharacterDescription {
  sex: string
  height: string
  hair: string
  eyes: string
  demeanor: string
  notes: string
}

function DetailsStep({
  name,
  description,
  onUpdate,
}: {
  name: string
  description: CharacterDescription
  onUpdate: (name: string, description: CharacterDescription) => void
}) {
  const updateDescription = (field: keyof CharacterDescription, value: string) => {
    onUpdate(name, { ...description, [field]: value })
  }

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Character Details</h2>

      <div className="mb-6">
        <label className="label block mb-2">Character Name *</label>
        <input
          type="text"
          value={name}
          onChange={(e) => onUpdate(e.target.value, description)}
          placeholder="Enter your character's name"
          className="input w-full"
        />
      </div>

      <h3 className="font-display text-lg text-parchment-200 mb-3 border-b border-dungeon-600 pb-1">
        Physical Description (Optional)
      </h3>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="label block mb-1 text-sm">Sex</label>
          <input
            type="text"
            value={description.sex}
            onChange={(e) => updateDescription('sex', e.target.value)}
            placeholder="Male, Female, etc."
            className="input w-full text-sm"
          />
        </div>
        <div>
          <label className="label block mb-1 text-sm">Height</label>
          <input
            type="text"
            value={description.height}
            onChange={(e) => updateDescription('height', e.target.value)}
            placeholder="5'8, tall, short..."
            className="input w-full text-sm"
          />
        </div>
        <div>
          <label className="label block mb-1 text-sm">Hair</label>
          <input
            type="text"
            value={description.hair}
            onChange={(e) => updateDescription('hair', e.target.value)}
            placeholder="Black, blonde, bald..."
            className="input w-full text-sm"
          />
        </div>
        <div>
          <label className="label block mb-1 text-sm">Eyes</label>
          <input
            type="text"
            value={description.eyes}
            onChange={(e) => updateDescription('eyes', e.target.value)}
            placeholder="Blue, brown, green..."
            className="input w-full text-sm"
          />
        </div>
      </div>

      <div className="mb-4">
        <label className="label block mb-1 text-sm">Demeanor</label>
        <input
          type="text"
          value={description.demeanor}
          onChange={(e) => updateDescription('demeanor', e.target.value)}
          placeholder="Stoic, cheerful, mysterious..."
          className="input w-full text-sm"
        />
      </div>

      <div>
        <label className="label block mb-1 text-sm">Notes</label>
        <textarea
          value={description.notes}
          onChange={(e) => updateDescription('notes', e.target.value)}
          placeholder="Any additional notes about your character's appearance or background..."
          className="input w-full text-sm h-20 resize-none"
        />
      </div>
    </div>
  )
}

function ReviewStep({
  character,
  classes,
}: {
  character: {
    name: string
    abilityScores: AbilityScores
    characterClass: string
    alignment: string
    gold: number
    description: CharacterDescription
  }
  classes: CharacterClass[]
}) {
  const selectedClass = classes.find((c) => c.id === character.characterClass)
  const desc = character.description

  return (
    <div>
      <h2 className="font-display text-2xl text-parchment-100 mb-4">Review Your Character</h2>

      <div className="space-y-4">
        <div>
          <span className="text-parchment-400">Name: </span>
          <span className="text-parchment-100">{character.name || '(not set)'}</span>
        </div>
        <div>
          <span className="text-parchment-400">Class: </span>
          <span className="text-parchment-100">{selectedClass?.name || '(not set)'}</span>
        </div>
        <div>
          <span className="text-parchment-400">Alignment: </span>
          <span className="text-parchment-100">{character.alignment || '(not set)'}</span>
        </div>
        <div>
          <span className="text-parchment-400">Gold: </span>
          <span className="text-parchment-100">{character.gold} gp</span>
        </div>
        <div>
          <span className="text-parchment-400">Ability Scores: </span>
          <span className="text-parchment-100">
            STR {character.abilityScores.strength},
            INT {character.abilityScores.intelligence},
            WIS {character.abilityScores.wisdom},
            DEX {character.abilityScores.dexterity},
            CON {character.abilityScores.constitution},
            CHA {character.abilityScores.charisma}
          </span>
        </div>
        {(desc.sex || desc.height || desc.hair || desc.eyes) && (
          <div>
            <span className="text-parchment-400">Description: </span>
            <span className="text-parchment-100">
              {[desc.sex, desc.height, desc.hair && `${desc.hair} hair`, desc.eyes && `${desc.eyes} eyes`]
                .filter(Boolean)
                .join(', ')}
            </span>
          </div>
        )}
        {desc.demeanor && (
          <div>
            <span className="text-parchment-400">Demeanor: </span>
            <span className="text-parchment-100 italic">{desc.demeanor}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function getModifier(score: number): number {
  if (score <= 3) return -3
  if (score <= 5) return -2
  if (score <= 8) return -1
  if (score <= 12) return 0
  if (score <= 15) return 1
  if (score <= 17) return 2
  return 3
}

function getModifierText(score: number): string {
  const mod = getModifier(score)
  return mod >= 0 ? `+${mod}` : `${mod}`
}

/**
 * Calculate armor class from equipped armor and dexterity.
 * B/X uses descending AC (9 is unarmored, lower is better).
 */
function calculateArmorClass(
  equipmentIds: string[],
  dexScore: number,
  equipmentList: Array<{ id: string; ac?: number; ac_bonus?: number }>
): number {
  // Base AC is 9 (unarmored)
  let baseAC = 9

  // Find the best armor (lowest AC value)
  for (const itemId of equipmentIds) {
    const item = equipmentList.find((e) => e.id === itemId)
    if (item?.ac !== undefined && item.ac < baseAC) {
      baseAC = item.ac
    }
  }

  // Apply shield bonus if present
  let shieldBonus = 0
  for (const itemId of equipmentIds) {
    const item = equipmentList.find((e) => e.id === itemId)
    if (item?.ac_bonus !== undefined) {
      shieldBonus = Math.max(shieldBonus, item.ac_bonus)
    }
  }

  // Apply DEX modifier (improves AC in B/X)
  const dexMod = getModifier(dexScore)

  // Final AC: base - shield bonus - dex mod (lower is better)
  return baseAC - shieldBonus - dexMod
}
