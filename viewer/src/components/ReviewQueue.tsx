import { useEffect, useMemo, useState } from "react";
import type { GraphEdge, GraphNode } from "../types";
import { LABEL_COLORS } from "../lib/palette";
import { needsReview, parseJsonFields, titleFor } from "../lib/nodeDisplay";
import { primaryFieldFor, submitReviewDecision, type ReviewDecision } from "../lib/neo4j";
import { DetailPanel } from "./DetailPanel";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  codes: Map<string, string>;
  onMutated: () => Promise<void>;
}

const REVIEWER_STORAGE_KEY = "reqgraph-viewer-reviewer";
// Bug/Ambiguous/Obsolete/Insufficient don't change knowledge_status (same as
// bootstrap-review CLI), so the node would otherwise reappear at the top of
// this graph-derived queue forever. Track "already looked at, not
// validated" locally per browser instead — doesn't touch the graph, so
// knowledge_status stays an honest signal for any other tool/session.
const DISMISSED_STORAGE_KEY = "reqgraph-viewer-dismissed-reviews";
const NON_VALIDATING_DECISIONS = new Set<ReviewDecision>(["bug", "ambiguous", "obsolete", "insufficient"]);

function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>): void {
  localStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify([...ids]));
}

const DECISIONS: { value: ReviewDecision; label: string; needsNote: boolean; noteRequired: boolean }[] = [
  { value: "correct", label: "Correct", needsNote: false, noteRequired: false },
  { value: "reword", label: "Reword", needsNote: true, noteRequired: false },
  { value: "bug", label: "Bug", needsNote: true, noteRequired: true },
  { value: "ambiguous", label: "Ambiguous", needsNote: true, noteRequired: true },
  { value: "obsolete", label: "Obsolete", needsNote: true, noteRequired: false },
  { value: "insufficient", label: "Insufficient", needsNote: true, noteRequired: false },
];

export function ReviewQueue({ nodes, edges, codes, onMutated }: Props) {
  const allCandidates = useMemo(() => {
    return nodes
      .filter((n) => needsReview(n.props))
      .sort((a, b) => {
        const ca = String(a.props.created_at ?? "");
        const cb = String(b.props.created_at ?? "");
        return ca !== cb ? ca.localeCompare(cb) : a.id.localeCompare(b.id);
      });
  }, [nodes]);

  const [activeCyId, setActiveCyId] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<ReviewDecision | null>(null);
  const [note, setNote] = useState("");
  const [rewordValue, setRewordValue] = useState("");
  const [by, setBy] = useState(() => localStorage.getItem(REVIEWER_STORAGE_KEY) || "human");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() => loadDismissed());
  const [showDismissed, setShowDismissed] = useState(false);

  useEffect(() => {
    localStorage.setItem(REVIEWER_STORAGE_KEY, by);
  }, [by]);

  // Prune dismissed ids once their node leaves the queue for good (e.g.
  // validated by someone else, or superseded into a new version's id) so
  // localStorage doesn't grow unbounded.
  useEffect(() => {
    setDismissed((prev) => {
      const stillPresent = new Set(allCandidates.map((c) => c.cyId));
      const next = new Set([...prev].filter((id) => stillPresent.has(id)));
      if (next.size === prev.size) return prev;
      saveDismissed(next);
      return next;
    });
  }, [allCandidates]);

  const dismissedCount = useMemo(
    () => allCandidates.filter((c) => dismissed.has(c.cyId)).length,
    [allCandidates, dismissed]
  );
  const candidates = useMemo(
    () => (showDismissed ? allCandidates : allCandidates.filter((c) => !dismissed.has(c.cyId))),
    [allCandidates, dismissed, showDismissed]
  );

  useEffect(() => {
    if (!activeCyId && candidates.length > 0) setActiveCyId(candidates[0].cyId);
  }, [activeCyId, candidates]);

  const activeIndex = candidates.findIndex((c) => c.cyId === activeCyId);
  const active = activeIndex >= 0 ? candidates[activeIndex] : candidates[0] ?? null;

  function resetForm() {
    setPendingDecision(null);
    setNote("");
    setRewordValue("");
    setError(null);
  }

  function selectCandidate(cyId: string) {
    setActiveCyId(cyId);
    resetForm();
  }

  function startDecision(decision: ReviewDecision) {
    setPendingDecision(decision);
    setNote("");
    setError(null);
    if (decision === "reword" && active) {
      const field = primaryFieldFor(active.label);
      const props = parseJsonFields(active.label, active.props);
      setRewordValue(field ? String(props[field] ?? "") : "");
    }
  }

  async function confirmDecision(decision: ReviewDecision) {
    if (!active || submitting) return;
    setSubmitting(true);
    setError(null);
    const currentIndex = candidates.findIndex((c) => c.cyId === active.cyId);
    const nextCyId = candidates[currentIndex + 1]?.cyId ?? null;
    try {
      await submitReviewDecision({
        node: active,
        decision,
        by: by.trim() || "human",
        note: note.trim(),
        rewordValue: decision === "reword" ? rewordValue : undefined,
      });
      if (NON_VALIDATING_DECISIONS.has(decision)) {
        setDismissed((prev) => {
          const next = new Set(prev).add(active.cyId);
          saveDismissed(next);
          return next;
        });
      }
      await onMutated();
      setActiveCyId(nextCyId);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (candidates.length === 0) {
    return (
      <div className="review-queue review-queue-empty">
        <p>Nothing to review — every node is validated, disputed, or stale.</p>
        {dismissedCount > 0 && (
          <p>
            {dismissedCount} node{dismissedCount === 1 ? "" : "s"} reviewed but not validated (Bug /
            Ambiguous / Obsolete / Insufficient) {dismissedCount === 1 ? "is" : "are"} hidden.{" "}
            <button onClick={() => setShowDismissed(true)}>Show them</button>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="review-queue">
      <div className="review-list">
        <div className="review-list-header">
          <h2>Needs review ({candidates.length})</h2>
          {dismissedCount > 0 && (
            <button className="dismissed-toggle" onClick={() => setShowDismissed((v) => !v)}>
              {showDismissed ? "Hide" : "Show"} {dismissedCount} dismissed
            </button>
          )}
          <label className="reviewer-input">
            Reviewer
            <input value={by} onChange={(e) => setBy(e.target.value)} placeholder="human" />
          </label>
        </div>
        <ul>
          {candidates.map((c) => (
            <li
              key={c.cyId}
              className={[
                "review-item",
                c.cyId === active?.cyId ? "active" : "",
                dismissed.has(c.cyId) ? "dismissed" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => selectCandidate(c.cyId)}
            >
              <span className="swatch" style={{ background: LABEL_COLORS[c.label] }} />
              <span className="review-item-code">{codes.get(c.cyId) ?? c.label}</span>
              <span className="review-item-title">{titleFor(c.label, c.props)}</span>
            </li>
          ))}
        </ul>
      </div>

      {active && (
        <>
          <div className="review-detail">
            <DetailPanel node={active} nodes={nodes} edges={edges} />
          </div>

          <div className="review-actions">
            <h3>Decision</h3>
            <div className="decision-buttons">
              {DECISIONS.map((d) => {
                const disabled = d.value === "reword" && !primaryFieldFor(active.label);
                return (
                  <button
                    key={d.value}
                    className={pendingDecision === d.value ? "active" : ""}
                    disabled={disabled || submitting}
                    title={disabled ? `${active.label} has no authored text field to reword` : undefined}
                    onClick={() => (d.needsNote ? startDecision(d.value) : confirmDecision(d.value))}
                  >
                    {d.label}
                  </button>
                );
              })}
            </div>

            {pendingDecision && (
              <div className="decision-form">
                {pendingDecision === "reword" && (
                  <>
                    <label>New text</label>
                    <textarea
                      className="reword-textarea"
                      value={rewordValue}
                      onChange={(e) => setRewordValue(e.target.value)}
                      rows={5}
                    />
                  </>
                )}
                <label>
                  {pendingDecision === "bug"
                    ? "What's wrong (opens an Issue)"
                    : pendingDecision === "ambiguous"
                      ? "What needs clarifying (opens a Clarification)"
                      : "Note (optional)"}
                </label>
                <textarea
                  className="note-textarea"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                />
                {error && <p className="decision-error">{error}</p>}
                <div className="decision-form-buttons">
                  <button onClick={resetForm} disabled={submitting}>
                    Cancel
                  </button>
                  <button
                    className="primary"
                    disabled={
                      submitting ||
                      (DECISIONS.find((d) => d.value === pendingDecision)?.noteRequired && !note.trim())
                    }
                    onClick={() => confirmDecision(pendingDecision)}
                  >
                    {submitting ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
