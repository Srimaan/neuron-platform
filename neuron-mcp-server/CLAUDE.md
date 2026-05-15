# neuron-mcp-server — AI assistant instructions

Neuron’s **MCP tool registry**: a Python 3.11+ **FastMCP** server exposing **five** tools (GitHub ×2, Jira ×2, Slack ×1) for agent workflows. Official walkthrough: [Chapter 3 — Your First MCP Server](https://srimaan.github.io/neuron-guide/03-first-mcp-server.html).

## Stack

- **FastMCP** (`@mcp.tool` / `mcp.tool(fn)`) — type hints + docstrings become MCP schemas.
- **PyGithub**, **`jira`**, **slack-sdk** — integrations (blocking calls wrapped with `asyncio.to_thread`).
- **Pydantic Settings** — `mcp_server/config.py` + `.env`.
- **pytest**, **pytest-asyncio**, **ruff** — dev.

## Add a new tool (pattern)

1. Pick a module under `mcp_server/tools/` (or create one) and define an **`async def`** with a **clear docstring** and **annotated parameters**.
2. Wrap the body in `try` / `except Exception` → return **`format_error("tool_name", exc)`** (never raise from tools).
3. On success, return **`slim_result(payload)`** whenever the payload is or contains lists/large dicts/strings.
4. Register with **`mcp.tool(your_function)`** inside that file’s **`register_*_tools(mcp)`**.
5. Call your `register_*_tools` from `mcp_server/tools/__init__.py` (`register_all_tools`).

Example shape:

```python
async def my_tool(foo: str) -> dict[str, Any]:
    \"\"\"One-line what it does; when the AI should use it.\"\"\"
    try:
        data = await asyncio.to_thread(blocking_call, foo)
        return slim_result(data)
    except Exception as exc:  # noqa: BLE001
        return format_error("my_tool", exc)
```

## `slim_result()` — when to use

Apply **`slim_result`** to **every** tool response that can grow without bound (search hits, file lists, API blobs). It caps list length, truncates long strings, strips nulls, and sets **`_truncated`** when anything was cut—protecting the model context window (see guide Figure 3.3).

## Conventions

- Tools are **`async`**; blocking SDKs run in **`asyncio.to_thread`**.
- **Docstrings** and **type hints** are required (they drive MCP `description` + JSON Schema).
- **Never raise** from tool entrypoints—return **`format_error`** instead.
- Keep **`main.py`** thin: construct `FastMCP`, register tools, optional `/health`, run.

## Run the server

From `neuron-mcp-server/`:

```bash
uv sync --extra dev
uv run python -m mcp_server.main
```

- Default: **HTTP** on **`0.0.0.0:8001`** (`GET /health`, MCP on `/mcp`).
- **Claude Desktop / stdio**: `TRANSPORT=stdio uv run python -m mcp_server.main`

## Tests

```bash
uv run pytest tests/ -v
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TRANSPORT` | Set to `stdio` for stdio; omit for HTTP. |
| `MCP_HOST` | Bind address (default `0.0.0.0`). |
| `MCP_PORT` | Port (default `8001`). |
| `MCP_AUTH_TOKEN` | If set, require `Authorization: Bearer …` on MCP routes (`/health` exempt). |
| `GITHUB_TOKEN` | GitHub PAT (`repo`, `read:org` as needed). |
| `JIRA_DOMAIN` | e.g. `yourcompany.atlassian.net` (no `https://`). |
| `JIRA_USER` | Jira login email. |
| `JIRA_API_TOKEN` | Atlassian API token. |
| `SLACK_BOT_TOKEN` | Bot token (`xoxb-…`). |
| `LOG_LEVEL` | e.g. `INFO`, `DEBUG`. |

Copy `.env.example` → `.env` and fill values locally (never commit `.env`).
