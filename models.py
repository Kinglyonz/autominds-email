"""
AutoMinds Email Assistant - Data Models
Pydantic models for emails, users, briefings, and API responses.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ─── Enums ───────────────────────────────────────────────

class EmailProvider(str, Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"


class EmailPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class EmailCategory(str, Enum):
    ACTION_REQUIRED = "action_required"
    WAITING_ON = "waiting_on"
    FYI = "fyi"
    NEWSLETTER = "newsletter"
    PROMOTIONAL = "promotional"
    PERSONAL = "personal"
    SPAM = "spam"


class DraftStatus(str, Enum):
    PENDING = "pending"       # AI drafted, waiting for user review
    APPROVED = "approved"     # User approved, ready to send
    SENT = "sent"             # Sent
    REJECTED = "rejected"     # User rejected the draft
    AUTO_SENT = "auto_sent"   # Auto-sent (user opted in for this contact)


# ─── Core Models ─────────────────────────────────────────

class EmailAddress(BaseModel):
    """Parsed email address."""
    name: str = ""
    email: str


class EmailMessage(BaseModel):
    """A normalized email message (works for both Gmail and Outlook)."""
    id: str
    thread_id: Optional[str] = None
    provider: EmailProvider
    subject: str = "(No Subject)"
    sender: EmailAddress
    to: list[EmailAddress] = []
    cc: list[EmailAddress] = []
    date: datetime
    body_text: str = ""
    body_html: str = ""
    snippet: str = ""
    is_unread: bool = True
    labels: list[str] = []
    has_attachments: bool = False
    attachment_names: list[str] = []

    # AI-generated fields (populated after analysis)
    priority: Optional[EmailPriority] = None
    category: Optional[EmailCategory] = None
    summary: Optional[str] = None
    suggested_action: Optional[str] = None
    is_vip: bool = False


class EmailDraft(BaseModel):
    """An AI-generated draft reply."""
    id: str = ""
    original_email_id: str
    to: str
    subject: str
    body: str
    status: DraftStatus = DraftStatus.PENDING
    instructions: str = ""  # What the user asked the AI to write
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Safety guardrail results (from evaluator-optimizer pattern)
    safety_flags: list[str] = Field(default_factory=list)
    safety_severity: str = "none"  # none | low | medium | high


class DailyBriefing(BaseModel):
    """The daily email briefing sent to the user."""
    user_id: str
    date: datetime = Field(default_factory=datetime.utcnow)
    total_unread: int = 0
    urgent_count: int = 0
    action_required_count: int = 0

    # The briefing content sections
    greeting: str = ""
    urgent_summary: str = ""
    action_items: str = ""
    fyi_summary: str = ""
    newsletter_summary: str = ""
    recommended_actions: str = ""

    # Full rendered text
    full_text: str = ""

    # Metadata
    emails_analyzed: int = 0
    processing_time_seconds: float = 0.0
    estimated_cost_usd: float = 0.0


# ─── User Models ─────────────────────────────────────────

class UserSettings(BaseModel):
    """Per-user configuration."""
    briefing_time: str = "07:00"  # When to send daily briefing (HH:MM)
    briefing_timezone: str = "America/New_York"
    vip_contacts: list[str] = []  # Email addresses that are always high priority
    auto_send_contacts: list[str] = []  # Contacts where auto-send is enabled
    categories_enabled: bool = True
    draft_tone: str = "professional"  # professional | casual | formal
    notification_channel: str = "email"  # email | telegram | sms


class ConnectedAccount(BaseModel):
    """A connected email account (Gmail or Outlook)."""
    provider: EmailProvider
    email: str
    display_name: str = ""
    access_token: str
    refresh_token: str
    token_expiry: Optional[datetime] = None
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class User(BaseModel):
    """A user of the email assistant."""
    id: str
    email: str
    name: str = ""
    connected_accounts: list[ConnectedAccount] = []
    settings: UserSettings = UserSettings()
    tier: str = "free"  # free | pro | business
    stripe_customer_id: Optional[str] = None
    subscription_id: Optional[str] = None
    plan_expires_at: Optional[datetime] = None
    actions_used: int = 0
    actions_reset_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: Optional[datetime] = None


# ─── API Request/Response Models ─────────────────────────

class BriefingRequest(BaseModel):
    """Request to generate a briefing."""
    max_emails: int = 25
    include_read: bool = False


class DraftRequest(BaseModel):
    """Request to draft a reply."""
    email_id: str
    instructions: str = "Write a professional reply"
    tone: str = "professional"


class DraftApproval(BaseModel):
    """Request to approve/reject a draft."""
    draft_id: str
    action: str  # "approve" | "reject" | "edit"
    edited_body: Optional[str] = None


class SendRequest(BaseModel):
    """Request to send an email."""
    to: str
    subject: str
    body: str
    reply_to_id: Optional[str] = None


class AutoSendRuleRequest(BaseModel):
    """Request to add/remove auto-send rules."""
    contact_email: str
    enabled: bool


class HealthResponse(BaseModel):
    """Server health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    connected_accounts: int = 0
    uptime_seconds: float = 0.0
