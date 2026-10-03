"""Connector: the implementation lives in schema_guard/engine/impact.py."""

from .engine.impact import analyze_collection, deep_reason_specs, explain, reason_specs, summarize_values, warning_specs

__all__ = ["analyze_collection", "deep_reason_specs", "explain", "reason_specs", "summarize_values", "warning_specs"]
