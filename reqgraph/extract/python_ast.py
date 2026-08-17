"""Python-only symbol extraction via `ast` — the concrete `Extractor` for
this pass. Deliberately bounded (spec-conformant MVP boundary, not a full
static analyzer):

- Granularity is top-level function/class + method, not statement-level.
- `hash` is a content hash of exactly that symbol's source span
  (`ast.get_source_segment`), never the whole file — this is what makes
  `detect-changes` symbol-granular instead of file-granular (spec §9.3).
- The import graph is module-level only, not symbol-level.
- The call graph (`ExtractionResult.calls`) is **intra-file only**: bare
  calls to a top-level function defined in the same file, and `self.method()`
  calls resolved against the enclosing class. Calls to imports, dotted
  external calls, and dynamic dispatch are not resolved — same documented
  boundary as the import graph, just one level deeper.
"""

from __future__ import annotations

import ast

from reqgraph.extract.base import (
    ExtractedCall,
    ExtractedImport,
    ExtractedSymbol,
    ExtractedTest,
    ExtractionResult,
)
from reqgraph.extract.hashing import sha256_text
from reqgraph.extract.naming import path_to_module_name

module_name_for = path_to_module_name  # thin re-export; kept for existing import sites


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


def _find_node_by_symbol(tree: ast.Module, module: str, symbol: str) -> ast.AST | None:
    """Shared qualname-matching walk used by `extract_symbol_source` and
    `extract_symbol_docstring` — same top-level-function/class/method scheme
    `PythonExtractor.extract` uses to build symbol names.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if f"{module}.{node.name}" == symbol:
                return node
        elif isinstance(node, ast.ClassDef):
            class_symbol = f"{module}.{node.name}"
            if class_symbol == symbol:
                return node
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if f"{class_symbol}.{child.name}" == symbol:
                    return child
    return None


class PythonExtractor:
    extensions: tuple[str, ...] = (".py",)
    language = "python"

    def extract(self, path: str, source: str) -> ExtractionResult:
        result = ExtractionResult()
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            return result

        module = module_name_for(path)
        is_test_file = _is_test_file(path)
        framework = _detect_framework(source) if is_test_file else None

        # Pass 1: collect symbols (as before), plus two lookup maps and the
        # callable bodies pass 2 needs to resolve intra-file calls.
        callable_bodies: list[tuple[ast.AST, str, str | None]] = []
        top_level_functions: dict[str, str] = {}
        methods_by_class: dict[str, dict[str, str]] = {}

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{module}.{node.name}"
                is_test = is_test_file and node.name.startswith("test_")
                self._record_function(node, path, symbol, source, is_test, framework, result)
                if not is_test:
                    top_level_functions[node.name] = symbol
                callable_bodies.append((node, symbol, None))
            elif isinstance(node, ast.ClassDef):
                class_symbol = f"{module}.{node.name}"
                class_segment = ast.get_source_segment(source, node) or ""
                result.codeunits.append(
                    ExtractedSymbol(path=path, symbol=class_symbol, kind="class", hash=sha256_text(class_segment))
                )
                is_test_class = is_test_file and _is_test_class(node)
                method_map: dict[str, str] = {}
                for child in node.body:
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    method_symbol = f"{class_symbol}.{child.name}"
                    is_test = is_test_class and child.name.startswith("test")
                    self._record_method(child, path, method_symbol, source, is_test, framework, result)
                    if not is_test:
                        method_map[child.name] = method_symbol
                    callable_bodies.append((child, method_symbol, class_symbol))
                methods_by_class[class_symbol] = method_map
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._handle_import(node, path, result)

        # Pass 2: resolve intra-file calls against the maps pass 1 just built.
        for body_node, caller_symbol, enclosing_class in callable_bodies:
            for call in ast.walk(body_node):
                if not isinstance(call, ast.Call):
                    continue
                callee = self._resolve_callee(call.func, top_level_functions, methods_by_class, enclosing_class)
                if callee:
                    result.calls.append(ExtractedCall(caller_symbol=caller_symbol, callee_symbol=callee))

        return result

    @staticmethod
    def _record_function(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        path: str,
        symbol: str,
        source: str,
        is_test: bool,
        framework: str | None,
        result: ExtractionResult,
    ) -> None:
        segment = ast.get_source_segment(source, node) or ""
        digest = sha256_text(segment)
        if is_test:
            result.tests.append(
                ExtractedTest(path=path, symbol=symbol, kind="function", hash=digest, framework=framework)
            )
        else:
            result.codeunits.append(ExtractedSymbol(path=path, symbol=symbol, kind="function", hash=digest))

    @staticmethod
    def _record_method(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        path: str,
        symbol: str,
        source: str,
        is_test: bool,
        framework: str | None,
        result: ExtractionResult,
    ) -> None:
        segment = ast.get_source_segment(source, node) or ""
        digest = sha256_text(segment)
        if is_test:
            result.tests.append(
                ExtractedTest(path=path, symbol=symbol, kind="method", hash=digest, framework=framework)
            )
        else:
            result.codeunits.append(ExtractedSymbol(path=path, symbol=symbol, kind="method", hash=digest))

    @staticmethod
    def _resolve_callee(
        func: ast.expr,
        top_level_functions: dict[str, str],
        methods_by_class: dict[str, dict[str, str]],
        enclosing_class: str | None,
    ) -> str | None:
        if isinstance(func, ast.Name):
            return top_level_functions.get(func.id)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and enclosing_class is not None
        ):
            return methods_by_class.get(enclosing_class, {}).get(func.attr)
        return None

    def _handle_import(
        self, node: ast.Import | ast.ImportFrom, path: str, result: ExtractionResult
    ) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(ExtractedImport(path=path, imports=alias.name))
        else:
            module = node.module or ""
            result.imports.append(ExtractedImport(path=path, imports=module))


def extract_symbol_source(path: str, source: str, symbol: str) -> str | None:
    """Live source text for one target symbol, or None if not found. Used by
    `complete` to hand the Reviewer role real code, not just a content hash.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    node = _find_node_by_symbol(tree, module_name_for(path), symbol)
    return ast.get_source_segment(source, node) if node is not None else None


def extract_symbol_docstring(path: str, source: str, symbol: str) -> str | None:
    """Docstring for one target symbol, or None if absent/not found. Used by
    `bootstrap-observe` to produce `documentation`-evidence ObservedBehavior.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    node = _find_node_by_symbol(tree, module_name_for(path), symbol)
    if node is None or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None
    return ast.get_docstring(node)
