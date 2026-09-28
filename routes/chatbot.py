import json
import urllib.request
import urllib.error
import socket
import logging
from flask import Blueprint, request, jsonify, session, current_app
from routes.auth import login_required
from database.db import get_db
from routes.applications import format_application_row

logger = logging.getLogger(__name__)

chatbot_bp = Blueprint('chatbot', __name__)

def resolve_local_portfolio_query(user_message, apps):
    """Answers common portfolio/application count and status questions directly from local DB."""
    if not user_message:
        return None

    msg_lower = user_message.lower().strip()

    is_how_many = any(phrase in msg_lower for phrase in [
        'how many', 'count of', 'total job', 'total application',
        'number of job', 'number of application', 'how many job', 'how many app'
    ])
    is_job_query = any(word in msg_lower for word in [
        'applied', 'job', 'application', 'interview', 'offer', 'rejection', 'status', 'portfolio'
    ])

    if is_how_many or (is_job_query and any(w in msg_lower for w in ['how', 'total', 'summary', 'list', 'show', 'my'])):
        total = len(apps)
        applied = sum(1 for a in apps if a['status'] == 'Applied')
        interviewing = sum(1 for a in apps if a['status'] == 'Interviewing')
        offered = sum(1 for a in apps if a['status'] == 'Offered')
        rejected = sum(1 for a in apps if a['status'] == 'Rejected')

        if 'interview' in msg_lower and not ('how many' in msg_lower and 'job' in msg_lower):
            reply = f"You currently have **{interviewing}** application(s) in the **Interviewing** stage."
            if interviewing > 0:
                int_list = [
                    f"- **{a['company_name']}** ({a['job_title']})" +
                    (f" — Interview on {a['formatted_interview_date']}" if a.get('formatted_interview_date') else "")
                    for a in apps if a['status'] == 'Interviewing'
                ]
                reply += "\n\n" + "\n".join(int_list)
            return reply

        if 'offer' in msg_lower and not ('how many' in msg_lower and 'job' in msg_lower):
            reply = f"You currently have **{offered}** job offer(s)."
            if offered > 0:
                off_list = [f"- **{a['company_name']}** ({a['job_title']})" for a in apps if a['status'] == 'Offered']
                reply += "\n\n" + "\n".join(off_list)
            return reply

        if 'reject' in msg_lower and not ('how many' in msg_lower and 'job' in msg_lower):
            return f"You currently have **{rejected}** application(s) marked as **Rejected** out of **{total}** total applications."

        if total == 0:
            return "You haven't logged any job applications yet! Click **+ Add Application** to log your first job submission."

        reply = (
            f"📊 **Job Application Portfolio Summary**\n\n"
            f"You have logged a total of **{total}** job application{'s' if total != 1 else ''}:\n\n"
            f"- 📝 **Applied**: {applied}\n"
            f"- 🎤 **Interviewing**: {interviewing}\n"
            f"- 🎉 **Offered**: {offered}\n"
            f"- ❌ **Rejected**: {rejected}\n"
        )
        if apps:
            recent_list = [f"- **{a['company_name']}** — *{a['job_title']}* (`{a['status']}`)" for a in apps[:5]]
            reply += "\n**Logged Applications:**\n" + "\n".join(recent_list)
        return reply

    return None

@chatbot_bp.route('/api/chat', methods=['POST'])
@login_required
def chat():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    history = data.get('history', [])

    if not user_message:
        return jsonify({'error': 'Please provide a message.'}), 400

    api_key = current_app.config.get('GROQ_API_KEY', '').strip()

    if not api_key:
        fallback_msg = (
            "**Groq API Key Required**\n\n"
            "To activate your AI Career Assistant powered by Groq AI, please add your Groq API key to the `.env` file:\n"
            "```env\nGROQ_API_KEY=gsk_your_actual_key_here\n```\n\n"
            "**How to get a FREE key (1 minute):**\n"
            "1. Visit [console.groq.com/keys](https://console.groq.com/keys)\n"
            "2. Sign in with Google / GitHub\n"
            "3. Click **Create API Key** and copy your `gsk_...` key\n"
            "4. Paste it in `.env` and restart the server!"
        )
        return jsonify({
            'reply': fallback_msg,
            'api_key_missing': True
        })

    # Fetch User's Applications to build real-time context
    db = get_db()
    rows = db.execute('SELECT * FROM applications WHERE user_id = ? AND (archived = 0 OR archived IS NULL) ORDER BY last_updated DESC', (user_id,)).fetchall()
    apps = [format_application_row(r) for r in rows]

    app_context_lines = []
    for a in apps:
        line = f"- {a['company_name']} ({a['job_title']}): Status={a['status']}"
        if a.get('formatted_interview_date'):
            line += f", Interview={a['formatted_interview_date']}"
        if a.get('location'):
            line += f", Location={a['location']}"
        if a.get('salary'):
            line += f", Salary={a['salary']}"
        app_context_lines.append(line)

    app_context_str = "\n".join(app_context_lines) if app_context_lines else "No applications logged yet."

    # Fetch User's Synced Career Emails
    email_rows = db.execute('''
        SELECT em.sender_name, em.sender_email, em.subject, em.classification, em.received_at, em.extracted_data,
               a.company_name as app_company, a.job_title as app_role
        FROM email_messages em
        LEFT JOIN applications a ON em.matched_application_id = a.id
        WHERE em.user_id = ? AND (em.is_job_related IS NULL OR em.is_job_related = 1)
        ORDER BY em.received_at DESC
        LIMIT 10
    ''', (user_id,)).fetchall()

    email_context_lines = []
    for em in email_rows:
        cls_clean = em['classification'].replace('_', ' ').title()
        line = f"- [{cls_clean}] From: {em['sender_name'] or em['sender_email']} | Subject: \"{em['subject']}\" | Date: {em['received_at']}"
        if em['app_company']:
            line += f" | Matched: {em['app_company']} - {em['app_role']}"
        email_context_lines.append(line)

    email_context_str = "\n".join(email_context_lines) if email_context_lines else "No synced career emails yet."

    # Active resume context (server-resolved; user never needs to paste it).
    from services.resume_context import get_active_resume, build_resume_brief
    resume_ctx = get_active_resume(user_id)
    if resume_ctx['has_resume']:
        resume_context_str = (
            f"Active resume: {resume_ctx['resume_filename']} ({resume_ctx['version_name']}).\n"
            f"RESUME CONTENT (authoritative — base resume recommendations ONLY on this text):\n"
            f"{build_resume_brief(resume_ctx['resume_text'])}"
        )
    else:
        resume_context_str = "No active resume saved yet. If the user asks for resume feedback, invite them to upload one in FIT Score."

    system_prompt = (
        "You are an expert AI Career Coach & Interview Assistant embedded in the 'Job & Internship Tracker' app. "
        "Your goal is to empower the user in their job search, interview preparation, resume tuning, and follow-up emails.\n\n"
        "Here is the user's real-time job application portfolio:\n"
        f"{app_context_str}\n\n"
        "Here are the user's recent synced career/recruitment emails:\n"
        f"{email_context_str}\n\n"
        "Here is the user's active resume context:\n"
        f"{resume_context_str}\n\n"
        "Guidelines:\n"
        "1. Be direct, encouraging, practical, and highly relevant to their target companies and roles.\n"
        "2. When asked about interview prep, tailor questions specifically to the roles and companies in their tracker.\n"
        "3. When asked about recent emails, status updates, or recruiters to follow up with, answer accurately using the real synced email intelligence above.\n"
        "4. When asked about their resume, use the RESUME CONTENT above — NEVER ask the user to paste/upload a resume that is already active. If no resume is active, say so plainly and point to FIT Score upload.\n"
        "5. NEVER invent experience, projects, skills, employers, certifications, education, or achievements. Ground resume advice in the provided resume content.\n"
        "6. Keep formatting clean with short markdown sections, bullet points, and bold emphasis where helpful. Keep replies focused and complete.\n"
        "7. IMPORTANT: You must ONLY answer questions related to careers, job applications, interview preparation, resumes, and career emails. If the user asks about unrelated topics, politely decline and steer them back to career topics."
    )

    # Build full messages payload
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in history[-6:]:  # include up to last 6 turns for context
        if isinstance(msg, dict) and msg.get('role') in ('user', 'assistant') and msg.get('content'):
            messages.append({'role': msg['role'], 'content': msg['content']})

    messages.append({'role': 'user', 'content': user_message})

    configured_model = current_app.config.get('GROQ_MODEL', 'openai/gpt-oss-120b')
    models_to_try = [configured_model]
    for m in ['openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'groq/compound', 'groq/compound-mini']:
        if m not in models_to_try:
            models_to_try.append(m)

    last_error_msg = ""
    for model_name in models_to_try:
        groq_payload = json.dumps({
            'model': model_name,
            'messages': messages,
            'temperature': 0.7,
            'max_tokens': 2048
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

            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                reply = res_data['choices'][0]['message']['content']
                finish_reason = res_data['choices'][0].get('finish_reason')
                if finish_reason == 'length':
                    reply = reply.rstrip() + (
                        "\n\n*(My reply was cut short by length limits — "
                        "press Regenerate for the complete answer.)*"
                    )
                return jsonify({'reply': reply, 'model': model_name})

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='ignore')
            logger.error(f"Groq API Error for model {model_name} ({e.code}): {error_body}")
            last_error_msg = error_body
            if e.code == 401:
                return jsonify({
                    'reply': "**Invalid Groq API Key**. Please check your `GROQ_API_KEY` in `.env` and verify it starts with `gsk_`."
                })
            continue

        except (urllib.error.URLError, socket.gaierror, TimeoutError, OSError) as e:
            logger.warning(f"Groq API connection network error ({model_name}): {e}")
            last_error_msg = str(e)
            local_reply = resolve_local_portfolio_query(user_message, apps)
            if local_reply:
                return jsonify({
                    'reply': local_reply + "\n\n*(Note: Groq AI service is currently unreachable — answered directly from your local application portfolio.)*",
                    'offline_fallback': True
                })
            return jsonify({
                'reply': (
                    "🌐 **Network / Connection Warning**\n\n"
                    "Unable to reach the Groq AI service (`api.groq.com`).\n\n"
                    "**Troubleshooting Checklist:**\n"
                    "1. Check your internet connection.\n"
                    "2. If you are using a VPN, proxy, or firewall, ensure `api.groq.com` is permitted.\n"
                    "3. All your application data, calendar events, and analytics remain fully saved and operational locally!"
                ),
                'network_error': True
            })

        except Exception as e:
            logger.error(f"Chatbot Exception for model {model_name}: {e}")
            last_error_msg = str(e)
            continue

    # Final fallback if loop ends
    local_reply = resolve_local_portfolio_query(user_message, apps)
    if local_reply:
        return jsonify({
            'reply': local_reply + "\n\n*(Note: Groq AI service unavailable — answered directly from your local application portfolio.)*",
            'offline_fallback': True
        })

    return jsonify({
        'reply': f"Groq API Service Unavailable. Details: {last_error_msg[:120] if last_error_msg else 'Could not connect to Groq AI.'}"
    })
