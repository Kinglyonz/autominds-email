"""
AutoMinds Email Assistant - User Store
Supabase-backed user storage with JSON file fallback for local dev.

Backend selection:
  - If SUPABASE_URL + SUPABASE_SERVICE_KEY are set → uses Supabase (production)
  - Otherwise → falls back to local JSON file (development)
"""

import json
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

from models import User, ConnectedAccount, UserSettings, EmailProvider

logger = logging.getLogger(__name__)

# ─── Backend detection ──────────────────────────────────

_supabase_client = None
_USE_SUPABASE = False


def _init_supabase():
    """Initialize Supabase client if credentials are available."""
    global _supabase_client, _USE_SUPABASE

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if url and key and not url.startswith("PLACEHOLDER"):
        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
            _USE_SUPABASE = True
            logger.info("User store: Supabase backend active")
        except Exception as e:
            logger.warning(f"Supabase init failed, falling back to JSON: {e}")
            _USE_SUPABASE = False
    else:
        logger.info("User store: JSON file backend (set SUPABASE_URL + SUPABASE_SERVICE_KEY for production)")


# Initialize on import
_init_supabase()


# ═══════════════════════════════════════════════════════════
# PUBLIC API — same interface regardless of backend
# ═══════════════════════════════════════════════════════════

def get_user(user_id: str) -> Optional[User]:
    """Get a user by ID."""
    if _USE_SUPABASE:
        return _sb_get_user(user_id)
    return _json_get_user(user_id)


def get_user_by_email(email: str) -> Optional[User]:
    """Get a user by their email address."""
    if _USE_SUPABASE:
        return _sb_get_user_by_email(email)
    return _json_get_user_by_email(email)


def create_user(email: str, name: str = "") -> User:
    """Create a new user. Returns existing user if email already exists."""
    existing = get_user_by_email(email)
    if existing:
        return existing

    if _USE_SUPABASE:
        return _sb_create_user(email, name)
    return _json_create_user(email, name)


def save_user(user: User):
    """Save/update a user."""
    if _USE_SUPABASE:
        _sb_save_user(user)
    else:
        _json_save_user(user)


def add_connected_account(user_id: str, account: ConnectedAccount) -> User:
    """Add or update a connected email account for a user."""
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Remove existing account for same email
    user.connected_accounts = [
        a for a in user.connected_accounts if a.email != account.email
    ]
    user.connected_accounts.append(account)
    user.last_active = datetime.utcnow()

    if _USE_SUPABASE:
        _sb_save_user(user)
        _sb_upsert_connected_account(user_id, account)
    else:
        _json_save_user(user)

    logger.info(f"Connected {account.provider.value} account {account.email} for user {user_id}")
    return user


def get_connected_account(user_id: str, provider: EmailProvider = None) -> Optional[ConnectedAccount]:
    """Get a user's connected account, optionally filtered by provider."""
    user = get_user(user_id)
    if not user or not user.connected_accounts:
        return None
    for acct in user.connected_accounts:
        if provider is None or acct.provider == provider:
            if acct.is_active:
                return acct
    return None


def update_user_settings(user_id: str, settings: UserSettings) -> User:
    """Update a user's settings."""
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    user.settings = settings
    save_user(user)
    return user


def list_all_users() -> list[User]:
    """List all users."""
    if _USE_SUPABASE:
        return _sb_list_all_users()
    return _json_list_all_users()


# Alias for backward compatibility
list_users = list_all_users


# ═══════════════════════════════════════════════════════════
# SUPABASE BACKEND
# ═══════════════════════════════════════════════════════════

def _sb_get_user(user_id: str) -> Optional[User]:
    try:
        result = _supabase_client.table("users").select("*").eq("id", user_id).execute()
        if not result.data:
            return None
        return _sb_row_to_user(result.data[0])
    except Exception as e:
        logger.error(f"Supabase get_user error: {e}")
        return None


def _sb_get_user_by_email(email: str) -> Optional[User]:
    try:
        # Check users table
        result = _supabase_client.table("users").select("*").eq("email", email).execute()
        if result.data:
            return _sb_row_to_user(result.data[0])

        # Also check connected accounts
        result = _supabase_client.table("connected_accounts").select("user_id").eq("email", email).execute()
        if result.data:
            return _sb_get_user(result.data[0]["user_id"])

        return None
    except Exception as e:
        logger.error(f"Supabase get_user_by_email error: {e}")
        return None


def _sb_create_user(email: str, name: str = "") -> User:
    user_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    settings = UserSettings()

    row = {
        "id": user_id,
        "email": email,
        "name": name,
        "tier": "free",
        "settings": settings.model_dump(),
        "created_at": now,
    }

    _supabase_client.table("users").insert(row).execute()
    logger.info(f"Created user: {email} (id={user_id})")

    return User(
        id=user_id,
        email=email,
        name=name,
        created_at=datetime.utcnow(),
        settings=settings,
        connected_accounts=[],
    )


def _sb_save_user(user: User):
    """Save user row and connected accounts to Supabase."""
    try:
        row = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "tier": user.tier,
            "stripe_customer_id": user.stripe_customer_id,
            "subscription_id": user.subscription_id,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "actions_used": user.actions_used,
            "actions_reset_at": user.actions_reset_at.isoformat() if user.actions_reset_at else None,
            "settings": user.settings.model_dump(),
            "last_active": datetime.utcnow().isoformat(),
        }
        _supabase_client.table("users").upsert(row).execute()

        # Sync connected accounts
        for acct in user.connected_accounts:
            _sb_upsert_connected_account(user.id, acct)

    except Exception as e:
        logger.error(f"Supabase save_user error: {e}")
        raise


def _sb_upsert_connected_account(user_id: str, account: ConnectedAccount):
    """Upsert a connected account row."""
    row = {
        "user_id": user_id,
        "provider": account.provider.value,
        "email": account.email,
        "display_name": account.display_name,
        "access_token": account.access_token,
        "refresh_token": account.refresh_token,
        "token_expiry": account.token_expiry.isoformat() if account.token_expiry else None,
        "connected_at": account.connected_at.isoformat() if account.connected_at else datetime.utcnow().isoformat(),
        "is_active": account.is_active,
    }
    _supabase_client.table("connected_accounts").upsert(
        row, on_conflict="user_id,email"
    ).execute()


def _sb_list_all_users() -> list[User]:
    try:
        result = _supabase_client.table("users").select("*").execute()
        return [_sb_row_to_user(row) for row in result.data]
    except Exception as e:
        logger.error(f"Supabase list_all_users error: {e}")
        return []


def _sb_row_to_user(row: dict) -> User:
    """Convert a Supabase users row + connected_accounts into a User model."""
    user_id = row["id"]

    # Fetch connected accounts
    accounts = []
    try:
        acct_result = _supabase_client.table("connected_accounts").select("*").eq("user_id", user_id).execute()
        for acct_row in acct_result.data:
            accounts.append(ConnectedAccount(
                provider=EmailProvider(acct_row["provider"]),
                email=acct_row["email"],
                display_name=acct_row.get("display_name", ""),
                access_token=acct_row["access_token"],
                refresh_token=acct_row["refresh_token"],
                token_expiry=acct_row.get("token_expiry"),
                connected_at=acct_row.get("connected_at"),
                is_active=acct_row.get("is_active", True),
            ))
    except Exception as e:
        logger.warning(f"Failed to fetch connected accounts for {user_id}: {e}")

    # Parse settings
    settings_data = row.get("settings", {})
    if isinstance(settings_data, str):
        settings_data = json.loads(settings_data)
    settings = UserSettings(**settings_data) if settings_data else UserSettings()

    return User(
        id=user_id,
        email=row["email"],
        name=row.get("name", ""),
        tier=row.get("tier", "free"),
        stripe_customer_id=row.get("stripe_customer_id"),
        subscription_id=row.get("subscription_id"),
        plan_expires_at=row.get("plan_expires_at"),
        actions_used=row.get("actions_used", 0),
        actions_reset_at=row.get("actions_reset_at"),
        settings=settings,
        connected_accounts=accounts,
        created_at=row.get("created_at"),
        last_active=row.get("last_active"),
    )


# ═══════════════════════════════════════════════════════════
# JSON FILE BACKEND (fallback for local development)
# ═══════════════════════════════════════════════════════════

USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")


def _ensure_data_dir():
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)


def _load_users() -> dict:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_users(users: dict):
    _ensure_data_dir()
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, default=str)


def _json_get_user(user_id: str) -> Optional[User]:
    users = _load_users()
    data = users.get(user_id)
    if data:
        return User(**data)
    return None


def _json_get_user_by_email(email: str) -> Optional[User]:
    users = _load_users()
    for uid, data in users.items():
        if data.get("email") == email:
            return User(**data)
        for acct in data.get("connected_accounts", []):
            if acct.get("email") == email:
                return User(**data)
    return None


def _json_create_user(email: str, name: str = "") -> User:
    users = _load_users()
    user_id = str(uuid.uuid4())[:8]
    user = User(
        id=user_id,
        email=email,
        name=name,
        created_at=datetime.utcnow(),
    )
    users[user_id] = user.model_dump()
    _save_users(users)
    logger.info(f"Created user: {email} (id={user_id})")
    return user


def _json_save_user(user: User):
    users = _load_users()
    users[user.id] = user.model_dump()
    _save_users(users)


def _json_list_all_users() -> list[User]:
    users = _load_users()
    return [User(**data) for data in users.values()]
