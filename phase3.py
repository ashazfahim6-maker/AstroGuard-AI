"""SQLite persistence for AstroGuard Phase 3 prototype features."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    assessment_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    fatigue INTEGER NOT NULL CHECK(fatigue BETWEEN 1 AND 5),
    stress INTEGER NOT NULL CHECK(stress BETWEEN 1 AND 5),
    sleep_quality INTEGER NOT NULL CHECK(sleep_quality BETWEEN 1 AND 5),
    symptoms_json TEXT NOT NULL,
    recent_activity TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    client_id TEXT UNIQUE,
    UNIQUE(profile_id, assessment_date)
);
CREATE INDEX IF NOT EXISTS idx_assessments_profile_date
    ON assessments(profile_id, assessment_date DESC);

CREATE TABLE IF NOT EXISTS outgoing_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deliver_at TEXT NOT NULL,
    delivered_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('queued', 'delivered')),
    report_kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    delay_seconds INTEGER NOT NULL,
    client_id TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_reports_profile_created
    ON outgoing_reports(profile_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sync_receipts (
    client_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    processed_at TEXT NOT NULL
);
"""


def connect(path):
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


@contextmanager
def database_session(path):
    connection = connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_database(path):
    with database_session(path) as database:
        database.executescript(SCHEMA)
        columns = {row['name'] for row in database.execute('PRAGMA table_info(assessments)')}
        if 'recent_activity' not in columns:
            database.execute("ALTER TABLE assessments ADD COLUMN recent_activity TEXT NOT NULL DEFAULT ''")


def assessment_dict(row):
    result = dict(row)
    result['symptoms'] = json.loads(result.pop('symptoms_json'))
    return result


def report_dict(row):
    result = dict(row)
    result['payload'] = json.loads(result.pop('payload_json'))
    return result


def save_assessment(path, profile_id, data, now):
    client_id = data.get('client_id')
    symptoms_json = json.dumps(data['symptoms'], separators=(',', ':'))
    with database_session(path) as database:
        if client_id:
            receipt = database.execute(
                "SELECT record_id FROM sync_receipts WHERE client_id=? AND resource_type='assessment'",
                (client_id,)
            ).fetchone()
            if receipt:
                existing = database.execute('SELECT * FROM assessments WHERE id=?', (receipt['record_id'],)).fetchone()
                return assessment_dict(existing), False
        database.execute(
            """INSERT INTO assessments
               (profile_id, assessment_date, created_at, updated_at, fatigue, stress,
                sleep_quality, symptoms_json, recent_activity, notes, client_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, assessment_date) DO UPDATE SET
                 updated_at=excluded.updated_at, fatigue=excluded.fatigue,
                 stress=excluded.stress, sleep_quality=excluded.sleep_quality,
                 symptoms_json=excluded.symptoms_json, recent_activity=excluded.recent_activity,
                 notes=excluded.notes,
                 client_id=assessments.client_id""",
            (profile_id, data['assessment_date'], now, now, data['fatigue'], data['stress'],
             data['sleep_quality'], symptoms_json, data['recent_activity'], data['notes'], client_id)
        )
        row = database.execute(
            'SELECT * FROM assessments WHERE profile_id = ? AND assessment_date = ?',
            (profile_id, data['assessment_date'])
        ).fetchone()
        if client_id:
            database.execute(
                "INSERT OR IGNORE INTO sync_receipts(client_id, resource_type, record_id, processed_at) VALUES (?, 'assessment', ?, ?)",
                (client_id, row['id'], now)
            )
        return assessment_dict(row), True


def list_assessments(path, profile_id, limit=30):
    with database_session(path) as database:
        rows = database.execute(
            'SELECT * FROM assessments WHERE profile_id = ? ORDER BY assessment_date DESC, id DESC LIMIT ?',
            (profile_id, limit)
        ).fetchall()
    return [assessment_dict(row) for row in rows]


def queue_report(path, profile_id, data, created_at, deliver_at):
    client_id = data.get('client_id')
    with database_session(path) as database:
        if client_id:
            existing = database.execute(
                'SELECT * FROM outgoing_reports WHERE client_id = ?', (client_id,)
            ).fetchone()
            if existing:
                return report_dict(existing), False
        cursor = database.execute(
            """INSERT INTO outgoing_reports
               (profile_id, created_at, deliver_at, delivered_at, status, report_kind,
                subject, payload_json, delay_seconds, client_id)
               VALUES (?, ?, ?, NULL, 'queued', ?, ?, ?, ?, ?)""",
            (profile_id, created_at, deliver_at, data['report_kind'], data['subject'],
             json.dumps(data['payload'], separators=(',', ':')), data['delay_seconds'], client_id)
        )
        row = database.execute('SELECT * FROM outgoing_reports WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return report_dict(row), True


def list_reports(path, profile_id, limit=50):
    with database_session(path) as database:
        rows = database.execute(
            'SELECT * FROM outgoing_reports WHERE profile_id=? ORDER BY created_at DESC, id DESC LIMIT ?',
            (profile_id, limit)
        ).fetchall()
    return [report_dict(row) for row in rows]


def synchronize_reports(path, profile_id, now):
    """Simulate a communications synchronization and deliver only eligible reports."""
    with database_session(path) as database:
        cursor = database.execute(
            """UPDATE outgoing_reports SET status='delivered', delivered_at=?
               WHERE profile_id=? AND status='queued' AND deliver_at<=?""",
            (now, profile_id, now)
        )
        rows = database.execute(
            'SELECT * FROM outgoing_reports WHERE profile_id=? ORDER BY created_at DESC, id DESC LIMIT 50',
            (profile_id,)
        ).fetchall()
    return [report_dict(row) for row in rows], cursor.rowcount
