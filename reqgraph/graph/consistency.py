"""Translates graph-schema-v0.2.json's `consistency_queries` (spec §14) into
runnable checks. 8 of the 10 are pure Cypher; checks 7 and 8 need
project-state files (phase/task scope, exit criteria) alongside the graph.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from neo4j import Session

from reqgraph.state import io as state_io
from reqgraph.state.paths import phase_todo_path, task_dir


@dataclass
class Violation:
    check_id: str
    description: str
    node_id: str
    detail: str = ""


@dataclass
class CypherCheck:
    check_id: str
    description: str
    query: str


CYPHER_CHECKS: list[CypherCheck] = [
    CypherCheck(
        "1",
        "validated Requirement without validated Contract",
        """
        MATCH (r:Requirement {knowledge_status: 'validated'})
        WHERE NOT EXISTS { MATCH (:Contract {knowledge_status: 'validated'})-[:FORMALIZES]->(r) }
        RETURN r.id AS id, r.text AS detail
        """,
    ),
    CypherCheck(
        "2",
        "validated Contract without minimum behavioral coverage (>=3 Examples, >=1 edge case)",
        """
        MATCH (c:Contract {knowledge_status: 'validated'})
        OPTIONAL MATCH (e:Example {knowledge_status: 'validated'})-[:WITNESSES]->(c)
        WITH c, count(e) AS n, sum(CASE WHEN e.edge_case THEN 1 ELSE 0 END) AS edge_n
        WHERE n < 3 OR edge_n < 1
        RETURN c.id AS id, ('examples=' + toString(n) + ' edge_cases=' + toString(coalesce(edge_n, 0))) AS detail
        """,
    ),
    CypherCheck(
        "3",
        "generated Test without GENERATED_FROM when produced from an Example",
        """
        MATCH (t:Test {knowledge_status: 'generated'})
        WHERE NOT t.created_by STARTS WITH 'static-analysis' AND NOT t.created_by STARTS WITH 'import:'
          AND NOT EXISTS { MATCH (t)-[:GENERATED_FROM]->(:Example) }
        RETURN t.id AS id, (t.path + '::' + coalesce(t.symbol, '')) AS detail
        """,
    ),
    CypherCheck(
        "4",
        "lifecycle-generated CodeUnit/ConfigUnit/Test without GENERATED_BY Task",
        """
        MATCH (n)
        WHERE (n:CodeUnit OR n:ConfigUnit OR n:Test) AND n.knowledge_status = 'generated'
          AND NOT n.created_by STARTS WITH 'static-analysis' AND NOT n.created_by STARTS WITH 'import:'
          AND NOT EXISTS { MATCH (n)-[:GENERATED_BY]->(:Task) }
        RETURN n.id AS id, labels(n)[0] AS detail
        """,
    ),
    CypherCheck(
        "5",
        "validated CodeUnit without IMPLEMENTS Contract (excluding unresolved legacy artifacts)",
        """
        MATCH (cu:CodeUnit {knowledge_status: 'validated'})
        WHERE NOT EXISTS { MATCH (cu)-[:IMPLEMENTS]->(:Contract) }
          AND cu.created_by <> 'static-analysis'
        RETURN cu.id AS id, (cu.path + '::' + cu.symbol) AS detail
        """,
    ),
    CypherCheck(
        "6",
        "confirmed_bug Issue closed without resolution/provenance",
        """
        MATCH (i:Issue {classification: 'confirmed_bug', workflow_status: 'closed'})
        WHERE i.resolution IS NULL AND NOT EXISTS { MATCH (:Task)-[:ADDRESSES]->(i) }
        RETURN i.id AS id, i.title AS detail
        """,
    ),
    CypherCheck(
        "9",
        "open CONTRADICTS edge",
        """
        MATCH (a)-[r:CONTRADICTS {status: 'open'}]->(b)
        RETURN a.id AS id, (labels(a)[0] + ' <-> ' + labels(b)[0] + ' (' + b.id + ')') AS detail
        """,
    ),
    CypherCheck(
        "10",
        "legacy inferred Requirement/Contract validated without human validation provenance",
        """
        MATCH (r:Requirement {knowledge_status: 'validated', origin_mode: 'legacy-bootstrap'})
        WHERE coalesce(r.trust, '') <> 'human-validated'
        RETURN r.id AS id, 'Requirement' AS detail
        UNION
        MATCH (c:Contract {knowledge_status: 'validated', origin_mode: 'legacy-bootstrap'})-[f:FORMALIZES]->(:Requirement)
        WHERE f.reviewed_by IS NULL
        RETURN c.id AS id, 'Contract' AS detail
        """,
    ),
]


def _run_cypher_check(sess: Session, check: CypherCheck) -> list[Violation]:
    result = sess.run(check.query)
    return [
        Violation(check.check_id, check.description, r["id"], r.get("detail") or "")
        for r in result
    ]


def _check_7_out_of_scope(sess: Session, state_root: Path) -> list[Violation]:
    """Task changed artifact outside declared scope without Issue/decision.

    scope.target_codeunits/target_configunits are exact-id checks (pure
    Cypher); scope.allowed_paths are globs, matched in Python after fetch.
    """
    result = sess.run(
        """
        MATCH (a)-[:GENERATED_BY]->(t:Task)
        WHERE a:CodeUnit OR a:ConfigUnit
        RETURN a.id AS artifact_id, a.path AS path, t.id AS task_id, t.external_id AS task_external_id,
               t.scope AS scope
        """
    )
    violations: list[Violation] = []
    for record in result:
        import json

        scope = json.loads(record["scope"]) if record["scope"] else {}
        target_ids = set(scope.get("target_codeunits", [])) | set(scope.get("target_configunits", []))
        allowed_paths = scope.get("allowed_paths", [])
        artifact_id = record["artifact_id"]
        path = record["path"] or ""
        in_scope = artifact_id in target_ids or any(
            fnmatch.fnmatch(path, pattern) for pattern in allowed_paths
        )
        if in_scope:
            continue
        task_external_id = record["task_external_id"]
        has_issue = False
        if task_external_id:
            task_file = task_dir(state_root, _phase_of(task_external_id)) / f"{task_external_id}.json"
            if task_file.exists():
                data = state_io.read_json(task_file)
                findings = data.get("out_of_scope_findings", [])
                has_issue = any(f.get("summary") for f in findings)
        if not has_issue:
            violations.append(
                Violation("7", "Task changed artifact outside declared scope", artifact_id, path)
            )
    return violations


def _phase_of(task_external_id: str) -> str:
    # "task-01-01" -> "phase-01"
    parts = task_external_id.split("-")
    return f"phase-{parts[1]}" if len(parts) >= 2 else "phase-01"


def _check_8_unresolved_revalidation(sess: Session, state_root: Path, phase_id: str | None) -> list[Violation]:
    """Unresolved needs_revalidation at phase close.

    Phase boundaries live only in project-state, not the graph: this reads
    the target phase's task files, resolves their generated artifact ids,
    and checks verification_status on that specific node set.
    """
    if phase_id is None:
        return []
    todo_path = phase_todo_path(state_root, phase_id)
    if not todo_path.exists():
        return []
    phase_data = state_io.read_json(todo_path)
    artifact_ids: set[str] = set()
    for task in phase_data.get("tasks", []):
        task_file = task_dir(state_root, phase_id) / f"{task['id']}.json"
        if not task_file.exists():
            continue
        task_data = state_io.read_json(task_file)
        generated = task_data.get("artifacts_generated", {})
        artifact_ids |= set(generated.get("codeunits", []))
        artifact_ids |= set(generated.get("configunits", []))
        artifact_ids |= set(generated.get("tests", []))
    if not artifact_ids:
        return []
    result = sess.run(
        "MATCH (n) WHERE n.id IN $ids AND n.verification_status = 'needs_revalidation' "
        "RETURN n.id AS id, labels(n)[0] AS label",
        ids=list(artifact_ids),
    )
    return [
        Violation("8", "Unresolved needs_revalidation at phase close", r["id"], r["label"])
        for r in result
    ]


def run_consistency_checks(
    sess: Session, state_root: Path, phase_id: str | None = None
) -> list[Violation]:
    violations: list[Violation] = []
    for check in CYPHER_CHECKS:
        violations.extend(_run_cypher_check(sess, check))
    violations.extend(_check_7_out_of_scope(sess, state_root))
    violations.extend(_check_8_unresolved_revalidation(sess, state_root, phase_id))
    violations.sort(key=lambda v: v.check_id)
    return violations
