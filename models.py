import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.environ.get("DB_PATH", "practice.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        student_id TEXT NOT NULL,
        class_id INTEGER,
        has_submitted INTEGER DEFAULT 0,
        submitted_at TEXT,
        assigned_position_id INTEGER,
        FOREIGN KEY (class_id) REFERENCES classes(id),
        UNIQUE(student_id)
    );
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_name TEXT NOT NULL,
        quota INTEGER NOT NULL DEFAULT 1,
        current_count INTEGER NOT NULL DEFAULT 0,
        instructor TEXT,
        requirements TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS position_classes (
        position_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        PRIMARY KEY (position_id, class_id),
        FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
        FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS student_position_assign (
        student_id INTEGER NOT NULL,
        position_id INTEGER NOT NULL,
        PRIMARY KEY (student_id),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (position_id) REFERENCES positions(id)
    );
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        position_id INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (position_id) REFERENCES positions(id),
        UNIQUE(student_id)
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    # default admin
    pw = generate_password_hash("admin123")
    conn.execute("INSERT OR IGNORE INTO admin (username, password_hash) VALUES (?, ?)", ("admin", pw))
    # default settings
    for k, v in [("system_open", "0"), ("open_time", ""), ("close_time", "")]:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def check_admin(username, password):
    conn = get_db()
    row = conn.execute("SELECT * FROM admin WHERE username=?", (username,)).fetchone()
    conn.close()
    return row and check_password_hash(row["password_hash"], password)

def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if row and row["value"]:
        return row["value"]
    return default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()
