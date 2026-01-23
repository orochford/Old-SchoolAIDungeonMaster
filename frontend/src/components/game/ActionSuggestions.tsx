import { useMemo } from 'react'
import { Swords, Eye, Backpack, Moon, MessageCircle, Search, DoorOpen, Ear, Shield, Footprints, Package } from 'lucide-react'

interface GameState {
  location?: string
  inCombat?: boolean
  conditions?: string[]
}

interface ActionSuggestionsProps {
  onAction: (action: string) => void
  gameState?: GameState
  disabled?: boolean
}

interface ActionButton {
  label: string
  action: string
  icon?: React.ReactNode
}

/**
 * Contextual action suggestions that appear above the input field.
 * Clicking a button populates the input field without sending.
 */
export function ActionSuggestions({ onAction, gameState, disabled }: ActionSuggestionsProps) {
  const suggestions = useMemo(() => {
    const base: ActionButton[] = [
      { label: 'Look around', action: 'I look around and examine my surroundings.', icon: <Eye className="w-3 h-3" /> },
      { label: 'Check inventory', action: 'I check my inventory and equipment.', icon: <Backpack className="w-3 h-3" /> },
    ]

    if (gameState?.inCombat) {
      // Combat actions
      return [
        { label: 'Attack', action: 'I attack the nearest enemy with my weapon.', icon: <Swords className="w-3 h-3" /> },
        { label: 'Defend', action: 'I take a defensive stance, focusing on blocking incoming attacks.', icon: <Shield className="w-3 h-3" /> },
        { label: 'Flee', action: 'I attempt to flee from combat!', icon: <Footprints className="w-3 h-3" /> },
        { label: 'Use item', action: 'I reach for an item in my pack...', icon: <Package className="w-3 h-3" /> },
        ...base,
      ]
    }

    // Exploration/default actions
    return [
      { label: 'Search area', action: 'I carefully search the area for hidden objects, traps, or secret doors.', icon: <Search className="w-3 h-3" /> },
      { label: 'Listen', action: 'I stop and listen carefully for any sounds.', icon: <Ear className="w-3 h-3" /> },
      { label: 'Open door', action: 'I cautiously open the door ahead.', icon: <DoorOpen className="w-3 h-3" /> },
      ...base,
      { label: 'Rest', action: 'I take a short rest to catch my breath.', icon: <Moon className="w-3 h-3" /> },
      { label: 'Talk', action: 'I approach and attempt to speak with...', icon: <MessageCircle className="w-3 h-3" /> },
    ]
  }, [gameState?.inCombat])

  return (
    <div className="flex flex-wrap gap-2 mb-3">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion.label}
          onClick={() => onAction(suggestion.action)}
          disabled={disabled}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-dungeon-700 hover:bg-dungeon-600
                     text-parchment-300 hover:text-parchment-100 rounded-full border border-dungeon-600
                     hover:border-parchment-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {suggestion.icon}
          <span>{suggestion.label}</span>
        </button>
      ))}
    </div>
  )
}
