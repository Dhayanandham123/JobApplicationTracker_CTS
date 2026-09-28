import os
from flask import Flask, g
from config import Config
from database.db import init_db
from routes.applications import applications_bp
from routes.auth import auth_bp
from routes.chatbot import chatbot_bp
from routes.profile import profile_bp
from routes.resume_versions import resume_versions_bp
from routes.email_intelligence import email_intelligence_bp
from routes.fit_analysis import fit_analysis_bp
from routes.cron import cron_bp
from services.scheduler import start_email_scheduler

def create_app(config_class=Config):
    app = Flask(__name__)
    if isinstance(config_class, dict):
        app.config.from_object(Config)
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    # Initialize database
    with app.app_context():
        init_db()

    # Start background email scheduler (if not testing and not on Vercel)
    is_vercel = os.environ.get('VERCEL') == '1'
    on_cloud_run = bool(os.environ.get('K_SERVICE'))  # reminders run via Cloud Scheduler there
    if not app.config.get('TESTING') and not is_vercel and not on_cloud_run:
        start_email_scheduler(app)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(resume_versions_bp)
    app.register_blueprint(email_intelligence_bp)
    app.register_blueprint(fit_analysis_bp)
    app.register_blueprint(cron_bp)

    @app.context_processor
    def inject_user_context():
        return {
            'current_user': getattr(g, 'user', None),
            'google_client_id': app.config.get('GOOGLE_CLIENT_ID', '')
        }

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
