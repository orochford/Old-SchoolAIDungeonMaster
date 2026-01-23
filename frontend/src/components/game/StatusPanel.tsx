import { MapPin, AlertTriangle, Wifi, WifiOff, Clock } from 'lucide-react'

interface Props {
  location?: string
  conditions?: string[]
  isConnected: boolean
  sessionId?: string | null
}

export function StatusPanel({ location, conditions, isConnected, sessionId }: Props) {
  return (
    <div className="card">
      <h3 className="font-display text-sm text-parchment-100 mb-3">Status</h3>

      {/* Location */}
      <div className="flex items-start gap-2 mb-3">
        <MapPin className="w-4 h-4 text-parchment-400 mt-0.5" />
        <div>
          <div className="text-parchment-500 text-xs">Location</div>
          <div className="text-parchment-200 text-sm">
            {location || 'Unknown'}
          </div>
        </div>
      </div>

      {/* Conditions */}
      {conditions && conditions.length > 0 && (
        <div className="flex items-start gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5" />
          <div>
            <div className="text-parchment-500 text-xs">Conditions</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {conditions.map((condition, i) => (
                <span
                  key={i}
                  className="bg-yellow-900/30 border border-yellow-700 text-yellow-300 px-1.5 py-0.5 rounded text-xs"
                >
                  {condition}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Connection Status */}
      <div className="flex items-center gap-2 pt-2 border-t border-dungeon-600">
        {isConnected ? (
          <>
            <Wifi className="w-4 h-4 text-green-500" />
            <span className="text-green-400 text-xs">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="w-4 h-4 text-red-500" />
            <span className="text-red-400 text-xs">Disconnected</span>
          </>
        )}
      </div>

      {/* Session Info */}
      {sessionId && (
        <div className="flex items-center gap-2 mt-2 text-parchment-600 text-[10px]">
          <Clock className="w-3 h-3" />
          <span className="truncate">Session: {sessionId.slice(0, 8)}...</span>
        </div>
      )}
    </div>
  )
}
