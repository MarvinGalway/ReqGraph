# ReqGraph

Semantic traceability system for building and maintaining a verifiable relationship between
intention, behavioral specification, work, implementation, and observed behavior of a software
project. See `specifica-architetturale-v0.2.md` for the full design.

`graph-cli` implements both spec modes end to end — Greenfield (§6, G0–G4) and Existing Project
Bootstrap (§7, B0–B5) — plus local/offline embeddings-backed candidate discovery, Python and
JavaScript/TypeScript extraction, and a documented contract (`docs/AGENT_INTEGRATION.md`) for
driving the loop from an external coding agent. Codegen itself stays external by design — see
that doc for why, and `docs/AGENT_INTEGRATION.md` for the exact command sequence.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"                    # base install
pip install -e ".[dev,embeddings,js]"      # + local embeddings, + JS/TS extraction (both optional)

cp .env.example .env   # fill in ANTHROPIC_API_KEY for LLM-backed commands

docker compose up -d neo4j
graph-cli init --project "My Project" --mode greenfield --test-command "pytest -q"
```

`graph-cli --help` lists all commands, grouped as in spec §13: greenfield (`ingest-requirements`,
`run-critic`, `formalize`, `validate`, `derive-tasks`, `context`, `run-task`, `complete`,
`close-phase`), legacy bootstrap (`bootstrap-scan`, `bootstrap-observe`, `bootstrap-infer`,
`bootstrap-review`), and maintenance (`detect-changes`, `impact`, `revalidate`, `open-issue`,
`triage-issue`, `authorize-issue`, `invalidate`, `consistency-check`). `status` is at the top
level. `context`/`status` support `--json` for machine consumption — see
`docs/AGENT_INTEGRATION.md`.

### Optional extras

- `embeddings` (`fastembed`) — local, offline, no API key. Once installed, every Requirement/
  Contract/Example/ObservedBehavior/Issue gets a real embedding on creation, and `impact`/
  `triage-issue` gain vector-similarity candidate discovery on top of deterministic traversal.
  Requires `init --with-vector` to actually create the Neo4j vector indexes.
- `js` (`tree-sitter` + JS/TS grammars) — extends `bootstrap-scan`/`detect-changes` to
  JavaScript/TypeScript alongside Python, same symbol/call-graph granularity.

Both degrade gracefully when not installed — the base install works exactly as before.

## Tests

```bash
docker compose up -d neo4j
pytest                       # unit + integration (skips integration tests if Neo4j is unreachable)
pytest tests/unit            # no external services required
pytest -m integration        # requires the live Neo4j above
```

Tests never call the real Anthropic API — LLM-backed commands are tested against a fake client
(`tests/conftest.py`'s `fake_anthropic` fixture). The `embeddings`/`js` extras are exercised for
real when installed (`fastembed` downloads its model from Hugging Face Hub on first use — needs
network once) rather than faked, since both run fully offline/local once available.
