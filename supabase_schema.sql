-- AutoMinds Email Assistant - Supabase Schema
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard → SQL Editor)
-- This creates all tables needed for persistent user, draft, and agent storage.

-- ═══════════════════════════════════════════════════════════
-- USERS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT '',
    tier TEXT DEFAULT 'free',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active TIMESTAMPTZ
);

-- ═══════════════════════════════════════════════════════════
-- CONNECTED ACCOUNTS (OAuth tokens for Gmail/Outlook)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS connected_accounts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_expiry TIMESTAMPTZ,
    connected_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true,
    UNIQUE(user_id, email)
);

CREATE INDEX IF NOT EXISTS idx_connected_accounts_user_id ON connected_accounts(user_id);

-- ═══════════════════════════════════════════════════════════
-- DRAFTS (AI-generated email replies awaiting approval)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_email_id TEXT NOT NULL,
    to_address TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    instructions TEXT DEFAULT '',
    safety_flags JSONB DEFAULT '[]',
    safety_severity TEXT DEFAULT 'none',
    source_provider TEXT,
    source_email TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);

-- ═══════════════════════════════════════════════════════════
-- AGENT STATE (processed email IDs for idempotency)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS agent_state (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    processed_ids JSONB DEFAULT '[]',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════
-- AGENT LOGS (audit trail of what the autonomous agent did)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS agent_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    log_type TEXT DEFAULT 'user_cycle',
    cycle_start TIMESTAMPTZ,
    cycle_end TIMESTAMPTZ,
    elapsed_seconds FLOAT,
    emails_processed INT DEFAULT 0,
    errors JSONB DEFAULT '[]',
    actions JSONB DEFAULT '[]',
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_user_id ON agent_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_logs_created_at ON agent_logs(created_at DESC);

-- ═══════════════════════════════════════════════════════════
-- BRIEFINGS (cached daily briefings)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS briefings (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    briefing_date DATE NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, briefing_date)
);

CREATE INDEX IF NOT EXISTS idx_briefings_user_date ON briefings(user_id, briefing_date DESC);

-- ═══════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY (disabled for service key access)
-- Enable these later when you add user-facing auth
-- ═══════════════════════════════════════════════════════════

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE connected_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (your backend uses service key)
CREATE POLICY "Service role full access" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON connected_accounts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON drafts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON agent_state FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON agent_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON briefings FOR ALL USING (true) WITH CHECK (true);
