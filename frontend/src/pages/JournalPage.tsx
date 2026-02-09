import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/services/api'

// ─── Types ───

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
  is_discovered: boolean
  is_cleared: boolean
  visit_count: number
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

interface SessionInfo {
  id: string
  campaign_id: string
  character_id: string
  title: string | null
  status: string
  created_at: string
  updated_at: string
}

// ─── Type Config ───

type DisplayType = 'auto' | 'event' | 'note' | 'discovery'

const TYPE_CONFIG: Record<DisplayType, { label: string; icon: string; color: string; accent: string; border: string }> = {
  auto: {
    label: "Auto Summary", icon: "📋", color: "var(--text-dim)",
    accent: "rgba(138,130,112,0.15)", border: "rgba(138,130,112,0.2)",
  },
  event: {
    label: "Key Event", icon: "⭐", color: "var(--gold)",
    accent: "rgba(180,160,80,0.08)", border: "rgba(180,160,80,0.2)",
  },
  note: {
    label: "Note", icon: "✎", color: "#7a9ab8",
    accent: "rgba(122,154,184,0.06)", border: "rgba(122,154,184,0.15)",
  },
  discovery: {
    label: "Discovery", icon: "◇", color: "#8a9a6a",
    accent: "rgba(138,154,106,0.06)", border: "rgba(138,154,106,0.15)",
  },
}

function mapEntryType(backendType: string): { displayType: DisplayType; icon: string; label: string } {
  switch (backendType) {
    case 'auto_summary': return { displayType: 'auto', icon: '📋', label: 'Auto Summary' }
    case 'key_event': return { displayType: 'event', icon: '⭐', label: 'Key Event' }
    case 'player_note': return { displayType: 'note', icon: '✎', label: 'Note' }
    case 'location': return { displayType: 'discovery', icon: '◇', label: 'Discovery' }
    case 'npc': return { displayType: 'event', icon: '⭐', label: 'Key Event' }
    case 'combat': return { displayType: 'event', icon: '⚔', label: 'Combat' }
    case 'loot': return { displayType: 'discovery', icon: '💰', label: 'Loot' }
    case 'achievement': return { displayType: 'event', icon: '🏆', label: 'Achievement' }
    default: return { displayType: 'auto', icon: '📋', label: 'Entry' }
  }
}

function extractMetadata(entry: JournalEntry) {
  const m = entry.entry_metadata as Record<string, unknown> || {}
  return {
    tags: (m.key_events as string[] || []),
    locations: (m.locations_visited as string[] || []),
    loot: (m.loot_found as string[] || []),
    npcs: (m.npcs_encountered as string[] || []),
    combatCount: (m.combat_count as number) || 0,
    xpEstimate: (m.xp_estimate as number) || 0,
  }
}

// ─── Entry Card ───

function EntryCard({
  entry,
  expanded,
  onToggle,
  onEdit,
  onDelete,
}: {
  entry: JournalEntry
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const mapped = mapEntryType(entry.entry_type)
  const tc = TYPE_CONFIG[mapped.displayType]
  const meta = extractMetadata(entry)
  const hasLoot = meta.loot.length > 0
  const hasLocations = meta.locations.length > 0
  const allTags = [...meta.tags, ...meta.npcs.map(n => `npc:${n}`)]
  const time = new Date(entry.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <div style={{
      position: "relative",
      paddingLeft: 28,
      animation: "entryIn 0.3s ease both",
    }}>
      {/* Timeline dot */}
      <div style={{
        position: "absolute", left: 0, top: 6,
        width: 12, height: 12, borderRadius: "50%",
        background: expanded ? tc.accent : "var(--bg-panel)",
        border: `2px solid ${expanded ? tc.color : "var(--border)"}`,
        transition: "all 0.2s",
        zIndex: 2,
      }} />

      {/* Card */}
      <div
        onClick={onToggle}
        style={{
          background: expanded ? tc.accent : "transparent",
          border: `1px solid ${expanded ? tc.border : "transparent"}`,
          borderRadius: 6, cursor: "pointer",
          padding: expanded ? "14px 16px" : "8px 12px",
          marginBottom: 2,
          transition: "all 0.2s ease",
        }}
        onMouseEnter={e => { if (!expanded) { e.currentTarget.style.background = "rgba(180,160,100,0.02)"; e.currentTarget.style.borderColor = "var(--border)"; } }}
        onMouseLeave={e => { if (!expanded) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "transparent"; } }}
      >
        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Type + time */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
              <span style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.06em", color: tc.color,
              }}>
                <span style={{ fontSize: 10 }}>{mapped.icon}</span>
                {mapped.label}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", opacity: 0.5 }}>
                {time}
              </span>
              {entry.game_date && (
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", opacity: 0.4 }}>
                  In-game: {entry.game_date}
                </span>
              )}
            </div>

            {/* Title */}
            <div style={{
              fontFamily: "var(--font-body)", fontSize: 15, fontWeight: 600,
              color: "var(--text)", lineHeight: 1.3,
            }}>
              {entry.title}
            </div>

            {/* Preview (collapsed) */}
            {!expanded && (
              <div style={{
                fontFamily: "var(--font-body)", fontSize: 13,
                color: "var(--text-dim)", lineHeight: 1.5,
                marginTop: 4,
                display: "-webkit-box", WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical", overflow: "hidden",
                opacity: 0.7,
              }}>
                {entry.content}
              </div>
            )}
          </div>

          {/* Tags (collapsed — show count) */}
          {!expanded && allTags.length > 0 && (
            <div style={{ display: "flex", gap: 3, flexShrink: 0, marginTop: 16 }}>
              {allTags.slice(0, 2).map(t => (
                <span key={t} style={{
                  fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)",
                  padding: "1px 6px", borderRadius: 6,
                  background: "rgba(180,160,100,0.04)", border: "1px solid var(--border)",
                }}>{t}</span>
              ))}
              {allTags.length > 2 && (
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", opacity: 0.5 }}>
                  +{allTags.length - 2}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Expanded content */}
        {expanded && (
          <div style={{ marginTop: 10, animation: "fadeIn 0.2s ease" }}>
            {/* Full body */}
            <div style={{
              fontFamily: "var(--font-body)", fontSize: 14,
              color: "var(--text-dim)", lineHeight: 1.65,
              whiteSpace: "pre-wrap",
            }}>
              {entry.content}
            </div>

            {/* Metadata grid */}
            {(hasLocations || hasLoot || allTags.length > 0) && (
              <div style={{
                marginTop: 14, paddingTop: 12,
                borderTop: `1px solid ${tc.border}`,
                display: "flex", flexWrap: "wrap", gap: 16,
              }}>
                {/* Locations */}
                {hasLocations && (
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--muted)", marginBottom: 4 }}>LOCATIONS</div>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {meta.locations.map(l => (
                        <span key={l} style={{
                          fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text)",
                          padding: "2px 8px", borderRadius: 4,
                          background: "rgba(180,160,100,0.05)", border: "1px solid var(--border)",
                          display: "inline-flex", alignItems: "center", gap: 4,
                        }}>
                          <span style={{ fontSize: 9, color: "var(--gold)" }}>⚑</span>{l}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Loot */}
                {hasLoot && (
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--muted)", marginBottom: 4 }}>LOOT</div>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {meta.loot.map(l => (
                        <span key={l} style={{
                          fontFamily: "var(--font-body)", fontSize: 12, color: "#c90",
                          padding: "2px 8px", borderRadius: 4,
                          background: "rgba(204,153,0,0.05)", border: "1px solid rgba(204,153,0,0.12)",
                          display: "inline-flex", alignItems: "center", gap: 4,
                        }}>
                          <span style={{ fontSize: 9 }}>💰</span>{l}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tags */}
            {allTags.length > 0 && (
              <div style={{ marginTop: 10, display: "flex", gap: 4, flexWrap: "wrap" }}>
                {allTags.map(t => (
                  <span key={t} style={{
                    fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)",
                    padding: "2px 8px", borderRadius: 8,
                    background: "rgba(180,160,100,0.04)", border: "1px solid var(--border)",
                  }}>#{t}</span>
                ))}
              </div>
            )}

            {/* Actions */}
            <div style={{
              marginTop: 12, display: "flex", gap: 6, justifyContent: "flex-end",
            }}>
              <button onClick={e => { e.stopPropagation(); onEdit(); }} style={{
                padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)",
                fontFamily: "var(--font-mono)", fontSize: 10,
                color: "var(--muted)",
                display: "flex", alignItems: "center", gap: 4,
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.color = "var(--text-dim)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--muted)"; }}
              >
                <span style={{ fontSize: 10 }}>✎</span>Edit
              </button>
              <button onClick={e => { e.stopPropagation(); onDelete(); }} style={{
                padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)",
                fontFamily: "var(--font-mono)", fontSize: 10,
                color: "rgba(204,68,68,0.5)",
                display: "flex", alignItems: "center", gap: 4,
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(204,68,68,0.2)"; e.currentTarget.style.color = "#c44"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "rgba(204,68,68,0.5)"; }}
              >
                <span style={{ fontSize: 10 }}>🗑</span>Delete
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Modals ───

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
    if (!selectedCampaign || !selectedCharacter) return
    createMutation.mutate({
      campaign_id: selectedCampaign,
      character_id: selectedCharacter,
      title,
      content,
      entry_type: 'player_note',
    })
  }

  const modalOverlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  }
  const modalPanel: React.CSSProperties = {
    background: 'var(--bg-panel)', border: '1px solid var(--border-strong)',
    borderRadius: 8, padding: 24, width: '100%', maxWidth: 480,
  }
  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--font-label)', fontSize: 10, letterSpacing: '0.08em',
    color: 'var(--muted)', display: 'block', marginBottom: 4,
  }
  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
    borderRadius: 4, padding: '8px 10px', color: 'var(--text)',
    fontFamily: 'var(--font-body)', fontSize: 14,
  }

  return (
    <div style={modalOverlay} onClick={onClose}>
      <div style={modalPanel} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--gold-bright)', marginBottom: 16 }}>
          Add Journal Note
        </h2>
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>Campaign</label>
              <select
                value={selectedCampaign}
                onChange={e => setSelectedCampaign(e.target.value)}
                style={{ ...inputStyle, cursor: 'pointer' }}
                required
              >
                <option value="">Select Campaign</option>
                {campaigns?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Character</label>
              <select
                value={selectedCharacter}
                onChange={e => setSelectedCharacter(e.target.value)}
                style={{ ...inputStyle, cursor: 'pointer' }}
                required
              >
                <option value="">Select Character</option>
                {characters?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Title</label>
            <input type="text" value={title} onChange={e => setTitle(e.target.value)} style={inputStyle} required />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Content</label>
            <textarea
              value={content} onChange={e => setContent(e.target.value)}
              style={{ ...inputStyle, height: 120, resize: 'vertical' }} required
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" onClick={onClose} style={{
              padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
              background: 'transparent', border: '1px solid var(--border)',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-dim)',
            }}>Cancel</button>
            <button type="submit" disabled={createMutation.isPending} style={{
              padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
              background: 'rgba(180,160,80,0.12)', border: '1px solid rgba(180,160,80,0.25)',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--gold)',
              opacity: createMutation.isPending ? 0.5 : 1,
            }}>
              {createMutation.isPending ? 'Saving...' : 'Save Note'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditEntryModal({ entry, onClose }: { entry: JournalEntry; onClose: () => void }) {
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

  const modalOverlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  }
  const modalPanel: React.CSSProperties = {
    background: 'var(--bg-panel)', border: '1px solid var(--border-strong)',
    borderRadius: 8, padding: 24, width: '100%', maxWidth: 480,
  }
  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--font-label)', fontSize: 10, letterSpacing: '0.08em',
    color: 'var(--muted)', display: 'block', marginBottom: 4,
  }
  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
    borderRadius: 4, padding: '8px 10px', color: 'var(--text)',
    fontFamily: 'var(--font-body)', fontSize: 14,
  }

  return (
    <div style={modalOverlay} onClick={onClose}>
      <div style={modalPanel} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--gold-bright)', marginBottom: 16 }}>
          Edit Entry
        </h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Title</label>
            <input type="text" value={title} onChange={e => setTitle(e.target.value)} style={inputStyle} required />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Content</label>
            <textarea
              value={content} onChange={e => setContent(e.target.value)}
              style={{ ...inputStyle, height: 120, resize: 'vertical' }} required
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" onClick={onClose} style={{
              padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
              background: 'transparent', border: '1px solid var(--border)',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-dim)',
            }}>Cancel</button>
            <button type="submit" disabled={updateMutation.isPending} style={{
              padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
              background: 'rgba(180,160,80,0.12)', border: '1px solid rgba(180,160,80,0.25)',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--gold)',
              opacity: updateMutation.isPending ? 0.5 : 1,
            }}>
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function DeleteConfirmModal({
  entry,
  onClose,
  onConfirm,
  isPending,
}: {
  entry: JournalEntry
  onClose: () => void
  onConfirm: () => void
  isPending: boolean
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border-strong)',
        borderRadius: 8, padding: 24, width: '100%', maxWidth: 400,
      }} onClick={e => e.stopPropagation()}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--gold-bright)', marginBottom: 12 }}>
          Delete Entry?
        </h2>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-dim)', marginBottom: 20 }}>
          Are you sure you want to delete &ldquo;{entry.title}&rdquo;? This cannot be undone.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
            background: 'transparent', border: '1px solid var(--border)',
            fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-dim)',
          }}>Cancel</button>
          <button onClick={onConfirm} disabled={isPending} style={{
            padding: '8px 16px', borderRadius: 4, cursor: 'pointer',
            background: 'rgba(204,68,68,0.12)', border: '1px solid rgba(204,68,68,0.25)',
            fontFamily: 'var(--font-body)', fontSize: 13, color: '#c44',
            opacity: isPending ? 0.5 : 1,
          }}>
            {isPending ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ───

type TabType = 'log' | 'locations' | 'equipment' | 'world'

export function JournalPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const activeTab = (searchParams.get('tab') as TabType) || 'log'
  const selectedCampaignId = searchParams.get('campaign') || ''
  const selectedCharacterId = searchParams.get('character') || ''
  const filterType = searchParams.get('type') || 'all'

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingEntry, setEditingEntry] = useState<JournalEntry | null>(null)
  const [deletingEntry, setDeletingEntry] = useState<JournalEntry | null>(null)

  const setParam = (key: string, value: string) => {
    if (value === '' || value === 'all') {
      searchParams.delete(key)
    } else {
      searchParams.set(key, value)
    }
    setSearchParams(searchParams)
  }

  // ─── Data fetching ───

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  const { data: characters } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  const filteredCharacters = selectedCampaignId
    ? characters?.filter(c => c.campaign_id === selectedCampaignId)
    : characters

  const entryParams = new URLSearchParams()
  if (selectedCampaignId) entryParams.set('campaign_id', selectedCampaignId)
  if (selectedCharacterId) entryParams.set('character_id', selectedCharacterId)

  const { data: entries, isLoading: entriesLoading } = useQuery({
    queryKey: ['journal-entries', selectedCampaignId, selectedCharacterId],
    queryFn: () => api.get<JournalEntry[]>(`/journal/entries?${entryParams.toString()}`),
  })

  const { data: sessions } = useQuery({
    queryKey: ['sessions', selectedCampaignId],
    queryFn: () => {
      const p = new URLSearchParams()
      if (selectedCampaignId) p.set('campaign_id', selectedCampaignId)
      return api.get<SessionInfo[]>(`/sessions?${p.toString()}`)
    },
  })

  const { data: locations } = useQuery({
    queryKey: ['world-locations', selectedCampaignId],
    queryFn: () => api.get<WorldLocation[]>(`/journal/locations?campaign_id=${selectedCampaignId}`),
    enabled: !!selectedCampaignId && activeTab === 'locations',
  })

  const { data: equipment } = useQuery({
    queryKey: ['equipment-history', selectedCharacterId],
    queryFn: () => api.get<EquipmentHistory[]>(`/journal/equipment?character_id=${selectedCharacterId}`),
    enabled: !!selectedCharacterId && activeTab === 'equipment',
  })

  const { data: consequences } = useQuery({
    queryKey: ['world-consequences', selectedCampaignId],
    queryFn: () => api.get<WorldConsequence[]>(`/journal/consequences?campaign_id=${selectedCampaignId}`),
    enabled: !!selectedCampaignId && activeTab === 'world',
  })

  const deleteMutation = useMutation({
    mutationFn: (entryId: string) => api.delete(`/journal/entries/${entryId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      setDeletingEntry(null)
    },
  })

  // ─── Derived data ───

  const sessionMap = useMemo(() => {
    const map = new Map<string, { num: number; date: string; title: string | null }>()
    if (!sessions) return map
    const sorted = [...sessions].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    sorted.forEach((s, i) => {
      map.set(s.id, {
        num: i + 1,
        date: new Date(s.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }),
        title: s.title,
      })
    })
    return map
  }, [sessions])

  const filteredEntries = useMemo(() => {
    if (!entries) return []
    if (filterType === 'all') return entries
    return entries.filter(e => {
      const mapped = mapEntryType(e.entry_type).displayType
      return mapped === filterType
    })
  }, [entries, filterType])

  const sessionGroups = useMemo(() => {
    const groups: { key: string; num: number | null; date: string; entryCount: number; entries: JournalEntry[] }[] = []
    const bySession = new Map<string, JournalEntry[]>()
    const unsorted: JournalEntry[] = []

    filteredEntries.forEach(e => {
      if (e.session_id) {
        const arr = bySession.get(e.session_id) || []
        arr.push(e)
        bySession.set(e.session_id, arr)
      } else {
        unsorted.push(e)
      }
    })

    // Sort sessions by number descending
    const sessionIds = [...bySession.keys()].sort((a, b) => {
      const aInfo = sessionMap.get(a)
      const bInfo = sessionMap.get(b)
      return (bInfo?.num || 0) - (aInfo?.num || 0)
    })

    sessionIds.forEach(sid => {
      const info = sessionMap.get(sid)
      const sessionEntries = bySession.get(sid) || []
      groups.push({
        key: sid,
        num: info?.num || null,
        date: info?.date || new Date(sessionEntries[0]?.created_at || '').toLocaleDateString(),
        entryCount: sessionEntries.length,
        entries: sessionEntries.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
      })
    })

    if (unsorted.length > 0) {
      groups.push({
        key: 'unsorted',
        num: null,
        date: '',
        entryCount: unsorted.length,
        entries: unsorted.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
      })
    }

    return groups
  }, [filteredEntries, sessionMap])

  // Tab counts
  const totalEntries = filteredEntries.length
  const locationCount = locations?.length || 0
  const equipmentCount = equipment?.length || 0
  const consequenceCount = consequences?.length || 0

  const TABS: { key: TabType; label: string; icon: string; count: number }[] = [
    { key: 'log', label: 'Adventure Log', icon: '📋', count: totalEntries },
    { key: 'locations', label: 'Locations', icon: '⚑', count: locationCount },
    { key: 'equipment', label: 'Equipment', icon: '⚔', count: equipmentCount },
    { key: 'world', label: 'World Events', icon: '◇', count: consequenceCount },
  ]

  const TYPE_PILLS = [
    { key: 'all', label: 'All Entries' },
    { key: 'auto', label: '📋 Summaries' },
    { key: 'event', label: '⭐ Key Events' },
    { key: 'note', label: '✎ Notes' },
    { key: 'discovery', label: '◇ Discoveries' },
  ]

  return (
    <>
      <style>{`
        :root {
          --bg: #0f0d0a; --bg-panel: #141210; --bg-card: rgba(255,245,220,0.03);
          --bg-deep: #0a0908; --bg-input: #1a1816;
          --border: rgba(180,160,100,0.1); --border-strong: rgba(180,160,100,0.2);
          --text: #c8c0aa; --text-dim: #8a8270; --muted: #6a6250;
          --gold: #b8a060; --gold-dim: rgba(180,160,80,0.4); --gold-bright: #d4b870;
          --font-display: 'Cinzel', serif; --font-body: 'Crimson Text', serif;
          --font-label: 'Cinzel', serif; --font-mono: 'IBM Plex Mono', monospace;
        }

        @keyframes entryIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes heroIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }

        .journal-page select {
          background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px;
          padding: 5px 24px 5px 8px; color: var(--text); font-family: var(--font-body);
          font-size: 12px; cursor: pointer; appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%236a6250' fill='none' stroke-width='1.2'/%3E%3C/svg%3E");
          background-repeat: no-repeat; background-position: right 8px center;
        }
        .journal-page select:focus { outline: none; border-color: var(--gold-dim); }

        .journal-page .tab-btn {
          display: flex; align-items: center; gap: 6px;
          padding: 8px 14px; border-radius: 6px; cursor: pointer;
          background: transparent; border: 1px solid transparent;
          font-family: 'Crimson Text', serif; font-size: 13px;
          color: #6a6250; transition: all 0.15s; white-space: nowrap;
        }
        .journal-page .tab-btn:hover { color: #8a8270; background: rgba(180,160,80,0.03); }
        .journal-page .tab-btn.active {
          color: #b8a060; border-color: rgba(180,160,80,0.2);
          background: rgba(180,160,80,0.06);
        }

        .journal-page .type-pill {
          padding: 3px 10px; border-radius: 10px; cursor: pointer;
          background: transparent; border: 1px solid transparent;
          font-family: 'IBM Plex Mono', monospace; font-size: 9px;
          color: #6a6250; transition: all 0.12s; letter-spacing: 0.05em;
        }
        .journal-page .type-pill:hover { color: #8a8270; }
        .journal-page .type-pill.active { color: #b8a060; border-color: rgba(180,160,80,0.3); background: rgba(180,160,80,0.06); }
      `}</style>

      <div className="journal-page" style={{ minHeight: 'calc(100vh - 8rem)', display: 'flex', color: 'var(--text)' }}>
        {/* Left atmosphere panel */}
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

        <div className="flex-1 lg:w-[70%] lg:ml-[30%]" style={{ maxWidth: 820, padding: '40px 32px 80px' }}>

          {/* Hero */}
          <div style={{ marginBottom: 28, animation: 'heroIn 0.4s ease both' }}>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700,
              fontStyle: 'italic', color: 'var(--text)', letterSpacing: '0.03em', marginBottom: 6,
            }}>
              Journal
            </h1>
            <p style={{
              fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--muted)', fontStyle: 'italic',
            }}>
              A record of events, discoveries, and decisions. Review it often. Memory is fallible.
            </p>
          </div>

          {/* Filter bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            {/* Tabs */}
            <div style={{ display: 'flex', gap: 3 }}>
              {TABS.map(t => (
                <button
                  key={t.key}
                  className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
                  onClick={() => setParam('tab', t.key)}
                >
                  <span style={{ fontSize: 12 }}>{t.icon}</span>
                  {t.label}
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 9,
                    color: activeTab === t.key ? 'var(--gold-dim)' : 'var(--muted)',
                    opacity: 0.6,
                  }}>{t.count}</span>
                </button>
              ))}
            </div>

            <div style={{ flex: 1 }} />

            {/* Campaign/Character filters */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <select
                value={selectedCampaignId}
                onChange={e => {
                  setParam('campaign', e.target.value)
                  setParam('character', '')
                }}
              >
                <option value="">All Campaigns</option>
                {campaigns?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select
                value={selectedCharacterId}
                onChange={e => setParam('character', e.target.value)}
              >
                <option value="">All Characters</option>
                {filteredCharacters?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>

          {/* Type filter pills (only on log tab) */}
          {activeTab === 'log' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 24 }}>
              {TYPE_PILLS.map(f => (
                <button
                  key={f.key}
                  className={`type-pill ${filterType === f.key || (filterType === '' && f.key === 'all') ? 'active' : ''}`}
                  onClick={() => setParam('type', f.key)}
                >{f.label}</button>
              ))}

              <div style={{ flex: 1 }} />

              <button
                onClick={() => setShowCreateModal(true)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '5px 14px', borderRadius: 4, cursor: 'pointer',
                  background: 'rgba(180,160,80,0.06)',
                  border: '1px solid rgba(180,160,80,0.15)',
                  fontFamily: 'var(--font-body)', fontSize: 13,
                  color: 'var(--gold)', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gold-dim)'; e.currentTarget.style.background = 'rgba(180,160,80,0.1)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(180,160,80,0.15)'; e.currentTarget.style.background = 'rgba(180,160,80,0.06)'; }}
              >
                <span style={{ fontSize: 14 }}>+</span> Add Note
              </button>
            </div>
          )}

          {/* ═══ ADVENTURE LOG TAB ═══ */}
          {activeTab === 'log' && (
            <div>
              {entriesLoading && (
                <div style={{ textAlign: 'center', padding: '40px 0', fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)', fontStyle: 'italic' }}>
                  Loading entries...
                </div>
              )}

              {!entriesLoading && sessionGroups.map(session => (
                <div key={session.key} style={{ marginBottom: 32 }}>
                  {/* Session header */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14,
                    paddingLeft: 28,
                  }}>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
                      color: 'var(--text-dim)', letterSpacing: '0.06em', whiteSpace: 'nowrap',
                    }}>
                      {session.num ? `Session ${session.num}` : 'Unsorted'}
                    </div>
                    <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                    <div style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--muted)', whiteSpace: 'nowrap',
                    }}>
                      {session.date}
                    </div>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)', opacity: 0.5,
                      padding: '1px 6px', borderRadius: 6, background: 'rgba(180,160,100,0.04)',
                    }}>
                      {session.entryCount} {session.entryCount === 1 ? 'entry' : 'entries'}
                    </span>
                  </div>

                  {/* Timeline line + entries */}
                  <div style={{ position: 'relative', paddingLeft: 0 }}>
                    <div style={{
                      position: 'absolute', left: 5, top: 12, bottom: 12,
                      width: 1, background: 'var(--border)',
                    }} />

                    {session.entries.map(entry => (
                      <EntryCard
                        key={entry.id}
                        entry={entry}
                        expanded={expandedId === entry.id}
                        onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                        onEdit={() => setEditingEntry(entry)}
                        onDelete={() => setDeletingEntry(entry)}
                      />
                    ))}
                  </div>
                </div>
              ))}

              {/* Empty state */}
              {!entriesLoading && sessionGroups.length === 0 && (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.2 }}>📖</div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 16, color: 'var(--muted)' }}>
                    No journal entries yet.
                  </div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--muted)', opacity: 0.5, marginTop: 4 }}>
                    Your adventures will be recorded here automatically.
                  </div>
                  <button
                    onClick={() => setShowCreateModal(true)}
                    style={{
                      marginTop: 16, display: 'inline-flex', alignItems: 'center', gap: 5,
                      padding: '8px 20px', borderRadius: 4, cursor: 'pointer',
                      background: 'rgba(180,160,80,0.08)', border: '1px solid rgba(180,160,80,0.2)',
                      fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--gold)',
                    }}
                  >
                    <span>+</span> Add Note
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ═══ LOCATIONS TAB ═══ */}
          {activeTab === 'locations' && (
            <div>
              {!selectedCampaignId ? (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.2 }}>⚑</div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 16, color: 'var(--muted)' }}>
                    Select a campaign to view locations
                  </div>
                </div>
              ) : !locations?.length ? (
                <div style={{ textAlign: 'center', padding: '40px 0', fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)', fontStyle: 'italic' }}>
                  No locations discovered yet.
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
                  {locations.map(loc => (
                    <div
                      key={loc.id}
                      style={{
                        padding: '12px 14px', borderRadius: 6,
                        background: 'var(--bg-card)', border: '1px solid var(--border)',
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-strong)'}
                      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: 10, color: loc.is_cleared ? '#6a9a6a' : 'var(--gold)' }}>⚑</span>
                        <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text)', flex: 1 }}>{loc.name}</span>
                        {loc.is_cleared && (
                          <span style={{
                            fontFamily: 'var(--font-mono)', fontSize: 8, color: '#6a9a6a',
                            padding: '1px 5px', borderRadius: 4, background: 'rgba(106,154,106,0.1)',
                            border: '1px solid rgba(106,154,106,0.15)',
                          }}>CLEARED</span>
                        )}
                      </div>
                      {loc.location_type && (
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)', marginBottom: 4, textTransform: 'capitalize' }}>
                          {loc.location_type}
                        </div>
                      )}
                      {loc.description && (
                        <div style={{
                          fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-dim)',
                          lineHeight: 1.5, marginBottom: 6,
                          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                        }}>
                          {loc.description}
                        </div>
                      )}
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--muted)' }}>
                        {loc.visit_count} visit{loc.visit_count !== 1 ? 's' : ''} · Discovered {new Date(loc.created_at).toLocaleDateString()}
                      </div>
                      {loc.notes && (
                        <div style={{
                          marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--border)',
                          fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-dim)', fontStyle: 'italic',
                        }}>
                          {loc.notes}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ═══ EQUIPMENT TAB ═══ */}
          {activeTab === 'equipment' && (
            <div>
              {!selectedCharacterId ? (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.2 }}>⚔</div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 16, color: 'var(--muted)' }}>
                    Select a character to view equipment
                  </div>
                </div>
              ) : !equipment?.length ? (
                <div style={{ textAlign: 'center', padding: '40px 0', fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)', fontStyle: 'italic' }}>
                  No equipment recorded yet.
                </div>
              ) : (
                <div>
                  {/* Currently carried */}
                  {equipment.filter(e => e.status === 'carried').length > 0 && (
                    <div style={{ marginBottom: 24 }}>
                      <div style={{
                        fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                        color: 'var(--text-dim)', letterSpacing: '0.06em', marginBottom: 10,
                      }}>Currently Carried</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
                        {equipment.filter(e => e.status === 'carried').map(item => (
                          <EquipmentCard key={item.id} item={item} />
                        ))}
                      </div>
                    </div>
                  )}
                  {/* Past equipment */}
                  {equipment.filter(e => e.status !== 'carried').length > 0 && (
                    <div>
                      <div style={{
                        fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                        color: 'var(--text-dim)', letterSpacing: '0.06em', marginBottom: 10,
                      }}>Past Equipment</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
                        {equipment.filter(e => e.status !== 'carried').map(item => (
                          <EquipmentCard key={item.id} item={item} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ═══ WORLD EVENTS TAB ═══ */}
          {activeTab === 'world' && (
            <div>
              {!selectedCampaignId ? (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.2 }}>◇</div>
                  <div style={{ fontFamily: 'var(--font-body)', fontSize: 16, color: 'var(--muted)' }}>
                    Select a campaign to view world events
                  </div>
                </div>
              ) : !consequences?.length ? (
                <div style={{ textAlign: 'center', padding: '40px 0', fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)', fontStyle: 'italic' }}>
                  No world events recorded yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {consequences.map(c => (
                    <ConsequenceCard key={c.id} consequence={c} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateEntryModal
          campaignId={selectedCampaignId}
          characterId={selectedCharacterId}
          onClose={() => setShowCreateModal(false)}
        />
      )}
      {editingEntry && (
        <EditEntryModal entry={editingEntry} onClose={() => setEditingEntry(null)} />
      )}
      {deletingEntry && (
        <DeleteConfirmModal
          entry={deletingEntry}
          onClose={() => setDeletingEntry(null)}
          onConfirm={() => deleteMutation.mutate(deletingEntry.id)}
          isPending={deleteMutation.isPending}
        />
      )}
    </>
  )
}

// ─── Equipment Card ───

function EquipmentCard({ item }: { item: EquipmentHistory }) {
  const statusColors: Record<string, string> = {
    carried: '#6a9a6a',
    stored: '#7a9ab8',
    lost: '#c44',
    destroyed: '#a33',
    sold: 'var(--gold-bright)',
    given: 'var(--gold)',
  }

  return (
    <div
      style={{
        padding: '10px 12px', borderRadius: 6,
        background: 'rgba(204,153,0,0.03)', border: '1px solid rgba(204,153,0,0.08)',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(204,153,0,0.2)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(204,153,0,0.08)'}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 3 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10 }}>💰</span>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: '#c90' }}>
            {item.item_name}
            {item.is_magical && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--gold)', marginLeft: 6, opacity: 0.7 }}>MAGICAL</span>
            )}
          </span>
        </div>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: statusColors[item.status] || 'var(--muted)',
          textTransform: 'capitalize',
        }}>
          {item.status}
        </span>
      </div>
      {item.item_type && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)', textTransform: 'capitalize', marginBottom: 2 }}>
          {item.item_type}
        </div>
      )}
      {item.obtained_from && (
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-dim)' }}>
          <span style={{ color: 'var(--muted)' }}>From:</span> {item.obtained_from}
        </div>
      )}
      {item.obtained_location && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--muted)' }}>
          at {item.obtained_location}
        </div>
      )}
      {item.status_details && (
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-dim)', fontStyle: 'italic', marginTop: 4 }}>
          {item.status_details}
        </div>
      )}
      {item.history_entries && item.history_entries.length > 0 && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--border)' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em', color: 'var(--muted)', marginBottom: 3 }}>HISTORY</div>
          {item.history_entries.map((h, i) => (
            <div key={i} style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-dim)', marginBottom: 1 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)' }}>{h.date}:</span> {h.event}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Consequence Card ───

function ConsequenceCard({ consequence }: { consequence: WorldConsequence }) {
  const scopeConfig: Record<string, { color: string; bg: string; border: string }> = {
    local: { color: '#6a9a6a', bg: 'rgba(106,154,106,0.06)', border: 'rgba(106,154,106,0.12)' },
    regional: { color: 'var(--gold)', bg: 'rgba(180,160,80,0.06)', border: 'rgba(180,160,80,0.12)' },
    global: { color: '#c44', bg: 'rgba(204,68,68,0.06)', border: 'rgba(204,68,68,0.12)' },
  }
  const sc = scopeConfig[consequence.scope] || scopeConfig.local

  return (
    <div style={{
      padding: '12px 14px', borderRadius: 6,
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      transition: 'all 0.15s',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9, color: sc.color,
          padding: '1px 6px', borderRadius: 4, background: sc.bg, border: `1px solid ${sc.border}`,
          textTransform: 'capitalize',
        }}>
          {consequence.scope}
        </span>
        {!consequence.is_permanent && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, color: '#7a9ab8',
            padding: '1px 6px', borderRadius: 4, background: 'rgba(122,154,184,0.06)',
            border: '1px solid rgba(122,154,184,0.12)',
          }}>Temporary</span>
        )}
        {!consequence.is_active && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)', marginLeft: 'auto' }}>Resolved</span>
        )}
      </div>

      <div style={{ marginBottom: 6 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em', color: 'var(--muted)', marginBottom: 2 }}>ACTION</div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text)' }}>
          {consequence.trigger_action}
        </div>
      </div>

      <div style={{ marginBottom: 6 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.12em', color: 'var(--muted)', marginBottom: 2 }}>CONSEQUENCE</div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-dim)' }}>
          {consequence.consequence}
        </div>
      </div>

      {(consequence.affected_npcs.length > 0 || consequence.affected_locations.length > 0 || consequence.affected_factions.length > 0) && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
          {consequence.affected_npcs.map((npc, i) => (
            <span key={`npc-${i}`} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
              padding: '1px 6px', borderRadius: 4, background: 'rgba(180,160,100,0.04)',
              border: '1px solid var(--border)',
            }}>{npc}</span>
          ))}
          {consequence.affected_locations.map((loc, i) => (
            <span key={`loc-${i}`} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
              padding: '1px 6px', borderRadius: 4, background: 'rgba(180,160,100,0.04)',
              border: '1px solid var(--border)',
            }}>{loc}</span>
          ))}
          {consequence.affected_factions.map((f, i) => (
            <span key={`fac-${i}`} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)',
              padding: '1px 6px', borderRadius: 4, background: 'rgba(180,160,100,0.04)',
              border: '1px solid var(--border)',
            }}>{f}</span>
          ))}
        </div>
      )}

      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--muted)', marginTop: 6, opacity: 0.5 }}>
        {new Date(consequence.created_at).toLocaleDateString()}
      </div>
    </div>
  )
}
