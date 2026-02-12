"""
AutoMinds Email Assistant - Draft Store
Supabase-backed draft storage with in-memory fallback.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── In-memory fallback ──────────────────────────────────
_drafts: dict[str, dict] = {}


def _get_supabase():
    """Get Supabase client if available."""
    from user_store import _supabase_client, _USE_SUPABASE
    if _USE_SUPABASE and _supabase_client:
        return _supabase_client
    return None


def save_draft(draft_id: str, draft_data: dict, user_id: str,
               source_provider: str, source_email: str):
    """Save a draft (Supabase or in-memory)."""
    sb = _get_supabase()
    if sb:
        try:
            draft_obj = draft_data
            row = {
                "id": draft_id,
                "user_id": user_id,
                "original_email_id": draft_obj.get("original_email_id", ""),
                "to_address": draft_obj.get("to", ""),
                "subject": draft_obj.get("subject", ""),
                "body": draft_obj.get("body", ""),
                "status": draft_obj.get("status", "pending"),
                "instructions": draft_obj.get("instructions", ""),
                "safety_flags": draft_obj.get("safety_flags", []),
                "safety_severity": draft_obj.get("safety_severity", "none"),
                "source_provider": source_provider,
                "source_email": source_email,
                "created_at": draft_obj.get("created_at", datetime.utcnow().isoformat()),
            }
            sb.table("drafts").upsert(row).execute()
            return
        except Exception as e:
            logger.warning(f"Supabase draft save failed, using in-memory: {e}")

    # Fallback: in-memory
    _drafts[draft_id] = {
        "draft": draft_data,
        "user_id": user_id,
        "source_provider": source_provider,
        "source_email": source_email,
    }


def get_draft(draft_id: str) -> Optional[dict]:
    """Get a draft by ID. Returns dict with 'draft', 'user_id', 'source_provider', 'source_email'."""
    sb = _get_supabase()
    if sb:
        try:
            result = sb.table("drafts").select("*").eq("id", draft_id).execute()
            if result.data:
                row = result.data[0]
                return _row_to_draft_dict(row)
        except Exception as e:
            logger.warning(f"Supabase draft get failed, checking in-memory: {e}")

    return _drafts.get(draft_id)


def list_user_drafts(user_id: str) -> list[dict]:
    """List all drafts for a user."""
    sb = _get_supabase()
    if sb:
        try:
            result = sb.table("drafts").select("*").eq("user_id", user_id).execute()
            return [_row_to_draft_dict(row)["draft"] for row in result.data]
        except Exception as e:
            logger.warning(f"Supabase draft list failed, using in-memory: {e}")

    return [v["draft"] for v in _drafts.values() if v["user_id"] == user_id]


def update_draft_status(draft_id: str, status: str):
    """Update a draft's status."""
    sb = _get_supabase()
    if sb:
        try:
            sb.table("drafts").update({"status": status}).eq("id", draft_id).execute()
            return
        except Exception as e:
            logger.warning(f"Supabase draft update failed: {e}")

    if draft_id in _drafts:
        _drafts[draft_id]["draft"]["status"] = status


def _row_to_draft_dict(row: dict) -> dict:
    """Convert a Supabase row to the draft dict format used by server.py."""
    return {
        "draft": {
            "id": row["id"],
            "original_email_id": row["original_email_id"],
            "to": row["to_address"],
            "subject": row["subject"],
            "body": row["body"],
            "status": row["status"],
            "instructions": row.get("instructions", ""),
            "safety_flags": row.get("safety_flags", []),
            "safety_severity": row.get("safety_severity", "none"),
            "created_at": row.get("created_at", ""),
        },
        "user_id": row["user_id"],
        "source_provider": row.get("source_provider", ""),
        "source_email": row.get("source_email", ""),
    }
