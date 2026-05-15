"""
Register all MCP tools (Chapter 3 — Neuron guide).

Each integration module exposes ``register_*_tools(mcp)`` so ``main.py`` stays a thin shell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_all_tools(mcp: "FastMCP") -> None:
    """Register GitHub, Jira, and Slack tool sets (five tools total)."""
    from mcp_server.tools.github_tools import register_github_tools
    from mcp_server.tools.jira_tools import register_jira_tools
    from mcp_server.tools.slack_tools import register_slack_tools

    register_github_tools(mcp)
    register_jira_tools(mcp)
    register_slack_tools(mcp)
