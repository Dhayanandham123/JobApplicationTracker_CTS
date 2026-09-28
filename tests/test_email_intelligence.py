import json
import pytest
from app import create_app
from database.db import get_db, init_db, save_email_connection, upsert_email_message, add_application_timeline_event
from services.email_classifier_service import (
    _classify_with_heuristics,
    match_email_to_applications
)

@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_email.db"
    test_config = {
        'TESTING': True,
        'DATABASE': str(db_file),
        'SECRET_KEY': 'test-email-key',
        'GOOGLE_CLIENT_ID': 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com'
    }
    app = create_app(test_config)
    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client

def test_heuristic_classification_interview():
    subject = "Interview Invitation: Software Engineer at Stripe"
    body = "Hi Candidate, We would like to invite you for a virtual technical interview on September 15, 2026 at 10:00 AM EST. https://meet.google.com/abc-defg-hij"
    sender_name = "Jane Doe at Stripe"
    sender_email = "jane@stripe.com"

    result = _classify_with_heuristics(subject, body, sender_name, sender_email)
    assert result['classification'] == 'INTERVIEW_INVITATION'
    assert result['proposed_status'] == 'Interviewing'
    assert result['company_name'] == 'Stripe'
    assert result['interview_date'] == '2026-09-15'
    assert result['interview_time'] == '10:00 AM EST'
    assert result['meeting_link'] == 'https://meet.google.com/abc-defg-hij'

def test_heuristic_classification_rejection():
    subject = "Status Update regarding your application"
    body = "Thank you for your interest, but unfortunately we are pursuing other candidates at this time."
    sender_name = "Talent Team"
    sender_email = "careers@amazon.com"

    result = _classify_with_heuristics(subject, body, sender_name, sender_email)
    assert result['classification'] == 'REJECTION'
    assert result['proposed_status'] == 'Rejected'
    assert result['company_name'] == 'Amazon'

def test_heuristic_classification_offer():
    subject = "Job Offer: Senior Frontend Engineer"
    body = "We are pleased to offer you the position of Senior Frontend Engineer!"
    sender_name = "HR Team"
    sender_email = "hr@meta.com"

    result = _classify_with_heuristics(subject, body, sender_name, sender_email)
    assert result['classification'] == 'OFFER'
    assert result['proposed_status'] == 'Offered'
    assert result['company_name'] == 'Meta'

def test_multi_signal_matcher():
    user_apps = [
        {'id': 1, 'company_name': 'Google', 'job_title': 'Software Engineer', 'status': 'Applied'},
        {'id': 2, 'company_name': 'Microsoft', 'job_title': 'Product Manager', 'status': 'Applied'}
    ]

    extraction = {
        'company_name': 'Google',
        'job_title': 'Software Engineer',
        'recruiter_email': 'recruiter@google.com'
    }

    matched_id, conf, reason = match_email_to_applications(extraction, user_apps)
    assert matched_id == 1
    assert conf >= 0.80
    assert "company match" in reason.lower()

def test_email_intelligence_flow_authenticated(client):
    # 1. Register and Login
    client.post('/signup', data={
        'username': 'tester_email',
        'email': 'tester@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)

    # 2. Check initial status (Disconnected)
    res = client.get('/api/email-intelligence/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['connected'] is False
    assert data['total_scanned'] == 0

    # 3. Connect Gmail (dev mock redirect)
    connect_res = client.get('/auth/google/gmail/connect', follow_redirects=True)
    assert connect_res.status_code == 200

    # 4. Check status after connect (Connected)
    res2 = client.get('/api/email-intelligence/status')
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2['connected'] is True

    # 5. Create an Application in DB
    with client.session_transaction() as sess:
        user_id = sess['user_id']

    app_res = client.post('/applications', json={
        'company_name': 'Netflix',
        'job_title': 'Backend Engineer',
        'status': 'Applied',
        'date_applied': '2026-09-01'
    })
    assert app_res.status_code == 201
    created_app = app_res.get_json()
    app_id = created_app['id']

    # 6. Simulate synced email message
    upsert_email_message(
        user_id=user_id,
        message_id='msg_netflix_123',
        thread_id='th_123',
        sender_name='Recruiter at Netflix',
        sender_email='recruiter@netflix.com',
        subject='Interview with Netflix for Backend Engineer',
        snippet='We would like to invite you for an interview...',
        body_text='We would like to schedule an interview on 2026-09-10.',
        body_html_sanitized='<p>We would like to schedule an interview on 2026-09-10.</p>',
        received_at='2026-09-01 10:00:00',
        classification='INTERVIEW_INVITATION',
        confidence_score=0.92,
        extracted_data=json.dumps({
            'company_name': 'Netflix',
            'job_title': 'Backend Engineer',
            'proposed_status': 'Interviewing',
            'interview_date': '2026-09-10',
            'interview_time': '2:00 PM',
            'key_summary': 'Interview scheduled for 2026-09-10'
        }),
        matched_application_id=app_id,
        match_confidence=0.95,
        match_status='pending',
        is_action_required=1
    )

    # 7. Verify stats & emails list
    stats_res = client.get('/api/email-intelligence/stats')
    assert stats_res.status_code == 200
    stats_data = stats_res.get_json()
    assert stats_data['total_career_emails'] == 1
    assert stats_data['interviews'] == 1

    emails_res = client.get('/api/email-intelligence/emails')
    assert emails_res.status_code == 200
    emails_data = emails_res.get_json()
    assert len(emails_data['emails']) == 1
    assert emails_data['emails'][0]['matched_company_name'] == 'Netflix'

    # 8. Confirm Match & Update Application
    confirm_res = client.post('/api/email-intelligence/confirm-match', json={
        'message_id': 'msg_netflix_123',
        'application_id': app_id,
        'new_status': 'Interviewing'
    })
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.get_json()
    assert confirm_data['success'] is True
    assert confirm_data['new_status'] == 'Interviewing'

    # Verify application status was updated
    detail_res = client.get(f'/applications/{app_id}')
    assert detail_res.status_code == 200
    assert detail_res.get_json()['status'] == 'Interviewing'

    # 9. Verify Application Activity Timeline
    timeline_res = client.get(f'/api/applications/{app_id}/timeline')
    assert timeline_res.status_code == 200
    timeline_data = timeline_res.get_json()
    assert len(timeline_data['timeline']) >= 2 # Application Submitted + Email Update

    # 10. Generate Recruiter Reply Draft
    draft_res = client.post('/api/email-intelligence/draft-reply', json={
        'message_id': 'msg_netflix_123'
    })
    assert draft_res.status_code == 200
    draft_data = draft_res.get_json()
    assert 'draft' in draft_data
    assert len(draft_data['draft']) > 20

    # 11. Disconnect Gmail
    disc_res = client.post('/api/email-intelligence/disconnect')
    assert disc_res.status_code == 200
    assert disc_res.get_json()['success'] is True

    # Status check after disconnect
    res_after_disc = client.get('/api/email-intelligence/status')
    assert res_after_disc.get_json()['connected'] is False

def test_google_api_error_parsing_api_disabled():
    from services.gmail_service import parse_google_api_error, GmailApiError
    import io
    import urllib.error

    json_payload = json.dumps({
        "error": {
            "code": 403,
            "message": "Gmail API has not been used in project 123456789 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=123456789 then retry.",
            "errors": [
                {
                    "message": "Gmail API has not been used in project 123456789 before or it is disabled.",
                    "domain": "usageLimits",
                    "reason": "accessNotConfigured"
                }
            ],
            "status": "PERMISSION_DENIED"
        }
    }).encode('utf-8')

    mock_err = urllib.error.HTTPError(
        url="https://gmail.googleapis.com/gmail/v1/users/me/profile",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(json_payload)
    )

    err = parse_google_api_error(mock_err, endpoint="GMAIL_GET_PROFILE")
    assert isinstance(err, GmailApiError)
    assert err.status_code == 403
    assert err.reason == "accessNotConfigured"
    assert err.error_type == "GMAIL_API_NOT_ENABLED"
    assert "Gmail API has not been used in project" in err.message

def test_google_api_error_parsing_insufficient_permissions():
    from services.gmail_service import parse_google_api_error, GmailApiError
    import io
    import urllib.error

    json_payload = json.dumps({
        "error": {
            "code": 403,
            "message": "Request had insufficient authentication scopes.",
            "status": "PERMISSION_DENIED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
                }
            ]
        }
    }).encode('utf-8')

    mock_err = urllib.error.HTTPError(
        url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(json_payload)
    )

    err = parse_google_api_error(mock_err, endpoint="GMAIL_LIST_MESSAGES")
    assert isinstance(err, GmailApiError)
    assert err.status_code == 403
    assert err.error_type == "INSUFFICIENT_PERMISSIONS"
    assert "insufficient" in err.message.lower()

def test_oauth_callback_redirect_to_dashboard_html(client):
    # Register and login
    client.post('/signup', data={
        'username': 'oauth_redirect_user',
        'email': 'oauth_user@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)

    # 1. Dev connect should redirect to HTML dashboard with view=email-intelligence
    conn_res = client.get('/auth/google/gmail/connect', follow_redirects=False)
    assert conn_res.status_code == 302
    assert conn_res.location.startswith('/?')
    assert 'view=email-intelligence' in conn_res.location
    assert 'connected=true' in conn_res.location

    # 2. Accessing /applications?view=email-intelligence in browser should redirect to HTML dashboard
    apps_view_res = client.get('/applications?view=email-intelligence&connected=true', follow_redirects=False)
    assert apps_view_res.status_code == 302
    assert apps_view_res.location.startswith('/?')
    assert 'view=email-intelligence' in apps_view_res.location

def test_two_stage_relevance_exclusion_filter():
    from services.email_classifier_service import evaluate_recruitment_relevance

    # 1. Amazon order shipped
    msg_amazon_order = {
        'subject': 'Amazon.com: Your order #112-3456789-1234567 has shipped',
        'body_text': 'Hi, your Amazon package has shipped and will arrive tomorrow. Track your delivery.',
        'sender_name': 'Amazon Shipments',
        'sender_email': 'shipment-tracking@amazon.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_amazon_order)
    assert is_rel is False
    assert any('E-Commerce' in r for r in reasons)

    # 2. Amazon Prime Deals
    msg_amazon_deals = {
        'subject': 'Amazon Prime: Exclusive deals on electronics this weekend',
        'body_text': 'Check out 50% discount deals on laptops, monitors, and accessories.',
        'sender_name': 'Amazon Deals',
        'sender_email': 'deals@amazon.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_amazon_deals)
    assert is_rel is False

    # 3. Bank Transaction
    msg_bank = {
        'subject': 'Alert: Your A/C has been debited by USD 45.00',
        'body_text': 'Your account has been debited for transaction reference UPI/123456. Available bank balance USD 2,450.00',
        'sender_name': 'Chase Bank',
        'sender_email': 'alerts@chase.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_bank)
    assert is_rel is False
    assert any('Banking' in r for r in reasons)

    # 4. OTP / Verification Code
    msg_otp = {
        'subject': 'Your One Time Password (OTP) is 492810',
        'body_text': 'Do not share your verification code with anyone. This OTP is valid for 10 minutes.',
        'sender_name': 'Security Service',
        'sender_email': 'no-reply@auth.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_otp)
    assert is_rel is False
    assert any('Security' in r for r in reasons)

    # 5. Marketing Newsletter
    msg_newsletter = {
        'subject': 'TechWeekly Digest #142: Future of AI and Cloud',
        'body_text': 'Read our weekly newsletter. Unsubscribe here if you no longer wish to receive updates.',
        'sender_name': 'TechWeekly Newsletter',
        'sender_email': 'newsletter@techweekly.io'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_newsletter)
    assert is_rel is False

    # 6. Food Delivery
    msg_swiggy = {
        'subject': 'Swiggy: Order confirmed! Delivery in 25 mins',
        'body_text': 'Your food order from Burger King has been placed. Track order.',
        'sender_name': 'Swiggy',
        'sender_email': 'orders@swiggy.in'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_swiggy)
    assert is_rel is False

    # 7. GitHub Star Notification
    msg_github = {
        'subject': '[GitHub] alex starred your repository username/project',
        'body_text': 'You received a new star on repository username/project.',
        'sender_name': 'GitHub',
        'sender_email': 'notifications@github.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_github)
    assert is_rel is False

    # 8. College Announcement Fee Payment
    msg_college = {
        'subject': 'College Notice: Semester exam fee submission last date',
        'body_text': 'All students must submit exam fees by September 20 at the admin office.',
        'sender_name': 'College Office',
        'sender_email': 'admin@kce.ac.in'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_college)
    assert is_rel is False

    # 9. LinkedIn Promotional
    msg_linkedin_promo = {
        'subject': 'LinkedIn: 50% discount on LinkedIn Premium for 3 months',
        'body_text': 'Upgrade to Premium today with exclusive discount code. View in browser.',
        'sender_name': 'LinkedIn Offers',
        'sender_email': 'promotions@linkedin.com'
    }
    is_rel, score, reasons = evaluate_recruitment_relevance(msg_linkedin_promo)
    assert is_rel is False

def test_two_stage_relevance_acceptance_filter():
    from services.email_classifier_service import evaluate_recruitment_relevance

    # 1. Interview Invitation
    msg1 = {
        'subject': 'Interview Invitation - Software Engineer at Stripe',
        'body_text': 'Hi, We would like to schedule a technical interview on September 15. Please choose a time slot.',
        'sender_name': 'Jane Recruiter at Stripe',
        'sender_email': 'recruiting@stripe.com'
    }
    is_rel1, score1, _ = evaluate_recruitment_relevance(msg1)
    assert is_rel1 is True
    assert score1 >= 5.0

    # 2. Application Received
    msg2 = {
        'subject': 'Your application has been received - Google',
        'body_text': 'Thank you for applying for the Software Engineer role at Google. We are reviewing your application.',
        'sender_name': 'Google Careers',
        'sender_email': 'no-reply@greenhouse.io'
    }
    is_rel2, score2, _ = evaluate_recruitment_relevance(msg2)
    assert is_rel2 is True
    assert score2 >= 4.0

    # 3. Technical Assessment Invitation
    msg3 = {
        'subject': 'Technical Assessment Invitation - Backend Engineer',
        'body_text': 'Please complete the coding assessment on HackerRank within 48 hours. Link to complete the test: https://hackerrank.com/test123',
        'sender_name': 'Talent Team',
        'sender_email': 'careers@hackerrank.com'
    }
    is_rel3, score3, _ = evaluate_recruitment_relevance(msg3)
    assert is_rel3 is True
    assert score3 >= 5.0

    # 4. Next Steps in Application
    msg4 = {
        'subject': 'Next Steps in Your Application for Frontend Developer',
        'body_text': 'We are pleased to inform you that you have advanced to the next round. We would like to schedule an interview with the hiring manager.',
        'sender_name': 'Talent Acquisition Team',
        'sender_email': 'recruiting@lever.co'
    }
    is_rel4, score4, _ = evaluate_recruitment_relevance(msg4)
    assert is_rel4 is True
    assert score4 >= 4.0

    # 5. Interview Scheduled
    msg5 = {
        'subject': 'Interview Scheduled for September 15 with Hiring Manager',
        'body_text': 'Your interview has been scheduled for September 15 at 10:30 AM EST via Google Meet: https://meet.google.com/abc-defg-hij',
        'sender_name': 'Coordinator at Datadog',
        'sender_email': 'recruiting@datadoghq.com'
    }
    is_rel5, score5, _ = evaluate_recruitment_relevance(msg5)
    assert is_rel5 is True
    assert score5 >= 5.0

    # 6. Job Offer
    msg6 = {
        'subject': 'Congratulations! Job Offer from Microsoft',
        'body_text': 'We are pleased to offer you the position of Software Engineer. Please find your offer letter and compensation details attached.',
        'sender_name': 'HR Operations',
        'sender_email': 'talent@microsoft.com'
    }
    is_rel6, score6, _ = evaluate_recruitment_relevance(msg6)
    assert is_rel6 is True
    assert score6 >= 5.0

    # 7. Rejection update
    msg7 = {
        'subject': 'Unfortunately, we will not be moving forward with your application',
        'body_text': 'Thank you for your time. Unfortunately, after careful consideration, we are pursuing other candidates at this time.',
        'sender_name': 'Recruitment Team',
        'sender_email': 'careers@netflix.com'
    }
    is_rel7, score7, _ = evaluate_recruitment_relevance(msg7)
    assert is_rel7 is True
    assert score7 >= 4.5

    # 8. Recruiter reaching out
    msg8 = {
        'subject': 'Recruiter - Software Engineer Opportunity at Adobe',
        'body_text': 'Hi, I am a recruiter at Adobe. I came across your background and would love to connect about an open software engineering role.',
        'sender_name': 'Sarah Smith (Talent Acquisition)',
        'sender_email': 'sarah@adobe.com'
    }
    is_rel8, score8, _ = evaluate_recruitment_relevance(msg8)
    assert is_rel8 is True
    assert score8 >= 4.0

    # 9. Online Coding Assessment
    msg9 = {
        'subject': 'Online Coding Assessment - Amazon SDE',
        'body_text': 'You have been invited to take the online coding assessment for Amazon SDE on Codility. Please complete the assessment by Friday.',
        'sender_name': 'Amazon University Recruiting',
        'sender_email': 'university-recruiting@amazon.com'
    }
    is_rel9, score9, _ = evaluate_recruitment_relevance(msg9)
    assert is_rel9 is True
    assert score9 >= 5.0

    # 10. Application Status Changed
    msg10 = {
        'subject': 'Your application status has changed - Workday',
        'body_text': 'Status update regarding your application for Cloud Architect. Please log in to the candidate portal to view next steps.',
        'sender_name': 'Workday Recruiting Portal',
        'sender_email': 'notifications@myworkday.com'
    }
    is_rel10, score10, _ = evaluate_recruitment_relevance(msg10)
    assert is_rel10 is True
    assert score10 >= 4.0

def test_two_stage_relevance_with_app_matching():
    from services.email_classifier_service import evaluate_recruitment_relevance

    user_apps = [
        {'id': 10, 'company_name': 'Amazon', 'job_title': 'Full Stack Developer', 'status': 'Applied'}
    ]

    # Amazon Interview vs Active App -> Highly Relevant
    msg_interview = {
        'subject': 'Your Amazon interview has been scheduled',
        'body_text': 'We look forward to speaking with you regarding your application for Full Stack Developer.',
        'sender_name': 'Amazon Talent Team',
        'sender_email': 'recruiting@amazon.com'
    }
    is_rel, score, signals = evaluate_recruitment_relevance(msg_interview, user_apps)
    assert is_rel is True
    assert score >= 7.0
    assert any('Matched active application company' in s for s in signals)

    # Amazon Prime Deals vs Active App -> MUST STILL BE REJECTED (Exclusion rules)
    msg_prime = {
        'subject': 'Amazon Prime deals are here',
        'body_text': 'Shop millions of deals with fast shipping.',
        'sender_name': 'Amazon Prime',
        'sender_email': 'deals@amazon.com'
    }
    is_rel_prime, score_prime, _ = evaluate_recruitment_relevance(msg_prime, user_apps)
    assert is_rel_prime is False
