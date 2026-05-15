"""GitHub MCP tools (PyGithub) — Chapter 3 Neuron guide."""

from __future__ import annotations

import asyncio
import itertools
from typing import TYPE_CHECKING, Any

from github import Auth, Github

from mcp_server.config import get_settings
from mcp_server.utils import format_error, slim_result

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _github_client() -> Github:
    settings = get_settings()
    token = settings.github_token
    if not token:
        raise ValueError("GITHUB_TOKEN is not set")
    client = Github(auth=Auth.Token(token))

    # Optional guardrail: enforce token ownership by service account login.
    expected_user = settings.github_service_user.strip().lower()
    if expected_user:
        actual_user = (client.get_user().login or "").strip().lower()
        if actual_user != expected_user:
            raise ValueError(
                f"GITHUB_TOKEN belongs to '{actual_user}', expected '{expected_user}'"
            )
    return client


def _build_search_query(query: str, repo: str, state: str) -> str:
    parts: list[str] = []
    if repo.strip():
        r = repo.strip()
        if "/" in r:
            parts.append(f"repo:{r}")
        else:
            raise ValueError("repo must be 'owner/name' when provided")
    q = (query or "").strip()
    if q:
        parts.append(q)
    elif not repo.strip():
        parts.append("sort:updated-desc")
    if "is:pr" not in " ".join(parts).lower():
        parts.append("is:pr")
    st = state.lower().strip()
    if st in {"open", "closed"} and f"is:{st}" not in " ".join(parts).lower():
        parts.append(f"is:{st}")
    elif st == "all":
        pass
    elif st not in {"open", "closed", "all"}:
        raise ValueError("state must be one of: open, closed, all")
    return " ".join(parts)


def _github_search_prs_sync(query: str, repo: str, state: str) -> list[dict[str, Any]]:
    g = _github_client()
    q = _build_search_query(query, repo, state)
    results = g.search_issues(query=q)
    out: list[dict[str, Any]] = []
    for issue in itertools.islice(results, 80):
        if issue.pull_request is None:
            continue
        body = issue.body or ""
        out.append(
            {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "url": issue.html_url,
                "author": issue.user.login if issue.user else None,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "body_preview": body[:500],
            }
        )
        if len(out) >= 50:
            break
    return out


def _github_get_pr_diff_sync(owner: str, repo: str, pull_number: int) -> dict[str, Any]:
    g = _github_client()
    r = g.get_repo(f"{owner}/{repo}")
    pr = r.get_pull(pull_number)
    files_out: list[dict[str, Any]] = []
    for f in itertools.islice(pr.get_files(), 20):
        patch = f.patch or ""
        if len(patch) > 2000:
            patch = patch[:2000]
        files_out.append(
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": patch,
            }
        )
    return {
        "title": pr.title,
        "author": pr.user.login if pr.user else None,
        "files": files_out,
    }


def _github_create_repo_sync(owner: str, repo_name: str, description: str, private: bool) -> dict[str, Any]:
    g = _github_client()
    try:
        # Get current authenticated user for comparison
        current_user = g.get_user()
        
        # If owner is the current user, create in their account
        if current_user.login.lower() == owner.lower():
            repo = current_user.create_repo(
                name=repo_name,
                description=description,
                private=private,
                auto_init=True
            )
        else:
            # Otherwise try org
            org_obj = g.get_organization(owner)
            repo = org_obj.create_repo(
                name=repo_name,
                description=description,
                private=private,
                auto_init=True
            )
        
        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "url": repo.html_url,
            "clone_url": repo.clone_url,
        }
    except Exception as e:
        if "name already exists" in str(e).lower():
            try:
                current_user = g.get_user()
                if current_user.login.lower() == owner.lower():
                    repo = current_user.get_repo(repo_name)
                else:
                    repo = org_obj.get_repo(repo_name)
            except:
                pass
            return {
                "name": repo.name,
                "full_name": repo.full_name,
                "url": repo.html_url,
                "clone_url": repo.clone_url,
                "status": "already_exists",
            }
        raise


async def github_search_prs(query: str, repo: str = "", state: str = "open") -> dict[str, Any]:
    """
    Search GitHub pull requests.

    Pass ``repo`` as ``owner/name`` to scope results; ``state`` is ``open``, ``closed``,
    or ``all``. The ``query`` string is combined with ``is:pr`` (and repo/state filters)
    for the GitHub search API.
    """
    try:
        rows = await asyncio.to_thread(_github_search_prs_sync, query, repo, state)
        return slim_result(rows)
    except Exception as exc:  # noqa: BLE001 — tools must not raise
        return format_error("github_search_prs", exc)


async def github_get_pr_diff(owner: str, repo: str, pull_number: int) -> dict[str, Any]:
    """
    Fetch a pull request as structured file changes (up to 20 files).

    Each file entry includes a ``patch`` preview (first 2000 characters of the unified diff
    fragment returned by GitHub).
    """
    try:
        payload = await asyncio.to_thread(_github_get_pr_diff_sync, owner, repo, pull_number)
        return slim_result(payload)
    except Exception as exc:  # noqa: BLE001
        return format_error("github_get_pr_diff", exc)


async def github_create_repo(org: str, repo_name: str, description: str = "", private: bool = False) -> dict[str, Any]:
    """
    Create a GitHub repository in an organization.
    
    Returns repo details including URL and clone URL.
    If repo already exists, returns its details with status='already_exists'.
    """
    try:
        payload = await asyncio.to_thread(_github_create_repo_sync, org, repo_name, description, private)
        return slim_result(payload)
    except Exception as exc:  # noqa: BLE001
        return format_error("github_create_repo", exc)


def register_github_tools(mcp: "FastMCP") -> None:
    """Register GitHub tools on the FastMCP server."""
    mcp.tool(github_search_prs)
    mcp.tool(github_get_pr_diff)
    mcp.tool(github_create_repo)
    mcp.tool(github_create_repo)
