import React, { useEffect, useRef } from 'react'
import { Dice5, Swords, Sparkles, BookOpen, Heart, Star, User, MapPin } from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  toolName?: string
  created_at: string
}

interface Props {
  messages: Message[]
}

const TOOL_ICONS: Record<string, typeof Dice5> = {
  roll_dice: Dice5,
  roll_morale: Swords,
  roll_reaction: Sparkles,
  calculate_thac0: Swords,
  apply_damage_or_healing: Heart,
  award_xp: Star,
  oracle_query: Sparkles,
  random_event: Sparkles,
  lookup_rule: BookOpen,
  query_character: User,
  update_game_state: MapPin,
}

const TOOL_COLORS: Record<string, string> = {
  roll_dice: 'border-blue-600',
  roll_morale: 'border-orange-600',
  roll_reaction: 'border-purple-600',
  calculate_thac0: 'border-red-600',
  apply_damage_or_healing: 'border-red-500',
  award_xp: 'border-yellow-600',
  oracle_query: 'border-violet-600',
  random_event: 'border-violet-500',
  lookup_rule: 'border-parchment-600',
  query_character: 'border-cyan-600',
  update_game_state: 'border-green-600',
}

// Internal tool names that should be hidden from players
const HIDDEN_TOOL_LABELS = new Set([
  'update_adventure_location',
  'update_adventure_state',
  'save_npc_interaction',
  'advance_scene',
  'update_plot_thread',
  'record_npc_encounter',
  'query_journal',
  'record_discovery',
  'query_world_state',
  'advance_time',
  'get_current_time',
  'schedule_event',
  'check_upcoming_events',
  'update_map_position',
  'add_map_marker',
  'create_map',
])

export function GameLog({ messages }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="card flex-1">
        <h3 className="font-display text-sm text-parchment-100 mb-2">Game Log</h3>
        <p className="text-parchment-500 text-sm text-center py-4">
          Dice rolls and game mechanics will appear here
        </p>
      </div>
    )
  }

  return (
    <div className="card flex-1 flex flex-col min-h-0">
      <h3 className="font-display text-sm text-parchment-100 mb-2">Game Log</h3>
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-2">
        {messages.map((message) => (
          <GameLogEntry key={message.id} message={message} />
        ))}
      </div>
    </div>
  )
}

function GameLogEntry({ message }: { message: Message }) {
  const toolName = message.toolName || ''
  const isHiddenTool = HIDDEN_TOOL_LABELS.has(toolName)

  // Don't render entries for internal tools
  if (isHiddenTool) {
    return null
  }

  const Icon = TOOL_ICONS[toolName] || Dice5
  const borderColor = TOOL_COLORS[toolName] || 'border-dungeon-500'

  return (
    <div className={`bg-dungeon-700 rounded p-2 border-l-2 ${borderColor}`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3 h-3 text-parchment-400" />
        <span className="text-parchment-500 text-[10px] uppercase">
          {formatToolName(toolName || 'game')}
        </span>
      </div>
      <div className="text-parchment-200 text-xs whitespace-pre-wrap leading-relaxed">
        {formatContent(message.content)}
      </div>
    </div>
  )
}

function formatToolName(toolName: string): string {
  return toolName.replace(/_/g, ' ')
}

function formatContent(content: string): React.ReactNode {
  // Remove leading emoji for cleaner display since we have icons
  const cleaned = content.replace(/^[^\w\s]+ /, '')

  // Parse simple markdown (bold with **)
  const parts: React.ReactNode[] = []
  let remaining = cleaned
  let key = 0

  while (remaining.length > 0) {
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/)
    if (boldMatch && boldMatch.index !== undefined) {
      // Add text before the bold
      if (boldMatch.index > 0) {
        parts.push(remaining.slice(0, boldMatch.index))
      }
      // Add the bold text
      parts.push(
        <strong key={key++} className="text-parchment-100 font-semibold">
          {boldMatch[1]}
        </strong>
      )
      remaining = remaining.slice(boldMatch.index + boldMatch[0].length)
    } else {
      // No more bold, add the rest
      parts.push(remaining)
      break
    }
  }

  return parts.length > 0 ? parts : cleaned
}
