"""Neo4j driver singleton + session context manager.

This module is the only place a `neo4j.Driver` is constructed. Everything
else (repositories, consistency checks, CLI commands) obtains a session via
`session()` so connection lifecycle stays centralized.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase, Session

from reqgraph.config import get_settings

# Neo4j's server-side notifications (e.g. "property key does not exist" on
# an empty graph) are expected and noisy on a fresh project; only surface
# real driver errors.
logging.getLogger("neo4j").setLevel(logging.ERROR)

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def session(database: str | None = None) -> Iterator[Session]:
    settings = get_settings()
    drv = get_driver()
    with drv.session(database=database or settings.neo4j_database) as s:
        yield s


def verify_connectivity() -> bool:
    try:
        get_driver().verify_connectivity()
        return True
    except Exception:  # noqa: BLE001 — health check: any driver failure means "not reachable"
        return False
