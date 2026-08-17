# Driving graph-cli from an external agent

Spec §13 states it plainly: *"OpenCode non scrive direttamente su Neo4j: passa
attraverso graph-cli"* — OpenCode (or any other coding agent) never touches
the graph directly. It shells out to `graph-cli` and reads back structured
output. This document is that contract, made concrete enough for any agent —
OpenCode, Claude Code, a hand-rolled script — to drive the G3 loop end to end.

This is not a description of an OpenCode-specific plugin protocol (no such
thing is verified or assumed here). It is the minimum an agent needs to know
to script `graph-cli` correctly: which commands to call, in what order, what
their JSON output looks like, and how to tell success from failure.

## The loop, end to end

For one Task (`task-01-01` below is illustrative):

```
1.  graph-cli context task-01-01 --json
        -> read Contract/Requirement/Examples/scope. This is everything
           the agent needs to know what to build.

2.  [agent implements the change with its own tools — Read/Edit/Write, or
     equivalent — outside graph-cli entirely]

3.  graph-cli run-task task-01-01 --repo-path <repo> --verify-red \
        --record-test <path>:<symbol>
        -> confirms the new test actually fails before the fix lands.
           Exit code 1 means the test unexpectedly passed already —
           stop and re-check the test, don't proceed to step 4.

4.  [agent implements the fix]

5.  graph-cli run-task task-01-01 --repo-path <repo> \
        --record-codeunit <path>:<symbol> [--record-codeunit ... repeatable]
        -> records what was actually built. Idempotent: recording the same
           artifact twice does not create duplicate edges.

6.  graph-cli impact <codeunit-id> --repo-path <repo>
        -> required before `complete` will accept this task if any
           CodeUnit/ConfigUnit was recorded — run once per recorded artifact.

7.  graph-cli complete task-01-01 --repo-path <repo> --test-command "<cmd>"
        -> the real gate: artifacts recorded, impact checked, the actual
           test suite run, and a Reviewer LLM verdict on Contract/Requirement
           fidelity. Exit code 0 = done. Exit code 1 = one or more gates
           failed; stdout says which, in plain English. Fix and re-run —
           complete is fully idempotent on failure, no partial state.

8.  graph-cli status --json
        -> re-check overall project state (open issues, needs_revalidation,
           last regression result) before picking the next task.
```

Nothing here requires parsing Rich-formatted tables. Steps 1 and 8 are the
two commands with a `--json` mode; every other command's contract is its
**exit code** (0 = proceed, non-zero = stop and read stdout for why) — that's
enough to drive the loop without scraping human-readable output.

## `context <task-id> --json` shape

```json
{
  "task_id": "task-01-01",
  "task_title": "Implement cancel_order",
  "items": [
    {"category": "contracts_and_requirements", "text": "[VALIDATED] Contract <id>: pre=[...] post=[...] acceptance=[...]"},
    {"category": "validated_examples", "text": "[VALIDATED] Example <id>: input={...} -> expected={...} edge_case=true"},
    {"category": "implementation_and_dependency_interfaces", "text": "[OBSERVED] CodeUnit orders.py::orders.cancel_order"},
    {"category": "constraints_assumptions_issues", "text": "..."},
    {"category": "state_todo_decisions", "text": "Task file: status=in_progress tdd_step=verify-red decisions=[...]"}
  ]
}
```

`items` is a flat, budgeted list (see `models-config-v0.2.json`'s
`context_budget_quotas`) — each entry's `category` says which part of the
Task context it belongs to, and each `text` is already human/LLM-readable
prose, not something to parse further. Feed it straight into whatever prompt
the driving agent uses to decide what to build.

## `status --json` shape

```json
{
  "project": "Demo",
  "project_mode": "greenfield",
  "current_phase": "phase-01",
  "node_counts": {"Task": {"done": 3, "in_progress": 1}, "Issue": {"open": 1}, "...": "..."},
  "open_issues": 1,
  "open_contradictions": 0,
  "needs_revalidation": 0,
  "stale_nodes_count": 0,
  "last_regression": {"at": "2026-...", "result": "green"},
  "open_assumptions": [],
  "phases": [{"id": "phase-01", "status": "in_progress", "tasks_done": 3, "tasks_total": 4}]
}
```

On a missing project (`init` never run), this is `{"error": "..."}` with
exit code 1 rather than a stack trace — safe to `json.loads` unconditionally.

## Exit code convention

Every graph-cli command follows the same rule: **0 means the operation
succeeded (or, for gate commands like `complete`/`run-task --verify-red`,
that the gate passed); any non-zero code means stop and read stdout.**
Gate failures print a plain-English reason (`Cannot complete task-01-01,
Definition of Done not met: - impact not checked for ...`) — an agent
doesn't need special-case parsing per failure type, just needs to surface
that text back to whatever is deciding what to do next (a human, or another
LLM call).

## What this contract deliberately does not cover

- **Authentication/transport** — graph-cli is a local CLI talking to a local
  (or otherwise reachable) Neo4j via `NEO4J_URI`/`NEO4J_PASSWORD` env vars.
  There's no remote-invocation story here; an agent runs `graph-cli` as a
  subprocess in the same environment.
- **Concurrency** — nothing here handles two agents driving the same Task at
  once. Out of scope for this pass.
- **Codegen itself** — by design (see the implementation plan), graph-cli
  never writes code. Steps 2 and 4 above are entirely the driving agent's own
  responsibility, using whatever tools it already has.

## Reference implementation

`scripts/agent_driver_example.py` implements exactly the 8 steps above via
subprocess calls to `graph-cli`, against a real Neo4j instance. It is a
demonstration, not a production framework — read it alongside this document,
not instead of it.
