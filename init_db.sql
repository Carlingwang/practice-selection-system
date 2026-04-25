-- 实习选岗系统数据库初始化（干净版本，无数据）
-- 使用方法：sqlite3 practice.db < init_db.sql

CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
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

-- 默认管理员（密码：Wenjuan13579@）
INSERT OR IGNORE INTO admin (username, password_hash) VALUES ('kayson', 'pbkdf2:sha256:600000$default$hash');

-- 默认项目
INSERT OR IGNORE INTO projects (id, name, description, status) VALUES (1, '默认项目', '系统默认项目', 'close');
