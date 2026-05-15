"""
Result shaping and logging (Chapter 3 — Neuron guide).

Example::

    try:
        rows = await fetch_many()
        return slim_result(rows)
    except Exception as exc:
        return format_error("my_tool", exc)

See https://srimaan.github.io/neuron-guide/03-first-mcp-server.html
"""

from __future__ import annotations

import logging
from typing import Any


def setup_logger(name: str) -> logging.Logger:
    """
    Return a named logger with a single stream handler (idempotent per logger name).

    Use for tool modules or the MCP server process; respects subsequent level changes
    on the returned logger.
    """
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log


def slim_result(data: Any, max_items: int = 50, max_str_len: int = 5000) -> dict[str, Any]:
    """
    Shrink payloads before returning them to an MCP host.

    - Lists: keep at most ``max_items`` elements (sets ``_truncated`` if capped).
    - Dicts: recurse; drop keys whose value is ``None``; truncate strings longer than
      ``max_str_len``.
    - Strings at the top level: truncated with ``_truncated`` when shortened.
    """
    truncated = False

    def inner(value: Any) -> Any:
        nonlocal truncated

        if isinstance(value, list):
            if len(value) > max_items:
                truncated = True
                value = value[:max_items]
            return [inner(v) for v in value]
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if v is None:
                    continue
                if isinstance(v, str) and v == "":
                    continue
                out[k] = inner(v)
            return out
        if isinstance(value, str):
            if len(value) > max_str_len:
                truncated = True
                return value[:max_str_len]
            return value
        return value

    slimmed = inner(data)
    envelope: dict[str, Any] = {"data": slimmed}
    if truncated:
        envelope["_truncated"] = True
    return envelope


def format_error(tool_name: str, error: Exception) -> dict[str, Any]:
    """
    Normalized tool failure payload (never raises).

    Shape matches the Neuron guide: ``error``, ``tool``, ``message``, ``type``.
    """
    log = logging.getLogger("neuron.tools")
    log.error("%s failed: %s", tool_name, error, exc_info=error)
    return {
        "error": True,
        "tool": tool_name,
        "message": str(error),
        "type": type(error).__name__,
    }
