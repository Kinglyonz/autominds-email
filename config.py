"""
AutoMinds Email Assistant - Configuration
All settings loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os
import logging

_config_logger = logging.getLogger("autominds.config")


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    # --- Core ---
    app_secret_key: str = "dev-secret-change-in-production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"  # development | staging | production

    # --- Anthropic (Claude) ---
    anthropic_api_key: str = ""

    # --- Google OAuth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # --- Microsoft OAuth ---
    ms_client_id: Optional[str] = None
    ms_client_secret: Optional[str] = None
    ms_tenant_id: str = "common"
    ms_redirect_uri: str = "http://localhost:8000/auth/microsoft/callback"

    # --- Supabase ---
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None

    # --- Stripe ---
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None

    # --- Gmail API Scopes ---
    gmail_scopes: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/tasks",
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    # --- Autonomous Agent ---
    agent_interval_minutes: int = 60  # How often the agent scans (default: every hour)
    agent_enabled: bool = True        # Set False to disable the autonomous agent

    # --- Microsoft Graph Scopes ---
    ms_scopes: list[str] = [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/User.Read",
    ]

    # --- Email Processing ---
    max_emails_per_fetch: int = 50
    max_email_body_chars: int = 1500  # Truncate body to control Claude costs
    briefing_max_emails: int = 15

    # --- Claude Models (hybrid routing) ---
    # Sonnet 4 for analysis, briefing, draft replies
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 2048
    # Haiku 4.5 for simple/cheap tasks (spam detection, read-receipts, labeling)
    claude_fast_model: str = "claude-haiku-4-5-20251001"
    claude_fast_max_tokens: int = 512

    # --- Costs ---
    # Estimated cost per email processed (Sonnet = ~$0.008, Haiku = ~$0.002)
    estimated_cost_per_email_usd: float = 0.008

    # --- Admin ---
    admin_api_key: str = ""  # Set ADMIN_API_KEY env var to protect /admin routes

    # --- Rate Limiting ---
    rate_limit_per_minute: int = 30  # Max requests per minute per IP

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()

# Startup security warnings
if settings.app_secret_key == "dev-secret-change-in-production":
    _config_logger.warning(
        "\u26a0\ufe0f  APP_SECRET_KEY is using the default dev value! "
        "Set APP_SECRET_KEY env var in production to prevent session forgery."
    )
if not settings.admin_api_key:
    _config_logger.warning(
        "\u26a0\ufe0f  ADMIN_API_KEY is not set! Admin routes (/admin/*) will reject all requests. "
        "Set ADMIN_API_KEY env var to enable admin access."
    )
