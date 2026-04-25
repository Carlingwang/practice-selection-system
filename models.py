import sqlite3
import os
from datetime import datetime
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
    );
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'draft',
        open_time TEXT,
        close_time TEXT,
        timer_enabled INTEGER DEFAULT 0,
        random_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        project_id INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(name, project_id)
    );
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        student_id TEXT NOT NULL,
        class_id INTEGER,
        project_id INTEGER NOT NULL DEFAULT 1,
        has_submitted INTEGER DEFAULT 0,
        submitted_at TEXT,
        assigned_position_id INTEGER,
        FOREIGN KEY (class_id) REFERENCES classes(id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(student_id, project_id)
    );
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_name TEXT NOT NULL,
        quota INTEGER NOT NULL DEFAULT 1,
        current_count INTEGER NOT NULL DEFAULT 0,
        instructor TEXT,
        requirements TEXT,
        project_id INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
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
        project_id INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (student_id, project_id),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (position_id) REFERENCES positions(id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        position_id INTEGER NOT NULL,
        project_id INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (position_id) REFERENCES positions(id),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(student_id, project_id)
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT NOT NULL,
        value TEXT,
        project_id INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (key, project_id)
    );
    """)
    conn.execute("INSERT OR IGNORE INTO projects (id, name, description, status) VALUES (1, '默认项目', '系统默认项目', 'close')")
    conn.commit()
    conn.close()
    conn = get_db()
    row = conn.execute("SELECT * FROM admin WHERE username=?", (username,)).fetchone()
    conn.close()
def get_setting(key, default="", project_id=0):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=? AND project_id=?", (key, project_id)).fetchone()
    conn.close()
    if row and row["value"]:
        return row["value"]
    return default
def set_setting(key, value, project_id=0):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value, project_id) VALUES (?, ?, ?)", (key, str(value), project_id))
    conn.commit()
    conn.close()
def get_project_mode(project_id):
    conn = get_db()
    row = conn.execute("SELECT status FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return row["status"] if row else "close"
def set_project_mode(project_id, mode):
    conn = get_db()
    conn.execute("UPDATE projects SET status=? WHERE id=?", (mode, project_id))
    conn.commit()
    conn.close()