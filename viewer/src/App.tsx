import { useCallback, useEffect, useMemo, useState } from "react";
import { NODE_LABELS, type GraphData, type GraphNode, type NodeLabel } from "./types";
import { fetchGraph } from "./lib/neo4j";
import { buildNodeCodes, isNotValidated, needsReview } from "./lib/nodeDisplay";
import { connectedSubgraph } from "./lib/subgraph";
import { TypeFilter } from "./components/TypeFilter";
import { GraphView } from "./components/GraphView";
import { DetailPanel } from "./components/DetailPanel";
import { RequirementsText } from "./components/RequirementsText";
import { ReviewQueue } from "./components/ReviewQueue";
import { BootstrapPanel } from "./components/BootstrapPanel";
import type { Theme } from "./lib/palette";

type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "ready" };
type ViewMode = "graph" | "requirements" | "review" | "bootstrap";

const THEME_KEY = "reqgraph-viewer-theme";

function getInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [data, setData] = useState<GraphData>({ nodes: [], edges: [] });
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [selectedLabels, setSelectedLabels] = useState<Set<NodeLabel>>(new Set(NODE_LABELS));
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightInvalid, setHighlightInvalid] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [focusNodeIds, setFocusNodeIds] = useState<Set<string> | null>(null);
  const [focusedRequirementCyId, setFocusedRequirementCyId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const load = useCallback(() => {
    setLoadState({ status: "loading" });
    return fetchGraph()
      .then((result) => {
        setData(result);
        setLoadState({ status: "ready" });
      })
      .catch((err: unknown) => {
        setLoadState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const counts = useMemo(() => {
    const out: Partial<Record<NodeLabel, number>> = {};
    for (const node of data.nodes) out[node.label] = (out[node.label] ?? 0) + 1;
    return out;
  }, [data.nodes]);

  const invalidCount = useMemo(() => data.nodes.filter((n) => isNotValidated(n.props)).length, [
    data.nodes,
  ]);

  const reviewCount = useMemo(() => data.nodes.filter((n) => needsReview(n.props)).length, [
    data.nodes,
  ]);

  const codes = useMemo(() => buildNodeCodes(data.nodes), [data.nodes]);

  const requirements = useMemo(
    () => data.nodes.filter((n) => n.label === "Requirement"),
    [data.nodes]
  );

  const toggleLabel = useCallback((label: NodeLabel) => {
    setSelectedLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }, []);

  const focusOnRequirement = useCallback(
    (node: GraphNode) => {
      // Deliberately doesn't switch viewMode — the Requirements tab shows
      // the list and the resulting graph side by side, so picking a
      // different requirement never hides the list you picked it from.
      setFocusNodeIds(connectedSubgraph(node.cyId, data.nodes, data.edges));
      setSelectedNode(node);
      setFocusedRequirementCyId(node.cyId);
    },
    [data.nodes, data.edges]
  );

  const clearFocus = useCallback(() => {
    setFocusNodeIds(null);
    setFocusedRequirementCyId(null);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>ReqGraph Viewer</h1>
        <div className="app-header-actions">
          <div className="view-toggle">
            <button
              className={viewMode === "bootstrap" ? "active" : ""}
              onClick={() => setViewMode("bootstrap")}
            >
              Bootstrap
            </button>
            <button
              className={viewMode === "graph" ? "active" : ""}
              onClick={() => setViewMode("graph")}
            >
              Graph
            </button>
            <button
              className={viewMode === "requirements" ? "active" : ""}
              onClick={() => setViewMode("requirements")}
            >
              Requirements
            </button>
            <button
              className={viewMode === "review" ? "active" : ""}
              onClick={() => setViewMode("review")}
            >
              Review ({reviewCount})
            </button>
          </div>
          {(viewMode === "graph" || viewMode === "requirements") && focusNodeIds && (
            <button onClick={clearFocus}>Clear focus</button>
          )}
          {viewMode === "graph" && (
            <input
              className="graph-search-input"
              type="search"
              placeholder="Find a node (title or code)…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          )}
          <label className="highlight-toggle">
            <input
              type="checkbox"
              checked={highlightInvalid}
              onChange={(e) => setHighlightInvalid(e.target.checked)}
            />
            Highlight not-validated ({invalidCount})
          </label>
          <button
            className="theme-toggle"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
          <button onClick={load}>Refresh</button>
        </div>
      </header>

      {loadState.status === "error" && (
        <div className="banner banner-error">
          Could not connect to Neo4j: {loadState.message}. Check that{" "}
          <code>docker compose up -d neo4j</code> is running and that <code>viewer/.env.local</code>{" "}
          matches its credentials.
        </div>
      )}
      {loadState.status === "loading" && <div className="banner">Loading graph…</div>}

      {viewMode === "bootstrap" ? (
        <div className="app-body">
          <BootstrapPanel onMutated={load} onOpenReview={() => setViewMode("review")} />
        </div>
      ) : viewMode === "requirements" ? (
        <div className="app-body">
          <RequirementsText
            requirements={requirements}
            codes={codes}
            selectedCyId={focusedRequirementCyId}
            onSelectRequirement={focusOnRequirement}
          />
          {focusNodeIds ? (
            <>
              <GraphView
                nodes={data.nodes}
                edges={data.edges}
                visibleLabels={selectedLabels}
                highlightInvalid={highlightInvalid}
                focusNodeIds={focusNodeIds}
                searchQuery=""
                theme={theme}
                onSelectNode={setSelectedNode}
              />
              {selectedNode && (
                <DetailPanel
                  node={selectedNode}
                  nodes={data.nodes}
                  edges={data.edges}
                  onClose={() => setSelectedNode(null)}
                />
              )}
            </>
          ) : (
            <div className="requirements-graph-placeholder">
              <p>Select a requirement to see its graph.</p>
            </div>
          )}
        </div>
      ) : viewMode === "review" ? (
        <div className="app-body">
          <ReviewQueue nodes={data.nodes} edges={data.edges} codes={codes} onMutated={load} />
        </div>
      ) : (
        <div className="app-body">
          <TypeFilter
            selected={selectedLabels}
            counts={counts}
            onToggle={toggleLabel}
            onSelectAll={() => setSelectedLabels(new Set(NODE_LABELS))}
            onSelectNone={() => setSelectedLabels(new Set())}
          />
          <GraphView
            nodes={data.nodes}
            edges={data.edges}
            visibleLabels={selectedLabels}
            highlightInvalid={highlightInvalid}
            focusNodeIds={focusNodeIds}
            searchQuery={searchQuery}
            theme={theme}
            onSelectNode={setSelectedNode}
          />
          <DetailPanel node={selectedNode} nodes={data.nodes} edges={data.edges} />
        </div>
      )}
    </div>
  );
}
