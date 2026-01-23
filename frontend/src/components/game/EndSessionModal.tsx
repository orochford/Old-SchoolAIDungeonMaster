import { X, Save, ScrollText } from 'lucide-react'

interface SessionSummary {
  title: string
  summary: string
  key_events: string[]
  npcs_encountered: string[]
  locations_visited: string[]
  combat_count: number
  xp_estimate: number
  loot_found: string[]
  mood: string
}

interface Props {
  summary: SessionSummary | null
  isEnding: boolean
  onConfirmEnd: () => void
  onCancel: () => void
  onClose: () => void
}

export function EndSessionModal({ summary, isEnding, onConfirmEnd, onCancel, onClose }: Props) {
  // Show confirmation dialog if no summary yet
  if (!summary) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="card w-full max-w-md mx-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl text-parchment-100 flex items-center gap-2">
              <Save className="w-6 h-6" />
              End Session?
            </h2>
            <button
              onClick={onCancel}
              className="text-parchment-400 hover:text-parchment-200"
              disabled={isEnding}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <p className="text-parchment-300 mb-4">
            This will save your current progress and generate a summary of your adventure.
            You can resume from where you left off next time.
          </p>

          <div className="flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="btn btn-secondary"
              disabled={isEnding}
            >
              Cancel
            </button>
            <button
              onClick={onConfirmEnd}
              disabled={isEnding}
              className="btn btn-primary"
            >
              {isEnding ? (
                <>
                  <span className="animate-pulse">Saving...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  End & Save Session
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Show summary after session ended
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="card w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-xl text-parchment-100 flex items-center gap-2">
            <ScrollText className="w-6 h-6" />
            {summary.title || 'Session Complete'}
          </h2>
          <button
            onClick={onClose}
            className="text-parchment-400 hover:text-parchment-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4">
          {/* Summary */}
          <div className="bg-dungeon-700 rounded p-4">
            <h3 className="text-sm font-medium text-parchment-400 mb-2">Session Summary</h3>
            <p className="text-parchment-200 whitespace-pre-wrap">{summary.summary}</p>
          </div>

          {/* Key Events */}
          {summary.key_events && summary.key_events.length > 0 && (
            <div className="bg-dungeon-700 rounded p-4">
              <h3 className="text-sm font-medium text-parchment-400 mb-2">Key Events</h3>
              <ul className="list-disc list-inside text-parchment-300 space-y-1">
                {summary.key_events.map((event, i) => (
                  <li key={i}>{event}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Stats Row */}
          <div className="grid grid-cols-3 gap-3">
            {summary.locations_visited && summary.locations_visited.length > 0 && (
              <div className="bg-dungeon-700 rounded p-3">
                <h4 className="text-xs text-parchment-500 mb-1">Locations</h4>
                <p className="text-parchment-300 text-sm">
                  {summary.locations_visited.join(', ')}
                </p>
              </div>
            )}

            {summary.npcs_encountered && summary.npcs_encountered.length > 0 && (
              <div className="bg-dungeon-700 rounded p-3">
                <h4 className="text-xs text-parchment-500 mb-1">NPCs Met</h4>
                <p className="text-parchment-300 text-sm">
                  {summary.npcs_encountered.join(', ')}
                </p>
              </div>
            )}

            {summary.combat_count > 0 && (
              <div className="bg-dungeon-700 rounded p-3">
                <h4 className="text-xs text-parchment-500 mb-1">Combats</h4>
                <p className="text-parchment-300 text-sm">{summary.combat_count}</p>
              </div>
            )}
          </div>

          {/* Loot */}
          {summary.loot_found && summary.loot_found.length > 0 && (
            <div className="bg-dungeon-700 rounded p-4">
              <h3 className="text-sm font-medium text-parchment-400 mb-2">Treasure Found</h3>
              <ul className="list-disc list-inside text-parchment-300 space-y-1">
                {summary.loot_found.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* XP */}
          {summary.xp_estimate > 0 && (
            <div className="bg-dungeon-700 rounded p-4">
              <span className="text-parchment-400">Estimated XP Gained:</span>{' '}
              <span className="text-gold-400 font-bold">{summary.xp_estimate}</span>
            </div>
          )}
        </div>

        <div className="mt-4 pt-4 border-t border-dungeon-600">
          <p className="text-parchment-500 text-sm text-center mb-3">
            Your progress has been saved. You can resume from where you left off!
          </p>
          <button onClick={onClose} className="btn btn-primary w-full">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
