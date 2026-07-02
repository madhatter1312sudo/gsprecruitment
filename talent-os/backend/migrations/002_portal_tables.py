"""
Talent OS — Schema migration: portal tables (saved_jobs, pipeline_entries,
user_clients, audit_log, site_content, system_settings, contact_submissions).
Run against the PostgreSQL database directly.
"""

MIGRATION_SQL = """
-- ── Saved Jobs (candidate favorites) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_jobs (
    id              SERIAL PRIMARY KEY,
    candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id          INTEGER NOT NULL REFERENCES job_orders(id) ON DELETE CASCADE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_jobs_candidate ON saved_jobs(candidate_id);

-- ── Pipeline Entries (client recruitment pipeline) ─────────────────────
CREATE TABLE IF NOT EXISTS pipeline_entries (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id          INTEGER NOT NULL REFERENCES job_orders(id) ON DELETE CASCADE,
    stage           VARCHAR(50) DEFAULT 'sourced',
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP,
    UNIQUE (client_id, candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_client ON pipeline_entries(client_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_candidate ON pipeline_entries(candidate_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON pipeline_entries(stage);

-- ── User-Client Mapping (many-to-many) ────────────────────────────────
CREATE TABLE IF NOT EXISTS user_clients (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    role_in_company VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_user_clients_user ON user_clients(user_id);
CREATE INDEX IF NOT EXISTS idx_user_clients_client ON user_clients(client_id);

-- ── Audit Log (admin actions) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    action          VARCHAR(100) NOT NULL,
    actor_id        INTEGER REFERENCES users(id),
    target_type     VARCHAR(50),
    target_id       INTEGER,
    changes         JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);

-- ── Site Content (CMS for public pages) ───────────────────────────────
CREATE TABLE IF NOT EXISTS site_content (
    id              SERIAL PRIMARY KEY,
    section         VARCHAR(100) NOT NULL,
    key             VARCHAR(100) NOT NULL,
    value           TEXT NOT NULL,
    label           VARCHAR(255),
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP,
    UNIQUE (section, key)
);

CREATE INDEX IF NOT EXISTS idx_site_content_section ON site_content(section);

-- Insert default content
INSERT INTO site_content (section, key, value, label, sort_order) VALUES
    ('hero', 'title', 'Find Your Next Tech Role in Brainport Eindhoven', 'Hero Title', 1),
    ('hero', 'subtitle', 'GSP Recruitment connects top tech talent with leading companies in the Brainport Eindhoven region.', 'Hero Subtitle', 2),
    ('hero', 'cta_text', 'Get Started', 'CTA Button Text', 3),
    ('features', 'title', 'How It Works', 'Features Section Title', 1),
    ('about', 'title', 'About GSP Recruitment', 'About Section Title', 1)
ON CONFLICT (section, key) DO NOTHING;

-- ── System Settings (key-value config) ────────────────────────────────
CREATE TABLE IF NOT EXISTS system_settings (
    id              SERIAL PRIMARY KEY,
    key             VARCHAR(100) NOT NULL UNIQUE,
    value           TEXT NOT NULL,
    description     TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP
);

-- Insert default settings
INSERT INTO system_settings (key, value, description) VALUES
    ('platform_name', 'GSP Recruitment', 'Platform display name'),
    ('contact_email', 'hello@gsprecruitment.nl', 'Public contact email'),
    ('maintenance_mode', 'false', 'Enable maintenance mode'),
    ('default_fee_percentage', '20', 'Default placement fee percentage')
ON CONFLICT (key) DO NOTHING;

-- ── Contact Submissions (lead/contact form) ───────────────────────────
CREATE TABLE IF NOT EXISTS contact_submissions (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    company         VARCHAR(255),
    phone           VARCHAR(50),
    message         TEXT NOT NULL,
    interest_type   VARCHAR(100),
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_submissions_created ON contact_submissions(created_at DESC);
"""

if __name__ == "__main__":
    import asyncio
    import asyncpg
    import os

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    async def run():
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
        try:
            for statement in MIGRATION_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)
            print("Migration completed: portal tables created.")
        finally:
            await conn.close()

    asyncio.run(run())