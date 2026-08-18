import type { GraphNode, NodeLabel } from "../types";

// Fields that reqgraph/graph/repositories/base.py JSON-encodes to a string
// on write (see reqgraph/graph/models.py JSON_FIELDS). Reading the raw graph
// bypasses that repository layer, so we decode them back here.
const JSON_FIELDS: Partial<Record<NodeLabel, string[]>> = {
  Contract: ["acceptance"],
  Example: ["input", "expected_output", "behavioral_signature"],
  Task: ["scope", "decisions"],
};

export function parseJsonFields(
  label: NodeLabel,
  props: Record<string, unknown>
): Record<string, unknown> {
  const fields = JSON_FIELDS[label];
  if (!fields) return props;
  const out = { ...props };
  for (const field of fields) {
    const raw = out[field];
    if (typeof raw === "string" && raw.length > 0) {
      try {
        out[field] = JSON.parse(raw);
      } catch {
        // Not valid JSON (e.g. a default empty string) — keep as-is.
      }
    }
  }
  return out;
}

export function truncate(text: string, max = 60): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 1)}…` : oneLine;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

// Every node type has a different "name" field in the schema (Requirement.text,
// Task.title, CodeUnit.path+symbol, ...). This computes one consistent
// display title per node so the graph and the filter/detail panel can label
// nodes uniformly, without adding a redundant `title` property to the graph
// schema itself.
export function titleFor(label: NodeLabel, props: Record<string, unknown>): string {
  switch (label) {
    case "Requirement":
    case "Assumption":
      return truncate(str(props.text)) || "(untitled)";
    case "Clarification":
      return truncate(str(props.question)) || "(untitled)";
    case "Contract":
    case "Example":
      return truncate(str(props.summary)) || `${label} ${String(props.id).slice(0, 8)}`;
    case "Task":
    case "Issue":
      return truncate(str(props.title)) || "(untitled)";
    case "CodeUnit":
      return `${str(props.symbol) || "?"} — ${str(props.path) || "?"}`;
    case "ConfigUnit":
      return `${str(props.key) || "?"} — ${str(props.path) || "?"}`;
    case "Test":
      return str(props.symbol) || str(props.path) || "(untitled)";
    case "ObservedBehavior":
      return truncate(str(props.when) || str(props.given)) || "(untitled)";
    default:
      return String(props.id ?? "?");
  }
}

export interface FieldSpec {
  key: string;
  label: string;
}

// Ordered, human-labeled fields shown in the detail panel per node type —
// only what's specific to that type. Common provenance/status fields live in
// METADATA_FIELDS instead, kept separate so the panel leads with what the
// node actually says.
export const DETAIL_FIELDS: Record<NodeLabel, FieldSpec[]> = {
  Requirement: [
    { key: "text", label: "Text" },
    { key: "source", label: "Source" },
    { key: "trust", label: "Trust" },
    { key: "origin_mode", label: "Origin" },
  ],
  Clarification: [
    { key: "question", label: "Question" },
    { key: "answer", label: "Answer" },
    { key: "answered_by", label: "Answered by" },
    { key: "blocking", label: "Blocking" },
  ],
  Assumption: [
    { key: "text", label: "Text" },
    { key: "rationale", label: "Rationale" },
    { key: "decision_status", label: "Decision" },
  ],
  Contract: [
    { key: "summary", label: "Summary" },
    { key: "preconditions", label: "Preconditions" },
    { key: "postconditions", label: "Postconditions" },
    { key: "invariants", label: "Invariants" },
    { key: "acceptance", label: "Acceptance criteria" },
    { key: "origin_mode", label: "Origin" },
  ],
  Example: [
    { key: "summary", label: "Summary" },
    { key: "input", label: "Input" },
    { key: "expected_output", label: "Expected output" },
    { key: "edge_case", label: "Edge case" },
    { key: "behavioral_signature", label: "Behavioral signature" },
    { key: "origin", label: "Origin" },
  ],
  Task: [
    { key: "title", label: "Title" },
    { key: "phase", label: "Phase" },
    { key: "workflow_status", label: "Workflow status" },
    { key: "definition_of_done", label: "Definition of done" },
    { key: "scope", label: "Scope" },
    { key: "decisions", label: "Decisions" },
    { key: "external_id", label: "External ID" },
  ],
  CodeUnit: [
    { key: "path", label: "Path" },
    { key: "symbol", label: "Symbol" },
    { key: "kind", label: "Kind" },
    { key: "language", label: "Language" },
    { key: "git_commit", label: "Git commit" },
    { key: "hash", label: "Hash" },
  ],
  ConfigUnit: [
    { key: "path", label: "Path" },
    { key: "key", label: "Key" },
    { key: "kind", label: "Kind" },
    { key: "scope_hint", label: "Scope hint" },
    { key: "value_hash", label: "Value hash" },
  ],
  Test: [
    { key: "path", label: "Path" },
    { key: "symbol", label: "Symbol" },
    { key: "framework", label: "Framework" },
    { key: "last_result", label: "Last result" },
  ],
  Issue: [
    { key: "title", label: "Title" },
    { key: "description", label: "Description" },
    { key: "severity", label: "Severity" },
    { key: "classification", label: "Classification" },
    { key: "workflow_status", label: "Workflow status" },
    { key: "reported_by", label: "Reported by" },
    { key: "evidence", label: "Evidence" },
    { key: "resolution", label: "Resolution" },
  ],
  ObservedBehavior: [
    { key: "given", label: "Given" },
    { key: "when", label: "When" },
    { key: "observed", label: "Observed" },
    { key: "evidence_type", label: "Evidence type" },
    { key: "confidence", label: "Confidence" },
  ],
};

export const METADATA_FIELDS: FieldSpec[] = [
  { key: "knowledge_status", label: "Knowledge status" },
  { key: "verification_status", label: "Verification status" },
  { key: "created_by", label: "Created by" },
  { key: "created_at", label: "Created at" },
  { key: "updated_at", label: "Updated at" },
  { key: "source_refs", label: "Source refs" },
  { key: "id", label: "ID" },
];

export function isNotValidated(props: Record<string, unknown>): boolean {
  return props.knowledge_status !== "validated";
}

// The review queue: nodes still in a "raw" state (bootstrap/greenfield
// output not yet looked at by a human). Deliberately excludes `disputed`
// (already reviewed and rejected) and `stale` (was validated, now
// superseded — a revalidation concern, not a first-pass review one).
const UNREVIEWED_STATUSES = new Set(["observed", "inferred", "generated"]);

export function needsReview(props: Record<string, unknown>): boolean {
  return UNREVIEWED_STATUSES.has(String(props.knowledge_status));
}

// Short per-type code shown on graph nodes instead of full text (e.g. "RQ1"
// for the first Requirement) — color already carries the type, this just
// gives each node a stable, compact identifier. Numbered per label, ordered
// by created_at (falling back to id) so the same node keeps the same code
// across a session.
const LABEL_CODE_PREFIX: Record<NodeLabel, string> = {
  Requirement: "RQ",
  Clarification: "CL",
  Assumption: "AS",
  Contract: "CT",
  Example: "EX",
  Task: "TK",
  CodeUnit: "CU",
  ConfigUnit: "CF",
  Test: "TS",
  Issue: "IS",
  ObservedBehavior: "OB",
};

export function buildNodeCodes(nodes: GraphNode[]): Map<string, string> {
  const byLabel = new Map<NodeLabel, GraphNode[]>();
  for (const node of nodes) {
    const list = byLabel.get(node.label);
    if (list) list.push(node);
    else byLabel.set(node.label, [node]);
  }
  const codes = new Map<string, string>();
  for (const [label, list] of byLabel) {
    const sorted = [...list].sort((a, b) => {
      const ca = String(a.props.created_at ?? "");
      const cb = String(b.props.created_at ?? "");
      return ca !== cb ? ca.localeCompare(cb) : a.id.localeCompare(b.id);
    });
    const prefix = LABEL_CODE_PREFIX[label];
    sorted.forEach((node, i) => codes.set(node.cyId, `${prefix}${i + 1}`));
  }
  return codes;
}
