"""
Application configuration (Chapter 3 — Neuron guide).

Loads from `neuron-mcp-server/.env` when present, else from process environment.
See https://srimaan.github.io/neuron-guide/03-first-mcp-server.html
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP server bind address, auth, integrations, and logging."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MCP HTTP (guide default port 8001)
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001
    mcp_auth_token: str = ""

    github_token: str = ""
    github_service_user: str = ""
    jira_domain: str = ""
    jira_user: str = ""
    jira_api_token: str = ""
    jira_ssl_trust_store: str = ""
    jira_ssl_insecure_skip_tls_verify: bool = False
    slack_bot_token: str = ""

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (cleared in tests via `get_settings.cache_clear()`)."""
    return Settings()
