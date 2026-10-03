"""Connector: the implementation lives in schema_guard/engine/diff.py."""

from .engine.diff import classify, compare

__all__ = ["classify", "compare"]
