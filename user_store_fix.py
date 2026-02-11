"""
Quick fix for Railway user storage - use environment variables for persistence
"""
import os
import json
import uuid
from datetime import datetime
from typing import Optional
from models import User, ConnectedAccount, UserSettings, EmailProvider
import logging

logger = logging.getLogger(__name__)

def get_user(user_id: str) -> Optional[User]:
    """Get a user by ID from environment storage."""
    user_data = os.environ.get(f"USER_{user_id}")
    if user_data:
        try:
            data = json.loads(user_data)
            return User(**data)
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {e}")
    return None

def get_user_by_email(email: str) -> Optional[User]:
    """Get a user by email - search through all stored users."""
    # For now, we'll use a simple approach - store the email->user_id mapping
    user_id = os.environ.get(f"EMAIL_{email.replace('@', '_').replace('.', '_')}")
    if user_id:
        return get_user(user_id)
    return None

def create_user(email: str, name: str = "") -> User:
    """Create a new user and store in environment."""
    # Check if user already exists
    existing = get_user_by_email(email)
    if existing:
        return existing
    
    user_id = str(uuid.uuid4())[:8]
    user = User(
        id=user_id,
        email=email, 
        name=name,
        created_at=datetime.utcnow(),
        settings=UserSettings(),
        connected_accounts=[]
    )
    
    # Store user data in environment variable
    try:
        user_data = json.dumps(user.model_dump(), default=str)
        os.environ[f"USER_{user_id}"] = user_data
        
        # Store email mapping  
        email_key = email.replace('@', '_').replace('.', '_')
        os.environ[f"EMAIL_{email_key}"] = user_id
        
        logger.info(f"Created user: {email} (id={user_id})")
        return user
    except Exception as e:
        logger.error(f"Error creating user {email}: {e}")
        raise

def save_user(user: User):
    """Save/update a user in environment storage."""
    try:
        user_data = json.dumps(user.model_dump(), default=str)
        os.environ[f"USER_{user.id}"] = user_data
        
        # Update email mapping
        email_key = user.email.replace('@', '_').replace('.', '_')
        os.environ[f"EMAIL_{email_key}"] = user.id
        
        logger.info(f"Saved user: {user.email} (id={user.id})")
    except Exception as e:
        logger.error(f"Error saving user {user.id}: {e}")
        raise

def add_connected_account(user_id: str, account: ConnectedAccount) -> User:
    """Add a connected account to user."""
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    # Remove existing account with same provider
    user.connected_accounts = [
        acc for acc in user.connected_accounts 
        if acc.provider != account.provider
    ]
    
    # Add new account
    user.connected_accounts.append(account)
    save_user(user)
    
    logger.info(f"Added {account.provider} account for user {user_id}")
    return user

def list_users() -> list[User]:
    """List all users - for admin purposes."""
    users = []
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            try:
                data = json.loads(value)
                users.append(User(**data))
            except Exception:
                continue
    return users