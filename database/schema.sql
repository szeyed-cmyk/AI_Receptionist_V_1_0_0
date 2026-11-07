-- FrontDesk AI — full SQLite schema.
-- Matches app/models.py exactly (columns, NOT NULL, FKs + ON DELETE rules, indexes);
-- verified by FrontDesk Project/tests/test_audit_v106.py::test_schema_sql_matches_sqlalchemy_models.
-- The application also creates these tables on startup via SQLAlchemy metadata. You can instead initialize with:
--   sqlite3 data/ai_receptionist.db < database/schema.sql
--   sqlite3 data/ai_receptionist.db < database/seed.sql

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER NOT NULL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER NOT NULL PRIMARY KEY,
    question VARCHAR(500) NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(100) DEFAULT 'general',
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER NOT NULL PRIMARY KEY,
    channel VARCHAR(50) DEFAULT 'web',
    external_id VARCHAR(200),
    visitor_token VARCHAR(64),
    customer_name VARCHAR(200),
    customer_phone VARCHAR(50),
    status VARCHAR(50) DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME
);

CREATE INDEX IF NOT EXISTS ix_conversations_external_id ON conversations(external_id);
CREATE INDEX IF NOT EXISTS ix_conversations_visitor_token ON conversations(visitor_token);
CREATE INDEX IF NOT EXISTS ix_conversations_updated_at ON conversations(updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER NOT NULL PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER NOT NULL PRIMARY KEY,
    conversation_id INTEGER,
    customer_name VARCHAR(200) NOT NULL,
    customer_phone VARCHAR(50),
    service VARCHAR(200),
    appointment_time DATETIME NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    notes TEXT,
    status VARCHAR(50) DEFAULT 'confirmed',
    created_at DATETIME,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_appointments_conversation_id ON appointments(conversation_id);
CREATE INDEX IF NOT EXISTS ix_appointments_phone_time ON appointments(customer_phone, appointment_time);
