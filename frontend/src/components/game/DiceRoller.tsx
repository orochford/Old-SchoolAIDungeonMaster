import { useState } from 'react'
import { Dice5 } from 'lucide-react'
import { rollDice } from '@/game-systems/bx-dnd/utils/calculations'

interface RollResult {
  id: string
  notation: string
  rolls: number[]
  modifier: number
  total: number
  timestamp: Date
}

interface DiceRollerProps {
  onRoll?: (result: RollResult) => void
  onDirection?: (direction: string) => void
  compact?: boolean
}

const DICE_TYPES = [
  { sides: 4, label: 'd4' },
  { sides: 6, label: 'd6' },
  { sides: 8, label: 'd8' },
  { sides: 10, label: 'd10' },
  { sides: 12, label: 'd12' },
  { sides: 20, label: 'd20' },
]

const DIRECTIONS = ['N', 'S', 'E', 'W'] as const

export function DiceRoller({ onRoll, onDirection, compact = false }: DiceRollerProps) {
  const [customNotation, setCustomNotation] = useState('')
  const [rollHistory, setRollHistory] = useState<RollResult[]>([])
  const [lastRoll, setLastRoll] = useState<RollResult | null>(null)

  const handleRoll = (notation: string) => {
    const result = rollDice(notation)
    const rollResult: RollResult = {
      id: `roll-${Date.now()}`,
      notation,
      rolls: result.rolls,
      modifier: result.modifier,
      total: result.total,
      timestamp: new Date(),
    }

    setLastRoll(rollResult)
    setRollHistory((prev) => [rollResult, ...prev].slice(0, 5))

    // Notify parent of roll
    if (onRoll) {
      onRoll(rollResult)
    }
  }

  const handleQuickRoll = (sides: number) => {
    handleRoll(`1d${sides}`)
  }

  const handleCustomRoll = () => {
    if (!customNotation.trim()) return
    handleRoll(customNotation.trim().toLowerCase())
    setCustomNotation('')
  }

  // Compact mode for inline placement above chat
  if (compact) {
    return (
      <div className="flex items-center gap-2 p-2 bg-dungeon-800 rounded-lg border border-dungeon-600">
        <DiceIcon className="w-4 h-4 text-parchment-500" />
        {/* Quick Dice Buttons */}
        <div className="flex gap-1">
          {DICE_TYPES.map(({ sides, label }) => (
            <button
              key={sides}
              onClick={() => handleQuickRoll(sides)}
              className="bg-dungeon-700 hover:bg-dungeon-600 text-parchment-200 rounded px-2 py-1 text-xs font-semibold transition-colors"
            >
              {label}
            </button>
          ))}
        </div>
        {/* Custom Input */}
        <input
          type="text"
          value={customNotation}
          onChange={(e) => setCustomNotation(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCustomRoll()}
          placeholder="2d6+3"
          className="input text-xs w-20 px-2 py-1"
        />
        <button
          onClick={handleCustomRoll}
          disabled={!customNotation.trim()}
          className="btn btn-primary text-xs px-2 py-1"
        >
          Roll
        </button>
        {/* Direction Buttons */}
        {onDirection && (
          <>
            <div className="w-px h-5 bg-dungeon-600" />
            <div className="flex gap-0.5">
              {DIRECTIONS.map((dir) => (
                <button
                  key={dir}
                  onClick={() => onDirection(dir)}
                  className="bg-dungeon-700 hover:bg-dungeon-600 text-parchment-300 hover:text-parchment-100 rounded w-6 h-6 text-[10px] font-bold transition-colors"
                >
                  {dir}
                </button>
              ))}
            </div>
          </>
        )}
        {/* Last Result */}
        {lastRoll && (
          <span className="text-parchment-200 text-sm ml-2">
            <span className="text-parchment-500">{lastRoll.notation}:</span>{' '}
            <span className="font-bold">{lastRoll.total}</span>
            {lastRoll.notation.includes('d20') && lastRoll.rolls[0] === 20 && (
              <span className="text-green-400 ml-1">Nat 20!</span>
            )}
            {lastRoll.notation.includes('d20') && lastRoll.rolls[0] === 1 && (
              <span className="text-red-400 ml-1">Nat 1!</span>
            )}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="card">
      <h3 className="font-display text-sm text-parchment-100 mb-3">Dice Roller</h3>

      {/* Quick Dice Buttons */}
      <div className="grid grid-cols-3 gap-1.5 mb-3">
        {DICE_TYPES.map(({ sides, label }) => (
          <button
            key={sides}
            onClick={() => handleQuickRoll(sides)}
            className="bg-dungeon-700 hover:bg-dungeon-600 text-parchment-200 rounded p-2 text-sm font-semibold transition-colors"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Custom Notation Input */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={customNotation}
          onChange={(e) => setCustomNotation(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCustomRoll()}
          placeholder="2d6+3"
          className="input text-sm flex-1"
        />
        <button
          onClick={handleCustomRoll}
          disabled={!customNotation.trim()}
          className="btn btn-primary text-sm px-3"
        >
          Roll
        </button>
      </div>

      {/* Last Roll Result */}
      {lastRoll && (
        <div className="bg-dungeon-700 rounded p-3 mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-parchment-400 text-xs">{lastRoll.notation}</span>
            <DiceIcon className="w-4 h-4 text-parchment-500" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-parchment-300 text-sm">
              [{lastRoll.rolls.join(', ')}]
              {lastRoll.modifier !== 0 && (
                <span className="text-parchment-500">
                  {lastRoll.modifier > 0 ? ` + ${lastRoll.modifier}` : ` - ${Math.abs(lastRoll.modifier)}`}
                </span>
              )}
            </span>
            <span className="text-parchment-100 font-bold text-xl ml-auto">
              = {lastRoll.total}
            </span>
          </div>
          {lastRoll.notation.includes('d20') && lastRoll.rolls[0] === 20 && (
            <div className="text-green-400 text-xs mt-1">Natural 20!</div>
          )}
          {lastRoll.notation.includes('d20') && lastRoll.rolls[0] === 1 && (
            <div className="text-red-400 text-xs mt-1">Natural 1!</div>
          )}
        </div>
      )}

      {/* Roll History */}
      {rollHistory.length > 1 && (
        <div className="border-t border-dungeon-600 pt-2">
          <div className="text-parchment-500 text-xs mb-1">Recent Rolls</div>
          <div className="space-y-1">
            {rollHistory.slice(1).map((roll) => (
              <div key={roll.id} className="flex justify-between text-xs text-parchment-400">
                <span>{roll.notation}</span>
                <span className="text-parchment-300">{roll.total}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function DiceIcon({ className }: { className?: string }) {
  return <Dice5 className={className} />
}
