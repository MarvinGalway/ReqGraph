import { useMemo, useState } from "react";
import type { GraphEdge, GraphNode } from "../types";
import { LABEL_COLORS } from "../lib/palette";
import {
  DETAIL_FIELDS,
  METADATA_FIELDS,
  buildNodeCodes,
  parseJsonFields,
  titleFor,
  truncate,
} from "../lib/nodeDisplay";

interface Props {
  node: GraphNode | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  onClose?: () => void;
}

// For a CodeUnit, "what does this do" isn't one of its own fields (path/
// symbol/hash are identifiers, not a description) — it lives on whatever the
// CodeUnit IMPLEMENTS (a Contract's summary) or, failing that, on the
// docstring/source evidence bootstrap-observe already extracted for it
// (EVIDENCES -> ObservedBehavior). Prefer the Contract since it's the
// human-reviewed one; fall back to raw evidence when there's no Contract yet.
function findCodeUnitContext(
  node: GraphNode,
  nodes: GraphNode[],
  edges: GraphEdge[]
): { contract: GraphNode | null; behavior: GraphNode | null } {
  const contractId = edges.find((e) => e.relType === "IMPLEMENTS" && e.sourceCyId === node.cyId)
    ?.targetCyId;
  const contract = contractId ? nodes.find((n) => n.cyId === contractId) ?? null : null;

  const behaviorId = edges.find((e) => e.relType === "EVIDENCES" && e.sourceCyId === node.cyId)
    ?.targetCyId;
  const behavior = behaviorId ? nodes.find((n) => n.cyId === behaviorId) ?? null : null;

  return { contract, behavior };
}

interface AcceptanceCriterion {
  given: string;
  when: string;
  then: string;
}

interface BehavioralSignature {
  input_types?: string[];
  output_types?: string[];
  tags?: string[];
}

interface Decision {
  choice: string;
  rationale: string;
  at: string;
}

interface TaskScope {
  target_contracts?: string[];
  target_codeunits?: string[];
  target_configunits?: string[];
  allowed_paths?: string[];
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function StringList({ items }: { items: unknown[] }) {
  if (items.length === 0) return <span className="empty">—</span>;
  return (
    <ul className="field-list">
      {items.map((item, i) => (
        <li key={i}>{String(item)}</li>
      ))}
    </ul>
  );
}

function AcceptanceList({ items }: { items: AcceptanceCriterion[] }) {
  if (items.length === 0) return <span className="empty">—</span>;
  return (
    <div className="acceptance-list">
      {items.map((item, i) => (
        <div key={i} className="acceptance-item">
          <div>
            <strong>Given</strong> {item.given}
          </div>
          <div>
            <strong>When</strong> {item.when}
          </div>
          <div>
            <strong>Then</strong> {item.then}
          </div>
        </div>
      ))}
    </div>
  );
}

function BehavioralSignatureView({ value }: { value: BehavioralSignature }) {
  const { input_types = [], output_types = [], tags = [] } = value;
  return (
    <div className="behavioral-signature">
      {tags.length > 0 && (
        <div className="chips">
          {tags.map((tag) => (
            <span key={tag} className="chip">
              {tag}
            </span>
          ))}
        </div>
      )}
      {input_types.length > 0 && (
        <div>
          <em>input:</em> {input_types.join(", ")}
        </div>
      )}
      {output_types.length > 0 && (
        <div>
          <em>output:</em> {output_types.join(", ")}
        </div>
      )}
    </div>
  );
}

function DecisionsList({ items }: { items: Decision[] }) {
  if (items.length === 0) return <span className="empty">—</span>;
  return (
    <div className="decisions-list">
      {items.map((item, i) => (
        <div key={i} className="decision-item">
          <div>
            <strong>{item.choice}</strong>
          </div>
          <div className="decision-rationale">{item.rationale}</div>
          <div className="decision-at">{item.at}</div>
        </div>
      ))}
    </div>
  );
}

function ScopeView({ value }: { value: TaskScope }) {
  const groups: [string, string[] | undefined][] = [
    ["Contracts", value.target_contracts],
    ["Code units", value.target_codeunits],
    ["Config units", value.target_configunits],
    ["Allowed paths", value.allowed_paths],
  ];
  const nonEmpty = groups.filter(([, list]) => list && list.length > 0);
  if (nonEmpty.length === 0) return <span className="empty">—</span>;
  return (
    <div className="scope-view">
      {nonEmpty.map(([label, list]) => (
        <div key={label}>
          <em>{label}:</em>
          <StringList items={list ?? []} />
        </div>
      ))}
    </div>
  );
}

function FieldValue({ fieldKey, value }: { fieldKey: string; value: unknown }) {
  if (isEmpty(value)) return <span className="empty">—</span>;

  if (fieldKey === "acceptance") return <AcceptanceList items={value as AcceptanceCriterion[]} />;
  if (fieldKey === "behavioral_signature")
    return <BehavioralSignatureView value={value as BehavioralSignature} />;
  if (fieldKey === "decisions") return <DecisionsList items={value as Decision[]} />;
  if (fieldKey === "scope") return <ScopeView value={value as TaskScope} />;

  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;

  if (Array.isArray(value)) {
    if (typeof value[0] === "string" || value.length === 0) return <StringList items={value} />;
    return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
  }

  if (typeof value === "object") {
    return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
  }

  return <span className="field-text">{String(value)}</span>;
}

export function DetailPanel({ node, nodes, edges, onClose }: Props) {
  const [showMetadata, setShowMetadata] = useState(false);
  const codes = useMemo(() => buildNodeCodes(nodes), [nodes]);

  if (!node) {
    return (
      <div className="detail-panel detail-panel-empty">
        <p>Select a node to see its details.</p>
      </div>
    );
  }

  const props = parseJsonFields(node.label, node.props);
  const fields = DETAIL_FIELDS[node.label];
  const codeContext = node.label === "CodeUnit" ? findCodeUnitContext(node, nodes, edges) : null;

  return (
    <div className="detail-panel">
      <div className="detail-header">
        {onClose && (
          <button className="detail-close" onClick={onClose} title="Close" aria-label="Close">
            ×
          </button>
        )}
        <span className="type-chip" style={{ background: LABEL_COLORS[node.label] }}>
          {node.label}
        </span>
        <h1 className="detail-code">{codes.get(node.cyId) ?? node.label}</h1>
        <h2>{titleFor(node.label, node.props)}</h2>
      </div>

      {codeContext && (
        <div className="code-context">
          <h3>What this does</h3>
          {codeContext.contract ? (
            <>
              <span className="code-context-source">via Contract</span>
              <p>{String(codeContext.contract.props.summary ?? "") || <span className="empty">—</span>}</p>
            </>
          ) : codeContext.behavior ? (
            <>
              <span className="code-context-source">
                {codeContext.behavior.props.evidence_type === "documentation"
                  ? "from docstring"
                  : "from source"}
              </span>
              <p>{truncate(String(codeContext.behavior.props.observed ?? ""), 400)}</p>
            </>
          ) : (
            <p className="empty">
              No description yet — no Contract implements this, and no docstring/test evidence was
              extracted. Run <code>bootstrap-observe</code> (add <code>--legacy</code> for
              undocumented code) to derive one.
            </p>
          )}
        </div>
      )}

      <dl className="field-grid">
        {fields.map(({ key, label }) =>
          isEmpty(props[key]) ? null : (
            <div key={key} className="field-row">
              <dt>{label}</dt>
              <dd>
                <FieldValue fieldKey={key} value={props[key]} />
              </dd>
            </div>
          )
        )}
      </dl>

      <button className="metadata-toggle" onClick={() => setShowMetadata((v) => !v)}>
        {showMetadata ? "Hide" : "Show"} metadata
      </button>
      {showMetadata && (
        <dl className="field-grid metadata">
          {METADATA_FIELDS.map(({ key, label }) =>
            isEmpty(props[key]) ? null : (
              <div key={key} className="field-row">
                <dt>{label}</dt>
                <dd>
                  <FieldValue fieldKey={key} value={props[key]} />
                </dd>
              </div>
            )
          )}
        </dl>
      )}
    </div>
  );
}
