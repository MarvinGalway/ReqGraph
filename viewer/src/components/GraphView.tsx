import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import type { GraphEdge, GraphNode, NodeLabel } from "../types";
import { LABEL_COLORS, NODE_SIZES, INVALID_HIGHLIGHT_COLOR, GRAPH_THEME, type Theme } from "../lib/palette";
import { buildNodeCodes, titleFor } from "../lib/nodeDisplay";
import { connectedSubgraph } from "../lib/subgraph";

cytoscape.use(fcose);

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  visibleLabels: Set<NodeLabel>;
  highlightInvalid: boolean;
  focusNodeIds: Set<string> | null;
  searchQuery: string;
  theme: Theme;
  onSelectNode: (node: GraphNode | null) => void;
}

function buildStyle(theme: Theme): cytoscape.StylesheetJson {
  const colors = GRAPH_THEME[theme];
  const perLabel = (Object.entries(LABEL_COLORS) as [NodeLabel, string][]).map(
    ([label, color]) => ({
      selector: `node[label = "${label}"]`,
      style: { "background-color": color, width: NODE_SIZES[label], height: NODE_SIZES[label] },
    })
  );
  return [
    {
      selector: "node",
      style: {
        // Color alone carries the type; the label is just a short stable
        // code (e.g. "RQ1") so nodes stay identifiable without clutter.
        label: "data(code)",
        "font-size": 8,
        color: colors.nodeText,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 3,
        width: 22,
        height: 22,
        "border-width": 1,
        "border-color": colors.nodeBorder,
      },
    },
    ...perLabel,
    {
      // A "module" CodeUnit is the file itself, not a unit of behavior — it
      // can never have evidence/a Contract (bootstrap-observe skips
      // non-function/method kinds by design) and is easy to mistake for the
      // real symbol otherwise, since both share the same color/shape.
      // Smaller, fainter, square: reads as "container", not "component".
      selector: 'node[label = "CodeUnit"][kind = "module"]',
      style: {
        shape: "round-rectangle",
        width: 14,
        height: 14,
        "background-opacity": 0.55,
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.2,
        "line-color": colors.edgeLine,
        "target-arrow-color": colors.edgeLine,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.8,
        "curve-style": "bezier",
        "font-size": 7,
        color: colors.edgeText,
        label: "data(relType)",
        "text-rotation": "autorotate",
        // Without a background the label just sits on top of the line with
        // nothing behind it, so the edge visually strikes through the text
        // instead of the text reading over it — matches the graph canvas
        // background (must stay equal to --bg-canvas in styles.css) so the
        // line looks like it stops at the label, not crosses it.
        "text-background-color": colors.canvasBg,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
      },
    },
    {
      selector: "node.dimmed",
      style: { opacity: 0.2 },
    },
    {
      selector: "node.emphasized",
      style: {
        "border-width": 3,
        "border-color": INVALID_HIGHLIGHT_COLOR,
        "border-style": "dashed",
      },
    },
    {
      selector: "node.selected",
      style: {
        "border-width": 4,
        "border-color": colors.nodeText,
      },
    },
    {
      selector: "node.search-match",
      style: {
        "border-width": 3,
        "border-color": "#4c6ef5",
        "border-style": "solid",
        "background-opacity": 1,
      },
    },
  ] as cytoscape.StylesheetJson;
}

const ZOOM_STEP = 1.25;
const DBLCLICK_ZOOM_STEP = 1.6;

export function GraphView({
  nodes,
  edges,
  visibleLabels,
  highlightInvalid,
  focusNodeIds,
  searchQuery,
  theme,
  onSelectNode,
}: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const onSelectNodeRef = useRef(onSelectNode);
  onSelectNodeRef.current = onSelectNode;
  // Read fresh in the mount-once effect below via a ref, same reason as
  // nodesRef: that effect must not re-run (it would destroy/recreate the
  // whole cytoscape instance) just because the theme toggled.
  const themeRef = useRef(theme);
  themeRef.current = theme;
  // The tap handler below is registered once, on mount, so it must read
  // `nodes` through a ref rather than closing over the prop directly —
  // otherwise it keeps matching against the very first (often empty,
  // pre-fetch) `nodes` array and clicks silently do nothing.
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  const codes = useMemo(() => buildNodeCodes(nodes), [nodes]);

  const searchMatchIds = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return null;
    const matches = new Set<string>();
    for (const n of nodes) {
      const code = codes.get(n.cyId)?.toLowerCase() ?? "";
      const title = titleFor(n.label, n.props).toLowerCase();
      if (code === query || title.includes(query)) matches.add(n.cyId);
    }
    return matches;
  }, [nodes, codes, searchQuery]);

  // A search result isn't just the matched node(s) in isolation — it's the
  // whole connected tree reachable from them (same traversal as "focus on
  // Requirement"), not just direct neighbors, so e.g. searching "CU13" pulls
  // in everything transitively linked to it. The match itself always shows;
  // everything else reached is still filtered by the type filter.
  const searchFocusIds = useMemo(() => {
    if (!searchMatchIds || searchMatchIds.size === 0) return null;
    const reachable = new Set<string>();
    for (const matchId of searchMatchIds) {
      for (const id of connectedSubgraph(matchId, nodes, edges)) reachable.add(id);
    }
    const nodeById = new Map(nodes.map((n) => [n.cyId, n]));
    const focus = new Set<string>();
    for (const id of reachable) {
      if (searchMatchIds.has(id)) {
        focus.add(id);
        continue;
      }
      const node = nodeById.get(id);
      if (node && visibleLabels.has(node.label)) focus.add(id);
    }
    return focus;
  }, [searchMatchIds, nodes, edges, visibleLabels]);

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      style: buildStyle(themeRef.current),
      wheelSensitivity: 0.25,
    });
    cy.on("tap", "node", (evt) => {
      const nodeId = evt.target.id();
      const match = nodesRef.current.find((n) => n.cyId === nodeId) ?? null;
      onSelectNodeRef.current(match);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) onSelectNodeRef.current(null);
    });
    // Double-click/double-tap anywhere (node or background) zooms in
    // centered on the click point, same convention as maps.
    cy.on("dbltap", (evt) => {
      cy.zoom({
        level: cy.zoom() * DBLCLICK_ZOOM_STEP,
        renderedPosition: evt.renderedPosition,
      });
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cy is created once; data is synced via the effect below
  }, []);

  useEffect(() => {
    function onFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === wrapperRef.current);
      // The container's size changes when entering/exiting fullscreen;
      // cytoscape caches its canvas dimensions and needs telling.
      requestAnimationFrame(() => cyRef.current?.resize());
    }
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    cyRef.current?.style(buildStyle(theme));
  }, [theme]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    // Priority: an active search result narrows the view to that match plus
    // its neighbors; failing that, a Requirement-focus (from the
    // Requirements tab) narrows it to that chain; failing that, the normal
    // type filter.
    const visibleNodes = searchFocusIds
      ? nodes.filter((n) => searchFocusIds.has(n.cyId))
      : focusNodeIds
        ? nodes.filter((n) => focusNodeIds.has(n.cyId))
        : nodes.filter((n) => visibleLabels.has(n.label));
    const visibleIds = new Set(visibleNodes.map((n) => n.cyId));
    const visibleEdges = edges.filter(
      (e) => visibleIds.has(e.sourceCyId) && visibleIds.has(e.targetCyId)
    );

    const elements: ElementDefinition[] = [
      ...visibleNodes.map((n) => ({
        data: {
          id: n.cyId,
          label: n.label,
          nodeId: n.id,
          code: codes.get(n.cyId) ?? n.label,
          kind: n.props.kind,
          knowledge_status: n.props.knowledge_status,
        },
      })),
      ...visibleEdges.map((e) => ({
        data: {
          id: e.cyId,
          source: e.sourceCyId,
          target: e.targetCyId,
          relType: e.relType,
        },
      })),
    ];

    cy.elements().remove();
    cy.add(elements);
    // fcose (force-directed) instead of dagre: dagre ranks every node with
    // no edges into the same column, which collapsed the graph into a
    // single vertical line since most ConfigUnit nodes are edgeless. fcose
    // spreads connected clusters with a force simulation and tiles
    // disconnected nodes into a packed grid instead of stacking them.
    const layoutOptions = {
      name: "fcose",
      quality: "default",
      randomize: true,
      animate: false,
      fit: true,
      padding: 40,
      nodeSeparation: 60,
      idealEdgeLength: 80,
      nodeRepulsion: 8000,
      packComponents: true,
      tile: true,
      // cytoscape-fcose's option set isn't modeled in @types/cytoscape's
      // LayoutOptions union, so this is cast rather than typed inline.
    } as unknown as cytoscape.LayoutOptions;
    cy.layout(layoutOptions).run();
  }, [nodes, edges, visibleLabels, focusNodeIds, searchFocusIds, codes]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("emphasized").removeClass("dimmed").removeClass("search-match");

    if (highlightInvalid) {
      cy.nodes('[knowledge_status != "validated"]').addClass("emphasized");
      cy.nodes('[knowledge_status = "validated"]').addClass("dimmed");
    }

    // Filtering (above) already narrows the view to the match + its
    // neighbors when a search is active — this just distinguishes the
    // actual match from the neighbors shown for context.
    if (searchMatchIds) {
      cy.nodes().forEach((n) => {
        if (searchMatchIds.has(n.id())) n.addClass("search-match");
      });
    }
  }, [highlightInvalid, searchMatchIds, searchFocusIds, nodes, edges, visibleLabels, focusNodeIds]);

  function zoomBy(factor: number) {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({
      level: cy.zoom() * factor,
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    });
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void wrapperRef.current?.requestFullscreen();
    }
  }

  return (
    <div ref={wrapperRef} className="graph-view-wrapper">
      <div ref={containerRef} className="graph-view" />
      <div className="graph-controls">
        <button onClick={() => zoomBy(ZOOM_STEP)} title="Zoom in">
          +
        </button>
        <button onClick={() => zoomBy(1 / ZOOM_STEP)} title="Zoom out">
          −
        </button>
        <button onClick={toggleFullscreen} title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}>
          {isFullscreen ? "⤡" : "⛶"}
        </button>
      </div>
    </div>
  );
}
