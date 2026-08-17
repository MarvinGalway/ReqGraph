"""Extractor protocol — `bootstrap-scan`/`detect-changes` are language-agnostic
at the CLI level; only `python_ast.py` implements a concrete extractor this
pass. `registry.py` maps file extensions to an extractor instance so future
languages plug in without touching the CLI layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ExtractedSymbol:
    path: str
    symbol: str
    kind: str  # function | class | method | module | other
    hash: str
    language: str = "python"


@dataclass(frozen=True)
class ExtractedTest(ExtractedSymbol):
    framework: str | None = None


@dataclass(frozen=True)
class ExtractedImport:
    path: str
    imports: str  # dotted module imported, at module granularity


@dataclass
class ExtractionResult:
    codeunits: list[ExtractedSymbol] = field(default_factory=list)
    tests: list[ExtractedTest] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)


class Extractor(Protocol):
    extensions: tuple[str, ...]

    def extract(self, path: str, source: str) -> ExtractionResult: ...
