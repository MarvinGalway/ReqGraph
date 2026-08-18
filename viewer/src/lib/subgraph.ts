import type { GraphEdge, GraphNode } from "../types";

// All nodes reachable from `startCyId` following edges in either direction —
// used to focus the graph on one Requirement's full chain (its Contract and
// everything downstream: Examples, Tasks, CodeUnits, ConfigUnits, Tests, ...).
export function connectedSubgraph(
  startCyId: string,
  nodes: GraphNode[],
  edges: GraphEdge[]
): Set<string> {
  const neighbors = new Map<string, string[]>();
  for (const node of nodes) neighbors.set(node.cyId, []);
  for (const edge of edges) {
    neighbors.get(edge.sourceCyId)?.push(edge.targetCyId);
    neighbors.get(edge.targetCyId)?.push(edge.sourceCyId);
  }

  const visited = new Set<string>([startCyId]);
  const queue = [startCyId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of neighbors.get(current) ?? []) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  return visited;
}
