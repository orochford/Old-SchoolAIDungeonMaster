import { useState, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { DungeonGraph } from '@/components/graph/DungeonGraph'
import { ArrowLeft, AlertTriangle, ChevronDown, ChevronUp, RefreshCw, Wand2, Sword, Users, Gem, EyeOff } from 'lucide-react'

interface GraphValidationReport {
  dangling_exits: Array<{
    from_id: string
    from_name: string
    direction: string
    missing_target: string
  }>
  orphan_locations: Array<{
    id: string
    name: string
  }>
  total_locations: number
  total_connections: number
}

interface GraphVisualizationResponse {
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
  validation_report?: GraphValidationReport | null
}

export function GraphMapPage() {
  const { moduleId } = useParams<{ moduleId: string }>()
  const queryClient = useQueryClient()
  const [showValidationDetails, setShowValidationDetails] = useState(false)
  const [rebuildStatus, setRebuildStatus] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['module-graph', moduleId],
    queryFn: () => api.get<GraphVisualizationResponse>(`/adventures/${moduleId}/graph`),
    enabled: !!moduleId,
    refetchOnMount: 'always',
  })

  const rebuildMutation = useMutation({
    mutationFn: () => api.post<{ locations: number }>(`/adventures/${moduleId}/rebuild-graph`),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['module-graph', moduleId] })
      setRebuildStatus(`Graph rebuilt (${result.locations} locations).`)
      setTimeout(() => setRebuildStatus(null), 8000)
    },
    onError: (err) => {
      setRebuildStatus(`Rebuild failed: ${err.message}`)
      setTimeout(() => setRebuildStatus(null), 5000)
    },
  })

  interface ExtractResult {
    message: string
    extracted: number
    extracted_names?: string[]
    not_found: number
    remaining_dangling?: number
    total_locations?: number
    reachable_from_start?: number
    corridors_added?: number
    map_corridors_added?: number
    reconciliation_changes?: number
  }

  const sweepingRef = useRef(false)
  const [sweepProgress, setSweepProgress] = useState<string | null>(null)

  const runSweep = useCallback(async () => {
    if (sweepingRef.current) return
    sweepingRef.current = true
    const MAX_SWEEPS = 5
    let sweep = 0
    let totalExtracted = 0
    const allNames: string[] = []

    try {
      while (sweep < MAX_SWEEPS) {
        sweep++
        setSweepProgress(`Sweep ${sweep}/${MAX_SWEEPS}...`)
        setRebuildStatus(`Running sweep ${sweep}...`)

        const result = await api.post<ExtractResult>(`/adventures/${moduleId}/extract-missing-rooms`)
        totalExtracted += result.extracted
        if (result.extracted_names) allNames.push(...result.extracted_names)

        queryClient.invalidateQueries({ queryKey: ['module-graph', moduleId] })

        const dangling = result.remaining_dangling ?? 0
        const total = result.total_locations ?? 0
        const reachable = result.reachable_from_start ?? 0
        const madeProgress = result.extracted > 0 || (result.corridors_added ?? 0) > 0
          || (result.map_corridors_added ?? 0) > 0 || (result.reconciliation_changes ?? 0) > 0

        // Stop if fully connected with no dangling exits, or no progress made
        if ((dangling === 0 && reachable === total) || !madeProgress) {
          break
        }
      }

      let msg = `Sweep complete (${sweep} pass${sweep > 1 ? 'es' : ''}). Extracted ${totalExtracted} room(s).`
      if (allNames.length > 0) msg += ` Rooms: ${allNames.join(', ')}.`
      setRebuildStatus(msg)
      setTimeout(() => setRebuildStatus(null), 15000)
    } catch (err) {
      setRebuildStatus(`Sweep failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
      setTimeout(() => setRebuildStatus(null), 5000)
    } finally {
      sweepingRef.current = false
      setSweepProgress(null)
    }
  }, [moduleId, queryClient])

  const extractMutation = useMutation({
    mutationFn: () => api.post<ExtractResult>(`/adventures/${moduleId}/extract-missing-rooms`),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['module-graph', moduleId] })
      const names = result.extracted_names?.join(', ') || ''
      let msg = `Extracted ${result.extracted} room(s)`
      if (names) msg += `: ${names}`
      if (result.not_found > 0) msg += `. ${result.not_found} could not be found in source text.`
      if (result.remaining_dangling != null && result.remaining_dangling > 0) {
        msg += ` ${result.remaining_dangling} dangling exit(s) remain.`
      } else if (result.remaining_dangling === 0) {
        msg += ' All exits now resolved!'
      }
      setRebuildStatus(msg)
      setTimeout(() => setRebuildStatus(null), 12000)
    },
    onError: (err) => {
      setRebuildStatus(`Extraction failed: ${err.message}`)
      setTimeout(() => setRebuildStatus(null), 5000)
    },
  })

  const validation = data?.validation_report
  const hasDanglingExits = validation && validation.dangling_exits.length > 0

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Minimal header bar */}
      <div
        className="flex items-center gap-3 px-4 py-2 flex-shrink-0"
        style={{
          background: '#0f0d0a',
          borderBottom: '1px solid rgba(180,160,100,0.1)',
        }}
      >
        <Link
          to="/campaigns"
          className="flex items-center gap-1.5 text-[#6a6250] hover:text-[#b8a060] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="font-['Crimson_Text',serif] text-sm">Back</span>
        </Link>
        <div className="w-px h-4 bg-[rgba(180,160,100,0.15)]" />
        <span className="font-['Cinzel',serif] text-sm text-[#c8c0aa]">
          Dungeon Map
        </span>

        {/* Legend */}
        <div className="ml-auto flex items-center gap-3">
          <LegendIcon icon={<Sword className="w-3 h-3 text-red-400/70" />} label="Creatures" />
          <LegendIcon icon={<Users className="w-3 h-3 text-blue-400/70" />} label="NPCs" />
          <LegendIcon icon={<Gem className="w-3 h-3 text-amber-400/70" />} label="Items" />
          <LegendIcon icon={<AlertTriangle className="w-3 h-3 text-orange-400/70" />} label="Traps" />
          <LegendIcon icon={<EyeOff className="w-3 h-3 text-purple-400/70" />} label="Secrets" />
          <div className="w-px h-3 bg-[rgba(180,160,100,0.15)]" />
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0 border-t border-dashed border-purple-400/50" />
            <span className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#6a6250]">Secret</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1 h-3 rounded-sm bg-green-500/60" />
            <div className="w-1 h-3 rounded-sm bg-amber-500/60" />
            <div className="w-1 h-3 rounded-sm bg-red-500/60" />
            <span className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#6a6250]">Difficulty</span>
          </div>
          <div className="flex items-center gap-1">
            <span
              className="font-['IBM_Plex_Mono',monospace] text-[8px] uppercase tracking-widest px-1 py-0.5 rounded"
              style={{ background: 'rgba(212,160,32,0.15)', color: '#d4a020', border: '1px solid rgba(212,160,32,0.3)' }}
            >
              Ent
            </span>
            <span className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#6a6250]">Entrance</span>
          </div>
        </div>
      </div>

      {/* Validation warning banner */}
      {hasDanglingExits && (
        <div
          className="px-4 py-2 flex-shrink-0"
          style={{
            background: 'rgba(196,140,40,0.08)',
            borderBottom: '1px solid rgba(196,140,40,0.2)',
          }}
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500/80 flex-shrink-0" />
            <span className="font-['Crimson_Text',serif] text-sm text-amber-400/90 flex-1">
              {validation.dangling_exits.length} exit(s) reference rooms not found in the extraction
            </span>
            <button
              onClick={() => setShowValidationDetails(!showValidationDetails)}
              className="flex items-center gap-1 text-[#6a6250] hover:text-[#c8c0aa] transition-colors"
            >
              <span className="font-['IBM_Plex_Mono',monospace] text-[10px]">Details</span>
              {showValidationDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            <button
              onClick={() => extractMutation.mutate()}
              disabled={extractMutation.isPending || rebuildMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1 rounded text-sm transition-all"
              style={{
                background: 'rgba(140,100,196,0.1)',
                border: '1px solid rgba(140,100,196,0.25)',
                color: '#b090d0',
              }}
            >
              <Wand2 className={`w-3 h-3 ${extractMutation.isPending ? 'animate-pulse' : ''}`} />
              <span className="font-['Crimson_Text',serif]">
                {extractMutation.isPending ? 'Extracting...' : 'Extract Missing Rooms'}
              </span>
            </button>
            <button
              onClick={() => rebuildMutation.mutate()}
              disabled={rebuildMutation.isPending || extractMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1 rounded text-sm transition-all"
              style={{
                background: 'rgba(180,160,100,0.1)',
                border: '1px solid rgba(180,160,100,0.2)',
                color: '#b8a060',
              }}
            >
              <RefreshCw className={`w-3 h-3 ${rebuildMutation.isPending ? 'animate-spin' : ''}`} />
              <span className="font-['Crimson_Text',serif]">Rebuild Graph</span>
            </button>
          </div>
          {showValidationDetails && (
            <div className="mt-2 ml-6 space-y-1">
              {validation.dangling_exits.map((de, i) => (
                <div
                  key={i}
                  className="font-['IBM_Plex_Mono',monospace] text-[11px] text-[#8a8270]"
                >
                  {de.from_name} ({de.from_id}) &rarr; {de.direction} &rarr;{' '}
                  <span className="text-amber-400/70">Room {de.missing_target}</span>{' '}
                  <span className="text-[#6a6250]">(missing)</span>
                </div>
              ))}
              {validation.orphan_locations.length > 0 && (
                <div className="mt-1 font-['IBM_Plex_Mono',monospace] text-[11px] text-[#6a6250]">
                  + {validation.orphan_locations.length} orphan location(s) with no connections
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Rebuild status message */}
      {rebuildStatus && (
        <div
          className="px-4 py-1.5 flex-shrink-0 font-['Crimson_Text',serif] text-xs"
          style={{
            background: 'rgba(90,138,90,0.08)',
            borderBottom: '1px solid rgba(90,138,90,0.2)',
            color: rebuildStatus.includes('failed') ? '#c44' : '#5a8a5a',
          }}
        >
          {rebuildStatus}
        </div>
      )}

      {/* Graph area */}
      <div className="flex-1 relative">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="font-['Cinzel',serif] text-lg text-[#6a6250] mb-2">Loading dungeon map...</div>
              <div className="w-32 h-0.5 mx-auto bg-[#1a1816] rounded overflow-hidden">
                <div className="h-full bg-[#b8a060] animate-pulse rounded" style={{ width: '60%' }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="text-4xl mb-3 opacity-30">&#x26A0;</div>
              <div className="font-['Cinzel',serif] text-lg text-[#c8c0aa] mb-2">Map Unavailable</div>
              <p className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                The knowledge graph for this module hasn't been built yet. Try rebuilding it from the sourcebooks page.
              </p>
            </div>
          </div>
        )}

        {data && (
          <DungeonGraph
            moduleId={data.module_id}
            moduleTitle={data.module_title}
            nodes={data.nodes}
            edges={data.edges}
          />
        )}
      </div>
    </div>
  )
}

function LegendIcon({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-1">
      {icon}
      <span className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#6a6250]">{label}</span>
    </div>
  )
}
