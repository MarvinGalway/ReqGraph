"""Content hashing used for symbol- and key-level granularity (spec §9.3/§9.4)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, default=str))
