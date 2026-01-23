import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Map, Play, BookOpen, User, Scroll, Trash2, MapPin, Users, Swords } from 'lucide-react'
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
      console.log('Creating campaign with data:', data)
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
      console.log('Campaign created successfully')
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
    <div className="relative lg:pl-[20%]">
      {/* Decorative side image with fade */}
      <div
        className="fixed left-0 top-0 w-1/3 h-full pointer-events-none z-0 hidden lg:block"
        style={{
          backgroundImage: 'url(/img/windingroad.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center right',
          maskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
        }}
      />

      <div className="flex items-center justify-between mb-8">
        <h1 className="font-display text-4xl text-parchment-100">Campaigns</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary flex items-center space-x-2"
        >
          <Plus className="w-5 h-5" />
          <span>New Campaign</span>
        </button>
      </div>

      {isLoading ? (
        <div className="text-center text-parchment-400 py-12">
          Loading campaigns...
        </div>
      ) : campaigns?.length === 0 ? (
        <div className="card text-center py-12">
          <Map className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
          <h2 className="font-display text-2xl text-parchment-100 mb-2">No Campaigns Yet</h2>
          <p className="text-parchment-400 mb-6">
            Create your first campaign to start adventuring
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary inline-flex items-center space-x-2"
          >
            <Plus className="w-5 h-5" />
            <span>New Campaign</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {campaigns?.map((campaign) => {
            const adventureModule = getAdventureModule(campaign.adventure_document_id)
            return (
              <div key={campaign.id} className="card overflow-hidden">
                {/* Cover Image */}
                {campaign.adventure_document_id && (
                  <div className="relative -mx-6 -mt-6 mb-4 h-32 bg-dungeon-900">
                    <img
                      src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${campaign.adventure_document_id}/cover`}
                      alt="Module cover"
                      className="w-full h-full object-cover opacity-60"
                      onError={(e) => {
                        // Hide if no cover available
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-dungeon-800 to-transparent" />
                  </div>
                )}
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-display text-xl text-parchment-100">{campaign.name}</h3>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-1 rounded ${
                        campaign.status === 'active'
                          ? 'bg-green-900 text-green-300'
                          : 'bg-dungeon-700 text-parchment-400'
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
                      className="p-1 text-parchment-500 hover:text-red-400 transition-colors"
                      title="Delete campaign"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <p className="text-parchment-500 text-xs mb-3">{getSystemName(campaign.rpg_system_id)}</p>

                {campaign.settings?.character_id && (
                  <div className="flex items-center text-parchment-300 text-sm mb-1">
                    <User className="w-4 h-4 mr-2 text-parchment-500" />
                    {getCharacterDisplay(campaign.settings.character_id)}
                  </div>
                )}

                {campaign.adventure_document_id && (
                  <div className="flex items-center text-parchment-300 text-sm mb-1">
                    <Scroll className="w-4 h-4 mr-2 text-parchment-500" />
                    {getAdventureName(campaign.adventure_document_id)}
                  </div>
                )}

                {/* Parsed adventure module stats */}
                {adventureModule && adventureModule.parsing_status === 'completed' && (
                  <div className="mt-2 p-2 bg-dungeon-900 rounded border border-dungeon-700">
                    <div className="text-parchment-400 text-xs mb-1">Parsed Module Data:</div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="flex items-center text-parchment-300">
                        <MapPin className="w-3 h-3 mr-1 text-purple-400" />
                        {adventureModule.location_count} locations
                      </div>
                      <div className="flex items-center text-parchment-300">
                        <Users className="w-3 h-3 mr-1 text-blue-400" />
                        {adventureModule.npc_count} NPCs
                      </div>
                      <div className="flex items-center text-parchment-300">
                        <Swords className="w-3 h-3 mr-1 text-red-400" />
                        {adventureModule.encounter_count} encounters
                      </div>
                    </div>
                  </div>
                )}

                {campaign.description && (
                  <p className="text-parchment-400 text-sm mt-3 mb-4">
                    {campaign.description}
                  </p>
                )}

                <div className="flex justify-end mt-4">
                  <Link
                    to={`/play/${campaign.settings?.character_id || ''}/${campaign.id}`}
                    className="btn btn-primary btn-sm flex items-center space-x-1"
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

  // Debug: log what we're working with
  console.log('Selected systemId:', systemId)
  console.log('All sourcebooks:', sourcebooks.length, sourcebooks.map(s => ({ id: s.id, sys: s.rpg_system_id, cat: s.category })))

  // Filter by selected system
  const systemCharacters = characters.filter((c) => c.rpg_system_id === systemId)
  const systemSourcebooks = sourcebooks.filter((s) => s.rpg_system_id === systemId)
  const systemAdventures = systemSourcebooks.filter((s) => s.category === 'adventure')
  const systemRules = systemSourcebooks.filter((s) => s.category === 'rules' || s.category === 'supplement')
  const uncategorizedCount = systemSourcebooks.filter((s) => !s.category).length

  console.log('Filtered systemSourcebooks:', systemSourcebooks.length, 'adventures:', systemAdventures.length)

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
      <div className="card w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <h2 className="font-display text-2xl text-parchment-100 mb-6">New Campaign</h2>

        {/* Campaign Name */}
        <div className="mb-4">
          <label className="label block mb-2">Campaign Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="The Lost Temple of Moldvay"
            className="input w-full"
          />
        </div>

        {/* RPG System */}
        <div className="mb-4">
          <label className="label block mb-2">Game System</label>
          <select
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
            className="input w-full"
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
          <label className="label block mb-2 flex items-center">
            <User className="w-4 h-4 mr-2" />
            Character
          </label>
          {systemCharacters.length === 0 ? (
            <p className="text-parchment-500 text-sm">
              No characters for this system. <Link to="/characters/create" className="text-parchment-300 underline">Create one</Link>
            </p>
          ) : (
            <select
              value={characterId}
              onChange={(e) => setCharacterId(e.target.value)}
              className="input w-full"
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
          <label className="label block mb-2 flex items-center">
            <Scroll className="w-4 h-4 mr-2" />
            Adventure Module (optional)
          </label>
          {systemAdventures.length === 0 ? (
            <p className="text-parchment-500 text-sm">
              No adventures for this system.
              {uncategorizedCount > 0 ? (
                <> You have {uncategorizedCount} uncategorized sourcebook(s). <Link to="/sourcebooks" className="text-parchment-300 underline">Set their category</Link> to "Adventure"</>
              ) : (
                <> <Link to="/sourcebooks" className="text-parchment-300 underline">Upload one</Link> and set its category to "Adventure"</>
              )}
            </p>
          ) : (
            <select
              value={adventureId}
              onChange={(e) => setAdventureId(e.target.value)}
              className="input w-full"
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
          <label className="label block mb-2 flex items-center">
            <BookOpen className="w-4 h-4 mr-2" />
            Rulebooks & Supplements (optional)
          </label>
          {systemRules.length === 0 ? (
            <p className="text-parchment-500 text-sm">
              No rulebooks for this system.
              {uncategorizedCount > 0 && (
                <> Set sourcebook categories on the <Link to="/sourcebooks" className="text-parchment-300 underline">Sourcebooks page</Link></>
              )}
            </p>
          ) : (
            <div className="space-y-2 max-h-40 overflow-y-auto border border-dungeon-600 rounded p-2">
              {systemRules.map((sb) => (
                <label
                  key={sb.id}
                  className="flex items-center space-x-2 text-parchment-200 text-sm cursor-pointer hover:bg-dungeon-700 p-1 rounded"
                >
                  <input
                    type="checkbox"
                    checked={selectedSourcebookIds.includes(sb.id)}
                    onChange={() => toggleSourcebook(sb.id)}
                    className="rounded border-dungeon-600"
                  />
                  <span>{sb.title || sb.original_filename}</span>
                  <span className="text-parchment-500 text-xs">({sb.category})</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Description */}
        <div className="mb-4">
          <label className="label block mb-2">Description (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A classic dungeon crawl..."
            className="input w-full h-20 resize-none"
          />
        </div>

        {/* Debug info */}
        <p className="text-parchment-600 text-xs mb-4">
          Sourcebooks for this system: {systemSourcebooks.length} total ({systemAdventures.length} adventures, {systemRules.length} rules/supplements, {uncategorizedCount} uncategorized)
        </p>

        {!canCreate && (
          <p className="text-yellow-500 text-sm mb-4">
            Required: {!name && 'Campaign name, '}{!characterId && 'Character'}
          </p>
        )}

        <div className="flex justify-end space-x-2">
          <button onClick={onClose} className="btn btn-secondary">
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
            className="btn btn-primary"
          >
            {isLoading ? 'Creating...' : 'Create Campaign'}
          </button>
        </div>
      </div>
    </div>
  )
}
