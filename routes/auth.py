from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, current_app, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from database.db import get_user_by_email, get_user_by_username, get_user_by_id, get_user_by_google_id, create_user

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            if request.path.startswith('/api') or (request.path.startswith('/applications') and request.method != 'GET') or request.is_json:
                return jsonify({'error': 'Authentication required. Please log in.', 'redirect': '/welcome'}), 401
            return redirect(url_for('auth.welcome'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_user_by_id(user_id)

@auth_bp.route('/welcome')
def welcome():
    return render_template('landing.html', current_user=g.user)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('applications.index'))

    error = None
    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        password = request.form.get('password', '')

        if not login_input or not password:
            error = "Please enter your username/email and password."
        else:
            # Check by email or username
            user = get_user_by_email(login_input) or get_user_by_username(login_input)
            if user is None:
                error = "Invalid username/email or password."
            elif not user['password_hash']:
                error = "This account was created with Google Sign-In. Please log in using Google."
            elif not check_password_hash(user['password_hash'], password):
                error = "Invalid username/email or password."
            else:
                session.clear()
                session['user_id'] = user['id']
                next_page = request.args.get('next') or url_for('applications.index')
                return redirect(next_page)

    google_client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    return render_template('login.html', error=error, google_client_id=google_client_id)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if g.user:
        return redirect(url_for('applications.index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not email or not password:
            error = "All fields marked with * are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters long."
        elif get_user_by_email(email):
            error = "Email address is already registered. Please log in instead."
        elif get_user_by_username(username):
            error = "Username is already taken. Please choose another."
        else:
            password_hash = generate_password_hash(password)
            user_id = create_user(username=username, email=email, password_hash=password_hash)
            session.clear()
            session['user_id'] = user_id
            return redirect(url_for('applications.index'))

    google_client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    return render_template('signup.html', error=error, google_client_id=google_client_id)

@auth_bp.route('/auth/google', methods=['POST'])
def google_auth():
    data = request.get_json() or request.form
    token = data.get('credential')

    if not token:
        return jsonify({'error': 'Missing credential token'}), 400

    client_id = current_app.config.get('GOOGLE_CLIENT_ID')

    try:
        # Verify Google OAuth 2.0 ID Token
        # If client_id is placeholder during local development, verify unverified token payload safely
        if not client_id or client_id.startswith('YOUR_GOOGLE_CLIENT_ID'):
            import jwt
            # Decode token payload without signature verification for local testing with dummy token
            id_info = jwt.decode(token, options={"verify_signature": False})
        else:
            id_info = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)

        google_id = id_info.get('sub')
        email = id_info.get('email', '').lower()
        name = id_info.get('name') or email.split('@')[0]
        picture = id_info.get('picture')

        if not email:
            return jsonify({'error': 'Invalid Google account email'}), 400

        # Check existing user by google_id or email
        user = get_user_by_google_id(google_id) or get_user_by_email(email)

        if user:
            user_id = user['id']
        else:
            # Create user for first-time Google login
            # Ensure unique username
            base_username = name.replace(' ', '_').lower()
            username = base_username
            counter = 1
            while get_user_by_username(username):
                username = f"{base_username}_{counter}"
                counter += 1

            user_id = create_user(
                username=username,
                email=email,
                password_hash=None,
                google_id=google_id,
                avatar_url=picture
            )

        session.clear()
        session['user_id'] = user_id
        return jsonify({'success': True, 'redirect': url_for('applications.index')})

    except Exception as e:
        current_app.logger.error(f"Google auth error: {e}")
        return jsonify({'error': f"Google login failed: {str(e)}"}), 400

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
