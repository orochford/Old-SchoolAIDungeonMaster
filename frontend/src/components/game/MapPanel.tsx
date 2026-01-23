import { useState } from 'react'
import { Map, Maximize2, Minimize2, X, Navigation, MapPin, ScrollText } from 'lucide-react'
import { DungeonMap } from './DungeonMap'

interface Marker {
  id: string
  x: number
  y: number
  symbol: string
  label: string
  type: string
  description?: string
  visited?: boolean
  notes?: string
}

interface MapData {
  map_id: string
  map_name: string
  rendered_map: string
  width: number
  height: number
  player_position: { x: number; y: number } | null
  markers: Marker[]
  exploration_progress?: string
}

interface Props {
  mapData: MapData | null
  onClose?: () => void
  onNavigateTo?: (location: string) => void
}

export function MapPanel({ mapData, onClose, onNavigateTo }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedMarker, setSelectedMarker] = useState<Marker | null>(null)

  // Handle clicking on a cell - find if there's a marker there
  const handleCellClick = (x: number, y: number) => {
    if (!mapData) return
    const marker = mapData.markers.find(m => m.x === x && m.y === y)
    if (marker) {
      setSelectedMarker(marker)
    }
  }

  // Handle navigating to a location
  const handleNavigate = (location: string) => {
    onNavigateTo?.(location)
    setSelectedMarker(null)
    setIsExpanded(false)
  }

  if (!mapData) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <Map className="w-4 h-4 text-parchment-400" />
          <h3 className="font-display text-sm text-parchment-100">Map</h3>
        </div>
        <p className="text-parchment-500 text-xs italic">
          No map available for this area.
        </p>
      </div>
    )
  }

  const expandedView = (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-dungeon-900/90 backdrop-blur-sm">
      <div className="bg-dungeon-800 border border-parchment-700 rounded-lg shadow-2xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-dungeon-600 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Map className="w-5 h-5 text-parchment-400" />
            <h2 className="font-display text-lg text-parchment-100">
              {mapData.map_name}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsExpanded(false)}
              className="text-parchment-500 hover:text-parchment-200 transition-colors p-1"
              title="Minimize"
            >
              <Minimize2 className="w-5 h-5" />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="text-parchment-500 hover:text-parchment-200 transition-colors p-1"
                title="Close"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        </div>

        {/* Main content area - map and sidebar */}
        <div className="flex-1 overflow-hidden flex">
          {/* Map */}
          <div className="flex-1 overflow-auto p-4">
            <div className="bg-dungeon-900 rounded-lg p-4 inline-block min-w-full">
              <DungeonMap mapData={mapData} onCellClick={handleCellClick} />
            </div>
          </div>

          {/* Location Sidebar */}
          <div className="w-64 border-l border-dungeon-600 bg-dungeon-850 overflow-y-auto">
            {/* Selected location details */}
            {selectedMarker && (
              <div className="p-3 border-b border-dungeon-600">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-display text-parchment-100 text-sm">
                    {selectedMarker.label}
                  </h4>
                  <button
                    onClick={() => setSelectedMarker(null)}
                    className="text-parchment-500 hover:text-parchment-200"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                {selectedMarker.description && (
                  <p className="text-parchment-400 text-xs mb-2">
                    {selectedMarker.description}
                  </p>
                )}
                {selectedMarker.notes && (
                  <div className="text-parchment-500 text-xs italic mb-2 border-l-2 border-dungeon-500 pl-2">
                    {selectedMarker.notes}
                  </div>
                )}
                {onNavigateTo && (
                  <button
                    onClick={() => handleNavigate(selectedMarker.label)}
                    className="w-full btn btn-primary text-xs py-1 flex items-center justify-center gap-1"
                  >
                    <Navigation className="w-3 h-3" />
                    Go to {selectedMarker.label}
                  </button>
                )}
              </div>
            )}

            {/* List of all markers */}
            <div className="p-3">
              <h4 className="font-display text-parchment-200 text-xs uppercase mb-2">
                Known Locations
              </h4>
              <div className="space-y-1">
                {mapData.markers.length === 0 ? (
                  <p className="text-parchment-600 text-xs italic">
                    No locations discovered yet.
                  </p>
                ) : (
                  mapData.markers.map((marker) => (
                    <button
                      key={marker.id}
                      onClick={() => setSelectedMarker(marker)}
                      className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2 transition-colors ${
                        selectedMarker?.id === marker.id
                          ? 'bg-parchment-700 text-dungeon-900'
                          : 'hover:bg-dungeon-700 text-parchment-300'
                      }`}
                    >
                      <MapPin className={`w-3 h-3 ${
                        marker.type === 'treasure' ? 'text-yellow-400' :
                        marker.type === 'danger' ? 'text-red-400' :
                        marker.type === 'secret' ? 'text-cyan-400' :
                        marker.visited ? 'text-green-400' : 'text-parchment-500'
                      }`} />
                      <span className="truncate">{marker.label}</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-dungeon-600 flex items-center justify-between text-xs text-parchment-500">
          <span>Size: {mapData.width} x {mapData.height}</span>
          {mapData.exploration_progress && (
            <span>Explored: {mapData.exploration_progress}</span>
          )}
          {mapData.player_position && (
            <span>
              Position: ({mapData.player_position.x}, {mapData.player_position.y})
            </span>
          )}
        </div>

        {/* Legend */}
        <div className="px-4 py-2 border-t border-dungeon-600">
          <div className="flex flex-wrap gap-4 text-xs">
            <span><span className="text-green-400 font-mono">@</span> You</span>
            <span><span className="text-parchment-600 font-mono">#</span> Wall</span>
            <span><span className="text-parchment-400 font-mono">.</span> Floor</span>
            <span><span className="text-amber-500 font-mono">+</span> Door</span>
            <span><span className="text-yellow-400 font-mono">$</span> Treasure</span>
            <span><span className="text-red-400 font-mono">!</span> Danger</span>
            <span><span className="text-dungeon-500 font-mono">?</span> Unexplored</span>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <>
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Map className="w-4 h-4 text-parchment-400" />
            <h3 className="font-display text-sm text-parchment-100">
              {mapData.map_name}
            </h3>
          </div>
          <button
            onClick={() => setIsExpanded(true)}
            className="text-parchment-500 hover:text-parchment-200 transition-colors"
            title="Expand map"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>

        {/* Compact map view */}
        <div className="bg-dungeon-900 rounded p-2 overflow-auto max-h-48">
          <DungeonMap mapData={mapData} onCellClick={handleCellClick} />
        </div>

        {/* Selected location quick info */}
        {selectedMarker && !isExpanded && (
          <div className="mt-2 p-2 bg-dungeon-700 rounded text-xs">
            <div className="flex items-center justify-between">
              <span className="text-parchment-200 font-semibold">{selectedMarker.label}</span>
              {onNavigateTo && (
                <button
                  onClick={() => handleNavigate(selectedMarker.label)}
                  className="text-parchment-400 hover:text-parchment-200 flex items-center gap-1"
                >
                  <Navigation className="w-3 h-3" />
                  Go
                </button>
              )}
            </div>
            {selectedMarker.description && (
              <p className="text-parchment-500 mt-1">{selectedMarker.description}</p>
            )}
          </div>
        )}

        {/* Info */}
        <div className="mt-2 flex items-center justify-between text-xs text-parchment-500">
          {mapData.exploration_progress && (
            <span>{mapData.exploration_progress}</span>
          )}
          {mapData.markers.length > 0 && (
            <span>{mapData.markers.length} markers</span>
          )}
        </div>
      </div>

      {isExpanded && expandedView}
    </>
  )
}
