import { Heart, Shield, Swords, Star, Scroll, Backpack } from 'lucide-react'
import type { Character } from '../../../types/base.types'
import { calculateBXModifier } from '../../utils/calculations'

interface BXAttributes {
  character_class: string
  ability_scores: {
    strength: number
    intelligence: number
    wisdom: number
    dexterity: number
    constitution: number
    charisma: number
  }
  saving_throws: {
    death_ray_poison: number
    wands: number
    paralysis_stone: number
    breath_attack: number
    spells: number
  }
  thac0: number
  armor_class: number
  alignment: string
  gold: number
  equipment: string[]
  spells_memorized?: string[]
}

interface Props {
  character: Character
}

export function BXCharacterSheet({ character }: Props) {
  const attrs = character.attributes as unknown as BXAttributes
  const abilities = attrs.ability_scores || {}
  const saves = attrs.saving_throws || {}

  const hpPercent = (character.currentHp / character.maxHp) * 100

  return (
    <div className="parchment rounded-lg p-6 text-dungeon-800">
      {/* Header */}
      <div className="border-b-2 border-dungeon-400 pb-4 mb-4">
        <h1 className="font-display text-3xl">{character.name}</h1>
        <p className="text-dungeon-600">
          Level {character.level} {attrs.character_class} ({attrs.alignment})
        </p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="space-y-4">
          {/* Ability Scores */}
          <section>
            <h2 className="font-display text-lg border-b border-dungeon-300 mb-2">
              Ability Scores
            </h2>
            <div className="grid grid-cols-3 gap-2 text-center">
              {Object.entries(abilities).map(([key, value]) => (
                <div key={key} className="bg-parchment-200 rounded p-2">
                  <div className="text-xs uppercase text-dungeon-500">
                    {key.substring(0, 3)}
                  </div>
                  <div className="text-2xl font-bold">{value}</div>
                  <div className="text-sm text-dungeon-600">
                    {formatModifier(calculateBXModifier(value))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Saving Throws */}
          <section>
            <h2 className="font-display text-lg border-b border-dungeon-300 mb-2">
              Saving Throws
            </h2>
            <div className="space-y-1 text-sm">
              <SaveRow label="Death Ray/Poison" value={saves.death_ray_poison} />
              <SaveRow label="Wands" value={saves.wands} />
              <SaveRow label="Paralysis/Stone" value={saves.paralysis_stone} />
              <SaveRow label="Breath Attack" value={saves.breath_attack} />
              <SaveRow label="Spells" value={saves.spells} />
            </div>
          </section>
        </div>

        {/* Right Column */}
        <div className="space-y-4">
          {/* Combat Stats */}
          <section>
            <h2 className="font-display text-lg border-b border-dungeon-300 mb-2">
              Combat
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-parchment-200 rounded p-3 text-center">
                <Shield className="w-6 h-6 mx-auto mb-1 text-dungeon-600" />
                <div className="text-xs text-dungeon-500">Armor Class</div>
                <div className="text-2xl font-bold">{attrs.armor_class}</div>
              </div>
              <div className="bg-parchment-200 rounded p-3 text-center">
                <Swords className="w-6 h-6 mx-auto mb-1 text-dungeon-600" />
                <div className="text-xs text-dungeon-500">THAC0</div>
                <div className="text-2xl font-bold">{attrs.thac0}</div>
              </div>
            </div>
          </section>

          {/* HP */}
          <section>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center">
                <Heart className="w-4 h-4 mr-1 text-red-600" />
                <span className="text-sm font-semibold">Hit Points</span>
              </div>
              <span className="font-bold">
                {character.currentHp} / {character.maxHp}
              </span>
            </div>
            <div className="h-4 bg-parchment-300 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  hpPercent > 50 ? 'bg-green-600' : hpPercent > 25 ? 'bg-yellow-600' : 'bg-red-600'
                }`}
                style={{ width: `${hpPercent}%` }}
              />
            </div>
          </section>

          {/* XP */}
          <section>
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <Star className="w-4 h-4 mr-1 text-yellow-600" />
                <span className="text-sm font-semibold">Experience</span>
              </div>
              <span className="font-bold">{character.experiencePoints.toLocaleString()} XP</span>
            </div>
          </section>

          {/* Gold */}
          <section>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Gold</span>
              <span className="font-bold">{attrs.gold} gp</span>
            </div>
          </section>
        </div>
      </div>

      {/* Spells (if any) */}
      {attrs.spells_memorized && attrs.spells_memorized.length > 0 && (
        <section className="mt-4">
          <h2 className="font-display text-lg border-b border-dungeon-300 mb-2 flex items-center">
            <Scroll className="w-4 h-4 mr-2" />
            Spells Memorized
          </h2>
          <div className="flex flex-wrap gap-2">
            {attrs.spells_memorized.map((spell, i) => (
              <span key={i} className="bg-parchment-200 px-2 py-1 rounded text-sm">
                {spell}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Equipment */}
      {attrs.equipment && attrs.equipment.length > 0 && (
        <section className="mt-4">
          <h2 className="font-display text-lg border-b border-dungeon-300 mb-2 flex items-center">
            <Backpack className="w-4 h-4 mr-2" />
            Equipment
          </h2>
          <div className="flex flex-wrap gap-2">
            {attrs.equipment.map((item, i) => {
              // Handle both string and object formats
              const itemName = typeof item === 'string' ? item : item.name
              const quantity = typeof item === 'object' && item.quantity && item.quantity > 1
                ? ` x${item.quantity}`
                : ''
              return (
                <span key={i} className="bg-parchment-200 px-2 py-1 rounded text-sm">
                  {itemName}{quantity}
                </span>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}

function SaveRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className="font-semibold">{value}+</span>
    </div>
  )
}

function formatModifier(mod: number): string {
  if (mod >= 0) return `+${mod}`
  return `${mod}`
}
