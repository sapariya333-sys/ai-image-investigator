"""
AI-Image Investigator — Database layer
Plain SQLite (no ORM) so the whole app has zero external DB dependency.
"""
import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "investigator.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    investigator TEXT,
    description TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    image_uid TEXT UNIQUE NOT NULL,
    original_filename TEXT,
    stored_path TEXT,
    mime_type TEXT,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    color_mode TEXT,
    sha256 TEXT,
    md5 TEXT,
    sha1 TEXT,
    phash TEXT,
    uploaded_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS metadata_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    category TEXT NOT NULL,        -- exif / gps / file / other
    field_name TEXT NOT NULL,
    field_value TEXT,
    source TEXT,                   -- e.g. 'EXIF', 'filesystem', 'derived'
    FOREIGN KEY (image_id) REFERENCES images(id)
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    derivative_id INTEGER,        -- NULL = ran on the original evidence file
    language TEXT,
    extracted_text TEXT,
    confidence REAL,
    FOREIGN KEY (image_id) REFERENCES images(id),
    FOREIGN KEY (derivative_id) REFERENCES derivatives(id)
);

CREATE TABLE IF NOT EXISTS manipulation_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    indicator TEXT NOT NULL,
    detail TEXT,
    severity TEXT,                 -- low / moderate / high
    ela_derivative_path TEXT,
    FOREIGN KEY (image_id) REFERENCES images(id)
);

CREATE TABLE IF NOT EXISTS derivatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    derivative_type TEXT NOT NULL, -- enhanced / ela / thumbnail
    label TEXT,
    stored_path TEXT,
    sha256 TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (image_id) REFERENCES images(id)
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    image_id INTEGER,
    event_time TEXT,               -- best-effort ISO timestamp, may be null
    event_label TEXT NOT NULL,
    source_field TEXT,             -- which metadata field produced this entry
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS investigator_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    image_id INTEGER,
    note TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (case_id) REFERENCES cases(id),
    FOREIGN KEY (image_id) REFERENCES images(id)
);

CREATE INDEX IF NOT EXISTS idx_images_case ON images(case_id);
CREATE INDEX IF NOT EXISTS idx_metadata_image ON metadata_findings(image_id);
CREATE INDEX IF NOT EXISTS idx_timeline_case ON timeline_events(case_id);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        result = None
        if fetchone:
            row = cur.fetchone()
            result = dict(row) if row else None
        elif fetchall:
            result = [dict(r) for r in cur.fetchall()]
        if commit:
            conn.commit()
            result = cur.lastrowid
        return result
