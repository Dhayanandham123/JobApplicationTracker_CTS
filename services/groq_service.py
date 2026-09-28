import json
import re
import urllib.request
import logging
from flask import current_app

logger = logging.getLogger(__name__)

FIT_STATUS_LABELS = ('PRESENT', 'MISSING', 'POTENTIALLY_RELEVANT', 'NEEDS_VERIFICATION')
FIT_PRIORITIES = ('HIGH', 'MEDIUM', 'LOW')

def compute_fit_score(jd_text, resume_text):
    """
    Sends job description (jd_text) and candidate resume (resume_text) to Groq AI API
    and requests STRICT JSON output:
    {"fit_score": <0-100 int>, "missing_skills": ["skill1", "skill2", ...]}
    Handles errors gracefully by returning (None, []).
    """
    if not jd_text or not resume_text:
        return None, []

    api_key = current_app.config.get('GROQ_API_KEY', '').strip() if current_app else ''
    if not api_key:
        logger.warning("Missing GROQ_API_KEY for compute_fit_score")
        return None, []

    system_prompt = (
        "You are an expert ATS (Applicant Tracking System) & technical resume recruiter.\n"
        "Compare the candidate's Resume against the Job Description (JD) text.\n"
        "Assess match quality and return STRICT JSON with exact structure:\n"
        "{\n"
        '  "fit_score": <integer from 0 to 100 representing overall percentage match>,\n'
        '  "missing_skills": ["List", "of", "3-6", "key", "required", "skills", "technologies", "or", "qualifications", "missing", "or", "weak", "in", "resume"]\n'
        "}\n\n"
        "Rules:\n"
        "- Do NOT include any intro or conversational text. Output ONLY valid JSON.\n"
        "- Extract ONLY true and accurate details based directly on the provided text. Do NOT hallucinate or guess. If there are no missing skills, leave the list blank ([]).\n"
        "- fit_score must be an integer between 0 and 100.\n"
        "- missing_skills must be a JSON list of concise strings (e.g. ['Kubernetes', 'AWS', 'System Design'])."
    )

    user_prompt = f"JOB DESCRIPTION:\n{jd_text[:4000]}\n\nCANDIDATE RESUME:\n{resume_text[:4000]}"

    models_to_try = [
        current_app.config.get('GROQ_MODEL', 'openai/gpt-oss-120b') if current_app else 'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'groq/compound'
    ]

    for model in models_to_try:
        groq_payload = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.1,
            'max_tokens': 300,
            'response_format': {'type': 'json_object'}
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                'https://api.groq.com/openai/v1/chat/completions',
                data=groq_payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=8) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                raw_content = res_data['choices'][0]['message']['content'].strip()

                if raw_content.startswith('```'):
                    raw_content = re.sub(r'^```(?:json)?\s*', '', raw_content)
                    raw_content = re.sub(r'\s*```$', '', raw_content)

                parsed = json.loads(raw_content)
                if isinstance(parsed, dict):
                    raw_score = parsed.get('fit_score')
                    try:
                        fit_score = int(raw_score)
                        fit_score = max(0, min(100, fit_score))
                    except (ValueError, TypeError):
                        fit_score = None

                    raw_skills = parsed.get('missing_skills', [])
                    if isinstance(raw_skills, list):
                        missing_skills = [str(s).strip() for s in raw_skills if str(s).strip()][:8]
                    else:
                        missing_skills = []

                    return fit_score, missing_skills

        except Exception as e:
            logger.error(f"Groq compute_fit_score error with {model}: {e}")
            continue

    return None, []


def _groq_chat_completion(api_key, model, system_prompt, user_prompt, max_tokens,
                          use_json_mode=True, temperature=0.2, timeout=25):
    """Low-level Groq chat call. Returns (content, finish_reason) or (None, None)."""
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    if use_json_mode:
        payload['response_format'] = {'type': 'json_object'}
    try:
        req = urllib.request.Request(
            'https://api.groq.com/openai/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            choice = res_data['choices'][0]
            return choice['message']['content'], choice.get('finish_reason')
    except Exception as e:
        logger.warning(f"Groq chat error with {model}: {e}")
        return None, None


FIT_ANALYSIS_SCHEMA_HINT = """{
  "fit_score": <integer 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "strengths": [{"title": "...", "detail": "...", "status": "PRESENT"}],
  "improvements": [{"priority": "HIGH|MEDIUM|LOW", "title": "...", "detail": "...",
                    "status": "MISSING|POTENTIALLY_RELEVANT|NEEDS_VERIFICATION",
                    "evidence": "<quote or section from resume/JD supporting this>"}],
  "keywords_present": [{"keyword": "...", "status": "PRESENT"}],
  "keywords_missing": [{"keyword": "...", "status": "MISSING|NEEDS_VERIFICATION"}],
  "final_advice": "<1-2 sentence next step>"
}"""


def validate_fit_analysis(parsed):
    """Validate structured FIT analysis. Returns (cleaned_dict | None, error)."""
    if not isinstance(parsed, dict):
        return None, "Response is not a JSON object"
    cleaned = {}
    try:
        score = int(parsed.get('fit_score'))
    except (TypeError, ValueError):
        return None, "Missing or invalid fit_score"
    cleaned['fit_score'] = max(0, min(100, score))
    cleaned['summary'] = str(parsed.get('summary') or '').strip()
    cleaned['final_advice'] = str(parsed.get('final_advice') or '').strip()
    if not cleaned['summary']:
        return None, "Missing summary"

    def _check_status(s):
        s = str(s or '').strip().upper()
        return s if s in FIT_STATUS_LABELS else 'NEEDS_VERIFICATION'

    strengths = []
    for item in (parsed.get('strengths') or [])[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        if not title:
            continue
        strengths.append({
            'title': title,
            'detail': str(item.get('detail') or '').strip(),
            'status': _check_status(item.get('status') or 'PRESENT'),
        })
    cleaned['strengths'] = strengths

    improvements = []
    for item in (parsed.get('improvements') or [])[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        if not title:
            continue
        prio = str(item.get('priority') or 'MEDIUM').strip().upper()
        improvements.append({
            'priority': prio if prio in FIT_PRIORITIES else 'MEDIUM',
            'title': title,
            'detail': str(item.get('detail') or '').strip(),
            'status': _check_status(item.get('status')),
            'evidence': str(item.get('evidence') or '').strip(),
        })
    cleaned['improvements'] = improvements

    def _kw_list(key):
        out = []
        for item in (parsed.get(key) or [])[:20]:
            if isinstance(item, dict):
                kw = str(item.get('keyword') or '').strip()
                if kw:
                    out.append({'keyword': kw, 'status': _check_status(item.get('status'))})
            elif isinstance(item, str) and item.strip():
                default = 'PRESENT' if key == 'keywords_present' else 'MISSING'
                out.append({'keyword': item.strip(), 'status': default})
        return out

    cleaned['keywords_present'] = _kw_list('keywords_present')
    cleaned['keywords_missing'] = _kw_list('keywords_missing')
    return cleaned, None


def analyze_resume_fit(resume_text, job, profile, existing_fit_score):
    """Analyze the active resume against a target job via Groq structured output.

    - resume_text: actual extracted resume content (required).
    - job: dict with company, role, location, job_type, description.
    - profile: dict of user profile fields (clearly labeled as PROFILE data).
    - existing_fit_score: authoritative deterministic score (may be None).

    Returns (cleaned_analysis_dict | None, error_str | None).
    The authoritative score is enforced server-side: the model is instructed
    to reuse it, and the returned fit_score is overwritten with it when set.
    """
    api_key = current_app.config.get('GROQ_API_KEY', '').strip() if current_app else ''
    if not api_key:
        return None, "AI service is not configured (missing GROQ_API_KEY)."
    if not (resume_text or '').strip():
        return None, "No active resume text found. Upload a resume first."

    score_line = (
        f"The authoritative Application Fit Score computed by the app is "
        f"{existing_fit_score}%. You MUST report exactly this value as fit_score "
        f"and explain it; do NOT invent a different score."
        if existing_fit_score is not None else
        "No authoritative score exists yet. Estimate fit_score honestly from the evidence."
    )

    system_prompt = (
        "You are an expert ATS recruiter and resume coach. Compare the candidate's "
        "RESUME DATA against the TARGET JOB and return STRICT JSON only.\n"
        "Response schema:\n" + FIT_ANALYSIS_SCHEMA_HINT + "\n\n"
        "HARD RULES:\n"
        "- NEVER invent experience, projects, skills, employers, certifications, "
        "education, achievements, or technologies. Every claim must be grounded in "
        "the provided resume, profile, or job text.\n"
        "- Every strength/improvement/keyword MUST carry a status label: PRESENT "
        "(verified in resume), MISSING (required by job, absent from resume), "
        "POTENTIALLY_RELEVANT (related material exists but is underrepresented), "
        "or NEEDS_VERIFICATION (profile data not confirmed in the resume, or conflicting info).\n"
        "- RESUME DATA and PROFILE DATA are different sources. Recommendations about "
        "resume content must be based on RESUME DATA. If profile and resume conflict, "
        "mark NEEDS_VERIFICATION instead of silently merging.\n"
        "- For MISSING items phrase as observation + suggestion, e.g. 'SQL appears in "
        "the job requirements but is not present in the current resume.' NEVER write "
        "'Add SQL experience to your resume' as if the candidate has it.\n"
        "- Output ONLY valid JSON. No markdown, no code fences, no commentary."
    )
    profile_lines = "\n".join(
        f"- {k}: {v}" for k, v in (profile or {}).items() if v
    ) or "(no profile data)"

    user_prompt = (
        f"TARGET JOB:\n"
        f"- Company: {job.get('company', '')}\n"
        f"- Role: {job.get('role', '')}\n"
        f"- Location: {job.get('location', '')}\n"
        f"- Job type: {job.get('job_type', '')}\n"
        f"- Description:\n{(job.get('description') or '(no saved description; use role title and company)')[:3000]}\n\n"
        f"RESUME DATA (authoritative for resume recommendations):\n{resume_text[:6000]}\n\n"
        f"PROFILE DATA (supplementary; verify against resume before using):\n{profile_lines}\n\n"
        f"{score_line}"
    )

    models_to_try = [
        current_app.config.get('GROQ_MODEL', 'openai/gpt-oss-120b') if current_app else 'openai/gpt-oss-120b',
        'qwen/qwen3.8-27b',
        'groq/compound'
    ]
    last_error = "AI service did not return a valid analysis."
    for model in models_to_try:
        content, finish = _groq_chat_completion(api_key, model, system_prompt, user_prompt, max_tokens=1500)
        if not content:
            last_error = f"No response from model {model}."
            continue
        cleaned_text = re.sub(r'^```(?:json)?\s*', '', content.strip())
        cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
        try:
            parsed = json.loads(cleaned_text)
        except json.JSONDecodeError:
            # One repair retry with explicit instruction.
            repair_sys = system_prompt + "\nYour previous reply was not valid JSON. Reply with ONLY the JSON object."
            content2, _ = _groq_chat_completion(
                api_key, model, repair_sys,
                f"Re-emit the previous analysis as pure JSON:\n{cleaned_text[:4000]}",
                max_tokens=1500)
            try:
                parsed = json.loads(re.sub(r'^```(?:json)?\s*', '', (content2 or '').strip()))
            except (json.JSONDecodeError, TypeError):
                last_error = f"Model {model} returned malformed output."
                continue
        cleaned, err = validate_fit_analysis(parsed)
        if err:
            last_error = f"Model {model} output failed validation: {err}"
            continue
        if existing_fit_score is not None:
            cleaned['fit_score'] = int(existing_fit_score)
            cleaned['score_source'] = 'application'
        else:
            cleaned['score_source'] = 'ai_assessment'
        return cleaned, None

    return None, last_error
