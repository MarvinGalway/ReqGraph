"""JavaScript/TypeScript extraction via tree-sitter — the second concrete
`Extractor`, gated behind the optional `js` extra (`tree-sitter`,
`tree-sitter-javascript`, `tree-sitter-typescript`). Mirrors
`PythonExtractor`'s documented boundaries exactly:

- Granularity is top-level function/class + method, not statement-level.
- `hash` is a content hash of exactly that symbol's source span, never the
  whole file.
- The import graph is module-level only (ES `import` statements).
- The call graph is intra-file only: bare `foo()` calls resolved against
  top-level functions/arrow-functions in the same file, and `this.method()`
  calls resolved against the enclosing class. Everything else (external
  calls, dynamic dispatch, CommonJS `require`) is unresolved.

`.ts`/`.tsx` use the TypeScript/TSX grammar; `.js`/`.jsx` use the JavaScript
grammar (which already parses JSX syntax).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from reqgraph.extract.base import (
    ExtractedCall,
    ExtractedImport,
    ExtractedSymbol,
    ExtractedTest,
    ExtractionResult,
)
from reqgraph.extract.hashing import sha256_text
from reqgraph.extract.naming import path_to_module_name

try:
    import tree_sitter_javascript as _tsjs
    import tree_sitter_typescript as _tsts
    from tree_sitter import Language, Node, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


def _is_test_file(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1]
    return (
        ".test." in filename
        or ".spec." in filename
        or "/__tests__/" in f"/{path}"
    )


def _detect_framework(source: str) -> str | None:
    if "vitest" in source:
        return "vitest"
    if "jest" in source or "@jest" in source:
        return "jest"
    if "mocha" in source:
        return "mocha"
    if "describe(" in source or "it(" in source or "test(" in source:
        return "unknown"
    return None


def _walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8")


def _declaration_of(node: Node) -> Node:
    """Unwraps `export`/`export default` — tree-sitter puts a `function_declaration`/
    `lexical_declaration`/`class_declaration` written as `export function foo() {}`
    (or `export default ...`) inside an `export_statement` node rather than as a
    direct child of the file, on a `declaration` field. Without unwrapping this,
    every exported top-level symbol — i.e. in idiomatic JS/TS, almost everything
    meant to be used from outside the file — is invisible to the two loops below;
    only private, non-exported helpers get through. `declaration` is absent only
    for an anonymous `export default <expression>`, which has no name to extract
    anyway and falls through to the caller's existing unhandled-node-type case.
    """
    if node.type == "export_statement":
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            return declaration
    return node


_TEST_CALL_NAMES = {"it", "test"}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "case"


class JavaScriptExtractor:
    extensions: tuple[str, ...] = (".js", ".jsx", ".ts", ".tsx")
    language = "javascript"

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                "JavaScriptExtractor requires the 'js' extra: pip install 'reqgraph[js]'"
            )
        self._js_lang = Language(_tsjs.language())
        self._ts_lang = Language(_tsts.language_typescript())
        self._tsx_lang = Language(_tsts.language_tsx())

    def _language_for(self, path: str) -> Language:
        if path.endswith(".tsx"):
            return self._tsx_lang
        if path.endswith(".ts"):
            return self._ts_lang
        return self._js_lang

    def extract(self, path: str, source: str) -> ExtractionResult:
        result = ExtractionResult()
        parser = Parser(self._language_for(path))
        try:
            tree = parser.parse(source.encode("utf-8"))
        except (ValueError, RecursionError):
            return result

        module = path_to_module_name(path)
        is_test_file = _is_test_file(path)
        framework = _detect_framework(source) if is_test_file else None

        top_level_functions: dict[str, str] = {}
        methods_by_class: dict[str, dict[str, str]] = {}
        callable_bodies: list[tuple[Node, str, str | None]] = []

        for raw_node in tree.root_node.children:
            node = _declaration_of(raw_node)
            if node.type == "function_declaration":
                name = _text(node.child_by_field_name("name"))
                if not name:
                    continue
                symbol = f"{module}.{name}"
                is_test = is_test_file and name.startswith("test")
                self._record(node, path, symbol, "function", is_test, framework, result)
                if not is_test:
                    top_level_functions[name] = symbol
                callable_bodies.append((node, symbol, None))

            elif node.type == "lexical_declaration":
                for decl in node.children:
                    if decl.type != "variable_declarator":
                        continue
                    value_node = decl.child_by_field_name("value")
                    if value_node is None or value_node.type != "arrow_function":
                        continue
                    name = _text(decl.child_by_field_name("name"))
                    if not name:
                        continue
                    symbol = f"{module}.{name}"
                    is_test = is_test_file and name.startswith("test")
                    self._record(decl, path, symbol, "function", is_test, framework, result)
                    if not is_test:
                        top_level_functions[name] = symbol
                    callable_bodies.append((value_node, symbol, None))

            elif node.type == "class_declaration":
                name = _text(node.child_by_field_name("name"))
                if not name:
                    continue
                class_symbol = f"{module}.{name}"
                result.codeunits.append(
                    ExtractedSymbol(
                        path=path, symbol=class_symbol, kind="class", hash=sha256_text(_text(node)), language="javascript"
                    )
                )
                method_map: dict[str, str] = {}
                body = node.child_by_field_name("body")
                for member in body.children if body else []:
                    if member.type != "method_definition":
                        continue
                    method_name = _text(member.child_by_field_name("name"))
                    if not method_name:
                        continue
                    method_symbol = f"{class_symbol}.{method_name}"
                    is_test = is_test_file and method_name.startswith("test")
                    self._record(member, path, method_symbol, "method", is_test, framework, result)
                    if not is_test:
                        method_map[method_name] = method_symbol
                    callable_bodies.append((member, method_symbol, class_symbol))
                methods_by_class[class_symbol] = method_map

            elif node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                module_path = _text(source_node).strip("'\"")
                if module_path:
                    result.imports.append(ExtractedImport(path=path, imports=module_path))

        if is_test_file:
            self._record_it_test_callbacks(tree.root_node, path, module, framework, result)

        for body_node, caller_symbol, enclosing_class in callable_bodies:
            for call in _walk(body_node):
                if call.type != "call_expression":
                    continue
                callee = self._resolve_callee(
                    call.child_by_field_name("function"), top_level_functions, methods_by_class, enclosing_class
                )
                if callee:
                    result.calls.append(ExtractedCall(caller_symbol=caller_symbol, callee_symbol=callee))

        return result

    @staticmethod
    def _record_it_test_callbacks(
        root: Node, path: str, module: str, framework: str | None, result: ExtractionResult
    ) -> None:
        """Real-world JS tests are overwhelmingly `it("description", () => {...})`
        / `test("description", () => {...})` callbacks, not named function
        declarations — the pattern the top-level-children loop above catches.
        Each call becomes a Test symbol named from a slugified description
        (there's no function name to use), deduplicated within the file.
        """
        seen: dict[str, int] = {}
        for node in _walk(root):
            if node.type != "call_expression":
                continue
            callee = node.child_by_field_name("function")
            if callee is None or callee.type != "identifier" or _text(callee) not in _TEST_CALL_NAMES:
                continue
            args = node.child_by_field_name("arguments")
            if args is None:
                continue
            arg_nodes = [c for c in args.named_children]
            if len(arg_nodes) < 2 or arg_nodes[0].type != "string":
                continue
            description = _text(arg_nodes[0]).strip("'\"`")
            slug = _slugify(description)
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            if count:
                slug = f"{slug}_{count}"
            result.tests.append(
                ExtractedTest(
                    path=path,
                    symbol=f"{module}.{slug}",
                    kind="function",
                    hash=sha256_text(_text(node)),
                    framework=framework,
                    language="javascript",
                )
            )

    @staticmethod
    def _record(
        node: Node,
        path: str,
        symbol: str,
        kind: str,
        is_test: bool,
        framework: str | None,
        result: ExtractionResult,
    ) -> None:
        digest = sha256_text(_text(node))
        if is_test:
            result.tests.append(ExtractedTest(path=path, symbol=symbol, kind=kind, hash=digest, framework=framework, language="javascript"))
        else:
            result.codeunits.append(ExtractedSymbol(path=path, symbol=symbol, kind=kind, hash=digest, language="javascript"))

    @staticmethod
    def _resolve_callee(
        func_node: Node | None,
        top_level_functions: dict[str, str],
        methods_by_class: dict[str, dict[str, str]],
        enclosing_class: str | None,
    ) -> str | None:
        if func_node is None:
            return None
        if func_node.type == "identifier":
            return top_level_functions.get(_text(func_node))
        if func_node.type == "member_expression" and enclosing_class is not None:
            obj = func_node.child_by_field_name("object")
            prop = func_node.child_by_field_name("property")
            if obj is not None and obj.type == "this" and prop is not None:
                return methods_by_class.get(enclosing_class, {}).get(_text(prop))
        return None


def _language_for(path: str) -> Language:
    if path.endswith(".tsx"):
        return Language(_tsts.language_tsx())
    if path.endswith(".ts"):
        return Language(_tsts.language_typescript())
    return Language(_tsjs.language())


def _parse_root(path: str, source: str) -> Node | None:
    parser = Parser(_language_for(path))
    try:
        tree = parser.parse(source.encode("utf-8"))
    except (ValueError, RecursionError):
        return None
    return tree.root_node


def _find_node_by_symbol(root: Node, module: str, symbol: str) -> Node | None:
    """Same top-level-function/class/method naming scheme as
    `JavaScriptExtractor.extract` — mirrors `python_ast._find_node_by_symbol`.
    Returns the same node whose text `extract()` hashes for that symbol
    (the `variable_declarator` for arrow functions, not its `arrow_function`
    value), so callers get source text consistent with the CodeUnit hash.
    """
    for raw_node in root.children:
        node = _declaration_of(raw_node)
        if node.type == "function_declaration":
            name = _text(node.child_by_field_name("name"))
            if name and f"{module}.{name}" == symbol:
                return node
        elif node.type == "lexical_declaration":
            for decl in node.children:
                if decl.type != "variable_declarator":
                    continue
                value_node = decl.child_by_field_name("value")
                if value_node is None or value_node.type != "arrow_function":
                    continue
                name = _text(decl.child_by_field_name("name"))
                if name and f"{module}.{name}" == symbol:
                    return decl
        elif node.type == "class_declaration":
            name = _text(node.child_by_field_name("name"))
            if not name:
                continue
            class_symbol = f"{module}.{name}"
            if class_symbol == symbol:
                return node
            body = node.child_by_field_name("body")
            for member in body.children if body else []:
                if member.type != "method_definition":
                    continue
                method_name = _text(member.child_by_field_name("name"))
                if method_name and f"{class_symbol}.{method_name}" == symbol:
                    return member
    return None


def _leading_comment(node: Node) -> Node | None:
    # A JSDoc block precedes the *statement* — for `const foo = () => {}` that
    # means the enclosing lexical_declaration, not the variable_declarator
    # `_find_node_by_symbol` returns for arrow functions. And for anything
    # exported (`export function foo() {}`), the JSDoc precedes the enclosing
    # export_statement, not the declaration `_find_node_by_symbol` returns
    # after `_declaration_of` unwraps it — same reason, one more level up.
    target = node.parent if node.type == "variable_declarator" else node
    if target is not None and target.parent is not None and target.parent.type == "export_statement":
        target = target.parent
    return target.prev_sibling if target is not None else None


def _clean_jsdoc(text: str) -> str:
    body = text.removeprefix("/**").removesuffix("*/")
    lines = [line.strip().lstrip("*").strip() for line in body.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_symbol_source(path: str, source: str, symbol: str) -> str | None:
    """Live source text for one target symbol, or None if not found/unavailable.
    JS/TS counterpart to `python_ast.extract_symbol_source` — used by
    `bootstrap-observe --legacy` to seed `static-code` evidence when there's
    no test or JSDoc for a CodeUnit.
    """
    if not TREE_SITTER_AVAILABLE:
        return None
    root = _parse_root(path, source)
    if root is None:
        return None
    node = _find_node_by_symbol(root, path_to_module_name(path), symbol)
    return _text(node) if node is not None else None


def extract_symbol_docstring(path: str, source: str, symbol: str) -> str | None:
    """JSDoc (`/** ... */`) immediately preceding one target symbol, or None.
    JS/TS counterpart to `python_ast.extract_symbol_docstring` — used by
    `bootstrap-observe` to produce `documentation`-evidence ObservedBehavior.
    """
    if not TREE_SITTER_AVAILABLE:
        return None
    root = _parse_root(path, source)
    if root is None:
        return None
    node = _find_node_by_symbol(root, path_to_module_name(path), symbol)
    if node is None:
        return None
    comment = _leading_comment(node)
    if comment is None or comment.type != "comment" or not _text(comment).startswith("/**"):
        return None
    return _clean_jsdoc(_text(comment)) or None
