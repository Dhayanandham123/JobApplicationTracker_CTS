import base64
import datetime
import json
import logging
import re
import urllib.parse
import urllib.request
from flask import current_app

logger = logging.getLogger(__name__)

# Google OAuth Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Scopes: Read-only access for Gmail and User Info
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email"
]

class GmailApiError(Exception):
    """
    Structured exception capturing exact Google API diagnostic information
    without leaking access tokens, refresh tokens, or user credentials.
    """
    def __init__(self, status_code, reason, message, details=None, error_type=None, google_raw=None, endpoint=None):
        self.status_code = status_code
        self.reason = reason
        self.message = message
        self.details = details or {}
        self.error_type = error_type or 'UNKNOWN_ERROR'
        self.google_raw = google_raw
        self.endpoint = endpoint
        super().__init__(f"Gmail API Error {status_code} [{self.error_type}]: {self.message}")

def parse_google_api_error(http_error, endpoint=None):
    """
    Parses exact Google API error payload from urllib.error.HTTPError without leaking credentials.
    """
    status_code = getattr(http_error, 'code', 500)
    reason = getattr(http_error, 'reason', 'Error')
    message = str(http_error)
    details = {}
    error_type = 'API_ERROR'
    raw_body = ""

    try:
        if hasattr(http_error, 'read'):
            raw_body = http_error.read().decode('utf-8', errors='replace')
        if raw_body:
            parsed = json.loads(raw_body)
            err_obj = parsed.get('error', {})
            if isinstance(err_obj, dict):
                message = err_obj.get('message', message)
                errors_list = err_obj.get('errors', [])
                if errors_list and isinstance(errors_list, list) and len(errors_list) > 0:
                    first_err = errors_list[0]
                    reason = first_err.get('reason', reason)
                    details = first_err
                elif err_obj.get('details'):
                    details = err_obj.get('details')

                # Categorize Google Error Type
                if reason == 'accessNotConfigured' or 'has not been used in project' in message or 'disabled' in message.lower():
                    error_type = 'GMAIL_API_NOT_ENABLED'
                elif reason == 'insufficientPermissions' or 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in str(details) or 'insufficient' in message.lower():
                    error_type = 'INSUFFICIENT_PERMISSIONS'
                elif status_code == 401 or reason in ('invalid_grant', 'authError', 'tokenExpired'):
                    error_type = 'AUTH_EXPIRED'
                elif status_code == 403 and ('rateLimitExceeded' in reason or 'userRateLimitExceeded' in reason or 'dailyLimitExceeded' in reason):
                    error_type = 'RATE_LIMIT_EXCEEDED'
                elif status_code >= 500:
                    error_type = 'GOOGLE_SERVER_ERROR'
    except Exception as parse_err:
        logger.warning(f"Could not parse Google JSON error response: {parse_err}")

    logger.error(
        f"[Gmail API Diagnostic] HTTP {status_code} on {endpoint or 'Gmail API'} | "
        f"Type: {error_type} | Reason: {reason} | Message: {message}"
    )

    return GmailApiError(
        status_code=status_code,
        reason=reason,
        message=message,
        details=details,
        error_type=error_type,
        google_raw=raw_body,
        endpoint=endpoint
    )

def get_google_auth_url(state=None):
    """
    Constructs Google OAuth 2.0 authorization URL for Gmail read-only access.
    """
    client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    redirect_uri = current_app.config.get('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:5000/auth/google/gmail/callback')

    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(GMAIL_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true'
    }
    if state:
        params['state'] = state

    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_tokens(code):
    """
    Exchanges Google authorization code for access and refresh tokens.
    """
    client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET', '')
    redirect_uri = current_app.config.get('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:5000/auth/google/gmail/callback')

    payload = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }).encode('utf-8')

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            token_data = json.loads(response.read().decode('utf-8'))
            return token_data
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint="GOOGLE_TOKEN_EXCHANGE")
        raise parsed_err
    except Exception as e:
        logger.error(f"Error during Google token exchange: {e}")
        raise e

def refresh_access_token(refresh_token):
    """
    Uses refresh token to get a new access token and expires_in duration.
    Returns: (new_access_token, expires_in) or (None, None)
    """
    if not refresh_token:
        return None, None

    client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET', '')

    payload = urllib.parse.urlencode({
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token'
    }).encode('utf-8')

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            token_data = json.loads(response.read().decode('utf-8'))
            new_access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)
            return new_access_token, expires_in
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint="GOOGLE_TOKEN_REFRESH")
        logger.warning(f"Failed to refresh Google token: {parsed_err.message}")
        return None, None
    except Exception as e:
        logger.warning(f"Network error refreshing Google token: {e}")
        return None, None

def get_user_email_from_token(access_token):
    """
    Retrieves the connected Gmail address from Google UserInfo API.
    """
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            info = json.loads(response.read().decode('utf-8'))
            return info.get('email')
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint="GOOGLE_USERINFO")
        logger.warning(f"Failed to fetch user email: {parsed_err.message}")
        return None
    except Exception as e:
        logger.warning(f"Error fetching user email from token: {e}")
        return None

def verify_gmail_profile_access(access_token):
    """
    Tests minimal Gmail API access (GET /profile) to verify scopes and API enablement
    before running the full search and classification pipeline.
    """
    url = f"{GMAIL_API_BASE}/profile"
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {access_token}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint="GMAIL_GET_PROFILE")
        raise parsed_err
    except Exception as e:
        logger.error(f"Gmail verify profile network error: {e}")
        raise e

def list_job_related_messages(access_token, query=None, max_results=30, page_token=None):
    """
    Queries Gmail API for messages matching career/recruitment keywords
    with explicit exclusions for promotional, social, and transactional noise.
    Targeted search avoids scanning the user's entire mailbox.

    Source/folder policy: defaults to the user's INBOX only (``in:inbox``).
    Without this, Gmail full-text search also returns archived / sent /
    library (all-mail) items, which previously leaked stale reference mail
    into Email Intelligence. Callers may pass an explicit ``query`` to
    override (e.g. to include archives), but every message is still run
    through the same relevance classifier and label tracking below — an
    archived/library message never bypasses filtering.
    """
    if not query:
        query = (
            'in:inbox '
            '("interview" OR "interview invitation" OR "interview scheduled" OR "interview process" '
            'OR "technical interview" OR "phone screen" OR "coding interview" OR "coding assessment" '
            'OR "technical assessment" OR "online assessment" OR "assessment" OR "hackerrank" '
            'OR "codility" OR "test invitation" OR "job offer" OR "offer letter" OR "employment offer" '
            'OR "application received" OR "application status" OR "application update" OR "application submitted" '
            'OR "application rejected" OR "not selected" OR "next steps" OR "next round" OR "final round" '
            'OR "recruiter" OR "recruitment" OR "talent acquisition" OR "hiring manager" '
            'OR from:greenhouse.io OR from:lever.co OR from:myworkday.com OR from:workday.com '
            'OR from:smartrecruiters.com OR from:ashbyhq.com OR from:icims.com OR from:jobvite.com '
            'OR from:taleo.net OR from:hackerrank.com OR from:codility.com OR from:hirevue.com OR from:karat.com) '
            '-category:promotions -category:social -category:forums '
            '-{"order confirmation" "your order" "order shipped" "delivered" "invoice" "receipt" "otp" "password reset" "flight ticket" "statement"}'
        )

    params = {
        'q': query,
        'maxResults': min(max_results, 50)
    }
    if page_token:
        params['pageToken'] = page_token

    url = f"{GMAIL_API_BASE}/messages?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {access_token}'}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('messages', []), data.get('nextPageToken')
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint="GMAIL_LIST_MESSAGES")
        raise parsed_err
    except Exception as e:
        logger.error(f"Gmail list messages error: {e}")
        raise e

def get_message_detail(access_token, message_id):
    """
    Fetches the full message metadata and content by message ID.
    """
    url = f"{GMAIL_API_BASE}/messages/{message_id}?format=full"
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {access_token}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        parsed_err = parse_google_api_error(e, endpoint=f"GMAIL_GET_MESSAGE_{message_id}")
        raise parsed_err
    except Exception as e:
        logger.error(f"Gmail get message detail error: {e}")
        raise e

def parse_gmail_message(msg_data):
    """
    Parses Gmail message payload into structured fields:
    - sender_name, sender_email, subject, received_at, snippet, body_text, body_html_sanitized
    - gmail_labels: raw Gmail labelIds (e.g. INBOX, SPAM, TRASH, SENT, UNREAD, CATEGORY_*)
    - source_folder: derived primary folder (INBOX / SPAM / TRASH / SENT / ARCHIVE / OTHER)
    - has_unsubscribe: True when a List-Unsubscribe header is present (bulk/newsletter signal)
    - is_bulk: True for auto-submitted / bulk-precedence / no-reply digest mail
    """
    message_id = msg_data.get('id')
    thread_id = msg_data.get('threadId')
    snippet = msg_data.get('snippet', '')
    internal_date_ms = int(msg_data.get('internalDate', '0'))
    gmail_labels = list(msg_data.get('labelIds', []) or [])

    if internal_date_ms > 0:
        received_at = datetime.datetime.fromtimestamp(internal_date_ms / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    else:
        received_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    payload = msg_data.get('payload', {})
    headers = payload.get('headers', [])

    header_dict = {}
    for h in headers:
        header_dict[h.get('name', '').lower()] = h.get('value', '')

    subject = header_dict.get('subject', 'No Subject')
    from_header = header_dict.get('from', '')

    # Parse From header: "Recruiter Name <recruiter@company.com>"
    sender_name = ''
    sender_email = ''
    match_from = re.match(r'^(.*?)\s*<([^>]+)>$', from_header.strip())
    if match_from:
        sender_name = match_from.group(1).strip(' "\'')
        sender_email = match_from.group(2).strip().lower()
    else:
        sender_email = from_header.strip().lower()
        sender_name = sender_email.split('@')[0] if '@' in sender_email else sender_email

    # Extract Body Parts
    body_text = ""
    body_html = ""

    def extract_parts(part):
        nonlocal body_text, body_html
        mime_type = part.get('mimeType', '')
        data_encoded = part.get('body', {}).get('data', '')

        if data_encoded:
            try:
                decoded_bytes = base64.urlsafe_b64decode(data_encoded.encode('ASCII'))
                decoded_text = decoded_bytes.decode('utf-8', errors='replace')
                if mime_type == 'text/plain' and not body_text:
                    body_text = decoded_text
                elif mime_type == 'text/html' and not body_html:
                    body_html = decoded_text
            except Exception as e:
                logger.warning(f"Error decoding email body part: {e}")

        for subpart in part.get('parts', []):
            extract_parts(subpart)

    extract_parts(payload)

    # If only HTML exists, strip tags for body_text
    if not body_text and body_html:
        clean = re.sub(r'<style[\s\S]*?</style>', ' ', body_html, flags=re.IGNORECASE)
        clean = re.sub(r'<script[\s\S]*?</script>', ' ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        body_text = re.sub(r'\s+', ' ', clean).strip()

    if not body_text:
        body_text = snippet

    body_html_sanitized = sanitize_email_html(body_html) if body_html else None

    # --- Source / folder / bulk signals -------------------------------------
    label_set = {str(lbl).upper() for lbl in gmail_labels}
    if 'SPAM' in label_set:
        source_folder = 'SPAM'
    elif 'TRASH' in label_set:
        source_folder = 'TRASH'
    elif 'SENT' in label_set and 'INBOX' not in label_set:
        source_folder = 'SENT'
    elif 'INBOX' in label_set:
        source_folder = 'INBOX'
    else:
        # Archived / library / all-mail items carry no INBOX label.
        source_folder = 'ARCHIVE'

    list_unsub = (header_dict.get('list-unsubscribe') or '').strip()
    precedence = (header_dict.get('precedence') or '').lower()
    auto_sub = (header_dict.get('auto-submitted') or '').lower()
    has_unsubscribe = bool(list_unsub)
    is_bulk = bool(
        has_unsubscribe
        or precedence in ('bulk', 'list', 'junk')
        or (auto_sub and auto_sub != 'no')
    )

    return {
        'message_id': message_id,
        'thread_id': thread_id,
        'sender_name': sender_name,
        'sender_email': sender_email,
        'subject': subject,
        'snippet': snippet,
        'body_text': body_text,
        'body_html_sanitized': body_html_sanitized,
        'received_at': received_at,
        'gmail_labels': gmail_labels,
        'source_folder': source_folder,
        'has_unsubscribe': has_unsubscribe,
        'is_bulk': is_bulk,
    }

def sanitize_email_html(raw_html):
    """
    Safely sanitizes email HTML:
    - Removes <script>, <style>, <iframe>, <object>, <embed>, <form>, <link>
    - Strips inline event handlers (onclick, onload, onerror, etc.)
    - Disallows javascript: or data: in href and src attributes
    """
    if not raw_html:
        return ""

    # 1. Remove dangerous tags completely
    cleaned = re.sub(r'<(script|style|iframe|object|embed|form|link|applet|meta)[\s\S]*?</\1>', '', raw_html, flags=re.IGNORECASE)
    cleaned = re.sub(r'<(script|style|iframe|object|embed|form|link|applet|meta)[^>]*?>', '', cleaned, flags=re.IGNORECASE)

    # 2. Remove all inline javascript event handlers: on*="..." or on*='...'
    cleaned = re.sub(r'\son\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', '', cleaned, flags=re.IGNORECASE)

    # 3. Disallow javascript: or data: in href/src
    cleaned = re.sub(r'(href|src)\s*=\s*(["\'])\s*(?:javascript|data):[^\2]*?\2', r'\1="#"', cleaned, flags=re.IGNORECASE)

    # 4. Target links to blank and noopener
    cleaned = re.sub(r'<a\s+([^>]*?)>', r'<a \1 target="_blank" rel="noopener noreferrer">', cleaned, flags=re.IGNORECASE)

    return cleaned
