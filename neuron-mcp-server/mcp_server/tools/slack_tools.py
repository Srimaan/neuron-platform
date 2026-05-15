"""Slack MCP tools (slack-sdk) — Chapter 3 Neuron guide."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from slack_sdk import WebClient

from mcp_server.config import get_settings
from mcp_server.utils import format_error, slim_result

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _slack_send_sync(channel: str, text: str, thread_ts: str) -> dict[str, Any]:
    token = get_settings().slack_bot_token
    if not token:
        raise ValueError("SLACK_BOT_TOKEN is not set")
    client = WebClient(token=token)
    kwargs: dict[str, str] = {"channel": channel, "text": text}
    if thread_ts.strip():
        kwargs["thread_ts"] = thread_ts.strip()
    resp = client.chat_postMessage(**kwargs)
    if not resp.get("ok"):
        raise RuntimeError(str(resp.get("error", resp)))
    return {
        "message_ts": resp.get("ts"),
        "channel": resp.get("channel"),
        "text": text,
    }


async def slack_send_message(channel: str, text: str, thread_ts: str = "") -> dict[str, Any]:
    """
    Post ``text`` to a Slack channel (name or ID). Use ``thread_ts`` to reply in a thread.
    """
    try:
        payload = await asyncio.to_thread(_slack_send_sync, channel, text, thread_ts)
        return slim_result(payload)
    except Exception as exc:  # noqa: BLE001
        return format_error("slack_send_message", exc)


def register_slack_tools(mcp: "FastMCP") -> None:
    """Register Slack tools on the FastMCP server."""
    mcp.tool(slack_send_message)
