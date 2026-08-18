import neo4j, { type Driver, type Integer } from "neo4j-driver";
import type { GraphData, GraphEdge, GraphNode, NodeLabel } from "../types";

let driver: Driver | null = null;

function getDriver(): Driver {
  if (!driver) {
    driver = neo4j.driver(
      import.meta.env.VITE_NEO4J_URI,
      neo4j.auth.basic(import.meta.env.VITE_NEO4J_USER, import.meta.env.VITE_NEO4J_PASSWORD)
    );
  }
  return driver;
}

function cyIdFor(label: string, id: string): string {
  return `${label}:${id}`;
}

// The Neo4j JS driver returns Integer/temporal wrapper objects for
// non-JS-native types (created_at/updated_at are Neo4j DateTime). Convert to
// plain JS values so the rest of the app can treat props as plain JSON.
// `embedding` is dropped — it's a 384-float vector with no display value.
function normalizeProps(raw: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (key === "embedding") continue;
    out[key] = normalizeValue(value);
  }
  return out;
}

function normalizeValue(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (neo4j.isInt(value)) return (value as Integer).toNumber();
  if (
    neo4j.isDate(value) ||
    neo4j.isDateTime(value) ||
    neo4j.isLocalDateTime(value) ||
    neo4j.isLocalTime(value) ||
    neo4j.isTime(value) ||
    neo4j.isDuration(value)
  ) {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(normalizeValue);
  return value;
}

export async function verifyConnection(): Promise<void> {
  await getDriver().verifyConnectivity();
}

export async function fetchGraph(): Promise<GraphData> {
  const session = getDriver().session({ database: import.meta.env.VITE_NEO4J_DATABASE });
  try {
    const nodeResult = await session.run(
      "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
    );
    const nodes: GraphNode[] = nodeResult.records.map((record) => {
      const labels = record.get("labels") as string[];
      const props = normalizeProps(record.get("props") as Record<string, unknown>);
      const label = labels[0] as NodeLabel;
      const id = String(props.id);
      return { cyId: cyIdFor(label, id), label, id, props };
    });

    const edgeResult = await session.run(
      `MATCH (a)-[r]->(b)
       RETURN labels(a)[0] AS fromLabel, a.id AS fromId,
              labels(b)[0] AS toLabel, b.id AS toId,
              type(r) AS relType, properties(r) AS relProps`
    );
    const edges: GraphEdge[] = edgeResult.records.map((record, index) => {
      const fromLabel = record.get("fromLabel") as string;
      const fromId = record.get("fromId") as string;
      const toLabel = record.get("toLabel") as string;
      const toId = record.get("toId") as string;
      const relType = record.get("relType") as string;
      const relProps = normalizeProps(record.get("relProps") as Record<string, unknown>);
      return {
        cyId: `edge:${index}:${relType}`,
        relType,
        sourceCyId: cyIdFor(fromLabel, fromId),
        targetCyId: cyIdFor(toLabel, toId),
        props: relProps,
      };
    });

    return { nodes, edges };
  } finally {
    await session.close();
  }
}

// --- Review decisions -------------------------------------------------
// Mirrors reqgraph/cli/commands/bootstrap_review.py's write logic exactly
// (same outcomes, same Issue/Clarification defaults) so a node validated
// here is indistinguishable from one validated via `graph-cli
// bootstrap-review`. Runs straight from the browser like the rest of this
// file — same trust model as Neo4j Browser/NeoDash.

export type ReviewDecision = "correct" | "reword" | "bug" | "ambiguous" | "obsolete" | "insufficient";

// The one field per label that carries its authored content, editable via
// "reword". Labels with no entry (CodeUnit, ConfigUnit, Test, ObservedBehavior,
// ...) are derived from source, not authored — reword doesn't apply to them.
const PRIMARY_FIELD: Partial<Record<NodeLabel, string>> = {
  Requirement: "text",
  Clarification: "question",
  Assumption: "text",
  Contract: "summary",
  Example: "summary",
  Task: "title",
  Issue: "title",
};

export function primaryFieldFor(label: NodeLabel): string | null {
  return PRIMARY_FIELD[label] ?? null;
}

export interface SubmitReviewInput {
  node: GraphNode;
  decision: ReviewDecision;
  by: string;
  note: string;
  rewordValue?: string;
}

export async function submitReviewDecision(input: SubmitReviewInput): Promise<void> {
  const { node, decision, by, note } = input;
  const session = getDriver().session({ database: import.meta.env.VITE_NEO4J_DATABASE });
  const isRequirement = node.label === "Requirement";
  try {
    if (decision === "correct" || decision === "reword") {
      const field = primaryFieldFor(node.label);
      const setClauses = ["n.knowledge_status = 'validated'", "n.updated_at = datetime()"];
      const params: Record<string, unknown> = { id: node.id };
      if (isRequirement) setClauses.push("n.trust = 'human-validated'");
      if (decision === "reword" && field) {
        setClauses.push(`n.${field} = $value`);
        params.value = input.rewordValue ?? "";
      }
      await session.run(`MATCH (n:${node.label} {id: $id}) SET ${setClauses.join(", ")}`, params);
      if (decision === "reword" && note.trim()) {
        await session.run("MATCH (n {id: $id}) SET n.source_refs = n.source_refs + $note", {
          id: node.id,
          note: `reword-note:${note.trim()}`,
        });
      }
      return;
    }

    if (decision === "bug") {
      const issueId = crypto.randomUUID();
      await session.executeWrite(async (tx) => {
        await tx.run(
          `CREATE (:Issue {
            id: $id, knowledge_status: 'generated', verification_status: 'not_applicable',
            created_by: $by, created_at: datetime(), updated_at: datetime(), source_refs: [],
            title: $title, description: $description, reported_by: $by,
            workflow_status: 'open', classification: 'suspected_bug', severity: 'unknown', evidence: []
          })`,
          {
            id: issueId,
            by,
            title: `Possible bug surfaced during review of ${node.label} ${node.id}`,
            description: note || "(no note provided)",
          }
        );
        if (node.label === "CodeUnit" || node.label === "ConfigUnit") {
          await tx.run(
            "MATCH (i:Issue {id: $issueId}), (t {id: $targetId}) CREATE (i)-[:AFFECTS]->(t)",
            { issueId, targetId: node.id }
          );
        }
      });
      return;
    }

    if (decision === "ambiguous") {
      const clarId = crypto.randomUUID();
      await session.executeWrite(async (tx) => {
        await tx.run(
          `CREATE (:Clarification {
            id: $id, knowledge_status: 'generated', verification_status: 'not_applicable',
            created_by: $by, created_at: datetime(), updated_at: datetime(), source_refs: [],
            question: $question, blocking: true
          })`,
          { id: clarId, by, question: note || `Is the inferred ${node.label} ${node.id} correct?` }
        );
        if (isRequirement) {
          await tx.run(
            "MATCH (c:Clarification {id: $clarId}), (t {id: $targetId}) CREATE (c)-[:CLARIFIES]->(t)",
            { clarId, targetId: node.id }
          );
        }
      });
      return;
    }

    // obsolete | insufficient
    await session.run("MATCH (n {id: $id}) SET n.source_refs = n.source_refs + $note, n.updated_at = datetime()", {
      id: node.id,
      note: `${decision}:${note || by}`,
    });
  } finally {
    await session.close();
  }
}

export async function closeDriver(): Promise<void> {
  if (driver) {
    await driver.close();
    driver = null;
  }
}
