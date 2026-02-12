"""
AutoMinds Email Assistant - Configuration
All settings loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


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
    # Sonnet 4 for analysis, briefing, draft replies (~5x cheaper than Opus)
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 2048
    # Haiku 3.5 for simple/cheap tasks (spam detection, read-receipts, labeling)
    claude_fast_model: str = "claude-3-5-haiku-20241022"
    claude_fast_max_tokens: int = 512

    # --- Costs ---
    # Estimated cost per email processed (Sonnet = ~$0.008, Haiku = ~$0.002)
    estimated_cost_per_email_usd: float = 0.008

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()
