import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ScrollText,
  Plus,
  ChevronDown,
  ChevronUp,
  Trophy,
  MapPin,
  BookOpen,
  X,
} from 'lucide-react'
import { api } from '@/services/api'

interface JournalEntry {
  id: string
  title: string
  content: string
  entry_type: string
  created_at: string
  game_date: string | null
  entry_metadata: Record<string, unknown>
}

interface Achievement {
  id: string
  code: string
  name: string
  description: string
  icon: string | null
  rarity: string
}

interface CharacterAchievement {
  id: string
  achievement: Achievement
  context: string | null
  created_at: string
}

interface Props {
  campaignId: string
  characterId: string
  sessionId: string
}

export function JournalPanel({ campaignId, characterId, sessionId }: Props) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [activeSection, setActiveSection] = useState<'entries' | 'achievements'>('entries')
  const [showNoteModal, setShowNoteModal] = useState(false)

  return (
    <div className="card">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <h3 className="font-display text-lg text-parchment-100 flex items-center">
          <ScrollText className="w-5 h-5 mr-2" />
          Journal
        </h3>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-parchment-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-parchment-400" />
        )}
      </div>

      {isExpanded && (
        <div className="mt-4">
          {/* Section Tabs */}
          <div className="flex space-x-1 mb-3">
            <button
              onClick={() => setActiveSection('entries')}
              className={`flex-1 flex items-center justify-center space-x-1 px-2 py-1 rounded text-sm transition-colors ${
                activeSection === 'entries'
                  ? 'bg-parchment-600 text-dungeon-900'
                  : 'bg-dungeon-700 text-parchment-400 hover:text-parchment-200'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span>Log</span>
            </button>
            <button
              onClick={() => setActiveSection('achievements')}
              className={`flex-1 flex items-center justify-center space-x-1 px-2 py-1 rounded text-sm transition-colors ${
                activeSection === 'achievements'
                  ? 'bg-parchment-600 text-dungeon-900'
                  : 'bg-dungeon-700 text-parchment-400 hover:text-parchment-200'
              }`}
            >
              <Trophy className="w-4 h-4" />
              <span>Deeds</span>
            </button>
          </div>

          {activeSection === 'entries' ? (
            <EntriesSection
              campaignId={campaignId}
              characterId={characterId}
              onAddNote={() => setShowNoteModal(true)}
            />
          ) : (
            <AchievementsSection characterId={characterId} />
          )}
        </div>
      )}

      {showNoteModal && (
        <AddNoteModal
          campaignId={campaignId}
          characterId={characterId}
          sessionId={sessionId}
          onClose={() => setShowNoteModal(false)}
        />
      )}
    </div>
  )
}

function EntriesSection({
  campaignId,
  characterId,
  onAddNote,
}: {
  campaignId: string
  characterId: string
  onAddNote: () => void
}) {
  const { data: entries, isLoading } = useQuery({
    queryKey: ['journal-entries', campaignId, characterId, 'recent'],
    queryFn: () =>
      api.get<JournalEntry[]>(
        `/journal/entries?campaign_id=${campaignId}&character_id=${characterId}&limit=5`
      ),
    refetchInterval: 30000, // Refetch every 30 seconds
  })

  return (
    <div>
      <button
        onClick={onAddNote}
        className="w-full btn btn-secondary text-sm flex items-center justify-center space-x-1 mb-3"
      >
        <Plus className="w-4 h-4" />
        <span>Add Note</span>
      </button>

      {isLoading ? (
        <div className="text-parchment-500 text-sm text-center py-4">Loading...</div>
      ) : entries?.length === 0 ? (
        <div className="text-parchment-500 text-sm text-center py-4">
          No journal entries yet
        </div>
      ) : (
        <div className="space-y-2 max-h-48 overflow-y-auto scrollbar-dark">
          {entries?.map((entry) => (
            <JournalEntryCard key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

function JournalEntryCard({ entry }: { entry: JournalEntry }) {
  const [expanded, setExpanded] = useState(false)

  const getIcon = () => {
    switch (entry.entry_type) {
      case 'auto_summary':
        return <BookOpen className="w-4 h-4" />
      case 'player_note':
        return <ScrollText className="w-4 h-4" />
      case 'location':
        return <MapPin className="w-4 h-4" />
      case 'achievement':
        return <Trophy className="w-4 h-4" />
      default:
        return <ScrollText className="w-4 h-4" />
    }
  }

  const formatTimestamp = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const isToday = date.toDateString() === now.toDateString()

    if (isToday) {
      return `Today at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    }
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  }

  return (
    <div
      className="bg-dungeon-700 rounded p-2 cursor-pointer hover:bg-dungeon-600 transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start space-x-2">
        <div className="text-parchment-500 mt-0.5">{getIcon()}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm text-parchment-200 truncate">{entry.title}</h4>
          {/* Show in-game date if available, otherwise real time */}
          {entry.game_date ? (
            <p className="text-xs text-amber-400" title={formatTimestamp(entry.created_at)}>
              📅 {entry.game_date}
            </p>
          ) : (
            <p className="text-xs text-parchment-500">
              {formatTimestamp(entry.created_at)}
            </p>
          )}
        </div>
      </div>
      {expanded && (
        <div className="mt-2 pt-2 border-t border-dungeon-600">
          <p className="text-xs text-parchment-300 whitespace-pre-wrap line-clamp-4">
            {entry.content}
          </p>
        </div>
      )}
    </div>
  )
}

function AchievementsSection({ characterId }: { characterId: string }) {
  const { data: achievements, isLoading } = useQuery({
    queryKey: ['character-achievements', characterId],
    queryFn: () =>
      api.get<CharacterAchievement[]>(`/journal/characters/${characterId}/achievements`),
    enabled: !!characterId,
  })

  const rarityColors: Record<string, string> = {
    common: 'text-parchment-300',
    uncommon: 'text-green-400',
    rare: 'text-blue-400',
    legendary: 'text-purple-400',
  }

  if (isLoading) {
    return <div className="text-parchment-500 text-sm text-center py-4">Loading...</div>
  }

  if (!achievements?.length) {
    return (
      <div className="text-parchment-500 text-sm text-center py-4">
        <Trophy className="w-8 h-8 mx-auto mb-2 opacity-50" />
        No achievements yet
      </div>
    )
  }

  const formatTimestamp = (dateStr: string) => {
    const date = new Date(dateStr)
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  }

  return (
    <div className="space-y-2 max-h-48 overflow-y-auto scrollbar-dark">
      {achievements.map((earned) => (
        <div
          key={earned.id}
          className="bg-dungeon-700 rounded p-2 flex items-center space-x-2"
        >
          <div className="text-xl">{earned.achievement.icon || '🏆'}</div>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm text-parchment-200 truncate">
              {earned.achievement.name}
            </h4>
            <div className="flex items-center gap-2">
              <span className={`text-xs ${rarityColors[earned.achievement.rarity]}`}>
                {earned.achievement.rarity}
              </span>
              <span className="text-xs text-parchment-600">
                {formatTimestamp(earned.created_at)}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function AddNoteModal({
  campaignId,
  characterId,
  sessionId,
  onClose,
}: {
  campaignId: string
  characterId: string
  sessionId: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: {
      campaign_id: string
      character_id: string
      session_id: string
      title: string
      content: string
      entry_type: string
    }) => api.post('/journal/entries', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      onClose()
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({
      campaign_id: campaignId,
      character_id: characterId,
      session_id: sessionId,
      title: title || 'Quick Note',
      content,
      entry_type: 'player_note',
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="card w-full max-w-md mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-xl text-parchment-100">Add Note</h2>
          <button
            onClick={onClose}
            className="text-parchment-400 hover:text-parchment-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Title (optional)</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Quick Note"
              className="input w-full"
            />
          </div>
          <div>
            <label className="label">Note</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="What do you want to remember?"
              className="input w-full h-24"
              required
              autoFocus
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!content.trim() || createMutation.isPending}
              className="btn btn-primary"
            >
              {createMutation.isPending ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
