import { useEffect, useCallback } from 'react'
import { wsClient, WebSocketMessage } from '@/services/websocket/WebSocketClient'
import { useGameStore } from '@/stores/gameStore'

export function useWebSocket(sessionId: string) {
  const {
    isConnected,
    isStreaming,
    setConnected,
    appendToStreaming,
    finalizeStreaming,
    updateCharacter,
    setLocation,
    addCondition,
    removeCondition,
  } = useGameStore()

  useEffect(() => {
    if (!sessionId) return

    // Connect to session
    wsClient.connect(sessionId)

    // Handle connection changes
    const unsubConnection = wsClient.onConnectionChange((connected) => {
      setConnected(connected)
    })

    // Handle messages
    const unsubMessage = wsClient.onMessage((message: WebSocketMessage) => {
      handleMessage(message)
    })

    return () => {
      unsubConnection()
      unsubMessage()
      wsClient.disconnect()
    }
  }, [sessionId])

  const handleMessage = useCallback((message: WebSocketMessage) => {
    switch (message.type) {
      case 'text':
        if (message.content) {
          appendToStreaming(message.content)
        }
        break

      case 'tool_result':
        // Handle specific tool results
        if (message.tool_name && message.result) {
          handleToolResult(message.tool_name, message.result)
        }
        break

      case 'complete':
        finalizeStreaming()
        break

      case 'error':
        console.error('DM error:', message.error)
        finalizeStreaming()
        break
    }
  }, [appendToStreaming, finalizeStreaming])

  const handleToolResult = useCallback((toolName: string, result: Record<string, unknown>) => {
    switch (toolName) {
      case 'apply_damage_or_healing':
        if (result.target === 'player') {
          updateCharacter({
            current_hp: result.new_hp as number,
          })
        }
        break

      case 'update_game_state':
        const updates = result.updates as Record<string, unknown>
        if (updates?.location) {
          setLocation(updates.location as string)
        }
        if (updates?.added_condition) {
          addCondition(updates.added_condition as string)
        }
        if (updates?.removed_condition) {
          removeCondition(updates.removed_condition as string)
        }
        break

      case 'award_xp':
        // Could update character XP here
        break
    }
  }, [updateCharacter, setLocation, addCondition, removeCondition])

  const sendMessage = useCallback((content: string) => {
    wsClient.sendMessage(content)
  }, [])

  return {
    isConnected,
    isStreaming,
    sendMessage,
  }
}
