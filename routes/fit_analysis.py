"""FIT Score AI analysis endpoint with server-resolved resume context.

Pipeline: Active Resume -> extracted text -> FIT backend -> AI ->
structured JSON -> UI components. The frontend never sends resume text;
the backend resolves it via services.resume_context so the AI always
analyzes the real active resume and can never be tricked into asking the
user to paste it again.
"""
import logging

from flask import Blueprint, request, jsonify, session

from routes.auth import login_required
from database.db import get_db, get_user_by_id
from services.resume_context import get_active_resume
from services.groq_service import analyze_resume_fit

logger = logging.getLogger(__name__)

fit_analysis_bp = Blueprint('fit_analysis', __name__)


@fit_analysis_bp.route('/api/fit-score/analyze', methods=['POST'])
@login_required
def analyze_fit():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    try:
        application_id = int(data.get('application_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'A target job (application_id) is required.',
                        'retryable': False}), 400

    db = get_db()
    app_row = db.execute(
        'SELECT * FROM applications WHERE id = ? AND user_id = ?', (application_id, user_id)
    ).fetchone()
    if not app_row:
        return jsonify({'success': False, 'error': 'Target job not found.', 'retryable': False}), 404

    job = dict(app_row)
    resume = get_active_resume(user_id)
    if not resume['has_resume']:
        return jsonify({
            'success': False,
            'error': 'No active resume found. Upload a resume in FIT Score first.',
            'retryable': False,
            'error_type': 'NO_RESUME',
        }), 400

    user = get_user_by_id(user_id)
    profile = {}
    if user:
        for key in ('full_name', 'headline', 'location', 'university', 'grad_year', 'phone'):
            try:
                val = user[key]
            except (KeyError, IndexError, TypeError):
                val = None
            if val:
                profile[key] = val

    target_job = {
        'company': job.get('company_name') or '',
        'role': job.get('job_title') or '',
        'location': job.get('location') or '',
        'job_type': job.get('job_type') or '',
        'description': job.get('notes') or '',
    }
    existing_score = job.get('fit_score')

    logger.info("[FIT Analyze] user=%s app=%s (%s - %s) resume=%s score=%s",
                user_id, application_id, target_job['company'], target_job['role'],
                resume['resume_filename'], existing_score)

    analysis, error = analyze_resume_fit(
        resume_text=resume['resume_text'],
        job=target_job,
        profile=profile,
        existing_fit_score=existing_score,
    )
    if error or not analysis:
        logger.warning("[FIT Analyze] failed user=%s app=%s: %s", user_id, application_id, error)
        return jsonify({
            'success': False,
            'error': 'The AI analysis could not be completed. Please try again.',
            'retryable': True,
        }), 502

    return jsonify({
        'success': True,
        'analysis': analysis,
        'target_job': {
            'application_id': application_id,
            'company': target_job['company'],
            'role': target_job['role'],
        },
        'authoritative_fit_score': existing_score,
        'resume_filename': resume['resume_filename'],
        'resume_version': resume['version_name'],
    })
