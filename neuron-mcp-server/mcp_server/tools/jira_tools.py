"""Jira MCP tools (``jira`` library) — Chapter 3 Neuron guide."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from jira import JIRA

from mcp_server.config import get_settings
from mcp_server.utils import format_error, slim_result

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _jira_server_url() -> str:
    s = get_settings()
    dom = s.jira_domain.strip().rstrip("/")
    dom = dom.removeprefix("https://").removeprefix("http://")
    if not dom:
        raise ValueError("JIRA_DOMAIN is not set")
    if not (s.jira_user and s.jira_api_token):
        raise ValueError("JIRA_USER and JIRA_API_TOKEN are required")
    return f"https://{dom}"


def _jira_client() -> JIRA:
    s = get_settings()
    verify: bool | str = True
    if s.jira_ssl_insecure_skip_tls_verify:
        verify = False
    else:
        trust_store = s.jira_ssl_trust_store.strip()
        if trust_store:
            verify = trust_store
    return JIRA(
        server=_jira_server_url(),
        basic_auth=(s.jira_user, s.jira_api_token),
        options={"verify": verify},
    )


def _jira_search_sync(jql: str, max_results: int) -> list[dict[str, Any]]:
    j = _jira_client()
    base = _jira_server_url()
    issues = j.search_issues(jql, maxResults=max_results)
    out: list[dict[str, Any]] = []
    for issue in issues:
        desc = issue.fields.description
        if desc is None:
            preview = ""
        elif isinstance(desc, str):
            preview = desc[:500]
        else:
            preview = str(desc)[:500]
        assignee = (
            issue.fields.assignee.displayName
            if getattr(issue.fields, "assignee", None) is not None
            else None
        )
        priority = (
            issue.fields.priority.name
            if getattr(issue.fields, "priority", None) is not None
            else None
        )
        status = issue.fields.status.name if issue.fields.status else None
        out.append(
            {
                "key": issue.key,
                "summary": issue.fields.summary,
                "status": status,
                "priority": priority,
                "assignee": assignee,
                "url": f"{base}/browse/{issue.key}",
                "description_preview": preview,
            }
        )
    return out


def _jira_create_sync(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str,
    priority: str,
) -> dict[str, Any]:
    j = _jira_client()
    base = _jira_server_url()
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = description
    if priority:
        fields["priority"] = {"name": priority}
    new_issue = j.create_issue(fields=fields)
    return {
        "key": new_issue.key,
        "url": f"{base}/browse/{new_issue.key}",
        "id": str(new_issue.id),
    }


async def jira_search_issues(jql: str, max_results: int = 20) -> dict[str, Any]:
    """
    Search Jira issues with JQL.

    Returns a slim list of matches (key, summary, status, priority, assignee, url,
    description preview).
    """
    try:
        max_results = max(1, min(max_results, 50))
        rows = await asyncio.to_thread(_jira_search_sync, jql, max_results)
        return slim_result(rows)
    except Exception as exc:  # noqa: BLE001
        return format_error("jira_search_issues", exc)


async def jira_create_issue(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
    priority: str = "Medium",
) -> dict[str, Any]:
    """
    Create a Jira issue in ``project_key`` with the given fields.

    ``issue_type`` and ``priority`` must match names configured in your Jira project.
    """
    try:
        payload = await asyncio.to_thread(
            _jira_create_sync,
            project_key,
            summary,
            description,
            issue_type,
            priority,
        )
        return slim_result(payload)
    except Exception as exc:  # noqa: BLE001
        return format_error("jira_create_issue", exc)


def register_jira_tools(mcp: "FastMCP") -> None:
    """Register Jira tools on the FastMCP server."""
    mcp.tool(jira_search_issues)
    mcp.tool(jira_create_issue)
