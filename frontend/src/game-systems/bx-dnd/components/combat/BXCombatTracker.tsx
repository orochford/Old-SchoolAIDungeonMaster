import { Swords, Skull, Flag, Heart } from 'lucide-react'
import type { CombatState, CombatParticipant } from '../../../types/base.types'

interface Props {
  combat: CombatState
}

export function BXCombatTracker({ combat }: Props) {
  const sortedParticipants = [...combat.participants].sort(
    (a, b) => b.initiative - a.initiative
  )

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Swords className="w-5 h-5 text-red-500" />
          <h3 className="font-display text-lg text-parchment-100">Combat</h3>
        </div>
        <div className="bg-dungeon-700 px-3 py-1 rounded">
          <span className="text-parchment-400 text-sm">Round </span>
          <span className="text-parchment-100 font-bold">{combat.round}</span>
        </div>
      </div>

      {/* Initiative Order */}
      <div className="space-y-2">
        {sortedParticipants.map((participant) => (
          <ParticipantRow key={participant.id} participant={participant} />
        ))}
      </div>

      {/* Combat Actions Legend */}
      <div className="mt-4 pt-4 border-t border-dungeon-600">
        <div className="text-xs text-parchment-400 space-y-1">
          <div>Attack: d20 + mods vs THAC0 - target AC</div>
          <div>Morale: 2d6 vs morale score</div>
        </div>
      </div>
    </div>
  )
}

function ParticipantRow({ participant }: { participant: CombatParticipant }) {
  const hpPercent = (participant.currentHp / participant.maxHp) * 100
  const isDead = participant.currentHp <= 0

  return (
    <div
      className={`p-3 rounded-lg transition-colors ${
        participant.isCurrentTurn
          ? 'bg-parchment-600 text-dungeon-900'
          : isDead
          ? 'bg-dungeon-800 opacity-50'
          : 'bg-dungeon-700'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          {isDead ? (
            <Skull className="w-4 h-4 text-red-500" />
          ) : participant.isCurrentTurn ? (
            <Flag className="w-4 h-4 text-dungeon-900" />
          ) : null}
          <span
            className={`font-semibold ${
              participant.isCurrentTurn ? 'text-dungeon-900' : 'text-parchment-100'
            }`}
          >
            {participant.name}
          </span>
          {participant.type !== 'player' && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded ${
                participant.isCurrentTurn
                  ? 'bg-dungeon-900/20 text-dungeon-800'
                  : 'bg-dungeon-600 text-parchment-400'
              }`}
            >
              {participant.type}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-3 text-sm">
          <span
            className={
              participant.isCurrentTurn ? 'text-dungeon-700' : 'text-parchment-400'
            }
          >
            Init: {participant.initiative}
          </span>
          <span
            className={
              participant.isCurrentTurn ? 'text-dungeon-700' : 'text-parchment-400'
            }
          >
            AC: {participant.armorClass}
          </span>
        </div>
      </div>

      {/* HP Bar */}
      <div className="flex items-center space-x-2">
        <Heart
          className={`w-4 h-4 ${
            participant.isCurrentTurn ? 'text-red-700' : 'text-red-500'
          }`}
        />
        <div className="flex-1">
          <div
            className={`h-2 rounded-full overflow-hidden ${
              participant.isCurrentTurn ? 'bg-dungeon-900/20' : 'bg-dungeon-600'
            }`}
          >
            <div
              className={`h-full transition-all duration-300 ${
                hpPercent > 50
                  ? 'bg-green-500'
                  : hpPercent > 25
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
              }`}
              style={{ width: `${Math.max(0, hpPercent)}%` }}
            />
          </div>
        </div>
        <span
          className={`text-sm font-mono ${
            participant.isCurrentTurn ? 'text-dungeon-800' : 'text-parchment-300'
          }`}
        >
          {participant.currentHp}/{participant.maxHp}
        </span>
      </div>

      {/* Conditions */}
      {participant.conditions.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {participant.conditions.map((condition, i) => (
            <span
              key={i}
              className={`text-xs px-1.5 py-0.5 rounded ${
                participant.isCurrentTurn
                  ? 'bg-red-700 text-white'
                  : 'bg-red-900 text-red-200'
              }`}
            >
              {condition}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
