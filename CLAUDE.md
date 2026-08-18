# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

ReqGraph is currently in the **specification / design phase**. There is no application code, package manifest, build system, or test suite in this repository yet — only versioned architecture documents and JSON schema/config artifacts. If asked to "build," "run," or "test" something, check first whether an implementation scaffold exists yet; as of now it does not. Most work in this repo is editing/extending the design documents themselves, not writing application code.

## What ReqGraph is

ReqGraph is a semantic traceability system for building and maintaining a verifiable chain between human intent and observed software behavior:

```
Human intent → Requirement → Contract → Example → Task → Test/CodeUnit → observed behavior/Issue
```

Target knowledge graph: Neo4j. Execution/orchestration target: OpenCode, kept swappable behind a planned `graph-cli` layer — OpenCode is expected to never write directly to Neo4j.

A project can enter ReqGraph two ways, which converge into the same graph and lifecycle after an initial phase:
- **Greenfield Mode** — start from requirements, drive toward implementation (phases G0–G4 in the spec).
- **Existing Project Bootstrap Mode** — start from an existing repo/tests/evidence, reconstruct candidate specs, then require human validation (phases B0–B5 in the spec).

## Key documents (source of truth)

- `specifica-architetturale-v0.2.md` — the canonical architectural spec (Italian). Read this before making any conceptual change to the model; the summaries below are not a substitute for it.
- `CHANGELOG-v0.2.md` — what changed from v0.1 to v0.2 (e.g. addition of `Issue`/`ObservedBehavior`/`ConfigUnit`, bootstrap mode, `needs_revalidation`).
- `graph-schema-v0.2.json` — logical Neo4j schema: node types (`Requirement`, `Clarification`, `Assumption`, `Contract`, `Example`, `Task`, `CodeUnit`, `ConfigUnit`, `Test`, `Issue`, `ObservedBehavior`), their fields, and relationships.
- `models-config-v0.2.json` — LLM role configuration (`critic`, `formalizer`, `planner`, `codegen`, `reviewer`, `librarian`, `reverse_analyst`, `impact_analyst`, `issue_triage`): which pipeline each belongs to, and model/temperature placeholders.
- `todo-templates-v0.2.json` — operational project-state file templates (`/.project-state/...`) used as agent/session working memory alongside the graph (distinct from the graph itself, which is the source of relational truth).

These four files describe one model from different angles and must stay consistent with each other: a new node type or relationship added to the spec should be reflected in `graph-schema-v0.2.json`, a new LLM role in `models-config-v0.2.json`, and new operational state in `todo-templates-v0.2.json`.

## Core model to keep in mind when editing the spec

- `Contract` is the bridge between intent and implementation: `Contract -FORMALIZES-> Requirement`, `Example -WITNESSES-> Contract`, `Task -DERIVES_FROM-> Contract`, `CodeUnit -IMPLEMENTS-> Contract`. No `Task` is ever derived directly from prose.
- Two independent status axes exist per artifact: `knowledge_status` (`observed | inferred | generated | validated | disputed | stale`) and `verification_status` (`not_applicable | unknown | needs_revalidation | verified | failed`). A code change does not automatically invalidate the `Contract` it implements — it marks the technical artifact `needs_revalidation`, distinct from a semantic `stale`.
- Invalidation granularity is symbolic/key-level, not file-level: changing one function or one config key must not cascade to every `CodeUnit`/`ConfigUnit` that happens to share the same file (this is the explicit design fix for "changing `settings.py` invalidates everything").
- `Issue` discovery is not authorization to fix: an agent that finds an out-of-scope bug during a `Task` opens an `Issue` and continues the current `Task` — it does not modify the unrelated code. Only a human-authorized follow-up `Task` (`Task -ADDRESSES-> Issue`) may resolve it.
- `Reviewer` and `Codegen` must be different models/passes (see `models-config-v0.2.json`), so a generator never reviews its own output.

## Non-negotiable rules (spec §16)

1. No modification outside an authorized Task, except mechanical operations the Task explicitly declares.
2. No legacy/observed behavior becomes validated intent without human review.
3. No regenerated Contract silently replaces the Requirement it formalizes.
4. No file-level modification automatically invalidates every CodeUnit in that file.
5. No global config change automatically invalidates the whole project.
6. Every generated artifact keeps provenance back to its Task/evidence.
7. Every historical branch of the graph stays queryable (nodes are versioned via `SUPERSEDES`, not overwritten).
8. Semantic changes produce `stale`; technical changes produce `needs_revalidation` first.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ReqGraph** (2049 symbols, 3474 relationships, 74 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/ReqGraph/context` | Codebase overview, check index freshness |
| `gitnexus://repo/ReqGraph/clusters` | All functional areas |
| `gitnexus://repo/ReqGraph/processes` | All execution flows |
| `gitnexus://repo/ReqGraph/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
