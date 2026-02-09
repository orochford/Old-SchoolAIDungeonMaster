import { useMemo } from 'react'
import dagre from 'dagre'
import type { Node, Edge } from '@xyflow/react'

const NODE_WIDTH = 200
const NODE_HEIGHT = 80

export function useGraphLayout(
  rawNodes: Node[],
  rawEdges: Edge[],
  direction: 'TB' | 'LR' = 'TB'
) {
  return useMemo(() => {
    if (rawNodes.length === 0) return { nodes: [], edges: rawEdges }

    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({
      rankdir: direction,
      nodesep: 60,
      ranksep: 100,
      marginx: 40,
      marginy: 40,
    })

    for (const node of rawNodes) {
      g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    }

    for (const edge of rawEdges) {
      g.setEdge(edge.source, edge.target)
    }

    dagre.layout(g)

    const nodes = rawNodes.map((node) => {
      const pos = g.node(node.id)
      return {
        ...node,
        position: {
          x: pos.x - NODE_WIDTH / 2,
          y: pos.y - NODE_HEIGHT / 2,
        },
      }
    })

    return { nodes, edges: rawEdges }
  }, [rawNodes, rawEdges, direction])
}
