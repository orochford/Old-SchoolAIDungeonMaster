import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, BookOpen, Plus, Minus, Sparkles, Moon } from 'lucide-react'
import { api } from '@/services/api'

interface Spell {
  id: string
  name: string
  code: string
  level: number
  spell_class: string
  duration: string | null
  range: string | null
  description: string
  reversible: boolean
  reversed_name: string | null
  save: string | null
  area_of_effect: string | null
}

interface SpellStatus {
  can_cast: boolean
  spell_class?: string
  max_spell_level: number
  spell_slots: Record<number, number>
  spells_memorized: Record<string, string[]>
  slots_remaining: Record<number, number>
  spellbook?: string[]
}

interface Props {
  characterId: string
  onClose: () => void
}

export function SpellbookModal({ characterId, onClose }: Props) {
  const queryClient = useQueryClient()
  const [selectedSpells, setSelectedSpells] = useState<Record<string, string[]>>({})
  const [viewingSpell, setViewingSpell] = useState<Spell | null>(null)

  const { data: status } = useQuery({
    queryKey: ['spell-status', characterId],
    queryFn: () => api.get<SpellStatus>(`/spells/character/${characterId}/status`),
  })

  const { data: availableSpells } = useQuery({
    queryKey: ['available-spells', characterId],
    queryFn: () => api.get<Spell[]>(`/spells/character/${characterId}/available`),
    enabled: !!characterId,
  })

  const { data: spellbookSpells } = useQuery({
    queryKey: ['spellbook', characterId],
    queryFn: () => api.get<Spell[]>(`/spells/character/${characterId}/spellbook`),
    enabled: !!characterId && status?.spell_class === 'magic-user',
  })

  // Initialize selected spells from currently memorized
  useEffect(() => {
    if (status?.spells_memorized) {
      setSelectedSpells(status.spells_memorized)
    }
  }, [status?.spells_memorized])

  const restMutation = useMutation({
    mutationFn: (spells: string[]) =>
      api.post(`/spells/character/${characterId}/rest`, { spells }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spell-status', characterId] })
      onClose()
    },
  })

  if (!status?.can_cast) {
    return null
  }

  // For magic-users, use spellbook; for clerics, use all available
  const spellsToShow =
    status.spell_class === 'magic-user' ? spellbookSpells : availableSpells

  // Group spells by level
  const spellsByLevel = (spellsToShow || []).reduce((acc, spell) => {
    if (!acc[spell.level]) acc[spell.level] = []
    acc[spell.level].push(spell)
    return acc
  }, {} as Record<number, Spell[]>)

  // Calculate how many slots are used per level
  const getUsedSlots = (level: number) => {
    return (selectedSpells[String(level)] || []).length
  }

  const getMaxSlots = (level: number) => {
    return status.spell_slots[level] || 0
  }

  const addSpell = (spell: Spell) => {
    const level = String(spell.level)
    const current = selectedSpells[level] || []
    const max = getMaxSlots(spell.level)

    if (current.length >= max) return

    setSelectedSpells({
      ...selectedSpells,
      [level]: [...current, spell.code],
    })
  }

  const removeSpell = (spell: Spell) => {
    const level = String(spell.level)
    const current = selectedSpells[level] || []
    const index = current.indexOf(spell.code)

    if (index === -1) return

    const newList = [...current]
    newList.splice(index, 1)

    setSelectedSpells({
      ...selectedSpells,
      [level]: newList,
    })
  }

  const getSpellCount = (spellCode: string, level: number) => {
    return (selectedSpells[String(level)] || []).filter((c) => c === spellCode).length
  }

  const handleRest = () => {
    // Flatten all selected spells into a single array
    const allSpells = Object.values(selectedSpells).flat()
    restMutation.mutate(allSpells)
  }

  const totalSelected = Object.values(selectedSpells).flat().length
  const totalSlots = Object.values(status.spell_slots || {}).reduce((a, b) => a + b, 0)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="card w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-xl text-parchment-100 flex items-center gap-2">
            <BookOpen className="w-6 h-6" />
            {status.spell_class === 'magic-user' ? 'Spellbook' : 'Prayer Book'}
          </h2>
          <button
            onClick={onClose}
            className="text-parchment-400 hover:text-parchment-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Slot Summary */}
        <div className="bg-dungeon-700 rounded p-3 mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-parchment-300">
              Preparing spells for tomorrow
            </span>
            <span className="text-sm text-parchment-400">
              {totalSelected} / {totalSlots} slots used
            </span>
          </div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(status.spell_slots || {}).map(([level, max]) => {
              const used = getUsedSlots(Number(level))
              return (
                <div
                  key={level}
                  className={`px-3 py-1 rounded text-sm ${
                    used === max
                      ? 'bg-purple-900/50 text-purple-300'
                      : used > 0
                      ? 'bg-dungeon-600 text-parchment-300'
                      : 'bg-dungeon-800 text-parchment-500'
                  }`}
                >
                  Level {level}: {used}/{max}
                </div>
              )
            })}
          </div>
        </div>

        {/* Spell List */}
        <div className="flex-1 overflow-y-auto space-y-4">
          {Object.entries(spellsByLevel)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([level, spells]) => {
              const maxSlots = getMaxSlots(Number(level))
              const usedSlots = getUsedSlots(Number(level))

              return (
                <div key={level}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-display text-parchment-200">
                      Level {level} Spells
                    </h3>
                    <span
                      className={`text-xs ${
                        usedSlots >= maxSlots
                          ? 'text-purple-400'
                          : 'text-parchment-500'
                      }`}
                    >
                      {usedSlots}/{maxSlots} slots
                    </span>
                  </div>

                  <div className="space-y-1">
                    {spells.map((spell) => {
                      const count = getSpellCount(spell.code, spell.level)
                      const canAdd = usedSlots < maxSlots

                      return (
                        <div
                          key={spell.code}
                          className={`flex items-center justify-between p-2 rounded transition-colors ${
                            count > 0
                              ? 'bg-purple-900/30 border border-purple-800/50'
                              : 'bg-dungeon-700 hover:bg-dungeon-600'
                          }`}
                        >
                          <div
                            className="flex-1 cursor-pointer"
                            onClick={() => setViewingSpell(spell)}
                          >
                            <span className="text-sm text-parchment-200">
                              {spell.name}
                            </span>
                            {spell.reversible && (
                              <span className="text-xs text-purple-400 ml-2">
                                (R)
                              </span>
                            )}
                            <span className="text-xs text-parchment-500 ml-2">
                              {spell.range} • {spell.duration}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            {count > 0 && (
                              <>
                                <button
                                  onClick={() => removeSpell(spell)}
                                  className="p-1 text-parchment-400 hover:text-parchment-200 bg-dungeon-600 rounded"
                                >
                                  <Minus className="w-4 h-4" />
                                </button>
                                <span className="text-sm text-parchment-200 w-6 text-center">
                                  {count}
                                </span>
                              </>
                            )}
                            <button
                              onClick={() => addSpell(spell)}
                              disabled={!canAdd}
                              className={`p-1 rounded ${
                                canAdd
                                  ? 'text-parchment-400 hover:text-parchment-200 bg-dungeon-600'
                                  : 'text-parchment-600 bg-dungeon-800 cursor-not-allowed'
                              }`}
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}

          {Object.keys(spellsByLevel).length === 0 && (
            <div className="text-center py-8">
              <Sparkles className="w-12 h-12 mx-auto mb-3 text-parchment-600" />
              <p className="text-parchment-500">
                {status.spell_class === 'magic-user'
                  ? 'No spells in your spellbook yet.'
                  : status.spell_class === 'cleric' && totalSlots === 0
                  ? 'Clerics gain spells at Level 2. Continue your journey and the divine will grant you power.'
                  : 'No spells available at your level.'}
              </p>
            </div>
          )}
        </div>

        {/* Spell Details */}
        {viewingSpell && (
          <div className="mt-4 p-3 bg-dungeon-900 rounded border border-dungeon-600">
            <div className="flex items-start justify-between mb-2">
              <h4 className="font-display text-parchment-100">{viewingSpell.name}</h4>
              <button
                onClick={() => setViewingSpell(null)}
                className="text-parchment-500 hover:text-parchment-300"
              >
                ×
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs mb-2">
              <div>
                <span className="text-parchment-500">Range:</span>{' '}
                <span className="text-parchment-300">{viewingSpell.range}</span>
              </div>
              <div>
                <span className="text-parchment-500">Duration:</span>{' '}
                <span className="text-parchment-300">{viewingSpell.duration}</span>
              </div>
              {viewingSpell.save && (
                <div>
                  <span className="text-parchment-500">Save:</span>{' '}
                  <span className="text-parchment-300">{viewingSpell.save}</span>
                </div>
              )}
              {viewingSpell.area_of_effect && (
                <div>
                  <span className="text-parchment-500">Area:</span>{' '}
                  <span className="text-parchment-300">{viewingSpell.area_of_effect}</span>
                </div>
              )}
            </div>
            <p className="text-xs text-parchment-400">{viewingSpell.description}</p>
            {viewingSpell.reversible && (
              <p className="text-xs text-purple-400 mt-1">
                Can be reversed as: {viewingSpell.reversed_name}
              </p>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="btn btn-secondary">
            Cancel
          </button>
          <button
            onClick={handleRest}
            disabled={restMutation.isPending}
            className="btn btn-primary"
          >
            <Moon className="w-4 h-4 mr-2" />
            {restMutation.isPending ? 'Resting...' : 'Rest & Memorize'}
          </button>
        </div>
      </div>
    </div>
  )
}
