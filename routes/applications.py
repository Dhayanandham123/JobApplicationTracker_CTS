from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, g, current_app
from datetime import datetime, date
from database.db import get_db
from routes.auth import login_required
from services.email_service import send_followup_email

applications_bp = Blueprint('applications', __name__)

VALID_STATUSES = ['Applied', 'Interviewing', 'Offered', 'Rejected']

def calculate_days_since(val):
    if not val:
        return 0
    if isinstance(val, datetime):
        val = val.date()
    if isinstance(val, date):
        delta = (date.today() - val).days
        return max(0, delta)
    try:
        updated_date = datetime.strptime(str(val), '%Y-%m-%d').date()
        delta = (date.today() - updated_date).days
        return max(0, delta)
    except (ValueError, TypeError):
        return 0

def format_application_row(row):
    app_dict = dict(row)
    date_keys = ['date_applied', 'last_updated', 'interview_date', 'deadline_date', 'assessment_date', 'followup_date', 'last_email_sent', 'last_interview_reminder_sent', 'last_assessment_reminder_sent']
    for key in date_keys:
        if isinstance(app_dict.get(key), (date, datetime)):
            app_dict[key] = app_dict[key].strftime('%Y-%m-%d')
        elif app_dict.get(key) is not None:
            app_dict[key] = str(app_dict[key])

    days_since = calculate_days_since(app_dict.get('last_updated') or app_dict.get('date_applied'))
    app_dict['days_since_update'] = days_since
    app_dict['needs_followup'] = days_since >= 7 and app_dict['status'] in ['Applied', 'Interviewing']

    # Formatted display dates
    for key in ['interview_date', 'deadline_date', 'assessment_date', 'followup_date', 'last_email_sent', 'last_interview_reminder_sent', 'last_assessment_reminder_sent']:
        fmt_key = f"formatted_{key}"
        val = app_dict.get(key)
        if val:
            try:
                d = datetime.strptime(val, '%Y-%m-%d')
                app_dict[fmt_key] = d.strftime('%b %d, %Y')
            except ValueError:
                app_dict[fmt_key] = val
        else:
            app_dict[fmt_key] = None

    # Parse missing_skills JSON list
    raw_skills = app_dict.get('missing_skills')
    if raw_skills:
        try:
            app_dict['missing_skills_list'] = json.loads(raw_skills) if isinstance(raw_skills, str) else list(raw_skills)
        except Exception:
            app_dict['missing_skills_list'] = []
    else:
        app_dict['missing_skills_list'] = []

    return app_dict

def _active_apps_filter(alias=''):
    """SQL fragment excluding soft-archived applications (NULL-safe for legacy DBs)."""
    prefix = f"{alias}." if alias else ""
    return f"({prefix}archived = 0 OR {prefix}archived IS NULL)"


@applications_bp.route('/')
@login_required
def index():
    user_id = session['user_id']
    db = get_db()
    include_archived = request.args.get('include_archived') == '1'
    archived_clause = '' if include_archived else f'AND {_active_apps_filter()}'
    rows = db.execute(f'SELECT * FROM applications WHERE user_id = ? {archived_clause} ORDER BY last_updated DESC, id DESC', (user_id,)).fetchall()
    applications = [format_application_row(r) for r in rows]

    counts = {
        'total': len(applications),
        'Applied': sum(1 for a in applications if a['status'] == 'Applied'),
        'Interviewing': sum(1 for a in applications if a['status'] == 'Interviewing'),
        'Offered': sum(1 for a in applications if a['status'] == 'Offered'),
        'Rejected': sum(1 for a in applications if a['status'] == 'Rejected'),
        'needs_followup': sum(1 for a in applications if a['needs_followup'])
    }

    grouped = {
        'Applied': [a for a in applications if a['status'] == 'Applied'],
        'Interviewing': [a for a in applications if a['status'] == 'Interviewing'],
        'Offered': [a for a in applications if a['status'] == 'Offered'],
        'Rejected': [a for a in applications if a['status'] == 'Rejected']
    }

    # Upcoming interviews filter
    upcoming_interviews = [
        a for a in applications 
        if a['status'] == 'Interviewing' or a.get('interview_date')
    ]
    upcoming_interviews.sort(
        key=lambda x: x.get('interview_date') or x.get('last_updated') or '',
        reverse=False
    )

    # Follow-up applications filter
    followup_applications = [
        a for a in applications
        if a.get('needs_followup')
    ]
    followup_applications.sort(
        key=lambda x: x.get('days_since_update', 0),
        reverse=True
    )

    today_str = date.today().strftime('%Y-%m-%d')
    
    resume_versions = db.execute('SELECT * FROM resume_versions WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    return render_template('dashboard.html', 
                           grouped=grouped, 
                           counts=counts, 
                           today_str=today_str,
                           all_applications=applications,
                           upcoming_interviews=upcoming_interviews,
                           followup_applications=followup_applications,
                           resume_versions=resume_versions,
                           current_user=g.user)

@applications_bp.route('/api/calendar-events', methods=['GET'])
@login_required
def get_calendar_events():
    user_id = session['user_id']
    db = get_db()
    rows = db.execute(f'SELECT * FROM applications WHERE user_id = ? AND {_active_apps_filter()} ORDER BY date_applied ASC', (user_id,)).fetchall()
    events = []

    for r in rows:
        app = format_application_row(r)
        app_id = app['id']
        company = app['company_name']
        title = app['job_title']
        status = app['status']

        meta = {
            'location': app.get('location') or 'Remote',
            'salary': app.get('salary') or 'Competitive',
            'job_type': app.get('job_type') or 'Full-time',
            'notes': app.get('notes') or '',
            'fit_score': app.get('fit_score'),
            'job_url': app.get('job_url') or '',
            'resume_version': app.get('resume_version') or '',
            'date_applied': app.get('date_applied'),
            'interview_date': app.get('interview_date'),
            'followup_date': app.get('followup_date'),
            'assessment_date': app.get('assessment_date')
        }

        # 1. Date Applied / Outcome Event
        if app.get('date_applied'):
            events.append({
                'app_id': app_id,
                'company_name': company,
                'job_title': title,
                'status': status,
                'event_type': status.lower(),
                'label': status,
                'date': app['date_applied'],
                'meta': meta
            })

        # 2. Interview Date Event (if distinct from date_applied)
        if app.get('interview_date') and app.get('interview_date') != app.get('date_applied'):
            events.append({
                'app_id': app_id,
                'company_name': company,
                'job_title': title,
                'status': 'Interviewing' if status == 'Interviewing' else status,
                'event_type': 'interviewing' if status == 'Interviewing' else status.lower(),
                'label': 'Interview Scheduled' if status == 'Interviewing' else status,
                'date': app['interview_date'],
                'meta': meta
            })

        # 3. Assessment Date Event
        if app.get('assessment_date') and app.get('assessment_date') not in (app.get('date_applied'), app.get('interview_date')):
            events.append({
                'app_id': app_id,
                'company_name': company,
                'job_title': title,
                'status': 'Interviewing',
                'event_type': 'assessment',
                'label': 'Assessment Due',
                'date': app['assessment_date'],
                'meta': meta
            })

        # 4. Follow-up Date Event
        if app.get('followup_date') and app.get('followup_date') not in (app.get('date_applied'), app.get('interview_date')):
            events.append({
                'app_id': app_id,
                'company_name': company,
                'job_title': title,
                'status': status,
                'event_type': 'followup',
                'label': 'Follow-up Reminder',
                'date': app['followup_date'],
                'meta': meta
            })

    return jsonify(events)


@applications_bp.route('/api/analytics', methods=['GET'])
@login_required
def get_analytics():
    user_id = session['user_id']
    db = get_db()
    rows = db.execute(f'SELECT * FROM applications WHERE user_id = ? AND {_active_apps_filter()}', (user_id,)).fetchall()
    applications = [format_application_row(r) for r in rows]

    total = len(applications)
    applied = sum(1 for a in applications if a['status'] == 'Applied')
    interviewing = sum(1 for a in applications if a['status'] == 'Interviewing')
    offered = sum(1 for a in applications if a['status'] == 'Offered')
    rejected = sum(1 for a in applications if a['status'] == 'Rejected')

    # Cumulative rates for more accurate KPIs
    total_interviewed = interviewing + offered
    # We assume 'offered' means they were interviewed. 

    interview_rate = round((total_interviewed / total * 100), 1) if total > 0 else 0.0
    offer_rate = round((offered / total * 100), 1) if total > 0 else 0.0
    rejection_rate = round((rejected / total * 100), 1) if total > 0 else 0.0
    applied_rate = round((applied / total * 100), 1) if total > 0 else 0.0

    return jsonify({
        'total': total,
        'applied': applied,
        'interviewing': interviewing,
        'total_interviewed': total_interviewed,
        'offered': offered,
        'rejected': rejected,
        'interview_rate': interview_rate,
        'offer_rate': offer_rate,
        'rejection_rate': rejection_rate,
        'applied_rate': applied_rate,
        'funnel': {
            'Applied': {'count': applied, 'percentage': applied_rate},
            'Interviewing': {'count': interviewing, 'percentage': interview_rate},
            'Offered': {'count': offered, 'percentage': offer_rate},
            'Rejected': {'count': rejected, 'percentage': rejection_rate}
        }
    })

@applications_bp.route('/applications', methods=['GET'])
@login_required
def get_applications():
    # If a browser navigation requests /applications with view param, redirect to dashboard HTML
    if request.args.get('view') or (request.headers.get('Sec-Fetch-Dest') == 'document' and 'text/html' in request.headers.get('Accept', '')):
        return redirect(url_for('applications.index', **request.args))

    user_id = session['user_id']
    db = get_db()
    search = request.args.get('search', '').strip().lower()
    include_archived = request.args.get('include_archived') == '1'
    archived_clause = '' if include_archived else f'AND {_active_apps_filter()}'
    rows = db.execute(f'SELECT * FROM applications WHERE user_id = ? {archived_clause} ORDER BY last_updated DESC, id DESC', (user_id,)).fetchall()
    applications = [format_application_row(r) for r in rows]

    if search:
        applications = [
            a for a in applications 
            if search in a['company_name'].lower() or search in a['job_title'].lower()
        ]

    return jsonify(applications)

import urllib.request
import re
from html.parser import HTMLParser

import json

class MetaTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta_tags = {}
        self.title = ""
        self.in_title = False
        self.h1_tags = []
        self.in_h1 = False
        self.current_h1 = ""
        self.json_ld_blocks = []
        self.in_json_ld = False
        self.current_json_ld = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'meta':
            name = attrs_dict.get('property') or attrs_dict.get('name')
            content = attrs_dict.get('content')
            if name and content:
                self.meta_tags[name.lower()] = content.strip()
        elif tag == 'title':
            self.in_title = True
        elif tag == 'h1':
            self.in_h1 = True
            self.current_h1 = ""
        elif tag == 'script' and attrs_dict.get('type') == 'application/ld+json':
            self.in_json_ld = True
            self.current_json_ld = ""

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'h1':
            self.in_h1 = False
            if self.current_h1.strip():
                self.h1_tags.append(self.current_h1.strip())
        elif tag == 'script' and self.in_json_ld:
            self.in_json_ld = False
            if self.current_json_ld.strip():
                self.json_ld_blocks.append(self.current_json_ld.strip())

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.current_h1 += data
        if self.in_json_ld:
            self.current_json_ld += data

import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Job platform vs employer distinction.
# These domains are job AGGREGATORS / platforms (the "source"), never the
# employer by default. The URL hostname must NEVER become Company Name for
# these hosts.
# ---------------------------------------------------------------------------
JOB_PLATFORMS = {
    'linkedin.com': 'LinkedIn',
    'indeed.com': 'Indeed',
    'glassdoor.com': 'Glassdoor',
    'glassdoor.co.in': 'Glassdoor',
    'wellfound.com': 'Wellfound',
    'angel.co': 'Wellfound',
    'naukri.com': 'Naukri',
    'internshala.com': 'Internshala',
    'monster.com': 'Monster',
    'monsterindia.com': 'Monster',
    'shine.com': 'Shine',
    'foundit.in': 'Foundit',
    'timesjobs.com': 'TimesJobs',
    'ziprecruiter.com': 'ZipRecruiter',
    'simplyhired.com': 'SimplyHired',
    'dice.com': 'Dice',
    'cutshort.io': 'Cutshort',
    'instahyre.com': 'Instahyre',
}


def detect_job_platform(domain):
    """Return platform display name if domain is a known job platform, else None."""
    d = (domain or '').lower()
    for host, platform in JOB_PLATFORMS.items():
        if host in d:
            return platform
    return None


def is_platform_name(name, platform):
    """True if a candidate company name is really just the platform name."""
    if not name or not platform:
        return False
    n = name.strip().lower().lstrip('@').strip()
    p = platform.strip().lower()
    return n == p or n == f"{p} jobs" or n == f"{p} careers" or n.startswith(p + ' ')


def normalize_company_name(raw, platform=None):
    """Strip @ prefixes, platform suffixes ('| LinkedIn', '- LinkedIn'), and noise."""
    if not raw:
        return ''
    name = str(raw).strip().lstrip('@').strip()
    if platform:
        # Remove trailing platform references: "Zenithbyte | LinkedIn", "X - LinkedIn Jobs", etc.
        name = re.sub(r'\s*[\|\-–—:]\s*' + re.escape(platform) + r'(\s+(jobs|careers|hiring))?\s*$', '', name, flags=re.IGNORECASE).strip()
        name = re.sub(r'\s+' + re.escape(platform) + r'\s*$', '', name, flags=re.IGNORECASE).strip()
    # Generic trailing site suffixes that are not part of employer names
    name = re.sub(r'\s*[\|\-–—:]\s*(jobs|careers|hiring|job search)\s*$', '', name, flags=re.IGNORECASE).strip()
    name = name.strip().lstrip('@').strip()
    if platform and is_platform_name(name, platform):
        return ''
    return name


def extract_linkedin_employer(html_content, parser):
    """LinkedIn-specific employer extraction (JSON-LD already handled by caller).

    Tries, in order: og:title 'X hiring Y' / 'Y at X' patterns, topcard
    company anchor, /company/ slug. Returns '' when nothing reliable found.
    """
    # 1. og:title / <title> patterns like "Zenithbyte hiring Data Science Intern"
    #    or "Data Science Intern at Zenithbyte" or "Zenithbyte | Data Science Intern"
    candidates = [
        parser.meta_tags.get('og:title', ''),
        parser.meta_tags.get('twitter:title', ''),
        parser.title or '',
    ]
    for text in candidates:
        text = (text or '').strip()
        if not text:
            continue
        m = re.search(r'^(.{2,60}?)\s+hiring\s+(.{3,80})$', text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r'^(.{3,80}?)\s+at\s+([A-Z][\w&.\- ]{1,50})(?:\s*[\|\-–—].*)?$', text)
        if m:
            return m.group(2).strip()
    # 2. LinkedIn top-card company anchor: <a ...>Zenithbyte</a> near topcard/org
    m = re.search(r'topcard[^>]{0,300}?org-name[^>]*?>([^<]{2,60})<', html_content, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'class="[^"]*topcard[^"]*"[^>]*>.*?<a[^>]*>([^<]{2,60})</a>', html_content, re.IGNORECASE | re.DOTALL)
    if m:
        cand = m.group(1).strip()
        if cand and 'linkedin' not in cand.lower() and len(cand) < 60:
            return cand
    # 3. /company/<slug> link text or slug
    m = re.search(r'href="[^"]*/company/([a-z0-9\-]+)[^"]*"[^>]*>([^<]{2,60})<', html_content, re.IGNORECASE)
    if m:
        label = m.group(2).strip()
        if label and 'linkedin' not in label.lower() and 'follow' not in label.lower():
            return label
        slug = m.group(1).replace('-', ' ').title()
        if slug.lower() != 'linkedin':
            return slug
    return ''


def extract_job_details_with_groq(html_content, domain="", platform=None):
    api_key = current_app.config.get('GROQ_API_KEY', '').strip()
    if not api_key:
        return None

    clean_text = re.sub(r'<script.*?>.*?</script>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<style.*?>.*?</style>', ' ', clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
    clean_text = ' '.join(clean_text.split())

    text_snippet = clean_text[:6000]

    platform_note = (
        f"The job page is hosted on the job platform '{platform}' ({domain}). "
        f"'{platform}' is the SOURCE/aggregator, NEVER the employer. "
        "Do NOT return the platform name as company_name. "
        "If the actual hiring employer cannot be found in the text, return an empty string for company_name."
        if platform else
        f"Target Domain: {domain}"
    )

    system_prompt = (
        "You are an expert job metadata extraction AI. "
        "Your task is to parse a job posting web page and extract details into JSON format.\n\n"
        "Return ONLY a single valid JSON object matching this schema:\n"
        "{\n"
        '  "company_name": "Actual hiring employer (e.g. Stripe, Salesforce, Google). Empty string if unknown.",\n'
        '  "job_title": "Exact position title (e.g. Software Engineer, Intern)",\n'
        '  "job_type": "One of: Internship, Full-time, Part-time, Contract, Other",\n'
        '  "location": "Exact location string (e.g. San Francisco, CA; Remote; Seattle, WA; Hybrid)",\n'
        '  "salary": "Salary or compensation if stated, else empty string",\n'
        '  "job_description": "A concise 2-4 sentence summary of key role responsibilities and requirements"\n'
        "}\n\n"
        "Rules:\n"
        "- Do NOT wrap JSON in extra markdown text. Output strictly valid JSON.\n"
        "- Extract ONLY true and accurate details found directly in the provided text. Do NOT hallucinate, guess, or make up information. If a detail (like salary, location, or company) is not clearly present in the text, leave the field blank (empty string).\n"
        "- company_name must be the HIRING EMPLOYER, never the job board / platform / aggregator hosting the page (LinkedIn, Indeed, Glassdoor, Wellfound, Naukri, Internshala, etc.).\n"
        "- For job_type: set 'Internship' if the title or text mentions intern/co-op/student, else 'Full-time', 'Part-time', 'Contract', or 'Other'.\n"
        "- For location: carefully search the text for city, state, country, 'Remote', 'Hybrid', or office locations. If multiple, separate with commas."
    )

    models_to_try = [
        current_app.config.get('GROQ_MODEL', 'openai/gpt-oss-120b'),
        'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'groq/compound'
    ]

    for model in models_to_try:
        groq_payload = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"{platform_note}\n\nJob Page Text:\n{text_snippet}"}
            ],
            'temperature': 0.1,
            'max_tokens': 500
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                'https://api.groq.com/openai/v1/chat/completions',
                data=groq_payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=6) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                raw_json = res_data['choices'][0]['message']['content'].strip()
                
                if raw_json.startswith('```'):
                    raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json)
                    raw_json = re.sub(r'\s*```$', '', raw_json)
                
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    jt = str(parsed.get('job_type', 'Full-time')).strip()
                    if jt not in ['Full-time', 'Internship', 'Part-time', 'Contract', 'Other']:
                        jt = 'Internship' if 'intern' in str(parsed.get('job_title', '')).lower() else 'Full-time'
                    ai_company = normalize_company_name(str(parsed.get('company_name', '')).strip(), platform)
                    return {
                        'company_name': ai_company,
                        'job_title': str(parsed.get('job_title', '')).strip(),
                        'job_type': jt,
                        'location': str(parsed.get('location', '')).strip(),
                        'salary': str(parsed.get('salary', '')).strip(),
                        'job_description': str(parsed.get('job_description', '')).strip()
                    }
        except Exception as e:
            print(f"Groq Auto-Fill Extraction error with {model}: {e}")
            continue

    return None

def parse_url_job_details(url):
    """Priority-based job extraction that never confuses platform with employer.

    Priority:
      1. Groq LLM extraction from page content (platform-aware prompt)
      2. JSON-LD JobPosting hiringOrganization (explicit employer field)
      3. Platform-specific extraction (e.g. LinkedIn topcard / og:title patterns)
      4. og:title 'Role at Company' / 'Company hiring Role' splits
      5. og:site_name — only when host is NOT a known job platform
      6. URL-path heuristics for ATS hosts (greenhouse/lever/workday) only
    Returns dict with company_name ('' when employer unknown), job fields,
    plus platform, extraction_source and company_confidence diagnostics.
    """
    company_name = ""
    job_title = ""
    job_type = "Full-time"
    location = ""
    salary = ""
    job_description = ""
    domain = ""
    platform = None
    extraction_source = "none"
    company_confidence = 0.0

    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        platform = detect_job_platform(domain)
        if not platform:
            # ATS / direct-career-site fallbacks only (never for job platforms).
            if 'greenhouse.io' in domain:
                parts = [p for p in urlparse(url).path.split('/') if p]
                if parts:
                    company_name = normalize_company_name(parts[0].replace('-', ' ').title(), platform)
                    extraction_source = "url_path"
                    company_confidence = 0.6
            elif 'lever.co' in domain:
                parts = [p for p in urlparse(url).path.split('/') if p]
                if parts:
                    company_name = normalize_company_name(parts[0].replace('-', ' ').title(), platform)
                    extraction_source = "url_path"
                    company_confidence = 0.6
            elif 'myworkdayjobs.com' in domain:
                company_name = normalize_company_name(domain.split('.')[0].replace('-', ' ').title(), platform)
                extraction_source = "url_path"
                company_confidence = 0.5
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html_content = response.read().decode('utf-8', errors='ignore')

        # 1. Try Groq AI Extraction first for 100% precision (platform-aware)
        ai_extracted = extract_job_details_with_groq(html_content, domain, platform)
        if ai_extracted and (ai_extracted.get('company_name') or ai_extracted.get('job_title')):
            ai_company = normalize_company_name(ai_extracted.get('company_name') or '', platform)
            result = {
                'company_name': ai_company,
                'job_title': ai_extracted.get('job_title') or job_title,
                'job_type': ai_extracted.get('job_type') or 'Full-time',
                'location': ai_extracted.get('location') or location,
                'salary': ai_extracted.get('salary') or salary,
                'job_description': ai_extracted.get('job_description') or job_description,
                'platform': platform,
                'extraction_source': 'groq_ai',
                'company_confidence': 0.9 if ai_company else 0.0,
            }
            logger.info("[AutoFill] domain=%s platform=%s employer=%r source=groq_ai title=%r",
                        domain, platform, ai_company, result['job_title'])
            return result

        # 2. Fallback HTML Meta Tag / Regex Parsing
        parser = MetaTagParser()
        parser.feed(html_content)

        for block in parser.json_ld_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, list):
                    data = data[0] if data else {}
                if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                    if data.get('title'):
                        job_title = data['title'].strip()
                    if data.get('hiringOrganization'):
                        org = data['hiringOrganization']
                        raw_org = ''
                        if isinstance(org, dict) and org.get('name'):
                            raw_org = org['name'].strip()
                        elif isinstance(org, str):
                            raw_org = org.strip()
                        if raw_org:
                            company_name = normalize_company_name(raw_org, platform)
                            extraction_source = "json_ld"
                            company_confidence = 0.95
                    if data.get('jobLocation'):
                        loc_obj = data['jobLocation']
                        if isinstance(loc_obj, dict):
                            addr = loc_obj.get('address', {})
                            if isinstance(addr, dict):
                                parts = [addr.get('addressLocality'), addr.get('addressRegion'), addr.get('addressCountry')]
                                location = ", ".join([p for p in parts if p])
                            elif isinstance(addr, str):
                                location = addr
                        elif isinstance(loc_obj, str):
                            location = loc_obj
                    if data.get('description'):
                        clean_desc = re.sub(r'<[^>]+>', ' ', str(data['description']))
                        job_description = ' '.join(clean_desc.split()).strip()
            except Exception:
                pass

        if not location:
            loc_label_match = re.search(r'Location\s*:\s*([^\n\r<]+)', html_content, re.IGNORECASE)
            if loc_label_match:
                extracted_loc = loc_label_match.group(1).strip()
                extracted_loc = re.sub(r'<[^>]+>', '', extracted_loc).strip()
                if extracted_loc and len(extracted_loc) < 80:
                    location = extracted_loc

        if not location:
            loc_match = re.search(r'(Remote|Hybrid|On-site|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2})', html_content)
            if loc_match:
                location = loc_match.group(1)

        if not job_description:
            meta_desc = parser.meta_tags.get('og:description') or parser.meta_tags.get('description') or parser.meta_tags.get('twitter:description')
            if meta_desc:
                job_description = meta_desc.strip()

        if not job_title and parser.h1_tags:
            for h in parser.h1_tags:
                if len(h) > 3 and not h.lower().endswith('jobs') and h.lower() != 'careers':
                    job_title = h
                    break
            if not job_title:
                job_title = parser.h1_tags[0]

        if not job_title:
            og_title = parser.meta_tags.get('og:title') or parser.meta_tags.get('twitter:title') or parser.title.strip()
            if og_title:
                cleaned_title = og_title
                if ' at ' in cleaned_title:
                    parts = cleaned_title.split(' at ')
                    job_title = parts[0].strip()
                    employer_raw = parts[1].split('-')[0].split('|')[0].strip()
                    employer = normalize_company_name(employer_raw, platform)
                    if employer:
                        company_name = employer
                        if extraction_source in ("none", "url_path"):
                            extraction_source = "og_title"
                            company_confidence = 0.7
                elif re.search(r'\bhiring\b', cleaned_title, re.IGNORECASE):
                    # "Zenithbyte hiring Data Science Intern ..." -> employer first
                    m = re.search(r'^(.{2,60}?)\s+hiring\s+(.{3,80})$', cleaned_title, re.IGNORECASE)
                    if m:
                        employer = normalize_company_name(m.group(1).strip(), platform)
                        if employer:
                            company_name = employer
                            extraction_source = "og_title"
                            company_confidence = 0.7
                        job_title = m.group(2).split('|')[0].split('-')[0].strip()
                    else:
                        job_title = cleaned_title
                elif ' - ' in cleaned_title:
                    parts = cleaned_title.split(' - ')
                    job_title = parts[0].strip()
                    if len(parts) > 1 and not company_name:
                        cand = normalize_company_name(parts[1].strip(), platform)
                        if cand:
                            company_name = cand
                            extraction_source = "og_title"
                            company_confidence = 0.55
                elif ' | ' in cleaned_title:
                    parts = cleaned_title.split(' | ')
                    job_title = parts[0].strip()
                    if len(parts) > 1 and not company_name:
                        cand = normalize_company_name(parts[1].strip(), platform)
                        if cand:
                            company_name = cand
                            extraction_source = "og_title"
                            company_confidence = 0.55
                else:
                    job_title = cleaned_title

        # 3b. Platform-specific extraction (fills gaps JSON-LD/og:title missed)
        if platform and not company_name:
            try:
                plat_employer = normalize_company_name(extract_linkedin_employer(html_content, parser), platform)
            except Exception:
                plat_employer = ''
            if plat_employer:
                company_name = plat_employer
                extraction_source = "platform_specific"
                company_confidence = 0.75

        if job_title.lower().endswith('jobs') and parser.h1_tags:
            for h in parser.h1_tags:
                if not h.lower().endswith('jobs') and h.lower() != 'careers':
                    job_title = h
                    break

        og_site = parser.meta_tags.get('og:site_name') or parser.meta_tags.get('twitter:site')
        if og_site and not company_name and not platform:
            # Only trustworthy for direct employer career sites. On job platforms
            # og:site_name is the platform itself (e.g. "LinkedIn") — never use it.
            cand = normalize_company_name(og_site, platform)
            if cand:
                company_name = cand
                extraction_source = "og_site_name"
                company_confidence = 0.5

        sal_match = re.search(r'(\$[\d,]+\s*(?:-|to)\s*\$[\d,]+|\$[\d,]+(?:\/yr|\/hr)?|₹\d+(?:\.\d+)?\s*(?:LPA|Lacs|Lakhs))', html_content, re.IGNORECASE)
        if sal_match:
            salary = sal_match.group(1)

        if 'intern' in job_title.lower() or 'co-op' in job_title.lower():
            job_type = 'Internship'

    except Exception as e:
        print(f"URL fetch error: {e}")

    # Final safety net: never return the platform name (or @platform) as employer.
    company_name = normalize_company_name(company_name, platform)
    if platform and is_platform_name(company_name, platform):
        company_name = ''
        company_confidence = 0.0
        extraction_source = "none" if extraction_source in ("url_path", "og_site_name") else extraction_source

    logger.info("[AutoFill] domain=%s platform=%s employer=%r source=%s confidence=%s title=%r",
                domain, platform, company_name, extraction_source, company_confidence, job_title)

    return {
        'company_name': company_name,
        'job_title': job_title,
        'job_type': job_type,
        'location': location,
        'salary': salary,
        'job_description': job_description,
        'platform': platform,
        'extraction_source': extraction_source,
        'company_confidence': company_confidence,
    }

@applications_bp.route('/api/autofill-url', methods=['POST'])
@login_required
def autofill_url():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Please provide a valid URL.'}), 400

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    extracted = parse_url_job_details(url)
    return jsonify({
        'success': True,
        'company_name': extracted.get('company_name', ''),
        'job_title': extracted.get('job_title', ''),
        'job_type': extracted.get('job_type', 'Full-time'),
        'location': extracted.get('location', ''),
        'salary': extracted.get('salary', ''),
        'job_description': extracted.get('job_description', ''),
        'platform': extracted.get('platform'),
        'extraction_source': extracted.get('extraction_source', 'none'),
        'company_confidence': extracted.get('company_confidence', 0.0),
    })

@applications_bp.route('/applications', methods=['POST'])
@login_required
def create_application():
    user_id = session['user_id']
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    company_name = data.get('company_name', '').strip()
    job_title = data.get('job_title', '').strip()
    status = data.get('status', 'Applied').strip()
    date_applied = data.get('date_applied', '').strip() or date.today().strftime('%Y-%m-%d')
    notes = data.get('notes', '').strip()
    interview_date = data.get('interview_date', '').strip() or None
    deadline_date = None
    assessment_date = data.get('assessment_date', '').strip() or None
    followup_date = None
    job_url = data.get('job_url', '').strip() or None
    salary = data.get('salary', '').strip() or None
    location = data.get('location', '').strip() or None
    job_type = data.get('job_type', 'Full-time').strip() or 'Full-time'
    resume_version = data.get('resume_version', '').strip() or None

    if not company_name or not job_title:
        return jsonify({'error': 'Company name and job title are required.'}), 400

    if status not in VALID_STATUSES:
        return jsonify({'error': f'Invalid status. Must be one of {VALID_STATUSES}'}), 400

    last_updated = date.today().strftime('%Y-%m-%d')
    force_add = str(data.get('force_add', '')).lower() in ['true', '1', 'yes']

    db = get_db()
    
    if not force_add:
        existing_app = db.execute('SELECT * FROM applications WHERE user_id = ? AND LOWER(company_name) = ? AND LOWER(job_title) = ?', 
                                  (user_id, company_name.lower(), job_title.lower())).fetchone()
        if existing_app:
            return jsonify({
                'duplicate_found': True,
                'existing_app': format_application_row(existing_app)
            }), 409
    
    # Check if user has resume_text to compute fit_score
    user_row = db.execute('SELECT resume_text FROM users WHERE id = ?', (user_id,)).fetchone()
    resume_text = user_row['resume_text'] if user_row and user_row['resume_text'] else ''
    
    fit_score = None
    missing_skills_str = None
    if resume_text:
        jd_text = notes or f"{company_name} {job_title} {location or ''} {job_type}"
        from services.groq_service import compute_fit_score
        fit_score, skills_list = compute_fit_score(jd_text, resume_text)
        if skills_list:
            missing_skills_str = json.dumps(skills_list)

    cursor = db.execute(
        'INSERT INTO applications (user_id, company_name, job_title, status, date_applied, last_updated, notes, interview_date, deadline_date, assessment_date, followup_date, job_url, salary, location, job_type, resume_version, fit_score, missing_skills) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (user_id, company_name, job_title, status, date_applied, last_updated, notes, interview_date, deadline_date, assessment_date, followup_date, job_url, salary, location, job_type, resume_version, fit_score, missing_skills_str)
    )
    db.commit()

    new_id = cursor.lastrowid
    
    # Add initial timeline event for application creation
    from database.db import add_application_timeline_event, get_application_timeline_events
    add_application_timeline_event(
        application_id=new_id,
        user_id=user_id,
        event_type='APPLICATION_SUBMITTED',
        event_title='Application Submitted',
        event_description=f"Submitted application for {job_title} at {company_name}",
        event_date=date_applied,
        source='MANUAL'
    )

    row = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (new_id, user_id)).fetchone()
    new_app = format_application_row(row)

    if request.is_json:
        return jsonify(new_app), 201
    return redirect(url_for('applications.index'))

@applications_bp.route('/applications/<int:app_id>', methods=['GET'])
@login_required
def get_application_details(app_id):
    user_id = session['user_id']
    db = get_db()
    row = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id)).fetchone()
    if not row:
        return jsonify({'error': 'Application not found'}), 404
    return jsonify(format_application_row(row))

@applications_bp.route('/api/applications/<int:app_id>/timeline', methods=['GET'])
@login_required
def get_application_timeline(app_id):
    user_id = session['user_id']
    from database.db import get_application_timeline_events
    events = get_application_timeline_events(app_id, user_id)
    return jsonify({'timeline': [dict(e) for e in events]})

@applications_bp.route('/applications/<int:app_id>', methods=['PUT', 'PATCH'])
@login_required
def update_application(app_id):
    user_id = session['user_id']
    db = get_db()
    existing = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Application not found'}), 404

    data = request.get_json() or request.form

    existing_dict = dict(existing)
    company_name = str(data.get('company_name', existing_dict['company_name'])).strip()
    job_title = str(data.get('job_title', existing_dict['job_title'])).strip()
    status = str(data.get('status', existing_dict['status'])).strip()
    date_applied = str(data.get('date_applied', existing_dict['date_applied'])).strip()
    notes = str(data.get('notes', existing_dict['notes'] or '')).strip()
    
    interview_date = data.get('interview_date', existing_dict.get('interview_date'))
    if interview_date is not None:
        interview_date = str(interview_date).strip() or None

    deadline_date = None

    assessment_date = data.get('assessment_date', existing_dict.get('assessment_date'))
    if assessment_date is not None:
        assessment_date = str(assessment_date).strip() or None

    followup_date = None

    job_url = data.get('job_url', existing_dict.get('job_url'))
    if job_url is not None:
        job_url = str(job_url).strip() or None

    salary = data.get('salary', existing_dict.get('salary'))
    if salary is not None:
        salary = str(salary).strip() or None

    location = data.get('location', existing_dict.get('location'))
    if location is not None:
        location = str(location).strip() or None

    job_type = data.get('job_type', existing_dict.get('job_type', 'Full-time'))
    if job_type is not None:
        job_type = str(job_type).strip() or 'Full-time'

    resume_version = data.get('resume_version', existing_dict.get('resume_version'))
    if resume_version is not None:
        resume_version = str(resume_version).strip() or None

    if status not in VALID_STATUSES:
        return jsonify({'error': f'Invalid status. Must be one of {VALID_STATUSES}'}), 400

    last_updated = date.today().strftime('%Y-%m-%d')

    # Re-calculate fit_score if notes or job_url changed or fit_score is missing
    fit_score = existing_dict.get('fit_score')
    missing_skills_str = existing_dict.get('missing_skills')

    user_row = db.execute('SELECT resume_text FROM users WHERE id = ?', (user_id,)).fetchone()
    resume_text = user_row['resume_text'] if user_row and user_row['resume_text'] else ''

    is_status_only = list(data.keys()) == ['status']
    
    if resume_text and not is_status_only and (notes != (existing_dict['notes'] or '') or job_url != existing_dict.get('job_url') or fit_score is None):
        jd_text = notes or f"{company_name} {job_title} {location or ''} {job_type}"
        from services.groq_service import compute_fit_score
        fit_score, skills_list = compute_fit_score(jd_text, resume_text)
        if skills_list:
            missing_skills_str = json.dumps(skills_list)
        else:
            missing_skills_str = None

    db.execute(
        'UPDATE applications SET company_name = ?, job_title = ?, status = ?, date_applied = ?, last_updated = ?, notes = ?, interview_date = ?, deadline_date = ?, assessment_date = ?, followup_date = ?, job_url = ?, salary = ?, location = ?, job_type = ?, resume_version = ?, fit_score = ?, missing_skills = ? WHERE id = ? AND user_id = ?',
        (company_name, job_title, status, date_applied, last_updated, notes, interview_date, deadline_date, assessment_date, followup_date, job_url, salary, location, job_type, resume_version, fit_score, missing_skills_str, app_id, user_id)
    )
    db.commit()

    updated_row = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id)).fetchone()
    return jsonify(format_application_row(updated_row))

@applications_bp.route('/applications/<int:app_id>', methods=['DELETE'])
@login_required
def delete_application(app_id):
    user_id = session['user_id']
    db = get_db()
    existing = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Application not found'}), 404

    db.execute('DELETE FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id))
    db.commit()
    return jsonify({'success': True, 'id': app_id})


@applications_bp.route('/api/applications/bulk', methods=['POST'])
@login_required
def bulk_update_applications():
    """One-tap bulk management: status change, archive/unarchive, or delete.

    Request: {"action": "status"|"archive"|"unarchive"|"delete",
              "ids": [1, 2, ...], "status": "Interviewing" (for action=status)}
    Response: {"success": bool, "action": str, "updated": [ids],
               "failed": [{"id": int, "error": str}], "message": str}
    Partial failures are reported per record — never silently swallowed.
    """
    from database.db import add_application_timeline_event

    user_id = session['user_id']
    data = request.get_json() or {}
    action = str(data.get('action', '')).strip().lower()
    raw_ids = data.get('ids', [])

    if action not in ('status', 'archive', 'unarchive', 'delete'):
        return jsonify({'error': 'Invalid action. Must be one of: status, archive, unarchive, delete.'}), 400

    try:
        ids = sorted({int(i) for i in raw_ids})
    except (TypeError, ValueError):
        return jsonify({'error': 'ids must be a list of application IDs.'}), 400

    if not ids:
        return jsonify({'error': 'No applications selected.'}), 400
    if len(ids) > 200:
        return jsonify({'error': 'Too many applications selected (max 200).'}), 400

    new_status = None
    if action == 'status':
        new_status = str(data.get('status', '')).strip()
        if new_status not in VALID_STATUSES:
            return jsonify({'error': f'Invalid status. Must be one of {VALID_STATUSES}'}), 400

    db = get_db()
    updated, failed = [], []
    today_str = date.today().strftime('%Y-%m-%d')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for app_id in ids:
        try:
            existing = db.execute(
                'SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id)
            ).fetchone()
            if not existing:
                failed.append({'id': app_id, 'error': 'Not found'})
                continue

            if action == 'status':
                old_status = existing['status']
                db.execute(
                    'UPDATE applications SET status = ?, last_updated = ? WHERE id = ? AND user_id = ?',
                    (new_status, today_str, app_id, user_id)
                )
                if old_status != new_status:
                    try:
                        add_application_timeline_event(
                            application_id=app_id,
                            user_id=user_id,
                            event_type='BULK_STATUS_UPDATE',
                            event_title='Status Updated (Bulk)',
                            event_description=f"Status updated: {old_status} → {new_status}",
                            event_date=today_str,
                            source='MANUAL'
                        )
                    except Exception:
                        pass
            elif action == 'archive':
                db.execute(
                    'UPDATE applications SET archived = 1, archived_at = ? WHERE id = ? AND user_id = ?',
                    (now_str, app_id, user_id)
                )
            elif action == 'unarchive':
                db.execute(
                    'UPDATE applications SET archived = 0, archived_at = NULL WHERE id = ? AND user_id = ?',
                    (app_id, user_id)
                )
            elif action == 'delete':
                db.execute('DELETE FROM applications WHERE id = ? AND user_id = ?', (app_id, user_id))

            updated.append(app_id)
        except Exception as e:
            failed.append({'id': app_id, 'error': str(e)})

    db.commit()

    total, ok_count, fail_count = len(ids), len(updated), len(failed)
    noun = f"{ok_count} application{'s' if ok_count != 1 else ''}"
    if fail_count == 0:
        if action == 'status':
            message = f"{noun} updated to {new_status}."
        elif action == 'archive':
            message = f"{noun} archived."
        elif action == 'unarchive':
            message = f"{noun} restored."
        else:
            message = f"{noun} removed."
    else:
        message = f"{ok_count} of {total} applications processed successfully."

    logger.info("[Bulk] user=%s action=%s status=%s updated=%d failed=%d",
                user_id, action, new_status, ok_count, fail_count)

    return jsonify({
        'success': fail_count == 0,
        'action': action,
        'status': new_status,
        'updated': updated,
        'failed': failed,
        'message': message
    })


