"""Single reusable resolver for the user's active resume context.

Everything that needs resume content (FIT Score analysis, AI Assistant,
job analysis, resume suggestions) goes through :func:`get_active_resume`
instead of implementing its own loading logic or asking the user to
paste/upload the resume again.
"""
import logging

logger = logging.getLogger(__name__)


def get_active_resume(user_id):
    """Resolve the active resume for a user.

    Returns a dict with:
      - has_resume (bool)
      - resume_text (str, may be '')
      - resume_filename (str)
      - version_name (str, e.g. 'Master Resume (Default)')
      - source ('users' | 'resume_versions' | 'none')
    Never raises: returns has_resume=False on any failure.
    """
    empty = {
        'has_resume': False,
        'resume_text': '',
        'resume_filename': '',
        'version_name': '',
        'source': 'none',
    }
    try:
        from flask import has_app_context
        if not has_app_context():
            return empty
        from database.db import get_db
        db = get_db()
        row = db.execute(
            'SELECT resume_text, resume_filename FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        if row and (row['resume_text'] or '').strip():
            return {
                'has_resume': True,
                'resume_text': row['resume_text'],
                'resume_filename': row['resume_filename'] or 'Master Resume',
                'version_name': 'Master Resume (Default)',
                'source': 'users',
            }
        # Fall back to the most recent saved version with extracted text.
        ver = db.execute(
            '''SELECT version_name, filename, resume_text FROM resume_versions
               WHERE user_id = ? AND resume_text IS NOT NULL AND TRIM(resume_text) != ''
               ORDER BY id DESC LIMIT 1''',
            (user_id,),
        ).fetchone()
        if ver:
            return {
                'has_resume': True,
                'resume_text': ver['resume_text'],
                'resume_filename': ver['filename'] or ver['version_name'],
                'version_name': ver['version_name'],
                'source': 'resume_versions',
            }
    except Exception as e:
        logger.warning(f"get_active_resume failed for user {user_id}: {e}")
    return empty


def build_resume_brief(resume_text, max_chars=3000):
    """Truncate resume text for prompt inclusion with a clear marker."""
    text = (resume_text or '').strip()
    if len(text) > max_chars:
        return text[:max_chars] + '\n[... truncated for length ...]'
    return text
