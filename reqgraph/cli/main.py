"""graph-cli — the sole write path into the ReqGraph Neo4j graph (spec §13)."""

from __future__ import annotations

import typer

from reqgraph.cli.commands import (
    authorize_issue,
    bootstrap_infer,
    bootstrap_observe,
    bootstrap_review,
    bootstrap_scan,
    complete,
    consistency_check,
    derive_tasks,
    detect_changes,
    formalize,
    impact,
    ingest_requirements,
    init,
    invalidate,
    open_issue,
    revalidate,
    run_critic,
    run_task,
    status,
    triage_issue,
    validate,
)
from reqgraph.cli.commands import (
    context as context_cmd,
)

app = typer.Typer(no_args_is_help=True, help="ReqGraph graph-cli")

greenfield_app = typer.Typer(no_args_is_help=True, help="Greenfield pipeline commands")
legacy_app = typer.Typer(no_args_is_help=True, help="Existing-project bootstrap commands")
maintenance_app = typer.Typer(no_args_is_help=True, help="Maintenance / impact / consistency commands")

# Greenfield
app.command("init")(init.run)
greenfield_app.command("ingest-requirements")(ingest_requirements.run)
greenfield_app.command("run-critic")(run_critic.run)
greenfield_app.command("formalize")(formalize.run)
greenfield_app.command("validate")(validate.run)
greenfield_app.command("derive-tasks")(derive_tasks.run)
greenfield_app.command("context")(context_cmd.run)
greenfield_app.command("run-task")(run_task.run)
greenfield_app.command("complete")(complete.run)

# Legacy bootstrap
legacy_app.command("bootstrap-scan")(bootstrap_scan.run)
legacy_app.command("bootstrap-observe")(bootstrap_observe.run)
legacy_app.command("bootstrap-infer")(bootstrap_infer.run)
legacy_app.command("bootstrap-review")(bootstrap_review.run)

# Maintenance
maintenance_app.command("detect-changes")(detect_changes.run)
maintenance_app.command("impact")(impact.run)
maintenance_app.command("revalidate")(revalidate.run)
maintenance_app.command("open-issue")(open_issue.run)
maintenance_app.command("triage-issue")(triage_issue.run)
maintenance_app.command("authorize-issue")(authorize_issue.run)
maintenance_app.command("invalidate")(invalidate.run)
maintenance_app.command("consistency-check")(consistency_check.run)
app.command("status")(status.run)

app.add_typer(greenfield_app)
app.add_typer(legacy_app)
app.add_typer(maintenance_app)


if __name__ == "__main__":
    app()
