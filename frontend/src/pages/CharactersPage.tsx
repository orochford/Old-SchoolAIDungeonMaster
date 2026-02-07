import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { User, Skull, Trash2 } from 'lucide-react'
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
    <div className="min-h-[calc(100vh-8rem)] flex">
      {/* Left atmosphere panel - fixed */}
      <div
        className="hidden lg:block w-[30%] fixed left-0 top-16 bottom-0"
        style={{
          backgroundImage: 'url(/img/tavern.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />
      </div>

      {/* Right content panel */}
      <div className="flex-1 lg:w-[70%] lg:ml-[30%] px-6 lg:px-12 py-12 overflow-y-auto">
      <div className="max-w-2xl mx-auto lg:mx-0">
        <div className="mb-8">
          <h1 className="font-['Cinzel',serif] text-4xl text-[#d4b870] mb-2">Characters</h1>
          <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif] mb-6">
            Your adventurers, past and present. Dead characters remain listed for the sake of the record.
          </p>
          <Link to="/characters/create" className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-6 py-2 rounded transition-colors inline-block">
            Create Character
          </Link>
        </div>

      {isLoading ? (
        <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
          Loading characters...
        </div>
      ) : characters?.length === 0 ? (
        <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
          <User className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
          <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">You have no characters prepared.</h2>
          <p className="text-[#8a8270] mb-6 font-['Crimson_Text',serif]">
            Most adventures are unforgiving without one.
          </p>
          <Link to="/characters/create" className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded transition-colors inline-block">
            Create Character
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
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
      </div>
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
  const hpRatio = character.max_hp > 0 ? character.current_hp / character.max_hp : 0

  return (
    <div className={`group bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 ${isDead ? 'opacity-50' : ''}`}>
      {/* Header with icon, name, delete */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#0f0d0a] rounded">
            {isDead ? (
              <Skull className="w-5 h-5 text-red-500" />
            ) : (
              <User className="w-5 h-5 text-[#b8a060]" />
            )}
          </div>
          <div>
            <Link to={`/characters/${character.id}`} className="hover:text-[#d4b870] transition-colors">
              <h3 className="font-['Cinzel',serif] text-xl text-[#d4b870]">{character.name}</h3>
            </Link>
            <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
              Level {character.level} {character.attributes.character_class || 'Adventurer'}
            </p>
          </div>
        </div>
        <button
          onClick={onDelete}
          disabled={isDeleting}
          className="p-1 text-[#6a6250] opacity-0 group-hover:opacity-100 hover:text-red-500 transition-all disabled:opacity-50"
          title="Delete character"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* HP bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-[#6a6250] font-['Cinzel',serif]">Hit Points</span>
          <span className="text-xs text-[#8a8270] font-['IBM_Plex_Mono',monospace] tabular-nums">
            {character.current_hp}/{character.max_hp}
          </span>
        </div>
        <div className="h-2 bg-[#0f0d0a] rounded-full overflow-hidden border border-[rgba(180,160,100,0.1)]">
          <div
            className={`h-full ${
              hpRatio > 0.5 ? 'bg-green-600' : hpRatio > 0.25 ? 'bg-yellow-600' : 'bg-red-600'
            }`}
            style={{ width: `${hpRatio * 100}%` }}
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Link
          to={`/characters/${character.id}`}
          className="flex-1 text-center bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.06)] font-['Cinzel',serif] text-sm py-2 px-3 rounded transition-colors"
        >
          View Sheet
        </Link>
        {!isDead && (
          <Link to={`/play/${character.id}`} className="flex-1 text-center bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] text-sm py-2 px-3 rounded transition-colors">
            Play
          </Link>
        )}
      </div>
    </div>
  )
}
