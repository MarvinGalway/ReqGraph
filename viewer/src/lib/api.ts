// Talks to the local API server (reqgraph/api/server.py, `graph-cli serve`)
// — the one thing the browser can't do itself: read the project's real
// filesystem and call tree-sitter/the Anthropic API to run bootstrap-scan/
// observe/infer. Everything else in this app talks to Neo4j directly.

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8321";

export interface BootstrapState {
  mode: string;
  stage: string;
  repository_revision: string;
  counts: Record<string, number>;
  review_queue: string[];
}

export async function fetchApiHealth(): Promise<{ status: string; project_root: string }> {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new Error(`API health check failed: ${res.status}`);
  return res.json();
}

export async function fetchBootstrapState(): Promise<BootstrapState> {
  const res = await fetch(`${API_URL}/bootstrap/state`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export type BootstrapStep = "scan" | "observe" | "infer";

export interface RunStepParams {
  repoPath?: string;
  includeLockfiles?: boolean;
  legacy?: boolean;
  maxGroups?: number;
}

export interface RunStepCallbacks {
  onLine: (line: string) => void;
  onDone: () => void;
  onFailed: (message: string) => void;
  onConnectionLost: () => void;
}

// Returns a function that cancels the stream (call on unmount / when
// starting a new run) — EventSource auto-reconnects by default once the
// server closes the response after `done`/`failed`, which would silently
// re-run the whole step, so callers MUST close it once onDone/onFailed
// fires (this module does that itself; exposed mainly for cleanup-on-unmount).
export function runBootstrapStep(
  step: BootstrapStep,
  params: RunStepParams,
  callbacks: RunStepCallbacks
): () => void {
  const query = new URLSearchParams();
  if (step === "scan" || step === "observe") {
    query.set("repo_path", params.repoPath?.trim() || ".");
  }
  if (step === "scan" && params.includeLockfiles) query.set("include_lockfiles", "true");
  if (step === "observe" && params.legacy) query.set("legacy", "true");
  if (step === "infer" && params.maxGroups) query.set("max_groups", String(params.maxGroups));

  const source = new EventSource(`${API_URL}/bootstrap/${step}/stream?${query.toString()}`);
  let settled = false;

  source.onmessage = (e) => callbacks.onLine(e.data);

  source.addEventListener("done", () => {
    settled = true;
    source.close();
    callbacks.onDone();
  });

  source.addEventListener("failed", (e) => {
    settled = true;
    source.close();
    callbacks.onFailed((e as MessageEvent).data);
  });

  // EventSource's own connection-drop event (server not running, network
  // error, or a genuinely unhandled server crash mid-stream) — distinct
  // from the "failed" business-logic event above.
  source.onerror = () => {
    if (settled) return;
    settled = true;
    source.close();
    callbacks.onConnectionLost();
  };

  return () => {
    settled = true;
    source.close();
  };
}
