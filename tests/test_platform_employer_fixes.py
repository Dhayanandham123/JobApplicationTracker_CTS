"""Regression tests for Issue 1 (platform vs employer) and Issue 2 (email relevance).

Issue 1: LinkedIn/Indeed/etc. are job PLATFORMS (sources), never the employer.
Issue 2: Email Intelligence must classify on actual context; digests,
newsletters, promos and non-inbox library noise must be excluded while
genuine archived application mail still passes on content.
"""
import json
from unittest.mock import patch

import pytest

from app import create_app
from routes.applications import (
    detect_job_platform,
    is_platform_name,
    normalize_company_name,
    parse_url_job_details,
)


@pytest.fixture
def app_ctx(tmp_path):
    db_file = tmp_path / "test_platform.db"
    test_config = {
        'TESTING': True,
        'DATABASE': str(db_file),
        'SECRET_KEY': 'test-platform-key',
        'GROQ_API_KEY': '',
    }
    app = create_app(test_config)
    with app.test_request_context():
        yield app


class FakeResp:
    def __init__(self, html):
        self._html = html

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._html.encode('utf-8')


def _parse(app_ctx, url, html):  # noqa: ANN001 - pytest helper
    with patch('routes.applications.urllib.request.urlopen', return_value=FakeResp(html)):
        return parse_url_job_details(url)


# --------------------------------------------------------------------------
# JOB TRACKER: platform vs employer
# --------------------------------------------------------------------------

def test_platform_detection():
    assert detect_job_platform('www.linkedin.com') == 'LinkedIn'
    assert detect_job_platform('www.indeed.com') == 'Indeed'
    assert detect_job_platform('www.glassdoor.com') == 'Glassdoor'
    assert detect_job_platform('wellfound.com') == 'Wellfound'
    assert detect_job_platform('www.naukri.com') == 'Naukri'
    assert detect_job_platform('internshala.com') == 'Internshala'
    assert detect_job_platform('google.com') is None
    assert detect_job_platform('careers.salesforce.com') is None


def test_normalize_company_name_strips_platform_noise():
    assert normalize_company_name('@LinkedIn', 'LinkedIn') == ''
    assert normalize_company_name('LinkedIn', 'LinkedIn') == ''
    assert normalize_company_name('Zenithbyte | LinkedIn', 'LinkedIn') == 'Zenithbyte'
    assert normalize_company_name('Zenithbyte - LinkedIn Jobs', 'LinkedIn') == 'Zenithbyte'
    assert normalize_company_name('Zenithbyte', 'LinkedIn') == 'Zenithbyte'
    assert not is_platform_name('Zenithbyte', 'LinkedIn')
    assert is_platform_name('@LinkedIn', 'LinkedIn')


def test_linkedin_json_ld_employer_extraction(app_ctx):
    """Test A: reported LinkedIn URL -> employer Zenithbyte, platform LinkedIn."""
    html = (
        '<html><head>'
        '<meta property="og:title" content="Zenithbyte hiring Data Science Intern in Bengaluru | LinkedIn" />'
        '<meta property="og:site_name" content="LinkedIn" />'
        '<meta property="og:description" content="Data Science Intern role" />'
        '<script type="application/ld+json">{"@type":"JobPosting","title":"Data Science Intern",'
        '"hiringOrganization":{"@type":"Organization","name":"Zenithbyte"}}</script>'
        '</head><body><h1>Data Science Intern</h1></body></html>'
    )
    result = _parse(app_ctx, 'https://www.linkedin.com/jobs/view/4465690070/?trackingId=abc', html)
    assert result['platform'] == 'LinkedIn'
    assert result['company_name'] == 'Zenithbyte'
    assert result['job_title'] == 'Data Science Intern'
    assert result['extraction_source'] == 'json_ld'


def test_linkedin_different_employer_generic(app_ctx):
    """Test B: another LinkedIn job, different employer — no hardcoding."""
    html = (
        '<html><head>'
        '<meta property="og:title" content="Globex Labs hiring Frontend Engineer in Remote | LinkedIn" />'
        '<meta property="og:site_name" content="LinkedIn" />'
        '</head><body><h1>Frontend Engineer</h1></body></html>'
    )
    result = _parse(app_ctx, 'https://www.linkedin.com/jobs/view/1234567890', html)
    assert result['platform'] == 'LinkedIn'
    assert result['company_name'] == 'Globex Labs'
    assert result['company_name'] != 'LinkedIn'


def test_other_platform_employer_not_platform(app_ctx):
    """Test C: Indeed job -> platform Indeed, employer is the hiring company."""
    html = (
        '<html><head>'
        '<meta property="og:title" content="Software Engineer at Initech LLC" />'
        '<meta property="og:site_name" content="Indeed" />'
        '</head><body><h1>Software Engineer</h1></body></html>'
    )
    result = _parse(app_ctx, 'https://www.indeed.com/viewjob?jk=abc123', html)
    assert result['platform'] == 'Indeed'
    assert result['company_name'] == 'Initech LLC'


def test_unresolvable_employer_not_platform(app_ctx):
    """Test D: employer unknown -> empty company, never the platform name."""
    html = (
        '<html><head><title>LinkedIn Job Search</title>'
        '<meta property="og:site_name" content="LinkedIn" /></head>'
        '<body><h1>Jobs</h1></body></html>'
    )
    result = _parse(app_ctx, 'https://www.linkedin.com/jobs/view/0000', html)
    assert result['company_name'] == '' or 'linkedin' not in result['company_name'].lower()


# --------------------------------------------------------------------------
# EMAIL INTELLIGENCE: structured relevance decisions
# --------------------------------------------------------------------------
from services.email_classifier_service import (  # noqa: E402
    classify_email_intelligence,
    evaluate_recruitment_relevance,
)
from services.gmail_service import parse_gmail_message  # noqa: E402


def _gmail_raw(label_ids, subject='Sub', sender='Jane <jane@stripe.com>', unsub=False):
    headers = [
        {'name': 'Subject', 'value': subject},
        {'name': 'From', 'value': sender},
    ]
    if unsub:
        headers.append({'name': 'List-Unsubscribe', 'value': '<mailto:unsub@example.com>'})
    return {
        'id': 'm1', 'threadId': 't1', 'snippet': 'snip', 'internalDate': '1750000000000',
        'labelIds': label_ids,
        'payload': {'headers': headers, 'mimeType': 'text/plain',
                    'body': {'data': ''}, 'parts': []},
    }


def test_source_folder_tracking():
    assert parse_gmail_message(_gmail_raw(['INBOX', 'UNREAD']))['source_folder'] == 'INBOX'
    assert parse_gmail_message(_gmail_raw(['SPAM']))['source_folder'] == 'SPAM'
    # Archived / library mail carries no INBOX label.
    assert parse_gmail_message(_gmail_raw([]))['source_folder'] == 'ARCHIVE'
    parsed = parse_gmail_message(_gmail_raw(['INBOX'], unsub=True))
    assert parsed['has_unsubscribe'] is True
    assert parsed['is_bulk'] is True


def test_relevant_application_confirmation_included():
    email = {
        'subject': 'Your application has been received - Google',
        'body_text': 'Thank you for applying for the Software Engineer role at Google. We are reviewing your application.',
        'sender_name': 'Google Careers', 'sender_email': 'no-reply@greenhouse.io',
        'source_folder': 'INBOX',
    }
    decision = classify_email_intelligence(email)
    assert decision['is_job_related'] is True
    assert decision['category'] == 'APPLICATION_RECEIVED'


def test_relevant_interview_recruiter_rejection_included():
    cases = [
        ({'subject': 'Interview Invitation - Software Engineer at Stripe',
          'body_text': 'We would like to schedule a technical interview on September 15. Please choose a time slot.',
          'sender_name': 'Jane Recruiter at Stripe', 'sender_email': 'recruiting@stripe.com',
          'source_folder': 'INBOX'}, 'INTERVIEW_INVITATION'),
        ({'subject': 'Recruiter - Software Engineer Opportunity at Adobe',
          'body_text': 'Hi, I am a recruiter at Adobe. I came across your background and would love to connect about an open role.',
          'sender_name': 'Sarah Smith (Talent Acquisition)', 'sender_email': 'sarah@adobe.com',
          'source_folder': 'INBOX'}, 'RECRUITER_MESSAGE'),
        ({'subject': 'Unfortunately, we will not be moving forward with your application',
          'body_text': 'Thank you for your time. Unfortunately we are pursuing other candidates at this time.',
          'sender_name': 'Recruitment Team', 'sender_email': 'careers@netflix.com',
          'source_folder': 'INBOX'}, 'REJECTION'),
    ]
    for email, expected in cases:
        decision = classify_email_intelligence(email)
        assert decision['is_job_related'] is True, (email, decision)
        assert decision['category'] == expected, (email, decision)


def test_linkedin_digest_and_newsletters_excluded():
    irrelevant = [
        {'subject': 'Jobs you may be interested in: Data Scientist roles in Bangalore',
         'body_text': 'Here are recommended jobs picked for you. View in browser. Manage your alerts.',
         'sender_name': 'LinkedIn Job Alerts', 'sender_email': 'jobalerts-noreply@linkedin.com',
         'source_folder': 'INBOX', 'has_unsubscribe': True, 'is_bulk': True},
        {'subject': 'LinkedIn: 50% discount on LinkedIn Premium for 3 months',
         'body_text': 'Upgrade to Premium today with exclusive discount code. View in browser.',
         'sender_name': 'LinkedIn Offers', 'sender_email': 'promotions@linkedin.com',
         'source_folder': 'INBOX', 'has_unsubscribe': True, 'is_bulk': True},
        {'subject': 'TechWeekly Digest #142: Future of AI and Cloud',
         'body_text': 'Read our weekly newsletter. Unsubscribe here if you no longer wish to receive updates.',
         'sender_name': 'TechWeekly Newsletter', 'sender_email': 'newsletter@techweekly.io',
         'source_folder': 'INBOX', 'has_unsubscribe': True, 'is_bulk': True},
        {'subject': 'Big sale: 50% off this weekend only',
         'body_text': 'Exclusive deal just for you. Unsubscribe here.',
         'sender_name': 'Store Deals', 'sender_email': 'deals@store.com',
         'source_folder': 'INBOX', 'has_unsubscribe': True, 'is_bulk': True},
    ]
    for email in irrelevant:
        decision = classify_email_intelligence(email)
        assert decision['is_job_related'] is False, (email, decision)
        assert decision['category'] == 'IRRELEVANT', (email, decision)


def test_archived_library_noise_excluded_but_genuine_archived_kept():
    # Library noise: vague career subject, archived, bulk -> excluded.
    noise = {
        'subject': 'Career opportunity you might like',
        'body_text': 'Check out these career opportunities. Manage your preferences here.',
        'sender_name': 'Jobs Digest', 'sender_email': 'digest@jobboard.com',
        'source_folder': 'ARCHIVE', 'has_unsubscribe': True, 'is_bulk': True,
    }
    d_noise = classify_email_intelligence(noise)
    assert d_noise['is_job_related'] is False

    # Genuine archived recruiter thread -> classified on content, still included.
    genuine = {
        'subject': 'Interview Invitation - Software Engineer at Stripe',
        'body_text': 'We would like to schedule a technical interview on September 15. Please choose a time slot.',
        'sender_name': 'Jane Recruiter at Stripe', 'sender_email': 'recruiting@stripe.com',
        'source_folder': 'ARCHIVE',
    }
    d_gen = classify_email_intelligence(genuine)
    assert d_gen['is_job_related'] is True
    assert d_gen['category'] == 'INTERVIEW_INVITATION'


def test_platform_sender_alone_is_not_relevant():
    email = {
        'subject': 'Your weekly LinkedIn highlights',
        'body_text': 'See who viewed your profile and new courses for your career growth.',
        'sender_name': 'LinkedIn', 'sender_email': 'notifications@linkedin.com',
        'source_folder': 'INBOX',
    }
    is_rel, _, _ = evaluate_recruitment_relevance(email)
    assert is_rel is False
    assert classify_email_intelligence(email)['is_job_related'] is False


def test_structured_schema_shape():
    email = {
        'subject': 'Interview Scheduled for September 15 with Hiring Manager',
        'body_text': 'Your interview has been scheduled for September 15 at 10:30 AM EST via Google Meet: https://meet.google.com/abc-defg-hij',
        'sender_name': 'Coordinator at Datadog', 'sender_email': 'recruiting@datadoghq.com',
        'source_folder': 'INBOX',
    }
    decision = classify_email_intelligence(email)
    assert set(['is_job_related', 'category', 'confidence', 'reason']).issubset(decision.keys())
    assert isinstance(decision['confidence'], float)
    assert 0.0 <= decision['confidence'] <= 1.0
    assert isinstance(decision['reason'], str) and decision['reason']
