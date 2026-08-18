#!/usr/bin/env python3
"""Reference implementation of docs/AGENT_INTEGRATION.md's 8-step loop.

This is a demonstration, not a production framework: it assumes the actual
code implementation (steps 2 and 4 of the documented loop) is already done
on disk by the time this script runs — driving that part is the job of
whatever agent (OpenCode, Claude Code, a human) is using this contract, not
of graph-cli or this script. What this script proves is that everything
*around* the implementation step — reading context, verifying RED, recording
artifacts, checking impact, and completing the task — can be driven purely
through graph-cli subprocess calls and JSON/exit-code parsing, with no
direct access to Neo4j or the reqgraph Python package.

Usage:
    python scripts/agent_driver_example.py \\
        --task-id task-01-01 \\
        --repo-path /path/to/target/repo \\
        --test-command "pytest -q" \\
        --record-test orders.py:orders.test_cancel_order_when_shipped_raises \\
        --record-codeunit orders.py:orders.cancel_order
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys

# The real, installed `graph-cli` console script — exactly what an external
# agent (OpenCode, Claude Code, a shell script) would invoke. Falls back to
# `python -m` only if the package wasn't installed with its console script
# (e.g. a bare checkout without `pip install -e .`).
GRAPH_CLI = shutil.which("graph-cli") or f"{sys.executable} -m reqgraph.cli.main"


def run_graph_cli(*args: str) -> subprocess.CompletedProcess:
    print(f"$ graph-cli {' '.join(args)}")
    result = subprocess.run([*GRAPH_CLI.split(), *args], capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result


def step(description: str) -> None:
    print(f"\n--- {description} ---")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--test-command", required=True)
    parser.add_argument("--record-test", action="append", default=[], help="path:symbol, repeatable")
    parser.add_argument("--record-codeunit", action="append", default=[], help="path:symbol, repeatable")
    args = parser.parse_args()

    step("1. Read task context (--json)")
    result = run_graph_cli("context", args.task_id, "--json")
    if result.returncode != 0:
        print("Could not read task context — is the task id correct and Neo4j reachable?")
        return 1
    context = json.loads(result.stdout)
    print(f"Loaded {len(context['items'])} context item(s) for {context['task_title']!r}.")

    print(
        "\n[This is where an external agent would implement the change with its own "
        "tools — Read/Edit/Write, or equivalent. This script assumes that's already "
        "done on disk before --record-test/--record-codeunit were passed in.]"
    )

    for test_ref in args.record_test:
        step(f"3. Verify RED for {test_ref}")
        result = run_graph_cli(
            "run-task", args.task_id, "--repo-path", args.repo_path, "--verify-red",
            "--test-command", args.test_command, "--allow-pass",
        )
        # --allow-pass: this demo runs after the fix already landed on disk, so RED
        # can't be observed for real here — a live agent would run this step BEFORE
        # implementing the fix and would omit --allow-pass.

        step(f"5. Record test artifact {test_ref}")
        result = run_graph_cli("run-task", args.task_id, "--repo-path", args.repo_path, "--record-test", test_ref)
        if result.returncode != 0:
            return 1

    step("6. Record CodeUnit artifacts and run impact on each")
    recorded_codeunit_ids = []
    for cu_ref in args.record_codeunit:
        result = run_graph_cli("run-task", args.task_id, "--repo-path", args.repo_path, "--record-codeunit", cu_ref)
        if result.returncode != 0:
            return 1
        # `run-task` echoes "recorded CodeUnit <path>::<symbol> id=<uuid>" to stdout —
        # that's the graph id `impact` needs next, read from the subprocess output,
        # not from a direct database lookup (this script never imports reqgraph itself).
        match = re.search(r"recorded CodeUnit .*? id=(\S+)", result.stdout)
        if match:
            recorded_codeunit_ids.append(match.group(1))

    for codeunit_id in recorded_codeunit_ids:
        result = run_graph_cli("impact", codeunit_id, "--repo-path", args.repo_path)
        if result.returncode != 0:
            return 1

    step("7. Complete the task")
    result = run_graph_cli(
        "complete", args.task_id, "--repo-path", args.repo_path, "--test-command", args.test_command
    )
    if result.returncode != 0:
        print("complete failed — see the gate failure reason above. Fix and re-run; no partial state to undo.")
        return 1

    step("8. Final status")
    run_graph_cli("status", "--json")

    print("\nDone — task driven end-to-end via graph-cli subprocess calls only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
