import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowLeft, Send, Loader, Scroll, Save } from 'lucide-react'
import { api } from '@/services/api'
import { CharacterSidebar } from '@/components/game/CharacterSidebar'
import { EquippedItem } from '@/game-systems/bx-dnd/utils/calculations'
import { DiceRoller } from '@/components/game/DiceRoller'
import { GameLog } from '@/components/game/GameLog'
import { StatusPanel } from '@/components/game/StatusPanel'
import { ActionSuggestions } from '@/components/game/ActionSuggestions'
import { JournalPanel } from '@/components/game/JournalPanel'
import { SessionRecap } from '@/components/game/SessionRecap'
import { CampaignFraming } from '@/components/game/CampaignFraming'
import { CalendarPanel } from '@/components/game/CalendarPanel'
import { MapPanel } from '@/components/game/MapPanel'
import { SpellPanel } from '@/components/game/SpellPanel'
import { SpellbookModal } from '@/components/game/SpellbookModal'
import { EndSessionModal } from '@/components/game/EndSessionModal'

// Simple markdown renderer for dice roll messages
function renderMarkdown(content: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let remaining = content
  let key = 0

  while (remaining.length > 0) {
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/)
    if (boldMatch && boldMatch.index !== undefined) {
      if (boldMatch.index > 0) {
        parts.push(remaining.slice(0, boldMatch.index))
      }
      parts.push(
        <strong key={key++} className="text-parchment-100 font-semibold">
          {boldMatch[1]}
        </strong>
      )
      remaining = remaining.slice(boldMatch.index + boldMatch[0].length)
    } else {
      parts.push(remaining)
      break
    }
  }

  return parts.length > 0 ? parts : content
}

interface Character {
  id: string
  name: string
  level: number
  current_hp: number
  max_hp: number
  experience_points: number
  attributes: {
    character_class?: string
    ability_scores?: Record<string, number>
    saving_throws?: Record<string, number>
    thac0?: number
    armor_class?: number
    alignment?: string
    gold?: number
    equipment?: string[]
  }
}

interface Campaign {
  id: string
  name: string
  settings?: {
    character_id?: string
  }
}

interface Session {
  id: string
  campaign_id: string
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool' | 'dice'
  content: string
  toolName?: string
  created_at: string
}

interface GameState {
  location?: string
  conditions?: string[]
  inCombat?: boolean
}

interface RecapData {
  campaign_name: string
  previous_session_id: string
  current_location: string
  active_plot_threads: { name: string; notes: string }[]
  npcs_encountered: { name: string; attitude: string; notes: string }[]
  session_goals: string[]
  summary: {
    title: string
    content: string
    key_events: string[]
    mood: string
  }
  narrative: string
}

interface FramingData {
  adventure_title: string
  adventure_code?: string
  recommended_levels?: string
  premise: string
  what_you_know?: string
  starting_situation: string
  rumored_dangers?: string[]
  rumors?: { text: string }[]
  character_name: string
}

interface MapData {
  map_id: string
  map_name: string
  rendered_map: string
  width: number
  height: number
  player_position: { x: number; y: number } | null
  markers: { id: string; x: number; y: number; symbol: string; label: string; type: string }[]
  exploration_progress?: string
}

interface TimeData {
  day: number
  month: number
  month_name: string
  year: number
  hour: number
  time_of_day: string
  formatted_date: string
  formatted_time: string
  moon_phase: string
  season: string
  weather: string
}

export function PlayPage() {
  const { characterId, campaignId: urlCampaignId } = useParams()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [selectedCampaign, setSelectedCampaign] = useState<string | null>(null)
  const [streamingContent, setStreamingContent] = useState('')
  const [gameState, setGameState] = useState<GameState>({})
  const [recapData, setRecapData] = useState<RecapData | null>(null)
  const [showRecap, setShowRecap] = useState(false)
  const [framingData, setFramingData] = useState<FramingData | null>(null)
  const [showFraming, setShowFraming] = useState(false)
  const [mapData, setMapData] = useState<MapData | null>(null)
  const [timeData, setTimeData] = useState<TimeData | null>(null)
  const [showSpellbook, setShowSpellbook] = useState(false)
  const [showEndSession, setShowEndSession] = useState(false)
  const [isEndingSession, setIsEndingSession] = useState(false)
  const [sessionSummary, setSessionSummary] = useState<{
    title: string
    summary: string
    key_events: string[]
    npcs_encountered: string[]
    locations_visited: string[]
    combat_count: number
    xp_estimate: number
    loot_found: string[]
    mood: string
  } | null>(null)
  const streamingContentRef = useRef('')  // Ref to avoid stale closure
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const isStartingSessionRef = useRef(false)  // Guard against double-starts from React StrictMode

  const { data: character, refetch: refetchCharacter } = useQuery({
    queryKey: ['character', characterId],
    queryFn: () => api.get<Character>(`/characters/${characterId}`),
    enabled: !!characterId,
  })

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  const queryClient = useQueryClient()

  // Mutation for updating character (e.g., equipment toggling)
  const updateCharacterMutation = useMutation({
    mutationFn: (attributes: Record<string, unknown>) =>
      api.patch(`/characters/${characterId}`, { attributes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character', characterId] })
    },
  })

  // Handler for weapon selection changes - saves to database
  const handleWeaponSelectionChange = useCallback((primary: string | null, secondary: string | null) => {
    const currentAttrs = character?.attributes || {}
    updateCharacterMutation.mutate({
      ...currentAttrs,
      equipped_weapons: { primary, secondary },
    })
  }, [character?.attributes, updateCharacterMutation])

  // Filter campaigns that use this character
  const characterCampaigns = campaigns?.filter(
    (c) => c.settings?.character_id === characterId
  )

  const startSessionMutation = useMutation({
    mutationFn: async (campaignId: string) => {
      const session = await api.post<Session>('/sessions', {
        campaign_id: campaignId,
        character_id: characterId,
      })
      return session
    },
    onSuccess: (session) => {
      setSessionId(session.id)
      connectWebSocket(session.id)
    },
  })

  // Auto-start session if campaignId is provided in URL (from Campaigns page Play button)
  // Uses ref guard to prevent double-starts from React StrictMode or effect re-runs
  useEffect(() => {
    if (urlCampaignId && !sessionId && !startSessionMutation.isPending && !isStartingSessionRef.current) {
      isStartingSessionRef.current = true
      startSessionMutation.mutate(urlCampaignId)
    }
  }, [urlCampaignId, sessionId, startSessionMutation])

  const connectWebSocket = useCallback((sessId: string) => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.hostname}:8000/api/v1/sessions/${sessId}/play`

    console.log('Connecting to WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      console.log('WS message:', data)

      switch (data.type) {
        case 'connected':
          setIsConnected(true)
          setIsLoading(false)
          // Restore game state if reconnecting
          if (data.game_state) {
            const gs = data.game_state as Record<string, unknown>
            setGameState({
              location: gs.location as string | undefined,
              conditions: gs.conditions as string[] | undefined,
              inCombat: gs.in_combat as boolean | undefined,
            })
          }
          break

        case 'session_recap':
          if (data.recap) {
            setRecapData(data.recap as RecapData)
            setShowRecap(true)
          }
          break

        case 'campaign_framing':
          if (data.framing) {
            setFramingData(data.framing as FramingData)
            setShowFraming(true)
          }
          break

        case 'conversation_history':
          if (data.messages && Array.isArray(data.messages)) {
            const historyMessages: Message[] = data.messages.map((msg: {
              id: string
              role: string
              content: string
              created_at: string
              tool_calls?: Array<{ name: string; [key: string]: unknown }>
              tool_results?: unknown
            }) => {
              const base = {
                id: msg.id,
                role: msg.role as Message['role'],
                content: msg.content,
                created_at: msg.created_at,
              }
              // For tool messages, extract toolName from tool_calls
              if (msg.role === 'tool' && msg.tool_calls?.[0]?.name) {
                return { ...base, toolName: msg.tool_calls[0].name }
              }
              return base
            })
            setMessages(historyMessages)
            console.log(`Loaded ${historyMessages.length} messages from history`)
          }
          break

        case 'dm_typing':
          setIsLoading(true)
          streamingContentRef.current = ''
          setStreamingContent('')
          break

        case 'dm_text':
          streamingContentRef.current += data.content
          setStreamingContent(streamingContentRef.current)
          break

        case 'tool_result':
          // Extract game state updates
          if (data.tool_name === 'update_game_state' && data.result?.updates) {
            const updates = data.result.updates as Record<string, unknown>
            setGameState((prev) => ({
              ...prev,
              location: (updates.location as string) || prev.location,
              conditions: (updates.conditions as string[]) || prev.conditions,
            }))
          }

          // Handle update_adventure_location
          if (data.tool_name === 'update_adventure_location' && data.result?.location) {
            setGameState((prev) => ({
              ...prev,
              location: data.result.location as string,
            }))
          }

          // Handle map display
          if (data.tool_name === 'display_map' && data.result?.rendered_map) {
            setMapData({
              map_id: data.result.map_id as string,
              map_name: data.result.map_name as string,
              rendered_map: data.result.rendered_map as string,
              width: data.result.width as number,
              height: data.result.height as number,
              player_position: data.result.player_position as { x: number; y: number } | null,
              markers: data.result.markers as MapData['markers'],
              exploration_progress: data.result.exploration_progress as string,
            })
          }

          // Handle map position update
          if (data.tool_name === 'update_map_position' && data.result?.rendered_map) {
            setMapData((prev) => prev ? {
              ...prev,
              rendered_map: data.result.rendered_map as string,
              player_position: data.result.new_position as { x: number; y: number },
            } : null)
          }

          // Handle time advance
          if (data.tool_name === 'advance_time' && data.result?.new_time) {
            const newTime = data.result.new_time as Record<string, unknown>
            setTimeData((prev) => prev ? {
              ...prev,
              day: newTime.day as number,
              month: newTime.month as number,
              month_name: newTime.month_name as string,
              year: newTime.year as number,
              hour: newTime.hour as number,
              formatted_date: `Day ${newTime.day} of ${newTime.month_name}, Year ${newTime.year}`,
              formatted_time: `${String(newTime.hour).padStart(2, '0')}:00`,
            } : null)
          }

          // Handle get current time
          if (data.tool_name === 'get_current_time' && data.result?.formatted_date) {
            setTimeData({
              day: data.result.day as number,
              month: data.result.month as number,
              month_name: data.result.month_name as string,
              year: data.result.year as number,
              hour: data.result.hour as number,
              time_of_day: data.result.time_of_day as string,
              formatted_date: data.result.formatted_date as string,
              formatted_time: data.result.formatted_time as string,
              moon_phase: data.result.moon_phase as string,
              season: data.result.season as string,
              weather: data.result.weather as string,
            })
          }

          // Show tool results as system messages
          const toolMsg: Message = {
            id: `tool-${Date.now()}`,
            role: 'tool',
            content: formatToolResult(data.tool_name, data.result),
            toolName: data.tool_name,
            created_at: new Date().toISOString(),
          }
          setMessages((prev) => [...prev, toolMsg])
          break

        case 'dm_complete':
          // Finalize the streamed DM message using ref (avoids stale closure)
          const finalContent = streamingContentRef.current || 'The Dungeon Master contemplates...'
          setMessages((prev) => [
            ...prev,
            {
              id: `dm-${Date.now()}`,
              role: 'assistant',
              content: finalContent,
              created_at: new Date().toISOString(),
            },
          ])
          streamingContentRef.current = ''
          setStreamingContent('')
          setIsLoading(false)
          // Refresh character data in case HP/XP changed
          refetchCharacter()
          break

        case 'error':
          setMessages((prev) => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: 'system',
              content: `Error: ${data.message}`,
              created_at: new Date().toISOString(),
            },
          ])
          setIsLoading(false)
          setIsEndingSession(false)
          break

        case 'session_ended':
          setIsEndingSession(false)
          if (data.summary) {
            setSessionSummary(data.summary as typeof sessionSummary)
          }
          break
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setIsConnected(false)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setIsConnected(false)
    }
  }, [refetchCharacter])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingContent])

  const handleSend = () => {
    if (!input.trim() || isLoading || !wsRef.current) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input,
      created_at: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])

    // Send to WebSocket
    wsRef.current.send(
      JSON.stringify({
        type: 'player_action',
        content: input,
      })
    )

    setInput('')
  }

  const handleEndSession = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    setIsEndingSession(true)
    wsRef.current.send(JSON.stringify({ type: 'end_session' }))
  }

  const handleCloseEndSession = () => {
    setShowEndSession(false)
    setSessionSummary(null)
    wsRef.current?.close()
    navigate(`/characters/${characterId}`)
  }

  // Format tool results for display
  const formatToolResult = (toolName: string, result: Record<string, unknown>): string => {
    switch (toolName) {
      case 'roll_dice':
        return `🎲 ${result.purpose}: rolled ${result.notation} = [${(result.rolls as number[]).join(', ')}]${
          result.modifier ? ` + ${result.modifier}` : ''
        } = **${result.total}**${result.natural_20 ? ' (Natural 20!)' : ''}${
          result.natural_1 ? ' (Natural 1!)' : ''
        }`

      case 'roll_morale':
        return `⚔️ Morale Check (${result.creature}): rolled ${result.roll} vs ${result.morale_score} - ${
          result.passed ? '✓ Holds firm' : '✗ Breaks and flees!'
        }`

      case 'roll_reaction':
        return `🤝 Reaction Roll (${result.npc}): ${result.roll}${
          result.cha_modifier ? ` + ${result.cha_modifier}` : ''
        } = ${result.modified_roll} → ${result.reaction} (${result.description})`

      case 'calculate_thac0':
        return `⚔️ Attack: ${result.attack_roll}${result.modifiers ? ` + ${result.modifiers}` : ''} = ${
          result.modified_roll
        } vs AC ${result.target_ac} (need ${result.target_number}) → ${
          result.hit ? '**HIT!**' : 'Miss'
        }${result.natural_20 ? ' (Critical!)' : ''}${result.natural_1 ? ' (Fumble!)' : ''}`

      case 'apply_damage_or_healing':
        const hpChange = (result.old_hp as number) - (result.new_hp as number)
        return `💔 ${result.target}: ${result.old_hp} → ${result.new_hp} HP (${
          hpChange > 0 ? `-${hpChange}` : `+${Math.abs(hpChange)}`
        } from ${result.source})`

      case 'award_xp':
        return `⭐ XP Gained: +${result.xp_gained} from ${result.source} (Total: ${result.new_xp})`

      case 'oracle_query':
        return `🔮 Oracle: "${result.question}" [${result.odds}, CF${result.chaos_factor}]\n` +
          `   Roll: ${result.roll} vs ${result.threshold} → **${result.answer}**` +
          (result.random_event_triggered ? ' ⚡ Random Event!' : '')

      case 'random_event':
        return `⚡ Random Event: ${result.event_focus}\n` +
          `   Meaning: ${result.event_meaning}\n` +
          `   ${result.interpretation_hint}`

      case 'lookup_rule':
        return `📖 Rule Lookup: "${result.query}"\n${result.rules_found}`

      case 'query_character': {
        const stats = result.stats as Record<string, unknown> | undefined
        return `📋 ${result.name} (Level ${result.level})\n` +
          (stats ? `   HP: ${stats.hp} | XP: ${stats.xp}` : '') +
          (result.conditions && (result.conditions as string[]).length > 0
            ? `\n   Conditions: ${(result.conditions as string[]).join(', ')}`
            : '')
      }

      case 'update_game_state': {
        if (!result.success) return `⚠️ Failed to update game state`
        const updates = result.updates as Record<string, unknown> | undefined
        if (!updates) return `✓ Game state updated`
        const parts: string[] = []
        if (updates.location) parts.push(`📍 ${updates.location}`)
        if (updates.conditions) parts.push(`⚠️ Conditions: ${(updates.conditions as string[]).join(', ')}`)
        if (updates.time) parts.push(`🕐 ${updates.time}`)
        return parts.length > 0 ? parts.join('\n') : `✓ Game state updated`
      }

      case 'update_adventure_location': {
        const loc = result.location as string
        const prev = result.previous_location as string
        if (prev) {
          return `📍 Moved from ${prev} to ${loc}`
        }
        return `📍 Now at: ${loc}`
      }

      case 'convert_damage_to_harm':
        return `⚔️ ${result.narrative}`

      case 'roll_fray_die':
        return `⚔️ Fray Die: ${result.roll} → ${result.narrative}`

      case 'defy_death':
        return `💀 Defy Death: ${result.roll} + ${result.con_modifier} + ${result.level} = ${result.total} → ${result.narrative}`

      case 'roll_trait_check':
        return `🎯 ${result.trait} Check: [${(result.dice as number[]).join(', ')}]${
          result.modifier !== 0 ? ` + ${result.modifier}` : ''
        } = ${result.total} vs ${result.target} (${result.difficulty}) → ${result.narrative}`

      case 'record_discovery':
        return `📝 Recorded: ${result.title} (${result.entry_type})`

      case 'query_journal':
        return `📖 Found ${result.count} journal entries`

      case 'query_world_state':
        return `🗺️ World state queried`

      case 'advance_time':
        return `⏰ Time passes: ${result.narrative || `${result.hours_advanced} hours`}`

      case 'get_current_time':
        return `🕐 ${result.formatted_date} (${result.time_of_day})`

      case 'schedule_event':
        return `📅 Event scheduled: ${(result.event as Record<string, unknown>)?.name}`

      case 'check_upcoming_events':
        return `📅 ${result.count} upcoming events`

      case 'display_map':
        return `🗺️ Map displayed: ${result.map_name}`

      case 'update_map_position':
        return `📍 Moved to (${(result.new_position as Record<string, unknown>)?.x}, ${(result.new_position as Record<string, unknown>)?.y}) - ${result.newly_revealed_count} new cells revealed`

      case 'add_map_marker':
        return `📌 Marker added: ${(result.marker as Record<string, unknown>)?.label}`

      default:
        return `[${toolName}]: ${JSON.stringify(result)}`
    }
  }

  // Campaign selection screen
  if (!sessionId) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center space-x-4 mb-8">
          <Link to={`/characters/${characterId}`} className="text-parchment-400 hover:text-parchment-200">
            <ArrowLeft className="w-6 h-6" />
          </Link>
          <h1 className="font-display text-4xl text-parchment-100">Start Adventure</h1>
        </div>

        <div className="card mb-6">
          <h2 className="font-display text-xl text-parchment-100 mb-2">Playing as</h2>
          <p className="text-parchment-300">
            {character?.name} - Level {character?.level} {character?.attributes.character_class}
          </p>
          <p className="text-parchment-500 text-sm">
            HP: {character?.current_hp}/{character?.max_hp} | XP: {character?.experience_points}
          </p>
        </div>

        <div className="card">
          <h2 className="font-display text-xl text-parchment-100 mb-4">Select Campaign</h2>

          {characterCampaigns && characterCampaigns.length > 0 ? (
            <div className="space-y-3 mb-6">
              {characterCampaigns.map((campaign) => (
                <div
                  key={campaign.id}
                  onClick={() => setSelectedCampaign(campaign.id)}
                  className={`p-4 rounded-lg border cursor-pointer transition-colors ${
                    selectedCampaign === campaign.id
                      ? 'border-parchment-500 bg-dungeon-700'
                      : 'border-dungeon-600 hover:border-parchment-600'
                  }`}
                >
                  <h3 className="text-parchment-100 font-semibold">{campaign.name}</h3>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Scroll className="w-12 h-12 text-parchment-500 mx-auto mb-4" />
              <p className="text-parchment-400 mb-4">
                No campaigns found for this character. Create a campaign with this character first!
              </p>
              <Link to="/campaigns" className="btn btn-secondary">
                Go to Campaigns
              </Link>
            </div>
          )}

          {characterCampaigns && characterCampaigns.length > 0 && (
            <button
              onClick={() => selectedCampaign && startSessionMutation.mutate(selectedCampaign)}
              disabled={!selectedCampaign || startSessionMutation.isPending}
              className="btn btn-primary w-full"
            >
              {startSessionMutation.isPending ? 'Starting...' : 'Begin Adventure'}
            </button>
          )}
        </div>
      </div>
    )
  }

  // Separate tool messages from chat messages (include dice rolls in chat)
  const chatMessages = messages.filter((m) => m.role !== 'tool')
  const toolMessages = messages.filter((m) => m.role === 'tool')

  // Game session screen - Three column layout
  return (
    <div className="h-[calc(100vh-8rem)] grid grid-cols-[280px_1fr_300px] gap-4">
      {/* Left Column - Character Info */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        {/* Session Controls */}
        <div className="flex items-center justify-between gap-2">
          <button
            onClick={() => {
              if (confirm('Leave without saving? Your session will continue where you left off.')) {
                wsRef.current?.close()
                navigate(`/characters/${characterId}`)
              }
            }}
            className="flex items-center gap-2 text-parchment-400 hover:text-parchment-200 text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Leave</span>
          </button>
          <button
            onClick={() => setShowEndSession(true)}
            disabled={!isConnected || isLoading}
            className="flex items-center gap-2 text-gold-400 hover:text-gold-300 text-sm disabled:text-parchment-600"
          >
            <Save className="w-4 h-4" />
            <span>End Session</span>
          </button>
        </div>

        <CharacterSidebar
          character={character}
          onWeaponSelectionChange={handleWeaponSelectionChange}
          onAttackRoll={(result) => {
            // Format attack roll message
            const attackTotal = result.attackRoll + result.strMod
            const damageTotal = result.damageRoll.total + result.strMod
            const isNat20 = result.attackRoll === 20
            const isNat1 = result.attackRoll === 1

            const attackContent = `⚔️ **${result.weapon} Attack**\n` +
              `Attack: d20 = ${result.attackRoll}${result.strMod !== 0 ? ` ${result.strMod > 0 ? '+' : ''}${result.strMod} STR` : ''} = **${attackTotal}**` +
              `${isNat20 ? ' (Natural 20!)' : ''}${isNat1 ? ' (Natural 1!)' : ''}\n` +
              `Damage: ${result.damageRoll.rolls.join('+')}${result.strMod !== 0 ? ` ${result.strMod > 0 ? '+' : ''}${result.strMod}` : ''} = **${damageTotal}**\n` +
              `(THAC0 ${result.thac0} - needs ${result.thac0 - attackTotal} or worse AC to hit)`

            // Add to chat
            const attackMsg: Message = {
              id: `attack-${Date.now()}`,
              role: 'dice',
              content: attackContent,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, attackMsg])

            // Send dice roll to DM via WebSocket
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              // First send the dice roll data
              wsRef.current.send(
                JSON.stringify({
                  type: 'dice_roll',
                  notation: `d20+${result.strMod} (${result.weapon} attack)`,
                  rolls: [result.attackRoll],
                  modifier: result.strMod,
                  total: attackTotal,
                  extra: {
                    damage: damageTotal,
                    damageRolls: result.damageRoll.rolls,
                    weapon: result.weapon,
                    thac0: result.thac0,
                  },
                })
              )
              // Then send a player action so the DM responds using the roll
              wsRef.current.send(
                JSON.stringify({
                  type: 'player_action',
                  content: `I attack with my ${result.weapon}! (I rolled ${attackTotal} to hit, ${damageTotal} damage)`,
                })
              )
            }
          }}
          onDropItem={(itemId, itemName) => {
            // Add drop message to chat
            const dropMsg: Message = {
              id: `drop-${Date.now()}`,
              role: 'user',
              content: `*drops ${itemName}*`,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, dropMsg])

            // Send drop action to DM
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(
                JSON.stringify({
                  type: 'player_action',
                  content: `I drop my ${itemName}.`,
                })
              )
            }
          }}
          onToggleEquipped={(itemId, equipped, updatedItems) => {
            // Update character attributes with new equipped_items
            const currentAttrs = character?.attributes || {}
            updateCharacterMutation.mutate({
              ...currentAttrs,
              equipped_items: updatedItems,
            })

            // Find the item name for the message
            const item = updatedItems.find((i) => i.id === itemId)
            if (item) {
              const action = equipped ? 'equips' : 'removes'
              const toggleMsg: Message = {
                id: `equip-${Date.now()}`,
                role: 'user',
                content: `*${action} ${item.name}*`,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, toggleMsg])
            }
          }}
          onAbilityCheck={(result) => {
            // Format ability/save check message
            let content: string
            if (result.type === 'ability') {
              const modText = result.modifier ? ` (${result.modifier >= 0 ? '+' : ''}${result.modifier})` : ''
              content = `🎲 **${result.name.charAt(0).toUpperCase() + result.name.slice(1)} Check**\n` +
                `d20 = **${result.roll}**${modText}`
            } else {
              // Saving throw
              const successText = result.success ? '✅ Success!' : '❌ Failed!'
              content = `🎲 **${result.name} Save**\n` +
                `d20 = **${result.roll}** vs target ${result.target}+ → ${successText}`
            }

            // Add to chat
            const checkMsg: Message = {
              id: `check-${Date.now()}`,
              role: 'dice',
              content,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, checkMsg])

            // Send dice roll to DM via WebSocket
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(
                JSON.stringify({
                  type: 'dice_roll',
                  notation: result.type === 'ability' ? `d20 (${result.name} check)` : `d20 (${result.name} save)`,
                  rolls: [result.roll],
                  modifier: result.modifier || 0,
                  total: result.roll,
                })
              )
            }
          }}
        />

        {/* Spell Panel - only shows for spellcasting classes */}
        {characterId && (
          <SpellPanel
            characterId={characterId}
            onCastSpell={(spell) => {
              // Add cast message to chat
              const castMsg: Message = {
                id: `cast-${Date.now()}`,
                role: 'user',
                content: `*casts ${spell.name}*`,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, castMsg])

              // Send cast action to DM
              if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.send(
                  JSON.stringify({
                    type: 'player_action',
                    content: `I cast ${spell.name}! (${spell.range}, ${spell.duration})`,
                  })
                )
              }
            }}
            onOpenSpellbook={() => setShowSpellbook(true)}
          />
        )}
      </div>

      {/* Middle Column - Chat */}
      <div className="flex flex-col min-h-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto card mb-4">
          <div className="space-y-4">
            {/* Initial loading placeholder - shown when no messages and waiting for DM */}
            {chatMessages.length === 0 && !streamingContent && (
              <div className="flex flex-col items-center justify-center h-full py-16">
                <div className="relative mb-6">
                  <Loader className="w-12 h-12 text-parchment-500 animate-spin" />
                  <div className="absolute inset-0 w-12 h-12 border-2 border-parchment-700 rounded-full animate-pulse" />
                </div>
                <h3 className="font-display text-xl text-parchment-200 mb-2">
                  Travelling to a far away land...
                </h3>
                <p className="text-parchment-500 text-sm text-center max-w-xs">
                  {isConnected
                    ? 'The Dungeon Master is preparing your adventure'
                    : 'Connecting to the realm...'}
                </p>
                <div className="mt-4 flex gap-1">
                  <span className="w-2 h-2 bg-parchment-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-parchment-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-parchment-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}

            {chatMessages.map((message) => (
              <div
                key={message.id}
                className={`${
                  message.role === 'user'
                    ? 'ml-12 bg-dungeon-600 rounded-lg p-4'
                    : message.role === 'system'
                    ? 'mx-8 bg-red-900/30 rounded-lg p-3 text-sm border border-red-800'
                    : message.role === 'dice'
                    ? 'mx-8 bg-amber-900/30 rounded-lg p-3 text-sm border border-amber-700'
                    : 'mr-12 bg-dungeon-700 rounded-lg p-4 border-l-4 border-parchment-600'
                }`}
              >
                <div className="text-parchment-500 text-xs mb-1">
                  {message.role === 'user' && 'You'}
                  {message.role === 'assistant' && 'Dungeon Master'}
                  {message.role === 'system' && 'System'}
                  {message.role === 'dice' && 'Dice Roll'}
                </div>
                <div className="text-parchment-200 whitespace-pre-wrap">
                  {message.role === 'dice' ? renderMarkdown(message.content) : message.content}
                </div>
              </div>
            ))}

            {/* Streaming content */}
            {streamingContent && (
              <div className="mr-12 bg-dungeon-700 rounded-lg p-4 border-l-4 border-parchment-600">
                <div className="text-parchment-500 text-xs mb-1">Dungeon Master</div>
                <div className="text-parchment-200 whitespace-pre-wrap">{streamingContent}</div>
              </div>
            )}

            {/* Loading indicator for subsequent messages */}
            {isLoading && !streamingContent && chatMessages.length > 0 && (
              <div className="mr-12 bg-dungeon-700 rounded-lg p-4 border-l-4 border-parchment-600">
                <div className="text-parchment-500 text-xs mb-1">Dungeon Master</div>
                <Loader className="w-5 h-5 text-parchment-400 animate-spin" />
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Action Suggestions & Input */}
        <div className="space-y-2">
          <ActionSuggestions
            onAction={(action) => setInput(action)}
            gameState={gameState}
            disabled={isLoading || !isConnected}
          />
          {/* Dice Roller above chat input */}
          <DiceRoller
            compact
            onRoll={(result) => {
              const rollContent = `🎲 Rolled ${result.notation}: [${result.rolls.join(', ')}]${
                result.modifier !== 0 ? (result.modifier > 0 ? ` + ${result.modifier}` : ` - ${Math.abs(result.modifier)}`) : ''
              } = **${result.total}**${
                result.notation.includes('d20') && result.rolls[0] === 20 ? ' (Natural 20!)' : ''
              }${result.notation.includes('d20') && result.rolls[0] === 1 ? ' (Natural 1!)' : ''}`

              // Add dice roll result to chat (using 'dice' role to show in main chat)
              const rollMsg: Message = {
                id: `roll-${Date.now()}`,
                role: 'dice',
                content: rollContent,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, rollMsg])

              // Send dice roll to DM via WebSocket so they can reference it
              if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.send(
                  JSON.stringify({
                    type: 'dice_roll',
                    notation: result.notation,
                    rolls: result.rolls,
                    modifier: result.modifier,
                    total: result.total,
                  })
                )
              }
            }}
          />
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="What do you do?"
              className="input flex-1"
              disabled={isLoading || !isConnected}
            />
            <button onClick={handleSend} disabled={!input.trim() || isLoading || !isConnected} className="btn btn-primary">
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Right Column - Game Log, Journal & Status */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        <StatusPanel
          location={gameState.location}
          conditions={gameState.conditions}
          isConnected={isConnected}
          sessionId={sessionId}
        />
        {timeData && <CalendarPanel timeData={timeData} />}
        <MapPanel
          mapData={mapData}
          onClose={() => setMapData(null)}
          onNavigateTo={(location) => {
            // Send navigation message to DM via WebSocket
            const navMsg: Message = {
              id: `nav-${Date.now()}`,
              role: 'user',
              content: `*heads towards ${location}*`,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, navMsg])

            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(
                JSON.stringify({
                  type: 'player_action',
                  content: `I want to go to ${location}.`,
                })
              )
            }
          }}
        />
        <GameLog messages={toolMessages} />
        {selectedCampaign && characterId && sessionId && (
          <JournalPanel
            campaignId={selectedCampaign}
            characterId={characterId}
            sessionId={sessionId}
          />
        )}
      </div>

      {/* Session Recap Modal */}
      {showRecap && recapData && (
        <SessionRecap
          recap={recapData}
          onDismiss={() => setShowRecap(false)}
        />
      )}

      {/* Campaign Framing Modal */}
      {showFraming && framingData && (
        <CampaignFraming
          framing={framingData}
          onDismiss={() => setShowFraming(false)}
        />
      )}

      {/* Spellbook Modal */}
      {showSpellbook && characterId && (
        <SpellbookModal
          characterId={characterId}
          onClose={() => setShowSpellbook(false)}
        />
      )}

      {/* End Session Modal */}
      {showEndSession && (
        <EndSessionModal
          summary={sessionSummary}
          isEnding={isEndingSession}
          onConfirmEnd={handleEndSession}
          onCancel={() => setShowEndSession(false)}
          onClose={handleCloseEndSession}
        />
      )}
    </div>
  )
}
