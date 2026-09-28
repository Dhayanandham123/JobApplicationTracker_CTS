import datetime
import json
import logging
import urllib.request
from flask import Blueprint, request, jsonify, session, redirect, url_for, current_app, g
from routes.auth import login_required
from database.db import (
    get_db,
    get_email_connection,
    save_email_connection,
    update_email_connection_status,
    update_email_sync_timestamp,
    delete_email_connection,
    get_email_messages,
    get_email_message_by_id,
    upsert_email_message,
    update_email_message_match,
    add_application_timeline_event,
    get_application_timeline_events,
    get_user_by_id
)
from services.gmail_service import (
    get_google_auth_url,
    exchange_code_for_tokens,
    refresh_access_token,
    get_user_email_from_token,
    verify_gmail_profile_access,
    list_job_related_messages,
    get_message_detail,
    parse_gmail_message,
    GmailApiError
)
from services.email_classifier_service import (
    classify_and_extract_email,
    classify_email_intelligence,
    evaluate_recruitment_relevance,
    match_email_to_applications,
    VALID_CLASSIFICATIONS
)

logger = logging.getLogger(__name__)

email_intelligence_bp = Blueprint('email_intelligence', __name__)

# --------------------------------------------------------------------------
# 1. Google OAuth Endpoints
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/auth/google/gmail/connect')
@login_required
def connect_gmail():
    """
    Redirects user to Google OAuth 2.0 consent screen for Gmail read-only access.
    """
    user_id = session.get('user_id')
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')

    if not client_id or client_id == 'your_google_client_id_here' or client_id.startswith('YOUR_GOOGLE_CLIENT_ID'):
        # Dev fallback: mock connection if no live credentials provided
        save_email_connection(
            user_id=user_id,
            email_address=session.get('user_email', 'dev_candidate@gmail.com'),
            access_token='dev_mock_access_token',
            refresh_token='dev_mock_refresh_token',
            granted_scopes='https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email',
            status='connected'
        )
        return redirect(url_for('applications.index', view='email-intelligence', connected='true'))

    auth_url = get_google_auth_url(state=str(user_id))
    return redirect(auth_url)

@email_intelligence_bp.route('/auth/google/gmail/callback')
@login_required
def gmail_callback():
    """
    Handles Google OAuth redirect with authorization code.
    Validates granted scopes to confirm gmail.readonly permission was granted.
    """
    user_id = session.get('user_id')
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        logger.error(f"Gmail OAuth callback error: {error}")
        return redirect(url_for('applications.index', view='email-intelligence', gmail_error=error or 'oauth_failed'))

    try:
        token_data = exchange_code_for_tokens(code)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        granted_scopes = token_data.get('scope', '')

        has_gmail_scope = 'gmail.readonly' in granted_scopes
        if not has_gmail_scope:
            logger.warning(
                f"[Gmail OAuth Callback] User {user_id} did NOT grant gmail.readonly scope! "
                f"Granted scopes: '{granted_scopes}'"
            )

        token_expiry = (datetime.datetime.now() + datetime.timedelta(seconds=expires_in)).strftime('%Y-%m-%d %H:%M:%S')
        email_address = get_user_email_from_token(access_token) or session.get('user_email', 'connected@gmail.com')

        save_email_connection(
            user_id=user_id,
            email_address=email_address,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            granted_scopes=granted_scopes,
            status='connected' if has_gmail_scope else 'insufficient_permissions'
        )

        return redirect(url_for('applications.index', view='email-intelligence', connected='true'))

    except Exception as e:
        logger.error(f"Error in Gmail OAuth callback: {e}")
        return redirect(url_for('applications.index', view='email-intelligence', gmail_error='token_exchange_failed'))

# --------------------------------------------------------------------------
# 2. Connection Status & Disconnect
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/api/email-intelligence/status', methods=['GET'])
@login_required
def get_status():
    """
    Returns Gmail connection status, active authorization state, and sync metadata.
    """
    user_id = session.get('user_id')
    conn = get_email_connection(user_id)
    db = get_db()
    total_emails = db.execute('SELECT COUNT(*) as cnt FROM email_messages WHERE user_id = ?', (user_id,)).fetchone()['cnt']

    if not conn:
        return jsonify({
            'connected': False,
            'status': 'disconnected',
            'email_address': None,
            'last_synced_at': None,
            'total_scanned': total_emails
        })

    conn_status = conn['status'] if 'status' in conn.keys() and conn['status'] else 'connected'
    last_error = conn['last_error'] if 'last_error' in conn.keys() else None

    return jsonify({
        'connected': True,
        'status': conn_status,
        'email_address': conn['email_address'],
        'last_synced_at': conn['last_synced_at'],
        'total_scanned': total_emails,
        'last_error': last_error
    })

@email_intelligence_bp.route('/api/email-intelligence/disconnect', methods=['POST'])
@login_required
def disconnect_gmail():
    """
    Disconnects Gmail account and stops future syncs.
    """
    user_id = session.get('user_id')
    delete_email_connection(user_id)
    return jsonify({'success': True, 'message': 'Gmail disconnected successfully.'})

# --------------------------------------------------------------------------
# 3. Incremental Mailbox Synchronization
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/api/email-intelligence/sync', methods=['POST'])
@login_required
def sync_emails():
    """
    Incrementally fetches career-related emails from Gmail,
    classifies them with AI/heuristics, and matches them to active applications.
    """
    user_id = session.get('user_id')
    conn = get_email_connection(user_id)

    if not conn:
        return jsonify({
            'success': False,
            'error_type': 'NOT_CONNECTED',
            'error': 'Gmail is not connected. Please connect Gmail first.',
            'action': 'connect'
        }), 400

    access_token = conn['access_token']
    refresh_tok = conn['refresh_token']
    token_expiry = conn['token_expiry']

    # If mock token (dev environment without live Google Cloud OAuth credentials)
    if access_token == 'dev_mock_access_token':
        update_email_sync_timestamp(user_id)
        return jsonify({
            'success': True,
            'scanned_count': 0,
            'new_relevant_count': 0,
            'message': 'No new career updates found in inbox.'
        })

    # Step A: Check if access token is expired or close to expiring (<60s)
    token_needs_refresh = False
    if token_expiry:
        try:
            exp_dt = datetime.datetime.strptime(token_expiry, '%Y-%m-%d %H:%M:%S')
            if datetime.datetime.now() >= (exp_dt - datetime.timedelta(seconds=60)):
                token_needs_refresh = True
        except Exception as e:
            logger.warning(f"Error parsing token expiry '{token_expiry}': {e}")
            token_needs_refresh = True

    if token_needs_refresh and refresh_tok:
        logger.info(f"Access token for user {user_id} expired or expiring soon. Attempting automatic refresh...")
        new_token, new_expires_in = refresh_access_token(refresh_tok)
        if new_token:
            access_token = new_token
            new_expiry = (datetime.datetime.now() + datetime.timedelta(seconds=new_expires_in or 3600)).strftime('%Y-%m-%d %H:%M:%S')
            save_email_connection(
                user_id=user_id,
                email_address=conn['email_address'],
                access_token=new_token,
                refresh_token=refresh_tok,
                token_expiry=new_expiry,
                status='connected'
            )
            logger.info(f"Successfully refreshed access token for user {user_id}.")
        else:
            logger.warning(f"Token refresh failed for user {user_id}. Marking connection as auth_expired.")
            update_email_connection_status(user_id, 'auth_expired', last_error='Token refresh failed')
            return jsonify({
                'success': False,
                'error_type': 'AUTH_EXPIRED',
                'error': 'Your Gmail authorization has expired. Please reconnect Gmail.',
                'action': 'reconnect'
            }), 401

    # Step B: Minimal Gmail API profile pre-flight check
    api_error = None
    try:
        verify_gmail_profile_access(access_token)
    except GmailApiError as err:
        api_error = err
        # If 401 and refresh token available, attempt refresh once
        if err.status_code == 401 and refresh_tok and not token_needs_refresh:
            logger.info(f"Received 401 during profile check. Attempting token refresh...")
            new_token, new_expires_in = refresh_access_token(refresh_tok)
            if new_token:
                access_token = new_token
                new_expiry = (datetime.datetime.now() + datetime.timedelta(seconds=new_expires_in or 3600)).strftime('%Y-%m-%d %H:%M:%S')
                save_email_connection(
                    user_id=user_id,
                    email_address=conn['email_address'],
                    access_token=new_token,
                    refresh_token=refresh_tok,
                    token_expiry=new_expiry,
                    status='connected'
                )
                try:
                    verify_gmail_profile_access(access_token)
                    api_error = None
                except GmailApiError as retry_err:
                    api_error = retry_err

    if api_error:
        if api_error.error_type == 'GMAIL_API_NOT_ENABLED':
            update_email_connection_status(user_id, 'api_disabled', last_error=api_error.message)
            return jsonify({
                'success': False,
                'error_type': 'GMAIL_API_NOT_ENABLED',
                'error': 'Google Gmail access is not configured correctly. Gmail API is not enabled in your Google Cloud Project.',
                'reason': api_error.reason,
                'message': api_error.message,
                'action': 'check_gcp'
            }), 403
        elif api_error.error_type == 'INSUFFICIENT_PERMISSIONS':
            update_email_connection_status(user_id, 'insufficient_permissions', last_error=api_error.message)
            return jsonify({
                'success': False,
                'error_type': 'INSUFFICIENT_PERMISSIONS',
                'error': 'Gmail permission is missing. Please reconnect and allow read-only Gmail access.',
                'reason': api_error.reason,
                'action': 'reconnect'
            }), 403
        elif api_error.error_type == 'AUTH_EXPIRED':
            update_email_connection_status(user_id, 'auth_expired', last_error=api_error.message)
            return jsonify({
                'success': False,
                'error_type': 'AUTH_EXPIRED',
                'error': 'Your Gmail authorization has expired. Please reconnect Gmail.',
                'reason': api_error.reason,
                'action': 'reconnect'
            }), 401
        elif api_error.error_type == 'RATE_LIMIT_EXCEEDED':
            return jsonify({
                'success': False,
                'error_type': 'RATE_LIMIT_EXCEEDED',
                'error': 'Gmail API rate limit exceeded. Please wait a moment and try again.',
                'reason': api_error.reason,
                'action': 'retry'
            }), 429
        else:
            return jsonify({
                'success': False,
                'error_type': api_error.error_type,
                'error': 'Gmail is temporarily unavailable. Please try again.',
                'reason': api_error.reason,
                'action': 'retry'
            }), api_error.status_code if api_error.status_code in (400, 401, 403, 404, 429, 500, 502, 503) else 500

    # Step C: Fetch User's Applications from DB for matching
    db = get_db()
    user_apps = db.execute('SELECT id, company_name, job_title, status FROM applications WHERE user_id = ? AND (archived = 0 OR archived IS NULL)', (user_id,)).fetchall()
    user_apps_list = [dict(a) for a in user_apps]

    scanned_count = 0
    new_relevant_count = 0

    try:
        messages_list, next_page_token = list_job_related_messages(access_token, max_results=30)
        scanned_count = len(messages_list)

        for m in messages_list:
            msg_id = m.get('id')
            # 1. Deduplication check: if message already processed, skip immediately
            existing_msg = get_email_message_by_id(user_id, msg_id)
            if existing_msg:
                continue

            # Fetch full message details
            try:
                full_msg = get_message_detail(access_token, msg_id)
                parsed = parse_gmail_message(full_msg)
                logger.info(
                    "[Email Sync] msg=%s folder=%s labels=%s bulk(unsub=%s/is_bulk=%s) from=%s subject=%r",
                    msg_id, parsed.get('source_folder'), parsed.get('gmail_labels'),
                    parsed.get('has_unsubscribe'), parsed.get('is_bulk'),
                    parsed.get('sender_email'), parsed.get('subject'),
                )

                # 2. Structured relevance decision (context-based, not keywords).
                # Archived / library / non-inbox items go through the SAME
                # classifier — they never bypass filtering for existing.
                decision = classify_email_intelligence(parsed, user_apps_list)
                if not decision.get('is_job_related'):
                    logger.info(
                        "[Email Intelligence Filter] Discarding non-career email %s "
                        "('%s'): %s",
                        msg_id, parsed.get('subject'), decision.get('reason'),
                    )
                    continue

                # 3. Structured extraction already ran inside the decision;
                # reuse it so AI/heuristic classification happens exactly once.
                extraction = decision.get('extraction') or classify_and_extract_email(parsed)
                classification = decision.get('category', extraction.get('classification', 'OTHER_JOB_RELATED'))
                confidence = decision.get('confidence', extraction.get('confidence_score', 0.8))

                # 4. Multi-Signal Matching against active applications
                matched_app_id, match_conf, match_reason = match_email_to_applications(extraction, user_apps_list)

                is_action_required = 1 if classification in ['INTERVIEW_INVITATION', 'ASSESSMENT', 'OFFER', 'RECRUITER_MESSAGE'] else 0

                upsert_email_message(
                    user_id=user_id,
                    message_id=parsed['message_id'],
                    thread_id=parsed['thread_id'],
                    sender_name=parsed['sender_name'],
                    sender_email=parsed['sender_email'],
                    subject=parsed['subject'],
                    snippet=parsed['snippet'],
                    body_text=parsed['body_text'],
                    body_html_sanitized=parsed['body_html_sanitized'],
                    received_at=parsed['received_at'],
                    classification=classification,
                    confidence_score=confidence,
                    extracted_data=json.dumps(extraction),
                    matched_application_id=matched_app_id,
                    match_confidence=match_conf,
                    match_status='pending',
                    is_action_required=is_action_required,
                    gmail_labels=parsed.get('gmail_labels'),
                    source_folder=parsed.get('source_folder'),
                    has_unsubscribe=parsed.get('has_unsubscribe', False),
                    is_bulk=parsed.get('is_bulk', False),
                    is_job_related=True,
                    exclude_reason=None,
                )
                new_relevant_count += 1
            except Exception as msg_err:
                logger.error(f"Error processing message {msg_id}: {msg_err}")
                continue

        update_email_sync_timestamp(user_id, sync_cursor=next_page_token)
        update_email_connection_status(user_id, 'connected', last_error=None)

        msg_text = f"{new_relevant_count} new career update{'s' if new_relevant_count != 1 else ''} found and analyzed." if new_relevant_count > 0 else "Inbox scanned. No new career updates found."
        return jsonify({
            'success': True,
            'scanned_count': scanned_count,
            'new_relevant_count': new_relevant_count,
            'message': msg_text
        })

    except GmailApiError as api_err:
        logger.error(f"GmailApiError during sync: {api_err}")
        return jsonify({
            'success': False,
            'error_type': api_err.error_type,
            'error': 'Gmail sync could not be completed. Please try again.',
            'action': 'retry'
        }), api_err.status_code if api_err.status_code in (400, 401, 403, 404, 429, 500, 502, 503) else 500
    except Exception as e:
        logger.error(f"Unexpected error during Gmail sync: {e}")
        return jsonify({
            'success': False,
            'error_type': 'UNEXPECTED_ERROR',
            'error': 'An unexpected error occurred during sync. Please try again.',
            'action': 'retry'
        }), 500

# --------------------------------------------------------------------------
# 4. Email Messages List & Statistics
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/api/email-intelligence/emails', methods=['GET'])
@login_required
def get_emails():
    """
    Returns list of synced career emails with parsed extractions and matching info.
    Only job-related messages are returned; rows explicitly marked as
    non-job-related (is_job_related=0, e.g. newsletters, digests, library
    noise) are excluded. Legacy rows predating relevance tracking
    (is_job_related IS NULL) are still shown for backward compatibility.
    """
    user_id = session.get('user_id')
    rows = get_email_messages(user_id, limit=60, job_related_only=True)

    result = []
    for r in rows:
        item = dict(r)
        # Parse JSON extracted data
        try:
            item['extracted_data'] = json.loads(item['extracted_data']) if item.get('extracted_data') else {}
        except:
            item['extracted_data'] = {}
        result.append(item)

    return jsonify({'emails': result})

@email_intelligence_bp.route('/api/email-intelligence/stats', methods=['GET'])
@login_required
def get_stats():
    """
    Returns compact statistics for the Email Intelligence view.
    """
    user_id = session.get('user_id')
    db = get_db()

    # Only count messages that passed the relevance decision. Legacy rows
    # without relevance tracking (is_job_related IS NULL) still count.
    rel_filter = "AND (is_job_related IS NULL OR is_job_related = 1)"
    total_emails = db.execute(f'SELECT COUNT(*) as cnt FROM email_messages WHERE user_id = ? {rel_filter}', (user_id,)).fetchone()['cnt']

    interviews = db.execute(f'''
        SELECT COUNT(*) as cnt FROM email_messages
        WHERE user_id = ? {rel_filter} AND classification IN ('INTERVIEW_INVITATION', 'INTERVIEW_UPDATE')
    ''', (user_id,)).fetchone()['cnt']

    assessments = db.execute(f'''
        SELECT COUNT(*) as cnt FROM email_messages
        WHERE user_id = ? {rel_filter} AND classification = 'ASSESSMENT'
    ''', (user_id,)).fetchone()['cnt']

    offers = db.execute(f'''
        SELECT COUNT(*) as cnt FROM email_messages
        WHERE user_id = ? {rel_filter} AND classification = 'OFFER'
    ''', (user_id,)).fetchone()['cnt']

    needs_review = db.execute(f'''
        SELECT COUNT(*) as cnt FROM email_messages
        WHERE user_id = ? {rel_filter} AND (classification = 'NEEDS_REVIEW' OR confidence_score < 0.75 OR (matched_application_id IS NULL AND match_status = 'pending'))
    ''', (user_id,)).fetchone()['cnt']

    return jsonify({
        'total_career_emails': total_emails,
        'interviews': interviews,
        'assessments': assessments,
        'offers': offers,
        'needs_review': needs_review
    })

# --------------------------------------------------------------------------
# 5. User Confirmations & Actions
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/api/email-intelligence/confirm-match', methods=['POST'])
@login_required
def confirm_match():
    """
    User confirms proposed application match and status update.
    Updates application record and writes an auditable Application Timeline event.
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}
    message_id = data.get('message_id')
    application_id = data.get('application_id')
    new_status = data.get('new_status')

    if not message_id or not application_id:
        return jsonify({'error': 'Missing message_id or application_id'}), 400

    db = get_db()
    app_row = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (application_id, user_id)).fetchone()
    if not app_row:
        return jsonify({'error': 'Application not found'}), 404

    email_row = get_email_message_by_id(user_id, message_id)
    if not email_row:
        return jsonify({'error': 'Email not found'}), 404

    extracted = json.loads(email_row['extracted_data']) if email_row['extracted_data'] else {}
    old_status = app_row['status']
    target_status = new_status or extracted.get('proposed_status') or old_status

    # Validate status
    if target_status not in ['Applied', 'Interviewing', 'Offered', 'Rejected']:
        target_status = old_status

    now_str = datetime.datetime.now().strftime('%Y-%m-%d')

    # Update application status & extracted dates
    interview_date = extracted.get('interview_date') or app_row['interview_date']
    assessment_date = extracted.get('assessment_deadline') or app_row['assessment_date']

    db.execute('''
        UPDATE applications
        SET status = ?,
            last_updated = ?,
            interview_date = ?,
            assessment_date = ?
        WHERE id = ? AND user_id = ?
    ''', (target_status, now_str, interview_date, assessment_date, application_id, user_id))

    # Mark email message match as confirmed
    update_email_message_match(message_id, user_id, application_id, match_status='confirmed')

    # Create Auditable Timeline Event
    event_title = f"{email_row['classification'].replace('_', ' ').title()}"
    desc = f"Email from {email_row['sender_name'] or email_row['sender_email']}: {email_row['subject']}"
    if old_status != target_status:
        desc += f" (Status updated: {old_status} → {target_status})"

    add_application_timeline_event(
        application_id=application_id,
        user_id=user_id,
        event_type=email_row['classification'],
        event_title=event_title,
        event_description=desc,
        event_date=email_row['received_at'] or now_str,
        source='GMAIL',
        email_id=message_id
    )

    return jsonify({
        'success': True,
        'message': f"Application updated to '{target_status}'.",
        'new_status': target_status
    })

@email_intelligence_bp.route('/api/email-intelligence/ignore-match', methods=['POST'])
@login_required
def ignore_match():
    """
    User ignores the proposed email match.
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}
    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    db = get_db()
    db.execute('''
        UPDATE email_messages
        SET match_status = 'ignored'
        WHERE message_id = ? AND user_id = ?
    ''', (message_id, user_id))
    db.commit()

    return jsonify({'success': True, 'message': 'Update proposal ignored.'})

@email_intelligence_bp.route('/api/email-intelligence/add-calendar-event', methods=['POST'])
@login_required
def add_calendar_event():
    """
    Adds detected interview or assessment event to the existing calendar system.
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}
    message_id = data.get('message_id')
    application_id = data.get('application_id')
    event_date = data.get('event_date')
    event_type = data.get('event_type', 'interview') # 'interview' or 'assessment'

    if not application_id or not event_date:
        return jsonify({'error': 'Missing application_id or event_date'}), 400

    db = get_db()
    app_row = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (application_id, user_id)).fetchone()
    if not app_row:
        return jsonify({'error': 'Application not found'}), 404

    if event_type == 'assessment':
        db.execute('UPDATE applications SET assessment_date = ? WHERE id = ? AND user_id = ?', (event_date, application_id, user_id))
        title = "Assessment Scheduled"
    else:
        db.execute('UPDATE applications SET interview_date = ? WHERE id = ? AND user_id = ?', (event_date, application_id, user_id))
        title = "Interview Scheduled"

    db.commit()

    # Add timeline event
    add_application_timeline_event(
        application_id=application_id,
        user_id=user_id,
        event_type=f"{event_type.upper()}_SCHEDULED",
        event_title=title,
        event_description=f"Scheduled for {event_date} via Email Intelligence",
        event_date=event_date,
        source='GMAIL',
        email_id=message_id
    )

    return jsonify({'success': True, 'message': f'{title} on {event_date} added to Calendar.'})

# --------------------------------------------------------------------------
# 6. Recruiter AI Draft Reply Generator
# --------------------------------------------------------------------------
@email_intelligence_bp.route('/api/email-intelligence/draft-reply', methods=['POST'])
@login_required
def draft_recruiter_reply():
    """
    Generates an editable AI reply draft to a recruiter email based on context.
    """
    user_id = session.get('user_id')
    data = request.get_json() or {}
    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'Missing message_id'}), 400

    email_row = get_email_message_by_id(user_id, message_id)
    if not email_row:
        return jsonify({'error': 'Email not found'}), 404

    user = get_user_by_id(user_id)
    candidate_name = user['full_name'] or user['username'] if user else 'Candidate'

    api_key = current_app.config.get('GROQ_API_KEY', '').strip()

    prompt = (
        f"You are an expert career advisor assisting a job candidate.\n"
        f"Write a polished, professional, and concise email reply to a recruiter.\n\n"
        f"Candidate Name: {candidate_name}\n"
        f"Recruiter Name: {email_row['sender_name'] or 'Hiring Team'}\n"
        f"Subject: Re: {email_row['subject']}\n"
        f"Original Email Excerpt:\n{email_row['body_text'][:1500]}\n\n"
        f"Guidelines:\n"
        f"- Thank them politely.\n"
        f"- State enthusiasm for the opportunity.\n"
        f"- If an interview or assessment was offered, confirm availability.\n"
        f"- Keep the tone professional, confident, and warm.\n"
        f"- Return ONLY the email body text without extra metadata."
    )

    if api_key:
        try:
            payload = json.dumps({
                'model': current_app.config.get('GROQ_MODEL', 'llama-3.3-70b-versatile'),
                'messages': [
                    {'role': 'system', 'content': 'You are a professional email copywriter.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.7,
                'max_tokens': 350
            }).encode('utf-8')

            req = urllib.request.Request(
                'https://api.groq.com/openai/v1/chat/completions',
                data=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode('utf-8'))
                draft_text = res_data['choices'][0]['message']['content'].strip()
                return jsonify({'draft': draft_text})
        except Exception as e:
            logger.warning(f"Error generating AI reply draft: {e}")

    # Fallback template
    recruiter_greeting = f"Hi {email_row['sender_name'].split()[0]}," if email_row['sender_name'] and ' ' in email_row['sender_name'] else "Hi Hiring Team,"
    fallback_draft = (
        f"{recruiter_greeting}\n\n"
        f"Thank you for reaching out regarding my application for the role. "
        f"I am very excited about the opportunity and would be glad to discuss my background further.\n\n"
        f"I am available for an interview this week and look forward to hearing about the next steps.\n\n"
        f"Best regards,\n"
        f"{candidate_name}"
    )

    return jsonify({'draft': fallback_draft})
