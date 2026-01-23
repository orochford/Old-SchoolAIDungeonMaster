import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Play, Trash2 } from 'lucide-react'
import { api } from '@/services/api'

interface Character {
  id: string
  name: string
  level: number
  experience_points: number
  status: string
  current_hp: number
  max_hp: number
  attributes: {
    character_class?: string
    alignment?: string
    ability_scores?: {
      strength: number
      intelligence: number
      wisdom: number
      dexterity: number
      constitution: number
      charisma: number
    }
    equipment?: string[]
    gold?: number
  }
}

export function CharacterSheetPage() {
  const { characterId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: character, isLoading, error } = useQuery({
    queryKey: ['character', characterId],
    queryFn: () => api.get<Character>(`/characters/${characterId}`),
    enabled: !!characterId,
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/characters/${characterId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      navigate('/characters')
    },
  })

  if (isLoading) {
    return (
      <div className="text-center text-parchment-400 py-12">
        Loading character...
      </div>
    )
  }

  if (error || !character) {
    return (
      <div className="text-center text-red-400 py-12">
        Character not found
      </div>
    )
  }

  const abilityScores = character.attributes.ability_scores
  const getModifier = (score: number) => {
    if (score <= 3) return -3
    if (score <= 5) return -2
    if (score <= 8) return -1
    if (score <= 12) return 0
    if (score <= 15) return 1
    if (score <= 17) return 2
    return 3
  }

  const formatMod = (mod: number) => (mod >= 0 ? `+${mod}` : `${mod}`)

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center space-x-4">
          <Link to="/characters" className="text-parchment-400 hover:text-parchment-200">
            <ArrowLeft className="w-6 h-6" />
          </Link>
          <div>
            <h1 className="font-display text-4xl text-parchment-100">{character.name}</h1>
            <p className="text-parchment-400">
              Level {character.level} {character.attributes.character_class || 'Adventurer'}
              {character.attributes.alignment && ` • ${character.attributes.alignment}`}
            </p>
          </div>
        </div>
        <div className="flex space-x-2">
          <Link to={`/play/${character.id}`} className="btn btn-primary flex items-center space-x-2">
            <Play className="w-5 h-5" />
            <span>Play</span>
          </Link>
          <button
            onClick={() => {
              if (confirm('Are you sure you want to delete this character?')) {
                deleteMutation.mutate()
              }
            }}
            className="btn btn-secondary text-red-400 hover:text-red-300"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Vitals */}
        <div className="card">
          <h2 className="font-display text-xl text-parchment-100 mb-4">Vitals</h2>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm text-parchment-400 mb-1">
                <span>Hit Points</span>
                <span>{character.current_hp} / {character.max_hp}</span>
              </div>
              <div className="h-3 bg-dungeon-700 rounded-full overflow-hidden">
                <div
                  className={`h-full ${
                    character.current_hp / character.max_hp > 0.5
                      ? 'bg-green-600'
                      : character.current_hp / character.max_hp > 0.25
                      ? 'bg-yellow-600'
                      : 'bg-red-600'
                  }`}
                  style={{ width: `${(character.current_hp / character.max_hp) * 100}%` }}
                />
              </div>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-400">Experience</span>
              <span className="text-parchment-100">{character.experience_points} XP</span>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-400">Gold</span>
              <span className="text-parchment-100">{character.attributes.gold || 0} gp</span>
            </div>
            <div className="flex justify-between">
              <span className="text-parchment-400">Status</span>
              <span className={`capitalize ${character.status === 'active' ? 'text-green-400' : 'text-red-400'}`}>
                {character.status}
              </span>
            </div>
          </div>
        </div>

        {/* Ability Scores */}
        <div className="card">
          <h2 className="font-display text-xl text-parchment-100 mb-4">Ability Scores</h2>
          {abilityScores ? (
            <div className="grid grid-cols-2 gap-4">
              {[
                { key: 'strength', label: 'STR' },
                { key: 'intelligence', label: 'INT' },
                { key: 'wisdom', label: 'WIS' },
                { key: 'dexterity', label: 'DEX' },
                { key: 'constitution', label: 'CON' },
                { key: 'charisma', label: 'CHA' },
              ].map(({ key, label }) => {
                const score = abilityScores[key as keyof typeof abilityScores]
                const mod = getModifier(score)
                return (
                  <div key={key} className="bg-dungeon-700 rounded-lg p-3 text-center">
                    <div className="text-parchment-400 text-sm">{label}</div>
                    <div className="text-2xl text-parchment-100 font-bold">{score}</div>
                    <div className="text-parchment-500 text-sm">{formatMod(mod)}</div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-parchment-400">No ability scores recorded</p>
          )}
        </div>

        {/* Equipment */}
        <div className="card">
          <h2 className="font-display text-xl text-parchment-100 mb-4">Equipment</h2>
          {character.attributes.equipment && character.attributes.equipment.length > 0 ? (
            <ul className="space-y-2">
              {character.attributes.equipment.map((item, i) => (
                <li key={i} className="text-parchment-300 flex items-center">
                  <span className="w-2 h-2 bg-parchment-500 rounded-full mr-2" />
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-parchment-400">No equipment</p>
          )}
        </div>
      </div>
    </div>
  )
}
