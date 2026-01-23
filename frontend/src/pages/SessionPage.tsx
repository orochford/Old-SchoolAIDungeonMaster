import { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Send, Swords, Heart, Shield, Scroll } from 'lucide-react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useGameStore } from '@/stores/gameStore'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  toolResults?: Array<{
    tool_name: string
    result: Record<string, unknown>
  }>
}

export function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { messages, addMessage, character, combat } = useGameStore()
  const { sendMessage, isConnected, isStreaming } = useWebSocket(sessionId!)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    }
    addMessage(userMessage)
    sendMessage(input)
    setInput('')
  }

  return (
    <div className="h-[calc(100vh-12rem)] flex gap-4">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto scrollbar-dark card mb-4">
          <div className="space-y-4">
            {messages.length === 0 ? (
              <div className="text-center text-parchment-400 py-12">
                <Scroll className="w-12 h-12 mx-auto mb-4" />
                <p>Your adventure begins here...</p>
                <p className="text-sm mt-2">Describe what you want to do</p>
              </div>
            ) : (
              messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))
            )}
            {isStreaming && (
              <div className="flex items-center space-x-2 text-parchment-400">
                <div className="animate-pulse">The DM is writing...</div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="What do you do?"
            disabled={!isConnected || isStreaming}
            className="input flex-1"
          />
          <button
            type="submit"
            disabled={!input.trim() || !isConnected || isStreaming}
            className="btn btn-primary px-6"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>

        {!isConnected && (
          <div className="text-red-400 text-sm mt-2">
            Disconnected from server. Reconnecting...
          </div>
        )}
      </div>

      {/* Side panel */}
      <div className="w-80 flex flex-col gap-4">
        {/* Character summary */}
        {character && <CharacterPanel character={character} />}

        {/* Combat tracker */}
        {combat && <CombatPanel combat={combat} />}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg p-4 ${
          isUser
            ? 'bg-parchment-600 text-dungeon-900'
            : 'bg-dungeon-700 text-parchment-100'
        }`}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>

        {/* Tool results */}
        {message.toolResults?.map((result, i) => (
          <ToolResultDisplay key={i} toolName={result.tool_name} result={result.result} />
        ))}

        <div className={`text-xs mt-2 ${isUser ? 'text-dungeon-600' : 'text-parchment-500'}`}>
          {message.timestamp.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}

function ToolResultDisplay({
  toolName,
  result,
}: {
  toolName: string
  result: Record<string, unknown>
}) {
  if (toolName === 'roll_dice') {
    const rolls = result.rolls as number[]
    const total = result.total as number
    const purpose = result.purpose as string

    return (
      <div className="mt-2 p-2 bg-dungeon-800 rounded text-sm">
        <div className="text-parchment-400">{purpose}</div>
        <div className="flex items-center space-x-2">
          <span className="text-parchment-300">
            [{rolls.join(', ')}]
          </span>
          <span className="text-parchment-100 font-bold">= {total}</span>
          {Boolean(result.natural_20) && <span className="text-green-400">Critical!</span>}
          {Boolean(result.natural_1) && <span className="text-red-400">Fumble!</span>}
        </div>
      </div>
    )
  }

  if (toolName === 'apply_damage_or_healing') {
    const change = Number(result.change) || 0
    const target = String(result.target || 'Unknown')

    return (
      <div className="mt-2 p-2 bg-dungeon-800 rounded text-sm">
        <div className={change < 0 ? 'text-red-400' : 'text-green-400'}>
          {target}: {change < 0 ? change : `+${change}`} HP
        </div>
      </div>
    )
  }

  return null
}

function CharacterPanel({ character }: { character: {
  name: string
  level: number
  character_class: string
  current_hp: number
  max_hp: number
  armor_class: number
  thac0: number
} }) {
  const hpPercent = (character.current_hp / character.max_hp) * 100

  return (
    <div className="card">
      <h3 className="font-display text-lg text-parchment-100 mb-2">{character.name}</h3>
      <p className="text-parchment-400 text-sm mb-4">
        Level {character.level} {character.character_class}
      </p>

      {/* HP Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="flex items-center text-parchment-400">
            <Heart className="w-4 h-4 mr-1 text-red-500" />
            HP
          </span>
          <span className="text-parchment-100">
            {character.current_hp} / {character.max_hp}
          </span>
        </div>
        <div className="h-3 bg-dungeon-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              hpPercent > 50 ? 'bg-green-600' : hpPercent > 25 ? 'bg-yellow-600' : 'bg-red-600'
            }`}
            style={{ width: `${hpPercent}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex items-center text-parchment-400">
          <Shield className="w-4 h-4 mr-2" />
          <span>AC: </span>
          <span className="text-parchment-100 ml-1">{character.armor_class}</span>
        </div>
        <div className="flex items-center text-parchment-400">
          <Swords className="w-4 h-4 mr-2" />
          <span>THAC0: </span>
          <span className="text-parchment-100 ml-1">{character.thac0}</span>
        </div>
      </div>
    </div>
  )
}

function CombatPanel({ combat }: { combat: {
  round: number
  participants: Array<{
    name: string
    current_hp: number
    max_hp: number
    is_current_turn: boolean
  }>
} }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-lg text-parchment-100">Combat</h3>
        <span className="text-parchment-400 text-sm">Round {combat.round}</span>
      </div>

      <div className="space-y-2">
        {combat.participants.map((p, i) => (
          <div
            key={i}
            className={`p-2 rounded ${
              p.is_current_turn ? 'bg-parchment-600 text-dungeon-900' : 'bg-dungeon-700'
            }`}
          >
            <div className="flex justify-between items-center">
              <span className={p.is_current_turn ? 'font-bold' : ''}>{p.name}</span>
              <span className="text-sm">
                {p.current_hp}/{p.max_hp}
              </span>
            </div>
            <div className="h-1.5 bg-dungeon-600 rounded-full mt-1 overflow-hidden">
              <div
                className="h-full bg-red-500"
                style={{ width: `${(p.current_hp / p.max_hp) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
