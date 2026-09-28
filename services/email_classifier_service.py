import datetime
import json
import logging
import re
import urllib.request
from flask import current_app

logger = logging.getLogger(__name__)

VALID_CLASSIFICATIONS = [
    'APPLICATION_RECEIVED',
    'INTERVIEW_INVITATION',
    'INTERVIEW_UPDATE',
    'ASSESSMENT',
    'OFFER',
    'REJECTION',
    'RECRUITER_MESSAGE',
    'FOLLOW_UP',
    'APPLICATION_UPDATE',
    'OTHER_JOB_RELATED',
    'NEEDS_REVIEW',
    'IRRELEVANT',
]

# Classifications that represent a REAL employment/application event. Only
# these may be stored/shown as Email Intelligence. NEEDS_REVIEW /
# OTHER_JOB_RELATED require high confidence (see CONFIDENCE_THRESHOLD);
# IRRELEVANT is never stored.
ACTIONABLE_CLASSIFICATIONS = {
    'APPLICATION_RECEIVED',
    'INTERVIEW_INVITATION',
    'INTERVIEW_UPDATE',
    'ASSESSMENT',
    'OFFER',
    'REJECTION',
    'RECRUITER_MESSAGE',
    'FOLLOW_UP',
    'APPLICATION_UPDATE',
}

CONFIDENCE_THRESHOLD = 0.75

# Strong evidence categories: at least one of these must support inclusion
# when the message looks like bulk / newsletter / digest mail.
STRONG_EVIDENCE_CATEGORIES = {
    'subject_high',
    'ats_sender',
    'recruiter_identity',
    'body_interview',
    'body_assessment',
    'body_offer',
    'body_rejection',
    'body_application',
}

# Job-recommendation / digest / newsletter patterns. These describe
# platform-generated suggestions ("jobs you may like"), NOT a real
# application event or recruiter interaction.
DIGEST_PATTERNS = re.compile(
    r'\b(jobs?\s+(you\s+may\s+(be\s+interested\s+in|like)|picked\s+for\s+you|'
    r'recommended\s+for\s+you|matching\s+your\s+profile|based\s+on\s+your\s+profile)|'
    r'recommended\s+jobs?|similar\s+jobs?|top\s+jobs?\s+for\s+you|'
    r'new\s+jobs?\s+in\b|daily\s+job\s+digest|weekly\s+(job|jobs|career)\b|'
    r'job\s+alerts?\b|jobs?\s+near\s+you|trending\s+jobs?|'
    r'still\s+interested\s+in\b.*\bjobs?|'
    r'view\s+in\s+browser|manage\s+(your\s+)?(email\s+)?(preferences|alerts|subscriptions))\b',
    re.IGNORECASE,
)

CLASSIFICATION_TO_STATUS = {
    'APPLICATION_RECEIVED': 'Applied',
    'APPLICATION_UPDATE': 'Applied',
    'INTERVIEW_INVITATION': 'Interviewing',
    'INTERVIEW_UPDATE': 'Interviewing',
    'ASSESSMENT': 'Interviewing',
    'OFFER': 'Offered',
    'REJECTION': 'Rejected',
    'RECRUITER_MESSAGE': None,
    'FOLLOW_UP': None,
    'OTHER_JOB_RELATED': None,
    'NEEDS_REVIEW': None
}

def evaluate_recruitment_relevance(email_dict, user_applications=None):
    """
    Two-Stage Pre-AI Relevance and Exclusion Engine.
    Filters out non-career noise (receipts, banking, OTPs, marketing, social, travel)
    and verifies multiple positive recruitment signals before AI classification.
    
    Returns: (is_relevant: bool, score: float, reasons: list)
    """
    subject = (email_dict.get('subject') or '').strip()
    body_text = (email_dict.get('body_text') or email_dict.get('snippet') or '').strip()
    sender_name = (email_dict.get('sender_name') or '').strip()
    sender_email = (email_dict.get('sender_email') or '').strip().lower()
    has_unsubscribe = bool(email_dict.get('has_unsubscribe'))
    is_bulk = bool(email_dict.get('is_bulk'))
    source_folder = (email_dict.get('source_folder') or '').upper()

    combined_text = f"{subject}\n{body_text}".lower()
    subject_lower = subject.lower()
    sender_lower = f"{sender_name} {sender_email}".lower()

    # ----------------------------------------------------------------------
    # STAGE 0: OVERRIDE CHECK FOR HIGH-CONFIDENCE INTERVIEW / OFFER / ASSESSMENT IN SUBJECT
    # ----------------------------------------------------------------------
    strong_subject_override = bool(re.search(
        r'\b(interview\s+(?:invitation|invite|scheduled|confirmation|details|process)|'
        r'invitation\s+to\s+interview|virtual\s+interview|technical\s+interview|'
        r'coding\s+assessment|technical\s+assessment|online\s+assessment|assessment\s+invitation|'
        r'job\s+offer|offer\s+letter|offer\s+of\s+employment|pleased\s+to\s+offer|'
        r'congratulations\s+on\s+your\s+offer|we\s+would\s+like\s+to\s+offer)\b',
        subject_lower
    ))

    # ----------------------------------------------------------------------
    # STAGE 1: EXCLUSION RULES (Immediate disqualification unless strong override)
    # ----------------------------------------------------------------------
    if not strong_subject_override:
        # 1. E-Commerce, Orders, Shipping, Deliveries, Invoices
        if re.search(
            r'\b(order\s+(?:confirmation|shipped|placed|delivered|summary|status|update)|'
            r'your\s+order|tracking\s+number|shipment|delivery\s+(?:update|confirmed)|'
            r'invoice\s+(?:attached|#|number|for)|receipt\s+(?:for|from)|'
            r'purchase\s+(?:of|confirmed|details)|cart\s+reminder|return\s+request|'
            r'amazon\s+(?:pay|prime|orders?|delivery|deals|fresh)|flipkart\s+(?:order|delivery|deals)|'
            r'zomato|swiggy|uber\s+eats|doordash|instacart|myntra|ajio|blinkit|zepto)\b',
            combined_text
        ):
            return False, 0.0, ["Excluded: E-Commerce / Order / Delivery notification"]

        # 2. Banking, Payments, Financial transactions
        if re.search(
            r'\b(debited\s+by|credited\s+with|account\s+statement|bank\s+balance|'
            r'credit\s+card\s+bill|payment\s+(?:received|successful|due|failed|alert)|'
            r'transaction\s+(?:successful|failed|alert|details)|upi\s+ref|wire\s+transfer|'
            r'fund\s+transfer|emi\s+due|loan\s+approved|recharge\s+successful|'
            r'billing\s+receipt|wallet\s+balance|paytm|phonepe|gpay)\b',
            combined_text
        ):
            return False, 0.0, ["Excluded: Banking / Payment / Transaction alert"]

        # 3. Security, OTP, Password Reset, Login alerts
        if re.search(
            r'\b(one\s+time\s+password|otp\s+(?:is|to|code)|verification\s+code|security\s+code|'
            r'password\s+reset|reset\s+your\s+password|login\s+(?:alert|from\s+new\s+device|detected)|'
            r'verify\s+your\s+email\s+address|two-factor\s+authentication|2fa\s+code|'
            r'authentication\s+code|security\s+alert)\b',
            combined_text
        ):
            return False, 0.0, ["Excluded: Security / OTP / Password notification"]

        # 4. Marketing, Discounts, Newsletters, Sales
        if re.search(
            r'\b(black\s+friday|cyber\s+monday|sale\s+is\s+live|discount\s+code|'
            r'exclusive\s+deal|promotional|unsubscribe\s+here|view\s+in\s+browser|'
            r'special\s+discount|cashback|deals\s+of\s+the\s+day|limited\s+time\s+deal|'
            r'weekly\s+newsletter|marketing\s+digest|spring\s+sale|mega\s+sale)\b',
            combined_text
        ) and not any(k in subject_lower for k in ['interview', 'application', 'assessment', 'offer', 'recruiter']):
            return False, 0.0, ["Excluded: Promotional / Marketing newsletter"]

        # 5. Travel & Transportation
        if re.search(
            r'\b(flight\s+(?:ticket|booking|status)|boarding\s+pass|hotel\s+booking|'
            r'booking\s+confirmation|trip\s+itinerary|pnr\s+status|check-in\s+reminder|'
            r'train\s+ticket|bus\s+booking|irctc|makemytrip|goibibo|airbnb)\b',
            combined_text
        ):
            return False, 0.0, ["Excluded: Travel / Hospitality booking"]

        # 6. Non-hiring Social & Streaming Notifications
        if re.search(
            r'\b(github\s+sponsored|starred\s+your\s+repository|subscribed\s+to\s+your|'
            r'new\s+follower|liked\s+your\s+post|friend\s+request|youtube\s+(?:video|channel|live)|'
            r'spotify\s+(?:premium|playlist)|netflix\s+(?:watch|subscription|payment))\b',
            combined_text
        ):
            return False, 0.0, ["Excluded: Social / Media notification"]

        # 7. Job-recommendation digests / newsletters / job alerts.
        # A LinkedIn/Indeed "jobs for you" digest is NOT a real application
        # event, even though it mentions jobs. Reject unless the subject
        # itself carries a high-confidence hiring event (handled by override).
        if DIGEST_PATTERNS.search(combined_text):
            if not re.search(
                r'\b(interview|assessment|offer\s+letter|offer\s+of\s+employment|'
                r'application\s+(?:received|submitted|status|update)|rejected|'
                r'not\s+moving\s+forward|recruiter\s+(?:at|from))\b',
                combined_text
            ):
                return False, 0.0, ["Excluded: Job recommendation / digest / alert newsletter"]

    # ----------------------------------------------------------------------
    # STAGE 2: MULTI-SIGNAL RELEVANCE SCORING
    # ----------------------------------------------------------------------
    score = 0.0
    signals = []
    signal_categories = set()

    # Category A: Subject Line Signals (Strongest single indicator)
    if re.search(
        r'\b(interview\s+(?:invitation|invite|scheduled|confirmation|process|details)|'
        r'invitation\s+to\s+interview|virtual\s+interview|technical\s+interview|'
        r'phone\s+screen(?:ing)?|coding\s+(?:interview|round)|onsite\s+interview|hr\s+round)\b',
        subject_lower
    ):
        score += 5.0
        signals.append("Subject: High-confidence interview phrase (+5)")
        signal_categories.add("subject_high")
    elif re.search(
        r'\b(coding\s+assessment|technical\s+assessment|online\s+assessment|'
        r'assessment\s+invitation|hackerrank\s+(?:test|assessment)|codility\s+test|'
        r'take-home\s+(?:challenge|assignment|test))\b',
        subject_lower
    ):
        score += 5.0
        signals.append("Subject: High-confidence assessment phrase (+5)")
        signal_categories.add("subject_high")
    elif re.search(
        r'\b(job\s+offer|offer\s+letter|offer\s+of\s+employment|'
        r'pleased\s+to\s+offer|congratulations\s+on\s+your\s+offer|we\s+would\s+like\s+to\s+offer)\b',
        subject_lower
    ):
        score += 5.0
        signals.append("Subject: High-confidence job offer phrase (+5)")
        signal_categories.add("subject_high")
    elif re.search(
        r'\b(application\s+received|thank\s+you\s+for\s+applying|application\s+submitted|'
        r'application\s+status\s+update|update\s+on\s+your\s+application|'
        r'next\s+steps\s+(?:with|in)\s+your\s+application|your\s+application\s+(?:at|with|for))\b',
        subject_lower
    ):
        score += 4.5
        signals.append("Subject: Application update / confirmation phrase (+4.5)")
        signal_categories.add("subject_high")
    elif re.search(
        r'\b(unfortunately,\s+we\s+will\s+not|not\s+moving\s+forward|'
        r'pursuing\s+other\s+candidates|status:\s*rejected|regret\s+to\s+inform)\b',
        subject_lower
    ):
        score += 4.5
        signals.append("Subject: Rejection update phrase (+4.5)")
        signal_categories.add("subject_high")
    elif re.search(
        r'\b(interview|assessment|recruiter|recruiting|hiring\s+team|'
        r'talent\s+acquisition|job\s+opportunity|career\s+opportunity|candidate\s+portal)\b',
        subject_lower
    ):
        score += 2.0
        signals.append("Subject: Moderate recruitment keyword (+2)")
        signal_categories.add("subject_moderate")

    # Category B: Sender Email & ATS Domain Signals
    ats_domains = [
        'greenhouse.io', 'lever.co', 'smartrecruiters.com', 'ashbyhq.com',
        'myworkday.com', 'workday.com', 'icims.com', 'jobvite.com',
        'taleo.net', 'hackerrank.com', 'codility.com', 'hirevue.com', 'karat.com'
    ]
    if any(domain in sender_email for domain in ats_domains):
        score += 3.0
        signals.append("Sender: Known ATS / Hiring assessment platform domain (+3)")
        signal_categories.add("ats_sender")

    if re.search(r'\b(recruiter|recruiting|talent\s+acquisition|hiring\s+team|careers\s+team)\b', sender_lower):
        score += 2.0
        signals.append("Sender: Recruitment title in sender identity (+2)")
        signal_categories.add("recruiter_identity")

    # Category C: Body Content Combinations
    if 'interview' in combined_text and any(k in combined_text for k in ['scheduled', 'rescheduled', 'zoom.us', 'meet.google.com', 'teams.microsoft.com', 'time slot', 'calendar invite']):
        score += 3.0
        signals.append("Body: Interview scheduling combination (+3)")
        signal_categories.add("body_interview")

    if any(k in combined_text for k in ['assessment', 'coding test', 'hackerrank', 'codility']) and any(k in combined_text for k in ['deadline', 'complete by', 'test link', 'duration', 'take-home']):
        score += 3.0
        signals.append("Body: Assessment instructions combination (+3)")
        signal_categories.add("body_assessment")

    if 'offer' in combined_text and any(k in combined_text for k in ['salary', 'compensation', 'benefits', 'start date', 'joining date', 'congratulations']):
        score += 3.5
        signals.append("Body: Employment offer details combination (+3.5)")
        signal_categories.add("body_offer")

    if any(k in combined_text for k in ['unfortunately', 'regret to inform', 'not moving forward', 'pursuing other candidates']) and any(k in combined_text for k in ['application', 'position', 'role', 'candidates', 'hiring process']):
        score += 3.0
        signals.append("Body: Application rejection combination (+3)")
        signal_categories.add("body_rejection")

    if any(k in combined_text for k in ['application received', 'thank you for applying', 'application submitted', 'reviewing your application']) and any(k in combined_text for k in ['position', 'role', 'candidate', 'resume']):
        score += 2.5
        signals.append("Body: Application acknowledgement combination (+2.5)")
        signal_categories.add("body_application")

    if any(k in combined_text for k in ['recruiter', 'hiring manager', 'talent acquisition']) and any(k in combined_text for k in ['position', 'opportunity', 'role', 'background', 'resume']):
        score += 2.0
        signals.append("Body: Recruiter outreach combination (+2)")
        signal_categories.add("body_recruiter")

    # Category D: Active User Applications Match Signal
    if user_applications and isinstance(user_applications, list):
        for app in user_applications:
            app_comp = (app.get('company_name') or '').strip().lower()
            if app_comp and len(app_comp) >= 3:
                if app_comp in subject_lower or app_comp in sender_lower or f"at {app_comp}" in combined_text or f"with {app_comp}" in combined_text:
                    score += 3.0
                    signals.append(f"Matched active application company: '{app_comp}' (+3)")
                    signal_categories.add("app_match")
                    break

    # ----------------------------------------------------------------------
    # STAGE 3: THRESHOLD VALIDATION
    # ----------------------------------------------------------------------
    is_relevant = (score >= 4.0 and len(signal_categories) >= 2) or (score >= 5.0 and "subject_high" in signal_categories)

    # ----------------------------------------------------------------------
    # STAGE 4: BULK / NEWSLETTER / NON-INBOX GATE
    # Emails carrying bulk signals (List-Unsubscribe, auto-submitted, digest
    # senders) or living outside the INBOX (archive / library / sent / spam)
    # need STRONG hiring-event evidence — a vague "career opportunity"
    # subject plus a matching company name is not enough. This stops
    # newsletters and stale library items from slipping through on weak
    # keyword overlap while still allowing a genuine archived recruiter
    # thread (interview/offer/assessment evidence) to pass on content.
    # ----------------------------------------------------------------------
    bulk_like = has_unsubscribe or is_bulk or DIGEST_PATTERNS.search(combined_text) is not None
    non_inbox = bool(source_folder) and source_folder not in ('INBOX', 'UNKNOWN', '')
    if is_relevant and (bulk_like or non_inbox):
        has_strong = bool(signal_categories.intersection(STRONG_EVIDENCE_CATEGORIES))
        only_weak_combo = signal_categories.issubset({'subject_moderate', 'body_recruiter', 'app_match'})
        if not has_strong or only_weak_combo:
            reasons = list(signals) + [
                "Excluded: bulk/newsletter or non-inbox source without strong hiring-event evidence"
            ]
            logger.info(
                "[Email Relevance Gate] Rejecting '%s' from %s (folder=%s bulk=%s): score=%s categories=%s",
                subject, sender_email, source_folder or 'unknown', bulk_like, score, sorted(signal_categories),
            )
            return False, round(score, 2), reasons
        signals = list(signals) + [
            f"Source check passed: folder={source_folder or 'unknown'} bulk={bulk_like} with strong evidence"
        ]

    return is_relevant, round(score, 2), signals


def classify_email_intelligence(email_dict, user_applications=None):
    """Structured, context-based relevance decision for one email.

    Returns a dict matching the required schema::

        {
          "is_job_related": True/False,
          "category": "<VALID_CLASSIFICATIONS entry>",
          "confidence": 0.0-1.0,
          "reason": "short explanation",
          "classification": "<same as category, legacy alias>",
          "extraction": {...} | None,
          "relevance_score": float,
        }

    Multiple signals are combined (sender, subject, body, labels/folder,
    bulk headers, thread-agnostic app matching) instead of relying on
    keywords or the sender platform alone.
    """
    subject = (email_dict.get('subject') or '').strip()
    sender_email = (email_dict.get('sender_email') or '').strip()
    source_folder = (email_dict.get('source_folder') or 'unknown')

    is_relevant, rel_score, rel_signals = evaluate_recruitment_relevance(email_dict, user_applications)
    if not is_relevant:
        reason = "; ".join(rel_signals[:2]) if rel_signals else "No recruitment signals"
        logger.info(
            "[Email Intelligence] EXCLUDED '%s' from %s (folder=%s score=%s): %s",
            subject, sender_email, source_folder, rel_score, reason,
        )
        return {
            'is_job_related': False,
            'category': 'IRRELEVANT',
            'classification': 'IRRELEVANT',
            'confidence': min(0.9, 0.5 + rel_score / 20.0),
            'reason': f"Excluded (folder={source_folder}, score={rel_score}): {reason}",
            'extraction': None,
            'relevance_score': rel_score,
        }

    extraction = classify_and_extract_email(email_dict)
    classification = (extraction or {}).get('classification', 'NEEDS_REVIEW')
    confidence = float((extraction or {}).get('confidence_score', 0.0) or 0.0)

    # Borderline / vague classifications need high confidence to be shown.
    if classification in ('NEEDS_REVIEW', 'OTHER_JOB_RELATED'):
        if confidence < CONFIDENCE_THRESHOLD or rel_score < 4.5:
            reason = (
                f"Borderline '{classification}' (confidence={confidence:.2f}, "
                f"relevance={rel_score}) below threshold {CONFIDENCE_THRESHOLD}"
            )
            logger.info("[Email Intelligence] EXCLUDED '%s' from %s: %s", subject, sender_email, reason)
            return {
                'is_job_related': False,
                'category': 'IRRELEVANT',
                'classification': 'IRRELEVANT',
                'confidence': confidence,
                'reason': reason,
                'extraction': extraction,
                'relevance_score': rel_score,
            }
        # High-confidence vague match: keep, but flag for review downstream.
        logger.info(
            "[Email Intelligence] INCLUDED (review) '%s' from %s: %s conf=%.2f score=%s",
            subject, sender_email, classification, confidence, rel_score,
        )
        return {
            'is_job_related': True,
            'category': classification,
            'classification': classification,
            'confidence': confidence,
            'reason': f"Relevant but vague ({classification}); folder={source_folder}, score={rel_score}",
            'extraction': extraction,
            'relevance_score': rel_score,
        }

    if classification not in ACTIONABLE_CLASSIFICATIONS:
        classification = 'NEEDS_REVIEW'
        return {
            'is_job_related': False,
            'category': 'IRRELEVANT',
            'classification': 'IRRELEVANT',
            'confidence': confidence,
            'reason': f"Unknown classification '{classification}' treated as irrelevant",
            'extraction': extraction,
            'relevance_score': rel_score,
        }

    logger.info(
        "[Email Intelligence] INCLUDED '%s' from %s: %s conf=%.2f score=%s folder=%s",
        subject, sender_email, classification, confidence, rel_score, source_folder,
    )
    return {
        'is_job_related': True,
        'category': classification,
        'classification': classification,
        'confidence': confidence,
        'reason': f"Real hiring event ({classification}); folder={source_folder}, score={rel_score}",
        'extraction': extraction,
        'relevance_score': rel_score,
    }

def classify_and_extract_email(email_dict):
    """
    Classifies a recruitment email and extracts structured information.
    Attempts Groq AI model first; falls back to robust regex heuristic parser.
    """
    subject = email_dict.get('subject', '')
    snippet = email_dict.get('snippet', '')
    body_text = email_dict.get('body_text', '') or snippet
    sender_name = email_dict.get('sender_name', '')
    sender_email = email_dict.get('sender_email', '')

    api_key = current_app.config.get('GROQ_API_KEY', '').strip() if current_app else ''
    if api_key:
        ai_result = _classify_with_ai(subject, body_text, sender_name, sender_email, api_key)
        if ai_result:
            return ai_result

    # Fallback to deterministic heuristic extraction
    return _classify_with_heuristics(subject, body_text, sender_name, sender_email)

def _classify_with_ai(subject, body_text, sender_name, sender_email, api_key):
    """
    Sends email content to Groq AI for structured classification and extraction.
    """
    system_prompt = (
        "You are an expert recruitment email intelligence analyzer.\n"
        "Analyze the provided job-search email and extract structured recruitment information.\n"
        "Decide from the ACTUAL EMAIL CONTEXT whether this is a REAL employment/application event:\n"
        "- RELEVANT: application confirmations, recruiter outreach about a specific role, interview/assessment scheduling, offers, rejections, hiring-process updates.\n"
        "- IRRELEVANT: job recommendations/digests/alerts, newsletters, marketing/promotional mail, generic platform notifications, course/educational mail, social notifications, personal mail, spam. "
        "An email is NOT job-related merely because it comes from LinkedIn/Indeed/Naukri, mentions 'job'/'career'/'resume', or contains an unsubscribe footer.\n"
        "Return STRICT JSON with exact keys:\n"
        "{\n"
        '  "classification": "<one of: APPLICATION_RECEIVED, INTERVIEW_INVITATION, INTERVIEW_UPDATE, ASSESSMENT, OFFER, REJECTION, RECRUITER_MESSAGE, FOLLOW_UP, APPLICATION_UPDATE, OTHER_JOB_RELATED, NEEDS_REVIEW>",\n'
        '  "company_name": "<detected company name or null>",\n'
        '  "job_title": "<detected job title/role or null>",\n'
        '  "proposed_status": "<one of: Applied, Interviewing, Offered, Rejected, or null>",\n'
        '  "recruiter_name": "<recruiter person name or null>",\n'
        '  "recruiter_email": "<recruiter email or null>",\n'
        '  "interview_date": "<YYYY-MM-DD if explicit interview date is mentioned, else null>",\n'
        '  "interview_time": "<e.g. 10:30 AM or null>",\n'
        '  "interview_type": "<e.g. Technical Interview, Coding Round, HR Screen, or null>",\n'
        '  "meeting_link": "<Google Meet / Zoom / Teams URL or null>",\n'
        '  "assessment_deadline": "<YYYY-MM-DD or deadline string if mentioned, else null>",\n'
        '  "location": "<job location if mentioned or null>",\n'
        '  "salary": "<salary/compensation if mentioned or null>",\n'
        '  "confidence_score": <float between 0.0 and 1.0>,\n'
        '  "key_summary": "<concise 1-2 sentence summary of this update>"\n'
        "}\n\n"
        "Rules:\n"
        "- Do NOT guess or hallucinate missing information; return null for absent values.\n"
        "- If the email is a digest/newsletter/notification rather than a real hiring event, use 'NEEDS_REVIEW' with confidence_score below 0.5.\n"
        "- If uncertain about classification, use 'NEEDS_REVIEW'.\n"
        "- Output ONLY valid JSON."
    )

    user_prompt = (
        f"EMAIL SENDER: {sender_name} <{sender_email}>\n"
        f"EMAIL SUBJECT: {subject}\n"
        f"EMAIL BODY:\n{body_text[:3500]}"
    )

    models_to_try = [
        current_app.config.get('GROQ_MODEL', 'openai/gpt-oss-120b') if current_app else 'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'groq/compound'
    ]

    for model in models_to_try:
        try:
            payload = json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 450,
                'response_format': {'type': 'json_object'}
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
                raw_text = res_data['choices'][0]['message']['content'].strip()

                if raw_text.startswith('```'):
                    raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
                    raw_text = re.sub(r'\s*```$', '', raw_text)

                parsed = json.loads(raw_text)
                if isinstance(parsed, dict) and 'classification' in parsed:
                    cls = parsed.get('classification', 'NEEDS_REVIEW')
                    if cls == 'IRRELEVANT':
                        # AI judged this as non-hiring mail: force below-threshold review.
                        cls = 'NEEDS_REVIEW'
                        parsed['confidence_score'] = min(float(parsed.get('confidence_score', 0.4) or 0.4), 0.4)
                    if cls not in VALID_CLASSIFICATIONS:
                        cls = 'NEEDS_REVIEW'

                    proposed_status = parsed.get('proposed_status') or CLASSIFICATION_TO_STATUS.get(cls)
                    conf = float(parsed.get('confidence_score', 0.85))

                    return {
                        'classification': cls,
                        'company_name': parsed.get('company_name') or _extract_company_fallback(subject, sender_name, sender_email),
                        'job_title': parsed.get('job_title') or _extract_job_title_fallback(subject, body_text),
                        'proposed_status': proposed_status,
                        'recruiter_name': parsed.get('recruiter_name'),
                        'recruiter_email': parsed.get('recruiter_email') or sender_email,
                        'interview_date': parsed.get('interview_date'),
                        'interview_time': parsed.get('interview_time'),
                        'interview_type': parsed.get('interview_type'),
                        'meeting_link': parsed.get('meeting_link') or _extract_meeting_link(body_text),
                        'assessment_deadline': parsed.get('assessment_deadline'),
                        'location': parsed.get('location'),
                        'salary': parsed.get('salary'),
                        'confidence_score': min(1.0, max(0.0, conf)),
                        'key_summary': parsed.get('key_summary') or subject
                    }
        except Exception as e:
            logger.warning(f"AI classification error with {model}: {e}")
            continue

    return None

def _classify_with_heuristics(subject, body_text, sender_name, sender_email):
    """
    Deterministic rule-based classification & extraction when AI API is unavailable.
    Returns NEEDS_REVIEW with low confidence for digests/newsletters so the
    structured decision layer filters them instead of showing them as jobs.
    """
    combined_text = f"{subject}\n{body_text}".lower()

    # Newsletter / digest guard: no real hiring-event phrase -> low-confidence review.
    has_event_phrase = bool(re.search(
        r'(interview|assessment|offer\s+letter|job\s+offer|application\s+(?:received|submitted|status)|'
        r'not\s+moving\s+forward|pursuing\s+other\s+candidates|regret\s+to\s+inform|'
        r'schedule.*interview|recruiter\s+(?:at|from)|talent\s+acquisition)',
        combined_text
    ))
    if DIGEST_PATTERNS.search(f"{subject}\n{body_text}") and not has_event_phrase:
        return {
            'classification': 'NEEDS_REVIEW',
            'company_name': None,
            'job_title': None,
            'proposed_status': None,
            'recruiter_name': None,
            'recruiter_email': sender_email,
            'interview_date': None,
            'interview_time': None,
            'interview_type': None,
            'meeting_link': None,
            'assessment_deadline': None,
            'location': None,
            'salary': None,
            'confidence_score': 0.35,
            'key_summary': subject
        }

    classification = 'OTHER_JOB_RELATED'
    confidence = 0.70

    if any(k in combined_text for k in ['offer letter', 'job offer', 'pleased to offer', 'congratulations on your offer', 'offer of employment']):
        classification = 'OFFER'
        confidence = 0.95
    elif any(k in combined_text for k in ['invitation to interview', 'interview invitation', 'schedule your interview', 'interview scheduled', 'technical round', 'coding round', 'virtual interview', 'onsite interview']):
        classification = 'INTERVIEW_INVITATION'
        confidence = 0.92
    elif any(k in combined_text for k in ['interview updated', 'interview rescheduled', 'interview reminder', 'interview confirmation']):
        classification = 'INTERVIEW_UPDATE'
        confidence = 0.88
    elif any(k in combined_text for k in ['coding assessment', 'online assessment', 'hackerrank', 'codility', 'take-home test', 'technical assessment', 'complete the assessment']):
        classification = 'ASSESSMENT'
        confidence = 0.90
    elif any(k in combined_text for k in ['unfortunately', 'not moving forward', 'pursuing other candidates', 'regret to inform', 'thank you for your interest, but', 'position has been filled', 'status: rejected']):
        classification = 'REJECTION'
        confidence = 0.94
    elif any(k in combined_text for k in ['thank you for applying', 'application received', 'we received your application', 'application submitted', 'application confirmation']):
        classification = 'APPLICATION_RECEIVED'
        confidence = 0.90
    elif any(k in combined_text for k in ['update on your application', 'application status update', 'application in review']):
        classification = 'APPLICATION_UPDATE'
        confidence = 0.82
    elif any(k in combined_text for k in ['reaching out regarding', 'came across your profile', 'are you available for a chat', 'recruiter at', 'talent acquisition']):
        classification = 'RECRUITER_MESSAGE'
        confidence = 0.80

    company = _extract_company_fallback(subject, sender_name, sender_email)
    job_title = _extract_job_title_fallback(subject, body_text)
    meeting_link = _extract_meeting_link(body_text)
    interview_date = _extract_date_fallback(body_text)

    return {
        'classification': classification,
        'company_name': company,
        'job_title': job_title,
        'proposed_status': CLASSIFICATION_TO_STATUS.get(classification),
        'recruiter_name': sender_name if '@' not in sender_name else None,
        'recruiter_email': sender_email,
        'interview_date': interview_date,
        'interview_time': _extract_time_fallback(body_text),
        'interview_type': 'Interview' if 'INTERVIEW' in classification else None,
        'meeting_link': meeting_link,
        'assessment_deadline': None,
        'location': None,
        'salary': None,
        'confidence_score': confidence,
        'key_summary': subject
    }

def _extract_company_fallback(subject, sender_name, sender_email):
    """
    Extracts likely company name from email domain, sender name, or subject.
    """
    # 1. Check sender domain (e.g. recruiter@google.com -> Google)
    if sender_email and '@' in sender_email:
        domain = sender_email.split('@')[1].lower()
        parts = domain.split('.')
        if len(parts) >= 2:
            main_domain = parts[-2]
            generic_domains = ['gmail', 'yahoo', 'outlook', 'hotmail', 'icloud', 'proton', 'linkedin', 'greenhouse', 'lever', 'myworkday', 'indeed', 'smartrecruiters', 'workable', 'ashbyhq']
            if main_domain not in generic_domains and len(main_domain) >= 3:
                return main_domain.capitalize()

    # 2. Check sender name "Recruiter at Company" or "Company Careers"
    match_at = re.search(r'(?:at|from|@)\s+([A-Z][A-Za-z0-9\s&.-]{2,25})', sender_name)
    if match_at:
        return match_at.group(1).strip()

    # 3. Check subject line patterns "Company - Role" or "Interview at Company"
    match_subj_at = re.search(r'(?:at|with|from)\s+([A-Z][A-Za-z0-9\s&.-]{2,25})', subject)
    if match_subj_at:
        return match_subj_at.group(1).strip()

    match_subj_dash = re.search(r'^([A-Z][A-Za-z0-9\s&.-]{2,25})\s*[-:|]\s*', subject)
    if match_subj_dash:
        candidate = match_subj_dash.group(1).strip()
        if candidate.lower() not in ['interview', 'application', 'status', 'update', 'invitation', 're']:
            return candidate

    return None

def _extract_job_title_fallback(subject, body_text):
    """
    Extracts likely job role/title from subject or body.
    """
    role_patterns = [
        r'(?:position|role|job):\s*([A-Za-z0-9\s/-]{3,40})',
        r'for\s+the\s+([A-Za-z0-9\s/-]{3,35})\s+(?:position|role|internship|job)',
        r'[-:|]\s*([A-Za-z0-9\s/-]{3,35})\s*(?:[-:|]|$)'
    ]

    for p in role_patterns:
        m = re.search(p, subject, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            if len(title) > 3 and not any(w in title.lower() for w in ['interview', 'update', 'application', 'invitation', 'schedule']):
                return title

    return None

def _extract_meeting_link(text):
    """
    Finds video meeting link (Google Meet, Zoom, Microsoft Teams, Webex).
    """
    patterns = [
        r'https?://meet\.google\.com/[a-z0-9-]+',
        r'https?://[a-zA-Z0-9.-]+\.zoom\.us/j/[0-9?=&]+',
        r'https?://teams\.microsoft\.com/l/meetup-join/[^\s<>"]+',
        r'https?://[a-zA-Z0-9.-]+\.webex\.com/[^\s<>"]+'
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None

def _extract_date_fallback(text):
    """
    Finds upcoming date in text (e.g. September 5, 2026 or 2026-09-05).
    """
    # ISO Format
    m_iso = re.search(r'\b(202[4-9]-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b', text)
    if m_iso:
        return m_iso.group(1)

    # Word month format (e.g. September 15, 2026)
    m_word = re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,\s*(202[4-9]))?\b', text, re.IGNORECASE)
    if m_word:
        month_name = m_word.group(1).capitalize()
        day = int(m_word.group(2))
        year = int(m_word.group(3)) if m_word.group(3) else datetime.datetime.now().year
        try:
            dt = datetime.datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y")
            return dt.strftime('%Y-%m-%d')
        except:
            pass

    return None

def _extract_time_fallback(text):
    """
    Finds time in text (e.g. 10:30 AM, 2:00 PM EST).
    """
    m = re.search(r'\b((?:0?[1-9]|1[0-2]):[0-5]\d\s*(?:AM|PM|am|pm)(?:\s*(?:EST|EDT|PST|PDT|CST|CDT|IST|GMT|UTC))?)\b', text)
    if m:
        return m.group(1).strip()
    return None

def match_email_to_applications(extracted_data, user_applications):
    """
    Multi-signal matching engine:
    Searches user applications based on Company Name, Role, and Recruiter domain.
    Returns:
    - matched_application_id (int or None)
    - match_confidence (0.0 to 1.0)
    - match_reason (str)
    """
    extracted_company = (extracted_data.get('company_name') or '').strip().lower()
    extracted_role = (extracted_data.get('job_title') or '').strip().lower()
    recruiter_email = (extracted_data.get('recruiter_email') or '').strip().lower()

    if not extracted_company and not extracted_role and not recruiter_email:
        return None, 0.0, "No extracted company or role to match"

    best_match_id = None
    highest_score = 0.0
    best_reason = ""

    for app in user_applications:
        score = 0.0
        reasons = []

        app_company = (app['company_name'] or '').strip().lower()
        app_title = (app['job_title'] or '').strip().lower()

        # 1. Company Name Signal (Weight: up to 0.60)
        if extracted_company and app_company:
            if extracted_company == app_company:
                score += 0.60
                reasons.append("Exact company match")
            elif extracted_company in app_company or app_company in extracted_company:
                score += 0.45
                reasons.append("Partial company match")

        # Domain Signal
        if recruiter_email and '@' in recruiter_email and app_company:
            domain = recruiter_email.split('@')[1]
            if app_company in domain:
                score += 0.20
                reasons.append("Email domain matched company")

        # 2. Job Title Signal (Weight: up to 0.35)
        if extracted_role and app_title:
            if extracted_role == app_title:
                score += 0.35
                reasons.append("Exact role match")
            else:
                # Token overlap
                role_tokens = set(re.findall(r'\w+', extracted_role))
                app_tokens = set(re.findall(r'\w+', app_title))
                common = role_tokens.intersection(app_tokens)
                if common:
                    overlap_ratio = len(common) / max(len(role_tokens), len(app_tokens))
                    score += 0.30 * overlap_ratio
                    reasons.append(f"Role keyword overlap ({', '.join(common)})")

        if score > highest_score:
            highest_score = score
            best_match_id = app['id']
            best_reason = "; ".join(reasons)

    # Normalize final score between 0.0 and 1.0
    match_confidence = min(1.0, round(highest_score, 2))

    if match_confidence >= 0.40:
        return best_match_id, match_confidence, best_reason
    return None, match_confidence, "Confidence too low for automatic match"
