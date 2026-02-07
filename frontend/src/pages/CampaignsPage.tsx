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

export function CampaignsPage() {
  const [showCreateModal, setShowCreateModal] = useState(false)
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
      // Fetch adventure module for each adventure sourcebook
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

  // Helper to get display names
  const getSystemName = (id: string) => systems?.find((s) => s.id === id)?.name || 'Unknown'
  const getCharacter = (id?: string) => id ? characters?.find((c) => c.id === id) : null
  const getCharacterDisplay = (id?: string) => {
    const char = getCharacter(id)
    if (!char) return null
    return `${char.name} - Level ${char.level} ${char.class_name}`
  }
  const getAdventureName = (id?: string) => {
    if (!id) return null
    const sb = sourcebooks?.find((s) => s.id === id)
    return sb?.title || sb?.original_filename || 'Unknown'
  }
  const getAdventureModule = (documentId?: string) => {
    if (!documentId) return null
    return adventureModules?.find((m) => m.pdf_document_id === documentId)
  }

  return (
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
      <div className="max-w-2xl mx-auto lg:mx-0">
        <div className="mb-8">
          <h1 className="font-['Cinzel',serif] text-4xl text-[#d4b870] mb-2">Adventures</h1>
          <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif] mb-6">
            Each adventure represents a single expedition into danger. Time passes. Consequences persist.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-6 py-2 rounded transition-colors"
          >
            Begin New Adventure
          </button>
        </div>

      {isLoading ? (
        <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
          Loading campaigns...
        </div>
      ) : campaigns?.length === 0 ? (
        <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
          <Map className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
          <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">No adventure is currently underway.</h2>
          <p className="text-[#8a8270] mb-6 font-['Crimson_Text',serif]">
            When you are ready, begin one.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded transition-colors"
          >
            Begin an Adventure
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {campaigns?.map((campaign) => {
            const adventureModule = getAdventureModule(campaign.adventure_document_id)
            return (
              <div key={campaign.id} className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 overflow-hidden">
                {/* Cover Image */}
                {campaign.adventure_document_id && (
                  <div className="relative -mx-6 -mt-6 mb-4 h-32 bg-[#0f0d0a]">
                    <img
                      src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${campaign.adventure_document_id}/cover`}
                      alt="Module cover"
                      className="w-full h-full object-cover opacity-60"
                      onError={(e) => {
                        // Hide if no cover available
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#141210] to-transparent" />
                  </div>
                )}
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-['Cinzel',serif] text-xl text-[#d4b870]">{campaign.name}</h3>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-1 rounded font-['Cinzel',serif] ${
                        campaign.status === 'active'
                          ? 'bg-green-900/50 text-green-400'
                          : 'bg-[rgba(255,245,220,0.03)] text-[#8a8270]'
                      }`}
                    >
                      {campaign.status}
                    </span>
                    <button
                      onClick={() => {
                        if (confirm(`Delete campaign "${campaign.name}"?`)) {
                          deleteMutation.mutate(campaign.id)
                        }
                      }}
                      className="p-1 text-[#6a6250] hover:text-red-400 transition-colors"
                      title="Delete campaign"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <p className="text-[#6a6250] text-xs mb-3 font-['Crimson_Text',serif]">{getSystemName(campaign.rpg_system_id)}</p>

                {campaign.settings?.character_id && (
                  <div className="flex items-center text-[#c8c0aa] text-sm mb-1 font-['Crimson_Text',serif]">
                    <User className="w-4 h-4 mr-2 text-[#b8a060]" />
                    {getCharacterDisplay(campaign.settings.character_id)}
                  </div>
                )}

                {campaign.adventure_document_id && (
                  <div className="flex items-center text-[#c8c0aa] text-sm mb-1 font-['Crimson_Text',serif]">
                    <Scroll className="w-4 h-4 mr-2 text-[#b8a060]" />
                    {getAdventureName(campaign.adventure_document_id)}
                  </div>
                )}

                {/* Parsed adventure module stats */}
                {adventureModule && adventureModule.parsing_status === 'completed' && (
                  <div className="mt-2 p-2 bg-[#0f0d0a] rounded border border-[rgba(180,160,100,0.1)]">
                    <div className="grid grid-cols-3 gap-2 text-xs font-['IBM_Plex_Mono',monospace]">
                      <div className="flex items-center text-[#8a8270]">
                        <MapPin className="w-3 h-3 mr-1 text-[#b8a060]" />
                        {adventureModule.location_count} loc
                      </div>
                      <div className="flex items-center text-[#8a8270]">
                        <Users className="w-3 h-3 mr-1 text-[#b8a060]" />
                        {adventureModule.npc_count} NPCs
                      </div>
                      <div className="flex items-center text-[#8a8270]">
                        <Swords className="w-3 h-3 mr-1 text-[#b8a060]" />
                        {adventureModule.encounter_count} enc
                      </div>
                    </div>
                  </div>
                )}

                {campaign.description && (
                  <p className="text-[#8a8270] text-sm mt-3 mb-4 font-['Crimson_Text',serif]">
                    {campaign.description}
                  </p>
                )}

                <div className="flex justify-end mt-4">
                  <Link
                    to={`/play/${campaign.settings?.character_id || ''}/${campaign.id}`}
                    className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] text-sm px-3 py-1.5 rounded flex items-center space-x-1 transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    <span>Play</span>
                  </Link>
                </div>
              </div>
            )
          })}
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

  // Initialize systemId when systems are available
  useEffect(() => {
    if (systems.length > 0 && !systemId) {
      const defaultSystem = systems.find((s) => s.code === 'bx-dnd') || systems[0]
      setSystemId(defaultSystem.id)
    }
  }, [systems, systemId])

  // Filter by selected system
  const systemCharacters = characters.filter((c) => c.rpg_system_id === systemId)
  const systemSourcebooks = sourcebooks.filter((s) => s.rpg_system_id === systemId)
  const systemAdventures = systemSourcebooks.filter((s) => s.category === 'adventure')
  const systemRules = systemSourcebooks.filter((s) => s.category === 'rules' || s.category === 'supplement')
  const uncategorizedCount = systemSourcebooks.filter((s) => !s.category).length

  // Reset selections when system changes
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

  // Adventure is optional - can run without a published module
  const canCreate = name && systemId && characterId

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-6">New Adventure</h2>

        {/* Campaign Name */}
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

        {/* RPG System */}
        <div className="mb-4">
          <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-2">Game System</label>
          <select
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
            className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
          >
            {systems.map((sys) => (
              <option key={sys.id} value={sys.id}>
                {sys.name}
              </option>
            ))}
          </select>
        </div>

        {/* Character Selection */}
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

        {/* Adventure Selection */}
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
                <option key={adv.id} value={adv.id}>
                  {adv.title || adv.original_filename}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Sourcebooks/Rules Selection */}
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

        {/* Description */}
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
