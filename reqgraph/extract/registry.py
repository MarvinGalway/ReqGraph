from __future__ import annotations

from pathlib import Path

from reqgraph.extract.base import Extractor
from reqgraph.extract.python_ast import PythonExtractor

_EXTRACTORS: list[Extractor] = [PythonExtractor()]

try:
    from reqgraph.extract.javascript_ts import JavaScriptExtractor

    _EXTRACTORS.append(JavaScriptExtractor())
except ImportError:
    pass  # 'js' extra not installed — JS/TS files are simply not extracted


def get_extractor_for(path: str) -> Extractor | None:
    suffix = Path(path).suffix
    for extractor in _EXTRACTORS:
        if suffix in extractor.extensions:
            return extractor
    return None
