"""
AutoMinds Email Assistant - Main Server
FastAPI application with OAuth flows, email endpoints, and briefing generation.

Run: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import html
import json as _json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from models import (
    EmailProvider, EmailPriority, EmailCategory,
    BriefingRequest, DraftRequest, DraftApproval, SendRequest,
    AutoSendRuleRequest, HealthResponse, UserSettings,
    DraftStatus,
)
import user_store
import gmail_provider
import outlook_provider
import email_brain
import scheduler
import autonomous_agent
import knowledge_worker_ami

# ─── Logging ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("autominds-email")

# ─── App startup/shutdown ────────────────────────────────

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("AutoMinds Email Assistant starting up...")
    scheduler.start_scheduler()

    # Start the autonomous agent (hourly email scanner)
    if settings.agent_enabled:
        autonomous_agent.schedule_agent(interval_minutes=settings.agent_interval_minutes)
        logger.info(f"Autonomous agent enabled (every {settings.agent_interval_minutes} min)")

    # Re-schedule briefings for all existing users
    try:
        all_users = user_store.list_all_users()
    except Exception as e:
        logger.warning(f"Could not load users on startup (Supabase may be down): {e}")
        all_users = []
    for user in all_users:
        if user.connected_accounts:
            try:
                parts = user.settings.briefing_time.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                scheduler.schedule_user_briefing(
                    user.id, hour=hour, minute=minute,
                    timezone=user.settings.briefing_timezone,
                )
            except Exception as e:
                logger.warning(f"Failed to schedule briefing for {user.id}: {e}")

    logger.info("Ready to serve requests")
    yield
    logger.info("Shutting down...")
    scheduler.stop_scheduler()


# ─── Rate Limiter ────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

# ─── FastAPI App ─────────────────────────────────────────

app = FastAPI(
    title="AutoMinds Email Assistant",
    description="AI-powered email management — connect Gmail or Outlook, get daily briefings, draft replies.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://autominds.org",
        "https://www.autominds.org",
        "https://app.autominds.org",
        "https://autominds-email-production-8ed3.up.railway.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Session middleware (signed cookie) ──────────────────

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    session_cookie="autominds_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    same_site="lax",
    https_only=settings.app_env == "production",
)


# ─── Security headers middleware ─────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        # Block direct access to dashboard.html — force through auth gate
        if request.url.path == "/static/dashboard.html":
            from starlette.responses import RedirectResponse as SRedirect
            return SRedirect("/dashboard")

        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

from fastapi.staticfiles import StaticFiles
import pathlib
STATIC_DIR = pathlib.Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Draft store (Supabase-backed with in-memory fallback) ─

import draft_store


# ─── Health / Root ───────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint — lightweight, no external calls."""
    try:
        all_users = user_store.list_all_users()
        total_accounts = sum(len(u.connected_accounts) for u in all_users)
    except Exception:
        total_accounts = -1  # Supabase may be down
    return HealthResponse(
        status="ok",
        version="1.0.0",
        connected_accounts=total_accounts,
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Landing page — shows connect or dashboard."""
    dashboard_path = STATIC_DIR / "index.html"
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
    return RedirectResponse("/docs")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Protected dashboard — requires Google OAuth session."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/auth/google")

    # Verify the user still exists
    user = user_store.get_user(user_id)
    if not user:
        request.session.clear()
        return RedirectResponse("/auth/google")

    # Serve the dashboard HTML
    dashboard_path = STATIC_DIR / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=500, detail="Dashboard not found")
    return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════
# AUTH ROUTES — OAuth flows for Gmail and Outlook
# ══════════════════════════════════════════════════════════

@app.get("/auth/google")
async def auth_google():
    """Start the Google OAuth flow — redirects user to Google consent screen."""
    state = str(uuid.uuid4())[:8]
    auth_url = gmail_provider.get_google_auth_url(state=state)
    return RedirectResponse(auth_url)


@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str, state: str = ""):
    """Google OAuth callback — exchanges code for tokens, creates/updates user."""
    try:
        account = gmail_provider.exchange_google_code(code)

        # Find or create user
        user = user_store.get_user_by_email(account.email)
        if not user:
            user = user_store.create_user(email=account.email, name=account.display_name)

        # Add/update connected account
        user = user_store.add_connected_account(user.id, account)

        # Schedule daily briefing
        parts = user.settings.briefing_time.split(":")
        scheduler.schedule_user_briefing(
            user.id,
            hour=int(parts[0]),
            minute=int(parts[1]) if len(parts) > 1 else 0,
            timezone=user.settings.briefing_timezone,
        )

        logger.info(f"Gmail connected: {account.email} (user_id={user.id})")

        # Set server-side session (signed HttpOnly cookie)
        request.session["user_id"] = user.id
        request.session["email"] = account.email
        request.session["name"] = account.display_name or account.email

        # Redirect to dashboard — also set localStorage for UI display
        # Escape all user-controlled data to prevent XSS
        safe_id = html.escape(user.id, quote=True)
        safe_email = html.escape(account.email, quote=True)
        safe_name = html.escape(account.display_name or account.email, quote=True)
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html><head><title>Connected!</title>
        <script>
            localStorage.setItem('autominds_user_id', {_json.dumps(safe_id)});
            localStorage.setItem('autominds_email', {_json.dumps(safe_email)});
            localStorage.setItem('autominds_name', {_json.dumps(safe_name)});
            window.location.href = '/dashboard';
        </script>
        </head><body style="background:#0a0a0a;color:#e0e0e0;font-family:sans-serif;text-align:center;padding-top:100px;">
        <p>Connecting... redirecting to dashboard.</p>
        </body></html>
        """)

    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")


@app.get("/auth/microsoft")
async def auth_microsoft():
    """Start the Microsoft OAuth flow."""
    if not settings.ms_client_id:
        raise HTTPException(status_code=501, detail="Outlook integration not configured yet")

    state = str(uuid.uuid4())[:8]
    auth_url = outlook_provider.get_microsoft_auth_url(state=state)
    return RedirectResponse(auth_url)


@app.get("/auth/microsoft/callback")
async def auth_microsoft_callback(request: Request, code: str, state: str = ""):
    """Microsoft OAuth callback."""
    try:
        account = outlook_provider.exchange_microsoft_code(code)

        user = user_store.get_user_by_email(account.email)
        if not user:
            user = user_store.create_user(email=account.email, name=account.display_name)

        user = user_store.add_connected_account(user.id, account)

        parts = user.settings.briefing_time.split(":")
        scheduler.schedule_user_briefing(
            user.id,
            hour=int(parts[0]),
            minute=int(parts[1]) if len(parts) > 1 else 0,
            timezone=user.settings.briefing_timezone,
        )

        logger.info(f"Outlook connected: {account.email} (user_id={user.id})")

        # Set server-side session
        request.session["user_id"] = user.id
        request.session["email"] = account.email
        request.session["name"] = account.display_name or account.email

        # Redirect to protected dashboard
        # Escape all user-controlled data to prevent XSS
        safe_id = html.escape(user.id, quote=True)
        safe_email = html.escape(account.email, quote=True)
        safe_name = html.escape(account.display_name or account.email, quote=True)
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html><head><title>Connected!</title>
        <script>
            localStorage.setItem('autominds_user_id', {_json.dumps(safe_id)});
            localStorage.setItem('autominds_email', {_json.dumps(safe_email)});
            localStorage.setItem('autominds_name', {_json.dumps(safe_name)});
            window.location.href = '/dashboard';
        </script>
        </head><body style="background:#0a0a0a;color:#e0e0e0;font-family:sans-serif;text-align:center;padding-top:100px;">
        <p>Connecting... redirecting to dashboard.</p>
        </body></html>
        """)

    except Exception as e:
        logger.error(f"Microsoft OAuth callback error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")


@app.get("/auth/check")
async def auth_check(request: Request):
    """Check if user has a valid session."""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"authenticated": False}, status_code=401)
    user = user_store.get_user(user_id)
    if not user:
        request.session.clear()
        return JSONResponse({"authenticated": False}, status_code=401)
    return {
        "authenticated": True,
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
    }


@app.get("/auth/logout")
async def auth_logout(request: Request):
    """Clear session and redirect to landing page."""
    request.session.clear()
    return RedirectResponse("/")


# ══════════════════════════════════════════════════════════
# EMAIL ROUTES — Fetch, read, categorize
# ══════════════════════════════════════════════════════════

@app.get("/emails")
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def get_emails(
    request: Request,
    user_id: str,
    max_results: int = Query(default=20, le=50),
    unread_only: bool = True,
    analyze: bool = True,
):
    """Fetch emails for a user from all connected accounts.
    
    Set analyze=true (default) to get AI-powered priority, category, and summary for each email.
    """
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.connected_accounts:
        raise HTTPException(status_code=400, detail="No email accounts connected")

    all_emails = []

    for account in user.connected_accounts:
        if not account.is_active:
            continue

        if account.provider == EmailProvider.GMAIL:
            query = "is:unread" if unread_only else ""
            emails = gmail_provider.fetch_emails(account, query=query, max_results=max_results)
        elif account.provider == EmailProvider.OUTLOOK:
            emails = outlook_provider.fetch_emails(account, unread_only=unread_only, max_results=max_results)
        else:
            continue

        all_emails.extend(emails)

        # Update stored tokens if they were refreshed
        user_store.add_connected_account(user_id, account)

    # Sort by date, newest first
    all_emails.sort(key=lambda e: e.date, reverse=True)

    # Trim to max_results
    all_emails = all_emails[:max_results]

    # Analyze with Claude if requested
    if analyze and all_emails:
        all_emails = email_brain.analyze_emails(
            all_emails,
            vip_contacts=user.settings.vip_contacts,
        )

    return {
        "user_id": user_id,
        "count": len(all_emails),
        "emails": [e.model_dump() for e in all_emails],
    }


@app.get("/emails/{email_id}")
async def get_email(user_id: str, email_id: str):
    """Get a single email by ID."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for account in user.connected_accounts:
        if account.provider == EmailProvider.GMAIL:
            email = gmail_provider.fetch_email_by_id(account, email_id)
        elif account.provider == EmailProvider.OUTLOOK:
            email = outlook_provider.fetch_email_by_id(account, email_id)
        else:
            continue

        if email:
            return email.model_dump()

    raise HTTPException(status_code=404, detail="Email not found")


# ══════════════════════════════════════════════════════════
# BRIEFING ROUTES — Daily email briefing
# ══════════════════════════════════════════════════════════

@app.get("/briefing")
@limiter.limit("10/minute")
async def get_briefing(
    request: Request,
    user_id: str,
    max_emails: int = Query(default=25, le=50),
    force_new: bool = False,
):
    """Generate or retrieve the daily email briefing.
    
    If a briefing was already generated today, returns the cached version.
    Set force_new=true to regenerate.
    """
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.connected_accounts:
        raise HTTPException(status_code=400, detail="No email accounts connected")

    # Check for cached briefing
    if not force_new:
        cached = scheduler.get_latest_briefing(user_id)
        if cached:
            # Check if it's from today
            cached_date = cached.get("date", "")
            today = datetime.utcnow().strftime("%Y-%m-%d")
            if today in str(cached_date):
                return cached

    # Generate fresh briefing
    all_emails = []
    for account in user.connected_accounts:
        if not account.is_active:
            continue
        if account.provider == EmailProvider.GMAIL:
            emails = gmail_provider.fetch_emails(account, query="is:unread", max_results=max_emails)
        elif account.provider == EmailProvider.OUTLOOK:
            emails = outlook_provider.fetch_emails(account, unread_only=True, max_results=max_emails)
        else:
            continue
        all_emails.extend(emails)
        user_store.add_connected_account(user_id, account)

    if not all_emails:
        return {
            "user_id": user_id,
            "total_unread": 0,
            "full_text": "🎉 Inbox zero! No unread emails.",
            "emails_analyzed": 0,
        }

    # Analyze
    analyzed = email_brain.analyze_emails(all_emails, vip_contacts=user.settings.vip_contacts)

    # Generate briefing
    briefing = email_brain.generate_briefing(analyzed, user_name=user.name)
    briefing.user_id = user_id

    # Cache it
    scheduler._store_briefing(user_id, briefing)

    return briefing.model_dump()


# ══════════════════════════════════════════════════════════
# DRAFT ROUTES — AI draft replies
# ══════════════════════════════════════════════════════════

@app.post("/drafts")
@limiter.limit("10/minute")
async def create_draft(request: Request, user_id: str, draft_req: DraftRequest):
    """Generate an AI draft reply to an email.
    
    The draft is NOT sent automatically — user must approve it first.
    """
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find the original email
    original = None
    source_account = None
    for account in user.connected_accounts:
        if account.provider == EmailProvider.GMAIL:
            original = gmail_provider.fetch_email_by_id(account, draft_req.email_id)
        elif account.provider == EmailProvider.OUTLOOK:
            original = outlook_provider.fetch_email_by_id(account, draft_req.email_id)

        if original:
            source_account = account
            break

    if not original:
        raise HTTPException(status_code=404, detail="Original email not found")

    # Generate draft
    draft = email_brain.draft_reply(
        original_email=original,
        instructions=draft_req.instructions,
        tone=draft_req.tone,
        user_name=user.name,
    )

    # Check auto-send rules
    if original.sender.email.lower() in [c.lower() for c in user.settings.auto_send_contacts]:
        draft.status = DraftStatus.AUTO_SENT
        # Actually send it
        if source_account.provider == EmailProvider.GMAIL:
            gmail_provider.send_email(
                source_account, draft.to, draft.subject, draft.body,
                reply_to_id=original.id,
            )
        elif source_account.provider == EmailProvider.OUTLOOK:
            outlook_provider.send_email(
                source_account, draft.to, draft.subject, draft.body,
                reply_to_id=original.id,
            )
        logger.info(f"Auto-sent reply to {draft.to} (auto-send rule)")

    # Store the draft (Supabase or in-memory)
    draft_store.save_draft(
        draft_id=draft.id,
        draft_data=draft.model_dump(),
        user_id=user_id,
        source_provider=source_account.provider.value,
        source_email=source_account.email,
    )

    return {
        "draft": draft.model_dump(),
        "auto_sent": draft.status == DraftStatus.AUTO_SENT,
        "message": "Draft auto-sent (auto-send enabled for this contact)"
                   if draft.status == DraftStatus.AUTO_SENT
                   else "Draft created — review and approve to send.",
    }


@app.get("/drafts")
async def list_drafts(user_id: str):
    """List all pending drafts for a user."""
    user_drafts = draft_store.list_user_drafts(user_id)
    return {"user_id": user_id, "count": len(user_drafts), "drafts": user_drafts}


@app.post("/drafts/{draft_id}/approve")
async def approve_draft(user_id: str, draft_id: str, edited_body: Optional[str] = None):
    """Approve and send a draft reply.
    
    Optionally provide edited_body to modify the draft before sending.
    """
    draft_data = draft_store.get_draft(draft_id)
    if not draft_data:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft_data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft")

    draft = draft_data["draft"]
    body = edited_body or draft["body"]

    # Find the source account
    user = user_store.get_user(user_id)
    source_account = None
    for account in user.connected_accounts:
        if account.email == draft_data["source_email"]:
            source_account = account
            break

    if not source_account:
        raise HTTPException(status_code=400, detail="Source email account not found")

    # Send the email
    success = False
    if source_account.provider == EmailProvider.GMAIL:
        success = gmail_provider.send_email(
            source_account, draft["to"], draft["subject"], body,
            reply_to_id=draft["original_email_id"],
        )
    elif source_account.provider == EmailProvider.OUTLOOK:
        success = outlook_provider.send_email(
            source_account, draft["to"], draft["subject"], body,
            reply_to_id=draft["original_email_id"],
        )

    if success:
        draft_store.update_draft_status(draft_id, DraftStatus.SENT.value)
        return {"status": "sent", "to": draft["to"], "subject": draft["subject"]}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")


@app.post("/drafts/{draft_id}/reject")
async def reject_draft(user_id: str, draft_id: str):
    """Reject/discard a draft."""
    draft_data = draft_store.get_draft(draft_id)
    if not draft_data:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft_data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft")

    draft_store.update_draft_status(draft_id, DraftStatus.REJECTED.value)
    return {"status": "rejected", "draft_id": draft_id}


# ══════════════════════════════════════════════════════════
# SEND ROUTE — Direct email sending
# ══════════════════════════════════════════════════════════

@app.post("/send")
@limiter.limit("10/minute")
async def send_email_route(request: Request, user_id: str, send_req: SendRequest):
    """Send a new email (not a reply)."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.connected_accounts:
        raise HTTPException(status_code=400, detail="No email accounts connected")

    # Use the first active account
    account = next((a for a in user.connected_accounts if a.is_active), None)
    if not account:
        raise HTTPException(status_code=400, detail="No active email account")

    if account.provider == EmailProvider.GMAIL:
        success = gmail_provider.send_email(
            account, send_req.to, send_req.subject, send_req.body,
            reply_to_id=send_req.reply_to_id,
        )
    elif account.provider == EmailProvider.OUTLOOK:
        success = outlook_provider.send_email(
            account, send_req.to, send_req.subject, send_req.body,
            reply_to_id=send_req.reply_to_id,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {account.provider}")

    if success:
        return {"status": "sent", "to": send_req.to, "subject": send_req.subject}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")


# ══════════════════════════════════════════════════════════
# USER SETTINGS ROUTES
# ══════════════════════════════════════════════════════════

@app.get("/user")
async def get_user_info(user_id: str):
    """Get user info and settings."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "tier": user.tier,
        "connected_accounts": [
            {
                "provider": a.provider.value,
                "email": a.email,
                "display_name": a.display_name,
                "is_active": a.is_active,
                "connected_at": str(a.connected_at),
            }
            for a in user.connected_accounts
        ],
        "settings": user.settings.model_dump(),
        "created_at": str(user.created_at),
    }


@app.put("/user/settings")
async def update_settings(user_id: str, new_settings: UserSettings):
    """Update user settings (VIP contacts, briefing time, tone, etc.)."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user = user_store.update_user_settings(user_id, new_settings)

    # Reschedule briefing with new time
    parts = new_settings.briefing_time.split(":")
    scheduler.schedule_user_briefing(
        user_id,
        hour=int(parts[0]),
        minute=int(parts[1]) if len(parts) > 1 else 0,
        timezone=new_settings.briefing_timezone,
    )

    return {"status": "updated", "settings": user.settings.model_dump()}


@app.post("/user/vip")
async def add_vip_contact(user_id: str, contact_email: str):
    """Add a VIP contact (always treated as high priority)."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if contact_email not in user.settings.vip_contacts:
        user.settings.vip_contacts.append(contact_email)
        user_store.save_user(user)

    return {"vip_contacts": user.settings.vip_contacts}


@app.delete("/user/vip")
async def remove_vip_contact(user_id: str, contact_email: str):
    """Remove a VIP contact."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.settings.vip_contacts = [
        c for c in user.settings.vip_contacts if c.lower() != contact_email.lower()
    ]
    user_store.save_user(user)

    return {"vip_contacts": user.settings.vip_contacts}


@app.post("/user/auto-send")
async def update_auto_send(user_id: str, rule: AutoSendRuleRequest):
    """Enable or disable auto-send for a specific contact.
    
    When auto-send is enabled for a contact, AI-drafted replies are sent
    immediately without requiring manual approval.
    """
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if rule.enabled:
        if rule.contact_email not in user.settings.auto_send_contacts:
            user.settings.auto_send_contacts.append(rule.contact_email)
    else:
        user.settings.auto_send_contacts = [
            c for c in user.settings.auto_send_contacts
            if c.lower() != rule.contact_email.lower()
        ]

    user_store.save_user(user)

    return {
        "auto_send_contacts": user.settings.auto_send_contacts,
        "message": f"Auto-send {'enabled' if rule.enabled else 'disabled'} for {rule.contact_email}",
    }


# ══════════════════════════════════════════════════════════
# ADMIN / DEBUG ROUTES (API key protected)
# ══════════════════════════════════════════════════════════

from fastapi.security import APIKeyHeader

_admin_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def _require_admin_key(api_key: str = Depends(_admin_api_key_header)):
    """Dependency that validates the admin API key on protected routes."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="Admin routes disabled — set ADMIN_API_KEY env var on server",
        )
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return True


@app.get("/admin/users", dependencies=[Depends(_require_admin_key)])
async def admin_list_users():
    """List all users (admin endpoint)."""
    users = user_store.list_all_users()
    return {
        "count": len(users),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "tier": u.tier,
                "accounts": len(u.connected_accounts),
                "created_at": str(u.created_at),
            }
            for u in users
        ],
    }


@app.get("/admin/scheduler", dependencies=[Depends(_require_admin_key)])
async def admin_scheduler_status():
    """Check scheduler status and list scheduled jobs."""
    return {
        "jobs": scheduler.list_scheduled_jobs(),
    }


# ══════════════════════════════════════════════════════════
# EMAIL ACTIONS — Mark read, label, etc.
# ══════════════════════════════════════════════════════════

@app.post("/emails/{email_id}/read")
async def mark_email_read(user_id: str, email_id: str):
    """Mark an email as read."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for account in user.connected_accounts:
        if account.provider == EmailProvider.GMAIL:
            success = gmail_provider.mark_as_read(account, email_id)
            if success:
                return {"status": "marked_read", "email_id": email_id}
        elif account.provider == EmailProvider.OUTLOOK:
            success = outlook_provider.mark_as_read(account, email_id)
            if success:
                return {"status": "marked_read", "email_id": email_id}

    raise HTTPException(status_code=404, detail="Email not found or couldn't mark as read")


@app.post("/emails/{email_id}/label")
async def label_email(user_id: str, email_id: str, label: str):
    """Add a label/category to an email (Gmail only for now)."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for account in user.connected_accounts:
        if account.provider == EmailProvider.GMAIL:
            success = gmail_provider.add_label(account, email_id, label)
            if success:
                return {"status": "labeled", "email_id": email_id, "label": label}

    raise HTTPException(status_code=400, detail="Labeling only supported for Gmail accounts")


# ══════════════════════════════════════════════════════════
# GOOGLE TASKS — Create / list / complete tasks from emails
# ══════════════════════════════════════════════════════════

import google_tasks_provider
import google_contacts_provider


@app.get("/tasks")
async def list_tasks(user_id: str):
    """List pending Google Tasks created from emails."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gmail_account = _get_gmail_account(user)
    if not gmail_account:
        raise HTTPException(status_code=400, detail="No Gmail connected — Tasks require Gmail OAuth")

    tasks = google_tasks_provider.list_pending_tasks(gmail_account)
    return {"tasks": tasks, "count": len(tasks)}


@app.post("/tasks/from-email")
async def create_task_from_email(
    user_id: str,
    email_id: str,
    title: str,
    notes: str = "",
    due_date: str | None = None,
):
    """Create a Google Task from an email — the agent does this automatically but users can trigger manually."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gmail_account = _get_gmail_account(user)
    if not gmail_account:
        raise HTTPException(status_code=400, detail="No Gmail connected")

    task = google_tasks_provider.create_task_from_email(
        account=gmail_account,
        title=title,
        notes=notes,
        due_date=due_date,
        email_id=email_id,
    )
    if task:
        return {"status": "created", "task": task}
    raise HTTPException(status_code=500, detail="Failed to create task")


@app.post("/tasks/{task_id}/complete")
async def complete_task(user_id: str, task_id: str):
    """Mark a Google Task as completed."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gmail_account = _get_gmail_account(user)
    if not gmail_account:
        raise HTTPException(status_code=400, detail="No Gmail connected")

    success = google_tasks_provider.complete_task(gmail_account, task_id)
    if success:
        return {"status": "completed", "task_id": task_id}
    raise HTTPException(status_code=500, detail="Failed to complete task")


# ══════════════════════════════════════════════════════════
# CONTACTS — CRM-style lookup
# ══════════════════════════════════════════════════════════

@app.get("/contacts/{email}")
async def lookup_contact(user_id: str, email: str):
    """Look up a contact by email address — CRM-style enrichment."""
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gmail_account = _get_gmail_account(user)
    if not gmail_account:
        raise HTTPException(status_code=400, detail="No Gmail connected")

    contact = google_contacts_provider.lookup_contact(gmail_account, email)
    if contact:
        return {"contact": contact, "found": True}
    return {"contact": None, "found": False, "email": email}


# ══════════════════════════════════════════════════════════
# AUTONOMOUS AGENT — Status & manual trigger
# ══════════════════════════════════════════════════════════

@app.get("/agent/status")
async def agent_status():
    """Get the autonomous agent's current status and recent run history."""
    return {
        "enabled": settings.agent_enabled,
        "interval_minutes": settings.agent_interval_minutes,
        "status": autonomous_agent.get_agent_status(),
    }


@app.post("/agent/run-now")
@limiter.limit("5/minute")
async def agent_run_now(request: Request, user_id: str | None = None):
    """Trigger an immediate agent cycle — runs for one user or all users."""
    if user_id:
        user = user_store.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        result = await autonomous_agent.run_agent_for_user(user_id)
        return {"status": "completed", "user_id": user_id, "result": result}
    else:
        results = await autonomous_agent.run_agent_for_all_users()
        return {"status": "completed", "users_processed": len(results), "results": results}


# ══════════════════════════════════════════════════════════
# HELPER — Get Gmail account from user
# ══════════════════════════════════════════════════════════

def _get_gmail_account(user):
    """Extract the Gmail connected account from a user, or None."""
    for account in user.connected_accounts:
        if account.provider == EmailProvider.GMAIL:
            return account
    return None


# ══════════════════════════════════════════════════════════
# AMI ROUTES — Knowledge Worker (RAG)
# ══════════════════════════════════════════════════════════

class KnowledgeSyncRequest(BaseModel):
    user_id: str
    folder_id: str

class KnowledgeQueryRequest(BaseModel):
    user_id: str
    question: str
    persona: Optional[str] = None


@app.post("/ami/knowledge/sync")
async def knowledge_sync(req: KnowledgeSyncRequest):
    """Sync a Google Drive folder into the user's RAG knowledge base."""
    result = knowledge_worker_ami.sync_user_drive_folder(req.user_id, req.folder_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Sync failed"))
    return result


@app.post("/ami/knowledge/query")
async def knowledge_query(req: KnowledgeQueryRequest):
    """Ask a question to the user's personal knowledge base."""
    result = knowledge_worker_ami.ask_knowledge_base(req.user_id, req.question, req.persona)
    return result


@app.get("/ami/knowledge/status/{user_id}")
async def knowledge_status(user_id: str):
    """Check if a user has an active knowledge base."""
    import os
    from rag_engine_skill import _get_store_path
    path = _get_store_path(user_id)
    has_kb = path.exists()
    return {"user_id": user_id, "has_knowledge_base": has_kb}


# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development"),
    )
