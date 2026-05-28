-- ============================================================
-- Multi-Agent Orchestration System — Supabase Schema
-- Run this once in your Supabase SQL Editor
-- ============================================================

-- Tasks: full agent state persisted per task
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    original_request TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'planning',
    plan_confidence FLOAT DEFAULT 0,
    reviewer_score  FLOAT DEFAULT 0,
    reviewer_feedback TEXT,
    final_output    TEXT,
    awaiting_human  BOOLEAN DEFAULT FALSE,
    human_feedback  TEXT,
    total_tokens    INT DEFAULT 0,
    total_tool_calls INT DEFAULT 0,
    errors          JSONB DEFAULT '[]',
    execution_plan  JSONB DEFAULT '[]',
    completed_subtasks JSONB DEFAULT '[]',
    escalations     JSONB DEFAULT '[]',
    memories_used   JSONB DEFAULT '[]',
    trace           JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_updated_at ON tasks;
CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Tool calls: full audit log of every tool invocation
CREATE TABLE IF NOT EXISTS tool_calls (
    id          BIGSERIAL PRIMARY KEY,
    task_id     TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    agent       TEXT NOT NULL,
    inputs      JSONB,
    output      JSONB,
    success     BOOLEAN,
    error       TEXT,
    latency_s   FLOAT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HITL events: durable audit trail for every escalation
CREATE TABLE IF NOT EXISTS hitl_events (
    id              TEXT PRIMARY KEY,
    task_id         TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    task_request    TEXT,
    trigger         TEXT NOT NULL,
    level           TEXT NOT NULL,
    context         JSONB,
    status          TEXT DEFAULT 'pending',
    human_response  TEXT,
    modified_output TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_tasks_user_id   ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created   ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_hitl_task       ON hitl_events(task_id);
CREATE INDEX IF NOT EXISTS idx_hitl_status     ON hitl_events(status);
