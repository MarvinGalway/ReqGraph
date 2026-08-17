"""Python-only symbol extraction via `ast` — the concrete `Extractor` for
this pass. Deliberately bounded (spec-conformant MVP boundary, not a full
static analyzer):

- Granularity is top-level function/class + method, not statement-level.
- `hash` is a content hash of exactly that symbol's source span
  (`ast.get_source_segment`), never the whole file — this is what makes
  `detect-changes` symbol-granular instead of file-granular (spec §9.3).
- `DEPENDS_ON` candidates are module-level imports only, not a full call
  graph.
"""

from __future__ import annotations

import ast

from reqgraph.extract.base import ExtractedImport, ExtractedSymbol, ExtractedTest, ExtractionResult
from reqgraph.extract.hashing import sha256_text


def module_name_for(path: str) -> str:
    stem = path.removesuffix(".py")
    return stem.replace("/", ".").replace("\\", ".")


def _is_test_file(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1]
    return filename.startswith("test_") or filename.endswith("_test.py")


def _detect_framework(source: str) -> str | None:
    if "import pytest" in source or "from pytest" in source:
        return "pytest"
    if "import unittest" in source or "from unittest" in source:
        return "unittest"
    return None


def _is_test_class(node: ast.ClassDef) -> bool:
    return any(
        (isinstance(base, ast.Attribute) and base.attr == "TestCase")
        or (isinstance(base, ast.Name) and base.id == "TestCase")
        for base in node.bases
    )


class PythonExtractor:
    extensions: tuple[str, ...] = (".py",)

    def extract(self, path: str, source: str) -> ExtractionResult:
        result = ExtractionResult()
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            return result

        module = module_name_for(path)
        is_test_file = _is_test_file(path)
        framework = _detect_framework(source) if is_test_file else None

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._handle_function(node, path, module, source, is_test_file, framework, result)
            elif isinstance(node, ast.ClassDef):
                self._handle_class(node, path, module, source, is_test_file, framework, result)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._handle_import(node, path, result)

        return result

    def _handle_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        path: str,
        module: str,
        source: str,
        is_test_file: bool,
        framework: str | None,
        result: ExtractionResult,
    ) -> None:
        symbol = f"{module}.{node.name}"
        segment = ast.get_source_segment(source, node) or ""
        digest = sha256_text(segment)
        if is_test_file and node.name.startswith("test_"):
            result.tests.append(
                ExtractedTest(path=path, symbol=symbol, kind="function", hash=digest, framework=framework)
            )
        else:
            result.codeunits.append(
                ExtractedSymbol(path=path, symbol=symbol, kind="function", hash=digest)
            )

    def _handle_class(
        self,
        node: ast.ClassDef,
        path: str,
        module: str,
        source: str,
        is_test_file: bool,
        framework: str | None,
        result: ExtractionResult,
    ) -> None:
        class_symbol = f"{module}.{node.name}"
        class_segment = ast.get_source_segment(source, node) or ""
        result.codeunits.append(
            ExtractedSymbol(path=path, symbol=class_symbol, kind="class", hash=sha256_text(class_segment))
        )
        is_test_class = is_test_file and _is_test_class(node)
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method_symbol = f"{class_symbol}.{child.name}"
            method_segment = ast.get_source_segment(source, child) or ""
            digest = sha256_text(method_segment)
            if is_test_class and child.name.startswith("test"):
                result.tests.append(
                    ExtractedTest(
                        path=path, symbol=method_symbol, kind="method", hash=digest, framework=framework
                    )
                )
            else:
                result.codeunits.append(
                    ExtractedSymbol(path=path, symbol=method_symbol, kind="method", hash=digest)
                )

    def _handle_import(
        self, node: ast.Import | ast.ImportFrom, path: str, result: ExtractionResult
    ) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(ExtractedImport(path=path, imports=alias.name))
        else:
            module = node.module or ""
            result.imports.append(ExtractedImport(path=path, imports=module))
