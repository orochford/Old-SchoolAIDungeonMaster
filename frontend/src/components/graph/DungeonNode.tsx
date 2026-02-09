import { memo, useState } from 'react'
import { Handle, Position } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'
import { Sword, Gem, AlertTriangle, EyeOff, Users, MapPin } from 'lucide-react'

export interface DungeonNodeData {
  key: string
  name: string
  isEmpty: boolean
  hasCreatures: boolean
  hasItems: boolean
  hasTraps: boolean
  hasSecrets: boolean
  hasNpcs: boolean
  dungeonLevel?: number
  isEntrance?: boolean
  creatureSummary?: string
  encounterHdTotal?: number
  selected: boolean
  playerView?: boolean
  isCurrentLocation?: boolean
  isMystery?: boolean
  [key: string]: unknown
}

function DungeonNodeComponent({ data }: NodeProps) {
  const {
    key: roomKey,
    name,
    isEmpty,
    hasCreatures,
    hasItems,
    hasTraps,
    hasSecrets,
    hasNpcs,
    dungeonLevel,
    isEntrance,
    creatureSummary,
    encounterHdTotal,
    selected,
    playerView,
    isCurrentLocation,
    isMystery,
  } = data as unknown as DungeonNodeData

  const [hovered, setHovered] = useState(false)

  const hasAnyIndicator = !playerView && (hasCreatures || hasItems || hasTraps || hasSecrets || hasNpcs)

  // Build tooltip lines
  const tooltipLines: string[] = []
  if (!playerView) {
    if (creatureSummary) tooltipLines.push(creatureSummary)
    if (encounterHdTotal && encounterHdTotal > 0) {
      const diff = encounterHdTotal >= 11 ? 'Dangerous' : encounterHdTotal >= 5 ? 'Moderate' : 'Easy'
      tooltipLines.push(`${diff} (${encounterHdTotal} HD)`)
    }
    const contents: string[] = []
    if (hasItems) contents.push('Items')
    if (hasTraps) contents.push('Traps')
    if (hasSecrets) contents.push('Secrets')
    if (hasNpcs) contents.push('NPCs')
    if (contents.length > 0) tooltipLines.push(contents.join(' \u00b7 '))
    if (isEmpty) tooltipLines.push('Empty room')
  }
  const showTooltip = hovered && !selected && tooltipLines.length > 0

  // Mystery node for undiscovered adjacent rooms
  if (isMystery) {
    return (
      <>
        <Handle type="target" position={Position.Top} className="!bg-[#3a3830] !border-none !w-2 !h-2" />
        <div
          className="px-3 py-2 rounded-lg min-w-[80px] text-center"
          style={{
            background: '#0f0e0c',
            border: '1px dashed rgba(100,95,80,0.3)',
            opacity: 0.5,
          }}
        >
          <span className="font-['Cinzel',serif] text-lg font-bold text-[#4a4840]">?</span>
        </div>
        <Handle type="source" position={Position.Bottom} className="!bg-[#3a3830] !border-none !w-2 !h-2" />
      </>
    )
  }

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-[#6a6250] !border-none !w-2 !h-2" />
      <div
        className="relative px-3 py-2 rounded-lg min-w-[180px] transition-all duration-200"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          background: isEmpty ? '#12110f' : '#1a1816',
          border: isCurrentLocation
            ? '2px solid #d4a020'
            : selected
              ? '2px solid #d4b870'
              : isEmpty
                ? '1px dashed rgba(180,160,100,0.15)'
                : '1px solid rgba(180,160,100,0.25)',
          boxShadow: isCurrentLocation
            ? '0 0 24px rgba(212,160,32,0.25), 0 0 8px rgba(212,160,32,0.15), 0 4px 12px rgba(0,0,0,0.4)'
            : selected
              ? '0 0 20px rgba(212,184,112,0.15), 0 4px 12px rgba(0,0,0,0.4)'
              : '0 2px 8px rgba(0,0,0,0.3)',
          opacity: isEmpty ? 0.6 : 1,
        }}
      >
        {/* Encounter difficulty indicator - colored left border strip */}
        {!!(encounterHdTotal && encounterHdTotal > 0 && !playerView) && (
          <div
            className="absolute left-0 top-0 bottom-0 w-1 rounded-l"
            style={{
              background: encounterHdTotal >= 11 ? '#dc2626' : encounterHdTotal >= 5 ? '#d97706' : '#16a34a',
              opacity: 0.6,
            }}
          />
        )}

        {/* Entrance badge */}
        {isEntrance && (
          <div className="mb-1">
            <span
              className="font-['IBM_Plex_Mono',monospace] text-[8px] uppercase tracking-widest px-1.5 py-0.5 rounded"
              style={{
                background: 'rgba(212,160,32,0.15)',
                color: '#d4a020',
                border: '1px solid rgba(212,160,32,0.3)',
              }}
            >
              Entrance
            </span>
          </div>
        )}

        {/* Room key badge + level badge + name */}
        <div className="flex items-start gap-2 mb-1">
          {isCurrentLocation && (
            <MapPin className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
          )}
          <span
            className="font-['IBM_Plex_Mono',monospace] text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{
              background: isCurrentLocation ? 'rgba(212,160,32,0.2)' : 'rgba(180,160,100,0.12)',
              color: isCurrentLocation ? '#d4a020' : '#b8a060',
              border: `1px solid ${isCurrentLocation ? 'rgba(212,160,32,0.3)' : 'rgba(180,160,100,0.2)'}`,
            }}
          >
            {roomKey}
          </span>
          {dungeonLevel != null && (
            <span
              className="font-['IBM_Plex_Mono',monospace] text-[9px] px-1 py-0.5 rounded"
              style={{
                background: 'rgba(100,140,200,0.1)',
                color: '#7a9cc0',
                border: '1px solid rgba(100,140,200,0.15)',
              }}
            >
              L{dungeonLevel}
            </span>
          )}
          <span
            className="font-['Cinzel',serif] text-xs font-semibold leading-tight flex-1"
            style={{ color: isEmpty ? '#6a6250' : '#c8c0aa' }}
          >
            {name}
          </span>
        </div>

        {/* Creature summary - hidden in player view */}
        {creatureSummary && !playerView && (
          <div className="font-['IBM_Plex_Mono',monospace] text-[9px] text-red-400/60 mt-0.5 truncate max-w-[180px]">
            {creatureSummary}
          </div>
        )}

        {/* Indicator icons - hidden in player view */}
        {hasAnyIndicator && (
          <div className="flex gap-2 mt-1.5 pt-1.5" style={{ borderTop: '1px solid rgba(180,160,100,0.1)' }}>
            {hasCreatures && <Sword className="w-3.5 h-3.5 text-red-400/70" />}
            {hasNpcs && <Users className="w-3.5 h-3.5 text-blue-400/70" />}
            {hasItems && <Gem className="w-3.5 h-3.5 text-amber-400/70" />}
            {hasTraps && <AlertTriangle className="w-3.5 h-3.5 text-orange-400/70" />}
            {hasSecrets && <EyeOff className="w-3.5 h-3.5 text-purple-400/70" />}
          </div>
        )}

        {/* Hover tooltip */}
        {showTooltip && (
          <div
            className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-3 py-2 rounded-lg pointer-events-none z-50 whitespace-nowrap"
            style={{
              background: '#1e1c18',
              border: '1px solid rgba(180,160,100,0.25)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
            }}
          >
            <div className="font-['Cinzel',serif] text-[11px] font-semibold text-[#c8c0aa] mb-1">
              {roomKey}. {name}
            </div>
            {tooltipLines.map((line, i) => (
              <div key={i} className="font-['IBM_Plex_Mono',monospace] text-[9px] text-[#8a8270]">
                {line}
              </div>
            ))}
            {/* Tooltip arrow */}
            <div
              className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0"
              style={{
                borderLeft: '5px solid transparent',
                borderRight: '5px solid transparent',
                borderTop: '5px solid rgba(180,160,100,0.25)',
              }}
            />
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-[#6a6250] !border-none !w-2 !h-2" />
    </>
  )
}

export const DungeonNode = memo(DungeonNodeComponent)
