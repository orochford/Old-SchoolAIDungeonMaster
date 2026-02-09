import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { DungeonGraph } from './DungeonGraph'

interface PlayerGraphResponse {
  module_id: string
  module_title: string
  nodes: Array<{
    id: string
    key: string
    name: string
    dungeon_level: number
    is_empty: boolean
    has_creatures: boolean
    has_items: boolean
    has_traps: boolean
    has_secrets: boolean
    has_npcs: boolean
    is_entrance?: boolean
    creature_summary?: string
    encounter_hd_total?: number
  }>
  edges: Array<{
    from_id: string
    to_id: string
    direction: string
    is_secret: boolean
    is_one_way: boolean
  }>
  current_location_key: string | null
  visited_count: number
  total_locations: number
}

interface PlayerMapPanelProps {
  moduleId: string
  sessionId: string
  currentLocationKey?: string | null
}

export function PlayerMapPanel({ moduleId, sessionId, currentLocationKey }: PlayerMapPanelProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-graph', moduleId, sessionId, currentLocationKey],
    queryFn: () => api.get<PlayerGraphResponse>(
      `/adventures/${moduleId}/graph/player?session_id=${sessionId}`
    ),
    enabled: !!moduleId && !!sessionId,
    refetchInterval: false,
  })

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 200,
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: "var(--font-heading, 'Cinzel', serif)", fontSize: 13, color: '#6a6250' }}>
            Loading map...
          </div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 200,
          padding: 16,
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.3 }}>🗺️</div>
          <div style={{ fontFamily: "var(--font-body, 'Crimson Text', serif)", fontSize: 12, fontStyle: 'italic', color: '#6a6250' }}>
            Map will appear as you explore.
          </div>
        </div>
      </div>
    )
  }

  if (data.nodes.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 200,
          padding: 16,
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.3 }}>🗺️</div>
          <div style={{ fontFamily: "var(--font-body, 'Crimson Text', serif)", fontSize: 12, fontStyle: 'italic', color: '#6a6250' }}>
            No locations discovered yet.
          </div>
          <div style={{ fontFamily: "var(--font-body, 'Crimson Text', serif)", fontSize: 11, color: '#4a4840', marginTop: 4 }}>
            Map will fill in as you explore the dungeon.
          </div>
        </div>
      </div>
    )
  }

  const effectiveCurrentKey = currentLocationKey || data.current_location_key

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 300 }}>
      <div
        style={{
          fontFamily: "var(--font-mono, 'IBM Plex Mono', monospace)",
          fontSize: 10,
          color: '#6a6250',
          padding: '4px 0',
          textAlign: 'center',
        }}
      >
        {data.visited_count} / {data.total_locations} rooms discovered
      </div>
      <div style={{ width: '100%', height: 'calc(100% - 24px)' }}>
        <DungeonGraph
          moduleId={data.module_id}
          moduleTitle={data.module_title}
          nodes={data.nodes}
          edges={data.edges}
          playerView
          currentLocationKey={effectiveCurrentKey}
        />
      </div>
    </div>
  )
}
