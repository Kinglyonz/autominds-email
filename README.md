# AutoMinds Email Assistant

AI-powered email assistant built with FastAPI. Connects to Gmail and Outlook, uses Claude (Anthropic) to analyze, categorize, and prioritize your inbox, generates daily briefings, and drafts intelligent replies — all with human-in-the-loop approval.

## Features

- **Multi-provider support** — Gmail (Google OAuth) and Outlook (Microsoft Graph)
- **AI email analysis** — Categorization, priority scoring, sentiment detection via Claude
- **Daily briefings** — Scheduled summaries of what matters in your inbox
- **Smart draft replies** — AI-generated responses you approve before sending (with opt-in auto-send)
- **VIP contacts** — Flag important senders for priority treatment
- **Scheduled automation** — APScheduler handles daily briefing generation

---

## Quick Start (Local Development)

### 1. Install dependencies

```bash
cd autominds-email
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file:

```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Microsoft OAuth (optional)
MICROSOFT_CLIENT_ID=your-azure-app-id
MICROSOFT_CLIENT_SECRET=your-azure-secret
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/microsoft/callback

# App
APP_URL=http://localhost:8000
```

### 3. Run the server

```bash
uvicorn server:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Google Cloud Console Setup

Step-by-step to get Gmail OAuth credentials:

1. **Create a Google Cloud project**
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Click the project dropdown → **New Project** → name it (e.g. `AutoMinds Email`) → **Create**

2. **Enable the Gmail API**
   - Navigate to **APIs & Services → Library**
   - Search for **Gmail API** → click **Enable**

3. **Configure OAuth consent screen**
   - Go to **APIs & Services → OAuth consent screen**
   - Select **External** user type → **Create**
   - Fill in app name, support email, and developer email
   - Add scopes: `gmail.readonly`, `gmail.send`, `gmail.modify`, `gmail.labels`
   - Add your email as a test user (required while in testing mode)
   - Save

4. **Create OAuth credentials**
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: `AutoMinds Email`
   - Authorized redirect URIs: `http://localhost:8000/auth/google/callback`
   - Click **Create**

5. **Copy credentials**
   - Copy the **Client ID** and **Client Secret** into your `.env` file

---

## Microsoft Azure Setup (Optional)

For Outlook/Microsoft 365 email support:

1. **Register an application**
   - Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory → App registrations → New registration**
   - Name: `AutoMinds Email`
   - Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
   - Redirect URI: `http://localhost:8000/auth/microsoft/callback` (Web)

2. **Set API permissions**
   - Go to **API permissions → Add a permission → Microsoft Graph**
   - Delegated permissions: `Mail.Read`, `Mail.Send`, `Mail.ReadWrite`, `User.Read`
   - Grant admin consent if applicable

3. **Create a client secret**
   - Go to **Certificates & secrets → New client secret**
   - Copy the secret value into your `.env` file along with the Application (client) ID

---

## API Endpoints

### General

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Landing page |
| `GET` | `/health` | Health check — returns service status |

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/google` | Start Gmail OAuth flow — redirects to Google consent |
| `GET` | `/auth/google/callback` | Google OAuth callback — exchanges code for tokens |
| `GET` | `/auth/microsoft` | Start Outlook OAuth flow — redirects to Microsoft consent |
| `GET` | `/auth/microsoft/callback` | Microsoft OAuth callback — exchanges code for tokens |

### Emails

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/emails?user_id=X` | Fetch emails with AI analysis (categorization, priority, summary) |
| `GET` | `/emails/{id}?user_id=X` | Get a single email with full details |
| `POST` | `/emails/{id}/read?user_id=X` | Mark an email as read |
| `POST` | `/emails/{id}/label?user_id=X` | Add a label to an email |

### Briefings

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/briefing?user_id=X` | Get or generate today's daily email briefing |

### Drafts

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/drafts?user_id=X` | Create an AI-generated draft reply for an email |
| `GET` | `/drafts?user_id=X` | List all pending drafts for a user |
| `POST` | `/drafts/{id}/approve?user_id=X` | Approve and send a draft |
| `POST` | `/drafts/{id}/reject?user_id=X` | Reject and discard a draft |

### Send

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/send?user_id=X` | Send a new email (compose and send directly) |

### User & Settings

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/user?user_id=X` | Get user profile and settings |
| `PUT` | `/user/settings?user_id=X` | Update user preferences (briefing time, tone, etc.) |
| `POST` | `/user/vip?user_id=X` | Add a VIP contact (prioritized in briefings) |
| `DELETE` | `/user/vip?user_id=X` | Remove a VIP contact |
| `POST` | `/user/auto-send?user_id=X` | Toggle auto-send rules (skip approval for certain categories) |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/users` | List all registered users |
| `GET` | `/admin/scheduler` | View scheduler status and upcoming jobs |

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client /   │────▶│   server.py   │────▶│  email_brain.py  │
│   Frontend   │◀────│   (FastAPI)   │◀────│  (Claude AI)     │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                    ┌──────┴───────┐
                    │              │
             ┌──────▼──────┐ ┌────▼────────────┐
             │gmail_provider│ │outlook_provider  │
             │   .py        │ │   .py            │
             │(Google OAuth)│ │(Microsoft Graph) │
             └─────────────┘ └─────────────────┘
                    │              │
                    ▼              ▼
              Gmail API    Microsoft Graph API
```

| Module | Role |
|--------|------|
| `server.py` | FastAPI app — routes, auth flows, scheduling |
| `email_brain.py` | AI logic — calls Claude to analyze, categorize, draft replies, generate briefings |
| `gmail_provider.py` | Gmail integration — OAuth token management, fetch/send via Gmail API |
| `outlook_provider.py` | Outlook integration — OAuth token management, fetch/send via Microsoft Graph |
| `models.py` | Pydantic models — Email, Draft, User, Briefing schemas |
| `config.py` | Configuration — env var loading, app settings |

**Flow:**
1. User authenticates via OAuth (`/auth/google` or `/auth/microsoft`)
2. Server fetches emails from the connected provider
3. `email_brain.py` sends email content to Claude for analysis
4. Results are returned to the client with priority scores, categories, and summaries
5. APScheduler triggers daily briefing generation at the user's configured time

---

## Deployment

### Docker

```bash
docker build -t autominds-email .
docker run -p 8000:8000 --env-file .env autominds-email
```

Or with Docker Compose:

```bash
docker-compose up --build
```

### Railway

The project includes `railway.toml` and `Procfile` for one-click Railway deployment:

1. Push to a GitHub repository
2. Connect the repo in [Railway](https://railway.app)
3. Set environment variables in Railway dashboard
4. Deploy — Railway will use the `Procfile` automatically

---

## Pricing / Cost Notes

This service uses the Anthropic Claude API for AI analysis.

| Operation | Estimated Cost |
|-----------|---------------|
| Single email analysis | ~$0.01–$0.03 |
| Daily briefing (20 emails) | ~$0.10–$0.30 |
| Draft reply generation | ~$0.01–$0.03 |

Costs depend on email length and Claude model used. Monitor usage at [console.anthropic.com](https://console.anthropic.com).

> **Tip:** Set `ANTHROPIC_MODEL` in your `.env` to use `claude-3-haiku` for lower-cost analysis or `claude-3-opus` for higher quality.

---

## License

Proprietary — AutoMinds © 2026
