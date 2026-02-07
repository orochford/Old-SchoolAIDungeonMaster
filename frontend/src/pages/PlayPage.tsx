import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowLeft, Loader, Scroll } from 'lucide-react'
import { api } from '@/services/api'
import { SessionRecap } from '@/components/game/SessionRecap'
import { CampaignFraming } from '@/components/game/CampaignFraming'
import { SpellbookModal } from '@/components/game/SpellbookModal'
import { EndSessionModal } from '@/components/game/EndSessionModal'
import { IllustrationPanel } from '@/components/game/IllustrationPanel'
import { OSRPlayInterface, CharacterData, MessageData } from '@/components/game/OSRPlayInterface'


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
    equipment?: Array<string | { name: string; quantity?: number }>
    race?: string
    armor?: string
    equipped_items?: { id: string; name: string; equipped?: boolean }[]
    weapons?: Array<{ name: string; damage?: string; range?: string; type?: string }>
    spells?: {
      slotsPerLevel?: Record<string, { total: number; used: number }>
      prepared?: { name: string; level: number; prepared?: boolean; cast?: boolean; description?: string }[]
      known?: { name: string; level: number; description?: string }[]
    }
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

interface IllustrationData {
  image_url: string
  title: string
  description: string
  mood: string
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
  const [gameLog, setGameLog] = useState<{ type: string; text: string }[]>([])
  const [showSpellbook, setShowSpellbook] = useState(false)
  const [showEndSession, setShowEndSession] = useState(false)
  const [isEndingSession, setIsEndingSession] = useState(false)
  const [illustrationData, setIllustrationData] = useState<IllustrationData | null>(null)
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
          // Restore game state from both game_state and adventure_state
          {
            const gs = data.game_state as Record<string, unknown> | undefined
            const advState = data.adventure_state as Record<string, unknown> | undefined
            const currentLocation = (advState?.current_location as string) || (gs?.location as string) || undefined
            setGameState({
              location: currentLocation,
              conditions: gs?.conditions as string[] | undefined,
              inCombat: (advState?.in_combat as boolean) || (gs?.in_combat as boolean) || undefined,
            })
            // Add session start to game log
            const adventureTitle = data.adventure_title as string | undefined
            if (adventureTitle) {
              setGameLog((prev) => [...prev, { type: 'event', text: `Adventure: ${adventureTitle}` }])
            }
            if (currentLocation) {
              setGameLog((prev) => [...prev, { type: 'location', text: `Current location: ${currentLocation}` }])
            }
            // Add combat status to game log if in combat
            if (advState?.in_combat || gs?.in_combat) {
              setGameLog((prev) => [...prev, { type: 'combat', text: 'Combat in progress' }])
            }
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
            const newLocation = data.result.location as string
            setGameState((prev) => ({
              ...prev,
              location: newLocation,
            }))
            // Add to game log
            setGameLog((prev) => [...prev, { type: 'location', text: `Entered ${newLocation}` }])
            // Update map if map_update data is included
            if (data.result.map_update) {
              const mapUpdate = data.result.map_update as {
                map_id: string
                map_name: string
                rendered_map: string
                width: number
                height: number
                player_position: { x: number; y: number } | null
                markers: MapData['markers']
                exploration_progress: string
              }
              setMapData({
                map_id: mapUpdate.map_id,
                map_name: mapUpdate.map_name,
                rendered_map: mapUpdate.rendered_map,
                width: mapUpdate.width,
                height: mapUpdate.height,
                player_position: mapUpdate.player_position,
                markers: mapUpdate.markers,
                exploration_progress: mapUpdate.exploration_progress,
              })
            }
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

          // Handle show_illustration - display atmospheric image
          if (data.tool_name === 'show_illustration' && data.result?.shown && data.result?.image_url) {
            setIllustrationData({
              image_url: data.result.image_url as string,
              title: data.result.title as string || '',
              description: data.result.description as string || '',
              mood: data.result.mood as string || 'dramatic',
            })
          }

          // Add to game log based on tool type
          if (data.tool_name === 'add_item' && data.result?.item_name) {
            setGameLog((prev) => [...prev, { type: 'loot', text: `Acquired: ${data.result.item_name}` }])
          }
          if (data.tool_name === 'start_encounter') {
            setGameLog((prev) => [...prev, { type: 'combat', text: `Combat started!` }])
          }
          if (data.tool_name === 'end_encounter') {
            setGameLog((prev) => [...prev, { type: 'combat', text: `Combat ended` }])
          }
          if (data.tool_name === 'apply_damage_or_healing' && data.result?.target) {
            const change = (data.result.old_hp as number) - (data.result.new_hp as number)
            const text = change > 0
              ? `${data.result.target} took ${change} damage`
              : `${data.result.target} healed ${Math.abs(change)} HP`
            setGameLog((prev) => [...prev, { type: 'combat', text }])
          }
          if (data.tool_name === 'advance_time' && data.result?.reason) {
            setGameLog((prev) => [...prev, { type: 'event', text: data.result.reason as string }])
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
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
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


  const handleEndSession = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      // WebSocket disconnected - notify user and close modal
      alert('Connection lost. Please refresh the page to reconnect.')
      setShowEndSession(false)
      return
    }

    setIsEndingSession(true)
    wsRef.current.send(JSON.stringify({ type: 'end_session' }))
  }

  const handleCloseEndSession = () => {
    setShowEndSession(false)
    setSessionSummary(null)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close()
    }
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

      case 'show_illustration':
        if (result.shown) {
          return `🖼️ Displaying: ${result.title || result.description}`
        }
        return `🖼️ No matching illustration found`

      default:
        return `[${toolName}]: ${JSON.stringify(result)}`
    }
  }

  // Adapter: Convert API character format to OSRPlayInterface format
  const adaptCharacterData = (char: Character | undefined): CharacterData | null => {
    if (!char) return null

    const attrs = char.attributes || {}
    const abilityScores = attrs.ability_scores as Record<string, number> | undefined || {}
    const savingThrows = attrs.saving_throws as Record<string, number> | undefined || {}

    // Calculate ability modifiers
    const getModifier = (score: number) => {
      if (score >= 18) return '+3'
      if (score >= 16) return '+2'
      if (score >= 13) return '+1'
      if (score >= 9) return '0'
      if (score >= 6) return '-1'
      if (score >= 4) return '-2'
      return '-3'
    }

    // Convert ability scores to the expected format
    const abilities: Record<string, { score: number; mod: string }> = {}
    for (const [key, value] of Object.entries(abilityScores)) {
      const abilityName = key.substring(0, 3).toUpperCase()
      abilities[abilityName] = { score: value, mod: getModifier(value) }
    }

    // Get weapons from multiple sources
    const weaponKeywords = ['sword', 'axe', 'dagger', 'mace', 'bow', 'spear', 'staff', 'hammer', 'club', 'flail', 'crossbow', 'sling', 'javelin', 'pike', 'halberd', 'morning star', 'warhammer']
    const isWeapon = (name: string) => weaponKeywords.some(k => name.toLowerCase().includes(k))

    let weapons: { name: string; damage: string; melee: boolean }[] = []

    // Source 1: Dedicated weapons field
    if (attrs.weapons && attrs.weapons.length > 0) {
      weapons = attrs.weapons.map((w) => ({
        name: w.name,
        damage: w.damage || '1d6',
        melee: !w.name.toLowerCase().includes('bow') && !w.name.toLowerCase().includes('crossbow') && !w.name.toLowerCase().includes('sling'),
      }))
    }

    // Source 2: equipped_items
    if (weapons.length === 0 && attrs.equipped_items) {
      const weaponItems = attrs.equipped_items.filter((item) => item.name && isWeapon(item.name))
      if (weaponItems.length > 0) {
        weapons = weaponItems.map((w) => ({
          name: w.name,
          damage: '1d6',
          melee: !w.name.toLowerCase().includes('bow') && !w.name.toLowerCase().includes('crossbow'),
        }))
      }
    }

    // Source 3: equipment array
    if (weapons.length === 0 && attrs.equipment) {
      const equipmentWeapons = attrs.equipment
        .map((item) => typeof item === 'string' ? item : item.name)
        .filter((name) => name && isWeapon(name))
      if (equipmentWeapons.length > 0) {
        weapons = equipmentWeapons.map((name) => ({
          name: name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
          damage: '1d6',
          melee: !name.toLowerCase().includes('bow') && !name.toLowerCase().includes('crossbow'),
        }))
      }
    }

    // Fallback to Unarmed
    if (weapons.length === 0) {
      weapons = [{ name: 'Unarmed', damage: '1d2', melee: true }]
    }

    // Get XP needed for next level (B/X D&D progression approximation)
    const xpByLevel: Record<number, number> = {
      1: 0, 2: 2000, 3: 4000, 4: 8000, 5: 16000, 6: 32000, 7: 64000, 8: 120000, 9: 240000, 10: 360000,
    }
    const nextLevelXP = xpByLevel[(char.level || 1) + 1] || (char.experience_points + 50000)

    // Get spells if character is a spellcaster
    const spellsData = attrs.spells as {
      slotsPerLevel?: Record<string, { total: number; used: number }>
      prepared?: { name: string; level: number; prepared?: boolean; cast?: boolean; description?: string }[]
      known?: { name: string; level: number; description?: string }[]
    } | undefined

    // Get armor from multiple sources (shields are separate)
    const armorKeywords = ['leather', 'chain', 'plate', 'mail', 'scale', 'banded', 'splint', 'padded', 'studded', 'ring', 'brigandine', 'armor', 'armour']
    const isArmor = (name: string) => {
      const lower = name.toLowerCase()
      // Exclude shield-only items
      if (lower === 'shield' || lower.match(/^(small|large|tower|wooden|iron|steel)\s+shield$/)) return false
      return armorKeywords.some(k => lower.includes(k))
    }
    const isShield = (name: string) => name.toLowerCase().includes('shield')

    let armor = (attrs.armor as string) || ''
    let shield = ''

    // If no armor field, check equipped_items
    if (!armor && attrs.equipped_items) {
      const armorItem = attrs.equipped_items.find((item) => item.name && isArmor(item.name))
      if (armorItem) armor = armorItem.name
      const shieldItem = attrs.equipped_items.find((item) => item.name && isShield(item.name))
      if (shieldItem) shield = shieldItem.name
    }

    // If still no armor, check equipment array
    if (!armor && attrs.equipment) {
      const equipNames = attrs.equipment.map((item) => typeof item === 'string' ? item : item.name).filter(Boolean)
      const armorInEquip = equipNames.find((name) => isArmor(name!))
      if (armorInEquip) {
        armor = armorInEquip.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
      }
      if (!shield) {
        const shieldInEquip = equipNames.find((name) => isShield(name!))
        if (shieldInEquip) {
          shield = shieldInEquip.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        }
      }
    }

    // Combine armor and shield for display
    const armorDisplay = armor && shield ? `${armor} + ${shield}` : armor || (shield ? `${shield} only` : '')

    return {
      name: char.name,
      class: (attrs.character_class as string) || 'Adventurer',
      level: char.level || 1,
      alignment: (attrs.alignment as string) || 'Neutral',
      race: (attrs.race as string) || 'Human',
      hp: { current: char.current_hp || 0, max: char.max_hp || 0 },
      ac: (attrs.armor_class as number) || 9,
      thac0: (attrs.thac0 as number) || (20 - (char.level || 1)),
      xp: { current: char.experience_points || 0, next: nextLevelXP },
      movement: 120,
      abilities,
      saves: savingThrows,
      weapons,
      armor: armorDisplay || 'None',
      gold: (attrs.gold as number) || 0,
      equipment: ((attrs.equipment || []) as Array<string | { name: string; quantity?: number }>).map(
        (item) => {
          if (typeof item === 'object' && item.name) {
            // Object format: {name: "Torch", quantity: 20}
            const name = item.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            return item.quantity && item.quantity > 1 ? `${name} (x${item.quantity})` : name
          }
          // String format: might be "torch_20" or "Torch (x20)" or just "Rope"
          const str = String(item)
          // Parse underscore format like "torch_20" -> "Torch (x20)"
          const underscoreMatch = str.match(/^([a-z_]+)_(\d+)$/i)
          if (underscoreMatch) {
            const name = underscoreMatch[1].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            const qty = parseInt(underscoreMatch[2])
            return qty > 1 ? `${name} (x${qty})` : name
          }
          // Already formatted or simple name - just title case it
          return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        }
      ),
      spells: spellsData ? {
        slotsPerLevel: spellsData.slotsPerLevel || {},
        prepared: (spellsData.prepared || []).map((s) => ({
          name: s.name,
          level: s.level,
          prepared: s.prepared ?? true,
          cast: s.cast ?? false,
          description: s.description || '',
        })),
        known: (spellsData.known || []).map((s) => ({
          name: s.name,
          level: s.level,
          description: s.description || '',
        })),
      } : undefined,
    }
  }

  // Adapter: Convert messages to OSRPlayInterface format
  const adaptMessages = (msgs: Message[]): MessageData[] => {
    return msgs.filter((m) => m.role !== 'tool').map((msg) => ({
      id: msg.id,
      type: msg.role === 'user' ? 'player' as const :
            msg.role === 'assistant' ? 'dm' as const :
            msg.role === 'dice' ? 'roll' as const :
            'system' as const,
      text: msg.content,
      content: msg.content,
      timestamp: new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }))
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

  // Game session screen - New OSR-style interface
  const adaptedCharacter = adaptCharacterData(character)
  const adaptedMessages = adaptMessages(messages)

  // Handle sending a message through WebSocket
  const handleOSRSendMessage = (text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected, cannot send message')
      return
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])

    // Send to WebSocket
    wsRef.current.send(
      JSON.stringify({
        type: 'player_action',
        content: text,
      })
    )
  }

  // Handle leaving the session
  const handleLeave = () => {
    if (confirm('Leave without saving? Your session will continue where you left off.')) {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }
      navigate(`/characters/${characterId}`)
    }
  }

  if (!adaptedCharacter) {
    return (
      <div className="flex items-center justify-center h-screen bg-dungeon-900">
        <Loader className="w-12 h-12 text-parchment-500 animate-spin" />
      </div>
    )
  }

  // Show loading screen while connecting to session
  if (!isConnected) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-dungeon-900">
        <Loader className="w-16 h-16 text-parchment-500 animate-spin mb-6" />
        <h2 className="text-parchment-200 text-xl font-serif mb-2">Preparing Your Adventure</h2>
        <p className="text-parchment-400 text-sm">
          {startSessionMutation.isPending ? 'Creating session...' : 'Connecting to the realm...'}
        </p>
      </div>
    )
  }

  return (
    <>
      <OSRPlayInterface
        character={adaptedCharacter}
        messages={adaptedMessages}
        streamingContent={streamingContent}
        isConnected={isConnected}
        isLoading={isLoading}
        currentLocation={gameState.location || 'Unknown'}
        timeData={timeData}
        mapData={mapData}
        gameLog={gameLog}
        onSendMessage={handleOSRSendMessage}
        onLeave={handleLeave}
        adventureTitle={framingData?.adventure_title || ''}
        campaignName={campaigns?.find((c) => c.id === selectedCampaign)?.name || ''}
      />

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

      {/* Illustration Display */}
      {illustrationData && (
        <IllustrationPanel
          illustration={illustrationData}
          onDismiss={() => setIllustrationData(null)}
        />
      )}
    </>
  )
}
