from flask import Blueprint, request, jsonify, session
from routes.auth import login_required
from database.db import get_db
from routes.applications import format_application_row
from routes.profile import extract_text_from_file, recalculate_user_fit_scores

resume_versions_bp = Blueprint('resume_versions', __name__)

@resume_versions_bp.route('/api/resume-versions', methods=['GET'])
@login_required
def get_resume_versions():
    user_id = session['user_id']
    db = get_db()
    rows = db.execute('SELECT * FROM resume_versions WHERE user_id = ? ORDER BY id ASC', (user_id,)).fetchall()
    versions = [dict(r) for r in rows]
    return jsonify(versions)

@resume_versions_bp.route('/api/resume-versions', methods=['POST'])
@login_required
def create_resume_version():
    user_id = session['user_id']
    data = request.form if request.form else (request.get_json() or {})
    version_name = str(data.get('version_name', '')).strip()

    if not version_name:
        return jsonify({'error': 'Version name is required.'}), 400

    filename = None
    extracted_text = None

    file_storage = request.files.get('resume_file') or request.files.get('file')
    if file_storage and file_storage.filename:
        try:
            filename, extracted_text = extract_text_from_file(file_storage)
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400
        except Exception as err:
            return jsonify({'error': f'Failed to process file: {str(err)}'}), 500

    db = get_db()
    # Check duplicate version name
    existing = db.execute('SELECT * FROM resume_versions WHERE user_id = ? AND LOWER(version_name) = ?', (user_id, version_name.lower())).fetchone()
    
    if existing:
        existing_id = existing['id']
        if filename and extracted_text:
            db.execute('UPDATE resume_versions SET filename = ?, resume_text = ? WHERE id = ?', (filename, extracted_text, existing_id))
            db.commit()
            db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?', (extracted_text, filename, user_id))
            db.commit()
            recalculate_user_fit_scores(user_id, extracted_text)
            
        row = db.execute('SELECT * FROM resume_versions WHERE id = ?', (existing_id,)).fetchone()
        return jsonify(dict(row)), 200

    cursor = db.execute(
        'INSERT INTO resume_versions (user_id, version_name, filename, resume_text) VALUES (?, ?, ?, ?)',
        (user_id, version_name, filename, extracted_text)
    )
    db.commit()

    new_id = cursor.lastrowid
    
    if extracted_text:
        db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?', (extracted_text, filename or version_name, user_id))
        db.commit()
        recalculate_user_fit_scores(user_id, extracted_text)

    row = db.execute('SELECT * FROM resume_versions WHERE id = ?', (new_id,)).fetchone()
    return jsonify(dict(row)), 201

@resume_versions_bp.route('/api/resume-versions/<int:version_id>', methods=['DELETE'])
@login_required
def delete_resume_version(version_id):
    user_id = session['user_id']
    db = get_db()
    existing = db.execute('SELECT * FROM resume_versions WHERE id = ? AND user_id = ?', (version_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Resume version not found'}), 404

    db.execute('DELETE FROM resume_versions WHERE id = ? AND user_id = ?', (version_id, user_id))
    db.commit()
    return jsonify({'success': True, 'id': version_id})

@resume_versions_bp.route('/api/fit-score/select-version', methods=['POST'])
@login_required
def select_resume_version_for_fit_score():
    user_id = session['user_id']
    data = request.get_json() or request.form
    version_id = data.get('version_id')

    db = get_db()
    
    selected_text = ""
    selected_filename = ""
    
    if not version_id or str(version_id).lower() in ['master', 'default', '0']:
        user_row = db.execute('SELECT resume_text, resume_filename FROM users WHERE id = ?', (user_id,)).fetchone()
        selected_text = user_row['resume_text'] if user_row else ""
        selected_filename = user_row['resume_filename'] if user_row else "Master Resume"
    else:
        ver_row = db.execute('SELECT * FROM resume_versions WHERE id = ? AND user_id = ?', (version_id, user_id)).fetchone()
        if not ver_row:
            return jsonify({'error': 'Selected resume version not found.'}), 404
        selected_text = ver_row['resume_text'] or ""
        selected_filename = ver_row['filename'] or ver_row['version_name']
        
        db.execute('UPDATE users SET resume_text = ?, resume_filename = ? WHERE id = ?', (selected_text, selected_filename, user_id))
        db.commit()

    apps_updated = recalculate_user_fit_scores(user_id, selected_text)
    
    return jsonify({
        'success': True,
        'version_id': version_id,
        'filename': selected_filename,
        'resume_text': selected_text,
        'apps_updated': apps_updated
    })

@resume_versions_bp.route('/api/analytics/resume-versions', methods=['GET'])
@login_required
def get_resume_versions_analytics():
    user_id = session['user_id']
    db = get_db()

    versions_rows = db.execute('SELECT * FROM resume_versions WHERE user_id = ? ORDER BY id ASC', (user_id,)).fetchall()
    versions = [dict(r) for r in versions_rows]

    apps_rows = db.execute('SELECT * FROM applications WHERE user_id = ?', (user_id,)).fetchall()
    apps = [format_application_row(r) for r in apps_rows]

    version_names = [v['version_name'] for v in versions]
    for a in apps:
        ver = a.get('resume_version')
        if ver and ver not in version_names:
            version_names.append(ver)

    if not version_names:
        version_names = ['Default / Unspecified']

    stats = []
    for ver in version_names:
        if ver == 'Default / Unspecified':
            ver_apps = [a for a in apps if not a.get('resume_version')]
        else:
            ver_apps = [a for a in apps if a.get('resume_version') == ver]

        total = len(ver_apps)
        interviewing = sum(1 for a in ver_apps if a['status'] == 'Interviewing')
        offered = sum(1 for a in ver_apps if a['status'] == 'Offered')
        rejected = sum(1 for a in ver_apps if a['status'] == 'Rejected')
        applied = sum(1 for a in ver_apps if a['status'] == 'Applied')

        interview_rate = round((interviewing / total * 100), 1) if total > 0 else 0.0
        offer_rate = round((offered / total * 100), 1) if total > 0 else 0.0
        rejection_rate = round((rejected / total * 100), 1) if total > 0 else 0.0

        stats.append({
            'version_name': ver,
            'total': total,
            'applied': applied,
            'interviewing': interviewing,
            'offered': offered,
            'rejected': rejected,
            'interview_rate': interview_rate,
            'offer_rate': offer_rate,
            'rejection_rate': rejection_rate
        })

    return jsonify(stats)
