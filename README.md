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
                        # (or OPENAI_API_KEY + REQGRAPH_PROVIDER=openai to use OpenAI instead — see .env.example)

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
- `llm-openai` (`openai`) — lets LLM roles run on OpenAI instead of (or alongside)
  Anthropic. Each role picks its provider independently via `REQGRAPH_PROVIDER_<ROLE>`,
  or move every role at once with `REQGRAPH_PROVIDER=openai`; per-role `REQGRAPH_MODEL_<ROLE>`
  still wins over either. See `.env.example` for the full list of role names.

Both degrade gracefully when not installed — the base install works exactly as before.

## One Neo4j instance per project

`docker-compose.yml` in this repo is ReqGraph's **own** dev/test instance — used by this repo's
test suite, which wipes it between runs (`tests/conftest.py`'s `neo4j_session` fixture). Never
point a real bootstrapped/greenfield project at it, and never share one Neo4j instance across two
projects: Neo4j Community Edition has no isolated per-project database, so "sharing" means every
project's data lives in the same store, at the mercy of any blanket query run against it (this
already happened once — a test run destroyed a real project's 827-node graph).

For every project, set up its own instance from `docs/templates/`:

```bash
cd /path/to/your/project
cp /path/to/reqgraph/docs/templates/docker-compose.neo4j.yml docker-compose.neo4j.yml
cp /path/to/reqgraph/docs/templates/.env.neo4j.example .env.neo4j   # edit only on port clashes
docker compose -f docker-compose.neo4j.yml --env-file .env.neo4j up -d
```

Then point the project's own `.env` (read by `graph-cli` — see below) and, if used,
`viewer/.env.local` at that instance's bolt port instead of ReqGraph's default 7687:

```bash
NEO4J_URI=bolt://localhost:7688   # NEO4J_BOLT_PORT from .env.neo4j
NEO4J_PASSWORD=reqgraph-dev       # NEO4J_PASSWORD from .env.neo4j
```

`graph-cli` reads a project's own `.env` when run from inside that project's directory (it loads
ReqGraph's `.env` as base defaults, then a `.env` in the current working directory on top, so the
project's settings win) — so once the above is in place, just `cd` into the project before running
any `graph-cli` command.

## Visualization

The Neo4j Browser (http://localhost:7474) is fine for ad-hoc Cypher, but for a project-status
view use [NeoDash](https://neo4j.com/labs/neodash/), bundled in `docker-compose.yml`:

```bash
docker compose up -d neo4j neodash
# open http://localhost:5005, connect with bolt://localhost:7687 / neo4j / <NEO4J_PASSWORD>,
# then Import -> docs/neodash-dashboard.json
```

The starter dashboard has three pages: the Requirement→Contract→Example/Task/CodeUnit/Test
traceability graph, a status overview (`knowledge_status`/`verification_status` distributions,
stale and `needs_revalidation` artifacts), and open Issues/blocking Clarifications/open
`CONTRADICTS` edges. It's a plain NeoDash export — edit reports/queries/layout freely in the UI
and re-export over the same file to keep it versioned.

For a purpose-built explorer (filter by node type, click a node for a formatted read-only
detail panel, highlight everything not `validated`) see `viewer/` — a small standalone
React + Cytoscape.js app that talks to Neo4j directly from the browser (`neo4j-driver`, same
approach as NeoDash/Neo4j Browser, no backend):

```bash
docker compose up -d neo4j
cd viewer
npm install
cp .env.example .env.local   # adjust if your NEO4J_PASSWORD differs from the compose default
npm run dev                  # http://localhost:5173
```

The viewer has four tabs: **Graph** (the explorer above), **Requirements** (all `Requirement.text`
read as one document — click one to focus the graph on its Contract/Example/Task/CodeUnit/
ConfigUnit/Test chain), **Review** (walk every node still `observed`/`inferred`/`generated` and
mark it `correct`/`reword`/`bug`/`ambiguous`/`obsolete`/`insufficient` — the same outcomes as
`bootstrap-review`, from the browser), and **Bootstrap**.

**Bootstrap** is the one tab that needs more than Neo4j: running `bootstrap-scan`/`bootstrap-observe`/
`bootstrap-infer` means reading the project's real files and, for infer, calling the Anthropic API —
neither is possible from the browser. It talks to a small local API server instead:

```bash
pip install -e ".[dev,api]"   # once, adds fastapi/uvicorn
graph-cli serve               # from the target project's own directory — see below
```

Like Neo4j (see next section), this server is **per project** — it serves whichever project its own
cwd/`.env` point at, the same as running `graph-cli` by hand. Run one `graph-cli serve` per project
you're actively bootstrapping, pointed at that project's own Neo4j. The Bootstrap tab then lets you
enter the repo path and run Scan → Observe → Infer in order, with output streamed live as it
happens, before jumping straight to Review.

## Tests

```bash
docker compose up -d neo4j
pytest                       # unit + integration (skips integration tests if Neo4j is unreachable)
pytest tests/unit            # no external services required
pytest -m integration        # requires the live Neo4j above
```

Tests never call the real Anthropic or OpenAI APIs — LLM-backed commands are tested against a
fake client (`tests/conftest.py`'s `fake_anthropic`/`fake_openai` fixtures). The `embeddings`/`js` extras are exercised for
real when installed (`fastembed` downloads its model from Hugging Face Hub on first use — needs
network once) rather than faked, since both run fully offline/local once available.
