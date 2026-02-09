import { X } from 'lucide-react'

interface IllustrationData {
  image_url: string
  title: string
  description: string
  mood: string
}

interface IllustrationPanelProps {
  illustration: IllustrationData
  onDismiss: () => void
}

export function IllustrationPanel({ illustration, onDismiss }: IllustrationPanelProps) {
  // Map mood to border/glow colors
  const moodStyles: Record<string, string> = {
    dramatic: 'border-amber-600 shadow-amber-900/50',
    mysterious: 'border-purple-600 shadow-purple-900/50',
    peaceful: 'border-emerald-600 shadow-emerald-900/50',
    dangerous: 'border-red-600 shadow-red-900/50',
    wondrous: 'border-cyan-600 shadow-cyan-900/50',
    dark: 'border-slate-600 shadow-slate-900/50',
  }

  const borderStyle = moodStyles[illustration.mood] || moodStyles.dramatic

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className={`relative max-w-2xl max-h-[80vh] rounded-lg border-2 ${borderStyle} shadow-2xl overflow-hidden`}>
        {/* Close button */}
        <button
          onClick={onDismiss}
          className="absolute top-2 right-2 z-10 p-1 rounded-full bg-black/50 text-parchment-300 hover:text-parchment-100 hover:bg-black/70 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Image */}
        <img
          src={illustration.image_url}
          alt={illustration.title}
          className="max-w-full max-h-[70vh] object-contain"
          onClick={onDismiss}
        />

        {/* Caption */}
        {(illustration.title || illustration.description) && (
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent p-4">
            {illustration.title && (
              <h3 className="font-display text-lg text-parchment-100 mb-1">
                {illustration.title}
              </h3>
            )}
            {illustration.description && (
              <p className="text-parchment-400 text-sm">
                {illustration.description}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Click outside to dismiss */}
      <div className="absolute inset-0 -z-10" onClick={onDismiss} />
    </div>
  )
}
