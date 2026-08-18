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


def extract_source_for_symbol(path: str, source: str, symbol: str) -> str | None:
    """Language-dispatching counterpart to `python_ast.extract_symbol_source` /
    `javascript_ts.extract_symbol_source` — picks the extractor by extension
    so callers don't need per-language imports."""
    suffix = Path(path).suffix
    if suffix == ".py":
        from reqgraph.extract.python_ast import extract_symbol_source

        return extract_symbol_source(path, source, symbol)
    if suffix in (".js", ".jsx", ".ts", ".tsx"):
        try:
            from reqgraph.extract.javascript_ts import extract_symbol_source as extract_js_source
        except ImportError:
            return None
        return extract_js_source(path, source, symbol)
    return None


def extract_docstring_for_symbol(path: str, source: str, symbol: str) -> str | None:
    """Language-dispatching counterpart to `python_ast.extract_symbol_docstring` /
    `javascript_ts.extract_symbol_docstring`."""
    suffix = Path(path).suffix
    if suffix == ".py":
        from reqgraph.extract.python_ast import extract_symbol_docstring

        return extract_symbol_docstring(path, source, symbol)
    if suffix in (".js", ".jsx", ".ts", ".tsx"):
        try:
            from reqgraph.extract.javascript_ts import extract_symbol_docstring as extract_js_docstring
        except ImportError:
            return None
        return extract_js_docstring(path, source, symbol)
    return None
