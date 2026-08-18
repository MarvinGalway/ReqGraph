import type { NodeLabel } from "../types";
import { NODE_LABELS } from "../types";
import { LABEL_COLORS } from "../lib/palette";

interface Props {
  selected: Set<NodeLabel>;
  counts: Partial<Record<NodeLabel, number>>;
  onToggle: (label: NodeLabel) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
}

export function TypeFilter({ selected, counts, onToggle, onSelectAll, onSelectNone }: Props) {
  return (
    <div className="type-filter">
      <div className="type-filter-header">
        <h2>Node types</h2>
        <div className="type-filter-actions">
          <button onClick={onSelectAll}>All</button>
          <button onClick={onSelectNone}>None</button>
        </div>
      </div>
      <ul>
        {NODE_LABELS.map((label) => (
          <li key={label}>
            <label className="type-filter-item">
              <input
                type="checkbox"
                checked={selected.has(label)}
                onChange={() => onToggle(label)}
              />
              <span className="swatch" style={{ background: LABEL_COLORS[label] }} />
              <span className="type-filter-name">{label}</span>
              <span className="type-filter-count">{counts[label] ?? 0}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
