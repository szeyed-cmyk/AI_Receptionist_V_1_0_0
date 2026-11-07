-- Demo data for reviewers and buyers. Fictional business only.
-- Apply after schema.sql:
--   sqlite3 data/ai_receptionist.db < database/seed.sql
--
-- Admin login is NOT seeded here. Create it at /admin/setup or via
-- ADMIN_USERNAME / ADMIN_PASSWORD in .env (hashed on first login), or /admin/setup with SETUP_TOKEN.

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO settings (key, value) VALUES
('business_name', 'Harborview Dental Demo'),
('opening_hour', '9'),
('closing_hour', '18'),
('closed_days', 'sunday'),
('holiday_dates', '2099-12-25'),
('admin_role', 'admin'),
('ai_base_url', ''),
('ai_model', ''),
('ai_api_key', '');

INSERT INTO knowledge_items (question, answer, category, is_active, created_at) VALUES
('What are your opening hours?',
 'Monday to Saturday, 9 AM to 6 PM. Closed on Sunday and listed holidays.',
 'general', 1, datetime('now')),
('Where are you located?',
 'We are a demo clinic at 100 Harbor Lane (fictional address for this sample).',
 'general', 1, datetime('now')),
('How long is each appointment?',
 'Each appointment is a 60-minute slot.',
 'booking', 1, datetime('now')),
('Can I book twice with the same phone?',
 'No. Each phone number may have only one confirmed appointment at a time.',
 'booking', 1, datetime('now')),
('Do you offer teeth whitening?',
 'Yes. Ask the receptionist to book a whitening consultation.',
 'services', 1, datetime('now'));

INSERT INTO conversations (id, channel, customer_name, customer_phone, status, created_at, updated_at)
VALUES
(1, 'web', 'Alex Rivera', '555-0101', 'active', datetime('now', '-2 days'), datetime('now', '-2 days')),
(2, 'web', 'Jordan Lee', '555-0102', 'closed', datetime('now', '-1 days'), datetime('now', '-1 days'));

INSERT INTO messages (conversation_id, role, content, created_at) VALUES
(1, 'user', 'Hi, what are your hours?', datetime('now', '-2 days')),
(1, 'assistant', 'We are open Monday to Saturday, 9 AM to 6 PM. Closed Sunday.', datetime('now', '-2 days')),
(1, 'user', 'I would like a checkup next Monday at 10am. My name is Alex Rivera, phone 555-0101.', datetime('now', '-2 days')),
(1, 'assistant', 'Your checkup is confirmed for Monday at 10:00 AM – 11:00 AM.', datetime('now', '-2 days')),
(2, 'user', 'Do you do whitening?', datetime('now', '-1 days')),
(2, 'assistant', 'Yes. We offer whitening consultations. Would you like to book one?', datetime('now', '-1 days'));

-- Use a far-future weekday morning so demo data stays valid for a long time.
INSERT INTO appointments (
  conversation_id, customer_name, customer_phone, service,
  appointment_time, duration_minutes, notes, status, created_at
) VALUES
(1, 'Alex Rivera', '555-0101', 'Checkup',
 '2099-06-01 10:00:00', 60, 'Demo booking', 'confirmed', datetime('now', '-2 days')),
(2, 'Jordan Lee', '555-0102', 'Whitening consult',
 '2099-06-02 14:00:00', 60, 'Demo booking', 'confirmed', datetime('now', '-1 days'));
