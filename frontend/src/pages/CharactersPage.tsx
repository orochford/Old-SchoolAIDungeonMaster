import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, User, Skull, Star, Trash2 } from 'lucide-react'
import { api, ApiError } from '@/services/api'

interface Character {
  id: string
  name: string
  level: number
  status: string
  current_hp: number
  max_hp: number
  attributes: {
    character_class?: string
    ability_scores?: {
      strength: number
      intelligence: number
      wisdom: number
      dexterity: number
      constitution: number
      charisma: number
    }
  }
}

export function CharactersPage() {
  const queryClient = useQueryClient()

  const { data: characters, isLoading } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  const deleteMutation = useMutation({
    mutationFn: ({ characterId, cascade }: { characterId: string; cascade: boolean }) =>
      api.delete(`/characters/${characterId}?cascade=${cascade}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
    onError: async (error: Error, variables) => {
      // Check if it's a 409 conflict (has related items)
      if (error instanceof ApiError && error.response.status === 409) {
        const detail = error.response.data?.detail
        const relatedSessions = detail?.related_sessions || 0
        const relatedCampaigns = detail?.related_campaigns || 0

        const shouldCascade = confirm(
          `This character has ${relatedSessions} session(s) and ${relatedCampaigns} campaign(s) associated with it.\n\n` +
          `Do you want to delete the character AND all related campaigns and sessions?\n\n` +
          `This cannot be undone.`
        )

        if (shouldCascade) {
          deleteMutation.mutate({ characterId: variables.characterId, cascade: true })
        }
      }
    },
  })

  const handleDelete = (character: Character) => {
    if (confirm(`Are you sure you want to delete ${character.name}? This cannot be undone.`)) {
      deleteMutation.mutate({ characterId: character.id, cascade: false })
    }
  }

  return (
    <div className="relative lg:pl-[20%]">
      {/* Decorative side image with fade */}
      <div
        className="fixed left-0 top-0 w-1/3 h-full pointer-events-none z-0 hidden lg:block"
        style={{
          backgroundImage: 'url(/img/tavern.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center right',
          maskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
        }}
      />

      <div className="flex items-center justify-between mb-8">
        <h1 className="font-display text-4xl text-parchment-100">Characters</h1>
        <Link to="/characters/create" className="btn btn-primary flex items-center space-x-2">
          <Plus className="w-5 h-5" />
          <span>Create Character</span>
        </Link>
      </div>

      {isLoading ? (
        <div className="text-center text-parchment-400 py-12">
          Loading characters...
        </div>
      ) : characters?.length === 0 ? (
        <div className="card text-center py-12">
          <User className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
          <h2 className="font-display text-2xl text-parchment-100 mb-2">No Characters Yet</h2>
          <p className="text-parchment-400 mb-6">
            Create your first character to begin your adventure
          </p>
          <Link to="/characters/create" className="btn btn-primary inline-flex items-center space-x-2">
            <Plus className="w-5 h-5" />
            <span>Create Character</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {characters?.map((character) => (
            <CharacterCard
              key={character.id}
              character={character}
              onDelete={() => handleDelete(character)}
              isDeleting={deleteMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function CharacterCard({
  character,
  onDelete,
  isDeleting,
}: {
  character: Character
  onDelete: () => void
  isDeleting: boolean
}) {
  const isDead = character.status === 'dead'

  return (
    <div className={`card ${isDead ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-display text-xl text-parchment-100">{character.name}</h3>
          <p className="text-parchment-400">
            Level {character.level} {character.attributes.character_class || 'Adventurer'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isDead ? (
            <Skull className="w-6 h-6 text-red-500" />
          ) : (
            <Star className="w-6 h-6 text-parchment-500" />
          )}
          <button
            onClick={onDelete}
            disabled={isDeleting}
            className="p-1 text-parchment-500 hover:text-red-500 transition-colors disabled:opacity-50"
            title="Delete character"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex justify-between text-sm text-parchment-400 mb-1">
          <span>HP</span>
          <span>{character.current_hp} / {character.max_hp}</span>
        </div>
        <div className="h-2 bg-dungeon-700 rounded-full overflow-hidden">
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

      {character.attributes.ability_scores && (
        <div className="grid grid-cols-6 gap-2 text-center text-sm">
          <div>
            <div className="text-parchment-400">STR</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.strength}</div>
          </div>
          <div>
            <div className="text-parchment-400">INT</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.intelligence}</div>
          </div>
          <div>
            <div className="text-parchment-400">WIS</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.wisdom}</div>
          </div>
          <div>
            <div className="text-parchment-400">DEX</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.dexterity}</div>
          </div>
          <div>
            <div className="text-parchment-400">CON</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.constitution}</div>
          </div>
          <div>
            <div className="text-parchment-400">CHA</div>
            <div className="text-parchment-100">{character.attributes.ability_scores.charisma}</div>
          </div>
        </div>
      )}

      <div className="mt-4 flex space-x-2">
        <Link
          to={`/characters/${character.id}`}
          className="btn btn-secondary flex-1 text-center"
        >
          View
        </Link>
        {!isDead && (
          <Link to={`/play/${character.id}`} className="btn btn-primary flex-1 text-center">
            Play
          </Link>
        )}
      </div>
    </div>
  )
}
