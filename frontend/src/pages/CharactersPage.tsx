import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { User, Skull, Trash2, Shield, Swords } from 'lucide-react'
import { api, ApiError } from '@/services/api'
import { getItemDisplayName } from '@/game-systems/bx-dnd/data/equipment'

interface Character {
  id: string
  name: string
  level: number
  status: string
  current_hp: number
  max_hp: number
  portrait_url?: string
  attributes: {
    character_class?: string
    race?: string
    alignment?: string
    armor_class?: number
    thac0?: number
    ability_scores?: {
      strength: number
      intelligence: number
      wisdom: number
      dexterity: number
      constitution: number
      charisma: number
    }
    equipment?: (string | { name: string; quantity?: number })[]
    gold?: number
  }
  created_at?: string
}

/* ─── COMPONENTS ─── */

const StatBadge = ({ icon, value, label, color }: { icon: React.ReactNode; value: number | string; label: string; color: string }) => (
  <div
    className="flex items-center gap-1.5 px-2.5 py-1 rounded"
    style={{
      background: `${color}10`,
      border: `1px solid ${color}20`,
    }}
  >
    <span className="text-xs" style={{ color }}>{icon}</span>
    <span className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold" style={{ color }}>{value}</span>
    <span className="font-['Crimson_Text',serif] text-[11px] text-[#6a6250]">{label}</span>
  </div>
)

const CharacterCard = ({
  character,
  onDelete,
  isDeleting,
  index,
}: {
  character: Character
  onDelete: () => void
  isDeleting: boolean
  index: number
}) => {
  const [menuOpen, setMenuOpen] = useState(false)
  const isDead = character.status === 'dead'
  const hpPct = character.max_hp > 0 ? (character.current_hp / character.max_hp) * 100 : 0
  const hpColor = hpPct <= 25 ? '#c44' : hpPct <= 50 ? '#c90' : '#5a8a5a'

  // Generate a hue from character name for avatar background
  const avatarHue = character.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360

  // Get first 3 equipment items for preview
  const equipmentPreview = (character.attributes.equipment || []).slice(0, 3).map(item => {
    const name = typeof item === 'string' ? item : item.name
    return getItemDisplayName(name)
  })

  return (
    <div
      className={`bg-[#141210] rounded-lg overflow-hidden flex flex-col transition-all duration-300 hover:border-[rgba(180,160,100,0.2)] hover:-translate-y-0.5 ${isDead ? 'opacity-60' : ''}`}
      style={{
        border: '1px solid rgba(180,160,100,0.1)',
        animation: `cardIn 0.4s ease ${index * 0.08}s both`,
      }}
    >
      {/* Avatar/Cover Area */}
      <div
        className="h-44 relative flex-shrink-0 flex items-center justify-center overflow-hidden"
        style={{
          background: `linear-gradient(160deg, hsl(${avatarHue}, 20%, 15%) 0%, hsl(${avatarHue}, 15%, 8%) 100%)`,
        }}
      >
        {/* Portrait or Character initial */}
        {character.portrait_url ? (
          <img
            src={character.portrait_url}
            alt={character.name}
            className="absolute inset-0 w-full h-full object-cover object-top"
            style={{ opacity: isDead ? 0.5 : 1 }}
          />
        ) : (
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{
              background: `hsl(${avatarHue}, 25%, 12%)`,
              border: `2px solid hsl(${avatarHue}, 30%, 25%)`,
            }}
          >
            {isDead ? (
              <Skull className="w-8 h-8 text-red-500" />
            ) : (
              <span className="font-['Cinzel',serif] text-2xl font-bold" style={{ color: `hsl(${avatarHue}, 40%, 60%)` }}>
                {character.name.charAt(0)}
              </span>
            )}
          </div>
        )}

        {/* Status badge */}
        <div
          className="absolute top-2 right-2 px-2.5 py-1 rounded-full flex items-center gap-1.5"
          style={{
            background: 'rgba(10,9,8,0.8)',
            backdropFilter: 'blur(8px)',
            border: `1px solid ${isDead ? '#c4430' : '#5a8a5a30'}`,
          }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: isDead ? '#c44' : '#5a8a5a', boxShadow: `0 0 6px ${isDead ? '#c4460' : '#5a8a5a60'}` }}
          />
          <span className="font-['IBM_Plex_Mono',monospace] text-[9px] tracking-wide" style={{ color: isDead ? '#c44' : '#5a8a5a' }}>
            {isDead ? 'Dead' : 'Active'}
          </span>
        </div>

        {/* Menu button */}
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen) }}
          className="absolute bottom-2 right-2 w-6 h-6 rounded flex items-center justify-center text-[#6a6250] hover:text-[#c8c0aa] cursor-pointer transition-colors"
          style={{
            background: 'rgba(10,9,8,0.7)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(180,160,100,0.1)',
          }}
        >
          ⋯
        </button>

        {menuOpen && (
          <div className="absolute bottom-10 right-2 z-20 bg-[#1a1816] border border-[rgba(180,160,100,0.2)] rounded-md p-1 min-w-[120px] shadow-xl">
            <button
              onClick={onDelete}
              disabled={isDeleting}
              className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3 h-3" />
              Delete
            </button>
          </div>
        )}

        <div className="absolute inset-0 bg-gradient-to-t from-[#141210] to-transparent pointer-events-none" />
      </div>

      {/* Content */}
      <div className="p-4 flex-1 flex flex-col">
        {/* Name & Class */}
        <Link to={`/characters/${character.id}`} className="hover:text-[#d4b870] transition-colors">
          <h3 className="font-['Cinzel',serif] text-lg font-bold text-[#c8c0aa] mb-0.5 leading-tight">
            {character.name}
          </h3>
        </Link>
        <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250] mb-3">
          Level {character.level} {character.attributes.race || ''} {character.attributes.character_class || 'Adventurer'}
        </div>

        {/* HP Bar */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250] tracking-wide">HP</span>
            <span className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold" style={{ color: hpColor }}>
              {character.current_hp}<span className="opacity-40">/{character.max_hp}</span>
            </span>
          </div>
          <div className="h-1.5 bg-[#0a0908] rounded overflow-hidden">
            <div
              className="h-full rounded transition-all duration-500"
              style={{ width: `${hpPct}%`, background: hpColor }}
            />
          </div>
        </div>

        {/* Stats row */}
        <div className="flex gap-1.5 mb-3 flex-wrap">
          <StatBadge
            icon={<Shield className="w-3 h-3" />}
            value={character.attributes.armor_class ?? 9}
            label="AC"
            color="#7a9ab8"
          />
          <StatBadge
            icon={<Swords className="w-3 h-3" />}
            value={character.attributes.thac0 ?? 19}
            label="THAC0"
            color="#c44"
          />
          {character.attributes.gold !== undefined && character.attributes.gold > 0 && (
            <StatBadge
              icon="💰"
              value={character.attributes.gold}
              label="gp"
              color="#b8a060"
            />
          )}
        </div>

        {/* Equipment preview */}
        {equipmentPreview.length > 0 && (
          <div className="font-['Crimson_Text',serif] text-xs text-[#6a6250] mb-3 line-clamp-1">
            {equipmentPreview.join(' • ')}
            {(character.attributes.equipment?.length || 0) > 3 && ` +${(character.attributes.equipment?.length || 0) - 3} more`}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-2 mt-auto pt-3">
          <Link
            to={`/characters/${character.id}`}
            className="flex-1 text-center py-2 rounded text-sm font-['Cinzel',serif] text-[#c8c0aa] transition-colors"
            style={{
              background: 'rgba(255,245,220,0.03)',
              border: '1px solid rgba(180,160,100,0.1)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,245,220,0.06)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255,245,220,0.03)'
            }}
          >
            View Sheet
          </Link>
          {!isDead && (
            <Link
              to={`/play/${character.id}`}
              className="flex-1 text-center py-2 rounded text-sm font-['Cinzel',serif] font-semibold text-[#f0e8d0] transition-all"
              style={{
                background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                border: '1px solid #b8a060',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'linear-gradient(135deg, #8a7030, #b8a060)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'linear-gradient(135deg, #6a5020, #8a7030)'
              }}
            >
              ▶ Play
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

export function CharactersPage() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('all')

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

  // Filter characters
  const filteredCharacters = filter === 'all'
    ? characters
    : filter === 'active'
    ? characters?.filter(c => c.status !== 'dead')
    : characters?.filter(c => c.status === 'dead')

  const activeCount = characters?.filter(c => c.status !== 'dead').length || 0
  const deadCount = characters?.filter(c => c.status === 'dead').length || 0

  return (
    <>
      <style>{`
        @keyframes cardIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .filter-pill {
          background: none;
          border: 1px solid transparent;
          cursor: pointer;
          font-family: 'Crimson Text', serif;
          font-size: 14px;
          color: #6a6250;
          padding: 5px 14px;
          border-radius: 20px;
          transition: all 0.2s;
        }
        .filter-pill:hover { color: #8a8270; }
        .filter-pill.active {
          color: #b8a060;
          border-color: rgba(180,160,80,0.4);
          background: rgba(180,160,80,0.06);
        }
      `}</style>

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
          <div className="max-w-3xl mx-auto lg:mx-0">
            {/* Hero */}
            <div className="mb-8 flex items-end justify-between">
              <div>
                <h1 className="font-['Cinzel',serif] text-4xl text-[#c8c0aa] tracking-wide mb-2">Characters</h1>
                <p className="font-['Crimson_Text',serif] text-base text-[#6a6250] italic">
                  Your adventurers, past and present. Dead characters remain listed for the sake of the record.
                </p>
              </div>
              <div className="flex gap-1">
                {[
                  { key: 'all', label: 'All' },
                  { key: 'active', label: `Active (${activeCount})` },
                  { key: 'dead', label: `Fallen (${deadCount})` },
                ].map(f => (
                  <button
                    key={f.key}
                    className={`filter-pill ${filter === f.key ? 'active' : ''}`}
                    onClick={() => setFilter(f.key)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Create Character zone */}
            <Link
              to="/characters/create"
              className="block mb-10 p-7 rounded-lg cursor-pointer transition-all flex items-center gap-5 hover:border-[rgba(180,160,100,0.3)]"
              style={{
                border: '2px dashed rgba(180,160,100,0.15)',
                background: 'transparent',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'rgba(180,160,100,0.3)'
                e.currentTarget.style.background = 'rgba(180,160,80,0.02)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'rgba(180,160,100,0.15)'
                e.currentTarget.style.background = 'transparent'
              }}
            >
              <div
                className="w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center"
                style={{
                  background: 'rgba(255,245,220,0.03)',
                  border: '1px solid rgba(180,160,100,0.1)',
                }}
              >
                <User className="w-5 h-5 text-[#6a6250]" />
              </div>
              <div>
                <div className="font-['Crimson_Text',serif] text-base text-[#c8c0aa] mb-0.5">
                  Create New Character
                </div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Roll abilities, choose a class, and equip for adventure.
                </div>
              </div>
            </Link>

            {isLoading ? (
              <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
                Loading characters...
              </div>
            ) : filteredCharacters?.length === 0 ? (
              <div className="text-center py-16">
                <User className="w-12 h-12 text-[#6a6250] mx-auto mb-4 opacity-40" />
                <div className="font-['Cinzel',serif] text-xl text-[#8a8270] mb-2">
                  {filter === 'dead' ? 'No fallen heroes yet.' : filter === 'active' ? 'No active characters.' : 'No characters yet.'}
                </div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Most adventures are unforgiving without a hero.
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {filteredCharacters?.map((character, i) => (
                  <CharacterCard
                    key={character.id}
                    character={character}
                    onDelete={() => handleDelete(character)}
                    isDeleting={deleteMutation.isPending}
                    index={i}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
