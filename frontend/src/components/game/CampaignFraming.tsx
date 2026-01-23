import { X, Scroll, MapPin, AlertTriangle, Sword, MessageCircle } from 'lucide-react'

interface Rumor {
  text: string
}

interface FramingData {
  adventure_title: string
  adventure_code?: string
  recommended_levels?: string
  premise: string
  what_you_know?: string
  starting_situation: string
  rumored_dangers?: string[]
  rumors?: Rumor[]
  character_name: string
}

interface Props {
  framing: FramingData
  onDismiss: () => void
}

export function CampaignFraming({ framing, onDismiss }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-dungeon-900/90 backdrop-blur-sm">
      <div className="bg-dungeon-800 border border-parchment-700 rounded-lg shadow-2xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-dungeon-600 flex items-center justify-between">
          <div>
            <h2 className="font-display text-2xl text-parchment-100">
              Adventure Awaits...
            </h2>
            <p className="text-parchment-400 text-sm mt-1">
              {framing.adventure_title}
              {framing.adventure_code && (
                <span className="text-parchment-500 ml-2">({framing.adventure_code})</span>
              )}
            </p>
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
          {/* Premise */}
          <div className="bg-dungeon-700 rounded-lg p-4 border-l-4 border-gold-500">
            <div className="flex items-center gap-2 mb-3">
              <Scroll className="w-5 h-5 text-gold-400" />
              <h3 className="font-display text-lg text-parchment-100">
                The Adventure
              </h3>
            </div>
            <p className="text-parchment-300 leading-relaxed">
              {framing.premise}
            </p>
            {framing.recommended_levels && (
              <p className="text-parchment-500 text-sm mt-3">
                Recommended for levels {framing.recommended_levels}
              </p>
            )}
          </div>

          {/* What You Know */}
          {framing.what_you_know && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Sword className="w-5 h-5 text-parchment-400" />
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  What You Know
                </h3>
              </div>
              <div className="bg-dungeon-700/50 border border-dungeon-600 rounded-lg p-4">
                <p className="text-parchment-200 whitespace-pre-wrap leading-relaxed">
                  {framing.what_you_know}
                </p>
              </div>
            </div>
          )}

          {/* Rumors/Legends */}
          {framing.rumors && framing.rumors.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <MessageCircle className="w-5 h-5 text-amber-400" />
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  Rumors & Legends
                </h3>
              </div>
              <ul className="space-y-2">
                {framing.rumors.map((rumor, i) => (
                  <li key={i} className="flex items-start gap-2 text-parchment-300 italic">
                    <span className="text-amber-500 mt-1">"</span>
                    <span>{rumor.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Rumored Dangers */}
          {framing.rumored_dangers && framing.rumored_dangers.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-red-400" />
                <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                  Rumored Dangers
                </h3>
              </div>
              <ul className="space-y-2">
                {framing.rumored_dangers.map((danger, i) => (
                  <li key={i} className="flex items-start gap-2 text-parchment-300">
                    <span className="text-red-500 mt-1">&#8226;</span>
                    <span>{danger}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Starting Situation */}
          <div className="flex items-start gap-3">
            <MapPin className="w-5 h-5 text-parchment-400 mt-0.5" />
            <div>
              <h3 className="font-display text-sm text-parchment-400 uppercase tracking-wider">
                Your Situation
              </h3>
              <p className="text-parchment-200 mt-1">{framing.starting_situation}</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-dungeon-600">
          <button
            onClick={onDismiss}
            className="btn btn-primary w-full"
          >
            Begin the Adventure
          </button>
        </div>
      </div>
    </div>
  )
}
