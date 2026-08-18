import { useEffect, useRef, useState } from "react";
import {
  fetchApiHealth,
  fetchBootstrapState,
  runBootstrapStep,
  type BootstrapState,
  type BootstrapStep,
} from "../lib/api";

interface Props {
  onMutated: () => Promise<void>;
  onOpenReview: () => void;
}

const REPO_PATH_KEY = "reqgraph-viewer-repo-path";

const STEP_LABEL: Record<BootstrapStep, string> = {
  scan: "Run Scan",
  observe: "Run Observe",
  infer: "Run Infer",
};

const STEP_RUNNING_LABEL: Record<BootstrapStep, string> = {
  scan: "Scanning…",
  observe: "Observing…",
  infer: "Inferring…",
};

export function BootstrapPanel({ onMutated, onOpenReview }: Props) {
  const [repoPath, setRepoPath] = useState(() => localStorage.getItem(REPO_PATH_KEY) || "");
  const [includeLockfiles, setIncludeLockfiles] = useState(false);
  const [legacy, setLegacy] = useState(false);
  const [maxGroups, setMaxGroups] = useState(10);
  const [running, setRunning] = useState<BootstrapStep | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [bootstrapState, setBootstrapState] = useState<BootstrapState | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem(REPO_PATH_KEY, repoPath);
  }, [repoPath]);

  function refreshState() {
    fetchBootstrapState()
      .then((s) => {
        setBootstrapState(s);
        setApiError(null);
      })
      .catch((e: unknown) => setApiError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    fetchApiHealth()
      .then((health) => {
        // repo_path is never stored in the graph (CodeUnit.path is
        // repo-relative) — it's only "where on this disk, right now, to
        // find a checkout". The server already knows that (it's per-project,
        // started from that project's own directory), so default to it
        // instead of making the user retype/paste it.
        if (!repoPath) setRepoPath(health.project_root);
      })
      .catch((e: unknown) => setApiError(e instanceof Error ? e.message : String(e)));
    refreshState();
    return () => cancelRef.current?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

  function runStep(step: BootstrapStep) {
    if (running) return;
    setRunning(step);
    setLines([]);
    setApiError(null);
    cancelRef.current = runBootstrapStep(
      step,
      { repoPath, includeLockfiles, legacy, maxGroups },
      {
        onLine: (line) => setLines((prev) => [...prev, line]),
        onDone: () => {
          setRunning(null);
          refreshState();
          void onMutated();
        },
        onFailed: (message) => {
          setRunning(null);
          setLines((prev) => [...prev, `✗ ${message}`]);
        },
        onConnectionLost: () => {
          setRunning(null);
          setApiError("Lost connection to the API server — is `graph-cli serve` still running?");
        },
      }
    );
  }

  const counts = bootstrapState?.counts;

  return (
    <div className="bootstrap-panel">
      <div className="bootstrap-controls">
        <h2>Bootstrap a project's graph</h2>
        <p className="bootstrap-hint">
          Runs against the project's real filesystem via the local API server (<code>graph-cli
          serve</code>) — everything else in this app talks to Neo4j directly, but reading source
          files and calling the Anthropic API can't happen from the browser.
        </p>

        {apiError && (
          <div className="banner banner-error">
            {apiError} — start it with <code>graph-cli serve</code> from the project's own
            directory (see README).
          </div>
        )}

        {counts && (
          <dl className="bootstrap-state-summary">
            <div>
              <dt>Stage</dt>
              <dd>{bootstrapState.stage || "—"}</dd>
            </div>
            <div>
              <dt>CodeUnit</dt>
              <dd>{counts.codeunits ?? 0}</dd>
            </div>
            <div>
              <dt>ConfigUnit</dt>
              <dd>{counts.configunits ?? 0}</dd>
            </div>
            <div>
              <dt>Test</dt>
              <dd>{counts.tests ?? 0}</dd>
            </div>
            <div>
              <dt>ObservedBehavior</dt>
              <dd>{counts.observed_behaviors ?? 0}</dd>
            </div>
            <div>
              <dt>Candidate Req/Contract</dt>
              <dd>
                {counts.candidate_requirements ?? 0}/{counts.candidate_contracts ?? 0}
              </dd>
            </div>
          </dl>
        )}

        <label className="bootstrap-repo-path">
          Repo path (defaults to the API server's own project — override only to scan a subdirectory)
          <input
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/project"
            disabled={!!running}
          />
        </label>

        <div className="bootstrap-steps">
          <div className="bootstrap-step">
            <button disabled={!!running} onClick={() => runStep("scan")}>
              {running === "scan" ? STEP_RUNNING_LABEL.scan : `1. ${STEP_LABEL.scan}`}
            </button>
            <label className="inline-checkbox">
              <input
                type="checkbox"
                checked={includeLockfiles}
                onChange={(e) => setIncludeLockfiles(e.target.checked)}
                disabled={!!running}
              />
              include lockfiles
            </label>
          </div>

          <div className="bootstrap-step">
            <button disabled={!!running} onClick={() => runStep("observe")}>
              {running === "observe" ? STEP_RUNNING_LABEL.observe : `2. ${STEP_LABEL.observe}`}
            </button>
            <label className="inline-checkbox">
              <input
                type="checkbox"
                checked={legacy}
                onChange={(e) => setLegacy(e.target.checked)}
                disabled={!!running}
              />
              --legacy
            </label>
          </div>

          <div className="bootstrap-step">
            <button disabled={!!running} onClick={() => runStep("infer")}>
              {running === "infer" ? STEP_RUNNING_LABEL.infer : `3. ${STEP_LABEL.infer}`}
            </button>
            <label className="inline-number">
              max groups
              <input
                type="number"
                min={1}
                value={maxGroups}
                onChange={(e) => setMaxGroups(Number(e.target.value) || 10)}
                disabled={!!running}
              />
            </label>
          </div>
        </div>

        <p className="bootstrap-hint">
          Requires <code>ANTHROPIC_API_KEY</code> set for the API server (Infer only — Scan/Observe
          are deterministic, no LLM call).
        </p>

        <button className="bootstrap-review-link" onClick={onOpenReview}>
          Go to Review →
        </button>
      </div>

      <div className="bootstrap-log" ref={logRef}>
        {lines.length === 0 ? (
          <p className="empty">No output yet — run a step above.</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="bootstrap-log-line">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
