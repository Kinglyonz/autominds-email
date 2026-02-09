"""
AutoMinds Email Assistant - Gmail Provider
Handles Gmail OAuth, email fetching, sending, and label management.
"""

import base64
import logging
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import settings
from models import (
    EmailMessage, EmailAddress, EmailProvider, ConnectedAccount
)

logger = logging.getLogger(__name__)


# ─── OAuth Flow ──────────────────────────────────────────

def get_google_auth_url(state: str = "") -> str:
    """Generate the Google OAuth consent URL.
    
    Args:
        state: Opaque string to pass through the OAuth flow (e.g., user_id).
    
    Returns:
        The authorization URL the user should be redirected to.
    """
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=settings.gmail_scopes,
    )
    flow.redirect_uri = settings.google_redirect_uri

    auth_url, _ = flow.authorization_url(
        access_type="offline",       # Get refresh token
        include_granted_scopes="true",
        prompt="consent",            # Force consent to get refresh token
        state=state,
    )

    return auth_url


def exchange_google_code(code: str) -> ConnectedAccount:
    """Exchange the authorization code for tokens and return a ConnectedAccount.
    
    Args:
        code: The authorization code from Google's OAuth callback.
    
    Returns:
        A ConnectedAccount with tokens populated.
    """
    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=settings.gmail_scopes,
    )
    flow.redirect_uri = settings.google_redirect_uri
    flow.fetch_token(code=code)

    creds = flow.credentials

    # Build Gmail service to get the user's email
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Build people service to get display name
    display_name = email.split("@")[0]
    try:
        people_service = build("people", "v1", credentials=creds)
        person = people_service.people().get(
            resourceName="people/me",
            personFields="names"
        ).execute()
        names = person.get("names", [])
        if names:
            display_name = names[0].get("displayName", display_name)
    except Exception:
        pass  # Non-critical — fallback to email prefix

    return ConnectedAccount(
        provider=EmailProvider.GMAIL,
        email=email,
        display_name=display_name,
        access_token=creds.token,
        refresh_token=creds.refresh_token or "",
        token_expiry=creds.expiry,
        is_active=True,
    )


# ─── Gmail Service Builder ──────────────────────────────

def _build_gmail_service(account: ConnectedAccount):
    """Build an authenticated Gmail API service from a ConnectedAccount.
    
    Automatically refreshes the token if expired.
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
        # Update the stored tokens
        account.access_token = creds.token
        account.token_expiry = creds.expiry

    return build("gmail", "v1", credentials=creds)


# ─── Email Fetching ──────────────────────────────────────

def fetch_emails(
    account: ConnectedAccount,
    query: str = "is:unread",
    max_results: int = 25,
) -> list[EmailMessage]:
    """Fetch emails from Gmail matching a query.
    
    Args:
        account: The connected Gmail account.
        query: Gmail search query (default: unread emails).
        max_results: Maximum number of emails to return.
    
    Returns:
        List of normalized EmailMessage objects.
    """
    service = _build_gmail_service(account)

    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute()

        message_refs = results.get("messages", [])
        if not message_refs:
            return []

        emails = []
        for ref in message_refs:
            try:
                raw = service.users().messages().get(
                    userId="me",
                    id=ref["id"],
                    format="full",
                ).execute()
                parsed = _parse_gmail_message(raw)
                if parsed:
                    emails.append(parsed)
            except Exception as e:
                logger.warning(f"Failed to parse message {ref['id']}: {e}")
                continue

        logger.info(f"Fetched {len(emails)} emails from {account.email}")
        return emails

    except Exception as e:
        logger.error(f"Error fetching emails from {account.email}: {e}")
        return []


def fetch_email_by_id(account: ConnectedAccount, email_id: str) -> Optional[EmailMessage]:
    """Fetch a single email by ID."""
    service = _build_gmail_service(account)
    try:
        raw = service.users().messages().get(
            userId="me", id=email_id, format="full"
        ).execute()
        return _parse_gmail_message(raw)
    except Exception as e:
        logger.error(f"Error fetching email {email_id}: {e}")
        return None


# ─── Email Sending ───────────────────────────────────────

def send_email(
    account: ConnectedAccount,
    to: str,
    subject: str,
    body: str,
    reply_to_id: Optional[str] = None,
) -> bool:
    """Send an email (or reply to an existing email).
    
    Args:
        account: The connected Gmail account.
        to: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        reply_to_id: If replying, the original message ID.
    
    Returns:
        True if sent successfully.
    """
    service = _build_gmail_service(account)

    try:
        message = MIMEMultipart("alternative")
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body, "plain"))

        body_dict = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}

        # If replying, set threadId and In-Reply-To headers
        if reply_to_id:
            original = service.users().messages().get(
                userId="me", id=reply_to_id, format="metadata",
                metadataHeaders=["Message-Id"]
            ).execute()

            thread_id = original.get("threadId")
            if thread_id:
                body_dict["threadId"] = thread_id

            headers = original.get("payload", {}).get("headers", [])
            msg_id = next(
                (h["value"] for h in headers if h["name"].lower() == "message-id"),
                None
            )
            if msg_id:
                message["In-Reply-To"] = msg_id
                message["References"] = msg_id
                body_dict["raw"] = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(userId="me", body=body_dict).execute()
        logger.info(f"Email sent to {to} from {account.email}")
        return True

    except Exception as e:
        logger.error(f"Error sending email from {account.email}: {e}")
        return False


# ─── Label Management ────────────────────────────────────

def mark_as_read(account: ConnectedAccount, email_id: str) -> bool:
    """Mark an email as read."""
    service = _build_gmail_service(account)
    try:
        service.users().messages().modify(
            userId="me", id=email_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error marking email as read: {e}")
        return False


def add_label(account: ConnectedAccount, email_id: str, label_name: str) -> bool:
    """Add a label to an email (creates the label if it doesn't exist)."""
    service = _build_gmail_service(account)
    try:
        # Find or create label
        label_id = _get_or_create_label(service, label_name)
        if label_id:
            service.users().messages().modify(
                userId="me", id=email_id,
                body={"addLabelIds": [label_id]}
            ).execute()
            return True
        return False
    except Exception as e:
        logger.error(f"Error adding label: {e}")
        return False


def _get_or_create_label(service, label_name: str) -> Optional[str]:
    """Get a label ID by name, creating it if it doesn't exist."""
    try:
        labels = service.users().labels().list(userId="me").execute()
        for label in labels.get("labels", []):
            if label["name"].lower() == label_name.lower():
                return label["id"]

        # Create label
        new_label = service.users().labels().create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
        ).execute()
        return new_label["id"]
    except Exception as e:
        logger.error(f"Error managing label '{label_name}': {e}")
        return None


# ─── Parsing Helpers ─────────────────────────────────────

def _parse_gmail_message(raw: dict) -> Optional[EmailMessage]:
    """Parse a raw Gmail API message into a normalized EmailMessage."""
    try:
        headers = raw.get("payload", {}).get("headers", [])

        def get_header(name: str) -> str:
            return next(
                (h["value"] for h in headers if h["name"].lower() == name.lower()),
                ""
            )

        # Parse sender
        from_raw = get_header("From")
        sender = _parse_email_address(from_raw)

        # Parse recipients
        to_raw = get_header("To")
        to_list = [_parse_email_address(a.strip()) for a in to_raw.split(",") if a.strip()] if to_raw else []

        cc_raw = get_header("Cc")
        cc_list = [_parse_email_address(a.strip()) for a in cc_raw.split(",") if a.strip()] if cc_raw else []

        # Parse date
        date_raw = get_header("Date")
        try:
            # Gmail dates can be complex; use internalDate as fallback
            internal_date_ms = int(raw.get("internalDate", 0))
            date = datetime.fromtimestamp(internal_date_ms / 1000)
        except (ValueError, TypeError, OSError):
            date = datetime.utcnow()

        # Extract body
        body_text = _extract_body(raw.get("payload", {}), "text/plain")
        body_html = _extract_body(raw.get("payload", {}), "text/html")

        # Check for attachments
        attachment_names = _get_attachment_names(raw.get("payload", {}))

        # Get labels
        labels = raw.get("labelIds", [])
        is_unread = "UNREAD" in labels

        return EmailMessage(
            id=raw["id"],
            thread_id=raw.get("threadId"),
            provider=EmailProvider.GMAIL,
            subject=get_header("Subject") or "(No Subject)",
            sender=sender,
            to=to_list,
            cc=cc_list,
            date=date,
            body_text=body_text[:settings.max_email_body_chars],
            body_html=body_html[:settings.max_email_body_chars],
            snippet=raw.get("snippet", ""),
            is_unread=is_unread,
            labels=labels,
            has_attachments=len(attachment_names) > 0,
            attachment_names=attachment_names,
        )

    except Exception as e:
        logger.error(f"Error parsing Gmail message: {e}")
        return None


def _parse_email_address(raw: str) -> EmailAddress:
    """Parse 'Name <email@example.com>' into EmailAddress."""
    if not raw:
        return EmailAddress(name="", email="")

    # Match "Name <email>" pattern
    match = re.match(r'^"?([^"<]*)"?\s*<?([^>]+)>?$', raw.strip())
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return EmailAddress(name=name, email=email)

    # Fallback: treat the whole thing as an email
    return EmailAddress(name="", email=raw.strip())


def _extract_body(payload: dict, mime_type: str) -> str:
    """Recursively extract email body of a given MIME type."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Recurse into parts
    for part in payload.get("parts", []):
        result = _extract_body(part, mime_type)
        if result:
            return result

    return ""


def _get_attachment_names(payload: dict) -> list[str]:
    """Get names of all attachments."""
    names = []
    for part in payload.get("parts", []):
        filename = part.get("filename")
        if filename:
            names.append(filename)
        # Recurse
        names.extend(_get_attachment_names(part))
    return names
