export type NodeLabel =
  | "Requirement"
  | "Clarification"
  | "Assumption"
  | "Contract"
  | "Example"
  | "Task"
  | "CodeUnit"
  | "ConfigUnit"
  | "Test"
  | "Issue"
  | "ObservedBehavior";

// Mirrors reqgraph/graph/models.py:NODE_LABELS — the canonical label list.
export const NODE_LABELS: NodeLabel[] = [
  "Requirement",
  "Clarification",
  "Assumption",
  "Contract",
  "Example",
  "Task",
  "CodeUnit",
  "ConfigUnit",
  "Test",
  "Issue",
  "ObservedBehavior",
];

export interface GraphNode {
  cyId: string;
  label: NodeLabel;
  id: string;
  props: Record<string, unknown>;
}

export interface GraphEdge {
  cyId: string;
  relType: string;
  sourceCyId: string;
  targetCyId: string;
  props: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
