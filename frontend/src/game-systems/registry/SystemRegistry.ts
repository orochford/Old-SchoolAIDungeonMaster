import type { GameSystemConfig } from '../types/base.types'

class SystemRegistry {
  private systems: Map<string, GameSystemConfig> = new Map()

  register(config: GameSystemConfig) {
    if (this.systems.has(config.id)) {
      console.warn(`System ${config.id} is already registered, overwriting.`)
    }
    this.systems.set(config.id, config)
  }

  get(systemId: string): GameSystemConfig | undefined {
    return this.systems.get(systemId)
  }

  getAll(): GameSystemConfig[] {
    return Array.from(this.systems.values())
  }

  has(systemId: string): boolean {
    return this.systems.has(systemId)
  }

  unregister(systemId: string): boolean {
    return this.systems.delete(systemId)
  }
}

export const systemRegistry = new SystemRegistry()

// Auto-load systems
export async function loadSystem(systemId: string): Promise<GameSystemConfig | null> {
  try {
    switch (systemId) {
      case 'bx-dnd':
        const { bxDndConfig } = await import('../bx-dnd/config')
        systemRegistry.register(bxDndConfig)
        return bxDndConfig
      default:
        console.error(`Unknown system: ${systemId}`)
        return null
    }
  } catch (error) {
    console.error(`Failed to load system ${systemId}:`, error)
    return null
  }
}

export function getSystem(systemId: string): GameSystemConfig | undefined {
  return systemRegistry.get(systemId)
}
