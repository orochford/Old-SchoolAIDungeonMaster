import { create } from 'zustand'

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

interface Character {
  name: string
  level: number
  character_class: string
  current_hp: number
  max_hp: number
  armor_class: number
  thac0: number
  ability_scores: {
    strength: number
    intelligence: number
    wisdom: number
    dexterity: number
    constitution: number
    charisma: number
  }
}

interface CombatParticipant {
  name: string
  current_hp: number
  max_hp: number
  is_current_turn: boolean
  initiative: number
}

interface Combat {
  round: number
  participants: CombatParticipant[]
}

interface GameStore {
  // Session state
  sessionId: string | null
  isConnected: boolean
  isStreaming: boolean

  // Messages
  messages: Message[]
  streamingContent: string

  // Character
  character: Character | null

  // Combat
  combat: Combat | null

  // Game state
  currentLocation: string
  conditions: string[]

  // Actions
  setSessionId: (id: string | null) => void
  setConnected: (connected: boolean) => void
  setStreaming: (streaming: boolean) => void
  addMessage: (message: Message) => void
  appendToStreaming: (content: string) => void
  finalizeStreaming: (toolResults?: Message['toolResults']) => void
  clearMessages: () => void
  setCharacter: (character: Character | null) => void
  updateCharacter: (updates: Partial<Character>) => void
  setCombat: (combat: Combat | null) => void
  updateCombat: (updates: Partial<Combat>) => void
  setLocation: (location: string) => void
  addCondition: (condition: string) => void
  removeCondition: (condition: string) => void
}

export const useGameStore = create<GameStore>((set, get) => ({
  // Initial state
  sessionId: null,
  isConnected: false,
  isStreaming: false,
  messages: [],
  streamingContent: '',
  character: null,
  combat: null,
  currentLocation: 'Unknown',
  conditions: [],

  // Actions
  setSessionId: (id) => set({ sessionId: id }),

  setConnected: (connected) => set({ isConnected: connected }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  appendToStreaming: (content) =>
    set((state) => ({
      streamingContent: state.streamingContent + content,
      isStreaming: true,
    })),

  finalizeStreaming: (toolResults) => {
    const { streamingContent } = get()
    if (streamingContent) {
      set((state) => ({
        messages: [
          ...state.messages,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: streamingContent,
            timestamp: new Date(),
            toolResults,
          },
        ],
        streamingContent: '',
        isStreaming: false,
      }))
    } else {
      set({ isStreaming: false })
    }
  },

  clearMessages: () => set({ messages: [], streamingContent: '' }),

  setCharacter: (character) => set({ character }),

  updateCharacter: (updates) =>
    set((state) => ({
      character: state.character ? { ...state.character, ...updates } : null,
    })),

  setCombat: (combat) => set({ combat }),

  updateCombat: (updates) =>
    set((state) => ({
      combat: state.combat ? { ...state.combat, ...updates } : null,
    })),

  setLocation: (location) => set({ currentLocation: location }),

  addCondition: (condition) =>
    set((state) => ({
      conditions: state.conditions.includes(condition)
        ? state.conditions
        : [...state.conditions, condition],
    })),

  removeCondition: (condition) =>
    set((state) => ({
      conditions: state.conditions.filter((c) => c !== condition),
    })),
}))
