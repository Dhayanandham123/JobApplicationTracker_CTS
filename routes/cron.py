"""Endpoint for Cloud Scheduler. Replaces the in-process thread, which cannot
run reliably on Cloud Run (instances scale to zero)."""
import os
import hmac
from flask import Blueprint, request, jsonify
from services.email_service import process_automated_stale_reminders, process_upcoming_event_reminders

cron_bp = Blueprint('cron', __name__)


@cron_bp.route('/internal/run-reminders', methods=['POST'])
def run_reminders():
    secret = os.environ.get('CRON_SECRET', '')
    supplied = request.headers.get('X-Cron-Secret', '')
    if not secret or not hmac.compare_digest(secret, supplied):
        return jsonify({'error': 'forbidden'}), 403
    stale = process_automated_stale_reminders()
    events = process_upcoming_event_reminders()
    return jsonify({'stale_followups': stale, 'event_reminders': events})
