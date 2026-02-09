import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { X, Sword, Gem, AlertTriangle, EyeOff, Users, DoorOpen, Scroll, ChevronDown, ChevronUp, Coins } from 'lucide-react'

interface LocationContext {
  location: {
    id: string
    location_key: string
    name: string
    dm_description: string
    read_aloud_text: string | null
    features: Array<{ name?: string; details?: string; description?: string }>
    exits: Record<string, string>
    traps: Array<{ name?: string; description?: string; effect?: string; trigger?: string }>
    secrets: Array<{ type?: string; name?: string; description?: string; detection?: string }>
    treasure: Array<{ item?: string; value?: string; location?: string }>
    dungeon_level: number
  }
  npcs: Array<{
    id: string
    name: string
    title: string | null
    description: string | null
    initial_disposition: string
  }>
  encounters: Array<{
    id: string
    name: string
    description: string | null
    creatures: Array<{ name?: string; count?: number; hd?: string }>
    tactics: string | null
  }>
  items: Array<{
    id: string
    name: string
    description: string | null
    is_magical: boolean
    is_key_item: boolean
  }>
  connected_locations: Array<{
    location_key: string
    name: string
  }>
}

interface NodeDetailPanelProps {
  moduleId: string
  locationKey: string
  onClose: () => void
}

const DESC_TRUNCATE = 400

export function NodeDetailPanel({ moduleId, locationKey, onClose }: NodeDetailPanelProps) {
  const [descExpanded, setDescExpanded] = useState(false)

  // Reset expansion when switching nodes
  const [prevKey, setPrevKey] = useState(locationKey)
  if (prevKey !== locationKey) {
    setPrevKey(locationKey)
    setDescExpanded(false)
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['location-context', moduleId, locationKey],
    queryFn: () => api.get<LocationContext>(`/adventures/${moduleId}/locations/${locationKey}`),
  })

  const desc = data?.location.dm_description || ''
  const isLongDesc = desc.length > DESC_TRUNCATE
  const displayDesc = descExpanded || !isLongDesc ? desc : desc.slice(0, DESC_TRUNCATE) + '...'

  return (
    <div
      className="absolute top-4 right-4 w-[380px] max-h-[calc(100%-2rem)] overflow-y-auto rounded-lg z-10"
      style={{
        background: '#141210',
        border: '1px solid rgba(180,160,100,0.2)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
      }}
    >
      {/* Header */}
      <div
        className="sticky top-0 flex items-center justify-between px-4 py-3 z-10"
        style={{
          background: '#1a1816',
          borderBottom: '1px solid rgba(180,160,100,0.15)',
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="font-['IBM_Plex_Mono',monospace] text-[11px] font-bold px-2 py-0.5 rounded flex-shrink-0"
            style={{
              background: 'rgba(180,160,100,0.12)',
              color: '#b8a060',
              border: '1px solid rgba(180,160,100,0.2)',
            }}
          >
            {locationKey}
          </span>
          <h3 className="font-['Cinzel',serif] text-sm font-semibold text-[#c8c0aa] truncate">
            {data?.location.name || locationKey}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="text-[#6a6250] hover:text-[#c8c0aa] transition-colors flex-shrink-0 ml-2"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {isLoading && (
          <div className="text-[#6a6250] font-['Crimson_Text',serif] text-sm text-center py-8">
            Loading...
          </div>
        )}

        {error && (
          <div className="text-red-400/70 font-['Crimson_Text',serif] text-sm text-center py-8">
            Failed to load location details.
          </div>
        )}

        {data && (
          <>
            {/* Read-aloud text */}
            {data.location.read_aloud_text && (
              <div
                className="p-3 rounded text-sm font-['Crimson_Text',serif] italic leading-relaxed"
                style={{
                  background: 'rgba(180,160,100,0.04)',
                  borderLeft: '3px solid rgba(180,160,100,0.3)',
                  color: '#a09880',
                }}
              >
                {data.location.read_aloud_text}
              </div>
            )}

            {/* DM Description (truncated) */}
            <div>
              <p className="text-[#8a8270] font-['Crimson_Text',serif] text-sm leading-relaxed">
                {displayDesc}
              </p>
              {isLongDesc && (
                <button
                  onClick={() => setDescExpanded(!descExpanded)}
                  className="flex items-center gap-1 mt-1 text-[#b8a060] font-['Crimson_Text',serif] text-xs hover:text-[#d4b870] transition-colors"
                >
                  {descExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  {descExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>

            {/* Features */}
            {data.location.features.length > 0 && (
              <Section icon={<Scroll className="w-3.5 h-3.5 text-[#b8a060]/70" />} title="Features">
                {data.location.features.map((feat, i) => (
                  <div key={i} className="mb-2 last:mb-0">
                    <div className="font-['Cinzel',serif] text-xs font-semibold text-[#c8c0aa]">
                      {feat.name || 'Feature'}
                    </div>
                    {(feat.details || feat.description) && (
                      <p className="font-['Crimson_Text',serif] text-xs text-[#8a8270] mt-0.5">
                        {feat.details || feat.description}
                      </p>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* Encounters / Creatures */}
            {data.encounters.length > 0 && (
              <Section icon={<Sword className="w-3.5 h-3.5 text-red-400/70" />} title="Encounters">
                {data.encounters.map((enc) => (
                  <div key={enc.id} className="mb-2 last:mb-0">
                    <div className="font-['Cinzel',serif] text-xs font-semibold text-[#c8c0aa]">
                      {enc.name}
                    </div>
                    {enc.creatures.length > 0 && (
                      <div className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250] mt-0.5">
                        {enc.creatures.map((c) => `${c.count || 1}x ${c.name || '?'} (HD ${c.hd || '?'})`).join(', ')}
                      </div>
                    )}
                    {enc.tactics && (
                      <p className="font-['Crimson_Text',serif] text-xs text-[#8a8270] mt-0.5 italic">
                        {enc.tactics}
                      </p>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* NPCs */}
            {data.npcs.length > 0 && (
              <Section icon={<Users className="w-3.5 h-3.5 text-blue-400/70" />} title="NPCs">
                {data.npcs.map((npc) => (
                  <div key={npc.id} className="mb-2 last:mb-0">
                    <div className="font-['Cinzel',serif] text-xs font-semibold text-[#c8c0aa]">
                      {npc.name}
                      {npc.title && <span className="font-normal text-[#6a6250]"> — {npc.title}</span>}
                    </div>
                    {npc.description && (
                      <p className="font-['Crimson_Text',serif] text-xs text-[#8a8270] mt-0.5">
                        {npc.description}
                      </p>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* Items (from encounter/item tables) */}
            {data.items.length > 0 && (
              <Section icon={<Gem className="w-3.5 h-3.5 text-amber-400/70" />} title="Items">
                {data.items.map((item) => (
                  <div key={item.id} className="flex items-start gap-1.5 mb-1 last:mb-0">
                    <span className="font-['Cinzel',serif] text-xs text-[#c8c0aa]">
                      {item.name}
                      {item.is_magical && <span className="text-purple-400/70 ml-1">*</span>}
                      {item.is_key_item && <span className="text-amber-400/70 ml-1">!</span>}
                    </span>
                  </div>
                ))}
              </Section>
            )}

            {/* Treasure (from location inline) */}
            {data.location.treasure.length > 0 && (
              <Section icon={<Coins className="w-3.5 h-3.5 text-yellow-500/70" />} title="Treasure">
                {data.location.treasure.map((t, i) => (
                  <div key={i} className="flex items-start gap-2 mb-1.5 last:mb-0">
                    <span className="font-['Cinzel',serif] text-xs text-[#c8c0aa]">
                      {t.item || 'Treasure'}
                    </span>
                    {t.value && (
                      <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#b8a060]">
                        {t.value}
                      </span>
                    )}
                    {t.location && (
                      <span className="font-['Crimson_Text',serif] text-[10px] text-[#6a6250] italic">
                        ({t.location})
                      </span>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* Traps */}
            {data.location.traps.length > 0 && (
              <Section icon={<AlertTriangle className="w-3.5 h-3.5 text-orange-400/70" />} title="Traps">
                {data.location.traps.map((trap, i) => (
                  <div key={i} className="mb-2 last:mb-0">
                    <div className="font-['Cinzel',serif] text-xs font-semibold text-[#c8c0aa]">
                      {trap.name || 'Trap'}
                    </div>
                    {trap.trigger && (
                      <div className="font-['Crimson_Text',serif] text-[10px] text-[#6a6250] mt-0.5">
                        Trigger: {trap.trigger}
                      </div>
                    )}
                    {trap.effect && (
                      <p className="font-['Crimson_Text',serif] text-xs text-[#8a8270] mt-0.5">
                        {trap.effect}
                      </p>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* Secrets */}
            {data.location.secrets.length > 0 && (
              <Section icon={<EyeOff className="w-3.5 h-3.5 text-purple-400/70" />} title="Secrets">
                {data.location.secrets.map((secret, i) => (
                  <div key={i} className="mb-2 last:mb-0">
                    <div className="font-['Cinzel',serif] text-xs font-semibold text-[#c8c0aa]">
                      {secret.type || secret.name || 'Secret'}
                    </div>
                    {secret.description && (
                      <p className="font-['Crimson_Text',serif] text-xs text-[#8a8270] mt-0.5">
                        {secret.description}
                      </p>
                    )}
                    {secret.detection && (
                      <div className="font-['Crimson_Text',serif] text-[10px] text-[#6a6250] mt-0.5 italic">
                        Detection: {secret.detection}
                      </div>
                    )}
                  </div>
                ))}
              </Section>
            )}

            {/* Exits */}
            {Object.keys(data.location.exits).length > 0 && (
              <Section icon={<DoorOpen className="w-3.5 h-3.5 text-[#6a6250]" />} title="Exits">
                {Object.entries(data.location.exits).map(([dir, dest]) => (
                  <div key={dir} className="flex items-center gap-2 mb-1 last:mb-0">
                    <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#b8a060] uppercase w-8">
                      {dir}
                    </span>
                    <span className="font-['Crimson_Text',serif] text-xs text-[#8a8270]">
                      {dest}
                    </span>
                  </div>
                ))}
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="flex items-center gap-1.5 mb-2 pb-1"
        style={{ borderBottom: '1px solid rgba(180,160,100,0.1)' }}
      >
        {icon}
        <span className="font-['Cinzel',serif] text-[11px] font-semibold text-[#8a8270] tracking-wide uppercase">
          {title}
        </span>
      </div>
      {children}
    </div>
  )
}
