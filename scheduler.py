"""
AutoMinds Email Assistant - Scheduler
Handles automated daily briefings and periodic email checking.
Uses APScheduler for task scheduling.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Optional

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler():
    """Start the background scheduler."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


async def process_daily_briefing(user_id: str):
    """Generate and send a daily briefing for a user.
    
    This is called by the scheduler at the user's configured briefing time.
    It:
    1. Fetches unread emails from all connected accounts
    2. Analyzes them with Claude
    3. Generates a briefing
    4. Sends the briefing via the user's preferred channel
    """
    from user_store import get_user, get_connected_account
    from gmail_provider import fetch_emails as gmail_fetch
    from outlook_provider import fetch_emails as outlook_fetch
    from email_brain import analyze_emails, generate_briefing
    from models import EmailProvider
    
    logger.info(f"Generating daily briefing for user {user_id}")
    
    try:
        user = get_user(user_id)
        if not user:
            logger.error(f"User {user_id} not found for briefing")
            return
        
        all_emails = []
        
        # Fetch from all connected accounts
        for account in user.connected_accounts:
            if not account.is_active:
                continue
            
            if account.provider == EmailProvider.GMAIL:
                emails = gmail_fetch(account, query="is:unread", max_results=25)
            elif account.provider == EmailProvider.OUTLOOK:
                emails = outlook_fetch(account, unread_only=True, max_results=25)
            else:
                continue
            
            all_emails.extend(emails)
        
        if not all_emails:
            logger.info(f"No unread emails for user {user_id} — skipping briefing")
            return
        
        # Analyze emails
        analyzed = analyze_emails(all_emails, vip_contacts=user.settings.vip_contacts)
        
        # Generate briefing
        briefing = generate_briefing(
            analyzed,
            user_name=user.name,
        )
        briefing.user_id = user_id
        
        # Log the briefing (in production, this would send via email/telegram/sms)
        logger.info(
            f"Briefing generated for {user_id}: "
            f"{briefing.total_unread} emails, "
            f"{briefing.urgent_count} urgent, "
            f"cost=${briefing.estimated_cost_usd:.3f}"
        )
        
        # Store the briefing for later retrieval via API
        _store_briefing(user_id, briefing)
        
        return briefing
        
    except Exception as e:
        logger.error(f"Error generating briefing for {user_id}: {e}", exc_info=True)
        return None


def schedule_user_briefing(user_id: str, hour: int = 7, minute: int = 0, timezone: str = "America/New_York"):
    """Schedule a daily briefing for a user.
    
    Args:
        user_id: The user's ID.
        hour: Hour to send the briefing (24h format).
        minute: Minute to send the briefing.
        timezone: User's timezone.
    """
    scheduler = get_scheduler()
    job_id = f"briefing_{user_id}"
    
    # Remove existing job if any
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)
    
    scheduler.add_job(
        process_daily_briefing,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        args=[user_id],
        id=job_id,
        name=f"Daily briefing for {user_id}",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace period
    )
    
    logger.info(f"Scheduled daily briefing for {user_id} at {hour:02d}:{minute:02d} {timezone}")


def unschedule_user_briefing(user_id: str):
    """Remove a user's scheduled briefing."""
    scheduler = get_scheduler()
    job_id = f"briefing_{user_id}"
    
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)
        logger.info(f"Removed briefing schedule for {user_id}")


def list_scheduled_jobs() -> list[dict]:
    """List all scheduled jobs (for admin/debugging)."""
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs


# ─── Briefing Storage (simple file-based) ────────────────

import json
import os

BRIEFINGS_DIR = os.path.join(os.path.dirname(__file__), "data", "briefings")


def _store_briefing(user_id: str, briefing):
    """Store a briefing for later retrieval."""
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(BRIEFINGS_DIR, f"{user_id}_{date_str}.json")
    
    with open(filepath, "w") as f:
        json.dump(briefing.model_dump(), f, indent=2, default=str)


def get_latest_briefing(user_id: str) -> Optional[dict]:
    """Get the most recent briefing for a user."""
    if not os.path.exists(BRIEFINGS_DIR):
        return None
    
    # Find all briefings for this user, sorted by date
    files = sorted(
        [f for f in os.listdir(BRIEFINGS_DIR) if f.startswith(user_id)],
        reverse=True,
    )
    
    if not files:
        return None
    
    filepath = os.path.join(BRIEFINGS_DIR, files[0])
    with open(filepath, "r") as f:
        return json.load(f)
