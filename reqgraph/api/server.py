"""Local HTTP API for `viewer/` — the one thing the browser genuinely can't
do itself: read a project's real filesystem, run tree-sitter, and call the
Anthropic API to run bootstrap-scan/observe/infer. Everything else the
viewer does (reading/writing the graph, the review queue) talks to Neo4j
directly over bolt, same as NeoDash/Neo4j Browser — this server exists only
to run and stream those three commands.

Serves exactly one project: whichever one this process's cwd/.env point at,
same as running `graph-cli` by hand from that project's directory (see
config.py's cwd-.env layering). Run one of these per project you're
actively bootstrapping — alongside its own dedicated Neo4j instance (see
README's "One Neo4j instance per project") — never one shared across
projects, for the same isolation reasons.

Requires the `api` extra: `pip install -e ".[dev,api]"`.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import typer
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from reqgraph.cli.commands import bootstrap_infer, bootstrap_observe, bootstrap_scan
from reqgraph.cli.common import project_root
from reqgraph.state import io as state_io
from reqgraph.state.paths import bootstrap_state_path
from reqgraph.state.schemas import BootstrapState

app = FastAPI(title="ReqGraph local API")

# Loopback-only, any port: a project's viewer/ and this server can each land
# on a different auto-incremented Vite port when several projects are open
# at once, so a fixed origin list would be too brittle.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "project_root": str(project_root())}


@app.get("/bootstrap/state")
def get_bootstrap_state() -> dict[str, Any]:
    path = bootstrap_state_path(project_root())
    if not path.exists():
        return BootstrapState().model_dump(mode="json")
    return state_io.read_json(path)


_DONE = object()


def _stream(work: Callable[[Callable[[str], None]], None]) -> StreamingResponse:
    """Runs `work` on a background thread — `work` takes an on_progress
    callback and calls it with a line at each meaningful step — and streams
    each line as a Server-Sent Event as it happens, finishing with a
    `done`/`error` event. Kept generic so the three endpoints below are one
    line each.
    """
    q: queue.Queue[Any] = queue.Queue()

    def _target() -> None:
        try:
            work(q.put)
        except typer.Exit:
            pass  # "nothing to do" cases — already explained via a progress line
        except Exception as exc:  # noqa: BLE001 — surfaced to the client, not swallowed
            q.put(("error", str(exc) or type(exc).__name__))
        finally:
            q.put(_DONE)

    threading.Thread(target=_target, daemon=True).start()

    async def event_gen() -> AsyncIterator[bytes]:
        while True:
            item = await run_in_threadpool(q.get)
            if item is _DONE:
                yield b"event: done\ndata: done\n\n"
                return
            if isinstance(item, tuple) and item[0] == "error":
                # Named "failed", not "error": EventSource's own connection-
                # failure event is also literally named "error" client-side,
                # so a custom SSE event reusing that name would be
                # indistinguishable from a dropped connection in the browser.
                yield f"event: failed\ndata: {item[1]}\n\n".encode()
                return
            yield f"data: {item}\n\n".encode()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_repo_path(repo_path: str) -> Path:
    """A path typed into the browser arrives as a literal string over HTTP —
    unlike a CLI arg, it never passes through a shell, so `~` is never
    expanded on its way here. `Path.expanduser()` does what the shell would
    have done for `graph-cli bootstrap-scan ~/...`.
    """
    return Path(repo_path).expanduser()


@app.get("/bootstrap/scan/stream")
def scan_stream(
    repo_path: str = Query(default="."),
    include_lockfiles: bool = Query(default=False),
) -> StreamingResponse:
    path = _resolve_repo_path(repo_path)
    return _stream(
        lambda on_progress: bootstrap_scan.run_impl(
            path, include_lockfiles=include_lockfiles, on_progress=on_progress
        )
    )


@app.get("/bootstrap/observe/stream")
def observe_stream(
    repo_path: str = Query(default="."),
    legacy: bool = Query(default=False),
) -> StreamingResponse:
    path = _resolve_repo_path(repo_path)
    return _stream(
        lambda on_progress: bootstrap_observe.run_impl(path, legacy=legacy, on_progress=on_progress)
    )


@app.get("/bootstrap/infer/stream")
def infer_stream(max_groups: int = Query(default=10)) -> StreamingResponse:
    return _stream(
        lambda on_progress: bootstrap_infer.run_impl(max_groups=max_groups, on_progress=on_progress)
    )


def run_server(host: str = "127.0.0.1", port: int = 8321) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)
