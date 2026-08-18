import type { NodeLabel } from "../types";

// One distinct hue per node label — used for the graph, the type filter
// swatches, and the detail panel chip, so a color always means the same type.
export const LABEL_COLORS: Record<NodeLabel, string> = {
  Requirement: "#4C6EF5",
  Clarification: "#1098AD",
  Assumption: "#0CA678",
  Contract: "#7950F2",
  Example: "#F59F00",
  Task: "#F76707",
  CodeUnit: "#37B24D",
  ConfigUnit: "#74B816",
  Test: "#D6336C",
  Issue: "#E03131",
  // Was a dark slate (#495057) — fine on the light canvas this shipped
  // against, but nearly invisible against a dark one. A mid-gray keeps the
  // "muted, least-prominent" character while staying visible on both.
  ObservedBehavior: "#868E96",
};

export const INVALID_HIGHLIGHT_COLOR = "#E03131";

export type Theme = "light" | "dark";

// Cytoscape renders to a <canvas>, not the DOM — it can't read CSS custom
// properties, so the graph gets its own small light/dark palette here. The
// two `canvasBg` values MUST match `--bg-canvas` in styles.css exactly:
// edge labels paint this as an opaque background to sit cleanly over the
// line (see GraphView's edge style comment), so any mismatch shows up as a
// visible box around every edge label.
export const GRAPH_THEME: Record<Theme, {
  canvasBg: string;
  nodeText: string;
  nodeBorder: string;
  edgeLine: string;
  edgeText: string;
}> = {
  light: {
    canvasBg: "#fbfbfd",
    nodeText: "#1a1a1a",
    nodeBorder: "#ffffff88",
    edgeLine: "#adb5bd",
    edgeText: "#868e96",
  },
  dark: {
    canvasBg: "#17181c",
    nodeText: "#e9ecef",
    nodeBorder: "#00000066",
    edgeLine: "#6c6f76",
    edgeText: "#adb5bd",
  },
};

// Node diameter by depth in the traceability chain (graph-schema-v0.2.json's
// `categories`, intent -> spec -> plan -> implementation): bigger the more
// abstract/central a label is, smaller the more granular/numerous. Issue and
// ObservedBehavior sit outside that chain (investigative/evidence side
// branches) — sized like the implementation tier they attach to.
export const NODE_SIZES: Record<NodeLabel, number> = {
  Requirement: 30,
  Clarification: 30,
  Assumption: 30,
  Contract: 26,
  Example: 26,
  Task: 24,
  CodeUnit: 20,
  ConfigUnit: 20,
  Test: 20,
  Issue: 20,
  ObservedBehavior: 18,
};
