import threading
import time
import logging
from services.email_service import process_automated_stale_reminders, process_upcoming_event_reminders

logger = logging.getLogger(__name__)

_scheduler_started = False
_lock = threading.Lock()

def start_email_scheduler(app, check_interval_seconds=3600):
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def run_loop():
        logger.info("Email follow-up & event background scheduler started.")
        # Delay initial run slightly to allow app to fully initialize
        time.sleep(5)
        while True:
            try:
                with app.app_context():
                    stale_count = process_automated_stale_reminders()
                    event_count = process_upcoming_event_reminders()
                    total_sent = stale_count + event_count
                    if total_sent > 0:
                        logger.info(f"Automated scheduler sent {total_sent} email(s) ({stale_count} follow-up, {event_count} 24h event reminders).")
            except Exception as e:
                logger.error(f"Error in email background scheduler: {e}")
            
            time.sleep(check_interval_seconds)

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
