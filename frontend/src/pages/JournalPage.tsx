import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  BookOpen,
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
  Pencil,
  Trash2,
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

type TabType = 'entries' | 'locations' | 'equipment' | 'consequences'

const tabs: { id: TabType; label: string; icon: typeof BookOpen }[] = [
  { id: 'entries', label: 'Adventure Log', icon: ScrollText },
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
    <div className="min-h-[calc(100vh-8rem)] flex">
      {/* Left atmosphere panel - fixed height */}
      <div
        className="hidden lg:block w-[30%] fixed left-0 top-16 bottom-0"
        style={{
          backgroundImage: 'url(/img/jounal.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'top center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />
      </div>

      {/* Right content panel */}
      <div className="flex-1 lg:w-[70%] lg:ml-[30%] px-6 lg:px-12 py-12 overflow-y-auto">
      <div className="max-w-2xl mx-auto lg:mx-0">
        <div className="mb-6">
          <h1 className="font-['Cinzel',serif] text-4xl text-[#d4b870] mb-2">Journal</h1>
          <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
            A record of events, discoveries, and decisions. Review it often. Memory is fallible.
          </p>
        </div>

      {/* Campaign/Character Filters */}
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-4 mb-6">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Campaign</label>
            <select
              value={selectedCampaignId}
              onChange={(e) => {
                searchParams.set('campaign', e.target.value)
                if (e.target.value === '') {
                  searchParams.delete('campaign')
                }
                setSearchParams(searchParams)
              }}
              className="w-48 bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
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
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Character</label>
            <select
              value={selectedCharacterId}
              onChange={(e) => {
                searchParams.set('character', e.target.value)
                if (e.target.value === '') {
                  searchParams.delete('character')
                }
                setSearchParams(searchParams)
              }}
              className="w-48 bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
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
              className={`flex items-center space-x-2 px-4 py-2 rounded transition-colors whitespace-nowrap font-['Cinzel',serif] text-sm ${
                activeTab === tab.id
                  ? 'bg-[#b8a060] text-[#0f0d0a]'
                  : 'bg-[#141210] text-[#8a8270] hover:bg-[rgba(255,245,220,0.03)] hover:text-[#c8c0aa] border border-[rgba(180,160,100,0.1)]'
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
    </div>
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
  const queryClient = useQueryClient()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingEntry, setEditingEntry] = useState<JournalEntry | null>(null)
  const [deletingEntry, setDeletingEntry] = useState<JournalEntry | null>(null)

  const queryParams = new URLSearchParams()
  if (campaignId) queryParams.set('campaign_id', campaignId)
  if (characterId) queryParams.set('character_id', characterId)

  const { data: entries, isLoading } = useQuery({
    queryKey: ['journal-entries', campaignId, characterId],
    queryFn: () =>
      api.get<JournalEntry[]>(`/journal/entries?${queryParams.toString()}`),
  })

  const deleteMutation = useMutation({
    mutationFn: (entryId: string) => api.delete(`/journal/entries/${entryId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      setDeletingEntry(null)
    },
  })

  if (isLoading) {
    return <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">Loading entries...</div>
  }

  if (!entries?.length) {
    return (
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <ScrollText className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">No Journal Entries</h2>
        <p className="text-[#8a8270] mb-6 font-['Crimson_Text',serif]">
          Your adventure log is empty. Play a session to generate entries or add your own notes.
        </p>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded inline-flex items-center space-x-2 transition-colors"
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
          className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded flex items-center space-x-2 transition-colors"
        >
          <Plus className="w-5 h-5" />
          <span>Add Note</span>
        </button>
      </div>

      <div className="space-y-4">
        {entries.map((entry) => (
          <JournalEntryCard
            key={entry.id}
            entry={entry}
            onEdit={() => setEditingEntry(entry)}
            onDelete={() => setDeletingEntry(entry)}
          />
        ))}
      </div>

      {showCreateModal && (
        <CreateEntryModal
          campaignId={campaignId}
          characterId={characterId}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {editingEntry && (
        <EditEntryModal
          entry={editingEntry}
          onClose={() => setEditingEntry(null)}
        />
      )}

      {deletingEntry && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 w-full max-w-md">
            <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-4">Delete Entry?</h2>
            <p className="text-[#c8c0aa] mb-6 font-['Crimson_Text',serif]">
              Are you sure you want to delete "{deletingEntry.title}"? This cannot be undone.
            </p>
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setDeletingEntry(null)}
                className="bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.06)] font-['Cinzel',serif] px-4 py-2 rounded transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deletingEntry.id)}
                disabled={deleteMutation.isPending}
                className="bg-red-600 hover:bg-red-700 text-white font-['Cinzel',serif] px-4 py-2 rounded transition-colors"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function JournalEntryCard({ entry, onEdit, onDelete }: { entry: JournalEntry; onEdit: () => void; onDelete: () => void }) {
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
    <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-4">
      <div
        className="flex items-start justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start space-x-3">
          <div className="p-2 bg-[rgba(255,245,220,0.03)] rounded border border-[rgba(180,160,100,0.1)]">
            <Icon className="w-5 h-5 text-[#b8a060]" />
          </div>
          <div>
            <h3 className="font-['Cinzel',serif] text-lg text-[#d4b870]">{entry.title}</h3>
            <div className="flex items-center space-x-3 text-sm text-[#8a8270] font-['Crimson_Text',serif]">
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
        <div className="flex items-center space-x-2">
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="p-1.5 text-[#6a6250] hover:text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.03)] rounded transition-colors"
            title="Edit entry"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="p-1.5 text-[#6a6250] hover:text-red-400 hover:bg-[rgba(255,245,220,0.03)] rounded transition-colors"
            title="Delete entry"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <ChevronRight
            className={`w-5 h-5 text-[#8a8270] transition-transform ${
              expanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-[rgba(180,160,100,0.1)]">
          <p className="text-[#c8c0aa] whitespace-pre-wrap font-['Crimson_Text',serif]">{entry.content}</p>

          {/* Metadata display for auto-summaries */}
          {entry.entry_type === 'auto_summary' && metadata && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
              {metadata.key_events && metadata.key_events.length > 0 && (
                <div>
                  <h4 className="text-sm text-[#8a8270] mb-1 font-['Cinzel',serif]">Key Events</h4>
                  <ul className="text-sm text-[#c8c0aa] font-['Crimson_Text',serif]">
                    {metadata.key_events.map((event, i) => (
                      <li key={i} className="flex items-start space-x-1">
                        <Star className="w-3 h-3 mt-1 flex-shrink-0 text-[#b8a060]" />
                        <span>{event}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {metadata.npcs_encountered && metadata.npcs_encountered.length > 0 && (
                <div>
                  <h4 className="text-sm text-[#8a8270] mb-1 font-['Cinzel',serif]">NPCs Met</h4>
                  <ul className="text-sm text-[#c8c0aa] font-['Crimson_Text',serif]">
                    {metadata.npcs_encountered.map((npc, i) => (
                      <li key={i}>{npc}</li>
                    ))}
                  </ul>
                </div>
              )}
              {metadata.locations_visited && metadata.locations_visited.length > 0 && (
                <div>
                  <h4 className="text-sm text-[#8a8270] mb-1 font-['Cinzel',serif]">Locations</h4>
                  <ul className="text-sm text-[#c8c0aa] font-['Crimson_Text',serif]">
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
                    <span className="text-sm text-[#c8c0aa] font-['Crimson_Text',serif]">
                      {metadata.combat_count} combat{metadata.combat_count > 1 ? 's' : ''}
                    </span>
                  </div>
                )}
                {metadata.xp_estimate !== undefined && metadata.xp_estimate > 0 && (
                  <div className="flex items-center space-x-2">
                    <Star className="w-4 h-4 text-[#d4b870]" />
                    <span className="text-sm text-[#c8c0aa] font-['IBM_Plex_Mono',monospace]">
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
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 w-full max-w-lg">
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-4">Add Journal Note</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Campaign</label>
              <select
                value={selectedCampaign}
                onChange={(e) => setSelectedCampaign(e.target.value)}
                className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
                required
              >
                <option value="">Select Campaign</option>
                {campaigns?.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Character</label>
              <select
                value={selectedCharacter}
                onChange={(e) => setSelectedCharacter(e.target.value)}
                className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
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
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
              required
            />
          </div>
          <div>
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif] h-32"
              required
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={onClose} className="bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.06)] font-['Cinzel',serif] px-4 py-2 rounded transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded transition-colors disabled:opacity-50"
            >
              {createMutation.isPending ? 'Saving...' : 'Save Note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditEntryModal({
  entry,
  onClose,
}: {
  entry: JournalEntry
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(entry.title)
  const [content, setContent] = useState(entry.content)

  const updateMutation = useMutation({
    mutationFn: (data: { title: string; content: string }) =>
      api.patch<JournalEntry>(`/journal/entries/${entry.id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMutation.mutate({ title, content })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 w-full max-w-lg">
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-4">Edit Journal Entry</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif]"
              required
            />
          </div>
          <div>
            <label className="text-[#8a8270] text-sm font-['Cinzel',serif] block mb-1">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] rounded px-3 py-2 font-['Crimson_Text',serif] h-32"
              required
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={onClose} className="bg-[rgba(255,245,220,0.03)] border border-[rgba(180,160,100,0.1)] text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.06)] font-['Cinzel',serif] px-4 py-2 rounded transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="bg-[#b8a060] hover:bg-[#d4b870] text-[#0f0d0a] font-['Cinzel',serif] px-4 py-2 rounded transition-colors disabled:opacity-50"
            >
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
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
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <MapPin className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">Select a Campaign</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
          Choose a campaign to view discovered locations
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">Loading locations...</div>
  }

  if (!locations?.length) {
    return (
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <MapPin className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">No Locations Discovered</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
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
    <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center space-x-2">
          <MapPin className={`w-5 h-5 ${location.is_cleared ? 'text-green-400' : 'text-[#b8a060]'}`} />
          <h3 className="font-['Cinzel',serif] text-lg text-[#d4b870]">{location.name}</h3>
        </div>
        {location.is_cleared && (
          <span className="text-xs bg-green-600/20 text-green-400 px-2 py-1 rounded font-['Cinzel',serif]">
            Cleared
          </span>
        )}
      </div>
      {location.location_type && (
        <p className="text-sm text-[#6a6250] capitalize mb-2 font-['Crimson_Text',serif]">{location.location_type}</p>
      )}
      {location.description && (
        <p className="text-sm text-[#c8c0aa] mb-3 font-['Crimson_Text',serif]">{location.description}</p>
      )}
      <div className="flex items-center justify-between text-xs text-[#6a6250] font-['IBM_Plex_Mono',monospace]">
        <span>Visited {location.visit_count} time{location.visit_count !== 1 ? 's' : ''}</span>
        <span>Discovered: {new Date(location.created_at).toLocaleDateString()}</span>
      </div>
      {location.notes && (
        <div className="mt-3 pt-3 border-t border-[rgba(180,160,100,0.1)]">
          <p className="text-sm text-[#8a8270] italic font-['Crimson_Text',serif]">{location.notes}</p>
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
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <Sword className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">Select a Character</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
          Choose a character to view their equipment history
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">Loading equipment...</div>
  }

  if (!equipment?.length) {
    return (
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <Sword className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">No Equipment Tracked</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
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
          <h2 className="font-['Cinzel',serif] text-xl text-[#d4b870] mb-3">Currently Carried</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {carried.map((item) => (
              <EquipmentCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
      {other.length > 0 && (
        <div>
          <h2 className="font-['Cinzel',serif] text-xl text-[#d4b870] mb-3">Past Equipment</h2>
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
    sold: 'text-[#d4b870]',
    given: 'text-[#b8a060]',
  }

  return (
    <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-['Cinzel',serif] text-lg text-[#d4b870]">
            {item.item_name}
            {item.is_magical && (
              <span className="ml-2 text-xs text-[#b8a060]">Magical</span>
            )}
          </h3>
          {item.item_type && (
            <p className="text-sm text-[#6a6250] capitalize font-['Crimson_Text',serif]">{item.item_type}</p>
          )}
        </div>
        <span className={`text-sm capitalize font-['Cinzel',serif] ${statusColors[item.status] || 'text-[#8a8270]'}`}>
          {item.status}
        </span>
      </div>
      {item.obtained_from && (
        <p className="text-sm text-[#c8c0aa] font-['Crimson_Text',serif]">
          <span className="text-[#6a6250]">Obtained:</span> {item.obtained_from}
        </p>
      )}
      {item.obtained_location && (
        <p className="text-sm text-[#8a8270] font-['Crimson_Text',serif]">at {item.obtained_location}</p>
      )}
      {item.status_details && (
        <p className="text-sm text-[#8a8270] mt-2 italic font-['Crimson_Text',serif]">{item.status_details}</p>
      )}
      {item.history_entries && item.history_entries.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[rgba(180,160,100,0.1)]">
          <h4 className="text-xs text-[#6a6250] mb-2 font-['Cinzel',serif]">History</h4>
          <ul className="text-sm text-[#8a8270] space-y-1 font-['Crimson_Text',serif]">
            {item.history_entries.map((entry, i) => (
              <li key={i}>
                <span className="text-[#6a6250] font-['IBM_Plex_Mono',monospace]">{entry.date}:</span> {entry.event}
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
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <AlertTriangle className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">Select a Campaign</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
          Choose a campaign to view world consequences
        </p>
      </div>
    )
  }

  if (isLoading) {
    return <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">Loading consequences...</div>
  }

  if (!consequences?.length) {
    return (
      <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
        <AlertTriangle className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
        <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">No World Events</h2>
        <p className="text-[#8a8270] font-['Crimson_Text',serif]">
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
    regional: 'bg-[#b8a060]/20 text-[#d4b870]',
    global: 'bg-red-600/20 text-red-400',
  }

  return (
    <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center space-x-2">
          <AlertTriangle className={`w-5 h-5 ${consequence.is_active ? 'text-[#d4b870]' : 'text-[#6a6250]'}`} />
          <span className={`text-xs px-2 py-1 rounded font-['Cinzel',serif] ${scopeColors[consequence.scope]}`}>
            {consequence.scope}
          </span>
          {!consequence.is_permanent && (
            <span className="text-xs bg-blue-600/20 text-blue-400 px-2 py-1 rounded font-['Cinzel',serif]">
              Temporary
            </span>
          )}
        </div>
        {!consequence.is_active && (
          <span className="text-xs text-[#6a6250] font-['Cinzel',serif]">Resolved</span>
        )}
      </div>

      <div className="mb-3">
        <h4 className="text-sm text-[#6a6250] font-['Cinzel',serif]">Action</h4>
        <p className="text-[#c8c0aa] font-['Crimson_Text',serif]">{consequence.trigger_action}</p>
      </div>

      <div>
        <h4 className="text-sm text-[#6a6250] font-['Cinzel',serif]">Consequence</h4>
        <p className="text-[#c8c0aa] font-['Crimson_Text',serif]">{consequence.consequence}</p>
      </div>

      {(consequence.affected_npcs.length > 0 ||
        consequence.affected_locations.length > 0 ||
        consequence.affected_factions.length > 0) && (
        <div className="mt-3 pt-3 border-t border-[rgba(180,160,100,0.1)] flex flex-wrap gap-2">
          {consequence.affected_npcs.map((npc, i) => (
            <span key={`npc-${i}`} className="text-xs bg-[rgba(255,245,220,0.03)] text-[#c8c0aa] px-2 py-1 rounded border border-[rgba(180,160,100,0.1)] font-['Crimson_Text',serif]">
              {npc}
            </span>
          ))}
          {consequence.affected_locations.map((loc, i) => (
            <span key={`loc-${i}`} className="text-xs bg-[rgba(255,245,220,0.03)] text-[#c8c0aa] px-2 py-1 rounded border border-[rgba(180,160,100,0.1)] font-['Crimson_Text',serif]">
              {loc}
            </span>
          ))}
          {consequence.affected_factions.map((faction, i) => (
            <span key={`faction-${i}`} className="text-xs bg-[rgba(255,245,220,0.03)] text-[#c8c0aa] px-2 py-1 rounded border border-[rgba(180,160,100,0.1)] font-['Crimson_Text',serif]">
              {faction}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 text-xs text-[#6a6250] font-['IBM_Plex_Mono',monospace]">
        {new Date(consequence.created_at).toLocaleDateString()}
      </div>
    </div>
  )
}
