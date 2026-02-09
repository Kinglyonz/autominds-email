"""
AutoMinds Email Assistant - Google Tasks Provider
Integrates with Google Tasks API to create tasks and reminders from emails.

Required scope: https://www.googleapis.com/auth/tasks
(Add to gmail_scopes in config.py to request during OAuth consent)
"""

import logging
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

from config import settings
from models import ConnectedAccount

logger = logging.getLogger(__name__)

# Module-level cache: email -> task_list_id
_task_list_cache: dict[str, str] = {}


# ─── Tasks Service Builder ──────────────────────────────

def _build_tasks_service(account: ConnectedAccount):
    """Build an authenticated Google Tasks API service from a ConnectedAccount.

    Reuses the same OAuth tokens as Gmail — Tasks API is part of Google
    Workspace and shares the same credential set.  Automatically refreshes
    the token if expired.
    """
    creds = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        # Keep the stored tokens up-to-date
        account.access_token = creds.token
        account.token_expiry = creds.expiry

    return build("tasks", "v1", credentials=creds)


# ─── Task List Management ───────────────────────────────

def list_task_lists(account: ConnectedAccount) -> list[dict]:
    """List all task lists for the account.

    Returns:
        A list of dicts with keys ``id``, ``title``, and ``updated``.
    """
    try:
        service = _build_tasks_service(account)
        result = service.tasklists().list().execute()
        return [
            {"id": tl["id"], "title": tl["title"], "updated": tl.get("updated", "")}
            for tl in result.get("items", [])
        ]
    except Exception as e:
        logger.error(f"Failed to list task lists: {e}")
        return []


def get_or_create_task_list(
    account: ConnectedAccount,
    title: str = "AutoMinds Email Actions",
) -> str:
    """Get (or create) a task list by name and return its ID.

    A dedicated *AutoMinds Email Actions* list is created the first time so
    email-derived tasks stay separate from the user's personal lists.

    The result is cached per-account so subsequent calls avoid extra API
    round-trips.
    """
    cache_key = f"{account.email}:{title}"
    if cache_key in _task_list_cache:
        return _task_list_cache[cache_key]

    try:
        service = _build_tasks_service(account)

        # Check existing lists
        result = service.tasklists().list().execute()
        for tl in result.get("items", []):
            if tl["title"] == title:
                _task_list_cache[cache_key] = tl["id"]
                return tl["id"]

        # Not found — create it
        new_list = service.tasklists().insert(body={"title": title}).execute()
        _task_list_cache[cache_key] = new_list["id"]
        logger.info(f"Created task list '{title}' ({new_list['id']}) for {account.email}")
        return new_list["id"]

    except Exception as e:
        logger.error(f"Failed to get/create task list '{title}': {e}")
        return ""


# ─── Task CRUD ───────────────────────────────────────────

def create_task_from_email(
    account: ConnectedAccount,
    title: str,
    notes: str = "",
    due_date: Optional[str] = None,
    email_id: Optional[str] = None,
    email_subject: Optional[str] = None,
    sender: Optional[str] = None,
    task_list_id: Optional[str] = None,
) -> dict:
    """Create a Google Task derived from an email.

    Args:
        title: Brief action description (e.g. "Reply to John about Q4 report").
        notes: Extra context to append after the auto-generated header.
        due_date: RFC 3339 date string, e.g. ``"2026-02-10T00:00:00.000Z"``.
        email_id: The Gmail message ID for back-linking.
        email_subject: Original email subject line.
        sender: Display name / address of the sender.
        task_list_id: Target task list.  Defaults to the AutoMinds list.

    Returns:
        The created task dict (``id``, ``title``, ``status``, …) or ``{}``
        on failure.
    """
    try:
        if not task_list_id:
            task_list_id = get_or_create_task_list(account)
            if not task_list_id:
                logger.error("Cannot create task — no task list available")
                return {}

        # Build rich notes with email context
        note_lines: list[str] = []
        if sender:
            note_lines.append(f"📧 From: {sender}")
        if email_subject:
            note_lines.append(f"📌 Subject: {email_subject}")
        if email_id:
            note_lines.append(f"🔗 Email ID: {email_id}")
        if note_lines:
            note_lines.append("")  # blank separator
        if notes:
            note_lines.append(notes)

        task_body: dict = {
            "title": title,
            "notes": "\n".join(note_lines),
            "status": "needsAction",
        }
        if due_date:
            task_body["due"] = due_date

        service = _build_tasks_service(account)
        created = (
            service.tasks()
            .insert(tasklist=task_list_id, body=task_body)
            .execute()
        )
        logger.info(f"Created task '{title}' ({created['id']}) in list {task_list_id}")
        return created

    except Exception as e:
        logger.error(f"Failed to create task '{title}': {e}")
        return {}


def complete_task(
    account: ConnectedAccount,
    task_id: str,
    task_list_id: Optional[str] = None,
) -> bool:
    """Mark a task as completed.

    Args:
        task_id: The Google Tasks task ID.
        task_list_id: The list containing the task.  Defaults to the AutoMinds list.

    Returns:
        ``True`` on success, ``False`` otherwise.
    """
    try:
        if not task_list_id:
            task_list_id = get_or_create_task_list(account)
            if not task_list_id:
                return False

        service = _build_tasks_service(account)
        service.tasks().patch(
            tasklist=task_list_id,
            task=task_id,
            body={"status": "completed"},
        ).execute()
        logger.info(f"Completed task {task_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to complete task {task_id}: {e}")
        return False


def list_pending_tasks(
    account: ConnectedAccount,
    task_list_id: Optional[str] = None,
) -> list[dict]:
    """List all incomplete tasks from the AutoMinds task list.

    Returns tasks sorted by due date (soonest first).  Tasks without a due
    date sort to the end.
    """
    try:
        if not task_list_id:
            task_list_id = get_or_create_task_list(account)
            if not task_list_id:
                return []

        service = _build_tasks_service(account)
        result = (
            service.tasks()
            .list(
                tasklist=task_list_id,
                showCompleted=False,
                showHidden=False,
            )
            .execute()
        )

        tasks = result.get("items", [])
        # Sort by due date — tasks without one go last
        tasks.sort(key=lambda t: t.get("due", "9999-12-31T23:59:59.000Z"))
        return tasks

    except Exception as e:
        logger.error(f"Failed to list pending tasks: {e}")
        return []


def delete_task(
    account: ConnectedAccount,
    task_id: str,
    task_list_id: Optional[str] = None,
) -> bool:
    """Delete a task.

    Args:
        task_id: The Google Tasks task ID.
        task_list_id: The list containing the task.  Defaults to the AutoMinds list.

    Returns:
        ``True`` on success, ``False`` otherwise.
    """
    try:
        if not task_list_id:
            task_list_id = get_or_create_task_list(account)
            if not task_list_id:
                return False

        service = _build_tasks_service(account)
        service.tasks().delete(tasklist=task_list_id, task=task_id).execute()
        logger.info(f"Deleted task {task_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete task {task_id}: {e}")
        return False
