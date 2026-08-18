import type { GraphNode } from "../types";

interface Props {
  requirements: GraphNode[];
  codes: Map<string, string>;
  selectedCyId: string | null;
  onSelectRequirement: (node: GraphNode) => void;
}

export function RequirementsText({ requirements, codes, selectedCyId, onSelectRequirement }: Props) {
  if (requirements.length === 0) {
    return (
      <div className="requirements-text requirements-text-empty">
        <p>No requirements found.</p>
      </div>
    );
  }

  const sorted = [...requirements].sort((a, b) => {
    const ca = String(a.props.created_at ?? "");
    const cb = String(b.props.created_at ?? "");
    return ca !== cb ? ca.localeCompare(cb) : a.id.localeCompare(b.id);
  });

  return (
    <div className="requirements-text">
      <p className="requirements-text-hint">
        Click a requirement to see its contract, examples, tasks, code and tests in the graph.
      </p>
      {sorted.map((req) => (
        <p
          key={req.cyId}
          className={
            req.cyId === selectedCyId ? "requirement-paragraph active" : "requirement-paragraph"
          }
          onClick={() => onSelectRequirement(req)}
        >
          <span className="requirement-code">{codes.get(req.cyId) ?? "RQ"}</span>
          {String(req.props.text ?? "")}
        </p>
      ))}
    </div>
  );
}
