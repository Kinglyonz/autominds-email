"""
AutoMinds Email Assistant - Outlook/Microsoft 365 Provider
Handles Microsoft OAuth, email fetching via Graph API, and sending.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx
import msal

from config import settings
from models import EmailMessage, EmailAddress, EmailProvider, ConnectedAccount

logger = logging.getLogger(__name__)


# ─── OAuth Flow ──────────────────────────────────────────

def get_microsoft_auth_url(state: str = "") -> str:
    """Generate the Microsoft OAuth consent URL."""
    if not settings.ms_client_id:
        raise ValueError("Microsoft OAuth not configured (MS_CLIENT_ID missing)")

    app = msal.ConfidentialClientApplication(
        settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        client_credential=settings.ms_client_secret,
    )

    auth_url = app.get_authorization_request_url(
        scopes=settings.ms_scopes,
        redirect_uri=settings.ms_redirect_uri,
        state=state,
    )

    return auth_url


def exchange_microsoft_code(code: str) -> ConnectedAccount:
    """Exchange the authorization code for tokens and return a ConnectedAccount."""
    app = msal.ConfidentialClientApplication(
        settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        client_credential=settings.ms_client_secret,
    )

    result = app.acquire_token_by_authorization_code(
        code,
        scopes=settings.ms_scopes,
        redirect_uri=settings.ms_redirect_uri,
    )

    if "error" in result:
        raise ValueError(f"Microsoft OAuth error: {result.get('error_description', result['error'])}")

    access_token = result["access_token"]
    refresh_token = result.get("refresh_token", "")

    # Get user profile
    with httpx.Client() as client:
        resp = client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile = resp.json()

    email = profile.get("mail") or profile.get("userPrincipalName", "")
    display_name = profile.get("displayName", email.split("@")[0])

    return ConnectedAccount(
        provider=EmailProvider.OUTLOOK,
        email=email,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        is_active=True,
    )


# ─── Token Refresh ───────────────────────────────────────

def _refresh_token(account: ConnectedAccount) -> str:
    """Refresh the Microsoft access token."""
    if not account.refresh_token:
        raise ValueError("No refresh token available for Microsoft account")

    app = msal.ConfidentialClientApplication(
        settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        client_credential=settings.ms_client_secret,
    )

    result = app.acquire_token_by_refresh_token(
        account.refresh_token,
        scopes=settings.ms_scopes,
    )

    if "error" in result:
        raise ValueError(f"Token refresh failed: {result.get('error_description')}")

    account.access_token = result["access_token"]
    if "refresh_token" in result:
        account.refresh_token = result["refresh_token"]

    return account.access_token


def _get_headers(account: ConnectedAccount) -> dict:
    """Get authorization headers, refreshing token if needed."""
    return {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
    }


# ─── Email Fetching ──────────────────────────────────────

def fetch_emails(
    account: ConnectedAccount,
    query: str = "",
    max_results: int = 25,
    unread_only: bool = True,
) -> list[EmailMessage]:
    """Fetch emails from Outlook/Microsoft 365 via Graph API."""
    try:
        headers = _get_headers(account)

        # Build OData filter
        url = "https://graph.microsoft.com/v1.0/me/messages"
        params = {
            "$top": max_results,
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,"
                       "receivedDateTime,bodyPreview,body,isRead,hasAttachments,"
                       "categories",
        }

        if unread_only:
            params["$filter"] = "isRead eq false"

        if query:
            params["$search"] = f'"{query}"'

        with httpx.Client() as client:
            resp = client.get(url, headers=headers, params=params)

            # If 401, try refreshing token
            if resp.status_code == 401:
                _refresh_token(account)
                headers = _get_headers(account)
                resp = client.get(url, headers=headers, params=params)

            resp.raise_for_status()
            data = resp.json()

        messages = data.get("value", [])
        emails = []

        for msg in messages:
            try:
                parsed = _parse_outlook_message(msg)
                if parsed:
                    emails.append(parsed)
            except Exception as e:
                logger.warning(f"Failed to parse Outlook message {msg.get('id')}: {e}")

        logger.info(f"Fetched {len(emails)} emails from Outlook ({account.email})")
        return emails

    except Exception as e:
        logger.error(f"Error fetching Outlook emails: {e}")
        return []


def fetch_email_by_id(account: ConnectedAccount, email_id: str) -> Optional[EmailMessage]:
    """Fetch a single email by ID from Outlook."""
    try:
        headers = _get_headers(account)
        url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}"

        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 401:
                _refresh_token(account)
                headers = _get_headers(account)
                resp = client.get(url, headers=headers)
            resp.raise_for_status()

        return _parse_outlook_message(resp.json())
    except Exception as e:
        logger.error(f"Error fetching Outlook email {email_id}: {e}")
        return None


# ─── Email Sending ───────────────────────────────────────

def send_email(
    account: ConnectedAccount,
    to: str,
    subject: str,
    body: str,
    reply_to_id: Optional[str] = None,
) -> bool:
    """Send an email via Microsoft Graph API."""
    try:
        headers = _get_headers(account)

        if reply_to_id:
            # Reply to existing message
            url = f"https://graph.microsoft.com/v1.0/me/messages/{reply_to_id}/reply"
            payload = {
                "message": {
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "comment": body,
            }
        else:
            # New message
            url = "https://graph.microsoft.com/v1.0/me/sendMail"
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            }

        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 401:
                _refresh_token(account)
                headers = _get_headers(account)
                resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()

        logger.info(f"Email sent to {to} from Outlook ({account.email})")
        return True

    except Exception as e:
        logger.error(f"Error sending Outlook email: {e}")
        return False


# ─── Mark as Read ────────────────────────────────────────

def mark_as_read(account: ConnectedAccount, email_id: str) -> bool:
    """Mark an Outlook email as read."""
    try:
        headers = _get_headers(account)
        url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}"

        with httpx.Client() as client:
            resp = client.patch(url, headers=headers, json={"isRead": True})
            resp.raise_for_status()

        return True
    except Exception as e:
        logger.error(f"Error marking Outlook email as read: {e}")
        return False


# ─── Parsing ─────────────────────────────────────────────

def _parse_outlook_message(msg: dict) -> Optional[EmailMessage]:
    """Parse an Outlook Graph API message into a normalized EmailMessage."""
    try:
        sender_data = msg.get("from", {}).get("emailAddress", {})
        sender = EmailAddress(
            name=sender_data.get("name", ""),
            email=sender_data.get("address", ""),
        )

        to_list = [
            EmailAddress(
                name=r.get("emailAddress", {}).get("name", ""),
                email=r.get("emailAddress", {}).get("address", ""),
            )
            for r in msg.get("toRecipients", [])
        ]

        cc_list = [
            EmailAddress(
                name=r.get("emailAddress", {}).get("name", ""),
                email=r.get("emailAddress", {}).get("address", ""),
            )
            for r in msg.get("ccRecipients", [])
        ]

        # Parse date
        date_str = msg.get("receivedDateTime", "")
        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            date = datetime.utcnow()

        # Body
        body_data = msg.get("body", {})
        body_text = ""
        body_html = ""
        if body_data.get("contentType") == "text":
            body_text = body_data.get("content", "")
        else:
            body_html = body_data.get("content", "")

        return EmailMessage(
            id=msg["id"],
            thread_id=msg.get("conversationId"),
            provider=EmailProvider.OUTLOOK,
            subject=msg.get("subject", "(No Subject)"),
            sender=sender,
            to=to_list,
            cc=cc_list,
            date=date,
            body_text=body_text[:settings.max_email_body_chars],
            body_html=body_html[:settings.max_email_body_chars],
            snippet=msg.get("bodyPreview", ""),
            is_unread=not msg.get("isRead", True),
            labels=msg.get("categories", []),
            has_attachments=msg.get("hasAttachments", False),
        )

    except Exception as e:
        logger.error(f"Error parsing Outlook message: {e}")
        return None
