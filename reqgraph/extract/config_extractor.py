"""Heuristic ConfigUnit extraction — deliberately rough (spec §9.4: config
diffing must be key-level, never whole-file). Supports `.env`, `.toml`,
`.json`, a naive flat `.yaml` (top-level `key: value` lines only, no
nesting/anchors — extend later if a project needs more), and top-level
literal assignments in `settings*.py`/`config*.py`. No external YAML/TOML
dependency beyond stdlib `tomllib` (py311+).
"""

from __future__ import annotations

import ast
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from reqgraph.extract.hashing import sha256_value

FEATURE_FLAG_MARKERS = ("_ENABLED", "_FLAG", "_ON", "_OFF")


@dataclass(frozen=True)
class ExtractedConfigUnit:
    path: str
    key: str
    kind: str  # setting | feature_flag | environment | route_config | framework_config | other
    value_hash: str
    scope_hint: str = "project-wide"


def _guess_kind(key: str, is_env_file: bool) -> str:
    upper = key.upper()
    if any(marker in upper for marker in FEATURE_FLAG_MARKERS):
        return "feature_flag"
    if is_env_file:
        return "environment"
    return "setting"


def _flatten(prefix: str, value: object) -> list[tuple[str, object]]:
    if isinstance(value, dict):
        out: list[tuple[str, object]] = []
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_flatten(key, v))
        return out
    return [(prefix, value)]


def _extract_env(path: str, source: str) -> list[ExtractedConfigUnit]:
    units = []
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        units.append(
            ExtractedConfigUnit(
                path=path, key=key, kind=_guess_kind(key, True), value_hash=sha256_value(value.strip())
            )
        )
    return units


def _extract_toml(path: str, source: str) -> list[ExtractedConfigUnit]:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return []
    return [
        ExtractedConfigUnit(path=path, key=k, kind=_guess_kind(k, False), value_hash=sha256_value(v))
        for k, v in _flatten("", data)
        if k
    ]


def _extract_json(path: str, source: str) -> list[ExtractedConfigUnit]:
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return [
        ExtractedConfigUnit(path=path, key=k, kind=_guess_kind(k, False), value_hash=sha256_value(v))
        for k, v in _flatten("", data)
        if k
    ]


def _extract_yaml_flat(path: str, source: str) -> list[ExtractedConfigUnit]:
    """Naive flat `key: value` parser — no nesting, lists, or anchors."""
    units = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        if line.startswith((" ", "\t")):
            continue  # nested — out of scope for this heuristic
        key, _, value = stripped.partition(":")
        key = key.strip()
        if not key:
            continue
        units.append(
            ExtractedConfigUnit(
                path=path, key=key, kind=_guess_kind(key, False), value_hash=sha256_value(value.strip())
            )
        )
    return units


def _extract_python_settings(path: str, source: str) -> list[ExtractedConfigUnit]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    units = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                units.append(
                    ExtractedConfigUnit(
                        path=path,
                        key=target.id,
                        kind=_guess_kind(target.id, False),
                        value_hash=sha256_value(value),
                    )
                )
    return units


def is_config_path(path: str) -> bool:
    name = Path(path).name
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith((".toml", ".json", ".yaml", ".yml"))
        and "settings" not in name
        or name.startswith(("settings", "config")) and name.endswith(".py")
    )


def extract_config_units(path: str, source: str) -> list[ExtractedConfigUnit]:
    name = Path(path).name
    if name == ".env" or name.startswith(".env."):
        return _extract_env(path, source)
    if name.endswith(".toml"):
        return _extract_toml(path, source)
    if name.endswith(".json"):
        return _extract_json(path, source)
    if name.endswith((".yaml", ".yml")):
        return _extract_yaml_flat(path, source)
    if name.startswith(("settings", "config")) and name.endswith(".py"):
        return _extract_python_settings(path, source)
    return []
