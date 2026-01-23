import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  BookOpen,
  Trophy,
  MapPin,
  Sword,
  ScrollText,
  Plus,
  ChevronRight,
  Star,
  Clock,
  Skull,
  Package,
  AlertTriangle,
} from 'lucide-react'
import { api } from '@/services/api'

// Types
interface JournalEntry {
  id: string
  session_id: string | null
  campaign_id: string
  character_id: string
  entry_type: string
  title: string
  content: string
  sequence: number
  game_date: string | null
  entry_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface Achievement {
  id: string
  code: string
  name: string
  description: string
  icon: string | null
  rarity: string
  criteria: Record<string, unknown>
}

interface CharacterAchievement {
  id: string
  character_id: string
  achievement_id: string
  session_id: string | null
  context: string | null
  created_at: string
  achievement: Achievement
}

interface WorldLocation {
  id: string
  campaign_id: string
  name: string
  description: string | null
  location_type: string | null
  parent_location_id: string | null
  map_x: number | null
  map_y: number | null
  is_discovered: boolean
  is_cleared: boolean
  visit_count: number
  first_visited_session_id: string | null
  notes: string | null
  location_metadata: Record<string, unknown>
  created_at: string
}

interface WorldConsequence {
  id: string
  campaign_id: string
  session_id: string | null
  trigger_action: string
  consequence: string
  scope: string
  is_permanent: boolean
  expires_at: string | null
  affected_locations: string[]
  affected_npcs: string[]
  affected_factions: string[]
  is_active: boolean
  is_known_to_player: boolean
  created_at: string
}

interface EquipmentHistory {
  id: string
  character_id: string
  item_name: string
  item_type: string | null
  is_magical: boolean
  obtained_from: string | null
  obtained_location: string | null
  obtained_session_id: string | null
  status: string
  status_details: string | null
  history_entries: Array<{ date: string; event: string; session_id?: string }>
  created_at: string
}

interface Campaign {
  id: string
  name: string
}

interface Character {
  id: string
  name: string
  campaign_id: string | null
}

type TabType = 'entries' | 'achievements' | 'locations' | 'equipment' | 'consequences'

const tabs: { id: TabType; label: string; icon: typeof BookOpen }[] = [
  { id: 'entries', label: 'Adventure Log', icon: ScrollText },
  { id: 'achievements', label: 'Achievements', icon: Trophy },
  { id: 'locations', label: 'Locations', icon: MapPin },
  { id: 'equipment', label: 'Equipment', icon: Sword },
  { id: 'consequences', label: 'World Events', icon: AlertTriangle },
]

const entryTypeIcons: Record<string, typeof BookOpen> = {
  auto_summary: BookOpen,
  player_note: ScrollText,
  key_event: Star,
  location: MapPin,
  npc: Skull,
  combat: Sword,
  loot: Package,
  achievement: Trophy,
}

const rarityColors: Record<string, string> = {
  common: 'text-parchment-300',
  uncommon: 'text-green-400',
  rare: 'text-blue-400',
  legendary: 'text-purple-400',
}

export function JournalPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = (searchParams.get('tab') as TabType) || 'entries'
  const selectedCampaignId = searchParams.get('campaign') || ''
  const selectedCharacterId = searchParams.get('character') || ''

  const setActiveTab = (tab: TabType) => {
    searchParams.set('tab', tab)
    setSearchParams(searchParams)
  }

  // Fetch campaigns and characters for filtering
  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  const { data: characters } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  // Filter characters by selected campaign
  const filteredCharacters = selectedCampaignId
    ? characters?.filter((c) => c.campaign_id === selectedCampaignId)
    : characters

  return (
    <div className="relative lg:pl-[20%]">
      {/* Decorative side image with fade */}
      <div
        className="fixed left-0 top-0 w-1/3 h-full pointer-events-none z-0 hidden lg:block"
        style={{
          backgroundImage: 'url(/img/jounal.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center right',
          maskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
        }}
      />

      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-4xl text-parchment-100">Journal</h1>
      </div>

      {/* Campaign/Character Filters */}
      <div className="card mb-6">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="label">Campaign</label>
            <select
              value={selectedCampaignId}
              onChange={(e) => {
                searchParams.set('campaign', e.target.value)
                if (e.target.value === '') {
                  searchParams.delete('campaign')
                }
                setSearchParams(searchParams)
              }}
              className="input w-48"
            >
              <option value="">All Campaigns</option>
              {campaigns?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Character</label>
            <select
              value={selectedCharacterId}
              onChange={(e) => {
                searchParams.set('character', e.target.value)
                if (e.target.value === '') {
                  searchParams.delete('character')
                }
                setSearchParams(searchParams)
              }}
              className="input w-48"
            >
              <option value="">All Characters</option>
              {filteredCharacters?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-1 mb-6 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-2 rounded transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-parchment-600 text-dungeon-900'
                  : 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600 hover:text-parchment-100'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span>{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'entries' && (
        <JournalEntriesTab
          campaignId={selectedCampaignId}
          characterId={selectedCharacterId}
        />
      )}
      {activeTab === 'achievements' && (
        <AchievementsTab characterId={selectedCharacterId} />
      )}
      {activeTab === 'locations' && (
        <LocationsTab campaignId={selectedCampaignId} />
      )}
      {activeTab === 'equipment' && (
        <EquipmentTab characterId={selectedCharacterId} />
      )}
      {activeTab === 'consequences' && (
        <ConsequencesTab campaignId={selectedCampaignId} />
      )}
    </div>
  )
}

// Journal Entries Tab
function JournalEntriesTab({
  campaignId,
  characterId,
}: {
  campaignId: string
  characterId: string
}) {
  const [showCreateModal, setShowCreateModal] = useState(false)

  const queryParams = new URLSearchParams()
  if (campaignId) queryParams.set('campaign_id', campaignId)
  if (characterId) queryParams.set('character_id', characterId)

  const { data: entries, isLoading } = useQuery({
    queryKey: ['journal-entries', campaignId, characterId],
    queryFn: () =>
      api.get<JournalEntry[]>(`/journal/entries?${queryParams.toString()}`),
  })

  if (isLoading) {
    return <div className="text-center text-parchment-400 py-12">Loading entries...</div>
  }

  if (!entries?.length) {
    return (
      <div className="card text-center py-12">
        <ScrollText className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">No Journal Entries</h2>
        <p className="text-parchment-400 mb-6">
          Your adventure log is empty. Play a session to generate entries or add your own notes.
        </p>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary inline-flex items-center space-x-2"
        >
          <Plus className="w-5 h-5" />
          <span>Add Note</span>
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-end mb-4">
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary flex items-center space-x-2"
        >
          <Plus className="w-5 h-5" />
          <span>Add Note</span>
        </button>
      </div>

      <div className="space-y-4">
        {entries.map((entry) => (
          <JournalEntryCard key={entry.id} entry={entry} />
        ))}
      </div>

      {showCreateModal && (
        <CreateEntryModal
          campaignId={campaignId}
          characterId={characterId}
          onClose={() => setShowCreateModal(false)}
        />
      )}
    </div>
  )
}

function JournalEntryCard({ entry }: { entry: JournalEntry }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = entryTypeIcons[entry.entry_type] || BookOpen

  const metadata = entry.entry_metadata as {
    key_events?: string[]
    npcs_encountered?: string[]
    locations_visited?: string[]
    combat_count?: number
    xp_estimate?: number
    loot_found?: string[]
    mood?: string
  }

  return (
    <div className="card">
      <div
        className="flex items-start justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start space-x-3">
          <div className="p-2 bg-dungeon-700 rounded">
            <Icon className="w-5 h-5 text-parchment-400" />
          </div>
          <div>
            <h3 className="font-display text-lg text-parchment-100">{entry.title}</h3>
            <div className="flex items-center space-x-3 text-sm text-parchment-400">
              <span className="flex items-center space-x-1">
                <Clock className="w-4 h-4" />
                <span>{new Date(entry.created_at).toLocaleDateString()}</span>
              </span>
              {entry.game_date && (
                <span>In-game: {entry.game_date}</span>
              )}
              <span className="capitalize">{entry.entry_type.replace('_', ' ')}</span>
            </div>
          </div>
        </div>
        <ChevronRight
          className={`w-5 h-5 text-parchment-400 transition-transform ${
            expanded ? 'rotate-90' : ''
          }`}
        />
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-dungeon-600">
          <p className="text-parchment-300 whitespace-pre-wrap">{entry.content}</p>

          {/* Metadata display for auto-summaries */}
          {entry.entry_type === 'auto_summary' && metadata && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
              {metadata.key_events && metadata.key_events.length > 0 && (
                <div>
                  <h4 className="text-sm text-parchment-400 mb-1">Key Events</h4>
                  <ul className="text-sm text-parchment-300">
                    {metadata.key_events.map((event, i) => (
                      <li key={i} className="flex items-start space-x-1">
                        <Star className="w-3 h-3 mt-1 flex-shrink-0" />
                        <span>{event}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {metadata.npcs_encountered && metadata.npcs_encountered.length > 0 && (
                <div>
                  <h4 className="text-sm text-parchment-400 mb-1">NPCs Met</h4>
                  <ul className="text-sm text-parchment-300">
                    {metadata.npcs_encountered.map((npc, i) => (
                      <li key={i}>{npc}</li>
                    ))}
                  </ul>
                </div>
              )}
              {metadata.locations_visited && metadata.locations_visited.length > 0 && (
                <div>
                  <h4 className="text-sm text-parchment-400 mb-1">Locations</h4>
                  <ul className="text-sm text-parchment-300">
                    {metadata.locations_visited.map((loc, i) => (
                      <li key={i}>{loc}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-col space-y-2">
                {metadata.combat_count !== undefined && metadata.combat_count > 0 && (
                  <div className="flex items-center space-x-2">
                    <Sword className="w-4 h-4 text-red-400" />
                    <span className="text-sm text-parchment-300">
                      {metadata.combat_count} combat{metadata.combat_count > 1 ? 's' : ''}
                    </span>
                  </div>
                )}
                {metadata.xp_estimate !== undefined && metadata.xp_estimate > 0 && (
                  <div className="flex items-center space-x-2">
                    <Star className="w-4 h-4 text-yellow-400" />
                    <span className="text-sm text-parchment-300">
                      ~{metadata.xp_estimate} XP
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CreateEntryModal({
  campaignId,
  characterId,
  onClose,
}: {
  campaignId: string
  characterId: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  const { data: characters } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  const [selectedCampaign, setSelectedCampaign] = useState(campaignId)
  const [selectedCharacter, setSelectedCharacter] = useState(characterId)

  const createMutation = useMutation({
    mutationFn: (data: { campaign_id: string; character_id: string; title: string; content: string; entry_type: string }) =>
      api.post<JournalEntry>('/journal/entries', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCampaign || !selectedCharacter) {
      alert('Please select a campaign and character')
      return
    }
    createMutation.mutate({
      campaign_id: selectedCampaign,
      character_id: selectedCharacter,
      title,
      content,
      entry_type: 'player_note',
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="card w-full max-w-lg">
        <h2 className="font-display text-2xl text-parchment-100 mb-4">Add Journal Note</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Campaign</label>
              <select
                value={selectedCampaign}
                onChange={(e) => setSelectedCampaign(e.target.value)}
                className="input w-full"
                required
              >
                <option value="">Select Campaign</option>
                {campaigns?.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Character</label>
              <select
                value={selectedCharacter}
                onChange={(e) => setSelectedCharacter(e.target.value)}
                className="input w-full"
                required
              >
                <option value="">Select Character</option>
                {characters?.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="input w-full"
              required
            />
          </div>
          <div>
            <label className="label">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="input w-full h-32"
              required
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn btn-primary"
            >
              {createMutation.isPending ? 'Saving...' : 'Save Note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Achievements Tab
function AchievementsTab({ characterId }: { characterId: string }) {
  const { data: allAchievements, isLoading: loadingAll } = useQuery({
    queryKey: ['achievements'],
    queryFn: () => api.get<Achievement[]>('/journal/achievements'),
  })

  const { data: earnedAchievements, isLoading: loadingEarned } = useQuery({
    queryKey: ['character-achievements', characterId],
    queryFn: () =>
      characterId
        ? api.get<CharacterAchievement[]>(`/journal/characters/${characterId}/achievements`)
        : Promise.resolve([]),
    enabled: !!characterId,
  })

  const isLoading = loadingAll || loadingEarned

  if (isLoading) {
    return <div className="text-center text-parchment-400 py-12">Loading achievements...</div>
  }

  const earnedIds = new Set(earnedAchievements?.map((a) => a.achievement_id) || [])

  return (
    <div>
      {characterId && earnedAchievements && earnedAchievements.length > 0 && (
        <div className="mb-8">
          <h2 className="font-display text-2xl text-parchment-100 mb-4">Earned Achievements</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {earnedAchievements.map((earned) => (
              <AchievementCard
                key={earned.id}
                achievement={earned.achievement}
                earned
                context={earned.context}
                earnedAt={earned.created_at}
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="font-display text-2xl text-parchment-100 mb-4">
          {characterId ? 'Available Achievements' : 'All Achievements'}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {allAchievements
            ?.filter((a) => !earnedIds.has(a.id))
            .map((achievement) => (
              <AchievementCard
                key={achievement.id}
                achievement={achievement}
                earned={false}
              />
            ))}
        </div>
      </div>
    </div>
  )
}

function AchievementCard({
  achievement,
  earned,
  context,
  earnedAt,
}: {
  achievement: Achievement
  earned: boolean
  context?: string | null
  earnedAt?: string
}) {
  return (
    <div className={`card ${!earned ? 'opacity-60' : ''}`}>
      <div className="flex items-start space-x-3">
        <div className={`text-3xl ${earned ? '' : 'grayscale'}`}>
          {achievement.icon || '🏆'}
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg text-parchment-100">{achievement.name}</h3>
            <span className={`text-xs uppercase ${rarityColors[achievement.rarity]}`}>
              {achievement.rarity}
            </span>
          </div>
          <p className="text-sm text-parchment-400">{achievement.description}</p>
          {earned && context && (
            <p className="text-sm text-parchment-300 mt-2 italic">"{context}"</p>
          )}
          {earned && earnedAt && (
            <p className="text-xs text-parchment-500 mt-1">
              Earned: {new Date(earnedAt).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// Locations Tab
function LocationsTab({ campaignId }: { campaignId: string }) {
  const { data: locations, isLoading } = useQuery({
    queryKey: ['world-locations', campaignId],
    queryFn: () =>
      campaignId
        ? api.get<WorldLocation[]>(`/journal/locations?campaign_id=${campaignId}`)
        : Promise.resolve([]),
    enabled: !!campaignId,
  })

  if (!campaignId) {
    return (
      <div className="card text-center py-12">
        <MapPin className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">Select a Campaign</h2>
        <p className="text-parchment-400">
          Choose a campaign to view discovered locations
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-parchment-400 py-12">Loading locations...</div>
  }

  if (!locations?.length) {
    return (
      <div className="card text-center py-12">
        <MapPin className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">No Locations Discovered</h2>
        <p className="text-parchment-400">
          Explore the world to discover new locations
        </p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {locations.map((location) => (
        <LocationCard key={location.id} location={location} />
      ))}
    </div>
  )
}

function LocationCard({ location }: { location: WorldLocation }) {
  return (
    <div className="card">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center space-x-2">
          <MapPin className={`w-5 h-5 ${location.is_cleared ? 'text-green-400' : 'text-parchment-400'}`} />
          <h3 className="font-display text-lg text-parchment-100">{location.name}</h3>
        </div>
        {location.is_cleared && (
          <span className="text-xs bg-green-600/20 text-green-400 px-2 py-1 rounded">
            Cleared
          </span>
        )}
      </div>
      {location.location_type && (
        <p className="text-sm text-parchment-500 capitalize mb-2">{location.location_type}</p>
      )}
      {location.description && (
        <p className="text-sm text-parchment-300 mb-3">{location.description}</p>
      )}
      <div className="flex items-center justify-between text-xs text-parchment-500">
        <span>Visited {location.visit_count} time{location.visit_count !== 1 ? 's' : ''}</span>
        <span>Discovered: {new Date(location.created_at).toLocaleDateString()}</span>
      </div>
      {location.notes && (
        <div className="mt-3 pt-3 border-t border-dungeon-600">
          <p className="text-sm text-parchment-400 italic">{location.notes}</p>
        </div>
      )}
    </div>
  )
}

// Equipment Tab
function EquipmentTab({ characterId }: { characterId: string }) {
  const { data: equipment, isLoading } = useQuery({
    queryKey: ['equipment-history', characterId],
    queryFn: () =>
      characterId
        ? api.get<EquipmentHistory[]>(`/journal/equipment?character_id=${characterId}`)
        : Promise.resolve([]),
    enabled: !!characterId,
  })

  if (!characterId) {
    return (
      <div className="card text-center py-12">
        <Sword className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">Select a Character</h2>
        <p className="text-parchment-400">
          Choose a character to view their equipment history
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-parchment-400 py-12">Loading equipment...</div>
  }

  if (!equipment?.length) {
    return (
      <div className="card text-center py-12">
        <Sword className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">No Equipment Tracked</h2>
        <p className="text-parchment-400">
          Notable equipment found during adventures will appear here
        </p>
      </div>
    )
  }

  // Group by status
  const carried = equipment.filter((e) => e.status === 'carried')
  const other = equipment.filter((e) => e.status !== 'carried')

  return (
    <div className="space-y-6">
      {carried.length > 0 && (
        <div>
          <h2 className="font-display text-xl text-parchment-100 mb-3">Currently Carried</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {carried.map((item) => (
              <EquipmentCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
      {other.length > 0 && (
        <div>
          <h2 className="font-display text-xl text-parchment-100 mb-3">Past Equipment</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {other.map((item) => (
              <EquipmentCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EquipmentCard({ item }: { item: EquipmentHistory }) {
  const statusColors: Record<string, string> = {
    carried: 'text-green-400',
    stored: 'text-blue-400',
    lost: 'text-red-400',
    destroyed: 'text-red-600',
    sold: 'text-yellow-400',
    given: 'text-purple-400',
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-display text-lg text-parchment-100">
            {item.item_name}
            {item.is_magical && (
              <span className="ml-2 text-xs text-purple-400">Magical</span>
            )}
          </h3>
          {item.item_type && (
            <p className="text-sm text-parchment-500 capitalize">{item.item_type}</p>
          )}
        </div>
        <span className={`text-sm capitalize ${statusColors[item.status] || 'text-parchment-400'}`}>
          {item.status}
        </span>
      </div>
      {item.obtained_from && (
        <p className="text-sm text-parchment-300">
          <span className="text-parchment-500">Obtained:</span> {item.obtained_from}
        </p>
      )}
      {item.obtained_location && (
        <p className="text-sm text-parchment-400">at {item.obtained_location}</p>
      )}
      {item.status_details && (
        <p className="text-sm text-parchment-400 mt-2 italic">{item.status_details}</p>
      )}
      {item.history_entries && item.history_entries.length > 0 && (
        <div className="mt-3 pt-3 border-t border-dungeon-600">
          <h4 className="text-xs text-parchment-500 mb-2">History</h4>
          <ul className="text-sm text-parchment-400 space-y-1">
            {item.history_entries.map((entry, i) => (
              <li key={i}>
                <span className="text-parchment-500">{entry.date}:</span> {entry.event}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// Consequences Tab
function ConsequencesTab({ campaignId }: { campaignId: string }) {
  const { data: consequences, isLoading } = useQuery({
    queryKey: ['world-consequences', campaignId],
    queryFn: () =>
      campaignId
        ? api.get<WorldConsequence[]>(`/journal/consequences?campaign_id=${campaignId}`)
        : Promise.resolve([]),
    enabled: !!campaignId,
  })

  if (!campaignId) {
    return (
      <div className="card text-center py-12">
        <AlertTriangle className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">Select a Campaign</h2>
        <p className="text-parchment-400">
          Choose a campaign to view world consequences
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-parchment-400 py-12">Loading consequences...</div>
  }

  if (!consequences?.length) {
    return (
      <div className="card text-center py-12">
        <AlertTriangle className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-2xl text-parchment-100 mb-2">No World Events</h2>
        <p className="text-parchment-400">
          Your actions haven't had major consequences... yet
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {consequences.map((consequence) => (
        <ConsequenceCard key={consequence.id} consequence={consequence} />
      ))}
    </div>
  )
}

function ConsequenceCard({ consequence }: { consequence: WorldConsequence }) {
  const scopeColors: Record<string, string> = {
    local: 'bg-green-600/20 text-green-400',
    regional: 'bg-yellow-600/20 text-yellow-400',
    global: 'bg-red-600/20 text-red-400',
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center space-x-2">
          <AlertTriangle className={`w-5 h-5 ${consequence.is_active ? 'text-yellow-400' : 'text-parchment-500'}`} />
          <span className={`text-xs px-2 py-1 rounded ${scopeColors[consequence.scope]}`}>
            {consequence.scope}
          </span>
          {!consequence.is_permanent && (
            <span className="text-xs bg-blue-600/20 text-blue-400 px-2 py-1 rounded">
              Temporary
            </span>
          )}
        </div>
        {!consequence.is_active && (
          <span className="text-xs text-parchment-500">Resolved</span>
        )}
      </div>

      <div className="mb-3">
        <h4 className="text-sm text-parchment-500">Action</h4>
        <p className="text-parchment-200">{consequence.trigger_action}</p>
      </div>

      <div>
        <h4 className="text-sm text-parchment-500">Consequence</h4>
        <p className="text-parchment-200">{consequence.consequence}</p>
      </div>

      {(consequence.affected_npcs.length > 0 ||
        consequence.affected_locations.length > 0 ||
        consequence.affected_factions.length > 0) && (
        <div className="mt-3 pt-3 border-t border-dungeon-600 flex flex-wrap gap-2">
          {consequence.affected_npcs.map((npc, i) => (
            <span key={`npc-${i}`} className="text-xs bg-dungeon-700 text-parchment-300 px-2 py-1 rounded">
              {npc}
            </span>
          ))}
          {consequence.affected_locations.map((loc, i) => (
            <span key={`loc-${i}`} className="text-xs bg-dungeon-700 text-parchment-300 px-2 py-1 rounded">
              {loc}
            </span>
          ))}
          {consequence.affected_factions.map((faction, i) => (
            <span key={`faction-${i}`} className="text-xs bg-dungeon-700 text-parchment-300 px-2 py-1 rounded">
              {faction}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 text-xs text-parchment-500">
        {new Date(consequence.created_at).toLocaleDateString()}
      </div>
    </div>
  )
}
