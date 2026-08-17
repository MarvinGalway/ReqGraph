# ReqGraph

Semantic traceability system for building and maintaining a verifiable relationship between
intention, behavioral specification, work, implementation, and observed behavior of a software
project. See `specifica-architetturale-v0.2.md` for the full design.

This repo currently implements `graph-cli` — the command-line surface and Neo4j-backed
persistence foundation described in the spec (§13). The full LLM-orchestrated TDD loop
(Codegen/Reviewer writing code autonomously) and OpenCode integration are not implemented yet.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # fill in ANTHROPIC_API_KEY for LLM-backed commands

docker compose up -d neo4j
graph-cli init --project "My Project" --mode greenfield
```

`graph-cli --help` lists all commands, grouped as in spec §13: greenfield (`ingest-requirements`,
`run-critic`, `formalize`, `validate`, `derive-tasks`, `context`, `run-task`, `complete`), legacy
bootstrap (`bootstrap-scan`, `bootstrap-observe`, `bootstrap-infer`, `bootstrap-review`), and
maintenance (`detect-changes`, `impact`, `revalidate`, `open-issue`, `triage-issue`,
`authorize-issue`, `invalidate`, `consistency-check`). `status` is at the top level.

## Tests

```bash
docker compose up -d neo4j
pytest                       # unit + integration (skips integration tests if Neo4j is unreachable)
pytest tests/unit            # no external services required
pytest -m integration        # requires the live Neo4j above
```

Tests never call the real Anthropic API — LLM-backed commands are tested against a fake client
(`tests/conftest.py`'s `fake_anthropic` fixture).
