import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Zap,
  Info,
} from 'lucide-react'
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
  reason?: string
  spell_class?: string
  max_spell_level: number
  spell_slots: Record<number, number>
  spells_memorized: Record<string, string[]>
  slots_remaining: Record<number, number>
  spellbook?: string[]
}

interface Props {
  characterId: string
  onCastSpell?: (spell: Spell) => void
  onOpenSpellbook: () => void
}

export function SpellPanel({ characterId, onCastSpell, onOpenSpellbook }: Props) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [selectedSpell, setSelectedSpell] = useState<Spell | null>(null)
  const queryClient = useQueryClient()

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['spell-status', characterId],
    queryFn: () => api.get<SpellStatus>(`/spells/character/${characterId}/status`),
    enabled: !!characterId,
    refetchInterval: 5000,
  })

  const { data: allSpells } = useQuery({
    queryKey: ['all-spells'],
    queryFn: () => api.get<Spell[]>('/spells'),
  })

  const castMutation = useMutation({
    mutationFn: (spellCode: string) =>
      api.post(`/spells/character/${characterId}/cast`, { spell_code: spellCode }),
    onSuccess: (_, spellCode) => {
      queryClient.invalidateQueries({ queryKey: ['spell-status', characterId] })
      // Find the spell and call onCastSpell
      const spell = allSpells?.find((s) => s.code === spellCode)
      if (spell && onCastSpell) {
        onCastSpell(spell)
      }
    },
  })

  if (statusLoading) {
    return (
      <div className="card">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-parchment-400" />
          <span className="text-parchment-400">Loading spells...</span>
        </div>
      </div>
    )
  }

  if (!status?.can_cast) {
    return null // Don't show panel for non-casters
  }

  // Get spell details for memorized spells
  const getSpellByCode = (code: string) => allSpells?.find((s) => s.code === code)

  // Group memorized spells by level
  const memorizedByLevel = status.spells_memorized || {}

  // Calculate total slots info
  const totalSlots = Object.values(status.spell_slots || {}).reduce((a, b) => a + b, 0)
  const usedSlots = Object.entries(memorizedByLevel).reduce(
    (total, [, spells]) => total - spells.length,
    totalSlots
  )

  return (
    <div className="card">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <h3 className="font-display text-lg text-parchment-100 flex items-center">
          <Sparkles className="w-5 h-5 mr-2" />
          Spells
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-parchment-400">
            {Object.values(memorizedByLevel).flat().length} memorized
          </span>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-parchment-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-parchment-400" />
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-3">
          {/* Spell Slots Summary */}
          <div className="flex items-center justify-between text-xs">
            <span className="text-parchment-400">Spell Slots:</span>
            <div className="flex gap-2">
              {Object.entries(status.spell_slots || {}).map(([level, max]) => {
                const memorized = (memorizedByLevel[level] || []).length
                return (
                  <span
                    key={level}
                    className={`px-2 py-0.5 rounded ${
                      memorized > 0
                        ? 'bg-amber-900/50 text-amber-300'
                        : 'bg-dungeon-700 text-parchment-500'
                    }`}
                  >
                    L{level}: {memorized}/{max}
                  </span>
                )
              })}
            </div>
          </div>

          {/* Memorized Spells */}
          {Object.entries(memorizedByLevel).length === 0 ? (
            <div className="text-center py-4">
              <p className="text-parchment-500 text-sm mb-2">No spells memorized</p>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenSpellbook()
                }}
                className="btn btn-secondary text-sm"
              >
                <BookOpen className="w-4 h-4 mr-1" />
                Prepare Spells
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {Object.entries(memorizedByLevel)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([level, spellCodes]) => {
                  if (spellCodes.length === 0) return null

                  // Count duplicates
                  const spellCounts = spellCodes.reduce((acc, code) => {
                    acc[code] = (acc[code] || 0) + 1
                    return acc
                  }, {} as Record<string, number>)

                  return (
                    <div key={level}>
                      <div className="text-xs text-parchment-500 mb-1">
                        Level {level}
                      </div>
                      <div className="space-y-1">
                        {Object.entries(spellCounts).map(([code, count]) => {
                          const spell = getSpellByCode(code)
                          if (!spell) return null

                          return (
                            <div
                              key={code}
                              className="flex items-center justify-between bg-dungeon-700 rounded p-2 group"
                            >
                              <div className="flex items-center gap-2 flex-1 min-w-0">
                                <span className="text-sm text-parchment-200 truncate">
                                  {spell.name}
                                  {count > 1 && (
                                    <span className="text-parchment-500 ml-1">
                                      x{count}
                                    </span>
                                  )}
                                </span>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setSelectedSpell(
                                      selectedSpell?.code === code ? null : spell
                                    )
                                  }}
                                  className="text-parchment-500 hover:text-parchment-300 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                  <Info className="w-3 h-3" />
                                </button>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  castMutation.mutate(code)
                                }}
                                disabled={castMutation.isPending}
                                className="btn btn-primary text-xs px-2 py-1"
                              >
                                <Zap className="w-3 h-3 mr-1" />
                                Cast
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
            </div>
          )}

          {/* Selected Spell Details */}
          {selectedSpell && (
            <div className="bg-dungeon-900 rounded p-3 border border-dungeon-600">
              <div className="flex items-start justify-between mb-2">
                <h4 className="font-display text-parchment-100">
                  {selectedSpell.name}
                </h4>
                <button
                  onClick={() => setSelectedSpell(null)}
                  className="text-parchment-500 hover:text-parchment-300"
                >
                  ×
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                <div>
                  <span className="text-parchment-500">Range:</span>{' '}
                  <span className="text-parchment-300">{selectedSpell.range}</span>
                </div>
                <div>
                  <span className="text-parchment-500">Duration:</span>{' '}
                  <span className="text-parchment-300">{selectedSpell.duration}</span>
                </div>
                {selectedSpell.save && (
                  <div>
                    <span className="text-parchment-500">Save:</span>{' '}
                    <span className="text-parchment-300">{selectedSpell.save}</span>
                  </div>
                )}
                {selectedSpell.area_of_effect && (
                  <div>
                    <span className="text-parchment-500">Area:</span>{' '}
                    <span className="text-parchment-300">
                      {selectedSpell.area_of_effect}
                    </span>
                  </div>
                )}
              </div>
              <p className="text-xs text-parchment-400">{selectedSpell.description}</p>
              {selectedSpell.reversible && (
                <p className="text-xs text-amber-400 mt-1">
                  Reversible: {selectedSpell.reversed_name}
                </p>
              )}
            </div>
          )}

          {/* Prepare Spells Button */}
          {Object.entries(memorizedByLevel).length > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onOpenSpellbook()
              }}
              className="w-full btn btn-secondary text-sm"
            >
              <BookOpen className="w-4 h-4 mr-1" />
              Manage Spells
            </button>
          )}
        </div>
      )}
    </div>
  )
}
