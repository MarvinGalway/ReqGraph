from __future__ import annotations

import typer

from reqgraph.cli.common import console, graph_session

CASCADE_QUERY = """
MATCH (root {id: $node_id})
CALL {
  WITH root
  MATCH (root)<-[:FORMALIZES|DERIVES_FROM|WITNESSES|GENERATED_BY*0..6]-(descendant)
  WHERE any(l IN labels(descendant) WHERE l IN
        ['Contract','Example','Task','CodeUnit','ConfigUnit','Test'])
  RETURN collect(DISTINCT descendant) AS descendants
}
UNWIND descendants + [root] AS n
SET n.knowledge_status = 'stale', n.updated_at = datetime()
RETURN count(n) AS invalidated_count
"""


def run(node_id: str) -> None:
    with graph_session() as sess:
        result = sess.run(CASCADE_QUERY, node_id=node_id)
        record = result.single()
        count = record["invalidated_count"] if record else 0

    if count == 0:
        console.print(f"[red]No node found with id {node_id}.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[yellow]Invalidated {count} node(s)[/yellow] in the derived branch of {node_id}.")
