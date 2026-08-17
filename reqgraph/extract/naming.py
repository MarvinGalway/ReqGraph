"""Shared symbol-naming scheme across language extractors — dotted
`module.symbol` / `module.Class.method`, so CodeUnit/Test symbols stay
consistent across languages in the same graph.
"""

from __future__ import annotations


def path_to_module_name(path: str) -> str:
    stem = path
    for suffix in (".py", ".js", ".jsx", ".ts", ".tsx"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.replace("/", ".").replace("\\", ".")
