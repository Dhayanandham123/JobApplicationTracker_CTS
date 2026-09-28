CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    google_id TEXT UNIQUE,
    avatar_url TEXT,
    full_name TEXT,
    phone TEXT,
    location TEXT,
    headline TEXT,
    university TEXT,
    grad_year TEXT,
    resume_text TEXT,
    resume_filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    notify_followup INTEGER DEFAULT 1,
    notify_interview INTEGER DEFAULT 1,
    reminder_time TEXT DEFAULT '1 Day Before',
    email_notifications INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'light',
    dashboard_view TEXT DEFAULT 'kanban',
    card_density TEXT DEFAULT 'comfortable',
    show_stats INTEGER DEFAULT 1,
    show_warnings INTEGER DEFAULT 1,
    show_interview_dates INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resume_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    version_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Applied', 'Interviewing', 'Offered', 'Rejected')),
    date_applied DATE NOT NULL,
    last_updated DATE NOT NULL,
    notes TEXT,
    last_email_sent DATE,
    interview_date DATE,
    deadline_date DATE,
    assessment_date DATE,
    followup_date DATE,
    job_url TEXT,
    salary TEXT,
    location TEXT,
    job_type TEXT DEFAULT 'Full-time',
    last_interview_reminder_sent DATE,
    last_assessment_reminder_sent DATE,
    fit_score INTEGER,
    missing_skills TEXT,
    resume_version TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    provider TEXT DEFAULT 'google',
    email_address TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expiry TIMESTAMP,
    last_synced_at TIMESTAMP,
    sync_cursor TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    thread_id TEXT,
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    snippet TEXT,
    body_text TEXT,
    body_html_sanitized TEXT,
    received_at TIMESTAMP,
    classification TEXT,
    confidence_score REAL,
    extracted_data TEXT,
    matched_application_id INTEGER,
    match_confidence REAL,
    match_status TEXT DEFAULT 'pending',
    is_action_required INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (matched_application_id) REFERENCES applications(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS application_timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_title TEXT NOT NULL,
    event_description TEXT,
    event_date TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'MANUAL',
    email_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
