import { useMemo } from 'react'

interface Marker {
  id: string
  x: number
  y: number
  symbol: string
  label: string
  type: string
}

interface MapData {
  map_id: string
  map_name: string
  rendered_map: string
  width: number
  height: number
  player_position: { x: number; y: number } | null
  markers: Marker[]
}

interface Props {
  mapData: MapData
  onCellClick?: (x: number, y: number) => void
}

export function DungeonMap({ mapData, onCellClick }: Props) {
  const lines = useMemo(() => {
    return mapData.rendered_map.split('\n')
  }, [mapData.rendered_map])

  const getCellClass = (char: string) => {
    switch (char) {
      case '@':
        return 'text-green-400 font-bold' // Player
      case '?':
        return 'text-dungeon-500' // Fog of war
      case '#':
        return 'text-parchment-600' // Wall
      case '.':
        return 'text-parchment-400' // Floor
      case '+':
        return 'text-amber-500' // Door
      case '$':
        return 'text-yellow-400' // Treasure
      case '!':
        return 'text-red-400' // Danger
      case '*':
        return 'text-blue-400' // Generic marker
      case 'S':
        return 'text-cyan-400' // Secret
      default:
        return 'text-parchment-300'
    }
  }

  const getMarkerTooltip = (x: number, y: number) => {
    const marker = mapData.markers.find(m => m.x === x && m.y === y)
    return marker?.label
  }

  return (
    <div className="font-mono text-xs leading-none select-none">
      {lines.map((line, y) => (
        <div key={y} className="flex">
          {line.split('').map((char, x) => {
            const tooltip = getMarkerTooltip(x, y)
            return (
              <span
                key={`${x}-${y}`}
                className={`w-3 h-4 inline-flex items-center justify-center ${getCellClass(char)} ${
                  onCellClick ? 'cursor-pointer hover:bg-dungeon-600' : ''
                }`}
                onClick={() => onCellClick?.(x, y)}
                title={tooltip}
              >
                {char}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}
