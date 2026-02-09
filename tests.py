"""
AutoMinds Email Assistant — Comprehensive Test Suite
Run with: pytest tests.py -v
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Ensure test-safe paths BEFORE importing project modules that read env vars
# ---------------------------------------------------------------------------

# Override the user store file path so tests never touch real data
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "_test_users")
TEST_USERS_FILE = os.path.join(TEST_DATA_DIR, "users.json")


@pytest.fixture(autouse=True)
def _isolate_user_store(monkeypatch):
    """Redirect user_store to a temp directory for every test."""
    import user_store

    monkeypatch.setattr(user_store, "USERS_FILE", TEST_USERS_FILE)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    with open(TEST_USERS_FILE, "w") as f:
        json.dump({}, f)
    yield
    # Cleanup
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


# ---------------------------------------------------------------------------
# Helpers — reusable factories
# ---------------------------------------------------------------------------

from models import (
    EmailMessage,
    EmailAddress,
    EmailProvider,
    EmailPriority,
    EmailCategory,
    EmailDraft,
    DailyBriefing,
    DraftStatus,
    User,
    UserSettings,
    ConnectedAccount,
    DraftRequest,
    AutoSendRuleRequest,
    HealthResponse,
)


def _make_email(**overrides) -> EmailMessage:
    """Build a minimal EmailMessage with sensible defaults."""
    defaults = dict(
        id="msg_001",
        thread_id="thread_001",
        provider=EmailProvider.GMAIL,
        subject="Hello Test",
        sender=EmailAddress(name="Alice", email="alice@example.com"),
        to=[EmailAddress(name="Bob", email="bob@example.com")],
        date=datetime(2026, 2, 8, 9, 0, 0),
        body_text="This is the body.",
        snippet="This is the body.",
        is_unread=True,
    )
    defaults.update(overrides)
    return EmailMessage(**defaults)


def _make_user(**overrides) -> User:
    """Build a minimal User."""
    defaults = dict(
        id="u_test1",
        email="testuser@example.com",
        name="Test User",
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_connected_account(**overrides) -> ConnectedAccount:
    defaults = dict(
        provider=EmailProvider.GMAIL,
        email="testuser@gmail.com",
        display_name="Test User",
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
        is_active=True,
    )
    defaults.update(overrides)
    return ConnectedAccount(**defaults)


# ===================================================================
# 1. MODEL CREATION & SERIALIZATION
# ===================================================================


class TestModels:
    """Pydantic model instantiation and round-trip serialization."""

    def test_email_message_defaults(self):
        em = _make_email()
        assert em.id == "msg_001"
        assert em.provider == EmailProvider.GMAIL
        assert em.is_unread is True
        assert em.priority is None  # AI fields start empty
        assert em.category is None

    def test_email_message_with_ai_fields(self):
        em = _make_email(
            priority=EmailPriority.URGENT,
            category=EmailCategory.ACTION_REQUIRED,
            summary="Important meeting request",
            suggested_action="Reply confirming attendance",
            is_vip=True,
        )
        assert em.priority == EmailPriority.URGENT
        assert em.category == EmailCategory.ACTION_REQUIRED
        assert em.is_vip is True

    def test_email_message_serialization(self):
        em = _make_email()
        data = em.model_dump()
        assert data["id"] == "msg_001"
        assert data["sender"]["email"] == "alice@example.com"
        # Round-trip
        em2 = EmailMessage(**data)
        assert em2.id == em.id
        assert em2.sender.email == em.sender.email

    def test_user_defaults(self):
        user = _make_user()
        assert user.tier == "free"
        assert user.settings.briefing_time == "07:00"
        assert user.connected_accounts == []

    def test_user_serialization(self):
        user = _make_user()
        data = user.model_dump()
        user2 = User(**data)
        assert user2.email == user.email

    def test_daily_briefing_defaults(self):
        b = DailyBriefing(user_id="u1")
        assert b.total_unread == 0
        assert b.urgent_count == 0
        assert b.full_text == ""

    def test_daily_briefing_populated(self):
        b = DailyBriefing(
            user_id="u1",
            total_unread=15,
            urgent_count=2,
            action_required_count=5,
            full_text="Good morning!",
            emails_analyzed=15,
            processing_time_seconds=1.23,
            estimated_cost_usd=0.30,
        )
        assert b.urgent_count == 2
        assert b.estimated_cost_usd == 0.30

    def test_email_draft_defaults(self):
        d = EmailDraft(
            original_email_id="msg_001",
            to="alice@example.com",
            subject="Re: Hello",
            body="Thanks!",
        )
        assert d.status == DraftStatus.PENDING
        assert d.instructions == ""

    def test_email_draft_serialization(self):
        d = EmailDraft(
            id="draft1",
            original_email_id="msg_001",
            to="alice@example.com",
            subject="Re: Hello",
            body="Thanks!",
            status=DraftStatus.APPROVED,
        )
        data = d.model_dump()
        d2 = EmailDraft(**data)
        assert d2.status == DraftStatus.APPROVED
        assert d2.to == "alice@example.com"

    def test_connected_account(self):
        acct = _make_connected_account()
        assert acct.provider == EmailProvider.GMAIL
        assert acct.is_active is True

    def test_user_settings_vip_contacts(self):
        s = UserSettings(vip_contacts=["boss@acme.com", "investor@vc.com"])
        assert len(s.vip_contacts) == 2
        assert "boss@acme.com" in s.vip_contacts

    def test_health_response(self):
        h = HealthResponse(connected_accounts=3, uptime_seconds=42.5)
        assert h.status == "ok"
        assert h.connected_accounts == 3


# ===================================================================
# 2. USER STORE CRUD
# ===================================================================


class TestUserStore:
    """Tests for user_store.py CRUD — uses the test-isolated JSON file."""

    def test_create_user(self):
        import user_store

        user = user_store.create_user("new@example.com", "New User")
        assert user.email == "new@example.com"
        assert user.name == "New User"
        assert user.id  # non-empty

    def test_get_user(self):
        import user_store

        created = user_store.create_user("get@example.com", "Get Me")
        fetched = user_store.get_user(created.id)
        assert fetched is not None
        assert fetched.email == "get@example.com"

    def test_get_user_not_found(self):
        import user_store

        assert user_store.get_user("nonexistent") is None

    def test_get_user_by_email(self):
        import user_store

        user_store.create_user("find@example.com", "Find Me")
        found = user_store.get_user_by_email("find@example.com")
        assert found is not None
        assert found.email == "find@example.com"

    def test_create_user_idempotent(self):
        import user_store

        u1 = user_store.create_user("dup@example.com", "First")
        u2 = user_store.create_user("dup@example.com", "Second")
        assert u1.id == u2.id  # same user returned

    def test_save_user(self):
        import user_store

        user = user_store.create_user("save@example.com")
        user.name = "Updated Name"
        user_store.save_user(user)

        reloaded = user_store.get_user(user.id)
        assert reloaded.name == "Updated Name"

    def test_update_user_settings(self):
        import user_store

        user = user_store.create_user("settings@example.com")
        new_settings = UserSettings(
            briefing_time="09:30",
            draft_tone="casual",
            vip_contacts=["vip@acme.com"],
        )
        updated = user_store.update_user_settings(user.id, new_settings)
        assert updated.settings.briefing_time == "09:30"
        assert updated.settings.draft_tone == "casual"

    def test_update_settings_nonexistent_user_raises(self):
        import user_store

        with pytest.raises(ValueError, match="not found"):
            user_store.update_user_settings("nope", UserSettings())

    def test_add_connected_account(self):
        import user_store

        user = user_store.create_user("acct@example.com")
        acct = _make_connected_account(email="acct@gmail.com")
        updated = user_store.add_connected_account(user.id, acct)
        assert len(updated.connected_accounts) == 1
        assert updated.connected_accounts[0].email == "acct@gmail.com"

    def test_add_connected_account_replaces_same_email(self):
        import user_store

        user = user_store.create_user("replace@example.com")
        acct1 = _make_connected_account(email="same@gmail.com", access_token="old")
        user_store.add_connected_account(user.id, acct1)

        acct2 = _make_connected_account(email="same@gmail.com", access_token="new")
        updated = user_store.add_connected_account(user.id, acct2)
        assert len(updated.connected_accounts) == 1
        assert updated.connected_accounts[0].access_token == "new"

    def test_add_connected_account_nonexistent_user_raises(self):
        import user_store

        with pytest.raises(ValueError, match="not found"):
            user_store.add_connected_account("nope", _make_connected_account())

    def test_list_all_users(self):
        import user_store

        user_store.create_user("a@example.com")
        user_store.create_user("b@example.com")
        users = user_store.list_all_users()
        assert len(users) >= 2

    def test_get_connected_account(self):
        import user_store

        user = user_store.create_user("conn@example.com")
        acct = _make_connected_account(email="conn@gmail.com")
        user_store.add_connected_account(user.id, acct)

        result = user_store.get_connected_account(user.id, EmailProvider.GMAIL)
        assert result is not None
        assert result.email == "conn@gmail.com"

    def test_get_connected_account_none(self):
        import user_store

        user = user_store.create_user("noacct@example.com")
        assert user_store.get_connected_account(user.id) is None


# ===================================================================
# 3. EMAIL PARSING HELPERS
# ===================================================================


class TestEmailParsing:
    """Tests for gmail_provider._parse_email_address."""

    def test_parse_name_and_email(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address('John Doe <john@example.com>')
        assert result.name == "John Doe"
        assert result.email == "john@example.com"

    def test_parse_quoted_name(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address('"Jane Smith" <jane@example.com>')
        assert result.name == "Jane Smith"
        assert result.email == "jane@example.com"

    def test_parse_email_only(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address("solo@example.com")
        assert result.email == "solo@example.com"
        # name may be empty or same as email — depends on regex
        assert result.name == "" or result.name == "solo@example.com"

    def test_parse_empty_string(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address("")
        assert result.email == ""
        assert result.name == ""

    def test_parse_angle_brackets_no_name(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address("<user@example.com>")
        assert result.email == "user@example.com"

    def test_parse_name_with_special_chars(self):
        from gmail_provider import _parse_email_address

        result = _parse_email_address("O'Brien, Pat <pat@example.com>")
        assert result.email == "pat@example.com"
        assert "Pat" in result.name or "O'Brien" in result.name


# ===================================================================
# 4. PRIORITY SCORING / ANALYSIS (mocked Claude)
# ===================================================================


class TestEmailAnalysis:
    """email_brain.analyze_emails — mock the Anthropic client."""

    def _mock_claude_response(self, emails):
        """Return a fake analysis JSON matching the expected schema."""
        results = []
        for em in emails:
            results.append({
                "id": em.id,
                "priority": "high",
                "category": "action_required",
                "summary": f"Summary for {em.subject}",
                "suggested_action": "Reply soon",
                "is_vip": em.sender.email in ["boss@acme.com"],
            })
        return json.dumps(results)

    @patch("email_brain._get_client")
    def test_analyze_emails_populates_fields(self, mock_get_client):
        from email_brain import analyze_emails

        emails = [_make_email(id="e1"), _make_email(id="e2", subject="Another")]

        # Set up mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=self._mock_claude_response(emails))]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = analyze_emails(emails)

        assert len(result) == 2
        assert result[0].priority == EmailPriority.HIGH
        assert result[0].category == EmailCategory.ACTION_REQUIRED
        assert result[0].summary.startswith("Summary for")

    @patch("email_brain._get_client")
    def test_analyze_emails_empty_list(self, mock_get_client):
        from email_brain import analyze_emails

        result = analyze_emails([])
        assert result == []
        mock_get_client.assert_not_called()

    @patch("email_brain._get_client")
    def test_analyze_emails_vip_contacts(self, mock_get_client):
        from email_brain import analyze_emails

        emails = [_make_email(id="e1", sender=EmailAddress(name="Boss", email="boss@acme.com"))]

        mock_client = MagicMock()
        resp_data = [{
            "id": "e1",
            "priority": "urgent",
            "category": "action_required",
            "summary": "Boss email",
            "suggested_action": "Reply ASAP",
            "is_vip": True,
        }]
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(resp_data))]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = analyze_emails(emails, vip_contacts=["boss@acme.com"])

        assert result[0].is_vip is True
        assert result[0].priority == EmailPriority.URGENT

    @patch("email_brain._get_client")
    def test_analyze_emails_handles_json_error(self, mock_get_client):
        from email_brain import analyze_emails

        emails = [_make_email(id="e1")]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="NOT JSON")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Should return emails without AI fields instead of raising
        result = analyze_emails(emails)
        assert len(result) == 1
        # priority stays None or default
        assert result[0].summary is None or result[0].summary == ""


# ===================================================================
# 5. DRAFT REPLY (mocked Claude)
# ===================================================================


class TestDraftReply:
    """email_brain.draft_reply — mock the Anthropic client."""

    @patch("email_brain._get_client")
    def test_draft_reply_success(self, mock_get_client):
        from email_brain import draft_reply

        original = _make_email(subject="Meeting Tomorrow")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Sure, I'll be there at 2 PM.")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        draft = draft_reply(original, instructions="Accept the meeting", tone="professional", user_name="Bob")

        assert draft.to == "alice@example.com"
        assert draft.subject == "Re: Meeting Tomorrow"
        assert "2 PM" in draft.body
        assert draft.status == DraftStatus.PENDING

    @patch("email_brain._get_client")
    def test_draft_reply_re_prefix_not_duplicated(self, mock_get_client):
        from email_brain import draft_reply

        original = _make_email(subject="Re: Already Replied")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Got it.")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        draft = draft_reply(original)
        assert draft.subject == "Re: Already Replied"  # no double Re:

    @patch("email_brain._get_client")
    def test_draft_reply_error_returns_error_body(self, mock_get_client):
        from email_brain import draft_reply

        original = _make_email()

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API down")
        mock_get_client.return_value = mock_client

        draft = draft_reply(original)
        assert "[Error generating draft" in draft.body
        assert draft.status == DraftStatus.PENDING


# ===================================================================
# 6. BRIEFING GENERATION (mocked Claude)
# ===================================================================


class TestBriefingGeneration:
    """email_brain.generate_briefing — mock the Anthropic client."""

    @patch("email_brain._get_client")
    def test_generate_briefing(self, mock_get_client):
        from email_brain import generate_briefing

        emails = [
            _make_email(id="e1", priority=EmailPriority.URGENT, category=EmailCategory.ACTION_REQUIRED),
            _make_email(id="e2", priority=EmailPriority.NORMAL, category=EmailCategory.FYI),
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Good morning! You have 2 unread emails...")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        briefing = generate_briefing(emails, user_name="Test User")

        assert briefing.total_unread == 2
        assert briefing.urgent_count == 1
        assert briefing.emails_analyzed == 2
        assert "Good morning" in briefing.full_text

    @patch("email_brain._get_client")
    def test_generate_briefing_error(self, mock_get_client):
        from email_brain import generate_briefing

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("timeout")
        mock_get_client.return_value = mock_client

        briefing = generate_briefing([_make_email()])
        assert "Error" in briefing.full_text


# ===================================================================
# 7. FASTAPI ENDPOINTS (httpx AsyncClient / TestClient)
# ===================================================================


@pytest.fixture()
def _seed_user():
    """Create a user with a connected Gmail account for API tests."""
    import user_store

    user = user_store.create_user("api@example.com", "API Tester")
    acct = _make_connected_account(email="api@gmail.com")
    user_store.add_connected_account(user.id, acct)
    return user


@pytest.fixture()
def _patch_lifespan():
    """Disable the real lifespan (scheduler) during tests."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    import server
    original = server.app.router.lifespan_context
    server.app.router.lifespan_context = _noop_lifespan
    yield
    server.app.router.lifespan_context = original


@pytest.mark.anyio
class TestFastAPIEndpoints:
    """Integration tests hitting the FastAPI routes with mocked providers."""

    @pytest.fixture(autouse=True)
    def _setup(self, _patch_lifespan):
        """Apply the lifespan patch to every test in this class."""
        pass

    # ── Health & Root ───────────────────────────────────

    async def test_health(self):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "uptime_seconds" in body

    async def test_root(self):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/")
        assert resp.status_code == 200
        assert "AutoMinds Email Assistant" in resp.text

    # ── GET /emails ─────────────────────────────────────

    @patch("gmail_provider.fetch_emails")
    @patch("email_brain.analyze_emails")
    async def test_get_emails(self, mock_analyze, mock_fetch, _seed_user):
        import server

        fake_emails = [_make_email(id="e1"), _make_email(id="e2")]
        mock_fetch.return_value = fake_emails
        mock_analyze.return_value = fake_emails

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/emails?user_id={_seed_user.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    async def test_get_emails_user_not_found(self):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/emails?user_id=ghost")
        assert resp.status_code == 404

    # ── POST /drafts ────────────────────────────────────

    @patch("gmail_provider.fetch_email_by_id")
    @patch("email_brain.draft_reply")
    async def test_create_draft(self, mock_draft_reply, mock_fetch_by_id, _seed_user):
        import server

        original = _make_email(id="orig1")
        mock_fetch_by_id.return_value = original

        draft = EmailDraft(
            id="d1",
            original_email_id="orig1",
            to="alice@example.com",
            subject="Re: Hello Test",
            body="Acknowledged.",
            status=DraftStatus.PENDING,
        )
        mock_draft_reply.return_value = draft

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/drafts?user_id={_seed_user.id}",
                json={"email_id": "orig1", "instructions": "Acknowledge", "tone": "professional"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["draft"]["to"] == "alice@example.com"
        assert data["auto_sent"] is False

    # ── GET /briefing ───────────────────────────────────

    @patch("scheduler.get_latest_briefing", return_value=None)
    @patch("gmail_provider.fetch_emails")
    @patch("email_brain.analyze_emails")
    @patch("email_brain.generate_briefing")
    @patch("scheduler._store_briefing")
    async def test_get_briefing(
        self, mock_store, mock_gen, mock_analyze, mock_fetch, mock_latest, _seed_user
    ):
        import server

        fake_emails = [
            _make_email(id="b1", priority=EmailPriority.URGENT, category=EmailCategory.ACTION_REQUIRED)
        ]
        mock_fetch.return_value = fake_emails
        mock_analyze.return_value = fake_emails

        briefing = DailyBriefing(
            user_id=_seed_user.id,
            total_unread=1,
            urgent_count=1,
            full_text="Morning briefing!",
            emails_analyzed=1,
        )
        mock_gen.return_value = briefing

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/briefing?user_id={_seed_user.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_unread"] == 1
        assert "Morning briefing" in data["full_text"]

    # ── GET /user ───────────────────────────────────────

    async def test_get_user(self, _seed_user):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/user?user_id={_seed_user.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "api@example.com"
        assert data["name"] == "API Tester"

    async def test_get_user_not_found(self):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/user?user_id=nonexistent")
        assert resp.status_code == 404

    # ── PUT /user/settings ──────────────────────────────

    @patch("scheduler.schedule_user_briefing")
    async def test_update_settings(self, mock_schedule, _seed_user):
        import server

        new_settings = {
            "briefing_time": "08:30",
            "briefing_timezone": "America/Chicago",
            "vip_contacts": ["vip@example.com"],
            "auto_send_contacts": [],
            "categories_enabled": True,
            "draft_tone": "casual",
            "notification_channel": "email",
        }

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.put(
                f"/user/settings?user_id={_seed_user.id}",
                json=new_settings,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["settings"]["briefing_time"] == "08:30"
        assert data["settings"]["draft_tone"] == "casual"
        mock_schedule.assert_called_once()

    # ── POST /user/vip ──────────────────────────────────

    async def test_add_vip_contact(self, _seed_user):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/user/vip?user_id={_seed_user.id}&contact_email=boss@acme.com"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "boss@acme.com" in data["vip_contacts"]

    async def test_add_vip_contact_idempotent(self, _seed_user):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            await ac.post(f"/user/vip?user_id={_seed_user.id}&contact_email=boss@acme.com")
            resp = await ac.post(f"/user/vip?user_id={_seed_user.id}&contact_email=boss@acme.com")

        data = resp.json()
        assert data["vip_contacts"].count("boss@acme.com") == 1

    # ── POST /user/auto-send ────────────────────────────

    async def test_enable_auto_send(self, _seed_user):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/user/auto-send?user_id={_seed_user.id}",
                json={"contact_email": "auto@example.com", "enabled": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "auto@example.com" in data["auto_send_contacts"]

    async def test_disable_auto_send(self, _seed_user):
        import server
        import user_store

        # Enable first
        user = user_store.get_user(_seed_user.id)
        user.settings.auto_send_contacts = ["auto@example.com"]
        user_store.save_user(user)

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                f"/user/auto-send?user_id={_seed_user.id}",
                json={"contact_email": "auto@example.com", "enabled": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "auto@example.com" not in data["auto_send_contacts"]

    # ── Edge cases ──────────────────────────────────────

    @patch("gmail_provider.fetch_emails", return_value=[])
    async def test_get_emails_empty(self, mock_fetch, _seed_user):
        import server

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/emails?user_id={_seed_user.id}&analyze=false")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    async def test_get_emails_no_connected_accounts(self):
        import server
        import user_store

        # user with 0 connected accounts
        user = user_store.create_user("bare@example.com")

        async with AsyncClient(
            transport=ASGITransport(app=server.app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/emails?user_id={user.id}")

        assert resp.status_code == 400


# ===================================================================
# pytest-anyio configuration
# ===================================================================

@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param
