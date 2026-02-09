"""
AutoMinds Email Assistant - User Store
Simple JSON-file-based user storage for development.
Swap to Supabase for production by changing the backend.
"""

import json
import os
from datetime import datetime
from typing import Optional
from models import User, ConnectedAccount, UserSettings, EmailProvider
import uuid
import logging

logger = logging.getLogger(__name__)

# Storage file path
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")


def _ensure_data_dir():
    """Ensure the data directory exists."""
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)


def _load_users() -> dict:
    """Load all users from disk."""
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_users(users: dict):
    """Save all users to disk."""
    _ensure_data_dir()
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2, default=str)


def get_user(user_id: str) -> Optional[User]:
    """Get a user by ID."""
    users = _load_users()
    data = users.get(user_id)
    if data:
        return User(**data)
    return None


def get_user_by_email(email: str) -> Optional[User]:
    """Get a user by their email address."""
    users = _load_users()
    for uid, data in users.items():
        if data.get("email") == email:
            return User(**data)
        # Also check connected accounts
        for acct in data.get("connected_accounts", []):
            if acct.get("email") == email:
                return User(**data)
    return None


def create_user(email: str, name: str = "") -> User:
    """Create a new user."""
    users = _load_users()

    # Check if user already exists
    existing = get_user_by_email(email)
    if existing:
        return existing

    user_id = str(uuid.uuid4())[:8]
    user = User(
        id=user_id,
        email=email,
        name=name,
        created_at=datetime.utcnow()
    )

    users[user_id] = user.model_dump()
    _save_users(users)
    logger.info(f"Created user: {email} (id={user_id})")
    return user


def save_user(user: User):
    """Save/update a user."""
    users = _load_users()
    users[user.id] = user.model_dump()
    _save_users(users)


def add_connected_account(user_id: str, account: ConnectedAccount) -> User:
    """Add or update a connected email account for a user."""
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    # Remove existing account for same email if it exists
    user.connected_accounts = [
        a for a in user.connected_accounts
        if a.email != account.email
    ]

    # Add the new/updated account
    user.connected_accounts.append(account)
    user.last_active = datetime.utcnow()

    save_user(user)
    logger.info(f"Connected {account.provider} account {account.email} for user {user_id}")
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
    """List all users (for admin/debugging)."""
    users = _load_users()
    return [User(**data) for data in users.values()]
