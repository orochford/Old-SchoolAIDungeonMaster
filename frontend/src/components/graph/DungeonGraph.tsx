import { useCallback, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { DungeonNode, type DungeonNodeData } from './DungeonNode'
import { DungeonEdge } from './DungeonEdge'
import { useGraphLayout } from './useGraphLayout'
import { NodeDetailPanel } from './NodeDetailPanel'

interface GraphNode {
  id: string
  key: string
  name: string
  dungeon_level: number
  is_empty: boolean
  has_creatures: boolean
  has_items: boolean
  has_traps: boolean
  has_secrets: boolean
  has_npcs: boolean
  is_entrance?: boolean
  creature_summary?: string
  encounter_hd_total?: number
}

interface GraphEdge {
  from_id: string
  to_id: string
  direction: string
  is_secret: boolean
  is_one_way: boolean
}

interface DungeonGraphProps {
  moduleId: string
  moduleTitle: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  playerView?: boolean
  currentLocationKey?: string | null
}

const nodeTypes: NodeTypes = {
  dungeon: DungeonNode,
}

const edgeTypes: EdgeTypes = {
  dungeon: DungeonEdge,
}

export function DungeonGraph({ moduleId, moduleTitle, nodes: rawNodes, edges: rawEdges, playerView, currentLocationKey }: DungeonGraphProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<number | null>(null)

  // Get available dungeon levels
  const levels = useMemo(() => {
    const lvls = [...new Set(rawNodes.map((n) => n.dungeon_level))].sort()
    return lvls
  }, [rawNodes])

  // Filter nodes by level
  const filteredNodeIds = useMemo(() => {
    if (levelFilter === null) return new Set(rawNodes.map((n) => n.id))
    return new Set(rawNodes.filter((n) => n.dungeon_level === levelFilter).map((n) => n.id))
  }, [rawNodes, levelFilter])

  // Build React Flow nodes
  const flowNodes: Node[] = useMemo(
    () =>
      rawNodes
        .filter((n) => filteredNodeIds.has(n.id))
        .map((n) => ({
          id: n.id,
          type: 'dungeon',
          position: { x: 0, y: 0 }, // Will be set by layout
          data: {
            key: n.key,
            name: n.name,
            isEmpty: n.is_empty,
            hasCreatures: n.has_creatures,
            hasItems: n.has_items,
            hasTraps: n.has_traps,
            hasSecrets: n.has_secrets,
            hasNpcs: n.has_npcs,
            dungeonLevel: n.dungeon_level,
            isEntrance: n.is_entrance ?? false,
            creatureSummary: n.creature_summary ?? '',
            encounterHdTotal: n.encounter_hd_total ?? 0,
            selected: n.id === selectedNodeId,
            playerView: playerView || false,
            isCurrentLocation: currentLocationKey === n.id,
            isMystery: playerView && n.name === '?',
          } satisfies DungeonNodeData,
        })),
    [rawNodes, filteredNodeIds, selectedNodeId, playerView, currentLocationKey]
  )

  // Build React Flow edges
  const flowEdges: Edge[] = useMemo(
    () =>
      rawEdges
        .filter((e) => filteredNodeIds.has(e.from_id) && filteredNodeIds.has(e.to_id))
        .map((e, i) => ({
          id: `e-${e.from_id}-${e.to_id}-${i}`,
          source: e.from_id,
          target: e.to_id,
          type: 'dungeon',
          data: {
            isSecret: e.is_secret,
            isOneWay: e.is_one_way,
            direction: e.direction,
          },
          markerEnd: e.is_one_way
            ? { type: MarkerType.ArrowClosed, color: '#6a6250', width: 16, height: 16 }
            : undefined,
        })),
    [rawEdges, filteredNodeIds]
  )

  // Apply dagre layout
  const { nodes: layoutNodes, edges: layoutEdges } = useGraphLayout(flowNodes, flowEdges)

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes)
  const [edges, _setEdges, onEdgesChange] = useEdgesState(layoutEdges)

  // Update nodes when layout changes (e.g., level filter changes)
  useMemo(() => {
    setNodes(layoutNodes)
  }, [layoutNodes, setNodes])

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      setSelectedNodeId((prev) => (prev === node.id ? null : node.id))
      // Update the selected state on all nodes
      setNodes((nds) =>
        nds.map((n) => ({
          ...n,
          data: {
            ...n.data,
            selected: n.id === node.id && selectedNodeId !== node.id,
          },
        }))
      )
    },
    [selectedNodeId, setNodes]
  )

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, selected: false },
      }))
    )
  }, [setNodes])

  // Find the selected node's key for the detail panel
  const selectedNodeKey = selectedNodeId
    ? rawNodes.find((n) => n.id === selectedNodeId)?.key
    : null

  return (
    <div className="w-full h-full relative" style={{ background: '#0a0908' }}>
      {/* Level filter bar - hidden in player view */}
      {!playerView && levels.length > 1 && (
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 px-3 py-1.5 rounded-lg"
          style={{
            background: 'rgba(20,18,16,0.9)',
            border: '1px solid rgba(180,160,100,0.15)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250] mr-2 uppercase tracking-wider">
            Level
          </span>
          <button
            onClick={() => setLevelFilter(null)}
            className="font-['IBM_Plex_Mono',monospace] text-xs px-2.5 py-1 rounded transition-all"
            style={{
              color: levelFilter === null ? '#b8a060' : '#6a6250',
              background: levelFilter === null ? 'rgba(180,160,80,0.1)' : 'transparent',
              border: levelFilter === null ? '1px solid rgba(180,160,80,0.3)' : '1px solid transparent',
            }}
          >
            All
          </button>
          {levels.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className="font-['IBM_Plex_Mono',monospace] text-xs px-2.5 py-1 rounded transition-all"
              style={{
                color: levelFilter === lvl ? '#b8a060' : '#6a6250',
                background: levelFilter === lvl ? 'rgba(180,160,80,0.1)' : 'transparent',
                border: levelFilter === lvl ? '1px solid rgba(180,160,80,0.3)' : '1px solid transparent',
              }}
            >
              {lvl}
            </button>
          ))}
        </div>
      )}

      {/* Title - hidden in player view */}
      {!playerView && (
        <div
          className="absolute top-4 left-4 z-10 px-3 py-1.5 rounded"
          style={{
            background: 'rgba(20,18,16,0.9)',
            border: '1px solid rgba(180,160,100,0.1)',
          }}
        >
          <h2 className="font-['Cinzel',serif] text-sm font-semibold text-[#c8c0aa]">
            {moduleTitle}
          </h2>
          <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250]">
            {rawNodes.length} rooms
          </span>
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="rgba(180,160,100,0.05)" gap={24} size={1} />
        {!playerView && (
          <Controls
            className="!bg-[#1a1816] !border-[rgba(180,160,100,0.15)] !rounded-lg [&>button]:!bg-[#1a1816] [&>button]:!border-[rgba(180,160,100,0.1)] [&>button]:!text-[#6a6250] [&>button:hover]:!bg-[rgba(180,160,100,0.1)]"
            position="bottom-left"
          />
        )}
        {!playerView && (
          <MiniMap
            className="!bg-[#12110f] !border-[rgba(180,160,100,0.1)]"
            nodeColor={() => '#6a6250'}
            maskColor="rgba(10,9,8,0.7)"
            position="bottom-right"
          />
        )}
      </ReactFlow>

      {/* Detail panel - hidden in player view */}
      {!playerView && selectedNodeKey && (
        <NodeDetailPanel
          moduleId={moduleId}
          locationKey={selectedNodeKey}
          onClose={() => {
            setSelectedNodeId(null)
            setNodes((nds) =>
              nds.map((n) => ({
                ...n,
                data: { ...n.data, selected: false },
              }))
            )
          }}
        />
      )}
    </div>
  )
}
