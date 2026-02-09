import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Map, Play, BookOpen, User, Scroll, Trash2, MapPin, Users, Swords } from 'lucide-react'
import { api, ApiError } from '@/services/api'

interface Campaign {
  id: string
  name: string
  description: string
  status: string
  rpg_system_id: string
  adventure_document_id?: string
  settings: {
    character_id?: string
    sourcebook_ids?: string[]
  }
  created_at: string
}

interface RPGSystem {
  id: string
  name: string
  code: string
}

interface Character {
  id: string
  name: string
  rpg_system_id: string
  class_name: string
  level: number
  current_hp?: number
  max_hp?: number
  race?: string
}

interface Sourcebook {
  id: string
  title: string | null
  original_filename: string
  category: 'rules' | 'adventure' | 'supplement' | null
  rpg_system_id: string
  status: string
}

interface AdventureModule {
  id: string
  pdf_document_id: string
  title: string
  code: string | null
  parsing_status: 'pending' | 'processing' | 'completed' | 'failed'
  location_count: number
  npc_count: number
  encounter_count: number
  item_count: number
}

/* ─── COMPONENTS ─── */

const CharacterMini = ({ character }: { character: Character }) => {
  const hp = character.current_hp ?? character.max_hp ?? 10
  const maxHp = character.max_hp ?? 10
  const hpPct = (hp / maxHp) * 100
  const hpColor = hpPct <= 25 ? '#c44' : hpPct <= 50 ? '#c90' : '#5a8a5a'

  return (
    <div className="flex items-center gap-3">
      {/* Character initial */}
      <div className="w-10 h-10 rounded flex-shrink-0 bg-[#0a0908] border border-[rgba(180,160,100,0.1)] flex items-center justify-center font-['Cinzel',serif] text-lg font-bold text-[rgba(180,160,80,0.4)]">
        {character.name.charAt(0)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-['Cinzel',serif] text-sm font-semibold text-[#c8c0aa] truncate">
          {character.name}
        </div>
        <div className="font-['Crimson_Text',serif] text-xs text-[#6a6250]">
          Lv.{character.level} {character.race || ''} {character.class_name}
        </div>
      </div>
      {/* HP mini */}
      <div className="text-right flex-shrink-0">
        <div className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold" style={{ color: hpColor }}>
          {hp}<span className="opacity-40 font-normal">/{maxHp}</span>
        </div>
        <div className="w-10 h-1 bg-[#0a0908] rounded mt-1 overflow-hidden">
          <div
            className="h-full rounded transition-all duration-400"
            style={{ width: `${hpPct}%`, background: hpColor }}
          />
        </div>
      </div>
    </div>
  )
}

const StatChip = ({ icon, value, label }: { icon: string; value: number | string; label: string }) => (
  <div className="text-center flex-1">
    <div className="text-xs mb-1">{icon}</div>
    <div className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold text-[#c8c0aa] leading-none">{value}</div>
    <div className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#6a6250] mt-1 tracking-wide">{label}</div>
  </div>
)

const FakeCover = ({ hue, title }: { hue: number; title: string }) => (
  <div
    className="w-full h-full relative overflow-hidden"
    style={{ background: `linear-gradient(160deg, hsl(${hue}, 28%, 16%) 0%, hsl(${hue}, 18%, 8%) 100%)` }}
  >
    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/60" />
    {/* Decorative geometry */}
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 rounded-full"
      style={{ border: `1px solid hsla(${hue}, 30%, 50%, 0.1)` }}
    />
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rotate-45 w-10 h-10"
      style={{ border: `1px solid hsla(${hue}, 30%, 50%, 0.07)` }}
    />
    {/* Module label */}
    <div className="absolute top-3 left-3 font-['IBM_Plex_Mono',monospace] text-[9px] tracking-wider uppercase" style={{ color: `hsla(${hue}, 40%, 65%, 0.5)` }}>
      Dungeon Module
    </div>
    {/* Title */}
    <div className="absolute bottom-3 left-3 right-3 font-['Cinzel',serif] text-sm font-semibold text-white/60 leading-tight">
      {title}
    </div>
  </div>
)

const AdventureCard = ({
  campaign,
  character,
  adventureModule,
  adventureName,
  onDelete,
  index,
}: {
  campaign: Campaign
  character: Character | null
  adventureModule: AdventureModule | null
  adventureName: string | null
  onDelete: () => void
  index: number
}) => {
  const [hovered, setHovered] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)

  const statusConfig: Record<string, { label: string; color: string }> = {
    active: { label: 'Active', color: '#5a8a5a' },
    completed: { label: 'Completed', color: '#b8a060' },
    abandoned: { label: 'Dead', color: '#c44' },
  }
  const st = statusConfig[campaign.status] || statusConfig.active

  // Generate a hue from the campaign name for the fake cover
  const coverHue = campaign.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setMenuOpen(false) }}
      className="bg-[#141210] rounded-lg overflow-hidden flex flex-col transition-all duration-300"
      style={{
        border: `1px solid ${hovered ? 'rgba(180,160,100,0.2)' : 'rgba(180,160,100,0.1)'}`,
        transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
        boxShadow: hovered ? '0 12px 40px rgba(0,0,0,0.35), 0 0 0 1px rgba(180,160,100,0.05)' : 'none',
        animation: `cardIn 0.45s ease ${index * 0.1}s both`,
      }}
    >
      {/* Cover area */}
      <div className="h-44 relative flex-shrink-0 bg-[#0a0908]">
        {campaign.adventure_document_id && !imgFailed ? (
          <img
            src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${campaign.adventure_document_id}/cover`}
            alt="Module cover"
            className="w-full h-full object-contain"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <FakeCover hue={coverHue} title={adventureName || campaign.name} />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[#141210] to-transparent pointer-events-none" />

        {/* Status badge */}
        <div
          className="absolute top-2.5 right-2.5 flex items-center gap-1.5 px-2.5 py-1 rounded-xl backdrop-blur-sm"
          style={{
            background: 'rgba(10,9,8,0.8)',
            border: `1px solid ${st.color}30`,
          }}
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: st.color, boxShadow: `0 0 6px ${st.color}60` }}
          />
          <span className="font-['IBM_Plex_Mono',monospace] text-[9px] tracking-wide" style={{ color: st.color }}>
            {st.label}
          </span>
        </div>

        {/* Menu button */}
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen) }}
          className="absolute bottom-2 right-2 w-6 h-6 rounded flex items-center justify-center text-[#6a6250] cursor-pointer transition-opacity backdrop-blur-sm"
          style={{
            background: 'rgba(10,9,8,0.65)',
            border: '1px solid rgba(180,160,100,0.1)',
            opacity: hovered ? 1 : 0,
          }}
        >
          ⋯
        </button>

        {menuOpen && (
          <div className="absolute bottom-10 right-2 z-20 bg-[#1a1816] border border-[rgba(180,160,100,0.2)] rounded-md p-1 min-w-[120px] shadow-xl">
            <button
              onClick={onDelete}
              className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-red-400 hover:bg-red-400/10 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Delete
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 flex-1 flex flex-col">
        <h3 className="font-['Cinzel',serif] text-lg font-bold text-[#c8c0aa] mb-0.5 leading-tight">
          {campaign.name}
        </h3>
        {adventureName && (
          <div className="font-['Crimson_Text',serif] text-xs text-[#6a6250] italic mb-3">
            {adventureName}
          </div>
        )}

        {/* Character bar */}
        {character && (
          <div className="p-2.5 rounded-md bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] mb-3">
            <CharacterMini character={character} />
          </div>
        )}

        {/* Module stats */}
        {adventureModule && adventureModule.parsing_status === 'completed' && (
          <div className="flex gap-1 py-2.5 border-t border-[rgba(180,160,100,0.1)] mb-3">
            <StatChip icon="📍" value={adventureModule.location_count} label="locations" />
            <StatChip icon="👥" value={adventureModule.npc_count} label="NPCs" />
            <StatChip icon="⚔" value={adventureModule.encounter_count} label="encounters" />
          </div>
        )}

        {campaign.description && (
          <p className="font-['Crimson_Text',serif] text-sm italic text-[#8a8270] leading-relaxed mb-4 flex-1 line-clamp-2">
            "{campaign.description}"
          </p>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between mt-auto pt-3">
          <div className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250]">
            {new Date(campaign.created_at).toLocaleDateString()}
          </div>
          <div className="flex items-center gap-2">
            {adventureModule && adventureModule.parsing_status === 'completed' && (
              <Link
                to={`/adventures/${adventureModule.id}/graph`}
                className="px-3 py-2 rounded-md cursor-pointer font-['Cinzel',serif] text-xs font-semibold tracking-wide text-[#6a6250] hover:text-[#b8a060] transition-all flex items-center gap-1.5"
                style={{
                  border: '1px solid rgba(180,160,100,0.15)',
                  background: 'rgba(255,245,220,0.02)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(180,160,100,0.3)'
                  e.currentTarget.style.background = 'rgba(180,160,80,0.06)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(180,160,100,0.15)'
                  e.currentTarget.style.background = 'rgba(255,245,220,0.02)'
                }}
              >
                <Map className="w-3.5 h-3.5" />
                Map
              </Link>
            )}
            {campaign.status === 'active' ? (
              <Link
                to={`/play/${campaign.settings?.character_id || ''}/${campaign.id}`}
                className="px-5 py-2 rounded-md cursor-pointer font-['Cinzel',serif] text-xs font-semibold tracking-wide text-[#f0e8d0] transition-all"
                style={{
                  background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                  border: '1px solid #b8a060',
                  boxShadow: '0 2px 12px rgba(180,160,80,0.15)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #8a7030, #b8a060)'
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(180,160,80,0.3)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #6a5020, #8a7030)'
                  e.currentTarget.style.boxShadow = '0 2px 12px rgba(180,160,80,0.15)'
                }}
              >
                ▶ Continue
              </Link>
            ) : (
              <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#c44] opacity-60">
                ☠ Adventure ended
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function CampaignsPage() {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [filter, setFilter] = useState('all')
  const queryClient = useQueryClient()

  // Fetch RPG systems
  const { data: systems } = useQuery({
    queryKey: ['rpg-systems'],
    queryFn: () => api.get<RPGSystem[]>('/campaigns/systems'),
  })

  // Fetch characters
  const { data: characters } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  // Fetch sourcebooks
  const { data: sourcebooks } = useQuery({
    queryKey: ['sourcebooks'],
    queryFn: () => api.get<Sourcebook[]>('/sourcebooks'),
  })

  const { data: campaigns, isLoading } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  // Fetch adventure modules for stats display
  const { data: adventureModules } = useQuery({
    queryKey: ['adventure-modules-all'],
    queryFn: async () => {
      const adventures = sourcebooks?.filter(s => s.category === 'adventure') || []
      const modules: AdventureModule[] = []
      for (const adv of adventures) {
        try {
          const module = await api.get<AdventureModule>(`/adventures/by-document/${adv.id}`)
          modules.push(module)
        } catch {
          // Module not parsed yet
        }
      }
      return modules
    },
    enabled: !!sourcebooks,
  })

  const deleteMutation = useMutation({
    mutationFn: (campaignId: string) => api.delete(`/campaigns/${campaignId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
    },
    onError: (error: Error) => {
      const message = error instanceof ApiError
        ? error.response.data?.detail || error.message
        : error.message
      alert(`Failed to delete campaign: ${message}`)
    },
  })

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string
      description: string
      rpg_system_id: string
      character_id: string
      adventure_document_id: string
      sourcebook_ids: string[]
    }) => {
      return api.post('/campaigns', {
        name: data.name,
        description: data.description,
        rpg_system_id: data.rpg_system_id,
        adventure_document_id: data.adventure_document_id || null,
        settings: {
          character_id: data.character_id,
          sourcebook_ids: data.sourcebook_ids,
        },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] })
      setShowCreateModal(false)
    },
    onError: (error) => {
      console.error('Failed to create campaign:', error)
      alert('Failed to create campaign: ' + (error as Error).message)
    },
  })

  // Helpers
  const getCharacter = (id?: string) => id ? characters?.find((c) => c.id === id) : null
  const getAdventureName = (id?: string) => {
    if (!id) return null
    const sb = sourcebooks?.find((s) => s.id === id)
    return sb?.title || sb?.original_filename || null
  }
  const getAdventureModule = (documentId?: string) => {
    if (!documentId) return null
    return adventureModules?.find((m) => m.pdf_document_id === documentId)
  }

  // Filter campaigns
  const filteredCampaigns = filter === 'all'
    ? campaigns
    : campaigns?.filter(c => c.status === filter)

  const activeCount = campaigns?.filter(c => c.status === 'active').length || 0
  const completedCount = campaigns?.filter(c => c.status === 'completed').length || 0

  return (
    <>
      <style>{`
        @keyframes cardIn {
          from { opacity: 0; transform: translateY(16px); }
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
            backgroundImage: 'url(/img/windingroad.png)',
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
            <div className="mb-8">
              <h1 className="font-['Cinzel',serif] text-4xl text-[#c8c0aa] tracking-wide mb-2">Adventures</h1>
              <p className="font-['Crimson_Text',serif] text-base text-[#6a6250] italic">
                Each adventure is a single expedition into danger. Time passes. Consequences persist.
              </p>
            </div>

            {/* Begin New Adventure zone */}
            <div
              onClick={() => setShowCreateModal(true)}
              className="mb-10 p-7 rounded-lg cursor-pointer transition-all flex items-center gap-5 hover:border-[rgba(180,160,100,0.3)]"
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
                <span className="text-[#6a6250] text-xl">+</span>
              </div>
              <div>
                <div className="font-['Crimson_Text',serif] text-base text-[#c8c0aa] mb-0.5">
                  Begin New Adventure
                </div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Select a character, choose an adventure module, and start your expedition.
                </div>
              </div>
            </div>

            {/* Filter bar */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex gap-1">
                {[
                  { key: 'all', label: 'All' },
                  { key: 'active', label: `Active (${activeCount})` },
                  { key: 'completed', label: `Completed (${completedCount})` },
                  { key: 'abandoned', label: 'Fallen' },
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
              <span className="font-['IBM_Plex_Mono',monospace] text-xs text-[#6a6250]">
                {filteredCampaigns?.length || 0} adventure{(filteredCampaigns?.length || 0) !== 1 ? 's' : ''}
              </span>
            </div>

            {isLoading ? (
              <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
                Loading adventures...
              </div>
            ) : filteredCampaigns?.length === 0 ? (
              <div className="text-center py-16">
                <div className="text-4xl mb-3 opacity-30">⚔</div>
                <div className="font-['Crimson_Text',serif] text-base text-[#6a6250]">
                  {filter === 'abandoned' ? 'No fallen adventurers yet.' :
                   filter === 'all' ? 'No adventures yet. Begin one above.' :
                   `No ${filter} adventures.`}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {filteredCampaigns?.map((campaign, i) => (
                  <AdventureCard
                    key={campaign.id}
                    campaign={campaign}
                    character={getCharacter(campaign.settings?.character_id) || null}
                    adventureModule={getAdventureModule(campaign.adventure_document_id) || null}
                    adventureName={getAdventureName(campaign.adventure_document_id)}
                    onDelete={() => {
                      if (confirm(`Delete adventure "${campaign.name}"?`)) {
                        deleteMutation.mutate(campaign.id)
                      }
                    }}
                    index={i}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Create Modal */}
          {showCreateModal && (
            <CreateCampaignModal
              onClose={() => setShowCreateModal(false)}
              onCreate={(data) => createMutation.mutate(data)}
              isLoading={createMutation.isPending}
              systems={systems || []}
              characters={characters || []}
              sourcebooks={sourcebooks || []}
            />
          )}
        </div>
      </div>
    </>
  )
}

function CreateCampaignModal({
  onClose,
  onCreate,
  isLoading,
  systems,
  characters,
  sourcebooks,
}: {
  onClose: () => void
  onCreate: (data: {
    name: string
    description: string
    rpg_system_id: string
    character_id: string
    adventure_document_id: string
    sourcebook_ids: string[]
  }) => void
  isLoading: boolean
  systems: RPGSystem[]
  characters: Character[]
  sourcebooks: Sourcebook[]
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemId, setSystemId] = useState('')
  const [characterId, setCharacterId] = useState('')
  const [adventureId, setAdventureId] = useState('')
  const [selectedSourcebookIds, setSelectedSourcebookIds] = useState<string[]>([])

  useEffect(() => {
    if (systems.length > 0 && !systemId) {
      const defaultSystem = systems.find((s) => s.code === 'bx-dnd') || systems[0]
      setSystemId(defaultSystem.id)
    }
  }, [systems, systemId])

  const systemCharacters = characters.filter((c) => c.rpg_system_id === systemId)
  const systemSourcebooks = sourcebooks.filter((s) => s.rpg_system_id === systemId)
  const systemAdventures = systemSourcebooks.filter((s) => s.category === 'adventure')
  const systemRules = systemSourcebooks.filter((s) => s.category === 'rules' || s.category === 'supplement')
  const uncategorizedCount = systemSourcebooks.filter((s) => !s.category).length

  useEffect(() => {
    setCharacterId('')
    setAdventureId('')
    setSelectedSourcebookIds([])
  }, [systemId])

  const toggleSourcebook = (id: string) => {
    setSelectedSourcebookIds((prev) =>
      prev.includes(id) ? prev.filter((sid) => sid !== id) : [...prev, id]
    )
  }

  const canCreate = name && systemId && characterId

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-6">New Adventure</h2>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2">Adventure Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="The Lost Temple of Moldvay"
            className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif] placeholder:text-[#6a6250]"
          />
        </div>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2">Game System</label>
          <select
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
            className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
          >
            {systems.map((sys) => (
              <option key={sys.id} value={sys.id}>{sys.name}</option>
            ))}
          </select>
        </div>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2 flex items-center">
            <User className="w-4 h-4 mr-2 text-[#b8a060]" />
            Character
          </label>
          {systemCharacters.length === 0 ? (
            <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
              No characters for this system. <Link to="/characters/create" className="text-[#b8a060] underline hover:text-[#d4b870]">Create one</Link>
            </p>
          ) : (
            <select
              value={characterId}
              onChange={(e) => setCharacterId(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
            >
              <option value="">Select a character...</option>
              {systemCharacters.map((char) => (
                <option key={char.id} value={char.id}>
                  {char.name} - Level {char.level} {char.class_name}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2 flex items-center">
            <Scroll className="w-4 h-4 mr-2 text-[#b8a060]" />
            Adventure Module (optional)
          </label>
          {systemAdventures.length === 0 ? (
            <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
              No adventures for this system.
              {uncategorizedCount > 0 ? (
                <> You have {uncategorizedCount} uncategorized sourcebook(s). <Link to="/sourcebooks" className="text-[#b8a060] underline hover:text-[#d4b870]">Set their category</Link> to "Adventure"</>
              ) : (
                <> <Link to="/sourcebooks" className="text-[#b8a060] underline hover:text-[#d4b870]">Upload one</Link> and set its category to "Adventure"</>
              )}
            </p>
          ) : (
            <select
              value={adventureId}
              onChange={(e) => setAdventureId(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
            >
              <option value="">Select an adventure...</option>
              {systemAdventures.map((adv) => (
                <option key={adv.id} value={adv.id}>{adv.title || adv.original_filename}</option>
              ))}
            </select>
          )}
        </div>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2 flex items-center">
            <BookOpen className="w-4 h-4 mr-2 text-[#b8a060]" />
            Rulebooks & Supplements (optional)
          </label>
          {systemRules.length === 0 ? (
            <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
              No rulebooks for this system.
              {uncategorizedCount > 0 && (
                <> Set sourcebook categories on the <Link to="/sourcebooks" className="text-[#b8a060] underline hover:text-[#d4b870]">Sourcebooks page</Link></>
              )}
            </p>
          ) : (
            <div className="space-y-2 max-h-40 overflow-y-auto border border-[rgba(180,160,100,0.1)] rounded p-2 bg-[#0f0d0a]">
              {systemRules.map((sb) => (
                <label
                  key={sb.id}
                  className="flex items-center space-x-2 text-[#c8c0aa] text-sm cursor-pointer hover:bg-[rgba(255,245,220,0.03)] p-1 rounded font-['Crimson_Text',serif]"
                >
                  <input
                    type="checkbox"
                    checked={selectedSourcebookIds.includes(sb.id)}
                    onChange={() => toggleSourcebook(sb.id)}
                    className="rounded border-[rgba(180,160,100,0.1)] bg-[#0f0d0a]"
                  />
                  <span>{sb.title || sb.original_filename}</span>
                  <span className="text-[#6a6250] text-xs">({sb.category})</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2">Description (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A classic dungeon crawl..."
            className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif] h-20 resize-none placeholder:text-[#6a6250]"
          />
        </div>

        {!canCreate && (
          <p className="text-[#b8a060] text-sm mb-4 font-['Crimson_Text',serif]">
            Required: {!name && 'Campaign name, '}{!characterId && 'Character'}
          </p>
        )}

        <div className="flex justify-end space-x-2">
          <button onClick={onClose} className="bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.06)] font-['Cinzel',serif] px-4 py-2 rounded transition-colors">
            Cancel
          </button>
          <button
            onClick={() =>
              onCreate({
                name,
                description,
                rpg_system_id: systemId,
                character_id: characterId,
                adventure_document_id: adventureId,
                sourcebook_ids: selectedSourcebookIds,
              })
            }
            disabled={!canCreate || isLoading}
            className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Creating...' : 'Create Campaign'}
          </button>
        </div>
      </div>
    </div>
  )
}
