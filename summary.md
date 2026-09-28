# 🚀 Job & Internship Application Tracker - Feature Summary

Welcome to the comprehensive feature guide for the **Job & Internship Application Tracker**! This document provides a complete breakdown of all major system capabilities, new features, and technical architecture implemented in the project.

---

## 📌 Executive Summary

The **Job & Internship Application Tracker** is a full-stack, enterprise-grade application built with **Flask**, **SQLite**, **Vanilla JavaScript (ES6+)**, and modern **CSS (Glassmorphism & Dark Mode)**. It empowers job seekers and students to track applications, organize interview schedules, monitor response rates with real-time analytics, and receive automated follow-up email reminders.

---

## 🌟 Newly Added Core Features

### 📊 1. Analytics & Performance Insights Dashboard

Located via the **`[ 📊 Analytics ]`** button in the header toolbar, this module provides real-time conversion metrics and visual charts:

- **Top KPI Metric Cards**:
  - 📊 **Total Applications**: Total count of job submissions logged.
  - ⏱️ **Interview Rate**: Percentage of applications reaching the interview stage (`(Interviewing / Total) * 100`).
  - ✅ **Offer Rate**: Conversion rate from applications to job offers (`(Offered / Total) * 100`).
  - ❌ **Rejection Rate**: Rate of rejected applications (`(Rejected / Total) * 100`).
- **Status Funnel Breakdown Chart**: Animated horizontal progress bars detailing exact counts and percentages for `Applied`, `Interviewing`, `Offered`, and `Rejected`.
- **Status Proportion Donut Ring Chart**: Interactive SVG ring chart displaying proportional distribution of application statuses with total count centered.
- **Backend API**: Powered by `GET /api/analytics` returning user-isolated statistical JSON metrics.

---

### 📅 2. Smart Calendar System

Located via the **`[ 📅 Calendar ]`** button in the header toolbar, this feature unifies all critical job search dates into a single interactive calendar:

- **Aggregated Event Types**:
  - 🎤 **Interview Dates**: Purple event pills.
  - 📞 **Follow-up Reminders**: Amber event pills (explicit dates or automated 7-day stale alerts).
  - ⏰ **Application Deadlines**: Red event pills.
  - 📝 **Assessment Dates**: Blue event pills.
- **Month Navigation**: Switch between months dynamically (e.g. `< AUGUST 2026 >`).
- **Interactive Card Highlight & Scroll**: Clicking any event pill automatically closes the calendar, smoothly scrolls to the application card on the Kanban board, and triggers a glowing pulse animation (`app-card-highlight-pulse`).
- **Backend API**: Powered by `GET /api/calendar-events` returning aggregated event payloads.

---

### 🎤 3. Upcoming Interviews Row

Positioned prominently above the 4-column Kanban board and below the top stat counter bar:

- **At-a-Glance Cards**: Displays company name, job role, purple accent indicator (`●`), and formatted interview date (e.g. `Aug 29, 2026`).
- **Auto-Sync**: Automatically updates whenever an application status is moved to `Interviewing` or an interview date is set.

---

### 📋 4. 4-Column Kanban Board & Instant Search

- **Status Columns**: `Applied`, `Interviewing`, `Offered`, `Rejected`.
- **Inline Status Transition**: Update status via card dropdown; cards instantly move to the appropriate column with updated dynamic counters.
- **Instant Search Bar**: Filter cards live by company name or job title.
- **Stale Application Alert**: Applications with no updates for 7+ days are highlighted in amber with a `Follow-up Needed` indicator.

---

### 📧 5. Automated & Manual Email Reminders

- **Background Daemon Thread**: `services/scheduler.py` runs a background daemon thread checking SQLite database for applications requiring follow-ups (stale for 7+ days).
- **Manual "Send Email Reminder" Action**: One-click email dispatch sending custom HTML reminder emails to the user's registered inbox via SMTP.
- **Gmail SMTP Integration**: Secure credential management via `.env` (`MAIL_USERNAME`, `MAIL_PASSWORD`).

---

### 🔑 6. User Authentication & Multi-User Isolation

- **Google One Tap Sign-In**: Integrated Google OAuth 2.0 credential verification (`routes/auth.py`).
- **Standard Registration & Login**: Password hashing via Werkzeug security primitives (`generate_password_hash`, `check_password_hash`).
- **Data Isolation**: All database queries enforce `WHERE user_id = ?` to guarantee privacy and multi-tenant data isolation.

---

## 🗄️ Database Schema & Architecture

The system uses SQLite with dynamic auto-migration support (`database/db.py`):

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    google_id TEXT UNIQUE,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## 🧪 Automated Test Suite Verification

Comprehensive unit test suite implemented in `tests/test_routes.py`:

```bash
pytest tests/test_routes.py
```

### Verified Test Cases (9/9 Passed):

1. `test_index_redirect_unauthenticated`
2. `test_register_and_login`
3. `test_create_and_get_application`
4. `test_update_application_status`
5. `test_delete_application`
6. `test_calculate_days_since`
7. `test_send_reminder_email`
8. `test_upcoming_interview_date`
9. `test_get_analytics`

---

## 📁 File Structure Overview

```
Job and Intern Tracker/
├── app.py                     # Main Flask application entry point
├── config.py                  # Configuration loader
├── .env                       # Environment credentials (git-ignored)
├── .env.example               # Credential template for team setup
├── README.md                  # Detailed README & PPT Presentation Guide
├── summary.md                 # Complete feature summary (This file)
├── database/
│   ├── db.py                  # SQLite connection & schema auto-migrations
│   └── schema.sql             # SQL schema definitions
├── routes/
│   ├── applications.py        # Applications CRUD, Analytics API, Calendar API
│   └── auth.py                # Login, Register, Google OAuth routes
├── services/
│   ├── email_service.py       # SMTP email dispatcher
│   └── scheduler.py           # Background email daemon thread
├── static/
│   ├── css/style.css          # CSS styles (Glassmorphism dark theme)
│   └── js/app.js              # Interactivity, search, calendar & analytics logic
├── templates/
│   ├── base.html              # Base template, header & nav buttons
│   ├── dashboard.html         # Main dashboard, Kanban board & modals
│   ├── login.html             # Login view
│   ├── register.html          # Registration view
│   └── partials/
│       ├── _application_card.html      # Card component
│       └── _upcoming_interview_card.html # Interview card component
└── tests/
    └── test_routes.py         # Pytest automated route & API unit tests
```

---

## 🚀 Running locally

1. **Install Dependencies**:
   ```bash
   pip install flask pytest python-dotenv google-auth
   ```
2. **Setup Credentials**: Copy `.env.example` to `.env` and fill in credentials.
3. **Launch Server**:
   ```bash
   python app.py
   ```
4. **Access App**: Open `http://127.0.0.1:5000` in your browser.
