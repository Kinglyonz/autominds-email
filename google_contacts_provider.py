"""
AutoMinds Email Assistant - Google Contacts Provider
Integrates with the Google People API to look up email senders,
retrieve company/org info, and auto-categorize them as a lightweight
CRM enrichment layer.

Required OAuth scope: https://www.googleapis.com/auth/contacts.readonly
"""

import logging
import time
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

from config import settings
from models import ConnectedAccount

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────

PEOPLE_READ_MASK = (
    "names,emailAddresses,organizations,phoneNumbers,"
    "photos,memberships,biographies"
)

CONTACTS_READONLY_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"

# Delay between individual lookups in batch to respect rate limits (seconds)
_BATCH_LOOKUP_DELAY = 0.1

# ─── Module-Level Cache ─────────────────────────────────

_contact_cache: dict[str, dict] = {}  # email -> contact info


# ─── Relationship Label Mappings ─────────────────────────

_RELATIONSHIP_MAP: dict[str, str] = {
    "clients": "client",
    "client": "client",
    "customers": "client",
    "customer": "client",
    "vip": "vip",
    "important": "vip",
    "team": "internal",
    "coworkers": "internal",
    "coworker": "internal",
    "colleagues": "internal",
    "colleague": "internal",
    "vendors": "vendor",
    "vendor": "vendor",
    "suppliers": "vendor",
    "supplier": "vendor",
    "students": "student",
    "student": "student",
    "family": "personal",
    "friends": "personal",
    "friend": "personal",
}


# ─── People API Service Builder ─────────────────────────

def _build_people_service(account: ConnectedAccount):
    """Build an authenticated Google People API service from a ConnectedAccount.

    Uses the same credential pattern as gmail_provider._build_gmail_service.
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

    return build("people", "v1", credentials=creds)


# ─── Contact Lookup ──────────────────────────────────────

def lookup_contact(
    account: ConnectedAccount, email_address: str
) -> Optional[dict]:
    """Look up a contact by email address using the Google People API.

    Uses searchContacts to find a matching person, then extracts name,
    company, job title, phone, labels (from contact groups), notes,
    photo URL, and an inferred relationship type.

    Results are cached in ``_contact_cache`` to avoid repeated API calls.

    Args:
        account: The connected Google account.
        email_address: The email address to search for.

    Returns:
        A dict with contact info, or None if not found.
    """
    email_lower = email_address.lower().strip()

    # Check cache first
    if email_lower in _contact_cache:
        logger.debug("Contact cache hit for %s", email_lower)
        return _contact_cache[email_lower]

    try:
        service = _build_people_service(account)

        # Search contacts by email address
        response = (
            service.people()
            .searchContacts(query=email_lower, readMask=PEOPLE_READ_MASK)
            .execute()
        )

        results = response.get("results", [])
        if not results:
            logger.debug("No contact found for %s", email_lower)
            _contact_cache[email_lower] = None  # Cache the miss too
            return None

        # Take the first (best) match
        person = results[0].get("person", {})
        contact_info = _parse_person(person, email_lower)

        # Resolve contact group names for labels
        group_resource_names = _extract_group_resource_names(person)
        if group_resource_names:
            contact_info["labels"] = _resolve_group_names(
                service, group_resource_names
            )
        else:
            contact_info["labels"] = []

        # Infer relationship from labels
        contact_info["relationship"] = infer_relationship(contact_info)

        # Cache and return
        _contact_cache[email_lower] = contact_info
        logger.info(
            "Found contact for %s: %s (%s)",
            email_lower,
            contact_info.get("name", ""),
            contact_info.get("company", ""),
        )
        return contact_info

    except Exception:
        logger.exception("Error looking up contact for %s", email_address)
        return None


def batch_lookup_contacts(
    account: ConnectedAccount, email_addresses: list[str]
) -> dict[str, dict]:
    """Look up multiple contacts at once.

    Returns a dict mapping email -> contact info (only for found contacts).
    Uses the cache to skip already-looked-up contacts and adds a small delay
    between uncached lookups to stay within People API rate limits.

    Args:
        account: The connected Google account.
        email_addresses: List of email addresses to look up.

    Returns:
        Dict of email -> contact info for contacts that were found.
    """
    results: dict[str, dict] = {}
    uncached = []

    # Separate cached from uncached
    for email in email_addresses:
        email_lower = email.lower().strip()
        if email_lower in _contact_cache:
            cached = _contact_cache[email_lower]
            if cached is not None:
                results[email_lower] = cached
        else:
            uncached.append(email_lower)

    # Look up uncached contacts sequentially with a small delay
    for i, email in enumerate(uncached):
        if i > 0:
            time.sleep(_BATCH_LOOKUP_DELAY)

        contact = lookup_contact(account, email)
        if contact is not None:
            results[email] = contact

    logger.info(
        "Batch lookup: %d/%d contacts found (%d from cache)",
        len(results),
        len(email_addresses),
        len(email_addresses) - len(uncached),
    )
    return results


# ─── Contact Groups ─────────────────────────────────────

def get_contact_groups(account: ConnectedAccount) -> list[dict]:
    """Get all contact groups/labels for the account.

    Args:
        account: The connected Google account.

    Returns:
        A list of dicts with ``id``, ``name``, and ``member_count`` keys.
        Returns an empty list on error.
    """
    try:
        service = _build_people_service(account)
        response = (
            service.contactGroups()
            .list(pageSize=100)
            .execute()
        )

        groups = []
        for group in response.get("contactGroups", []):
            groups.append(
                {
                    "id": group.get("resourceName", ""),
                    "name": group.get("name", ""),
                    "member_count": group.get("memberCount", 0),
                }
            )

        logger.info("Fetched %d contact groups", len(groups))
        return groups

    except Exception:
        logger.exception("Error fetching contact groups")
        return []


# ─── Email Enrichment ───────────────────────────────────

def enrich_email_with_contact(email_dict: dict, contact_info: dict) -> dict:
    """Add contact enrichment data to an email dict.

    Adds ``sender_company``, ``sender_title``, ``sender_relationship``,
    ``sender_name``, ``sender_phone``, ``sender_labels``, and
    ``sender_photo_url`` fields.  This is a pure data transformation
    — no API calls are made.

    Args:
        email_dict: The email dict to enrich (modified in place and returned).
        contact_info: The contact info dict from ``lookup_contact``.

    Returns:
        The enriched email dict.
    """
    if not contact_info:
        return email_dict

    email_dict["sender_name"] = contact_info.get("name", "")
    email_dict["sender_company"] = contact_info.get("company", "")
    email_dict["sender_title"] = contact_info.get("job_title", "")
    email_dict["sender_phone"] = contact_info.get("phone", "")
    email_dict["sender_relationship"] = contact_info.get("relationship", "unknown")
    email_dict["sender_labels"] = contact_info.get("labels", [])
    email_dict["sender_photo_url"] = contact_info.get("photo_url", "")
    email_dict["sender_notes"] = contact_info.get("notes", "")

    return email_dict


# ─── Relationship Inference ─────────────────────────────

def infer_relationship(contact_info: dict) -> str:
    """Infer a relationship type from a contact's labels/groups.

    Checks each label (case-insensitive) against a known mapping:
        - ``clients``, ``customers``  -> ``"client"``
        - ``vip``, ``important``       -> ``"vip"``
        - ``team``, ``coworkers``, ``colleagues`` -> ``"internal"``
        - ``vendors``, ``suppliers``   -> ``"vendor"``
        - ``students``                 -> ``"student"``
        - ``family``, ``friends``      -> ``"personal"``

    Returns ``"unknown"`` if no matching label is found.
    """
    labels = contact_info.get("labels", [])

    for label in labels:
        normalized = label.lower().strip()
        if normalized in _RELATIONSHIP_MAP:
            return _RELATIONSHIP_MAP[normalized]

    return "unknown"


# ─── Cache Management ───────────────────────────────────

def clear_cache() -> None:
    """Clear the contact cache.

    Call periodically (e.g., every hour) to pick up contact changes.
    """
    _contact_cache.clear()
    logger.info("Contact cache cleared")


# ─── Internal Helpers ────────────────────────────────────

def _parse_person(person: dict, fallback_email: str) -> dict:
    """Extract structured contact info from a People API person resource.

    Args:
        person: The ``person`` object from a People API response.
        fallback_email: Email address to use if none is found on the person.

    Returns:
        A dict with keys: email, name, company, job_title, phone, notes,
        photo_url.  Labels and relationship are filled in by the caller.
    """
    # Name
    names = person.get("names", [])
    name = names[0].get("displayName", "") if names else ""

    # Email — prefer a match to the search email, else first available
    emails = person.get("emailAddresses", [])
    email = fallback_email
    for entry in emails:
        if entry.get("value", "").lower() == fallback_email:
            email = entry["value"]
            break
    else:
        if emails:
            email = emails[0].get("value", fallback_email)

    # Organization
    orgs = person.get("organizations", [])
    company = ""
    job_title = ""
    if orgs:
        company = orgs[0].get("name", "")
        job_title = orgs[0].get("title", "")

    # Phone
    phones = person.get("phoneNumbers", [])
    phone = phones[0].get("value", "") if phones else ""

    # Photo
    photos = person.get("photos", [])
    photo_url = photos[0].get("url", "") if photos else ""

    # Notes / biographies
    bios = person.get("biographies", [])
    notes = bios[0].get("value", "") if bios else ""

    return {
        "email": email,
        "name": name,
        "company": company,
        "job_title": job_title,
        "phone": phone,
        "notes": notes,
        "photo_url": photo_url,
        # labels and relationship are added by the caller
    }


def _extract_group_resource_names(person: dict) -> list[str]:
    """Extract contactGroupResourceNames from a person's memberships."""
    resource_names: list[str] = []
    for membership in person.get("memberships", []):
        group_membership = membership.get("contactGroupMembership", {})
        rn = group_membership.get("contactGroupResourceName", "")
        if rn:
            resource_names.append(rn)
    return resource_names


def _resolve_group_names(
    service, group_resource_names: list[str]
) -> list[str]:
    """Resolve contactGroup resource names to human-readable label strings.

    Uses contactGroups().batchGet() for efficiency.

    Args:
        service: An authenticated People API service.
        group_resource_names: List of resource names like
            ``contactGroups/abc123``.

    Returns:
        A list of group name strings (e.g. ``["clients", "vip"]``).
    """
    if not group_resource_names:
        return []

    try:
        response = (
            service.contactGroups()
            .batchGet(resourceNames=group_resource_names)
            .execute()
        )

        names: list[str] = []
        for group_response in response.get("responses", []):
            group = group_response.get("contactGroup", {})
            name = group.get("name", "")
            # Skip Google's internal system groups (e.g. "myContacts")
            group_type = group.get("groupType", "")
            if name and group_type != "SYSTEM_CONTACT_GROUP":
                names.append(name)

        return names

    except Exception:
        logger.exception("Error resolving contact group names")
        return []
