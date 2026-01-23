import { io, Socket } from 'socket.io-client'

export interface WebSocketMessage {
  type: 'text' | 'tool_result' | 'complete' | 'error'
  content?: string
  tool_name?: string
  result?: Record<string, unknown>
  stop_reason?: string
  error?: string
}

export type MessageHandler = (message: WebSocketMessage) => void

export class WebSocketClient {
  private socket: Socket | null = null
  private sessionId: string | null = null
  private messageHandlers: Set<MessageHandler> = new Set()
  private connectionHandlers: Set<(connected: boolean) => void> = new Set()

  connect(sessionId: string) {
    if (this.socket?.connected && this.sessionId === sessionId) {
      return
    }

    this.disconnect()
    this.sessionId = sessionId

    this.socket = io('/', {
      path: '/socket.io',
      transports: ['websocket', 'polling'],
    })

    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.socket?.emit('join_session', { session_id: sessionId })
      this.notifyConnectionHandlers(true)
    })

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
      this.notifyConnectionHandlers(false)
    })

    this.socket.on('dm_response', (data: WebSocketMessage) => {
      this.notifyMessageHandlers(data)
    })

    this.socket.on('session_joined', (data: { session_id: string }) => {
      console.log('Joined session:', data.session_id)
    })

    this.socket.on('error', (error: { message: string }) => {
      console.error('WebSocket error:', error)
      this.notifyMessageHandlers({
        type: 'error',
        error: error.message,
      })
    })
  }

  disconnect() {
    if (this.socket) {
      if (this.sessionId) {
        this.socket.emit('leave_session', { session_id: this.sessionId })
      }
      this.socket.disconnect()
      this.socket = null
      this.sessionId = null
    }
  }

  sendMessage(content: string) {
    if (!this.socket?.connected || !this.sessionId) {
      console.error('Not connected to session')
      return
    }

    this.socket.emit('player_action', {
      session_id: this.sessionId,
      action: content,
    })
  }

  onMessage(handler: MessageHandler) {
    this.messageHandlers.add(handler)
    return () => this.messageHandlers.delete(handler)
  }

  onConnectionChange(handler: (connected: boolean) => void) {
    this.connectionHandlers.add(handler)
    return () => this.connectionHandlers.delete(handler)
  }

  get isConnected(): boolean {
    return this.socket?.connected ?? false
  }

  private notifyMessageHandlers(message: WebSocketMessage) {
    this.messageHandlers.forEach((handler) => handler(message))
  }

  private notifyConnectionHandlers(connected: boolean) {
    this.connectionHandlers.forEach((handler) => handler(connected))
  }
}

export const wsClient = new WebSocketClient()
