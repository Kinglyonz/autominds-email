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
    stripe_customer_id TEXT,
    subscription_id TEXT,
    plan_expires_at TIMESTAMPTZ,
    actions_used INTEGER DEFAULT 0,
    actions_reset_at TIMESTAMPTZ,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active TIMESTAMPTZ
);

-- Add billing columns if table already exists
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS actions_used INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS actions_reset_at TIMESTAMPTZ;

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
-- EMAIL RULES (user-defined automation triggers)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS email_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,      -- 'sender', 'subject', 'category', 'priority', 'keyword'
    conditions JSONB DEFAULT '{}',   -- {"sender_contains": "boss@x.com"} or {"priority": "urgent"}
    action_type TEXT NOT NULL,       -- 'auto_draft', 'label', 'forward', 'create_task', 'notify', 'mark_read'
    action_config JSONB DEFAULT '{}', -- {"draft_instructions": "...", "tone": "professional"}
    enabled BOOLEAN DEFAULT true,
    times_triggered INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_rules_user_id ON email_rules(user_id);

-- ═══════════════════════════════════════════════════════════
-- AUTOMATIONS (recurring scheduled tasks)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    schedule_type TEXT NOT NULL,     -- 'daily', 'weekly', 'monthly'
    day_of_week INT DEFAULT 1,      -- 0=Mon..6=Sun
    day_of_month INT DEFAULT 1,     -- 1-28
    hour INT DEFAULT 9,
    minute INT DEFAULT 0,
    timezone TEXT DEFAULT 'America/New_York',
    action TEXT NOT NULL,            -- 'weekly_digest', 'monthly_report', 'follow_up_check', 'inbox_cleanup'
    enabled BOOLEAN DEFAULT true,
    last_run TIMESTAMPTZ,
    run_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automations_user_id ON automations(user_id);

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
ALTER TABLE email_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE automations ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (your backend uses service key)
CREATE POLICY "Service role full access" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON connected_accounts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON drafts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON agent_state FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON agent_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON briefings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON email_rules FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON automations FOR ALL USING (true) WITH CHECK (true);
