import { X, MapPin, Users, Target, BookOpen } from 'lucide-react'

interface PlotThread {
  name: string
  notes: string
}

interface NPC {
  name: string
  attitude: string
  notes: string
}

interface RecapData {
  campaign_name: string
  previous_session_id: string
  current_location: string
  active_plot_threads: PlotThread[]
  npcs_encountered: NPC[]
  session_goals: string[]
  summary: {
    title: string
    content: string
    key_events: string[]
    mood: string
  }
  narrative: string
}

interface Props {
  recap: RecapData
  onDismiss: () => void
}

export function SessionRecap({ recap, onDismiss }: Props) {
  const getAttitudeColor = (attitude: string) => {
    switch (attitude) {
      case 'friendly':
        return 'text-green-400'
      case 'hostile':
        return 'text-red-400'
      default:
        return 'text-parchment-400'
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-dungeon-900/90 backdrop-blur-sm">
      <div className="bg-dungeon-800 border border-parchment-700 rounded-lg shadow-2xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-dungeon-600 flex items-center justify-between">
          <div>
            <h2 className="font-display text-2xl text-parchment-100">
              Previously on {recap.campaign_name}...
            </h2>
            {recap.summary.mood && (
              <p className="text-parchment-500 text-sm mt-1 italic">
                Mood: {recap.summary.mood}
              </p>
            )}
          </div>
          <button
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Narrative Summary */}
          <div className="bg-dungeon-700 rounded-lg p-4 border-l-4 border-parchment-600">
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="w-5 h-5 text-parchment-400" />
              <h3 className="font-display text-lg text-parchment-100">
                {recap.summary.title}
              </h3>
            </div>
            <p className="text-parchment-300 whitespace-pre-wrap leading-relaxed">
              {recap.narrative}
            </p>
          </div>

          {/* Key Events */}
          {recap.summary.key_events.length > 0 && (
            <div>
              <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider mb-3">
                Key Events
              </h3>
              <ul className="space-y-2">
                {recap.summary.key_events.map((event, i) => (
                  <li key={i} className="flex items-start gap-2 text-parchment-200">
                    <span className="text-parchment-500 mt-1">&#8226;</span>
                    <span>{event}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Current Location */}
          {recap.current_location && recap.current_location !== 'Unknown' && (
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-parchment-400 mt-0.5" />
              <div>
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  Current Location
                </h3>
                <p className="text-parchment-200 mt-1">{recap.current_location}</p>
              </div>
            </div>
          )}

          {/* Active Plot Threads */}
          {recap.active_plot_threads.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Target className="w-5 h-5 text-parchment-400" />
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  Unfinished Business
                </h3>
              </div>
              <div className="space-y-2">
                {recap.active_plot_threads.map((thread, i) => (
                  <div
                    key={i}
                    className="bg-dungeon-700/50 border border-dungeon-600 rounded px-3 py-2"
                  >
                    <div className="text-parchment-200 font-medium">
                      {thread.name}
                    </div>
                    {thread.notes && (
                      <div className="text-parchment-500 text-sm mt-1">
                        {thread.notes}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* NPCs Encountered */}
          {recap.npcs_encountered.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Users className="w-5 h-5 text-parchment-400" />
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  Recent Acquaintances
                </h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {recap.npcs_encountered.map((npc, i) => (
                  <div
                    key={i}
                    className="bg-dungeon-700/50 border border-dungeon-600 rounded px-3 py-1.5"
                    title={npc.notes || `${npc.attitude}`}
                  >
                    <span className="text-parchment-200">{npc.name}</span>
                    <span className={`ml-2 text-xs ${getAttitudeColor(npc.attitude)}`}>
                      ({npc.attitude})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-dungeon-600">
          <button
            onClick={onDismiss}
            className="btn btn-primary w-full"
          >
            Begin Session
          </button>
        </div>
      </div>
    </div>
  )
}
