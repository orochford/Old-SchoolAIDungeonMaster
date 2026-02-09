import { useState, useEffect, useCallback } from 'react'
import { Plus, X } from 'lucide-react'

interface Badge {
  id: string
  name: string
  prompt: string
}

interface CustomActionBadgesProps {
  onAction: (prompt: string) => void
  characterId: string
  disabled?: boolean
}

function storageKey(characterId: string) {
  return `action-badges-${characterId}`
}

function loadBadges(characterId: string): Badge[] {
  try {
    const key = storageKey(characterId)
    const raw = localStorage.getItem(key)
    const badges = raw ? JSON.parse(raw) : []
    console.log('[CustomActionBadges] Loading from key:', key, 'found:', badges.length, 'badges')
    return badges
  } catch (e) {
    console.error('[CustomActionBadges] Load error:', e)
    return []
  }
}

function saveBadges(characterId: string, badges: Badge[]) {
  const key = storageKey(characterId)
  const data = JSON.stringify(badges)
  console.log('[CustomActionBadges] Saving to key:', key, 'badges:', badges.length)
  localStorage.setItem(key, data)
  // Verify save
  const verify = localStorage.getItem(key)
  if (verify !== data) {
    console.error('[CustomActionBadges] Save verification FAILED!')
  }
}

export function CustomActionBadges({ onAction, characterId, disabled }: CustomActionBadgesProps) {
  const [badges, setBadges] = useState<Badge[]>([])
  const [isAdding, setIsAdding] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPrompt, setNewPrompt] = useState('')

  useEffect(() => {
    if (characterId) {
      setBadges(loadBadges(characterId))
    }
  }, [characterId])

  const addBadge = useCallback(() => {
    const trimmedName = newName.trim()
    const trimmedPrompt = newPrompt.trim()
    if (!trimmedName || !trimmedPrompt) return

    const badge: Badge = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: trimmedName,
      prompt: trimmedPrompt,
    }
    const updated = [...badges, badge]
    setBadges(updated)
    saveBadges(characterId, updated)
    setNewName('')
    setNewPrompt('')
    setIsAdding(false)
  }, [newName, newPrompt, badges, characterId])

  const removeBadge = useCallback((id: string) => {
    const updated = badges.filter((b) => b.id !== id)
    setBadges(updated)
    saveBadges(characterId, updated)
  }, [badges, characterId])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addBadge()
    } else if (e.key === 'Escape') {
      setIsAdding(false)
      setNewName('')
      setNewPrompt('')
    }
  }, [addBadge])

  if (!characterId) return null

  return (
    <div className="flex flex-wrap gap-2 mb-3">
      <button
        onClick={() => setIsAdding(!isAdding)}
        disabled={disabled}
        className="flex items-center gap-1 px-3 py-1.5 text-xs bg-dungeon-700 hover:bg-dungeon-600
                   text-parchment-300 hover:text-parchment-100 rounded-full border border-dashed border-parchment-700
                   hover:border-parchment-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus className="w-3 h-3" />
        <span>Add</span>
      </button>

      {badges.map((badge) => (
        <button
          key={badge.id}
          onClick={() => onAction(badge.prompt)}
          disabled={disabled}
          title={badge.prompt}
          className="group flex items-center gap-1.5 px-3 py-1.5 text-xs bg-dungeon-700 hover:bg-dungeon-600
                     text-parchment-300 hover:text-parchment-100 rounded-full border border-parchment-700
                     hover:border-parchment-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span>{badge.name}</span>
          <span
            role="button"
            onClick={(e) => {
              e.stopPropagation()
              removeBadge(badge.id)
            }}
            className="ml-0.5 text-parchment-500 hover:text-red-400 transition-colors"
          >
            <X className="w-3 h-3" />
          </span>
        </button>
      ))}

      {isAdding && (
        <div className="flex items-center gap-2 w-full mt-1">
          <input
            type="text"
            placeholder="Name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={20}
            autoFocus
            className="px-2 py-1 text-xs bg-dungeon-800 text-parchment-200 border border-dungeon-600
                       rounded focus:outline-none focus:border-parchment-600 w-24"
          />
          <input
            type="text"
            placeholder="Prompt text"
            value={newPrompt}
            onChange={(e) => setNewPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            className="px-2 py-1 text-xs bg-dungeon-800 text-parchment-200 border border-dungeon-600
                       rounded focus:outline-none focus:border-parchment-600 flex-1"
          />
          <button
            onClick={addBadge}
            disabled={!newName.trim() || !newPrompt.trim()}
            className="px-3 py-1 text-xs bg-dungeon-600 hover:bg-dungeon-500 text-parchment-200
                       rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Save
          </button>
          <button
            onClick={() => {
              setIsAdding(false)
              setNewName('')
              setNewPrompt('')
            }}
            className="px-3 py-1 text-xs bg-dungeon-700 hover:bg-dungeon-600 text-parchment-400
                       hover:text-parchment-200 rounded transition-colors"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}
